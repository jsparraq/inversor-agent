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

Two scrapers + one validator. Entry points:

| Script | Purpose | Platform |
|--------|---------|----------|
| `arenaalfa/usa/scraper_world.py` | Scrape USA / international companies | Teachable LMS |
| `arenaalfa/colombia/scraper_colombia.py` | Scrape Colombia (BVC) companies | arenaalfa.com (Joomla) |
| `arenaalfa/validate_investments.py` | Cross-market validation + current prices | yfinance |

```bash
# Colombia scraper
poetry run python arenaalfa/colombia/scraper_colombia.py
poetry run python arenaalfa/colombia/scraper_colombia.py --top 10 --meses 12

# Validation (reads latest reports from arenaalfa/reports/, fetches live prices)
poetry run python arenaalfa/validate_investments.py
```

Documentation: `arenaalfa/usa/docs.md`, `arenaalfa/colombia/docs.md`, and `arenaalfa/validate_investments.md`.

### USA scraper flow (6 steps)

```
step_login → step_ir_a_curriculum → step_abrir_listado → step_extraer_links → step_analizar_empresas → step_guardar_reporte
```

1. **`step_login`** — Password login via Teachable SSO. reCAPTCHA v3 is bypassed with `--disable-blink-features=AutomationControlled`, a real Chrome user-agent, and `navigator.webdriver` patched to `undefined` via `add_init_script`.
2. **`step_ir_a_curriculum`** — Navigate to the enrolled course curriculum page.
3. **`step_abrir_listado`** — JS-click (`page.evaluate`) the Start button on `li[data-lecture-id='46603807']` to land on the LISTADO DE ESTUDIOS lecture page. A regular Playwright `.click()` fails because the element may be outside the viewport.
4. **`step_extraer_links`** — Extract `(href, anchorText, ticker)` from `.lecture-text-container` paragraphs. Ticker = `p.textContent − a.textContent` (full paragraph text minus anchor text). Filters to studies within the `--meses` window; stops on first study older than cutoff (list is newest-first).
5. **`step_analizar_empresas`** — Opens each company lecture URL in a new page, scrolls to load dynamic content, extracts financial fields (scenarios, CAGRs, price zones, momento) via regex from full page text including iframes.
6. **`step_guardar_reporte`** — Scores each company (`CAGR_base×0.4 + CAGR_opt×0.3 + momento_pts×0.3`), prints top N, writes `resumen_inversiones_YYYY-MM-DD.md`.

### Colombia scraper flow (6 steps)

```
step_login → step_go_to_listing → step_extract_companies → step_analyze_companies → step_save_report → step_logout
```

1. **`step_login`** — Reuses saved session from `session.json` if still valid; otherwise prompts for credentials interactively and saves the new session.
2. **`step_go_to_listing`** — Navigates directly to `/valoracion` (Estudios de Valoración listing).
3. **`step_extract_companies`** — Queries `div.com-preciosobj-item` elements via `page.evaluate`. Extracts ticker, URL, rating, date, and the three price fields (hypothesis, rating-change, fundamental) from each item. Filters by `--meses` cutoff. Scores by rating: Undervalued=10, Neutral=5, Overvalued=2, Extremely Overvalued=0. All data comes from the listing page — no individual company pages are visited.
4. **`step_analyze_companies`** — Passthrough; prints a summary line per company and returns the list unchanged.
5. **`step_save_report`** — Sorts by score, prints top N, calls `generate_markdown`, writes `summary_invest_colombia_YYYY-MM-DD.md` to `arenaalfa/reports/`.
6. **`step_logout`** — Submits `#login-form` via JS to bypass the CSS-hidden form container (Joomla `task=user.logout`). Refreshes `session.json` with the logged-out state.

### Validation flow (validate_investments.py)

```
ultimo_reporte (USA + Colombia) → parsear_reporte_usa / parsear_reporte_colombia
        ↓
precio_actual / precio_colombia  (yfinance — BVC tickers mapped via COL_TICKER_YFINANCE)
        ↓
zona_precio_usa + semaforo_usa  /  veredicto_colombia + zona_colombia
        ↓
generar_reporte → arenaalfa/reports/validation_YYYY-MM-DD.md
```

