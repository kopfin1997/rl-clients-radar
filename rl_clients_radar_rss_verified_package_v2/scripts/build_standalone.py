#!/usr/bin/env python3
"""
Build a self-contained standalone HTML file from the latest JSON payloads.

Run:
  python scripts/build_standalone.py
"""
from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CLIENTS_PATH = ROOT / "data" / "clients.json"
SOURCES_PATH = ROOT / "data" / "sources.json"
HEADLINES_PATH = ROOT / "data" / "headlines.json"
OUT_PATH = ROOT / "standalone.html"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def script_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    clients = load_json(CLIENTS_PATH)
    sources = load_json(SOURCES_PATH)
    headlines = load_json(HEADLINES_PATH)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>RL Clients Radar · Standalone Export</title>
<style>
:root{{
  --bg:#f3f6fb;--paper:#fff;--soft:#fbfcff;--line:#e5ebf4;--text:#131a25;--muted:#6a7386;
  --red:#d7282f;--red-soft:#fff0f1;--blue:#2563eb;--blue-soft:#eef4ff;--green:#16a34a;--green-soft:#ecfdf3;--amber:#d97706;--amber-soft:#fff7e8;
  --shadow:0 18px 50px rgba(18,28,45,.075);--r:28px
}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(circle at top left,#fff 0,#f7f9fd 38%,#edf2f8 100%);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:var(--text)}}
a{{text-decoration:none;color:inherit}}
.app{{display:grid;grid-template-columns:270px 1fr;gap:20px;min-height:100vh;padding:18px}}
.side,.card{{background:rgba(255,255,255,.94);border:1px solid var(--line);box-shadow:var(--shadow)}}
.side{{border-radius:30px;padding:20px;display:flex;flex-direction:column}}
.brand{{display:flex;gap:12px;align-items:center;padding-bottom:20px;border-bottom:1px solid var(--line)}}
.logo{{width:46px;height:46px;border-radius:16px;background:linear-gradient(135deg,#ff4852,#b41219);color:#fff;display:grid;place-items:center;font-weight:900}}
.brand h1{{margin:0;font-size:22px;letter-spacing:-.05em}}.brand p{{margin:4px 0 0;color:var(--muted);font-size:12px;line-height:1.45}}
.sideCard{{margin-top:18px;padding:16px;border:1px solid var(--line);border-radius:22px;background:linear-gradient(180deg,#fff,#fbfcff)}}
.sideCard h3,.head h3{{margin:0;font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}
.sideCard p,.sideCard li{{margin:0;color:var(--muted);font-size:13px;line-height:1.55}}.sideCard ul{{padding-left:16px;margin:10px 0 0;display:grid;gap:8px}}
.main{{min-width:0;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px}}
.hero{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:18px}}
.hello h2{{margin:0;font-size:44px;letter-spacing:-.08em;line-height:1}}.hello p{{margin:10px 0 0;color:var(--muted);max-width:720px;line-height:1.6}}
.search{{display:flex;align-items:center;gap:10px;background:#fff;border:1px solid var(--line);border-radius:18px;padding:12px 14px;min-width:390px;box-shadow:0 8px 24px rgba(18,28,45,.04)}} .search input{{border:0;outline:0;background:transparent;width:100%;font:inherit}}
.card{{border-radius:var(--r);padding:18px}} .head{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}} .head span{{font-size:12px;color:var(--muted)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px}} .stat{{background:linear-gradient(180deg,#fff,#fbfcff);border:1px solid var(--line);border-radius:22px;padding:17px}} .stat b{{display:block;font-size:30px;letter-spacing:-.06em}} .stat span{{color:var(--muted);font-size:13px}}
.toolbar{{display:grid;grid-template-columns:minmax(0,1fr) 170px 170px;gap:12px;align-items:center;margin-bottom:14px}} .toolbar select{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:11px 12px;font:inherit;color:var(--text)}}
.clients{{display:flex;gap:10px;overflow:auto;padding:2px 0 4px}} .client{{border:0;background:transparent;display:flex;flex-direction:column;align-items:center;gap:8px;min-width:88px;cursor:pointer;color:#515b6d;font:inherit}} .bubble{{width:62px;height:62px;border-radius:999px;border:1px solid #dfe5ef;background:#fff;display:grid;place-items:center;font-weight:800;box-shadow:0 8px 24px rgba(18,28,45,.05)}} .client.on .bubble{{border:2px solid #f0b5b9;background:#fff6f6}} .client span{{font-size:12px;text-align:center}}
.feed{{display:grid;gap:14px}} .news{{display:grid;grid-template-columns:240px minmax(0,1fr);gap:18px;padding:16px;border:1px solid var(--line);border-radius:24px;background:linear-gradient(180deg,#fff,#fcfdff);box-shadow:0 8px 24px rgba(18,28,45,.045)}} .news.noImage{{grid-template-columns:minmax(0,1fr)}}
.thumb{{min-height:170px;border-radius:20px;background:linear-gradient(135deg,#171c28,#263248 45%,#d7282f);position:relative;overflow:hidden}} .thumb:before{{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(16,22,34,.05),rgba(16,22,34,.62));z-index:1}} .thumb:after{{content:"";position:absolute;right:-35px;bottom:-35px;width:160px;height:160px;border-radius:40px;background:rgba(255,255,255,.13);transform:rotate(22deg);z-index:2}} .thumb img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}} .thumb b{{position:absolute;left:16px;bottom:16px;color:#fff;font-size:28px;letter-spacing:-.06em;line-height:.95;z-index:3}} .label{{position:absolute;left:12px;top:12px;background:#fff;color:var(--red);border:1px solid #f2c5c8;border-radius:999px;padding:7px 10px;font-size:11px;font-weight:750;z-index:3}}
.meta{{display:flex;align-items:center;gap:9px;color:var(--muted);font-size:13px;flex-wrap:wrap}} .dot{{width:30px;height:30px;border-radius:999px;background:#111827;color:#fff;display:grid;place-items:center;font-size:11px;font-weight:800}} .news h4{{margin:12px 0 8px;font-size:30px;letter-spacing:-.06em;line-height:1.05}} .news p{{margin:0;color:#4f586a;line-height:1.56}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}} .badge{{font-size:12px;padding:7px 10px;border-radius:999px;border:1px solid var(--line);background:#fff}} .badge.red{{background:var(--red-soft);color:var(--red);border-color:#f2c9cc}} .badge.green{{background:var(--green-soft);color:var(--green);border-color:#cfeeda}} .badge.blue{{background:var(--blue-soft);color:var(--blue);border-color:#d6e4ff}} .badge.amber{{background:var(--amber-soft);color:var(--amber);border-color:#f4dfb8}}
.actions{{display:flex;justify-content:flex-end;margin-top:14px}} .open{{padding:10px 14px;border-radius:12px;border:1px solid var(--line);background:#fff;color:#536075;font-size:13px}}
.right{{display:grid;gap:16px;align-self:start;position:sticky;top:18px}}
.sideItem{{display:grid;grid-template-columns:58px 1fr;gap:12px;align-items:center;padding:12px;border:1px solid var(--line);border-radius:18px;background:#fff}} .date{{border:1px solid var(--line);border-radius:14px;padding:8px;text-align:center}} .date b{{display:block;font-size:11px;color:var(--red);text-transform:uppercase}} .date span{{display:block;font-size:24px;font-weight:850}} .sideItem h4{{margin:0;font-size:15px}} .sideItem p{{margin:4px 0 0;color:var(--muted);font-size:13px}}
.sources{{display:grid;gap:8px}} .source{{display:flex;justify-content:space-between;gap:10px;border:1px solid var(--line);border-radius:15px;background:#fff;padding:11px}} .source b{{font-size:13px}} .source span{{font-size:12px;color:var(--muted)}} .pill{{font-size:11px;border-radius:999px;padding:6px 9px;background:var(--green-soft);color:var(--green);font-weight:750}} .pill.amber{{background:var(--amber-soft);color:var(--amber)}}
.empty{{padding:30px;text-align:center;color:var(--muted);border:1px dashed #d8deea;border-radius:22px;background:#fff}} .small{{font-size:12px;color:var(--muted);line-height:1.5}}
@media(max-width:1240px){{.app{{grid-template-columns:1fr}}.main{{grid-template-columns:1fr}}.right{{position:relative;top:0;grid-template-columns:1fr 1fr}}.hero{{flex-direction:column}}.search{{min-width:0}}.toolbar{{grid-template-columns:1fr 1fr}}}}
@media(max-width:760px){{.app{{padding:10px}}.hello h2{{font-size:34px}}.right{{grid-template-columns:1fr}}.toolbar{{grid-template-columns:1fr}}.news{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand">
      <div class="logo">RL</div>
      <div>
        <h1>RL Clients Radar</h1>
        <p>Standalone export generated from the latest package data snapshot.</p>
      </div>
    </div>
    <div class="sideCard">
      <h3>Included In Export</h3>
      <ul>
        <li>Tracked clients and client categories</li>
        <li>Full configured source registry</li>
        <li>Latest generated headlines payload at export time</li>
      </ul>
    </div>
    <div class="sideCard">
      <h3>Package Status</h3>
      <p id="sideSummary">Preparing export summary…</p>
    </div>
  </aside>
  <main class="main">
    <section>
      <div class="hero">
        <div class="hello">
          <h2>Verified News Desk</h2>
          <p id="dateLine">Standalone export ready to open locally, share, or archive as a snapshot.</p>
        </div>
        <label class="search"><span>⌕</span><input id="q" placeholder="Search clients, headlines, publishers, topics..."><span style="font-size:12px;color:var(--muted)">HTML</span></label>
      </div>
      <div class="card">
        <div class="head"><h3>Coverage Summary</h3><span id="updatedAt">Embedded snapshot</span></div>
        <div class="stats" id="stats"></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="head"><h3>Filters</h3><span id="clientMeta">Loading clients…</span></div>
        <div class="toolbar">
          <select id="category"><option>All Categories</option></select>
          <select id="type"><option>All Sources</option><option>Official</option><option>Third-party RSS</option></select>
          <select id="sort"><option value="recent">Sort: Most Recent</option><option value="importance">Sort: Highest Score</option></select>
        </div>
        <div class="clients" id="clients"></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="head"><h3>Headline Feed</h3><span id="feedNote">Embedded feed</span></div>
        <div class="feed" id="feed"></div>
      </div>
    </section>
    <aside class="right">
      <div class="card"><div class="head"><h3>Upcoming Events</h3><span>Static rail</span></div><div id="events"></div></div>
      <div class="card"><div class="head"><h3>AI Insight</h3><span>Rule-based</span></div><p class="small" id="insight"></p></div>
      <div class="card"><div class="head"><h3>Source Registry</h3><span id="sourceMeta">Loaded sources</span></div><div class="sources" id="sourceStatus"></div></div>
    </aside>
  </main>
</div>
<script>
const INITIAL_CLIENTS = {script_json(clients)};
const INITIAL_SOURCES = {script_json(sources)};
const INITIAL_HEADLINES = {script_json(headlines)};
let activeClient = 'All', q = '', type = 'All Sources', category = 'All Categories', sortMode = 'recent';
const MAX_FEED_ITEMS = 40;
const MENU_LIKE_PATTERNS = ['official news source','official news hub','official formula 1 hub','latest-news feed','latest-news page','news page lists','currently surfaces','current listed sections include','official source for all team','only place for official'];
const RESERVED_TITLE_PATTERNS = ['news','latest','official','hub',"what's on"];
const events = [
  {{mon:'Jul',day:'6',title:'British Grand Prix',meta:'F1 race weekend'}},
  {{mon:'Jul',day:'13',title:'Berlin E-Prix',meta:'Formula E'}},
  {{mon:'Jul',day:'23',title:'WST event window',meta:'Snooker'}},
  {{mon:'Aug',day:'1',title:'Summer client watch',meta:'Monitor seasonal brand moments'}}
];
const state = {{
  items: Array.isArray(INITIAL_HEADLINES.items) ? INITIAL_HEADLINES.items.filter(item=>!isMenuLikeItem(item)) : [],
  clients: Array.isArray(INITIAL_HEADLINES.clients) && INITIAL_HEADLINES.clients.length ? INITIAL_HEADLINES.clients : (INITIAL_CLIENTS.clients || []),
  sources: Array.isArray(INITIAL_HEADLINES.sources) && INITIAL_HEADLINES.sources.length ? INITIAL_HEADLINES.sources : (INITIAL_SOURCES.sources || []),
  updatedAt: INITIAL_HEADLINES.updatedAt || null
}};
function dateFmt(v){{try{{return new Date(v).toLocaleString('en-GB',{{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}})}}catch(e){{return 'Recent'}}}}
function escapeHtml(s){{return String(s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}}[m]))}}
function normalizeText(s){{return String(s||'').toLowerCase().replace(/\\s+/g,' ').trim()}}
function isMenuLikeItem(item){{
  const title = normalizeText(item.title);
  const summary = normalizeText(item.summary);
  if (!title || RESERVED_TITLE_PATTERNS.includes(title)) return true;
  return MENU_LIKE_PATTERNS.some(pattern => title.includes(pattern) || summary.includes(pattern));
}}
function clientMap(){{return Object.fromEntries(state.clients.map(client => [client.name, client]))}}
function clientInfo(name){{return clientMap()[name] || {{name, shortName:name, category:'Other'}}}}
function clientLabel(name){{return clientInfo(name).shortName || name}}
function categoryNames(){{return ['All Categories', ...Array.from(new Set(state.clients.map(client => client.category).filter(Boolean))).sort((a,b)=>a.localeCompare(b))]}}
function clientNames(){{return ['All', ...state.clients.map(client => client.name)]}}
function matchesCategory(item){{return category === 'All Categories' || clientInfo(item.client).category === category}}
function filteredItems(){{
  const results = state.items.filter(item=>{{
    const blob = `${{item.client}} ${{item.title}} ${{item.summary}} ${{item.sourceName}} ${{item.sourceType}}`.toLowerCase();
    return (activeClient==='All'||item.client===activeClient) &&
      (type==='All Sources'||item.sourceType===type) &&
      matchesCategory(item) &&
      blob.includes(q.toLowerCase());
  }});
  return results.sort((a,b)=>{{
    if(sortMode==='importance') return (b.importance||0) - (a.importance||0) || String(b.publishedAt).localeCompare(String(a.publishedAt));
    return String(b.publishedAt).localeCompare(String(a.publishedAt)) || (b.importance||0) - (a.importance||0);
  }});
}}
function visibleItems(){{return filteredItems().slice(0,MAX_FEED_ITEMS)}}
function renderStats(){{
  const current = filteredItems();
  const official = current.filter(item=>item.sourceType==='Official').length;
  const third = current.filter(item=>item.sourceType==='Third-party RSS').length;
  const withImage = current.filter(item=>item.imageUrl).length;
  const categories = new Set(current.map(item=>clientInfo(item.client).category)).size;
  document.getElementById('stats').innerHTML = [
    [`${{current.length}}`,'Matched headlines'],
    [`${{state.clients.length}}`,'Tracked clients'],
    [`${{state.sources.length}}`,'Configured sources'],
    [`${{withImage}}`,'Cards with cover'],
    [`${{official}}`,'Official cards'],
    [`${{third}}`,'Third-party cards'],
    [`${{categories}}`,'Active categories']
  ].map(item=>`<div class="stat"><b>${{item[0]}}</b><span>${{item[1]}}</span></div>`).join('');
}}
function renderClientFilters(){{
  const list = clientNames().filter(name => name==='All' || category==='All Categories' || clientInfo(name).category===category);
  document.getElementById('clientMeta').textContent = `${{Math.max(clientNames().length-1,0)}} tracked clients`;
  const rail = document.getElementById('clients');
  rail.innerHTML = list.map(name=>`<button class="client ${{activeClient===name?'on':''}}" data-client="${{escapeHtml(name)}}"><div class="bubble">${{escapeHtml(clientLabel(name))}}</div><span>${{escapeHtml(name==='All'?'All clients':name)}}</span></button>`).join('');
  rail.querySelectorAll('.client').forEach(btn=>btn.addEventListener('click',()=>{{activeClient = btn.dataset.client || 'All';render()}}));
}}
function renderCategorySelect(){{
  const select = document.getElementById('category');
  const currentValue = category;
  select.innerHTML = categoryNames().map(value=>`<option>${{escapeHtml(value)}}</option>`).join('');
  select.value = categoryNames().includes(currentValue) ? currentValue : 'All Categories';
  category = select.value;
}}
function dotText(name){{return clientLabel(name).slice(0,3).toUpperCase()}}
function renderFeed(){{
  const items = visibleItems();
  const total = filteredItems().length;
  document.getElementById('feedNote').textContent = `${{total}} result${{total===1?'':'s'}} • standalone export`;
  document.getElementById('feed').innerHTML = items.length ? items.map(item=>`
    <article class="news ${{item.imageUrl ? '' : 'noImage'}}">
      ${{item.imageUrl ? `<div class="thumb">
        <img src="${{escapeHtml(item.imageUrl)}}" alt="${{escapeHtml(item.imageAlt || item.title || item.client)}}" loading="lazy" referrerpolicy="no-referrer">
        <span class="label">${{escapeHtml(item.sourceType)}}</span>
        <b>${{escapeHtml(clientLabel(item.client))}}</b>
      </div>` : ``}}
      <div>
        <div class="meta"><span class="dot">${{escapeHtml(dotText(item.client))}}</span><b>${{escapeHtml(item.client)}}</b><span>${{escapeHtml(clientInfo(item.client).category)}}</span><span>·</span><span>${{dateFmt(item.publishedAt)}}</span><span>·</span><span>${{escapeHtml(item.sourceName)}}</span></div>
        <h4>${{escapeHtml(item.title)}}</h4>
        <p>${{escapeHtml(item.summary || 'No summary available from feed. Open source to review full context.')}}</p>
        <div class="badges">
          <span class="badge ${{item.sourceType==='Official'?'green':'amber'}}">${{escapeHtml(item.sourceType)}}</span>
          <span class="badge blue">${{escapeHtml(item.verification || 'Verified source rule')}}</span>
          <span class="badge red">Score ${{item.importance||60}}</span>
          ${{item.imageUrl ? `<span class="badge green">Real image</span>` : ``}}
        </div>
        <div class="actions"><a class="open" href="${{item.url}}" target="_blank" rel="noreferrer" title="Open source">Open source ↗</a></div>
      </div>
    </article>`).join('') : `<div class="empty">No matching verified headlines in this standalone export.</div>`;
}}
function renderSide(){{
  document.getElementById('events').innerHTML = events.map(event=>`<div class="sideItem"><div class="date"><b>${{event.mon}}</b><span>${{event.day}}</span></div><div><h4>${{event.title}}</h4><p>${{event.meta}}</p></div></div>`).join('');
  const current = filteredItems();
  const coverRate = current.length ? Math.round((current.filter(item=>item.imageUrl).length/current.length)*100) : 0;
  const categoryCount = new Set(current.map(item=>clientInfo(item.client).category)).size;
  document.getElementById('insight').textContent = `${{current.length}} cards match the current filters across ${{categoryCount}} active categories. ${{coverRate}}% of the current result set has a real image URL embedded from a source page or feed.`;
  document.getElementById('sourceMeta').textContent = `${{state.sources.length}} configured sources`;
  document.getElementById('sourceStatus').innerHTML = state.sources.slice().sort((a,b)=>a.client.localeCompare(b.client)).map(source=>`<div class="source"><div><b>${{escapeHtml(source.client)}}</b><span style="display:block">${{escapeHtml(source.label)}}</span></div><span class="pill ${{source.sourceType==='Official'?'':'amber'}}">${{escapeHtml(source.sourceType)}}</span></div>`).join('');
  document.getElementById('sideSummary').textContent = `${{state.clients.length}} tracked clients are grouped across ${{new Set(state.clients.map(client=>client.category)).size}} categories. ${{state.sources.length}} sources are embedded directly in this file.`;
}}
function render(){{
  if(activeClient!=='All'&&!clientNames().includes(activeClient)) activeClient='All';
  if(category!=='All Categories'&&!categoryNames().includes(category)) category='All Categories';
  renderCategorySelect();
  renderStats();
  renderClientFilters();
  renderFeed();
  renderSide();
}}
document.getElementById('updatedAt').textContent = state.updatedAt ? `Embedded snapshot updated ${{dateFmt(state.updatedAt)}}` : 'Embedded snapshot';
document.getElementById('q').addEventListener('input',e=>{{q=e.target.value;render()}});
document.getElementById('type').addEventListener('change',e=>{{type=e.target.value;render()}});
document.getElementById('category').addEventListener('change',e=>{{category=e.target.value;activeClient='All';render()}});
document.getElementById('sort').addEventListener('change',e=>{{sortMode=e.target.value;render()}});
render();
</script>
</body>
</html>
"""
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote standalone export to {OUT_PATH}")


if __name__ == "__main__":
    main()
