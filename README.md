# pitfall-re

Reverse-engineering workspace for **Pitfall: The Mayan Adventure** (Win32, 1995),
bootstrapped with the [`/re` skill](https://github.com/vgrichina/re-skill).

Read [`CLAUDE.md`](CLAUDE.md) for conventions and the tool index, and
[`REVERSE.md`](REVERSE.md) for findings and the task list.

**The game data is not in this repository.** `game/` is gitignored — it holds
retail, copyrighted files. Supply your own copy of `PITFALL.EXE`, `INIT.PH` and
`LEVEL00.PH`…`LEVEL24.PH` there before running anything.

## Web port

A browser port is in progress; stage 1 (background renderer) is live.
`tools/export_web.py` turns the `.PH` files into a ~1.9 MB asset bundle under
`web/data/`, and `web/` deploys to GitHub Pages via
`.github/workflows/pages.yml`. See [`docs/architecture_web.md`](docs/architecture_web.md).

## Quick start

```bash
cd pitfall-re
python3 tools/instruction_set.py            # decoder self-tests
python3 tools/pe_info.py --dirs --imports   # identify the binary
python3 tools/check_ph.py                   # validate the .PH model on all 26 files
python3 tools/dis.py 0x004460E0 40          # annotated disassembly of load_level
python3 tools/render_level.py --all         # decode every level to gfx/*.png
python3 tools/gen_catalog.py                # asset browser data
python3 tools/export_web.py                 # web port asset bundle
cd web && python3 -m http.server 8000       # then open / or /catalog.html
```

Everything is stdlib-only Python 3.8+ — no disassembler library, no PNG library,
no build step.
