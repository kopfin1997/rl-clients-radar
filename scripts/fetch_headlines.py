#!/usr/bin/env python3
"""
RL Clients Radar fetch job
- Fetches official pages and third-party RSS feeds
- Outputs data/headlines.json for the static dashboard
- Enriches cards with cover images when available
- Uses client metadata from data/clients.json

Install:
  pip install -r requirements.txt

Run:
  python scripts/fetch_headlines.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
import hashlib
import html
import json
import re

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parents[1]
CLIENTS_PATH = ROOT / "data" / "clients.json"
SOURCES_PATH = ROOT / "data" / "sources.json"
OUT_PATH = ROOT / "data" / "headlines.json"

HEADERS = {
    "User-Agent": "RLClientsRadar/3.0 (+https://redlantern.example; contact: ops@example.com)"
}
RSS_LIMIT = 12
OFFICIAL_LIMIT = 8
MAX_ITEMS = 120
REQUEST_TIMEOUT = 15
MAX_ARTICLE_ENRICH = 36
HOT_TERMS = [
    "launch", "announce", "official", "sign", "calendar", "race",
    "draw", "partnership", "record", "winner", "champion", "opening",
]
NAV_BLOCK_TERMS = [
    "cookie", "privacy", "sign in", "log in", "subscribe", "ticket",
    "fixtures", "results", "standings", "shop", "account", "watch live",
]
DROP_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid",
}
DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})\b"
)
IMAGE_PATTERN = re.compile(r"""<img[^>]+src=["']([^"' >]+)""", re.I)


def clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", clean(text).lower()).strip()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_date(value, fallback: str | None = None) -> str | None:
    if not value:
        return fallback
    try:
        parsed = dateparser.parse(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return fallback


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in DROP_QUERY_PARAMS
    ]
    path = re.sub(r"/+$", "", parsed.path or "") or "/"
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        "",
        urlencode(sorted(query)),
        "",
    ))


def absolute_url(value: str, base_url: str) -> str:
    if not value:
        return ""
    return urljoin(base_url, value.strip())


def valid_image_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    return lower.startswith("http") and not lower.endswith(".svg")


def item_id(url: str, title: str) -> str:
    return hashlib.sha1((normalize_url(url) + title).encode("utf-8")).hexdigest()[:16]


def is_blocked_candidate(value: str, blocked_terms: list[str]) -> bool:
    haystack = normalize_text(value)
    return any(normalize_text(term) in haystack for term in blocked_terms if term)


def item_quality(item: dict) -> tuple[int, int, int, str]:
    source_priority = 1 if item.get("sourceType") == "Official" else 0
    has_image = 1 if item.get("imageUrl") else 0
    return source_priority, has_image, int(item.get("importance", 0)), item.get("publishedAt", "")


def choose_better(existing: dict | None, candidate: dict) -> dict:
    if existing is None:
        return candidate
    return candidate if item_quality(candidate) >= item_quality(existing) else existing


