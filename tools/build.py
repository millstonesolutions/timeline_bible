#!/usr/bin/env python3
"""Build the Timeline Bible Markdown from the WEB text and the dating data.

    python3 tools/build.py            # writes nt/*.md
    python3 tools/build.py --check    # validates the data only

Inputs (all relative to the timeline-bible folder):
  source/engwebp-usfm/*.usfm   World English Bible (public domain), unaltered USFM
  data/sources.yaml            bibliography
  data/anchors.yaml            chronological anchors with views and sources
  data/nt/*.yaml               per-book date of writing and per-chapter dates

Outputs: nt/<slug>.md per book, nt/anchors.md, nt/sources.md, nt/timeline.md,
nt/README.md. The outputs are generated: edit the data files, then rebuild.
"""

import argparse
import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USFM_DIR = os.path.join(ROOT, "source", "engwebp-usfm")
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "nt")

MODEL_A = "Model A (crucifixion AD 30)"
MODEL_B = "Model B (crucifixion AD 33)"


# --- USFM -------------------------------------------------------------------

def clean_inline(text):
    """Strip character markup, keeping the words."""
    text = re.sub(r"\\x .*?\\x\*", "", text)                      # cross references
    text = re.sub(r"\\\+?w ([^|\\]*?)(\|[^\\]*)?\\\+?w\*", r"\1", text)  # \w word|strong\w*
    text = re.sub(r"\\\+?(wj|wh|wg|add|nd|qs|tl|sc|it|bd|em)\*?\s?", "", text)
    return text


def parse_usfm(path):
    """Return {chapter: {"blocks": [(style, [(verse, text)])], "notes": [...]}}.

    style is "p" (prose) or "q1"/"q2" (poetry line). Verse is None for text that
    continues the previous verse. Footnote calls become [^id] markers.
    """
    chapters = {}
    chap = None
    raw = open(path, encoding="utf-8").read()
    # Each marker that starts a paragraph or verse begins a new token.
    tokens = re.split(r"(?=\\(?:c|v|p|m|nb|b|q1|q2|q|pi|mi|s1|s|d)\s)", raw)
    style = "p"
    for tok in tokens:
        tok = tok.replace("\n", " ")
        m = re.match(r"\\(\w+)\s*(.*)", tok, re.S)
        if not m:
            continue
        marker, rest = m.group(1), m.group(2)
        if marker == "c":
            chap = int(rest.split()[0])
            chapters[chap] = {"blocks": [], "notes": []}
            continue
        if chap is None:
            continue
        ch = chapters[chap]
        if marker in ("p", "m", "pi", "mi", "nb", "b", "q", "q1", "q2"):
            style = {"q": "q1"}.get(marker, marker if marker in ("q1", "q2") else "p")
            ch["blocks"].append((style, []))
            text, verse = rest, None
        elif marker == "v":
            vm = re.match(r"(\S+)\s*(.*)", rest, re.S)
            verse, text = vm.group(1), vm.group(2)
            if not ch["blocks"]:
                ch["blocks"].append((style, []))
        elif marker in ("s", "s1", "d"):
            ch["blocks"].append(("s", [(None, clean_inline(rest).strip())]))
            ch["blocks"].append((style, []))
            continue
        else:
            continue

        def footnote(fm):
            body = fm.group(1)
            body = re.sub(r"\\fr\s+\S+\s*", "", body)
            body = re.sub(r"\\f(t|qa|q|k|p)\*?\s*", "", body)
            note_id = f"{chap}-{len(ch['notes']) + 1}"
            ch["notes"].append((note_id, clean_inline(body).strip()))
            return f"[^{note_id}]"

        text = re.sub(r"\\f \+ (.*?)\\f\*", footnote, text, flags=re.S)
        text = re.sub(r"\s+", " ", clean_inline(text)).strip()
        if text or verse:
            ch["blocks"][-1][1].append((verse, text))
    return chapters


def render_text(chapter):
    out = []
    for style, verses in chapter["blocks"]:
        if not verses:
            continue
        if style == "s":
            out.append(f"#### {verses[0][1]}")
            continue
        parts = []
        for verse, text in verses:
            parts.append((f"<sup>{verse}</sup>" if verse else "") + text)
        line = " ".join(p for p in parts if p)
        if style == "q2":
            line = "&emsp;&emsp;" + line
        out.append(line + ("  " if style.startswith("q") else ""))
    # Prose blocks are separate paragraphs; consecutive poetry lines stay together.
    md, prev_poetry = [], False
    for (style, verses), line in zip([b for b in chapter["blocks"] if b[1]], out):
        poetry = style.startswith("q")
        if md and not (poetry and prev_poetry):
            md.append("")
        md.append(line)
        prev_poetry = poetry
    if chapter["notes"]:
        md.append("")
        for note_id, body in chapter["notes"]:
            md.append(f"[^{note_id}]: {body}")
    return "\n".join(md)


# --- Data -------------------------------------------------------------------

def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_cite(cite):
    key, _, loc = str(cite).partition(" ")
    return key, loc.strip()


