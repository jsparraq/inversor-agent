# scraper_world.py — Documentation

## Overview

Automated scraper for **Arena Alfa** investment study platform (Teachable-based). It logs in with email and password, navigates to the LISTADO DE ESTUDIOS lecture, extracts financial data from each company study published within a configurable time window, ranks them by a composite score, and exports a Markdown report.

---

## Requirements

- Python 3.12+
- [Poetry](https://python-poetry.org/) for dependency management
- Dependencies declared in `pyproject.toml`: `playwright`

Install dependencies and Chromium:
```bash
poetry install
poetry run playwright install chromium
```

---

## Usage

Run from the project root using Poetry:

```bash
poetry run python arenaalfa/usa/scraper_world.py [--top N] [--meses M]
```

| Argument  | Default | Description                                    |
|-----------|---------|------------------------------------------------|
| `--top`   | 5       | Number of companies to include in the ranking  |
| `--meses` | 24      | How many months back to look for studies       |

**Example:**
```bash
poetry run python arenaalfa/usa/scraper_world.py --top 10 --meses 12
```

The script will prompt for email and password interactively before starting.

---

## Flow

```
1. step_login              — Email + password login (prompts via stdin)
         ↓
2. step_ir_a_curriculum    — Navigate to the enrolled course page
         ↓
3. step_abrir_listado      — JS-click the Start button on the LISTADO DE ESTUDIOS row
         ↓
4. step_extraer_links      — Extract company links and tickers from .lecture-text-container
         ↓
5. step_analizar_empresas  — Visit each company page and scrape financial data
         ↓
6. step_guardar_reporte    — Rank by score, print top N, save Markdown report
```

---

## Step-by-step Details

### Step 1 — `step_login`
Navigates to the password login URL and fills `input#email` + `input#password`, then clicks `input[data-testid='login-button']`. Waits for `networkidle` to confirm the session is established.

- **Login URL:** `https://sso.teachable.com/secure/1229078/identity/login/password?force=true`
- **reCAPTCHA v3:** The browser is launched with `--disable-blink-features=AutomationControlled`, a real Chrome user-agent, and `navigator.webdriver` patched to `undefined` via `add_init_script` to pass the invisible reCAPTCHA score check.

### Step 2 — `step_ir_a_curriculum`
Navigates to `https://arenaalfa.teachable.com/courses/enrolled/1762706` — the enrolled course curriculum page. This is where the sidebar list of lectures (including LISTADO DE ESTUDIOS) is rendered.

### Step 3 — `step_abrir_listado`
Clicks the **Start** button on the LISTADO DE ESTUDIOS row using `page.evaluate()`:

```javascript
document.querySelector("li[data-lecture-id='46603807'] a").click()
```

JavaScript click is used instead of Playwright's `.click()` to bypass actionability checks (the element may be outside the viewport). After the click, the browser navigates to the LISTADO DE ESTUDIOS lecture page which contains the full company list with tickers.

### Step 4 — `step_extraer_links`
The LISTADO DE ESTUDIOS page contains a `<div class="lecture-text-container">` with one `<p>` per company study:

```html
<p><a href="URL">Caso de Estudio DATE</a>: TICKER<br></p>
```

The scraper evaluates JavaScript across all frames to find this container and extract `(href, anchorText, ticker)` for each entry. The ticker is computed as:

```
ticker = p.textContent − a.textContent  (leading ": " stripped)
```

Results are then filtered to only include studies within the `--meses` window. The list is ordered newest-first, so iteration stops as soon as a study older than the cutoff date is found.

### Step 5 — `step_analizar_empresas`
Calls `extraer_datos_empresa()` for each company. Each call opens a new page, loads the lecture URL, scrolls to trigger dynamic content, and extracts financial fields via regex from the full page text (including iframes).

### Step 6 — `step_guardar_reporte`
Sorts results by composite score (descending), selects the top N, prints a summary to stdout, and writes `resumen_inversiones_YYYY-MM-DD.md` to the working directory.

---

## Data Extracted per Company

| Field                  | Description                                      |
|------------------------|--------------------------------------------------|
| `escenario_negativo`   | Bear-case price target (USD)                    |
| `escenario_base`       | Base-case price target (USD)                    |
| `escenario_optimista`  | Bull-case price target (USD)                    |
| `cagr_negativo`        | Bear-case CAGR (%)                              |
| `cagr_base`            | Base-case CAGR (%)                              |
| `cagr_optimista`       | Bull-case CAGR (%)                              |
| `value`                | VALUE price range (e.g. `100 - 106 USD`)        |
| `deep_value`           | DEEP VALUE price range                          |
| `valoracion_historica` | Historical valuation range                      |
| `momento`              | Investment moment: DEEP VALUE / VALUE / NEUTRAL / CARA |
| `score`                | Composite ranking score (see formula below)     |

---

## Scoring Formula

```
score = (CAGR base × 0.40) + (CAGR optimista × 0.30) + (momento_pts × 0.30)
```

Moment points:

| Momento     | Points |
|-------------|--------|
| DEEP VALUE  | 10.0   |
| VALUE       | 7.0    |
| NEUTRAL     | 4.0    |
| CARA        | 1.0    |
| desconocido | 3.0    |

---

## Output

A Markdown file named `resumen_inversiones_YYYY-MM-DD.md` is saved in the current working directory. It contains:

- A ranked detail section for the top N companies
- A full sortable table of all companies analyzed

---

## Debug Files

Every run saves HTML snapshots and screenshots to `debug_html/` automatically:

| File | When saved |
|------|-----------|
| `debug_html/01_after_login.*` | Immediately after login |
| `debug_html/02_curriculum.*` | After navigating to the course curriculum |
| `debug_html/03_listado_estudios.*` | After clicking Start on LISTADO DE ESTUDIOS |
| `debug_html/03_error_click_listado.*` | If the LISTADO DE ESTUDIOS row is not found |
| `debug_html/04_frame_links.*` | The frame where company links were extracted |
| `debug_html/04_error_no_links.*` | If `.lecture-text-container` is not found |
| `debug_html/04_error_sin_empresas.*` | If no studies match the date filter |
| `debug_html/empresa_<ticker>.*` | Full page for every company visited |

---

## Key Implementation Notes

- **Login:** Password-based SSO via `https://sso.teachable.com`. No OTP/PIN required.
- **reCAPTCHA v3 bypass:** Browser is launched with `--disable-blink-features=AutomationControlled`, a macOS Chrome user-agent, and `navigator.webdriver` patched to `undefined` so the invisible reCAPTCHA v3 assigns a passing score.
- **Curriculum navigation:** After login the browser lands on the enrolled course page. Step 3 clicks the LISTADO DE ESTUDIOS row via `page.evaluate()` (JavaScript click) because the element may be off-screen or in a collapsed section.
- **Ticker extraction:** Tickers live as text after `<a>` tags in `.lecture-text-container`. Computed as `p.textContent − a.textContent` — more reliable than walking `nextSibling` text nodes.
- **Iframe awareness:** `texto_de_pagina()` searches all frames for content containing "escenario" or "cagr" when the main frame body does not have it.
- **Date parsing:** Supports Spanish month abbreviations (`Ene`, `Feb`, … `Dic`) and 2- or 4-digit years.
- **Headless mode:** Runs Chromium headlessly. Set `headless=False` in `main()` for visual debugging.