1. **`ultimo_reporte`** — Globs `arenaalfa/reports/` for the most recent `summary_invest_usa_*.md` and `summary_invest_colombia_*.md`.
2. **`parsear_reporte_usa`** — Extracts detailed blocks (`### N. TICKER`) plus `## Full Table` fallback; yields price zones, CAGR scenarios, score, and investment moment per company.
3. **`parsear_reporte_colombia`** — Reads `## Full Table`; yields ticker, rating, fundamental price, and score for every Colombian company.
4. **Price fetch** — USA: `yf.Ticker(ticker).fast_info.last_price`. Colombia: BVC tickers resolved via `COL_TICKER_YFINANCE` map (`.CL` → COP; `CIB` ADR → USD).
5. **Valuation logic** — USA: price zone (Historical / Deep Value / Value / Above Value) + implied 5-year CAGR vs original → BUY / WATCH / NOT ATTRACTIVE. Colombia: Arena Alfa rating (undervalued → BUY, neutral → WATCH, over/extremely over → NOT ATTRACTIVE).
6. **`generar_reporte`** — Writes unified `validation_YYYY-MM-DD.md` with BUY (detailed), WATCH (detailed), and NOT ATTRACTIVE (compact table) sections.

### Skills

| Skill | Trigger | Description |
|-------|---------|-------------|
| `/stock-analysis` | `.claude/commands/stock-analysis.md` | Deep analysis of BUY stocks from the latest validation report. Fetches current news, confirms price zones, checks superinvestor holdings, and generates a tiered priority report in `arenaalfa/reports/deep_analysis_YYYY-MM-DD.md` |
| `/allocate [COP]` | `.claude/commands/allocate.md` | Generates a monthly capital allocation proposal for a given COP amount (e.g. `/allocate 2000000`). Reads the latest `deep_analysis_*.md`, weights only `MANTENER CONVICCION` stocks using tier + superinvestor signal + upside/CAGR, fetches current TRM (USD/COP), calculates exact whole shares for Colombia and fractional shares for USA, and saves `arenaalfa/reports/allocation_[amount]_[YYYY-MM-DD].md` |

**Usage:** Type `/stock-analysis` in Claude Code. The skill auto-detects the latest `validation_*.md` report, analyzes every BUY stock using WebSearch/WebFetch, and produces a priority-tiered markdown report.

**Pipeline (7 steps):**
1. Load latest `validation_*.md` and extract all BUY stocks
2. Fetch current macro context (Fed, Banrep, USD/COP, S&P 500, Colcap)
3. Analyze each BUY stock — news, price confirmation, conviction check (`MANTENER CONVICCION` / `VIGILAR` / `REVISAR`)
4. **Superinvestors check** — for every `MANTENER CONVICCION` stock, searches SEC 13F filings via Dataroma/GuruFocus to see if Warren Buffett, Bill Ackman, Michael Burry, David Einhorn, Seth Klarman, Mohnish Pabrai, Li Lu, Joel Greenblatt, Guy Spier, Howard Marks (or others) hold a position. Colombian stocks: checks BlackRock ICOLCAP ETF and AFP pension fund exposure. Classifies each as `VALIDADO` / `POSICIÓN MENOR` / `SIN POSICIÓN CONOCIDA` / `VENDIDO RECIENTEMENTE`.
5. Group into priority tiers (superinvestor signal can promote a stock within its tier)
6. Generate and save the report
7. Print summary to user

**Output structure:**
- Tier 1: highest conviction + largest upside (boosted if `VALIDADO` by superinvestors)
- Tier 2: good entry, moderate upside
- Tier 3: watch / review (approaching target or mixed signals)
- `## Señal de Superinversores` — summary table of all MANTENER CONVICCION stocks vs. known institutional holders
- `## Resumen Ejecutivo` — full table with `Superinv.` column

### Debug output

Every run saves HTML + screenshots to `debug_html/` (gitignored).

**USA:** `01_after_login`, `02_curriculum`, `03_listado_estudios`, `04_frame_links`, `empresa_<ticker>`.

**Colombia:** `01_after_login`, `02_listado_valoracion`, `03_listado_links`, `06_logout`. On failure: `03_error_no_items`, `03_error_sin_empresas`.
