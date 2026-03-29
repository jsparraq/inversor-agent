"""
validate_investments.py
-----------------------
Reads the latest USA and Colombia summary reports, fetches current prices
for all tickers via yfinance, and produces a single unified validation report.
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path

import yfinance as yf


REPORTS_DIR = Path("./arenaalfa/reports")
USA_PREFIX  = "summary_invest_usa"
COL_PREFIX  = "summary_invest_colombia"


# ─────────────────────────────────────────
# COLOMBIA TICKER → YFINANCE SYMBOL MAP
# ─────────────────────────────────────────
# BVC tickers don't map directly to yfinance.
#   .CL suffix → local BVC listing, price in COP  (preferred: direct COP comparison)
#   ADR        → US exchange listing, price in USD (only fallback when .CL unavailable)
#
# To test a new ticker: python -c "import yfinance as yf; print(yf.Ticker('SYMBOL').fast_info.last_price)"
# Not available in yfinance (as of 2026-03-28):
#   PFBANCOLOMBIA (ordinary — uses preferred ADR CIB as fallback)

COL_TICKER_YFINANCE: dict[str, str] = {
    # ── BVC local listings — price in COP (.CL) ───────────────────
    "TIN":          "TIN.CL",
    "PROMIGAS":     "PROMIGAS.CL",
    "CELSIA":       "CELSIA.CL",
    "BVC":          "BVC.CL",
    "ECOPETROL":    "ECOPETROL.CL",
    "PFGRUPOARGOS": "PFGRUPOARG.CL",
    "PFCORFICOL":   "PFCORFICOL.CL",
    "BHI":          "BHI.CL",
    "PFGRUPOSURA":  "PFGRUPSURA.CL",
    "TERPEL":       "TERPEL.CL",
    "ISA":          "ISA.CL",
    "BOGOTA":       "BOGOTA.CL",
    "EXITO":        "EXITO.CL",
    "CEMARGOS":     "CEMARGOS.CL",
    "PFCEMARGOS":   "PFCEMARGOS.CL",
    "FABRICATO":    "FABRICATO.CL",
    "GRUPO AVAL":    "GRUPOAVAL.CL",
    "PF GRUPO AVAL": "PFAVAL.CL",
    "GRUPO SURA":    "GRUPOSURA.CL",
    "GRUPO ARGOS":   "GRUPOARGOS.CL",
    "GRUPO BOLIVAR": "GRUBOLIVAR.CL",
    "EEB":           "GEB.CL",
    "CORFICOL":      "CORFICOLCF.CL",
    "DAVIVIENDA":    "PFDAVVNDA.CL",   # preferred shares (ordinary not available)
    "MINEROS":       "MINEROS.CL",
    "NUTRESA":       "NUTRESA.CL",
    # ── ADR on NYSE — price in USD (no .CL available) ─────────────
    "BANCOLOMBIA":   "CIB",   # Bancolombia preferred ADR
    "PFBANCOLOMBIA": "CIB",   # Bancolombia preferred ADR
}

# yfinance symbols whose price is quoted in USD (ADRs, not COP)
COL_ADR_SYMBOLS: set[str] = {"CIB"}


# ─────────────────────────────────────────
# REPORT DISCOVERY
# ─────────────────────────────────────────

def ultimo_reporte(prefix: str) -> Path:
    archivos = sorted(
        REPORTS_DIR.glob(f"{prefix}_*.md"),
        key=lambda p: p.stem.replace(f"{prefix}_", ""),
        reverse=True,
    )
    if not archivos:
        print(f"ERROR: No report found in {REPORTS_DIR} with prefix '{prefix}'")
        sys.exit(1)
    return archivos[0]


# ─────────────────────────────────────────
# USA REPORT PARSING
# ─────────────────────────────────────────

def parsear_rango(texto: str):
    """'180 - 190 USD' → (180.0, 190.0) or None if not available."""
    if not texto or texto.strip().lower() == "not available":
        return None
    m = re.search(r"([\d,\.]+)\s*[-–]\s*([\d,\.]+)", texto)
    if m:
        return float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
    return None


def parsear_reporte_usa(path: Path) -> tuple[date, list[dict]]:
    """Parses all USA companies: detailed blocks first, then Full Table for the rest."""
    texto = path.read_text(encoding="utf-8")

    m_fecha = re.search(r"\*\*Generated:\*\*\s*(\d{2}-\d{2}-\d{4})", texto)
    if m_fecha:
        fecha_reporte = datetime.strptime(m_fecha.group(1), "%d-%m-%Y").date()
    else:
        fecha_reporte = date.today()

    # 1. Parse detailed blocks (### N. TICKER) — full price zone + CAGR data
    detallados: dict[str, dict] = {}
    bloques = re.split(r"(?=^### \d+\.)", texto, flags=re.MULTILINE)

    for bloque in bloques:
        ticker_m = re.search(r"### \d+\.\s+(\S+)", bloque)
        if not ticker_m:
            continue
        ticker = ticker_m.group(1).strip("`")

        def campo(patron, b=bloque):
            m = re.search(patron, b)
            return m.group(1).strip() if m else None

        study_date_str = campo(r"\*\*Study date:\*\*\s*(\S+)")
        momento        = campo(r"\*\*Investment moment:\*\*\s*`?([^`\n]+)`?")
        score_str      = campo(r"\*\*Composite score:\*\*\s*([\d\.]+)")
        value_str      = campo(r"- Value:\s+(.+)")
        deep_value_str = campo(r"- Deep Value:\s+(.+)")
        hist_val_str   = campo(r"- Historical valuation:\s+(.+)")
        bear_price_m   = re.search(r"Bear case:\s+\$([\d\.]+)", bloque)
        base_price_m   = re.search(r"Base case:\s+\$([\d\.]+)", bloque)
        bull_price_m   = re.search(r"Bull case:\s+\$([\d\.]+)", bloque)
        cagr_bear_m    = re.search(r"Bear case:.+CAGR\s+([\d\.]+)%", bloque)
        cagr_base_m    = re.search(r"Base case:.+CAGR\s+([\d\.]+)%", bloque)
        cagr_bull_m    = re.search(r"Bull case:.+CAGR\s+([\d\.]+)%", bloque)

        detallados[ticker] = {
            "ticker":      ticker,
            "study_date":  study_date_str,
            "momento":     momento or "unknown",
            "score":       float(score_str) if score_str else 0.0,
            "value":       parsear_rango(value_str),
            "deep_value":  parsear_rango(deep_value_str),
            "hist_val":    parsear_rango(hist_val_str),
            "bear_price":  float(bear_price_m.group(1)) if bear_price_m else None,
            "base_price":  float(base_price_m.group(1)) if base_price_m else None,
            "bull_price":  float(bull_price_m.group(1)) if bull_price_m else None,
            "cagr_bear":   float(cagr_bear_m.group(1)) if cagr_bear_m else None,
            "cagr_base":   float(cagr_base_m.group(1)) if cagr_base_m else None,
            "cagr_bull":   float(cagr_bull_m.group(1)) if cagr_bull_m else None,
        }

    # 2. Full Table — picks up companies not included in the top-N detailed blocks
    # Format: | Ticker | Date | CAGR Base | CAGR Bull | Moment | Score |
    tabla_m = re.search(
        r"## Full Table.*?\n\|[^\n]+\|\n\|[-| ]+\|\n((?:\|[^\n]+\|\n?)*)",
        texto, re.DOTALL,
    )
    if tabla_m:
        for linea in tabla_m.group(1).strip().splitlines():
            partes = [p.strip() for p in linea.strip("|").split("|")]
            if len(partes) < 6 or not partes[0] or partes[0].startswith("-"):
                continue
            ticker = partes[0]
            if ticker in detallados:
                continue
            try:
                cagr_base = float(partes[2].rstrip("%")) if partes[2].rstrip("%") else None
                cagr_bull = float(partes[3].rstrip("%")) if partes[3].rstrip("%") else None
                score     = float(partes[5]) if partes[5] else 0.0
            except ValueError:
                continue
            detallados[ticker] = {
                "ticker":      ticker,
                "study_date":  partes[1],
                "momento":     partes[4],
                "score":       score,
                "value":       None,
                "deep_value":  None,
                "hist_val":    None,
                "bear_price":  None,
                "base_price":  None,
                "bull_price":  None,
                "cagr_bear":   None,
                "cagr_base":   cagr_base,
                "cagr_bull":   cagr_bull,
            }

    return fecha_reporte, list(detallados.values())


# ─────────────────────────────────────────
# COLOMBIA REPORT PARSING
# ─────────────────────────────────────────

RATING_VERDICT = {
    "undervalued":           "BUY",
    "neutral":               "WATCH",
    "overvalued":            "NOT ATTRACTIVE",
    "extremely overvalued":  "NOT ATTRACTIVE",
}


def parsear_reporte_colombia(path: Path) -> tuple[date, list[dict]]:
    """Parses ALL Colombia companies from the Full Table (covers every company, not just top N)."""
    texto = path.read_text(encoding="utf-8")

    m_fecha = re.search(r"\*\*Generated:\*\*\s*([\d-]+)", texto)
    if m_fecha:
        try:
            fecha_reporte = datetime.strptime(m_fecha.group(1), "%Y-%m-%d").date()
        except ValueError:
            fecha_reporte = date.today()
    else:
        fecha_reporte = date.today()

    # Full Table: | Ticker | Last Updated | Rating | Fundamental Price | Score |
    tabla_m = re.search(
        r"## Full Table.*?\n\|[^\n]+\|\n\|[-| ]+\|\n((?:\|[^\n]+\|\n?)*)",
        texto, re.DOTALL,
    )
    empresas = []
    if tabla_m:
        for linea in tabla_m.group(1).strip().splitlines():
            partes = [p.strip() for p in linea.strip("|").split("|")]
            if len(partes) < 5 or not partes[0] or partes[0].startswith("-"):
                continue
            ticker, fecha_str, rating, p_fund, score_str = partes[0], partes[1], partes[2], partes[3], partes[4]
            try:
                study_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                study_date = None
            try:
                score = float(score_str)
            except ValueError:
                score = 0.0
            empresas.append({
                "ticker":        ticker,
                "study_date":    study_date,
                "rating":        rating,
                "score":         score,
                "p_fundamental": p_fund if p_fund != "N/A" else None,
            })

    return fecha_reporte, empresas


def veredicto_colombia(rating: str) -> str:
    return RATING_VERDICT.get(rating.strip().lower(), "WATCH")


# ─────────────────────────────────────────
# PRICE FETCH (USA & COLOMBIA)
# ─────────────────────────────────────────

def precio_actual(symbol: str) -> float | None:
    """Fetches the last price for any yfinance symbol."""
    try:
        info = yf.Ticker(symbol).fast_info
        precio = info.last_price
        return round(float(precio), 2) if precio else None
    except Exception as e:
        print(f"  [WARN] Could not fetch price for {symbol}: {e}")
        return None


def precio_colombia(bvc_ticker: str) -> tuple[float | None, str, str]:
    """Returns (price, currency, yf_symbol) for a Colombian BVC ticker.

    Looks up COL_TICKER_YFINANCE for a mapping; falls back to the raw ticker.
    Currency is 'USD' for known ADRs, 'COP' otherwise (best-effort).
    """
    symbol   = COL_TICKER_YFINANCE.get(bvc_ticker, bvc_ticker)
    currency = "USD" if symbol in COL_ADR_SYMBOLS else "COP"
    precio   = precio_actual(symbol)
    return precio, currency, symbol


def parsear_precio_cop(texto: str) -> float | None:
    """Converts Colombian COP price strings to float.
    'COP 19.000,00' → 19000.0  |  'COP 460,00' → 460.0
    Colombian format: period = thousands sep, comma = decimal sep.
    """
    if not texto:
        return None
    s = re.sub(r"[Cc][Oo][Pp]\s*", "", texto).strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def zona_colombia(precio_cop: float, fundamental_cop: float) -> str:
    """Price zone relative to the study fundamental price (both in COP)."""
    ratio = precio_cop / fundamental_cop
    upside = (fundamental_cop / precio_cop - 1) * 100
    if ratio <= 0.70:
        return f"WELL BELOW FUNDAMENTAL ({upside:.0f}% to target)"
    if ratio < 1.00:
        return f"BELOW FUNDAMENTAL ({upside:.0f}% to target)"
    if ratio <= 1.10:
        return "AT/NEAR FUNDAMENTAL"
    return f"ABOVE FUNDAMENTAL ({(ratio-1)*100:.0f}% over)"


# ─────────────────────────────────────────
# USA ANALYSIS HELPERS
# ─────────────────────────────────────────

def zona_precio_usa(precio: float, emp: dict) -> str:
    dv   = emp["deep_value"]
    val  = emp["value"]
    hist = emp["hist_val"]

    if hist and precio <= hist[1]:
        return "HISTORICAL VALUATION (very cheap)"
    if dv and precio < dv[0]:
        return "BELOW DEEP VALUE (very cheap)"
    if dv and dv[0] <= precio <= dv[1]:
        return "DEEP VALUE"
    if val and dv and dv[1] < precio <= val[0]:
        return "BETWEEN DEEP VALUE AND VALUE"
    if val and val[0] <= precio <= val[1]:
        return "VALUE"
    if val and precio > val[1]:
        return "ABOVE VALUE (expensive)"
    return "no zone defined"


def cagr_actual(precio_hoy: float, precio_objetivo: float, anos: float) -> float | None:
    if not precio_hoy or not precio_objetivo or anos <= 0:
        return None
    return round(((precio_objetivo / precio_hoy) ** (1 / anos) - 1) * 100, 2)


def semaforo_usa(zona: str, cagr_base_actual: float | None, cagr_base_original: float | None) -> str:
    atractiva = zona in (
        "HISTORICAL VALUATION (very cheap)",
        "BELOW DEEP VALUE (very cheap)",
        "DEEP VALUE",
        "BETWEEN DEEP VALUE AND VALUE",
    )
    cagr_ok = (
        cagr_base_actual is not None
        and cagr_base_original is not None
        and cagr_base_actual >= cagr_base_original * 0.85
    )
    if atractiva and (cagr_ok or cagr_base_actual is None):
        return "BUY"
    if atractiva:
        return "WATCH"
    if zona == "VALUE":
        return "WATCH"
    return "NOT ATTRACTIVE"




# ─────────────────────────────────────────
# UNIFIED MARKDOWN REPORT
# ─────────────────────────────────────────

def generar_reporte(
    resultados_usa: list[tuple[dict, float | None]],
    resultados_col: list[tuple[dict, float | None, str, str]],
    fuente_usa: Path,
    fuente_col: Path,
) -> str:
    hoy  = datetime.now().strftime("%d-%m-%Y")
    anos = 5.0

    def v_usa(emp, precio):
        if precio is None:
            return "NOT ATTRACTIVE"
        return semaforo_usa(
            zona_precio_usa(precio, emp),
            cagr_actual(precio, emp["base_price"], anos),
            emp["cagr_base"],
        )

    def v_col(emp):
        return veredicto_colombia(emp["rating"])

    usa_buy   = [(e, p) for e, p in resultados_usa if v_usa(e, p) == "BUY"]
    usa_watch = [(e, p) for e, p in resultados_usa if v_usa(e, p) == "WATCH"]
    usa_no    = [(e, p) for e, p in resultados_usa if v_usa(e, p) == "NOT ATTRACTIVE"]

    col_buy   = [(e, p, c, s) for e, p, c, s in resultados_col if v_col(e) == "BUY"]
    col_watch = [(e, p, c, s) for e, p, c, s in resultados_col if v_col(e) == "WATCH"]
    col_no    = [(e, p, c, s) for e, p, c, s in resultados_col if v_col(e) == "NOT ATTRACTIVE"]

    total_buy   = len(usa_buy)   + len(col_buy)
    total_watch = len(usa_watch) + len(col_watch)
    total_no    = len(usa_no)    + len(col_no)

    def seccion_usa(emp, precio, i):
        zona   = zona_precio_usa(precio, emp)
        c_bear = cagr_actual(precio, emp["bear_price"], anos)
        c_base = cagr_actual(precio, emp["base_price"], anos)
        c_bull = cagr_actual(precio, emp["bull_price"], anos)
        up = lambda obj: f"{(obj/precio-1)*100:+.1f}%" if obj and precio else "N/A"

        lineas = [
            f"### {i}. {emp['ticker']} 🇺🇸",
            f"- **Current price:** ${precio:.2f} USD",
            f"- **Price zone:** `{zona}`",
            f"- **Study date:** {emp['study_date']}",
            f"- **Investment moment (study):** `{emp['momento']}`",
            f"- **Composite score:** {emp['score']}",
            "- **Price zones (from study):**",
        ]
        if emp["deep_value"]:
            lineas.append(f"  - Deep Value: ${emp['deep_value'][0]} – ${emp['deep_value'][1]} USD")
        if emp["value"]:
            lineas.append(f"  - Value:      ${emp['value'][0]} – ${emp['value'][1]} USD")
        if emp["hist_val"]:
            lineas.append(f"  - Historical: ${emp['hist_val'][0]} – ${emp['hist_val'][1]} USD")
        lineas.append(f"- **Projections from current price (~{anos:.0f}-year horizon):**")
        if emp["bear_price"]:
            lineas.append(f"  - Bear: ${emp['bear_price']:.0f}  upside {up(emp['bear_price'])}  implied CAGR {c_bear}%  (original: {emp['cagr_bear']}%)")
        if emp["base_price"]:
            lineas.append(f"  - Base: ${emp['base_price']:.0f}  upside {up(emp['base_price'])}  implied CAGR {c_base}%  (original: {emp['cagr_base']}%)")
        if emp["bull_price"]:
            lineas.append(f"  - Bull: ${emp['bull_price']:.0f}  upside {up(emp['bull_price'])}  implied CAGR {c_bull}%  (original: {emp['cagr_bull']}%)")
        lineas.append("")
        return "\n".join(lineas)

    def seccion_col(emp, precio, currency, yf_symbol, i):
        lineas = [
            f"### {i}. {emp['ticker']} 🇨🇴",
            f"- **Rating:** `{emp['rating']}`",
            f"- **Score:** {emp['score']}",
            f"- **Last updated:** {emp['study_date']}",
        ]
        if precio is not None:
            lineas.append(f"- **Current price ({yf_symbol}):** {precio:,.2f} {currency}")
            if currency == "COP" and emp["p_fundamental"]:
                fundamental = parsear_precio_cop(emp["p_fundamental"])
                if fundamental:
                    zona = zona_colombia(precio, fundamental)
                    lineas.append(f"- **Fundamental price:** {emp['p_fundamental']}")
                    lineas.append(f"- **vs Fundamental:** `{zona}`")
            elif currency == "USD":
                lineas.append(f"- **Fundamental price (COP):** {emp['p_fundamental'] or 'N/A'} _(ADR — currencies differ)_")
        else:
            lineas.append(f"- **Current price:** not available via yfinance")
            if emp["p_fundamental"]:
                lineas.append(f"- **Fundamental price:** {emp['p_fundamental']}")
        lineas.append("")
        return "\n".join(lineas)

    # ── Build report ──────────────────────────────────────────────
    lineas = [
        "# Investment Validation — Combined Opportunities",
        "",
        f"**Generated:** {hoy}  ",
        f"**USA source:** `{fuente_usa.name}`  ",
        f"**Colombia source:** `{fuente_col.name}`  ",
        f"**Total companies analyzed:** {len(resultados_usa) + len(resultados_col)} ({len(resultados_usa)} USA · {len(resultados_col)} Colombia)  ",
        f"**Buy opportunities:** {total_buy}  ",
        f"**Watch list:** {total_watch}  ",
        "**Criteria:** USA — current price vs value zones + implied CAGR · Colombia — Arena Alfa rating + price vs fundamental",
        "",
        "---",
        "",
    ]

    if usa_buy or col_buy:
        lineas += [f"## BUY ({total_buy})", "", "> Attractive zone / Undervalued rating.", ""]
        idx = 1
        for emp, precio in usa_buy:
            lineas.append(seccion_usa(emp, precio, idx)); idx += 1
        for emp, precio, currency, yf_symbol in col_buy:
            lineas.append(seccion_col(emp, precio, currency, yf_symbol, idx)); idx += 1
    else:
        lineas += ["## BUY", "", "> No companies meet the criteria at this time.", ""]

    lineas += ["---", ""]

    if usa_watch or col_watch:
        lineas += [f"## WATCH ({total_watch})", "", "> Interesting zone / Neutral rating — monitor for better entry.", ""]
        idx = 1
        for emp, precio in usa_watch:
            lineas.append(seccion_usa(emp, precio, idx)); idx += 1
        for emp, precio, currency, yf_symbol in col_watch:
            lineas.append(seccion_col(emp, precio, currency, yf_symbol, idx)); idx += 1
    else:
        lineas += ["## WATCH", "", "> No companies in watch list.", ""]

    lineas += ["---", ""]

    if usa_no or col_no:
        lineas += [
            f"## NOT ATTRACTIVE ({total_no})",
            "",
            "| Market | Ticker | Current price | Zone / Rating | Implied base CAGR |",
            "|--------|--------|---------------|---------------|-------------------|",
        ]
        for emp, precio in usa_no:
            if precio is None:
                lineas.append(f"| 🇺🇸 USA | {emp['ticker']} | N/A | N/A | N/A |")
            else:
                zona   = zona_precio_usa(precio, emp)
                c_base = cagr_actual(precio, emp["base_price"], anos)
                lineas.append(f"| 🇺🇸 USA | {emp['ticker']} | ${precio:.2f} USD | {zona} | {c_base}% |")
        for emp, precio, currency, yf_symbol in col_no:
            precio_str = f"{precio:,.2f} {currency}" if precio is not None else "N/A"
            lineas.append(f"| 🇨🇴 COL | {emp['ticker']} | {precio_str} | {emp['rating']} | — |")

    return "\n".join(lineas)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    usa_path = ultimo_reporte(USA_PREFIX)
    col_path = ultimo_reporte(COL_PREFIX)
    print(f"USA report:      {usa_path.name}")
    print(f"Colombia report: {col_path.name}")

    fecha_usa, empresas_usa = parsear_reporte_usa(usa_path)
    fecha_col, empresas_col = parsear_reporte_colombia(col_path)
    print(f"\nUSA report date:      {fecha_usa}  |  Companies: {len(empresas_usa)}")
    print(f"Colombia report date: {fecha_col}  |  Companies: {len(empresas_col)}")

    # ── Fetch USA prices ──────────────────────────────────────────
    print("Fetching USA prices...", end=" ", flush=True)
    resultados_usa: list[tuple[dict, float | None]] = []
    for emp in empresas_usa:
        resultados_usa.append((emp, precio_actual(emp["ticker"])))
    print(f"done ({len(resultados_usa)} tickers)")

    # ── Fetch Colombia prices ─────────────────────────────────────
    print("Fetching Colombia prices...", end=" ", flush=True)
    resultados_col: list[tuple[dict, float | None, str, str]] = []
    for emp in empresas_col:
        precio, currency, yf_symbol = precio_colombia(emp["ticker"])
        resultados_col.append((emp, precio, currency, yf_symbol))
    print(f"done ({len(resultados_col)} tickers)")

    # ── Save report ───────────────────────────────────────────────
    print("Generating report...", end=" ", flush=True)
    markdown = generar_reporte(resultados_usa, resultados_col, usa_path, col_path)
    output = REPORTS_DIR / f"validation_{datetime.now().strftime('%Y-%m-%d')}.md"
    output.write_text(markdown, encoding="utf-8")
    print(f"done → {output.resolve()}")


if __name__ == "__main__":
    main()
