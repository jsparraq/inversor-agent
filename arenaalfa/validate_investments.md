# validate_investments.py — Documentation

Reads the latest USA and Colombia summary reports from `arenaalfa/reports/`, fetches current market prices via `yfinance`, and produces a single unified validation Markdown report categorising every company as **BUY**, **WATCH**, or **NOT ATTRACTIVE**.

## Usage

```bash
poetry run python arenaalfa/validate_investments.py
```

No arguments required. The script auto-discovers the most recent report file for each market by prefix.

---

## Flow

```
ultimo_reporte (USA + Colombia)
        ↓
parsear_reporte_usa  /  parsear_reporte_colombia
        ↓
precio_actual (yfinance)  /  precio_colombia (BVC → yfinance map)
        ↓
zona_precio_usa  /  zona_colombia  →  semaforo_usa  /  veredicto_colombia
        ↓
generar_reporte → validation_YYYY-MM-DD.md
```

---

## Step-by-step Details

### Step 1 — Report discovery (`ultimo_reporte`)

Globs `arenaalfa/reports/` for files matching `{prefix}_*.md`, sorts by filename (ISO date suffix), and returns the most recent one. Exits with an error message if no file is found.

| Prefix constant | Matches |
|-----------------|---------|
| `summary_invest_usa` | USA scraper output |
| `summary_invest_colombia` | Colombia scraper output |

---

### Step 2 — Parsing USA report (`parsear_reporte_usa`)

Supports two formats within the same file:

1. **Detailed blocks** — `### N. TICKER` sections with full price zone and CAGR data. Extracted fields: `study_date`, `momento`, `score`, `value`, `deep_value`, `hist_val`, `bear_price`, `base_price`, `bull_price`, `cagr_bear`, `cagr_base`, `cagr_bull`.
2. **Full Table** — `## Full Table` markdown table used for companies not covered in the top-N detail blocks. Extracts: `study_date`, `momento`, `score`, `cagr_base`, `cagr_bull` only (no price zones).

Returns `(report_date, list[dict])`.

---

### Step 3 — Parsing Colombia report (`parsear_reporte_colombia`)

Reads the `## Full Table` section (covers every company, not just top N). Columns expected: `Ticker | Last Updated | Rating | Fundamental Price | Score`.

Returns `(report_date, list[dict])` with: `ticker`, `study_date`, `rating`, `score`, `p_fundamental`.

---

### Step 4 — Price fetch

#### USA (`precio_actual`)
Calls `yf.Ticker(symbol).fast_info.last_price`. Returns `float | None`.

#### Colombia (`precio_colombia`)
Looks up the BVC ticker in `COL_TICKER_YFINANCE` to get the yfinance symbol (`.CL` BVC listing in COP, or ADR in USD). Returns `(price, currency, yf_symbol)`.

**Currency rules:**
- Symbols in `COL_ADR_SYMBOLS` → `"USD"` (e.g. `CIB` for Bancolombia/Pfbancolombia ADR).
- All other `.CL` symbols → `"COP"`.

**`COL_TICKER_YFINANCE` map (as of 2026-03-28):**

| BVC Ticker | yfinance Symbol | Currency |
|------------|----------------|----------|
| TIN | TIN.CL | COP |
| PROMIGAS | PROMIGAS.CL | COP |
| CELSIA | CELSIA.CL | COP |
| BVC | BVC.CL | COP |
| ECOPETROL | ECOPETROL.CL | COP |
| PFGRUPOARGOS | PFGRUPOARG.CL | COP |
| PFCORFICOL | PFCORFICOL.CL | COP |
| BHI | BHI.CL | COP |
| PFGRUPOSURA | PFGRUPSURA.CL | COP |
| TERPEL | TERPEL.CL | COP |
| ISA | ISA.CL | COP |
| BOGOTA | BOGOTA.CL | COP |
| EXITO | EXITO.CL | COP |
| CEMARGOS | CEMARGOS.CL | COP |
| PFCEMARGOS | PFCEMARGOS.CL | COP |
| FABRICATO | FABRICATO.CL | COP |
| GRUPO AVAL | GRUPOAVAL.CL | COP |
| PF GRUPO AVAL | PFAVAL.CL | COP |
| GRUPO SURA | GRUPOSURA.CL | COP |
| GRUPO ARGOS | GRUPOARGOS.CL | COP |
| GRUPO BOLIVAR | GRUBOLIVAR.CL | COP |
| EEB | GEB.CL | COP |
| CORFICOL | CORFICOLCF.CL | COP |
| DAVIVIENDA | PFDAVVNDA.CL | COP |
| MINEROS | MINEROS.CL | COP |
| NUTRESA | NUTRESA.CL | COP |
| BANCOLOMBIA | CIB | USD (ADR) |
| PFBANCOLOMBIA | CIB | USD (ADR) |