class Data:
    def __init__(self):
        self.sources = load_yaml(os.path.join(DATA_DIR, "sources.yaml"))
        self.anchors = load_yaml(os.path.join(DATA_DIR, "anchors.yaml"))
        self.books = [load_yaml(p) for p in sorted(glob.glob(os.path.join(DATA_DIR, "nt", "*.yaml")))]
        self.errors = []

    def check_cites(self, cites, where):
        for c in cites or []:
            key, _ = split_cite(c)
            if key not in self.sources:
                self.errors.append(f"{where}: unknown source '{key}'")

    def chapters(self, book, count):
        """Merge each chapter with the book default; report gaps and bad keys."""
        default = book.get("default", {})
        given = book.get("chapters") or {}
        for n in given:
            if not 1 <= int(n) <= count:
                self.errors.append(f"{book['book']}: chapter {n} doesn't exist")
        merged = {}
        for n in range(1, count + 1):
            ch = dict(default)
            ch.update(given.get(n) or {})
            where = f"{book['book']} {n}"
            if "date" not in ch or "range" not in ch:
                self.errors.append(f"{where}: needs date and range")
            for a in ch.get("anchors") or []:
                if a not in self.anchors:
                    self.errors.append(f"{where}: unknown anchor '{a}'")
            self.check_cites(ch.get("sources"), where)
            merged[n] = ch
        return merged

    def validate(self):
        for key, a in self.anchors.items():
            self.check_cites(a.get("sources"), f"anchor {key}")
        for b in self.books:
            for v in b["written"].get("views", []):
                self.check_cites(v.get("sources"), f"{b['book']} written")


# --- Rendering --------------------------------------------------------------

def fmt_year(y):
    return f"{-y} BC" if y < 0 else f"AD {y}"


def cite_link(data, cite, prefix=""):
    key, loc = split_cite(cite)
    src = data.sources[key]
    text = src["short"] + (f", {loc}" if loc else "")
    return f"[{text}]({prefix}sources.md#{key})"


def dedupe(seq):
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def chapter_header(data, book, n, ch):
    letter = book.get("kind") == "letter"
    label = ch.get("label") or ("Date written" if letter else "Date of events")
    lines = [f"> **{label}:** {ch['date']}"]
    if ch.get("a") or ch.get("b"):
        lines.append(">")
        if ch.get("a"):
            lines.append(f"> - *{MODEL_A}:* {ch['a']}")
        if ch.get("b"):
            lines.append(f"> - *{MODEL_B}:* {ch['b']}")
    if ch.get("note"):
        lines += [">", "> " + " ".join(ch["note"].split())]
    anchors = ch.get("anchors") or []
    if anchors:
        lines += [">", "> **Basis:**"]
        for a in anchors:
            an = data.anchors[a]
            lines.append(f"> - [{an['title']}](anchors.md#{a}), {an['date']}. {' '.join(an['short'].split())}")
    cites = list(ch.get("sources") or [])
    for a in anchors:
        cites += data.anchors[a].get("sources") or []
    if cites:
        lines += [">", "> **Sources:** " + "; ".join(cite_link(data, c) for c in dedupe(cites)) + "."]
    if not letter:
        w = book["written"]
        lines += [">", f"> **Book written:** {w['date']}; see [the date of {book['book']}](#date-of-writing)."]
    return "\n".join(lines)


def book_intro(data, book):
    w = book["written"]
    out = [
        f"# {book['book']}",
        "",
        "World English Bible text (public domain), with a date heading for each chapter.",
        "See [How to read the date headings](README.md#how-to-read-the-date-headings).",
        "",
        '<a id="date-of-writing"></a>',
        "",
        f"## Date of writing: {w['date']}",
        "",
        " ".join(w["summary"].split()),
        "",
        "| Date | Held by | Basis | Sources |",
        "|---|---|---|---|",
    ]
    for v in w.get("views", []):
        cites = "; ".join(cite_link(data, c) for c in v.get("sources", []))
        basis = " ".join((v.get("basis") or "").split()).replace("|", "\\|")
        out.append(f"| {v['date']} | {v.get('held_by', '')} | {basis} | {cites} |")
    return "\n".join(out)


def build_book(data, book):
    usfm = glob.glob(os.path.join(USFM_DIR, f"*-{book['code']}*.usfm"))
    if len(usfm) != 1:
        data.errors.append(f"{book['book']}: no USFM file for {book['code']}")
        return None, {}
    text = parse_usfm(usfm[0])
    chapters = data.chapters(book, len(text))
    parts = [book_intro(data, book)]
    for n in sorted(text):
        parts.append(f"## {book['book']} {n}\n\n{chapter_header(data, book, n, chapters[n])}\n\n{render_text(text[n])}")
    return "\n\n".join(parts) + "\n", chapters


