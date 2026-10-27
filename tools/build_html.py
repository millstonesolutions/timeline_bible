#!/usr/bin/env python3
"""Build a single-page HTML reader of the Timeline Bible.

    python3 tools/build_html.py

Writes two copies of the same page, generated from the same data and USFM
parsing as tools/build.py (edit data/ and rebuild, never the HTML):
  docs/index.html          standalone page, served by GitHub Pages
  site/artifact.html       body-only copy for publishing as a claude.ai artifact
                           (the artifact host adds the document skeleton)

Each book's text sits in a <template> and is only rendered when the book is
opened, so the page stays quick although it holds the whole Bible.
"""

import glob
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

OUT_PAGES = os.path.join(build.ROOT, "docs", "index.html")
OUT_ARTIFACT = os.path.join(build.ROOT, "site", "artifact.html")

DESCRIPTION = ("The Bible (World English Bible) with an approximate date for every chapter, "
               "the evidence, where scholars disagree, and sources.")

# What the artifact host's skeleton adds, for the standalone copy.
STANDALONE_HEAD = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{DESCRIPTION}">
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
"""


def esc(s):
    return html.escape(str(s), quote=True)


def inline(s):
    """Escape, then apply *italic* and **bold**."""
    s = esc(" ".join(str(s).split()))
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    return s


def blocks(md):
    """Tiny Markdown: paragraphs and pipe tables."""
    out = []
    for chunk in re.split(r"\n\s*\n", md.strip()):
        lines = [l.strip() for l in chunk.strip().splitlines()]
        if lines and lines[0].startswith("|"):
            rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines if not re.match(r"^\|[-| ]+\|$", l)]
            head, body = rows[0], rows[1:]
            t = "<div class=\"tablewrap\"><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
            t += "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
            out.append(t + "</tbody></table></div>")
        else:
            out.append(f"<p>{inline(' '.join(lines))}</p>")
    return "\n".join(out)


# --- Time scale -----------------------------------------------------------------

class Axis:
    def __init__(self, testament):
        t = build.TESTAMENTS[testament]
        self.lo, self.hi = t["axis"]
        self.ticks = t["ticks"]

    def pct(self, y):
        y = max(self.lo, min(self.hi, y))
        return (y - self.lo) / (self.hi - self.lo) * 100

    def ribbon(self, r, label=True):
        ticks = "".join(f'<span class="tick" style="left:{self.pct(y):.2f}%"></span>' for y, _ in self.ticks[1:-1])
        if not r:
            return (f'<div class="ribbon undated" role="img" aria-label="Undated">{ticks}</div>'
                    + ('<div class="ribbon-label">Undated</div>' if label else ""))
        lo, hi = r
        left = self.pct(lo)
        width = max(self.pct(hi + 1) - left, 0.9)
        title = build.fmt_range(r)
        return (f'<div class="ribbon" role="img" aria-label="Date range {esc(title)}">{ticks}'
                f'<span class="bar" style="left:{left:.2f}%;width:{width:.2f}%"></span></div>'
                + (f'<div class="ribbon-label">{esc(title)}</div>' if label else ""))

    def legend(self):
        return '<div class="scale">' + "".join(
            f'<span style="left:{self.pct(y):.2f}%">{t}</span>' for y, t in self.ticks) + "</div>"


AXES = {t: Axis(t) for t in build.TESTAMENTS}


def cite(data, c):
    key, loc = build.split_cite(c)
    s = data.sources[key]
    return f'<a href="#sources" data-src="{key}">{esc(s["short"])}{(", " + esc(loc)) if loc else ""}</a>'


def book_id(book):
    return re.sub(r"[^a-z0-9]+", "-", book["book"].lower()).strip("-")


# --- Books ------------------------------------------------------------------------

def render_scripture(chapter):
    out = []
    notes = dict(chapter["notes"])
    in_poem = False
    for style, verses in chapter["blocks"]:
        if not verses:
            continue
        parts = []
        for verse, text in verses:
            t = esc(text)
            t = re.sub(r"\[\^([\d-]+)\]", lambda m: f'<sup class="fn" title="{esc(notes.get(m.group(1), ""))}">†</sup>', t)
            parts.append((f'<sup class="v">{esc(verse)}</sup>' if verse else "") + t)
        line = " ".join(parts)
        if style.startswith("q"):
            if not in_poem:
                out.append('<div class="poem">')
                in_poem = True
            out.append(f'<span class="{style}">{line}</span>')
            continue
        if in_poem:
            out.append("</div>")
            in_poem = False
        if style == "s":
            out.append(f"<h4>{line}</h4>")
        elif style == "d":
            out.append(f'<p class="title">{line}</p>')
        else:
            out.append(f"<p>{line}</p>")
    if in_poem:
        out.append("</div>")
    if notes:
        out.append('<ol class="notes">' + "".join(f"<li>{esc(b)}</li>" for _, b in chapter["notes"]) + "</ol>")
    return "\n".join(out)


def render_chapter(data, book, n, ch, text):
    bid = book_id(book)
    label, show_written = build.KINDS[book["kind"]]
    label = ch.get("label") or book.get("label") or label
    (an, asub), (bn, bsub) = build.model_labels(book)
    models = ""
    if ch.get("a") or ch.get("b"):
        models = '<dl class="models">'
        if ch.get("a"):
            models += f'<div class="ma"><dt>{esc(an)} <small>{esc(asub)}</small></dt><dd>{esc(ch["a"])}</dd></div>'
        if ch.get("b"):
            models += f'<div class="mb"><dt>{esc(bn)} <small>{esc(bsub)}</small></dt><dd>{esc(ch["b"])}</dd></div>'
        models += "</dl>"
    anchors = ch.get("anchors") or []
    basis = "".join(
        f'<li><a href="#key-dates" data-anchor="{a}">{esc(data.anchors[a]["title"])}</a> '
        f'<span class="when">{esc(data.anchors[a]["date"])}</span><br>{inline(data.anchors[a]["short"])}</li>'
        for a in anchors)
    cites = list(ch.get("sources") or [])
    for a in anchors:
        cites += data.anchors[a].get("sources") or []
    srcs = "; ".join(cite(data, c) for c in build.dedupe(cites))
    detail = ""
    if basis or srcs:
        detail = ('<details><summary>Basis and sources</summary>'
                  + (f"<ul class=\"basis\">{basis}</ul>" if basis else "")
                  + (f'<p class="srcs"><span class="lbl">Sources</span> {srcs}</p>' if srcs else "")
                  + "</details>")
    written = f'<p class="written">Book written {esc(book["written"]["date"])}</p>' if show_written else ""
    note = f'<p class="note">{inline(ch["note"])}</p>' if ch.get("note") else ""
    return f'''<section class="chapter" id="{bid}-{n}">
<h3><span class="bk">{esc(book["book"])}</span> {n}</h3>
<aside class="datecard">
<div class="dc-head"><span class="lbl">{esc(label)}</span><span class="date">{esc(ch["date"])}</span></div>
{AXES[book["testament"]].ribbon(ch.get("range"))}
{models}{note}{detail}{written}
</aside>
<div class="text">{render_scripture(text)}</div>
</section>'''


def render_book(data, book):
    text = build.parse_usfm(build.usfm_path(book))
    chapters = data.chapters(book, len(text))
    w = book["written"]
    bid = book_id(book)
    axis = AXES[book["testament"]]
    views = "".join(
        f'<tr><td class="d">{esc(v["date"])}</td><td>{inline(v.get("held_by", ""))}</td>'
        f'<td>{inline(v.get("basis", ""))}</td><td class="c">{"; ".join(cite(data, c) for c in v.get("sources", []))}</td></tr>'
        for v in w.get("views", []))
    chips = "".join(f'<a href="#{bid}-{n}">{n}</a>' for n in sorted(text))
    kind = {"narrative": "Narrative", "prophecy": "Prophecy", "writing": "Poetry and wisdom", "letter": "Letter"}[book["kind"]]
    head = f'''<header class="bookhead">
<p class="eyebrow">{build.TESTAMENTS[book["testament"]]["title"]} · {kind} · {len(text)} chapter{"s" if len(text) > 1 else ""}</p>
<h2>{esc(book["book"])}</h2>
<div class="writing">
<div class="dc-head"><span class="lbl">Date of writing</span><span class="date">{esc(w["date"])}</span></div>
{axis.ribbon(w.get("range"))}
<p>{inline(w["summary"])}</p>
<div class="tablewrap"><table class="views"><thead><tr><th>Date</th><th>Held by</th><th>Basis</th><th>Sources</th></tr></thead><tbody>{views}</tbody></table></div>
</div>
<nav class="chips" aria-label="Chapters">{chips}</nav>
</header>'''
    body = "\n".join(render_chapter(data, book, n, chapters[n], text[n]) for n in sorted(text))
    return f'<template id="tpl-{bid}">{head}{body}</template>', chapters


# --- Other views ------------------------------------------------------------------

def render_timeline(data, all_ch):
    secs = ""
    for t, cfg in build.TESTAMENTS.items():
        rows = build.timeline_rows(data, t, all_ch)
        if not rows:
            continue
        axis = AXES[t]
        items = "".join(
            f'<li class="{r["kind"]}"><a href="#{book_id(r["book"])}-{r["first"]}">{esc(build.row_label(r))}</a>'
            f'<span class="tl-date">{esc(r["date"])}</span>{axis.ribbon(r["range"], label=False)}</li>'
            for r in rows)
        secs += f'''<section class="tl-section" id="timeline-{t}">
<h3 class="shelf">{cfg["title"]} <small>{len(rows)} rows</small></h3>
<div class="tl-scale">{axis.legend()}</div>
<ol class="timeline">{items}</ol></section>'''
    jump = " · ".join(f'<a href="#timeline" data-jump="timeline-{t}">{c["title"]}</a>' for t, c in build.TESTAMENTS.items())
    return f'''<article class="view" id="v-timeline" data-view="timeline" hidden>
<header class="pagehead"><p class="eyebrow">Every chapter in date order</p><h2>Timeline</h2>
<p class="lede">Narrative and prophetic chapters by the date of their events or oracles; letters, psalms and wisdom books by when they were written. Chapters with the same date share a row. Sorted by the middle of each range; a wide bar means scholars disagree.</p>
<p class="legend"><span class="sw events"></span> Events or prophecy <span class="sw written"></span> Written · Jump to {jump}</p></header>
{secs}</article>'''


def render_anchors(data):
    nt_keys = set()
    for p in glob.glob(os.path.join(build.DATA_DIR, "anchors-nt*.yaml")):
        nt_keys |= set((build.load_yaml(p) or {}).keys())
    out = ""
    for t, title in (("ot", "Old Testament"), ("nt", "New Testament")):
        keys = [k for k in data.anchors if (k in nt_keys) == (t == "nt")]
        axis = AXES[t]
        out += f'<h3 class="shelf testament">{title} <small>{len(keys)} key dates</small></h3>'
        for key in keys:
            a = data.anchors[key]
            out += f'''<section class="anchor" id="anchor-{key}">
<h3>{esc(a["title"])}</h3><div class="dc-head"><span class="date">{esc(a["date"])}</span></div>
{axis.ribbon(a.get("range"))}
<p class="short">{inline(a["short"])}</p>
{blocks(a["discussion"])}
<p class="srcs"><span class="lbl">Sources</span> {"; ".join(cite(data, c) for c in a.get("sources", []))}</p>
</section>'''
    return f'''<article class="view" id="v-key-dates" data-view="key-dates" hidden>
<header class="pagehead"><p class="eyebrow">{len(data.anchors)} fixed points</p><h2>Key dates</h2>
<p class="lede">The dates the chapter headings hang on, with the evidence and the competing views. Change one of these and every chapter that depends on it moves with it.</p></header>
{out}</article>'''


def render_sources(data):
    groups = [("ancient", "Ancient writers"), ("inscription", "Inscriptions"), ("modern", "Modern scholarship")]
    out = ""
    for kind, title in groups:
        items = "".join(
            f'<li id="src-{k}"><strong>{esc(s["short"])}</strong> <span class="full">{inline(s["full"])}</span></li>'
            for k, s in sorted(data.sources.items(), key=lambda kv: kv[1]["short"]) if s.get("kind") == kind)
        out += f"<h3>{title}</h3><ul class=\"biblio\">{items}</ul>"
    return f'''<article class="view" id="v-sources" data-view="sources" hidden>
<header class="pagehead"><p class="eyebrow">{len(data.sources)} works</p><h2>Sources</h2>
<p class="lede">Citations are a first draft, written from the standard literature and not yet checked page by page against the books. Ancient writers are cited by book and section; modern works by title.</p></header>
{out}</article>'''


def render_home(data):
    def card(b):
        return (f'<li><a href="#{book_id(b)}"><span class="bn">{esc(b["book"])}</span>'
                f'<span class="bw">{esc(b["written"]["date"])}</span>{AXES[b["testament"]].ribbon(b["written"].get("range"), label=False)}</a></li>')
    shelves = ""
    for t, cfg in build.TESTAMENTS.items():
        books = [b for b in data.books if b["testament"] == t]
        if not books:
            continue
        shelves += f'<h2 class="testament">{cfg["title"]}</h2><div class="tl-scale home-scale">{AXES[t].legend()}</div>'
        for lo, hi, title in cfg["groups"]:
            group = [b for b in books if lo <= b["order"] <= hi]
            if group:
                shelves += f'<h3 class="shelf">{title} <small>bar = when written</small></h3><ul class="books">{"".join(card(b) for b in group)}</ul>'
    nchap = sum(1 for _ in data.books)
    return f'''<article class="view" id="v-home" data-view="home">
<header class="hero"><p class="eyebrow">World English Bible · {nchap} books</p>
<h2>When did it happen,<br>and when was it written?</h2>
<p class="lede">Every chapter of the Bible with its approximate date, the evidence behind it, where scholars disagree, and who says what. The Bible text is the public-domain World English Bible, unaltered; the date notes are added above each chapter.</p>
<div class="how">
<div><h3>Reading a date</h3><p>Each chapter opens with a date card. The bar shows the range on the time scale for its Testament. Open <em>Basis and sources</em> for the reasoning and citations.</p></div>
<div><h3>Two models</h3><p>Where one disputed date moves many chapters, both are given: the exodus <span class="pill ma">c. 1446 BC</span> or <span class="pill mb">c. 1260 BC</span>, and the crucifixion <span class="pill ma">AD 30</span> or <span class="pill mb">AD 33</span>.</p></div>
<div><h3>Disputed authorship</h3><p>Some books are dated two ways, by tradition and by critical scholarship. Each book opens with a table of who holds which view, and why.</p></div>
</div>
<p class="go"><a class="btn" href="#timeline">See the timeline</a> <a class="btn ghost" href="#key-dates">Key dates</a></p>
</header>
{shelves}
<p class="fine">Draft of {build_date()}. Citations are still being verified against the published works.</p>
</article>'''


def build_date():
    import datetime
    return datetime.date.today().strftime("%-d %B %Y")


CSS = r"""
/* Layout: a fixed reading column with the book menu in a top bar; date cards sit beside each chapter's text. */
:root{
  --paper:#f6f7f4; --panel:#ffffff; --ink:#1c2422; --muted:#5d6864; --rule:#d9dfdb;
  --myrtle:#2e6352; --lapis:#34588f; --bar:#2e6352; --wash:#eef3f0;
  --f-display:"Cormorant Garamond","Iowan Old Style","Palatino Linotype",Georgia,serif;
  --f-body:"Literata",Georgia,"Times New Roman",serif;
  --f-ui:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;
  --f-data:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --paper:#141917; --panel:#1b211f; --ink:#e3e8e5; --muted:#9aa6a1; --rule:#2f3835;
  --myrtle:#7fbfa8; --lapis:#8eaee0; --bar:#7fbfa8; --wash:#1f2926; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#141917; --panel:#1b211f; --ink:#e3e8e5; --muted:#9aa6a1; --rule:#2f3835;
  --myrtle:#7fbfa8; --lapis:#8eaee0; --bar:#7fbfa8; --wash:#1f2926; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font-family:var(--f-body);font-size:17px;line-height:1.65}
a{color:var(--myrtle)}
a:focus-visible,button:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--lapis);outline-offset:2px}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--panel)}
.topbar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--panel);border-bottom:1px solid var(--rule);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:10px}
.topbar .in{max-width:1080px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px}
.brand{font-family:var(--f-display);font-weight:600;font-size:1.45rem;text-decoration:none;color:var(--ink);letter-spacing:.01em;margin-right:auto}
.brand b{color:var(--myrtle);font-weight:600}
.topbar nav{display:flex;gap:14px;flex-wrap:wrap;font-family:var(--f-ui);font-size:.9rem}
.topbar nav a{text-decoration:none;color:var(--muted)}
.topbar nav a[aria-current="page"]{color:var(--ink);font-weight:600}
.topbar select{font-family:var(--f-ui);font-size:.9rem;padding:6px 8px;border:1px solid var(--rule);border-radius:6px;background:var(--paper);color:var(--ink);max-width:100%}
main{max-width:1080px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:28px 64px}
.eyebrow,.lbl{font-family:var(--f-ui);font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin:0}
h2,h3,h4{font-family:var(--f-display);font-weight:600;text-wrap:balance;line-height:1.15}
h2{font-size:clamp(2.1rem,5vw,3.2rem);margin:.15em 0 .35em}
.lede{max-width:65ch;color:var(--muted);font-size:1.05rem}
/* Home */
.hero h2{font-size:clamp(2.3rem,6vw,3.8rem)}
.how{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px 28px;margin:26px 0;max-width:980px}
.how h3{font-size:1.3rem;margin:0 0 .2em}
.how p{margin:0;font-size:.95rem;color:var(--muted)}
.pill{font-family:var(--f-ui);font-size:.75rem;padding:1px 7px;border-radius:999px;white-space:nowrap}
.pill.ma{background:color-mix(in srgb,var(--myrtle) 16%,transparent);color:var(--myrtle)}
.pill.mb{background:color-mix(in srgb,var(--lapis) 16%,transparent);color:var(--lapis)}
.go{display:flex;gap:10px;flex-wrap:wrap}
.btn{font-family:var(--f-ui);font-size:.95rem;text-decoration:none;background:var(--myrtle);color:var(--paper);padding:9px 16px;border-radius:6px}
.btn.ghost{background:transparent;color:var(--myrtle);border:1px solid var(--myrtle)}
h2.testament{margin-top:48px;padding-top:14px;border-top:2px solid var(--ink)}
.shelf{font-size:1.5rem;margin:26px 0 10px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.shelf.testament{font-size:2rem;margin-top:40px;padding-top:12px;border-top:2px solid var(--ink)}
.shelf small,.fine{font-family:var(--f-ui);font-size:.78rem;color:var(--muted);font-weight:400}
.books{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:2px 24px}
.books a{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;padding:9px 0;border-bottom:1px solid var(--rule);text-decoration:none;color:var(--ink)}
.books .bn{font-family:var(--f-display);font-size:1.25rem;font-weight:600}
.books .bw{font-family:var(--f-data);font-size:.72rem;color:var(--muted);align-self:center;text-align:right;max-width:13em}
.books .ribbon{grid-column:1/-1}
.books a:hover .bn{color:var(--myrtle)}
/* Time scale */
.ribbon{position:relative;height:8px;border-radius:4px;background:var(--wash);margin:8px 0 2px;overflow:hidden}
.ribbon .bar{position:absolute;top:0;bottom:0;background:var(--bar);border-radius:4px;min-width:4px}
.ribbon .tick{position:absolute;top:0;bottom:0;width:1px;background:var(--rule)}
.ribbon.undated{background:repeating-linear-gradient(90deg,var(--rule) 0 6px,transparent 6px 12px)}
.ribbon-label{font-family:var(--f-data);font-size:.72rem;color:var(--muted);font-variant-numeric:tabular-nums}
.tl-scale{position:sticky;top:calc(env(safe-area-inset-top,0px) + 58px);z-index:2;background:var(--paper);padding:6px 0 4px}
.scale{position:relative;height:16px;font-family:var(--f-data);font-size:.68rem;color:var(--muted)}
.scale span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.scale span:first-child{transform:none}.scale span:last-child{transform:translateX(-100%)}
.home-scale{position:static;margin-top:4px}
/* Book */
.bookhead{border-bottom:1px solid var(--rule);padding-bottom:20px;margin-bottom:10px}
.writing{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:16px 18px;max-width:100%}
.writing>p{max-width:70ch}
.dc-head{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline}
.date{font-family:var(--f-data);font-size:.95rem;font-weight:500;font-variant-numeric:tabular-nums}
.tablewrap{overflow-x:auto;margin:10px 0}
table{border-collapse:collapse;font-family:var(--f-ui);font-size:.85rem;line-height:1.45;min-width:560px}
th,td{text-align:left;vertical-align:top;padding:7px 10px;border-bottom:1px solid var(--rule)}
th{font-weight:600;font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
td.d{font-family:var(--f-data);font-size:.8rem;min-width:9em}
td.c{min-width:150px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:16px}
.chips a{font-family:var(--f-data);font-size:.8rem;text-decoration:none;min-width:2.2em;text-align:center;padding:3px 6px;border:1px solid var(--rule);border-radius:4px;color:var(--ink)}
.chips a:hover{border-color:var(--myrtle);color:var(--myrtle)}
.chapter{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);gap:8px 40px;padding:28px 0;border-bottom:1px solid var(--rule);scroll-margin-top:80px}
.chapter h3{grid-column:1/-1;font-size:2rem;margin:0}
.chapter h3 .bk{color:var(--muted);font-weight:500}
.datecard{align-self:start;position:sticky;top:calc(env(safe-area-inset-top,0px) + 70px);font-family:var(--f-ui);font-size:.88rem;line-height:1.5;
  background:var(--panel);border:1px solid var(--rule);border-left:3px solid var(--myrtle);border-radius:6px;padding:12px 14px;max-height:calc(100vh - 100px);overflow:auto}
.datecard .date{display:block;width:100%;font-size:1rem}
.datecard .note{margin:10px 0 0}
.models{margin:10px 0 0;display:grid;gap:6px}
.models div{padding-left:8px;border-left:3px solid}
.models .ma{border-color:var(--myrtle)}.models .mb{border-color:var(--lapis)}
.models dt{font-weight:600;font-size:.8rem}.models dt small{font-weight:400;color:var(--muted)}
.models dd{margin:0;font-family:var(--f-data);font-size:.82rem}
details{margin-top:10px}
summary{cursor:pointer;color:var(--myrtle);font-weight:600;font-size:.85rem}
.basis{padding-left:18px;margin:8px 0}
.basis li{margin-bottom:8px}
.when{font-family:var(--f-data);font-size:.75rem;color:var(--muted)}
.srcs{font-size:.82rem;color:var(--muted)}
.srcs .lbl{display:block;margin-bottom:2px}
.written{margin:10px 0 0;font-size:.78rem;color:var(--muted)}
.text{max-width:65ch;min-width:0}
.text p{margin:0 0 .9em}
.text p.title{font-style:italic;color:var(--muted);font-size:.95em}
.text h4{font-size:1.2rem;margin:1em 0 .3em}
.v{font-family:var(--f-ui);font-size:.62em;font-weight:600;color:var(--myrtle);margin:0 .2em 0 .15em;vertical-align:.45em}
.fn{font-family:var(--f-ui);font-size:.65em;color:var(--muted);cursor:help}
.poem{margin:0 0 .9em;display:flex;flex-direction:column}
.poem .q2{padding-left:2em}
.notes{font-family:var(--f-ui);font-size:.78rem;color:var(--muted);border-top:1px solid var(--rule);padding-top:8px;padding-left:1.4em;margin-top:1.2em}
.notes li::marker{content:"† "}
/* Timeline */
.legend{font-family:var(--f-ui);font-size:.8rem;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sw{display:inline-block;width:18px;height:8px;border-radius:4px}
.sw.events{background:var(--myrtle)}.sw.written{background:var(--lapis)}
.tl-section{scroll-margin-top:70px}
.timeline{list-style:none;padding:0;margin:0}
.timeline li{display:grid;grid-template-columns:minmax(0,11rem) minmax(0,1fr);gap:0 14px;padding:5px 0;border-bottom:1px solid var(--rule);align-items:center}
.timeline li a{font-family:var(--f-display);font-weight:600;font-size:1.1rem;text-decoration:none}
.timeline .tl-date{font-family:var(--f-data);font-size:.75rem;color:var(--muted)}
.timeline .ribbon{grid-column:1/-1;margin:4px 0}
.timeline li.written .bar{background:var(--lapis)}
.timeline li.written a{color:var(--lapis)}
/* Key dates and sources */
.anchor{padding:24px 0;border-bottom:1px solid var(--rule);max-width:820px;scroll-margin-top:80px}
.anchor h3{font-size:1.8rem;margin:0 0 4px}
.anchor .short{font-weight:500}
.anchor p{max-width:70ch}
.biblio{padding-left:0;list-style:none;max-width:820px}
.biblio li{padding:8px 0;border-bottom:1px solid var(--rule);font-size:.95rem;scroll-margin-top:80px}
.biblio li.hl{background:var(--wash)}
.biblio .full{color:var(--muted)}
@media (max-width:760px){
  body{font-size:16px}
  .chapter{grid-template-columns:minmax(0,1fr)}
  .datecard{position:static;max-height:none}
  .tl-scale{top:calc(env(safe-area-inset-top,0px) + 96px)}
  .timeline li{grid-template-columns:minmax(0,1fr)}
}
"""

JS = r"""
(function(){
  var views = {}; document.querySelectorAll('.view').forEach(function(v){ views[v.dataset.view] = v; });
  var sel = document.getElementById('book');
  function show(view){
    var v = views[view];
    // Book text is kept in a <template> until the book is first opened.
    if (v.classList.contains('book') && !v.firstElementChild){
      var tpl = document.getElementById('tpl-' + view);
      if (tpl) v.appendChild(tpl.content.cloneNode(true));
    }
    Object.keys(views).forEach(function(k){ views[k].hidden = (k !== view); });
  }
  function route(){
    var h = decodeURIComponent(location.hash.slice(1)) || 'home';
    var view = h, target = null;
    if (!views[view]) {
      var m = h.match(/^(.*?)-(\d+)$/);
      if (m && views[m[1]]) view = m[1]; else view = 'home';
    }
    show(view);
    if (view !== h) target = document.getElementById(h);
    document.querySelectorAll('.topbar nav a').forEach(function(a){
      if (a.getAttribute('href') === '#' + view) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
    });
    sel.value = views[view].classList.contains('book') ? view : '';
    if (target) target.scrollIntoView({block:'start',behavior:'instant'}); else window.scrollTo(0,0);
  }
  sel.addEventListener('change', function(){ if (sel.value) location.hash = sel.value; });
  window.addEventListener('hashchange', route);
  // Links to a key date, a source or a timeline section: open that page, then scroll to the entry.
  document.addEventListener('click', function(e){
    var a = e.target.closest('a[data-anchor],a[data-src],a[data-jump]'); if (!a) return;
    e.preventDefault();
    var id = a.dataset.jump || (a.dataset.anchor ? 'anchor-' + a.dataset.anchor : 'src-' + a.dataset.src);
    var page = a.dataset.jump ? 'timeline' : a.dataset.anchor ? 'key-dates' : 'sources';
    if (location.hash !== '#' + page) location.hash = page;
    setTimeout(function(){
      var el = document.getElementById(id); if (!el) return;
      document.querySelectorAll('.biblio li.hl').forEach(function(x){ x.classList.remove('hl'); });
      if (a.dataset.src) el.classList.add('hl');
      el.scrollIntoView({block:'start',behavior:'instant'});
    }, 30);
  });
  route();
})();
"""


def main():
    data = build.Data()
    data.validate()
    templates, all_ch = [], {}
    for b in data.books:
        if not build.usfm_path(b):
            data.errors.append(f"{b['book']}: no USFM file for {b['code']}")
            continue
        h, chs = render_book(data, b)
        templates.append(h)
        all_ch[b["book"]] = chs
    if data.errors:
        print("\n".join(data.errors), file=sys.stderr)
        sys.exit(1)
    options = ""
    for t, cfg in build.TESTAMENTS.items():
        opts = "".join(f'<option value="{book_id(b)}">{esc(b["book"])}</option>' for b in data.books if b["testament"] == t)
        if opts:
            options += f'<optgroup label="{cfg["title"]}">{opts}</optgroup>'
    placeholders = "".join(f'<article class="view book" id="v-{book_id(b)}" data-view="{book_id(b)}" hidden></article>' for b in data.books)
    page = f'''<title>Timeline Bible</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;600&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;1,7..72,400&display=swap">
<style>{CSS}</style>
<div class="topbar"><div class="in">
<a class="brand" href="#home">Timeline <b>Bible</b></a>
<nav aria-label="Sections"><a href="#home">Introduction</a><a href="#timeline">Timeline</a><a href="#key-dates">Key dates</a><a href="#sources">Sources</a></nav>
<select id="book" aria-label="Go to a book"><option value="">Go to a book…</option>{options}</select>
</div></div>
<main>
{render_home(data)}
{render_timeline(data, all_ch)}
{render_anchors(data)}
{render_sources(data)}
{placeholders}
</main>
{"".join(templates)}
<script>{JS}</script>
'''
    head, body = page.split("<div class=\"topbar\">", 1)
    standalone = STANDALONE_HEAD + head + "</head>\n<body>\n<div class=\"topbar\">" + body + "</body>\n</html>\n"
    for path, text in ((OUT_PAGES, standalone), (OUT_ARTIFACT, page)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"Wrote {path} ({len(text.encode()) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
