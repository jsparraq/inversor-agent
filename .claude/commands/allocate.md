# Monthly Capital Allocation — Arena Alfa

Generates a capital allocation proposal based on the latest deep analysis report (`deep_analysis_*.md`). Receives the investment amount in Colombian pesos (COP) as a parameter.

**Usage:** `/allocate 2000000`

---

## STEP 1 — Read the amount and load the report

The argument received is the **COP amount** to invest (e.g. `2000000` = COP 2,000,000).

If no argument is provided, ask the user: "How much capital in COP do you want to invest this month?"

Use Glob to find the most recent file matching `arenaalfa/reports/deep_analysis_*.md`. Read it. Extract the following for every stock with `MANTENER CONVICCION` conviction:

- Ticker and country (🇺🇸 / 🇨🇴)
- Tier (1 or 2)
- Current price (USD for USA · COP for Colombia)
- Upside % to fundamental (Colombia) or implied Base CAGR (USA)
- Superinvestor signal: `VALIDADO` / `POSICIÓN MENOR` / `SIN POSICIÓN CONOCIDA` / `VENDIDO RECIENTEMENTE`
- Any confirmed insider buying notes

Ignore all stocks with `VIGILAR` or `REVISAR` conviction — they receive no allocation.

Announce: "Investment amount: COP [X]. Base report: [filename]. Eligible stocks: [MANTENER CONVICCION list]."

---

## STEP 2 — Fetch current USD/COP exchange rate

Search for the current exchange rate with WebSearch:

```
TRM dolar peso colombiano hoy [today's date]
```

Extract the current TRM value (Tasa Representativa del Mercado — official Colombian market rate). If not found, use 4,000 COP/USD as a conservative fallback and state it explicitly in the report.

---

## STEP 3 — Calculate allocation weights

Assign a **weight score** to each `MANTENER CONVICCION` stock using the following formula:

### Base score
- USA stocks: `base_score = Base_CAGR_% × 5` (normalizes CAGR to a scale comparable with Colombia upside %)
- Colombia stocks: `base_score = upside_to_fundamental_%`

### Multipliers
Apply in sequence on top of the base score:

| Factor | Condition | Multiplier |
|--------|-----------|------------|
| Superinvestor | `VALIDADO` | × 1.5 |
| Superinvestor | `POSICIÓN MENOR` or confirmed insider buying | × 1.1 |
| Superinvestor | `SIN POSICIÓN CONOCIDA` | × 1.0 |
| Superinvestor | `VENDIDO RECIENTEMENTE` | × 0.6 |
| Tier | Tier 1 | × 1.2 |
| Tier | Tier 2 | × 0.8 |

### Normalization
1. Sum all weighted scores → `total_score`
2. Each stock weight = `(stock_score / total_score) × 97%` (reserve 3% as liquidity)
3. Round weights to 1 decimal place

### COP allocated per stock
`cop_allocated = total_amount × weight`

---

## STEP 4 — Calculate units per stock

### Colombian stocks (whole shares only)
- Units: `units = floor(cop_allocated / price_cop)`
- `actual_cost = units × price_cop`
- `remainder = cop_allocated - actual_cost`
- If `units = 0` (price exceeds the allocated COP), flag: "Insufficient capital for 1 share — remainder moved to liquidity."

### USA stocks (fractional shares)
- Convert USD price to COP: `price_cop = price_usd × TRM`
- `fractions = cop_allocated / price_cop` (2 decimal places)
- `usd_equivalent = cop_allocated / TRM` (2 decimal places)

### Liquidity
`liquidity = total_amount × 3% + sum_of_colombia_remainders`

---

## STEP 5 — Generate the report

Save to `arenaalfa/reports/allocation_[AMOUNT]_[YYYY-MM-DD].md` where AMOUNT is the argument received (e.g. `allocation_2000000_2026-04-01.md`).

Use exactly this structure:

---

```markdown
# Monthly Allocation Proposal — Arena Alfa
**Date:** [today's date]
**Capital to invest:** COP [formatted with dots, e.g. 2,000,000]
**USD/COP reference (TRM):** [value] COP/USD
**Base report:** [deep_analysis filename]
**Eligible stocks (MANTENER CONVICCION):** [N] stocks

---

## Allocation Summary

| # | Stock | Country | Weight | COP Allocated | Units | Actual Cost | Remainder |
|---|-------|---------|--------|--------------|-------|-------------|-----------|
[one row per stock + Liquidity row + TOTAL row]

---

## Visual Distribution

[ASCII bar chart showing % per stock, max 40 chars wide]
Example:
  ADBE  35% ██████████████
  DUOL  15% ██████
  ...

---

## Position Detail

### [N]. [TICKER] [FLAG]
| Field | Value |
|-------|-------|
| Allocation | COP [X] ([%]) |
| Reference price | [price] (USA: USD + COP equiv.) |
| Units to buy | [N fractions / N whole shares] |
| Actual cost | COP [X] |
| Upside / CAGR | [upside % to fundamental or base CAGR] |
| Superinvestor signal | [signal + key detail in 1 line] |
| Rationale | [1-2 sentences explaining this weight] |

[repeat for each stock]

---

## Simplified Projection (base scenario ~5 years)

| Stock | COP Invested | Base Scenario | Estimated Return |
|-------|-------------|---------------|-----------------|
[one row per stock]
| **Total portfolio** | **COP [X]** | **COP [Y]** | **+[Z]% · ~[CAGR]% p.a.** |

> Projection based on upside/CAGR from the Arena Alfa report. Does not guarantee future performance.

---

## Monthly Alerts

[Bullet list of situations to watch this month:
- Dividend dates within the next 30 days
- Upcoming earnings dates
- Stocks with VENDIDO RECIENTEMENTE signal
- Stocks whose price has moved close to the fundamental since the last report
- Stocks with units = 0 due to insufficient capital]

---

## Execution Steps

1. Check the live TRM at time of purchase (reference used: [TRM])
2. [List Colombia stocks first with exact price × units]
3. [List USA stocks with fraction amount and USD equivalent]
4. Remaining liquidity: COP [X] — keep in a savings account or accumulate for next month

---

## Methodology Notes
- Only stocks with `MANTENER CONVICCION` conviction receive capital
- Weights calculated with: base_score × superinvestor_multiplier × tier_multiplier
- Colombian stocks: whole units only (floor); USA stocks: fractional (requires broker with fractional share support)
- This report is analytical support based on the Arena Alfa framework and does not constitute professional financial advice
```

---

## STEP 6 — Summary to user

After saving the file, output:

```
Allocation proposal generated for COP [amount].

[summary table with ticker, units, and COP allocated]

Alerts:
- [one bullet per alert identified]

Report saved to: arenaalfa/reports/allocation_[amount]_[date].md
```

---

## Important notes

- **Only MANTENER CONVICCION stocks receive capital.** VIGILAR and REVISAR are excluded even if they appear in the BUY list of the validation report.
- If the allocated COP for a Colombian stock is less than the price of 1 whole share, add the full amount to liquidity and flag it as an alert.
- If no `deep_analysis_*.md` exists in `arenaalfa/reports/`, tell the user to run `/stock-analysis` first.
- The calculated weights are a starting proposal — the user may adjust them manually. The goal is a rational, reproducible baseline every month.
- Always show the **actual cost** (whole units × price) vs. the theoretical COP allocated for Colombia stocks, so the user knows exactly how much is spent.
- Format all COP numbers with dot thousands separator (e.g. `1.234.567`) and USD with comma decimal (e.g. `$1,234.56`).
- The filename includes both the amount and the date so monthly reports are never overwritten and build a historical record.