def dedupe_items(items: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    without_url: list[dict] = []
    for item in items:
        url_key = normalize_url(item.get("url", ""))
        if not url_key:
            without_url.append(item)
            continue
        by_url[url_key] = choose_better(by_url.get(url_key), item)

    by_title: dict[str, dict] = {}
    for item in list(by_url.values()) + without_url:
        title_key = normalize_text(f"{item.get('client', '')} {item.get('title', '')}")
        if not title_key:
            continue
        by_title[title_key] = choose_better(by_title.get(title_key), item)
    return list(by_title.values())


def load_client_map() -> dict[str, dict]:
    payload = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
    return {client["name"]: client for client in payload.get("clients", [])}


def keyword_match(client_meta: dict, text: str) -> bool:
    terms = set(client_meta.get("keywords", []))
    terms.update(client_meta.get("aliases", []))
    terms.add(client_meta.get("name", ""))
    lower = normalize_text(text)
    return any(normalize_text(term) in lower for term in terms if term)


def score_item(source_type: str, title: str, summary: str = "") -> int:
    score = 75 if source_type == "Official" else 60
    text = normalize_text(f"{title} {summary}")
    score += sum(5 for term in HOT_TERMS if term in text)
    return min(score, 98)


def feed_image_from_html(value: str, base_url: str) -> str:
    match = IMAGE_PATTERN.search(value or "")
    if not match:
        return ""
    url = absolute_url(match.group(1), base_url)
    return url if valid_image_url(url) else ""


def entry_image(entry, base_url: str) -> str:
    media_content = entry.get("media_content") or []
    for media in media_content:
        url = absolute_url(media.get("url", ""), base_url)
        if valid_image_url(url):
            return url

    media_thumbnail = entry.get("media_thumbnail") or []
    for media in media_thumbnail:
        url = absolute_url(media.get("url", ""), base_url)
        if valid_image_url(url):
            return url

    for link in entry.get("links", []):
        href = absolute_url(link.get("href", ""), base_url)
        kind = (link.get("type") or "").lower()
        if href and link.get("rel") == "enclosure" and kind.startswith("image/"):
            return href

    image = entry.get("image")
    if hasattr(image, "get"):
        href = absolute_url(image.get("href", ""), base_url)
        if valid_image_url(href):
            return href

    for key in ("summary", "description", "content"):
        value = entry.get(key)
        if isinstance(value, list):
            for chunk in value:
                url = feed_image_from_html(chunk.get("value", ""), base_url)
                if url:
                    return url
        else:
            url = feed_image_from_html(value or "", base_url)
            if url:
                return url
    return ""


def meta_content(soup: BeautifulSoup, *attrs: tuple[str, str]) -> str:
    for attr_name, attr_value in attrs:
        tag = soup.find("meta", attrs={attr_name: attr_value})
        if tag and tag.get("content"):
            return clean(tag.get("content", ""))
    return ""


def image_from_soup(soup: BeautifulSoup, base_url: str) -> str:
    candidates = [
        meta_content(
            soup,
            ("property", "og:image"),
            ("name", "twitter:image"),
            ("property", "twitter:image"),
        )
    ]
    for img in soup.find_all("img", src=True):
        candidates.append(img.get("src", ""))
    for value in candidates:
        absolute = absolute_url(value, base_url)
        if valid_image_url(absolute):
            return absolute
    return ""


def extract_article_meta(
    session: requests.Session,
    article_cache: dict[str, dict],
    url: str,
    enrich_state: dict[str, int],
) -> dict:
    url_key = normalize_url(url)
    if not url_key:
        return {}
    if url_key in article_cache:
        return article_cache[url_key]
    if enrich_state["count"] >= MAX_ARTICLE_ENRICH:
        article_cache[url_key] = {}
        return {}

    enrich_state["count"] += 1
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        article_cache[url_key] = {}
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    data = {
        "title": meta_content(soup, ("property", "og:title"), ("name", "twitter:title")),
        "summary": meta_content(
            soup,
            ("property", "og:description"),
            ("name", "description"),
            ("name", "twitter:description"),
        ),
        "imageUrl": image_from_soup(soup, url),
        "publishedAt": None,
    }

    time_tag = soup.find("time")
    if time_tag:
        data["publishedAt"] = parse_date(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))
    if not data["publishedAt"]:
        for attr in ("article:published_time", "og:published_time"):
            value = meta_content(soup, ("property", attr))
            if value:
                data["publishedAt"] = parse_date(value)
                break

    article_cache[url_key] = data
    return data


def looks_like_article(title: str, url: str) -> bool:
    lower = normalize_text(title)
    if len(title) < 18 or len(title) > 140:
        return False
    if sum(ch.isalpha() for ch in title) < 12:
        return False
    if any(term in lower for term in NAV_BLOCK_TERMS):
        return False
    lower_url = url.lower()
    if any(lower_url.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".pdf")):
        return False
    return True


