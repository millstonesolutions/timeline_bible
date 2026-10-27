# Timeline Bible

The New Testament text of the World English Bible, with a heading on every chapter
giving its approximate date, the reasoning behind it, the scholarly views where they
disagree, and citations.

**Read it:** [nt/README.md](nt/README.md) (book list),
[nt/timeline.md](nt/timeline.md) (every chapter in date order),
[nt/anchors.md](nt/anchors.md) (the key dates and the debates behind them).

## How it's built

The text and the research are kept apart, so either can change without touching the
other:

| Path | What it is | Edit it? |
|---|---|---|
| `source/engwebp-usfm/` | WEB text (Protestant canon, "LORD" edition), unaltered USFM from [eBible.org](https://ebible.org/Scriptures/engwebp_usfm.zip), downloaded 2026-10-27. `copr.htm` is its public-domain notice. | No. Replace it to update the text. |
| `data/sources.yaml` | Bibliography: every work cited, by key. | Yes |
| `data/anchors.yaml` | Chronological anchors: Herod's death, Luke 3:1, the crucifixion year, Gallio, Festus, AD 70, Domitian… each with its views, explanation and sources. | Yes |
| `data/nt/NN-book.yaml` | Per book: date of writing (with views) and a date for every chapter. | Yes |
| `tools/build.py` | Merges text and data into Markdown. | Rarely |
| `nt/*.md` | Generated output. | **No.** Rebuilt from the above. |

Rebuild after any change:

```
python3 tools/build.py           # writes nt/
python3 tools/build.py --check   # validate only
```

It needs Python 3 with PyYAML (`pip install pyyaml`). The build fails if a chapter
has no date, or if it cites an anchor or source key that doesn't exist.

Everything is plain text (YAML and Markdown), so it diffs cleanly in git and converts
to other formats, e.g. `pandoc nt/40-matthew.md -o matthew.docx` or `.epub`/`.pdf`.

## How the dates work

- **Narrative books** (Gospels, Acts, Revelation): the date of the events in the
  chapter. **Letters**: the date the letter was written.
- **Two models for Jesus' ministry.** The crucifixion is dated to 7 April AD 30 or to
  3 April AD 33, and both have wide support. Chapters inside the ministry give a date
  under each model (fields `a` and `b`). See `models` and `crucifixion` in
  `data/anchors.yaml`.
- **Authorship-dependent dates.** For disputed letters (Ephesians, Colossians,
  2 Thessalonians, the Pastorals, James, 1–2 Peter, Jude) the heading gives both
  dates, "if by X" and "if not", and the book introduction sets out who holds which.
- `range: [lo, hi]` is the span that covers the main views (negative = BC, no year
  0). It's used to sort `nt/timeline.md`.

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

- **First draft (2026-10-27):** all 260 NT chapters have a date, reasoning and
  citations; 23 anchors; 50 sources.
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
  4. Old Testament: the same structure in `data/ot/`; the WEB USFM for it is in the
     same eBible.org zip.

## Licence

The World English Bible is in the public domain (see `source/engwebp-usfm/copr.htm`).
"World English Bible" is a trademark of eBible.org, which asks that changed texts not
use the name. The scripture text here is unaltered; the date headings are additions
and are clearly separated from it.
