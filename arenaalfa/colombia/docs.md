# scraper_colombia.py — Documentation

Scraper for investment ratings on Colombian companies from Arena Alfa (`arenaalfa.com`). Uses Playwright to automate the browser, extracts rating and price data from the Estudios de Valoración listing, and generates an English Markdown report.

## Usage

```bash
# Run with default options
poetry run python arenaalfa/colombia/scraper_colombia.py

# With custom options
poetry run python arenaalfa/colombia/scraper_colombia.py --top 10 --meses 12
```

| Flag | Default | Description |
|------|---------|-------------|
| `--top N` | 5 | Companies to include in the ranking |
| `--meses M` | 24 | Months back to look for studies |

When executed, the script prompts for credentials interactively (only when the saved session has expired):

```
>>> Enter your username and press ENTER:
>>> Enter your password and press ENTER:
```

---

## Architecture

### Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `URL_BASE` | `https://www.arenaalfa.com/` | Site entry point |
| `URL_VALORACION` | `https://www.arenaalfa.com/valoracion` | Estudios de Valoración listing |
| `SESSION_FILE` | `arenaalfa/colombia/session.json` | Saved Playwright storage state |
| `MESES_ES` | dict `ene/jan→1 … dic/dec→12` | Maps Spanish and English month abbreviations to numeric values |
| `RATING_PTS` | dict | Maps Spanish rating strings to score points |
| `RATING_EN` | dict | Maps Spanish rating strings to English labels for the report |

### Scraper flow (6 steps)

```
step_login → step_go_to_listing → step_extract_companies → step_analyze_companies → step_save_report → step_logout
```

### Data source

All company data is extracted from the single listing page (`/valoracion`), which is rendered by the custom Joomla component `com_preciosobj`. Each company is a `div.com-preciosobj-item` element containing rating, prices, and date. No individual company pages are visited.

---

## Functions

### `parse_date(texto) → date | None`

Converts a date string to a `date` object.

**Input:** string in formats like `"25/Jan/2026"`, `"15-Ene-2026"`, `"02-Oct-25"` — separators `-`, `/`, or space.

**Output:** `date` object, or `None` if the format is not recognised.

**Logic:**
1. Lowercases and splits by separator (`[-/\s]`).
2. Extracts day, month (via `MESES_ES`, supports Spanish and English abbreviations), and year.
3. Two-digit years are expanded to 4 digits by adding 2000.

---

### `page_text(page) → str`

Extracts visible text from a page, including iframes.

**Logic:**
1. Attempts `page.inner_text("body")` on the main frame.
2. If the text does not contain `"escenario"` or `"cagr"`, iterates over all frames looking for one that does.
3. Returns the first matching frame text, or the main body text if none is found.

---

### `save_debug(page, debug_dir, nombre)`

Saves the current page HTML and a screenshot to `debug_html/<nombre>.html` and `debug_html/<nombre>.png`.

---

### `is_logged_in(page) → bool`

Navigates to `URL_BASE` and returns `True` if `#link-login` is not visible (i.e. the session is still active).

---

### `step_login(page, context, debug_dir)`

**Step 1:** Reuses a saved session from `session.json` if still valid, otherwise performs an interactive login.

**Steps (fresh login):**
1. Navigates to `URL_BASE`.
2. Closes the legal popup (`#legal-overlay .close`) if present.
3. Clicks `#link-login` to open the login popup.
4. Prompts for username and password via console.
5. Fills `#modlgn-username` and `#modlgn-passwd`, clicks the submit button.
6. Detects and reports the "account in use" error, then exits if found.
7. Saves the session state to `session.json`.

---

### `step_go_to_listing(page, debug_dir)`

**Step 2:** Navigates directly to `URL_VALORACION` (`/valoracion`). Saves debug snapshot `02_listado_valoracion`.

---

### `step_extract_companies(page, debug_dir, fecha_corte, meses) → list[dict]`

**Step 3:** Extracts all company data from the `com-preciosobj` listing page.

