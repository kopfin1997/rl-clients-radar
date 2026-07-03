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
CLIENT_OFFICIAL_LIMIT = 4
CLIENT_THIRD_PARTY_LIMIT = 3
HOT_TERMS = [
    "launch", "announce", "official", "sign", "calendar", "race",
    "draw", "partnership", "record", "winner", "champion", "opening",
]
THIRD_PARTY_BLOCK_TERMS = [
    "odds", "sportsbook", "betting", "facebook.com", "free streaming info",
    "watch all of today's games", "q&a", "round-up",
]
FINANCIAL_NOISE_TERMS = [
    "stock price", "share price", "market cap", "shares close",
    "rate hike", "dow jones", "nasdaq", "s&p 500",
]
TRUSTED_PUBLISHER_HINTS = {
    "reuters", "bbc", "espn", "sky sports", "associated press", "ap news",
    "the new york times", "yahoo sports", "motorsport.com", "golfweek",
    "al jazeera", "sports illustrated", "formula 1", "formula e",
    "premier league", "liverpool fc", "juventus.com", "nba.com",
    "dp world tour", "world snooker tour", "andretti global",
}
TRUSTED_DOMAIN_HINTS = {
    "reuters.com", "bbc.com", "bbc.co.uk", "espn.com", "skysports.com",
    "apnews.com", "nytimes.com", "yahoo.com", "motorsport.com",
    "golfweek.usatoday.com", "aljazeera.com", "si.com", "formula1.com",
    "fiaformulae.com", "premierleague.com", "liverpoolfc.com", "juventus.com",
    "nba.com", "dpworldtour.com", "wst.tv", "andrettiglobal.com",
}
NAV_BLOCK_TERMS = [
    "cookie", "privacy", "sign in", "log in", "subscribe", "ticket",
    "fixtures", "results", "standings", "shop", "account", "watch live",
]
GENERIC_TITLE_TERMS = [
    "official news source", "official news hub", "official formula 1 hub",
    "latest news", "latest", "news", "what's on", "news hub", "home",
]
GENERIC_SUMMARY_TERMS = [
    "official source for all team", "current listed sections include",
    "currently surfaces", "latest-news feed", "latest-news page",
    "news page lists", "official site", "the official", "only place for official",
]
STRUCTURAL_BLOCK_HINTS = [
    "nav", "menu", "header", "footer", "breadcrumb", "cookie", "utility",
    "social", "share", "toolbar", "tab", "pagination",
]
CONTENT_SELECTORS = [
    "main article a[href]",
    "article a[href]",
    "main h1 a[href]",
    "main h2 a[href]",
    "main h3 a[href]",
    "main h4 a[href]",
    "[data-testid*='headline'] a[href]",
    "[data-testid*='article'] a[href]",
    "[class*='headline'] a[href]",
    "[class*='article'] a[href]",
    "[class*='story'] a[href]",
]
RESERVED_PATH_SEGMENTS = {
    "news", "latest", "latest-news", "articles", "article", "home",
    "sport", "all", "en", "what's-on", "formula1",
}
BLOCKED_URL_TERMS = {
    "privacy", "policy", "cookie", "terms", "conditions",
    "restaurant-detail", "sustainability", "accessibility",
}
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


def collapse_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(text))


def term_present(term: str, text: str) -> bool:
    normalized_term = normalize_text(term)
    normalized_text = normalize_text(text)
    if not normalized_term or not normalized_text:
        return False

    if len(collapse_text(normalized_term)) <= 3:
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text


def title_signature(text: str) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"\s*[-|]\s+[a-z0-9 .&'™-]+$", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


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


def base_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_root(url: str) -> str:
    host = base_domain(url)
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 2:
        return parts[-2]
    return host


def is_google_news_url(url: str) -> bool:
    return base_domain(url) == "news.google.com"


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
        title_key = title_signature(f"{item.get('client', '')} {item.get('title', '')}")
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
    return any(term_present(term, text) for term in terms if term)


def matched_terms(client_meta: dict, text: str) -> set[str]:
    hits = set()
    for term in client_meta.get("keywords", []) + client_meta.get("aliases", []) + [client_meta.get("name", "")]:
        normalized = normalize_text(term)
        if normalized and term_present(term, text):
            hits.add(normalized)
    return hits


def score_item(source_type: str, title: str, summary: str = "") -> int:
    score = 75 if source_type == "Official" else 60
    text = normalize_text(f"{title} {summary}")
    score += sum(5 for term in HOT_TERMS if term in text)
    return min(score, 98)


def relevance_score(client_meta: dict, title: str, summary: str, source_name: str = "") -> int:
    title_hits = matched_terms(client_meta, title)
    summary_hits = matched_terms(client_meta, summary)
    source_hits = matched_terms(client_meta, source_name)
    score = 0
    score += len(title_hits) * 35
    score += len(summary_hits - title_hits) * 12
    score += len(source_hits - title_hits - summary_hits) * 8
    return score


