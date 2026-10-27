# Timeline Bible

The whole Bible text of the World English Bible, with a heading on every chapter
giving its approximate date, the reasoning behind it, the scholarly views where they
disagree, and citations.

## Read it in your browser

**https://millstonesolutions.github.io/timeline_bible/**

The whole thing is one web page: a book menu, a date card on every chapter, a
timeline of all 1,189 chapters, the key dates behind them and the bibliography.
Nothing to download.

If that link isn't live yet, this mirror of the same page works now:
https://raw.githack.com/millstonesolutions/timeline_bible/main/docs/index.html

On GitHub itself the Markdown version reads well too: start at
[ot/README.md](ot/README.md) and [nt/README.md](nt/README.md) (book lists),
[ot/timeline.md](ot/timeline.md) and [nt/timeline.md](nt/timeline.md) (every chapter
in date order) or [reference/anchors.md](reference/anchors.md) (the key dates and
the debates behind them).

## How it's built

The text and the research are kept apart, so either can change without touching the
other:

| Path | What it is | Edit it? |
|---|---|---|
| `source/engwebp-usfm/` | WEB text, all 66 books (Protestant canon, "LORD" edition), unaltered USFM from [eBible.org](https://ebible.org/Scriptures/engwebp_usfm.zip), downloaded 2026-10-27. `copr.htm` is its public-domain notice. | No. Replace it to update the text. |
| `data/sources*.yaml` | Bibliography: every work cited, by key. | Yes |
| `data/anchors-*.yaml` | Chronological anchors: the exodus, Qarqar 853 BC, 597/587 BC, Cyrus, Antiochus IV, Herod's death, the crucifixion year, Gallio, AD 70… each with its views, explanation and sources. | Yes |
| `data/ot/NN-book.yaml`, `data/nt/NN-book.yaml` | Per book: date of writing (with views) and a date for every chapter. | Yes |
| `tools/build.py` | Merges text and data into Markdown (`nt/`). | Rarely |
| `tools/build_html.py` | Builds the web page (`docs/index.html`) from the same data. | Rarely |
| `ot/`, `nt/`, `reference/`, `docs/index.html` | Generated output. | **No.** Rebuilt from the above. |

Rebuild after any change:

```
python3 tools/build.py           # writes ot/, nt/, reference/ (Markdown)
python3 tools/build_html.py      # writes docs/index.html (web page)
python3 tools/build.py --check   # validate only
```

It needs Python 3 with PyYAML (`pip install pyyaml`). The build fails if a chapter
has no date, or if it cites an anchor or source key that doesn't exist.

Commit and push both outputs; GitHub Pages republishes the web page from
`docs/index.html` on `main` within a minute or two.

Everything is plain text (YAML and Markdown), so it diffs cleanly in git and converts
to other formats, e.g. `pandoc nt/40-matthew.md -o matthew.docx` or `.epub`/`.pdf`.

## How the dates work

- **Kinds of book.** `narrative` (Genesis–Esther, Gospels, Acts, Revelation): the
  date of the chapter's events. `prophecy`: when the oracle was given. `writing`
  (Psalms, wisdom books, Lamentations) and `letter`: when it was written.
- **Two models where one disputed date moves many chapters** (fields `a` and `b`):
  the exodus, c. 1446 BC or c. 1260 BC (Exodus to Judges), and the crucifixion,
  7 April AD 30 or 3 April AD 33 (the Gospels and early Acts). See `exodus`,
  `models` and `crucifixion` in the anchor files.
- **Tradition vs critical dates.** For books whose authorship or composition is
  disputed (the Pentateuch, Isaiah 40–66, Daniel, Ecclesiastes, the disputed Pauline
  letters, 2 Peter…) the heading gives both dates, and the book introduction sets out
  who holds which view.
- **Undated.** Genesis 1–11 and similar material get `range: null`: no historical
  date can be given. The heading says so and explains the traditional reckonings.
- `range: [lo, hi]` is the span that covers the main views (negative = BC, no year
  0). The timelines sort by its midpoint, or by `sort:` when a chapter sets one
  (psalms are sorted by the date their heading gives).

### A chapter entry

```yaml
chapters:
  14:
    date: "spring AD 29 or 32"         # shown in the heading
    a: "spring AD 29"                  # Model A (crucifixion AD 30), optional
    b: "spring AD 32"                  # Model B (crucifixion AD 33), optional
    range: [29, 32]                    # for sorting
    anchors: [john-baptist-death, models]   # pulls in their reasoning and sources
    note: >-
      Chapter-specific reasoning (internal clues, seasons, feasts...).
    sources: ["josephus-ant 18.116–119", hoehner]   # "key locator"
```

A letter's chapters inherit `default:` and list only the chapters with something of
their own to add. Citation format is `"key locator"`. Quote it when the locator has a
comma, or YAML splits it into two entries.

## Status and research to do

- **First draft (2026-10-27):** all 1,189 chapters (929 OT, 260 NT) have a date,
  reasoning and citations, with 57 anchors and 119 sources. The Old Testament data was
  drafted by several Claude helpers working to one brief, then checked by the build
  (every chapter present, every anchor and source key real).
- **Citations aren't verified yet.** They were written from knowledge of the standard
  literature, without checking against copies. Ancient references (Josephus, Tacitus,
  etc.) are given by book and section; modern works by title, with a chapter only
  where it's well known, and no page numbers. Every source is marked
  `status: unverified` in `data/sources.yaml`. As each one is checked, add page
  numbers to the citations and set `status: verified`.
- Good next steps:
  1. Verify the anchors first (they carry most of the weight), especially Brown 1997
     and Carson & Moo 2005 for each book's date.
  2. Add more views where only two are given, e.g. a Jewish-studies or Roman-history
     perspective, and recent work after 2010.
  3. Finer dates for Revelation and the letters' internal events (Galatians 1–2,
     2 Corinthians 11) as separate "events" notes.
  4. Old Testament items flagged while drafting: the day-exact Babylonian dates
     (Ezekiel, Haggai, Zechariah, Nehemiah 6:15) should be checked against Parker &
     Dubberstein's tables; several Josephus locators; scholars named in notes who
     aren't in the bibliography yet (Duhm, Mowinckel, de Wette, Bright, Porphyry).

## Licence

The World English Bible is in the public domain (see `source/engwebp-usfm/copr.htm`).
"World English Bible" is a trademark of eBible.org, which asks that changed texts not
use the name. The scripture text here is unaltered; the date headings are additions
and are clearly separated from it.