To test a new symbol: `python -c "import yfinance as yf; print(yf.Ticker('SYMBOL').fast_info.last_price)"`

---

### Step 5 — Valuation logic

#### USA — Price zone (`zona_precio_usa`)

Compares current price against study price zones in priority order:

| Condition | Zone label |
|-----------|-----------|
| `precio ≤ hist_val[1]` | `HISTORICAL VALUATION (very cheap)` |
| `precio < deep_value[0]` | `BELOW DEEP VALUE (very cheap)` |
| `deep_value[0] ≤ precio ≤ deep_value[1]` | `DEEP VALUE` |
| `deep_value[1] < precio ≤ value[0]` | `BETWEEN DEEP VALUE AND VALUE` |
| `value[0] ≤ precio ≤ value[1]` | `VALUE` |
| `precio > value[1]` | `ABOVE VALUE (expensive)` |
| No zones available | `no zone defined` |

#### USA — Signal (`semaforo_usa`)

```
attractive zone = HISTORICAL VALUATION / BELOW DEEP VALUE / DEEP VALUE / BETWEEN DEEP VALUE AND VALUE

BUY           → attractive zone  AND  (implied CAGR_base ≥ original CAGR_base × 0.85  OR  no base price available)
WATCH         → attractive zone with degraded CAGR  OR  zone == VALUE
NOT ATTRACTIVE→ everything else (ABOVE VALUE, no zone, price unavailable)
```

Implied CAGR is recalculated over a fixed 5-year horizon from current price to the study's base-case target.

#### Colombia — Signal (`veredicto_colombia`)

Derived directly from the Arena Alfa rating string:

| Rating | Signal |
|--------|--------|
| undervalued | BUY |
| neutral | WATCH |
| overvalued | NOT ATTRACTIVE |
| extremely overvalued | NOT ATTRACTIVE |

#### Colombia — Price zone vs fundamental (`zona_colombia`)

Compares current COP price to the study fundamental price (both in COP):

| Ratio (current / fundamental) | Zone |
|-------------------------------|------|
| ≤ 0.70 | `WELL BELOW FUNDAMENTAL (X% to target)` |
| 0.70 – 1.00 | `BELOW FUNDAMENTAL (X% to target)` |
| 1.00 – 1.10 | `AT/NEAR FUNDAMENTAL` |
| > 1.10 | `ABOVE FUNDAMENTAL (X% over)` |

Only shown when currency is COP and a fundamental price exists in the report. For ADRs the fundamental COP price is displayed with a note that currencies differ.

#### COP price parsing (`parsear_precio_cop`)

Handles Colombian locale format where `.` is the thousands separator and `,` is the decimal separator:
- `"COP 19.000,00"` → `19000.0`
- `"COP 460,00"` → `460.0`

---

### Step 6 — Report generation (`generar_reporte`)

Writes `arenaalfa/reports/validation_YYYY-MM-DD.md`.

**Report structure:**

```
# Investment Validation — Combined Opportunities
(metadata: sources, date, totals)

## BUY (N)
  ### N. TICKER 🇺🇸  (detailed block per company)
  ### N. TICKER 🇨🇴  (detailed block per company)

## WATCH (N)
  (same format)

## NOT ATTRACTIVE (N)
  (compact table: Market | Ticker | Current price | Zone/Rating | Implied base CAGR)
```

**USA detail block fields:** current price, price zone, study date, investment moment, composite score, price zones from study (Deep Value / Value / Historical), projections (bear/base/bull upside and implied CAGR vs original CAGR).

**Colombia detail block fields:** rating, score, last updated, current price + currency, fundamental price, price vs fundamental zone (if COP).

---

## Output

```
arenaalfa/reports/validation_YYYY-MM-DD.md
```

---

## Dependencies

- `yfinance` — real-time price fetching
- `re`, `sys`, `datetime`, `pathlib` — Python standard library
