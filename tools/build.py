#!/usr/bin/env python3
"""Build the Timeline Bible Markdown from the WEB text and the dating data.

    python3 tools/build.py            # writes ot/, nt/ and reference/
    python3 tools/build.py --check    # validates the data only

Inputs (relative to the repository root):
  source/engwebp-usfm/*.usfm   World English Bible (public domain), unaltered USFM
  data/sources*.yaml           bibliography
  data/anchors*.yaml           chronological anchors with views and sources
  data/ot/*.yaml, data/nt/*.yaml
                               per-book date of writing and per-chapter dates

Outputs: <testament>/<slug>.md per book, <testament>/timeline.md and README.md,
reference/anchors.md and reference/sources.md. They are generated: edit the
data files, then rebuild.
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
REF_DIR = os.path.join(ROOT, "reference")

TESTAMENTS = {
    "ot": {
        "title": "Old Testament",
        # Model a/b: the two main dates for the exodus, used from Exodus to Judges.
        "models": (("Early exodus", "c. 1446 BC"), ("Late exodus", "c. 1260 BC")),
        "axis": (-2200, -100),
        "ticks": [(-2200, "2200 BC"), (-2000, "2000"), (-1500, "1500"), (-1000, "1000"), (-587, "587"), (-100, "100 BC")],
        "groups": [(1, 5, "Law"), (6, 17, "History"), (18, 22, "Poetry and wisdom"), (23, 39, "Prophets")],
    },
    "nt": {
        "title": "New Testament",
        "models": (("Model A", "crucifixion AD 30"), ("Model B", "crucifixion AD 33")),
        "axis": (-10, 150),
        "ticks": [(-10, "10 BC"), (1, "AD 1"), (30, "30"), (70, "70"), (100, "100"), (150, "150")],
        "groups": [(40, 44, "Gospels and Acts"), (45, 65, "Letters"), (66, 66, "Revelation")],
    },
}

# kind -> (heading label, show the book's own date of writing under each chapter)
KINDS = {
    "narrative": ("Date of events", True),
    "prophecy": ("Date of the prophecy", True),
    "writing": ("Date written", False),
    "letter": ("Date written", False),
}


# --- USFM -------------------------------------------------------------------

def clean_inline(text):
    """Strip character markup, keeping the words."""
    text = re.sub(r"\\x .*?\\x\*", "", text)                      # cross references
    text = re.sub(r"\\\+?w ([^|\\]*?)(\|[^\\]*)?\\\+?w\*", r"\1", text)  # \w word|strong\w*
    text = re.sub(r"\\\+?(wj|wh|wg|add|nd|qs|tl|sc|it|bd|em|bk)\*?\s?", "", text)
    return text


PARA = ("p", "m", "pi", "pi1", "mi", "nb", "b", "li1", "q", "q1", "q2")


def parse_usfm(path):
    """Return {chapter: {"blocks": [(style, [(verse, text)])], "notes": [...]}}.

    style is "p" (prose), "q1"/"q2" (poetry line), "s" (heading) or "d" (psalm
    title). Verse is None for text that continues the previous verse. Footnote
    calls become [^id] markers.
    """
    chapters = {}
    chap = None
    raw = open(path, encoding="utf-8").read()
    # Each marker that starts a paragraph or verse begins a new token.
    tokens = re.split(r"(?=\\(?:c|v|p|m|nb|b|li1|q1|q2|q|pi1|pi|mi|s1|s|d|sp|ms1)\s)", raw)
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
        if marker in PARA:
            style = marker if marker in ("q1", "q2") else ("q1" if marker == "q" else "p")
            ch["blocks"].append((style, []))
            text, verse = rest, None
        elif marker == "v":
            vm = re.match(r"(\S+)\s*(.*)", rest, re.S)
            verse, text = vm.group(1), vm.group(2)
            if not ch["blocks"]:
                ch["blocks"].append((style, []))
        elif marker in ("s", "s1", "sp", "ms1", "d"):
            ch["blocks"].append(("d" if marker == "d" else "s", []))
            text, verse = rest, None
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
        if marker in ("s", "s1", "sp", "ms1", "d"):
            ch["blocks"].append((style, []))     # text after a heading resumes the old style
    return chapters


def render_text(chapter):
    md, prev_poetry = [], False
    for style, verses in chapter["blocks"]:
        if not verses:
            continue
        parts = [(f"<sup>{v}</sup>" if v else "") + t for v, t in verses]
        line = " ".join(p for p in parts if p)
        poetry = style.startswith("q")
        if style == "s":
            line = f"#### {line}"
        elif style == "d":
            line = f"*{line}*"
        elif style == "q2":
            line = "&emsp;&emsp;" + line
        if poetry:
            line += "  "
        # Prose blocks are separate paragraphs; consecutive poetry lines stay together.
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


def usfm_path(book):
    paths = glob.glob(os.path.join(USFM_DIR, f"*-{book['code']}engwebp.usfm"))
    return paths[0] if len(paths) == 1 else None


class Data:
    def __init__(self):
        self.errors = []
        self.sources = self.merged("sources*.yaml", "source")
        self.anchors = self.merged("anchors*.yaml", "anchor")
        self.books = []
        for t in TESTAMENTS:
            for p in sorted(glob.glob(os.path.join(DATA_DIR, t, "*.yaml"))):
                book = load_yaml(p)
                book["testament"] = t
                book.setdefault("kind", "narrative")
                if book["kind"] not in KINDS:
                    self.errors.append(f"{book['book']}: unknown kind '{book['kind']}'")
                self.books.append(book)
        self.books.sort(key=lambda b: b["order"])

    def merged(self, pattern, what):
        """Merge data/<pattern> files into one dict, reporting duplicate keys."""
        out = {}
        for p in sorted(glob.glob(os.path.join(DATA_DIR, pattern))):
            for key, value in (load_yaml(p) or {}).items():
                if key in out:
                    self.errors.append(f"{os.path.basename(p)}: {what} '{key}' defined twice")
                out[key] = value
        return out

    def check_cites(self, cites, where):
        for c in cites or []:
            key, _ = split_cite(c)
            if key not in self.sources:
                self.errors.append(f"{where}: unknown source '{key}'")

    def check_range(self, r, where):
        if r is None:
            return
        if not (isinstance(r, list) and len(r) == 2 and all(isinstance(y, int) for y in r) and r[0] <= r[1] and 0 not in r):
            self.errors.append(f"{where}: range must be [lo, hi] years, lo <= hi, no year 0 (got {r})")

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
                self.errors.append(f"{where}: needs date and range (range may be null for undated)")
            self.check_range(ch.get("range"), where)
            for a in ch.get("anchors") or []:
                if a not in self.anchors:
                    self.errors.append(f"{where}: unknown anchor '{a}'")
            self.check_cites(ch.get("sources"), where)
            merged[n] = ch
        return merged

    def validate(self):
        for key, a in self.anchors.items():
            self.check_cites(a.get("sources"), f"anchor {key}")
            self.check_range(a.get("range"), f"anchor {key}")
        for b in self.books:
            self.check_range(b["written"].get("range"), f"{b['book']} written")
            for v in b["written"].get("views", []):
                self.check_cites(v.get("sources"), f"{b['book']} written")


def model_labels(book):
    labels = book.get("models")
    return tuple(tuple(x) for x in labels) if labels else TESTAMENTS[book["testament"]]["models"]


def timeline_rows(data, testament, all_chapters):
    """One row per run of consecutive chapters with the same date, sorted by date.

    The sort year is the chapter's `sort:` if given (e.g. the date a psalm's heading
    implies, when the range also covers a much later critical date), otherwise the
    middle of its range.

    Returns dicts: book, first, last, date, range (or None), kind ('events' or
    'written'). Undated rows sort first.
    """
    rows = []
    for book in data.books:
        if book["testament"] != testament:
            continue
        chapters = all_chapters[book["book"]]
        kind = "written" if book["kind"] in ("letter", "writing") else "events"
        run = None
        for n in sorted(chapters):
            ch = chapters[n]
            key = (ch["date"], tuple(ch["range"]) if ch.get("range") else None, ch.get("sort"))
            if run and run["key"] == key:
                run["last"] = n
                continue
            run = {"key": key, "book": book, "first": n, "last": n, "date": ch["date"],
                   "range": ch.get("range"), "sort": ch.get("sort"), "kind": kind}
            rows.append(run)
    def year(r):
        if r["sort"] is not None:
            return r["sort"]
        return float("-inf") if not r["range"] else (r["range"][0] + r["range"][1]) / 2
    rows.sort(key=lambda r: (year(r), r["book"]["order"], r["first"]))
    return rows


def row_label(row):
    span = str(row["first"]) if row["first"] == row["last"] else f"{row['first']}–{row['last']}"
    return f"{row['book']['book']} {span}"


# --- Markdown rendering -------------------------------------------------------

def fmt_year(y):
    return f"{-y} BC" if y < 0 else f"AD {y}"


def fmt_range(r):
    if not r:
        return "undated"
    lo, hi = r
    return fmt_year(lo) if lo == hi else f"{fmt_year(lo)} – {fmt_year(hi)}"


def gh_id(text):
    """The anchor id GitHub gives a Markdown heading."""
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def cite_link(data, cite):
    key, loc = split_cite(cite)
    src = data.sources[key]
    text = src["short"] + (f", {loc}" if loc else "")
    return f"[{text}](../reference/sources.md#{key})"


def dedupe(seq):
    seen, out = set(), []
    for s in seq:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def chapter_header(data, book, n, ch):
    label, show_written = KINDS[book["kind"]]
    label = ch.get("label") or book.get("label") or label
    lines = [f"> **{label}:** {ch['date']}"]
    (an, asub), (bn, bsub) = model_labels(book)
    if ch.get("a") or ch.get("b"):
        lines.append(">")
        if ch.get("a"):
            lines.append(f"> - *{an} ({asub}):* {ch['a']}")
        if ch.get("b"):
            lines.append(f"> - *{bn} ({bsub}):* {ch['b']}")
    if ch.get("note"):
        lines += [">", "> " + " ".join(ch["note"].split())]
    anchors = ch.get("anchors") or []
    if anchors:
        lines += [">", "> **Basis:**"]
        for a in anchors:
            x = data.anchors[a]
            lines.append(f"> - [{x['title']}](../reference/anchors.md#{a}), {x['date']}. {' '.join(x['short'].split())}")
    cites = list(ch.get("sources") or [])
    for a in anchors:
        cites += data.anchors[a].get("sources") or []
    if cites:
        lines += [">", "> **Sources:** " + "; ".join(cite_link(data, c) for c in dedupe(cites)) + "."]
    if show_written:
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
    path = usfm_path(book)
    if not path:
        data.errors.append(f"{book['book']}: no USFM file for {book['code']}")
        return None, {}
    text = parse_usfm(path)
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
        "There is no year 0: 1 BC is followed by AD 1.",
    ]
    for key, a in data.anchors.items():
        cites = "; ".join(cite_link(data, c) for c in a.get("sources", []))
        out += ["", f'<a id="{key}"></a>', "", f"## {a['title']}: {a['date']}", "",
                " ".join(a["short"].split()), "", a["discussion"].rstrip(), "", f"**Sources:** {cites}."]
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
            if s.get("kind") == kind:
                out.append(f'- <a id="{key}"></a>**{s["short"]}**: {s["full"]} *({s.get("status", "unverified")})*')
    return "\n".join(out) + "\n"


def build_timeline(data, testament, all_chapters):
    t = TESTAMENTS[testament]
    out = [
        f"# Timeline: {t['title']}",
        "",
        "Narrative and prophetic chapters by the date of their events or oracles;",
        "letters, psalms and wisdom books by when they were written. Consecutive",
        "chapters with the same date share a row. Rows are sorted by the middle of",
        "the range, which covers the main scholarly views, so a wide range sorts to",
        "the middle of its span. Undated chapters come first. See each book for the",
        "reasoning.",
        "",
        "| Approx. date | Chapters | Range used for sorting |",
        "|---|---|---|",
    ]
    for r in timeline_rows(data, testament, all_chapters):
        b = r["book"]
        anchor = gh_id(f"{b['book']} {r['first']}")
        mark = " (written)" if r["kind"] == "written" else ""
        out.append(f"| {r['date']} | [{row_label(r)}]({b['slug']}.md#{anchor}){mark} | {fmt_range(r['range'])} |")
    return "\n".join(out) + "\n"


def build_index(data, testament):
    t = TESTAMENTS[testament]
    (an, asub), (bn, bsub) = t["models"]
    out = [
        f"# The Timeline Bible: {t['title']}",
        "",
        "Generated by `tools/build.py`; don't edit these files by hand. Edit `data/`",
        "and rebuild. See the project [README](../README.md).",
        "",
        "- [Timeline](timeline.md): every chapter in date order",
        "- [Chronological anchors](../reference/anchors.md): the fixed points and the debates behind them",
        "- [Sources](../reference/sources.md): bibliography",
    ]
    for lo, hi, title in t["groups"]:
        out += ["", f"## {title}", "", "| Book | Written |", "|---|---|"]
        for b in data.books:
            if lo <= b["order"] <= hi:
                out.append(f"| [{b['book']}]({b['slug']}.md) | {b['written']['date']} |")
    out += [
        "",
        "## How to read the date headings",
        "",
        "- **Date of events**: when the chapter's events took place. **Date of the",
        "  prophecy**: when the oracle was given. **Date written**: when a letter, psalm",
        "  or wisdom text was written.",
        f"- Where one disputed date moves a whole stretch of chapters, two dates are",
        f"  given: *{an} ({asub})* and *{bn} ({bsub})*. See the chronological anchors.",
        "- **Basis** lists the chronological anchors the date depends on, and **Sources**",
        "  combines the chapter's own citations with the anchors' citations.",
        "- *c.* = circa. A date like \"c. 700 BC or c. 520 BC\" means it depends on a",
        "  disputed question (authorship or composition), explained in the book's",
        "  *Date of writing* section. *Undated* means no historical date can be given.",
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
            outputs[os.path.join(book["testament"], f"{book['slug']}.md")] = md
            all_chapters[book["book"]] = chapters
    if data.errors:
        print("\n".join(data.errors), file=sys.stderr)
        sys.exit(1)
    for t in TESTAMENTS:
        if any(b["testament"] == t for b in data.books):
            outputs[os.path.join(t, "timeline.md")] = build_timeline(data, t, all_chapters)
            outputs[os.path.join(t, "README.md")] = build_index(data, t)
    outputs[os.path.join("reference", "anchors.md")] = build_anchors(data)
    outputs[os.path.join("reference", "sources.md")] = build_sources(data)
    if args.check:
        print(f"OK: {len(data.books)} books, {sum(len(c) for c in all_chapters.values())} chapters")
        return
    for name, md in outputs.items():
        path = os.path.join(ROOT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
    print(f"Wrote {len(outputs)} files")


if __name__ == "__main__":
    main()
