#!/usr/bin/env python3
"""Build The Daily Brief as a static page.

Runs once a day (GitHub Actions). Standard library only, so nothing to install.
- News: official RSS/Atom feeds, read directly from the server (no proxies).
- Research: PubMed E-utilities, newest first, last N days, with "new today" flags.
Output: docs/index.html plus docs/archive/YYYY-MM-DD.html.
"""
import html, json, os, re, sys, time
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(ROOT, "docs")
ARCHIVE = os.path.join(DOCS, "archive")
UA = "DailyBrief/1.0 (personal news digest; GitHub Actions)"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ATOM = "{http://www.w3.org/2005/Atom}"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(url, timeout=25, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # network hiccup: retry once, then give up on this source
            last = e
            time.sleep(2 + i * 3)
    raise last


# ---------------------------------------------------------------- news
def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def clip(s, n=260):
    return s if len(s) <= n else s[: n].rsplit(" ", 1)[0] + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def text_of(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return ""


def parse_feed(raw, source_name):
    root = ET.fromstring(raw)
    items = []
    for it in root.iter("item"):  # RSS 2.0
        items.append({
            "title": strip_tags(text_of(it, "title")),
            "link": text_of(it, "link"),
            "summary": strip_tags(text_of(it, "description")),
            "date": parse_date(text_of(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date")),
        })
    for it in root.iter(ATOM + "entry"):  # Atom
        link = ""
        for l in it.findall(ATOM + "link"):
            if l.get("rel", "alternate") == "alternate":
                link = l.get("href", "")
                break
        items.append({
            "title": strip_tags(text_of(it, ATOM + "title")),
            "link": link,
            "summary": strip_tags(text_of(it, ATOM + "summary", ATOM + "content")),
            "date": parse_date(text_of(it, ATOM + "published", ATOM + "updated")),
        })
    for x in items:
        # Google News appends " - Outlet" to titles and repeats the title as the summary.
        x["title"] = re.sub(r"\s+-\s+" + re.escape(source_name) + r"$", "", x["title"])
        x["title"] = re.sub(r"\s+-\s+(Reuters|AP News|The Associated Press)$", "", x["title"])
        if x["summary"].startswith(x["title"][:40]):
            x["summary"] = ""
        x["summary"] = clip(x["summary"])
    return [x for x in items if x["title"] and x["link"].startswith("http")]


def gather_news(feeds, window_h, now):
    cutoff = now - timedelta(hours=window_h)
    out, seen = [], set()
    for f in feeds:
        block = {"name": f["name"], "home": f.get("home", ""), "items": [], "error": ""}
        try:
            items = parse_feed(fetch(f["url"]), f["name"])
            dated = [x for x in items if x["date"]]
            if dated:
                items = sorted([x for x in dated if x["date"] >= cutoff], key=lambda x: x["date"], reverse=True)
            for x in items:
                key = re.sub(r"\W+", "", x["title"].lower())[:70]
                if key in seen:
                    continue
                seen.add(key)
                block["items"].append(x)
                if len(block["items"]) >= f.get("max", 4):
                    break
            log(f"news  {f['name']}: {len(block['items'])}")
        except Exception as e:
            block["error"] = "Feed unavailable today"
            log(f"news  {f['name']}: FAILED {e!r}")
        out.append(block)
        time.sleep(0.5)
    return out


# ---------------------------------------------------------------- PubMed
def eutils(endpoint, params, email):
    params = dict(params, tool="daily-brief", email=email)
    key = os.environ.get("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    raw = fetch(EUTILS + endpoint + "?" + urllib.parse.urlencode(params), timeout=40)
    time.sleep(0.4 if not key else 0.12)  # stay under NCBI's rate limit
    return raw


def esearch(term, days, email, retmax=12):
    raw = eutils("esearch.fcgi", {"db": "pubmed", "term": term, "reldate": days, "datetype": "edat",
                                  "retmax": retmax, "sort": "pub_date", "retmode": "json"}, email)
    return json.loads(raw)["esearchresult"].get("idlist", [])


def efetch_details(ids, email):
    if not ids:
        return {}
    raw = eutils("efetch.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}, email)
    root = ET.fromstring(raw)
    out = {}
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID") or ""
        a = art.find(".//Article")
        if a is None:
            continue
        title = strip_tags(ET.tostring(a.find("ArticleTitle"), encoding="unicode", method="text")) if a.find("ArticleTitle") is not None else ""
        journal = a.findtext("Journal/ISOAbbreviation") or a.findtext("Journal/Title") or ""
        parts = []
        for t in a.findall("Abstract/AbstractText"):
            txt = strip_tags(ET.tostring(t, encoding="unicode", method="text"))
            lab = t.get("Label")
            parts.append((lab + ": " if lab else "") + txt)
        authors = []
        for au in a.findall("AuthorList/Author"):
            ln = au.findtext("LastName")
            if ln:
                authors.append(ln + " " + (au.findtext("Initials") or ""))
            elif au.findtext("CollectiveName"):
                authors.append(au.findtext("CollectiveName"))
        au_str = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        doi = ""
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
        types = [t.text or "" for t in a.findall("PublicationTypeList/PublicationType")]
        kind = "Review" if any("Review" in t for t in types) else ("Case report" if any("Case Reports" in t for t in types) else "")
        out[pmid] = {"pmid": pmid, "title": title.strip(), "journal": journal, "abstract": " ".join(parts),
                     "authors": au_str.strip(), "doi": doi, "kind": kind}
    return out


def gather_research(topics, days, email):
    out = []
    for t in topics:
        block = {"desk": t["desk"], "label": t["label"], "query": t["query"], "items": [], "error": ""}
        try:
            ids = esearch(t["query"], days, email)
            new_ids = set(esearch(t["query"], 1, email, retmax=50)) if ids else set()
            details = efetch_details(ids, email)
            for i in ids:
                d = details.get(i)
                if d:
                    d["new"] = i in new_ids
                    block["items"].append(d)
            log(f"pubmed {t['label']}: {len(block['items'])} ({len(new_ids)} new)")
        except Exception as e:
            block["error"] = "PubMed didn't respond during today's build"
            log(f"pubmed {t['label']}: FAILED {e!r}")
        out.append(block)
    return out


# ---------------------------------------------------------------- render
def e(s):
    return html.escape(s or "", quote=True)


def story(x, sid):
    return (f'<article class="story" data-id="{sid}"><h3><a href="{e(x["link"])}" target="_blank" rel="noopener">{e(x["title"])}</a></h3>'
            f'<button class="chk" type="button" aria-pressed="false" aria-label="Mark as read">✓</button>'
            + (f'<p>{e(x["summary"])}</p>' if x["summary"] else "") + "</article>")


def news_section(blocks, lane):
    parts = []
    for bi, b in enumerate(blocks):
        head = f'<h4 class="src-h"><a href="{e(b["home"])}" target="_blank" rel="noopener">{e(b["name"])}</a></h4>'
        if b["error"] or not b["items"]:
            msg = b["error"] or "Nothing new in the last day"
            parts.append(head + f'<p class="msg">{e(msg)}. <a href="{e(b["home"])}" target="_blank" rel="noopener">Open the front page</a>.</p>')
        else:
            parts.append(head + "".join(story(x, f"{lane}{bi}-{i}") for i, x in enumerate(b["items"])))
    return "".join(parts)


def paper(p):
    link = f"https://pubmed.ncbi.nlm.nih.gov/{e(p['pmid'])}/"
    badges = ('<span class="new">New today</span>' if p.get("new") else "") + (f'<span class="kind">{e(p["kind"])}</span>' if p.get("kind") else "")
    doi = f' · <a href="https://doi.org/{e(p["doi"])}" target="_blank" rel="noopener">Full text</a>' if p.get("doi") else ""
    abstract = f'<details><summary>Abstract</summary><p>{e(p["abstract"])}</p></details>' if p.get("abstract") else ""
    return (f'<div class="paper"><h3><a href="{link}" target="_blank" rel="noopener">{e(p["title"])}</a></h3>'
            f'<div class="meta">{badges}<i>{e(p["journal"])}</i> · {e(p["authors"])}{doi}</div>{abstract}</div>')


def research_section(blocks, desk, days):
    mine = [b for b in blocks if b["desk"] == desk]
    tabs = "".join(
        f'<button class="tab" role="tab" type="button" aria-selected="{"true" if i == 0 else "false"}" data-t="{desk}{i}">'
        f'{e(b["label"])}<span class="n">{sum(1 for p in b["items"] if p.get("new")) or ""}</span></button>'
        for i, b in enumerate(mine))
    panels = []
    for i, b in enumerate(mine):
        pm = "https://pubmed.ncbi.nlm.nih.gov/?term=" + urllib.parse.quote(b["query"]) + "&sort=date"
        bar = f'<p class="panel-bar">Last {days} days, newest first · <a href="{pm}" target="_blank" rel="noopener">Same search in PubMed</a></p>'
        if b["error"]:
            body = f'<p class="msg">{e(b["error"])}. The PubMed link above always works.</p>'
        elif not b["items"]:
            body = f'<p class="msg">No new papers in the last {days} days for this search.</p>'
        else:
            body = "".join(paper(p) for p in b["items"])
        panels.append(f'<div class="panel" data-p="{desk}{i}"{"" if i == 0 else " hidden"}>{bar}{body}</div>')
    return f'<div class="tabs" role="tablist">{tabs}</div>{"".join(panels)}'


def render(cfg, en, es, research, now_local, archive_dates):
    tpl = open(os.path.join(ROOT, "template.html"), encoding="utf-8").read()
    days = cfg["research_window_days"]
    n_new = sum(1 for b in research for p in b["items"] if p.get("new"))
    arch = "".join(f'<a href="archive/{d}.html">{d}</a>' for d in archive_dates[:30])
    repl = {
        "{{TITLE}}": e(cfg["title"]),
        "{{DATE_ISO}}": now_local.strftime("%Y-%m-%d"),
        "{{DATELINE}}": now_local.strftime("%A, %B %-d, %Y") + " · built " + now_local.strftime("%-I:%M %p"),
        "{{NEWPAPERS}}": str(n_new),
        "{{EN}}": news_section(en, "en"),
        "{{ES}}": news_section(es, "es"),
        "{{BENCH}}": research_section(research, "bench", days),
        "{{PATH}}": research_section(research, "path", days),
        "{{ARCHIVE}}": arch or "<span>No past editions yet.</span>",
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    email = os.environ.get("NCBI_EMAIL") or cfg.get("contact_email", "")
    now = datetime.now(timezone.utc)
    now_local = now + timedelta(hours=cfg.get("timezone_offset_hours", 0))

    en = gather_news(cfg["english"], cfg["news_window_hours"], now)
    es = gather_news(cfg["spanish"], cfg["news_window_hours"], now)
    research = gather_research(cfg["research"], cfg["research_window_days"], email)

    os.makedirs(ARCHIVE, exist_ok=True)
    today = now_local.strftime("%Y-%m-%d")
    # keep ~60 days of archive
    olds = sorted([f[:-5] for f in os.listdir(ARCHIVE) if re.match(r"\d{4}-\d{2}-\d{2}\.html$", f)], reverse=True)
    for d in olds[60:]:
        os.remove(os.path.join(ARCHIVE, d + ".html"))
    past = [d for d in olds[:60] if d != today]

    total = sum(len(b["items"]) for b in en + es)
    if total == 0 and not any(b["items"] for b in research):
        log("Every source failed; keeping yesterday's page instead of publishing an empty one.")
        sys.exit(1)

    page = render(cfg, en, es, research, now_local, past)
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(page)
    # archive copy: links to other archive pages are siblings
    open(os.path.join(ARCHIVE, today + ".html"), "w", encoding="utf-8").write(
        page.replace('href="archive/', 'href="'))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    log(f"built {today}: {total} stories")


if __name__ == "__main__":
    main()