**Selector used:** `div.com-preciosobj-item`

**Per-item extraction (via `page.evaluate`):**

| Field | Source |
|-------|--------|
| `ticker` | `h4 a` text |
| `url` | `h4 a` href |
| `rating` | `h5.rating-info` text |
| `fecha` | `.item-right li` containing `"Fecha:"` |
| `precios` | All `.item-left li` texts |

**Post-processing:**
- Dates are parsed with `parse_date`; entries older than `fecha_corte` are discarded.
- Price fields are matched by label keywords: `"hipótesis"`, `"cambio de rating"`, `"fundamental"`.
- Score is assigned directly from `RATING_PTS`.

**Output dict structure per company:**

```python
{
    "nombre":               str,         # Ticker (e.g. "TIN", "BANCOLOMBIA")
    "fecha":                date,        # Date of last rating update
    "url":                  str,         # Link to reporte-consolidado-colombia page
    "rating":               str,         # Original Spanish rating string
    "precio_hipotesis":     str | None,  # Study hypothesis entry price
    "precio_cambio_rating": str | None,  # Price at which rating changes
    "precio_fundamental":   str | None,  # Fundamental (target) price
    "score":                float,       # Ranking score (see table below)
}
```

**Scoring:**

| Rating | Score |
|--------|-------|
| Subvaloración (Undervalued) | 10.0 |
| Neutral | 5.0 |
| Sobrevaloración (Overvalued) | 2.0 |
| Sobrevaloración Extrema (Extremely Overvalued) | 0.0 |
| Unknown | 3.0 |

---

### `step_analyze_companies(context, empresas, debug_dir) → list[dict]`

**Step 4:** Passthrough — all data was already extracted in step 3. Prints a summary line per company and returns the list unchanged.

---

### `step_save_report(resultados, top_n, fecha_corte)`

**Step 5:** Sorts companies by score descending, prints the top N to the console, calls `generar_markdown`, and writes the report to:

```
arenaalfa/reports/summary_invest_colombia_YYYY-MM-DD.md
```

---

### `step_logout(page, context, debug_dir)`

**Step 6:** Logs out by submitting `#login-form` via JS (`page.evaluate`), bypassing the CSS `display:none` on the form container. Refreshes `session.json` with the logged-out state.

---

### `generate_markdown(top_empresas, todas, fecha_corte) → str`

Generates the English Markdown report.

**Report structure:**
1. Header with generation date, analysed period, total company count, and ranking criterion.
2. Detailed section for each top N company: ticker, last updated date, English rating, score, and the three price fields.
3. Full table of all companies sorted by score descending.

Rating strings are translated to English via `RATING_EN` (e.g. `"Subvaloración"` → `"Undervalued"`).

---

## Implementation Status

| Step | Status | Description |
|------|--------|-------------|
| Login | Complete | Auth via popup; session reuse via `session.json` |
| `step_go_to_listing` | Complete | Direct `goto` to `/valoracion` |
| `step_extract_companies` | Complete | JS query on `div.com-preciosobj-item`; all data from listing page |
| `step_analyze_companies` | Complete (passthrough) | No individual page visits needed |
| `step_save_report` | Complete | English Markdown saved to `arenaalfa/reports/` |
| `step_logout` | Complete | Submits `#login-form` via JS (Joomla `task=user.logout`) |

---

## Debug output

Every run saves HTML + screenshots to `debug_html/` (gitignored):

| File | When saved |
|------|------------|
| `01_after_login.*` | After login (or session reuse) |
| `02_listado_valoracion.*` | After navigating to `/valoracion` |
| `03_listado_links.*` | After extracting company items |
| `03_error_no_items.*` | If no `com-preciosobj-item` elements found |
| `03_error_sin_empresas.*` | If no companies pass the date filter |
| `06_logout.*` | After logout |

---

## Dependencies

- `playwright` — browser automation (Chromium)
- `argparse`, `re`, `sys`, `datetime`, `pathlib` — Python standard library