def trusted_third_party(source_name: str, url: str) -> bool:
    normalized_name = normalize_text(source_name)
    normalized_url = normalize_text(url)
    if any(hint in normalized_name for hint in TRUSTED_PUBLISHER_HINTS):
        return True
    if any(hint in normalized_url for hint in TRUSTED_DOMAIN_HINTS):
        return True
    return False


def third_party_relevant(client_meta: dict, title: str, summary: str, source_name: str, url: str) -> bool:
    combined = normalize_text(f"{title} {summary} {source_name} {url}")
    if any(term in combined for term in THIRD_PARTY_BLOCK_TERMS):
        return False
    if any(term in combined for term in FINANCIAL_NOISE_TERMS):
        return False
    if "stock price & latest news" in combined:
        return False
    if not trusted_third_party(source_name, url):
        return False
    title_hits = matched_terms(client_meta, title)
    summary_hits = matched_terms(client_meta, summary)
    if title_hits:
        return True
    return len(summary_hits) >= 2


def official_identity_terms(client_meta: dict, source: dict) -> set[str]:
    values = {
        client_meta.get("name", ""),
        source.get("label", ""),
    }
    values.update(client_meta.get("aliases", []))

    host = base_domain(source.get("url", ""))
    root = domain_root(source.get("url", ""))
    values.add(host)
    values.add(host.replace(".", " "))
    values.add(root)
    values.add(root.replace("-", " "))

    normalized_terms = set()
    for value in values:
        normalized = normalize_text(value)
        collapsed = collapse_text(value)
        if len(collapsed) < 3:
            continue
        normalized_terms.add(normalized)
        normalized_terms.add(collapsed)
    return normalized_terms


def build_official_identity_map(client_map: dict[str, dict], sources: list[dict]) -> dict[str, set[str]]:
    identity_map: dict[str, set[str]] = {}
    for source in sources:
        if source.get("sourceType") != "Official":
            continue
        client_meta = client_map.get(source.get("client"))
        if not client_meta:
            continue
        identity_map.setdefault(source["client"], set()).update(official_identity_terms(client_meta, source))
    return identity_map


def official_wrapper_source(client_name: str, source_name: str, official_identity_map: dict[str, set[str]]) -> bool:
    normalized_source = normalize_text(source_name)
    collapsed_source = collapse_text(source_name)
    if not normalized_source or len(collapsed_source) < 3:
        return False

    for identity in official_identity_map.get(client_name, set()):
        collapsed_identity = collapse_text(identity)
        normalized_identity = normalize_text(identity)
        if len(collapsed_identity) < 3:
            continue
        if collapsed_source == collapsed_identity:
            return True
        if len(collapsed_identity) >= 6 and collapsed_identity in collapsed_source:
            return True
        if len(normalized_identity) >= 8 and normalized_identity in normalized_source:
            return True
    return False


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


def structural_hint(node) -> str:
    bits = []
    for current in [node] + list(getattr(node, "parents", []))[:4]:
        if not getattr(current, "name", None):
            continue
        bits.append(current.name)
        bits.extend(current.get("class", []) or [])
        if current.get("id"):
            bits.append(current["id"])
    return normalize_text(" ".join(bits))


def is_structural_anchor(anchor) -> bool:
    hint = structural_hint(anchor)
    return any(term in hint for term in STRUCTURAL_BLOCK_HINTS)


def generic_title(title: str) -> bool:
    lower = normalize_text(title)
    if lower in RESERVED_PATH_SEGMENTS:
        return True
    if any(lower == term or lower.startswith(f"{term} ") or lower.endswith(f" {term}") for term in GENERIC_TITLE_TERMS):
        return True
    if lower.startswith("about "):
        return True
    word_count = len(lower.split())
    return word_count <= 2 and any(term == lower for term in ("news", "latest", "official"))


def generic_summary(summary: str) -> bool:
    lower = normalize_text(summary)
    return any(term in lower for term in GENERIC_SUMMARY_TERMS)


