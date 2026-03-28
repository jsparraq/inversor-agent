# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
poetry install

# Install Chromium browser for Playwright
poetry run playwright install chromium

# Run the scraper (prompts for email + password interactively)
poetry run python arenaalfa/usa/scraper_world.py

# Run with custom options
poetry run python arenaalfa/usa/scraper_world.py --top 10 --meses 12
```

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | 5 | Companies to include in the ranking |
| `--meses M` | 24 | Months back to look for studies |

## Architecture

Single scraper project. The only runnable entry point is `arenaalfa/usa/scraper_world.py`. Documentation lives in `arenaalfa/usa/scraper_world.md`.

### Scraper flow (6 steps)

```
step_login → step_ir_a_curriculum → step_abrir_listado → step_extraer_links → step_analizar_empresas → step_guardar_reporte
```

1. **`step_login`** — Password login via Teachable SSO. reCAPTCHA v3 is bypassed with `--disable-blink-features=AutomationControlled`, a real Chrome user-agent, and `navigator.webdriver` patched to `undefined` via `add_init_script`.
2. **`step_ir_a_curriculum`** — Navigate to the enrolled course curriculum page.
3. **`step_abrir_listado`** — JS-click (`page.evaluate`) the Start button on `li[data-lecture-id='46603807']` to land on the LISTADO DE ESTUDIOS lecture page. A regular Playwright `.click()` fails because the element may be outside the viewport.
4. **`step_extraer_links`** — Extract `(href, anchorText, ticker)` from `.lecture-text-container` paragraphs. Ticker = `p.textContent − a.textContent` (full paragraph text minus anchor text). Filters to studies within the `--meses` window; stops on first study older than cutoff (list is newest-first).
5. **`step_analizar_empresas`** — Opens each company lecture URL in a new page, scrolls to load dynamic content, extracts financial fields (scenarios, CAGRs, price zones, momento) via regex from full page text including iframes.
6. **`step_guardar_reporte`** — Scores each company (`CAGR_base×0.4 + CAGR_opt×0.3 + momento_pts×0.3`), prints top N, writes `resumen_inversiones_YYYY-MM-DD.md`.

### Debug output

Every run saves HTML + screenshots to `debug_html/` (gitignored). Files named by step: `01_after_login`, `02_curriculum`, `03_listado_estudios`, `04_frame_links`, `empresa_<ticker>`. On failure additional `*_error_*` files are saved.