def find_date_near_link(anchor) -> str | None:
    nodes = [anchor]
    parent = getattr(anchor, "parent", None)
    while parent is not None and len(nodes) < 4:
        nodes.append(parent)
        parent = getattr(parent, "parent", None)

    for node in nodes:
        if not hasattr(node, "find"):
            continue
        time_tag = node.find("time")
        if time_tag:
            for candidate in (time_tag.get("datetime"), time_tag.get_text(" ", strip=True)):
                parsed = parse_date(candidate)
                if parsed:
                    return parsed
        for attr in ("datetime", "data-date", "data-datetime", "content"):
            parsed = parse_date(node.get(attr))
            if parsed:
                return parsed
        text = clean(node.get_text(" ", strip=True))
        match = DATE_PATTERN.search(text)
        if match:
            parsed = parse_date(match.group(0))
            if parsed:
                return parsed
    return None


def find_image_near_link(anchor, base_url: str) -> str:
    nodes = [anchor]
    parent = getattr(anchor, "parent", None)
    while parent is not None and len(nodes) < 4:
        nodes.append(parent)
        parent = getattr(parent, "parent", None)

    for node in nodes:
        if not hasattr(node, "find"):
            continue
        img = node.find("img", src=True)
        if img:
            url = absolute_url(img.get("src", ""), base_url)
            if valid_image_url(url):
                return url
        source = node.find("source", srcset=True)
        if source:
            first = source.get("srcset", "").split(",")[0].split(" ")[0]
            url = absolute_url(first, base_url)
            if valid_image_url(url):
                return url
    return ""


def publisher_allowed(source: dict, source_name: str, url: str) -> bool:
    publisher_terms = [normalize_text(value) for value in source.get("publisherAllowlist", [])]
    domain_terms = [normalize_text(value) for value in source.get("domainAllowlist", [])]
    normalized_name = normalize_text(source_name)
    normalized_url = normalize_text(url)
    publisher_match = any(term in normalized_name for term in publisher_terms) if publisher_terms else False
    domain_match = any(term in normalized_url for term in domain_terms) if domain_terms else False

    if publisher_terms or domain_terms:
        return publisher_match or domain_match
    return True


def base_item(source: dict, client_meta: dict, title: str, summary: str, url: str) -> dict:
    return {
        "id": item_id(url, title),
        "client": client_meta["name"],
        "clientShortName": client_meta.get("shortName", client_meta["name"]),
        "clientCategory": client_meta.get("category", "Other"),
        "sourceType": source["sourceType"],
        "title": title,
        "summary": summary,
        "url": url,
    }


