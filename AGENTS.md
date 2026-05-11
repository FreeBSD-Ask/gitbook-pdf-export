# Agent Instructions

- Preserve existing code comments when modifying files in this repository.
- Follow PEP 8 styling for Python files unless existing context dictates otherwise.
- Use two-space indentation for YAML files under `.github/`.
- Prefer adding or updating automated tests or workflows when introducing new build steps.
- Run `python mdconv.py -h` after significant code changes to ensure the CLI remains operational.

## Project Overview

`mdconv.py` converts GitBook-style Markdown documentation into PDF and EPUB. It reads `SUMMARY.md` for the file list, renders Markdown to HTML via mistune, converts LaTeX formulas to PNG images, and produces final output with WeasyPrint (PDF) and EbookLib (EPUB).

## Architecture

- **Entry point**: `main()` → `prepare_build_dir()` → `combine_markdown_to_html_parallel()` → WeasyPrint PDF + EbookLib EPUB
- **Formula pipeline**: `preprocess_formulas()` → `render_latex_to_png()` → xelatex/pdflatex → PDF → PyMuPDF (fitz) → PNG → `<img>` tag
- **Image pipeline**: `convert_local_paths_worker()` handles local copy tasks and remote image downloads
- **Styling**: `start.html` contains all CSS (including `.formula-display` / `.formula-inline` for rendered formulas)
- **Multi-process**: `ProcessPoolExecutor` is used for Markdown→HTML, path conversion, and image copying

## Key Files

| File | Purpose |
|---|---|
| `mdconv.py` | Main conversion script |
| `start.html` | HTML template with CSS styles |
| `requirements.txt` | Python dependencies |
| `AGENTS.md` | This file — AI agent instructions |

## Dependencies

### Python (pip / requirements.txt)

- `weasyprint>=68.1` — PDF generation
- `mistune` — Markdown to HTML
- `pygments` — Code syntax highlighting
- `EbookLib` — EPUB generation
- `beautifulsoup4` — HTML parsing
- `PyMuPDF` — PDF to PNG conversion for formula rendering

### System (optional, for LaTeX formula support)

- **LaTeX engine**: xelatex (preferred, CJK support) > lualatex > pdflatex
  - Windows: MiKTeX (`winget install MiKTeX.MiKTeX`)
  - Ubuntu: `sudo apt install texlive-xetex texlive-lang-chinese fonts-wqy-microhei`
  - FreeBSD: `pkg install texlive-xetex`

Formula rendering is **gracefully degraded**: if PyMuPDF or a LaTeX engine is missing, formulas are left as raw `$$...$$` text in the output.

## Formula Rendering Details

- Display formulas (`$$...$$`) → `<img class="formula-display">` (block, centered)
- Inline formulas (`$...$`) → `<img class="formula-inline">` (inline, height 1.5em)
- Code blocks (`` ```...``` `` and `` `...` ``) are protected from formula substitution
- Each formula is hashed (MD5, first 12 chars) for caching — re-rendering is skipped if the PNG already exists
- CJK-containing formulas require xelatex/lualatex with `ctex` package; pdflatex will fail for CJK

## CI/CD

- `.github/workflows/build-binaries.yml` — builds PyInstaller binaries for Ubuntu, Windows, and FreeBSD
- `.github/dependabot.yml` — daily dependency updates for GitHub Actions and pip