def build_anchors(data):
    out = [
        "# Chronological anchors",
        "",
        "The fixed points the chapter dates depend on. Each chapter heading quotes",
        "the short form; this page gives the reasoning and the alternatives.",
        "Years: negative ranges are BC; there is no year 0.",
    ]
    for key, a in data.anchors.items():
        cites = "; ".join(cite_link(data, c) for c in a.get("sources", []))
        out += [
            "",
            f'<a id="{key}"></a>',
            "",
            f"## {a['title']}: {a['date']}",
            "",
            " ".join(a["short"].split()),
            "",
            a["discussion"].rstrip(),
            "",
            f"**Sources:** {cites}.",
        ]
    return "\n".join(out) + "\n"


def build_sources(data):
    out = [
        "# Sources",
        "",
        "Status *unverified* means the work and its position are cited from general",
        "knowledge, and locators other than ancient book/section numbers still need",
        "checking against a copy. Change it to *verified* in `data/sources.yaml` once",
        "checked.",
    ]
    groups = [("ancient", "Ancient sources"), ("inscription", "Inscriptions"), ("modern", "Modern scholarship")]
    for kind, title in groups:
        out += ["", f"## {title}", ""]
        for key, s in sorted(data.sources.items(), key=lambda kv: kv[1]["short"]):
            if s.get("kind") != kind:
                continue
            out.append(f'- <a id="{key}"></a>**{s["short"]}**: {s["full"]} *({s.get("status", "unverified")})*')
    return "\n".join(out) + "\n"


def build_timeline(data, all_chapters):
    rows = []
    for book in data.books:
        chapters = all_chapters.get(book["book"], {})
        if book.get("kind") == "letter":
            w = book["written"]
            lo, hi = w["range"]
            span = f"1–{len(chapters)}" if len(chapters) > 1 else "1"
            rows.append(((lo + hi) / 2, book["order"], 0, w["date"], f"[{book['book']} {span}]({book['slug']}.md) (written)", f"{fmt_year(lo)} – {fmt_year(hi)}"))
            continue
        for n, ch in chapters.items():
            lo, hi = ch["range"]
            rows.append(((lo + hi) / 2, book["order"], n, ch["date"], f"[{book['book']} {n}]({book['slug']}.md#{book['slug'].split('-', 1)[1]}-{n})", f"{fmt_year(lo)} – {fmt_year(hi)}"))
    rows.sort()
    out = [
        "# Timeline",
        "",
        "Every chapter of the Gospels, Acts and Revelation by the date of its events,",
        "and each letter by its date of writing, sorted by the midpoint of the range.",
        "Ranges cover the main scholarly views, so wide ranges sort to the middle of",
        "their span. See each book for the reasoning.",
        "",
        "| Approx. date | Chapter | Range used for sorting |",
        "|---|---|---|",
    ]
    out += [f"| {r[3]} | {r[4]} | {r[5]} |" for r in rows]
    return "\n".join(out) + "\n"


def build_index(data):
    out = [
        "# The Timeline Bible: New Testament",
        "",
        "Generated by `tools/build.py`; don't edit these files by hand. Edit `data/`",
        "and rebuild. See the project [README](../README.md).",
        "",
        "- [Timeline](timeline.md): every chapter in date order",
        "- [Chronological anchors](anchors.md): the fixed points and the debates behind them",
        "- [Sources](sources.md): bibliography",
        "",
        "## Books",
        "",
        "| Book | Written |",
        "|---|---|",
    ]
    for b in data.books:
        out.append(f"| [{b['book']}]({b['slug']}.md) | {b['written']['date']} |")
    out += [
        "",
        "## How to read the date headings",
        "",
        "- **Date of events** (Gospels, Acts, Revelation): when the chapter's events took",
        "  place. **Date written** (letters): when the letter was written.",
        f"- Inside Jesus' ministry, dates are given for two models: *{MODEL_A}* and",
        f"  *{MODEL_B}*. Both have wide scholarly support; see",
        "  [the models](anchors.md#models).",
        "- **Basis** lists the chronological anchors the date depends on, and **Sources**",
        "  combines the chapter's own citations with the anchors' citations.",
        "- *c.* = circa. Ranges like \"AD 60–62 or 80–90\" mean the date depends on a",
        "  disputed question (usually authorship), explained in the book's",
        "  *Date of writing* section.",
    ]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only, write nothing")
    args = ap.parse_args()

    data = Data()
    data.validate()
    outputs, all_chapters = {}, {}
    for book in data.books:
        md, chapters = build_book(data, book)
        if md:
            outputs[f"{book['slug']}.md"] = md
            all_chapters[book["book"]] = chapters
    if data.errors:
        print("\n".join(data.errors), file=sys.stderr)
        sys.exit(1)
    outputs["anchors.md"] = build_anchors(data)
    outputs["sources.md"] = build_sources(data)
    outputs["timeline.md"] = build_timeline(data, all_chapters)
    outputs["README.md"] = build_index(data)
    if args.check:
        print(f"OK: {len(data.books)} books, {sum(len(c) for c in all_chapters.values())} chapters")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, md in outputs.items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    print(f"Wrote {len(outputs)} files to {OUT_DIR}")


if __name__ == "__main__":
    main()