def fetch_rss(
    session: requests.Session,
    source: dict,
    client_meta: dict,
    blocked_terms: list[str],
    article_cache: dict[str, dict],
    enrich_state: dict[str, int],
) -> list[dict]:
    try:
        response = session.get(source["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return []

    feed = feedparser.parse(response.content)
    items = []
    for entry in feed.entries[:RSS_LIMIT]:
        title = clean(entry.get("title", ""))
        summary = clean(entry.get("summary", entry.get("description", "")))[:280]
        url = entry.get("link", source["url"])
        blob = f"{title} {summary}"
        if not title or not keyword_match(client_meta, blob):
            continue

        source_meta = entry.get("source")
        source_name = clean(source_meta.get("title", "")) if hasattr(source_meta, "get") else ""
        source_name = source_name or source["label"]
        if is_blocked_candidate(f"{source_name} {url}", blocked_terms):
            continue
        if not publisher_allowed(source, source_name, url):
            continue

        image_url = entry_image(entry, url)
        article_meta = {}
        if not image_url or not summary:
            article_meta = extract_article_meta(session, article_cache, url, enrich_state)
            image_url = image_url or article_meta.get("imageUrl", "")
            if not summary:
                summary = clean(article_meta.get("summary", ""))[:280]

        published = entry.get("published") or entry.get("updated") or entry.get("created")
        item = base_item(
            source,
            client_meta,
            title=title,
            summary=summary or "Verified third-party RSS item. Open source for full context.",
            url=url,
        )
        item.update({
            "sourceName": source_name,
            "publishedAt": parse_date(published, fallback=article_meta.get("publishedAt") or now_iso()),
            "importance": score_item(source["sourceType"], title, summary),
            "verification": "Trusted RSS + keyword match + allowlist pass",
            "imageUrl": image_url or None,
            "imageAlt": title or client_meta["name"],
        })
        items.append(item)
    return items


def fetch_official_page(
    session: requests.Session,
    source: dict,
    client_meta: dict,
    article_cache: dict[str, dict],
    enrich_state: dict[str, int],
) -> list[dict]:
    try:
        response = session.get(source["url"], timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    fetched_at = now_iso()
    for anchor in soup.find_all("a", href=True):
        text = clean(anchor.get_text(" "))
        href = absolute_url(anchor["href"], source["url"])
        if not href.startswith("http") or not looks_like_article(text, href):
            continue
        candidates.append({
            "title": text,
            "url": href,
            "publishedAt": find_date_near_link(anchor) or fetched_at,
            "imageUrl": find_image_near_link(anchor, source["url"]),
        })

    seen = set()
    items = []
    for candidate in candidates:
        url_key = normalize_url(candidate["url"])
        if url_key in seen:
            continue
        seen.add(url_key)

        article_meta = extract_article_meta(session, article_cache, candidate["url"], enrich_state)
        title = candidate["title"] or clean(article_meta.get("title", "")) or client_meta["name"]
        summary = clean(article_meta.get("summary", ""))[:280]
        image_url = candidate["imageUrl"] or article_meta.get("imageUrl", "")
        published_at = candidate["publishedAt"] or article_meta.get("publishedAt") or fetched_at

        item = base_item(
            source,
            client_meta,
            title=title,
            summary=summary or "Official website headline. Open source for the full article and exact official wording.",
            url=candidate["url"],
        )
        item.update({
            "sourceName": source["label"],
            "publishedAt": published_at,
            "importance": score_item(source["sourceType"], title, summary),
            "verification": "Official source",
            "imageUrl": image_url or None,
            "imageAlt": title or client_meta["name"],
        })
        items.append(item)
        if len(items) >= OFFICIAL_LIMIT:
            break
    return items


def build_summary(items: list[dict], sources: list[dict], clients: list[dict]) -> dict:
    covered_clients = {item["client"] for item in items}
    return {
        "trackedClientCount": len(clients),
        "coveredClientCount": len(covered_clients),
        "sourceCount": len(sources),
        "itemCount": len(items),
        "officialItemCount": sum(1 for item in items if item["sourceType"] == "Official"),
        "thirdPartyItemCount": sum(1 for item in items if item["sourceType"] == "Third-party RSS"),
        "coverImageCount": sum(1 for item in items if item.get("imageUrl")),
    }


def main():
    client_map = load_client_map()
    source_payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = source_payload.get("sources", [])
    blocked_terms = source_payload.get("verificationRules", {}).get("blockedDomains", [])
    article_cache: dict[str, dict] = {}
    enrich_state = {"count": 0}
    all_items = []

    with requests.Session() as session:
        session.headers.update(HEADERS)
        for source in sources:
            client_meta = client_map.get(source["client"])
            if not client_meta:
                continue
            method = source.get("method")
            if method == "rss":
                all_items.extend(fetch_rss(session, source, client_meta, blocked_terms, article_cache, enrich_state))
            elif method == "scrape":
                all_items.extend(fetch_official_page(session, source, client_meta, article_cache, enrich_state))

    items = sorted(
        dedupe_items(all_items),
        key=lambda item: (item["publishedAt"], item.get("importance", 0)),
        reverse=True,
    )[:MAX_ITEMS]

    clients = list(client_map.values())
    OUT_PATH.write_text(json.dumps({
        "updatedAt": now_iso(),
        "clients": clients,
        "sources": sources,
        "summary": build_summary(items, sources, clients),
        "items": items,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} verified headline items to {OUT_PATH}")


if __name__ == "__main__":
    main()
