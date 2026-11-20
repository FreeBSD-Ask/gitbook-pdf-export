# Agent Instructions

- Preserve existing code comments when modifying files in this repository.
- Follow PEP 8 styling for Python files unless existing context dictates otherwise.
- Use two-space indentation for YAML files under `.github/`.
- Prefer adding or updating automated tests or workflows when introducing new build steps.
- Run `python mdconv.py -h` after significant code changes to ensure the CLI remains operational.

## Project Overview

`mdconv.py` converts GitBook-style Markdown documentation into PDF and EPUB. It reads `SUMMARY.md` for the file list, renders Markdown to HTML via mistune, converts LaTeX formulas to SVG images, and produces final output with WeasyPrint (PDF) and EbookLib (EPUB).

## Architecture

- **Entry point**: `main()` → `prepare_build_dir()` → `combine_markdown_to_html_parallel()` → WeasyPrint PDF + EbookLib EPUB
- **Formula pipeline**: `preprocess_formulas()` → `render_latex_to_svg()` → xelatex `-no-pdf` → XDV → dvisvgm → SVG → `<img>` tag; rendered SVGs are cached persistently in `~/.cache/mdconv/formulas` (override via `MDCONV_FORMULA_CACHE`) so repeated builds skip re-rendering
- **Image pipeline**: `convert_local_paths_worker()` handles local copy tasks and remote image downloads
- **Navigation**: PDF gets a typeset table of contents page (built from body headings by `build_toc_page`, page numbers via `target-counter`, cover and TOC excluded from page numbering) plus sidebar bookmarks whose depth is controlled by `--bookmark-depth` (Markdown heading level, default 2 → `build_bookmark_css` writes the rules into `pdf.html`); the source TOC files (`mu-lu.md`, `SUMMARY.md`) are excluded from the body and never typeset as a page. EPUB uses its generated `nav`, DOCX inserts a Word TOC field. The TOC page only exists in `pdf.html`; `final.html` (EPUB/DOCX input) has no TOC page
- **Styling**: `start.html` contains all CSS (including `.formula-display` / `.formula-inline` for rendered formulas, heading `bookmark-level` rules, and the named `@page cover` used to hide the cover page number)
- **Multi-process**: `ProcessPoolExecutor` is used for Markdown→HTML, path conversion, and image copying
- **PDF/A-4 output**: `pdf_version="2.0"` + `pdf_variant="pdf/a-4u"`; `_patch_pdfa4_output()` wraps WeasyPrint internals to close four ISO 19005-4 gaps (drop `pdfaid:conformance` for base level, add `pdfaid:rev="2020"`, sanitize NaN coordinates in `pydyf._to_bytes`, force `Interpolate` false)

## Key Files

| File | Purpose |
|---|---|
| `mdconv.py` | Main conversion script |
| `start.html` | HTML template with CSS styles |
| `requirements.txt` | Python dependencies |
| `tests/test_mdconv.py` | Regression tests (`python -m unittest discover -s tests`) |
| `tests/build_pdfa_sample.py` | Builds the minimal sample PDF validated in CI |
| `tests/verapdf_cli.py` | Downloads veraPDF CLI (cached) and validates a PDF (`-f 4`) |
| `AGENTS.md` | This file — AI agent instructions |

## Dependencies

### Python (pip / requirements.txt)

- `weasyprint>=68.1` — PDF generation (includes CairoSVG for SVG rendering)
- `mistune` — Markdown to HTML
- `pygments` — Code syntax highlighting
- `EbookLib` — EPUB generation
- `beautifulsoup4` — HTML parsing

No Python package is needed for formula rendering — it relies entirely on system tools (LaTeX + dvisvgm).

### System (optional, for LaTeX formula support)

- **LaTeX engine**: xelatex (preferred, CJK support) > lualatex > pdflatex
- **dvisvgm**: converts DVI/XDV to SVG (included in standard TeX distributions)
  - Windows: MiKTeX (`winget install MiKTeX.MiKTeX`) — dvisvgm included
  - Ubuntu: `sudo apt install texlive-xetex texlive-lang-chinese fonts-wqy-microhei` — dvisvgm included in `texlive-extra-utils`
  - FreeBSD: `pkg install texlive-xetex` — dvisvgm included

Formula rendering is **gracefully degraded**: if a LaTeX engine is missing, formulas are left as raw `$$...$$` text in the output.

## Formula Rendering Details

- Display formulas (`$$...$$`) → `<img class="formula-display">` (block, centered, SVG vector)
- Inline formulas (`$...$`) → `<img class="formula-inline">` (inline, height 1.2em, SVG vector)
- Code blocks (`` ```...``` `` and `` `...` ``) are protected from formula substitution
- Each formula is hashed (MD5, first 12 chars) for caching — re-rendering is skipped if the SVG already exists
- CJK-containing formulas require xelatex/lualatex with `ctex` package; pdflatex will fail for CJK
- SVG output uses `--no-fonts` flag in dvisvgm (glyphs are converted to paths, ensuring portability)

## CI/CD

- `.github/workflows/build-binaries.yml` — builds PyInstaller binaries on Python 3.15 for Ubuntu, Windows, and FreeBSD
- `.github/workflows/tests.yml` — runs the unit test suite on Python 3.15, builds a sample PDF and validates it with veraPDF (`tests/verapdf_cli.py`, PDF/A-4 flavour 4)
- `.github/dependabot.yml` — daily dependency updates for GitHub Actions and pip