def looks_like_article_url(url: str, source_url: str) -> bool:
    normalized = normalize_url(url)
    source_normalized = normalize_url(source_url)
    if not normalized or normalized == source_normalized:
        return False
    parsed = urlparse(normalized)
    source_parsed = urlparse(source_normalized)
    path = re.sub(r"/+$", "", parsed.path or "") or "/"
    source_path = re.sub(r"/+$", "", source_parsed.path or "") or "/"
    if path == "/" or path == source_path:
        return False
    if any(term in path.lower() for term in BLOCKED_URL_TERMS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    last = segments[-1].lower()
    if last in RESERVED_PATH_SEGMENTS:
        return False
    if "." in last and not any(last.endswith(ext) for ext in (".html", ".htm")):
        return False
    if len(segments) >= 2 and segments[-2].lower() in {"tag", "category", "topics"}:
        return False
    if "-" in last or any(ch.isdigit() for ch in last):
        return True
    return len(last) >= 12 or len(segments) >= 3


def content_anchors(soup: BeautifulSoup) -> list:
    anchors = []
    seen = set()
    for selector in CONTENT_SELECTORS:
        for anchor in soup.select(selector):
            href = anchor.get("href")
            key = (id(anchor), href)
            if href and key not in seen:
                seen.add(key)
                anchors.append(anchor)
    if anchors:
        return anchors
    return soup.find_all("a", href=True)


def candidate_title(anchor_title: str, article_meta: dict) -> str:
    anchor_title = clean(anchor_title)
    meta_title = clean(article_meta.get("title", ""))
    if meta_title and not generic_title(meta_title) and len(meta_title) >= len(anchor_title):
        return meta_title
    return anchor_title or meta_title


def good_official_candidate(title: str, summary: str, url: str, source_url: str) -> bool:
    if not looks_like_article(title, url):
        return False
    if generic_title(title):
        return False
    if generic_summary(summary):
        return False
    if not looks_like_article_url(url, source_url):
        return False
    return True


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
    official_identity_map: dict[str, set[str]],
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
        if official_wrapper_source(client_meta["name"], source_name, official_identity_map):
            continue
        if not publisher_allowed(source, source_name, url):
            continue
        if not third_party_relevant(client_meta, title, summary, source_name, url):
            continue

        image_url = entry_image(entry, url)
        article_meta = {}
        if (not image_url or not summary) and not is_google_news_url(url):
            article_meta = extract_article_meta(session, article_cache, url, enrich_state)
            image_url = image_url or article_meta.get("imageUrl", "")
            if not summary:
                summary = clean(article_meta.get("summary", ""))[:280]
        if not third_party_relevant(client_meta, title, summary, source_name, url):
            continue

        published = entry.get("published") or entry.get("updated") or entry.get("created")
        rel_score = relevance_score(client_meta, title, summary, source_name)
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
            "relevanceScore": rel_score,
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
    for anchor in content_anchors(soup):
        text = clean(anchor.get_text(" "))
        href = absolute_url(anchor["href"], source["url"])
        if not href.startswith("http") or is_structural_anchor(anchor):
            continue
        if not looks_like_article(text, href) or not looks_like_article_url(href, source["url"]):
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
        title = candidate_title(candidate["title"], article_meta) or client_meta["name"]
        summary = clean(article_meta.get("summary", ""))[:280]
        image_url = candidate["imageUrl"] or article_meta.get("imageUrl", "")
        published_at = candidate["publishedAt"] or article_meta.get("publishedAt") or fetched_at
        if not good_official_candidate(title, summary, candidate["url"], source["url"]):
            continue

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
            "relevanceScore": relevance_score(client_meta, title, summary, source["label"]) + 20,
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


def final_sort_key(item: dict) -> tuple[int, int, int, str]:
    return (
        1 if item.get("sourceType") == "Official" else 0,
        int(item.get("relevanceScore", 0)),
        int(item.get("importance", 0)),
        item.get("publishedAt", ""),
    )


def cap_items(items: list[dict]) -> list[dict]:
    by_client: dict[str, list[dict]] = {}
    for item in items:
        by_client.setdefault(item["client"], []).append(item)

    capped: list[dict] = []
    for client_items in by_client.values():
        ordered = sorted(client_items, key=final_sort_key, reverse=True)
        official = [item for item in ordered if item.get("sourceType") == "Official"][:CLIENT_OFFICIAL_LIMIT]
        third_party_limit = CLIENT_THIRD_PARTY_LIMIT if official else CLIENT_THIRD_PARTY_LIMIT + 2
        third_party = [item for item in ordered if item.get("sourceType") != "Official"][:third_party_limit]
        capped.extend(official + third_party)
    return capped


def main():
    client_map = load_client_map()
    source_payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = source_payload.get("sources", [])
    blocked_terms = source_payload.get("verificationRules", {}).get("blockedDomains", [])
    official_identity_map = build_official_identity_map(client_map, sources)
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
                all_items.extend(fetch_rss(
                    session,
                    source,
                    client_meta,
                    blocked_terms,
                    official_identity_map,
                    article_cache,
                    enrich_state,
                ))
            elif method == "scrape":
                all_items.extend(fetch_official_page(session, source, client_meta, article_cache, enrich_state))

    items = sorted(cap_items(dedupe_items(all_items)), key=final_sort_key, reverse=True)[:MAX_ITEMS]

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
