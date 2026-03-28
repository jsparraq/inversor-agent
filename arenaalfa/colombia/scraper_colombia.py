from playwright.sync_api import sync_playwright
import argparse
import re
import sys
from datetime import datetime, date
from pathlib import Path

URL_BASE        = "https://www.arenaalfa.com/"
URL_VALORACION  = "https://www.arenaalfa.com/valoracion"
SESSION_FILE    = Path(__file__).parent / "session.json"

MESES_ES = {
    "ene": 1, "jan": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4, "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8, "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12, "dec": 12,
}


# ─────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────

def parse_date(texto):
    """Converts '15-Ene-2026' or '02-Oct-25' into a date object."""
    texto = texto.strip().lower()
    partes = re.split(r"[-/\s]", texto)
    if len(partes) != 3:
        return None
    try:
        dia = int(partes[0])
        mes = MESES_ES.get(partes[1][:3])
        if not mes:
            return None
        anio = int(partes[2])
        if anio < 100:
            anio += 2000
        return date(anio, mes, dia)
    except Exception:
        return None


def page_text(page):
    """Extracts visible text from the page body, also searching inside iframes."""
    texto = ""
    try:
        texto = page.inner_text("body")
    except Exception:
        pass

    if "escenario" not in texto.lower() and "cagr" not in texto.lower():
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            try:
                frame_texto = frame.inner_text("body")
                if "escenario" in frame_texto.lower() or "cagr" in frame_texto.lower():
                    return frame_texto
            except Exception:
                continue
    return texto


def save_debug(page, debug_dir, nombre):
    """Saves the HTML and screenshot of the current page to debug_html/<nombre>.*"""
    try:
        (debug_dir / f"{nombre}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(debug_dir / f"{nombre}.png"))
        print(f"  [debug] {nombre}.html/.png guardados")
    except Exception as e:
        print(f"  [debug] No se pudo guardar {nombre}: {e}")


# ─────────────────────────────────────────
# SESSION MANAGEMENT
# ─────────────────────────────────────────

def is_logged_in(page):
    """Navigates to home and returns True if the session is still active."""
    try:
        page.goto(URL_BASE, wait_until="networkidle", timeout=20000)
        return not page.locator("#link-login").is_visible(timeout=3000)
    except Exception:
        return False


# ─────────────────────────────────────────
# STEP FUNCTIONS
# ─────────────────────────────────────────

def step_login(page, context, debug_dir):
    """Step 1: Reuse saved session or do a fresh login."""
    storage = str(SESSION_FILE) if SESSION_FILE.exists() else None

    if storage and is_logged_in(page):
        print("[auth] Session reused from file — no login needed.\n")
        save_debug(page, debug_dir, "01_after_login")
        return

    if storage:
        print("[auth] Saved session expired — logging in again...")
        SESSION_FILE.unlink(missing_ok=True)

    print("\n[1/5] Opening Arena Alfa homepage...")
    page.goto(URL_BASE, wait_until="networkidle")

    # Close legal popup if it appears
    try:
        page.wait_for_selector("#legal-overlay .close", timeout=5000)
        page.locator("#legal-overlay .close").click()
        print("[2/5] Legal popup closed.")
    except Exception:
        print("[2/5] No legal popup.")

    print("[3/5] Clicking 'Inicio de Sesión'...")
    page.locator("#link-login").click()

    page.wait_for_selector("#modlgn-username", timeout=15000)
    print("[4/5] Login popup visible. Entering credentials...")

    username = input(">>> Enter your username and press ENTER: ").strip()
    password = input(">>> Enter your password and press ENTER: ").strip()

    page.locator("#modlgn-username").fill(username)
    page.locator("#modlgn-passwd").fill(password)
    page.locator("input[type='submit'][value='OK']").click()
    page.wait_for_load_state("networkidle", timeout=20000)

    # Detect "account in use" warning
    try:
        warning = page.locator("text=actualmente en uso").first
        if warning.is_visible(timeout=3000):
            screenshot_path = Path(__file__).parent / "error_session_en_uso.png"
            page.screenshot(path=str(screenshot_path))
            print(
                f"\n[ERROR] 'Cuenta en uso' detectada — captura guardada en:\n"
                f"  {screenshot_path}\n"
                f"  El servidor tiene una sesión anterior activa. Espera ~15-60 min\n"
                f"  y vuelve a intentarlo, o contacta a Arena Alfa."
            )
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        pass

    print(f"[5/5] Login complete. URL: {page.url}\n")
    context.storage_state(path=str(SESSION_FILE))
    print(f"[auth] Session saved to {SESSION_FILE}\n")
    save_debug(page, debug_dir, "01_after_login")


def step_go_to_listing(page, debug_dir):
    """Step 2: Navigate to the Estudios de Valoración listing page."""
    print(f"Navigating to Estudios de Valoración: {URL_VALORACION}")
    try:
        page.goto(URL_VALORACION, wait_until="domcontentloaded", timeout=40000)
    except Exception:
        pass
    page.wait_for_load_state("load", timeout=20000)
    page.wait_for_timeout(2000)
    print(f"  [debug] URL listing: {page.url}")
    save_debug(page, debug_dir, "02_listado_valoracion")


RATING_PTS = {
    "subvaloración": 10.0,
    "subvaloracion": 10.0,
    "neutral": 5.0,
    "sobrevaloración": 2.0,
    "sobrevaloracion": 2.0,
    "sobrevaloración extrema": 0.0,
    "sobrevaloracion extrema": 0.0,
}


def step_extract_companies(page, debug_dir, fecha_corte, meses):
    """Step 3: Extracts company data from the com-preciosobj listing.
    Returns list of dicts with full company data extracted from the listing page."""
    print("Extracting company data from listing...")

    # Scroll to trigger any lazy-loaded content
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)

    items_raw = page.evaluate(
        """
        () => {
            const items = document.querySelectorAll('div.com-preciosobj-item');
            return Array.from(items).map(item => {
                const a = item.querySelector('h4 a');
                const ratingEl = item.querySelector('h5.rating-info');
                const rightLis = Array.from(item.querySelectorAll('.item-right li'));
                const fechaLi = rightLis.find(li => li.textContent.includes('Fecha:'));
                const leftLis = Array.from(item.querySelectorAll('.item-left li'));
                return {
                    ticker:      a         ? a.textContent.trim()        : '',
                    url:         a         ? a.href                      : '',
                    rating:      ratingEl  ? ratingEl.textContent.trim() : '',
                    fecha:       fechaLi   ? fechaLi.textContent.replace(/Fecha:\\s*/i, '').trim() : '',
                    precios:     leftLis.map(li => li.textContent.trim()),
                };
            });
        }
        """
    )

    if not items_raw:
        save_debug(page, debug_dir, "03_error_no_items")
        print("ERROR: No company items found on the listing page.")
        sys.exit(1)

    print(f"Total companies on page: {len(items_raw)}")
    save_debug(page, debug_dir, "03_listado_links")

    empresas = []
    for item in items_raw:
        if not item["ticker"]:
            continue

        fecha = parse_date(item["fecha"])
        if not fecha or fecha < fecha_corte:
            continue

        # Parse price fields from the left-column list items
        precio_hipotesis = precio_cambio = precio_fundamental = None
        for li_text in item["precios"]:
            lower = li_text.lower()
            valor = li_text.split(":", 1)[-1].strip() if ":" in li_text else None
            if "hipótesis" in lower or "hipotesis" in lower:
                precio_hipotesis = valor
            elif "cambio de rating" in lower:
                precio_cambio = valor
            elif "fundamental" in lower:
                precio_fundamental = valor

        score = RATING_PTS.get(item["rating"].lower().strip(), 3.0)

        empresas.append({
            "nombre":              item["ticker"],
            "fecha":               fecha,
            "url":                 item["url"],
            "rating":              item["rating"],
            "precio_hipotesis":    precio_hipotesis,
            "precio_cambio_rating": precio_cambio,
            "precio_fundamental":  precio_fundamental,
            "score":               score,
        })

    empresas.sort(key=lambda x: (x["score"], x["fecha"]), reverse=True)
    print(f"Companies within the last {meses} months: {len(empresas)}\n")

    if not empresas:
        save_debug(page, debug_dir, "03_error_sin_empresas")
        print("No companies found in the requested period.")
        sys.exit(1)

    return empresas


def step_analyze_companies(context, empresas, debug_dir):
    """Step 4: All data was already extracted from the listing page in step 3."""
    for emp in empresas:
        print(
            f"  {emp['nombre']:20} Rating: {emp['rating']:28} "
            f"Fundamental: {emp['precio_fundamental'] or 'N/A'}"
        )
    return empresas


def step_save_report(resultados, top_n, fecha_corte):
    """Step 5: Ranks companies, prints top N, and writes the Markdown report."""
    resultados.sort(key=lambda x: x["score"], reverse=True)
    top_n = min(top_n, len(resultados))
    top_empresas = resultados[:top_n]

    print("\n" + "=" * 40)
    print(f"TOP {top_n} COMPANIES:")
    for i, emp in enumerate(top_empresas, 1):
        print(f"  {i}. {emp['nombre']:20} Score: {emp['score']}  Rating: {emp['rating']}")
    print("=" * 40)

    markdown = generate_markdown(top_empresas, resultados, fecha_corte)
    output = Path(f"./arenaalfa/reports/summary_invest_colombia_{datetime.now().strftime('%Y-%m-%d')}.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"\nArchivo guardado: {output.resolve()}")


def step_logout(page, context, debug_dir):
    """Step 6: Logs out by submitting the Joomla logout form via JS.
    The form's container (.moduletable_logout) is CSS-hidden until JS shows it,
    so we skip visibility checks and submit directly with page.evaluate()."""
    print("\nCerrando sesión...")
    try:
        page.goto(URL_BASE, wait_until="networkidle", timeout=20000)
        # Submit the form via JS — bypasses CSS display:none on the container
        submitted = page.evaluate(
            """
            () => {
                const form = document.querySelector('#login-form');
                if (!form) return false;
                form.submit();
                return true;
            }
            """
        )
        if submitted:
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            print(f"  Sesión cerrada. URL: {page.url}")
        else:
            print("  [WARN] #login-form not found — session may already be closed.")
        save_debug(page, debug_dir, "06_logout")
        # Refresh saved cookies after logout so session.json reflects the logged-out state
        context.storage_state(path=str(SESSION_FILE))
    except Exception as e:
        print(f"  [WARN] Could not close session automatically: {e}")


# ─────────────────────────────────────────
# GENERATE MARKDOWN REPORT
# ─────────────────────────────────────────

RATING_EN = {
    "subvaloración": "Undervalued",
    "subvaloracion": "Undervalued",
    "neutral": "Neutral",
    "sobrevaloración": "Overvalued",
    "sobrevaloracion": "Overvalued",
    "sobrevaloración extrema": "Extremely Overvalued",
    "sobrevaloracion extrema": "Extremely Overvalued",
}


def generate_markdown(top_empresas, todas, fecha_corte):
    hoy = datetime.now().strftime("%Y-%m-%d")

    def rating_en(emp):
        return RATING_EN.get(emp["rating"].lower().strip(), emp["rating"])

    def seccion(i, emp):
        hip    = f"  - Study Hypothesis Price: {emp['precio_hipotesis']}"    if emp["precio_hipotesis"]    else "  - Study Hypothesis Price: N/A"
        cambio = f"  - Rating Change Price:     {emp['precio_cambio_rating']}" if emp["precio_cambio_rating"] else "  - Rating Change Price:     N/A"
        fund   = f"  - Fundamental Price:       {emp['precio_fundamental']}"   if emp["precio_fundamental"]   else "  - Fundamental Price:       N/A"
        return "\n".join([
            f"### {i}. {emp['nombre']}",
            f"- **Ticker:** `{emp['nombre']}`",
            f"- **Last updated:** {emp['fecha']}",
            f"- **Rating:** `{rating_en(emp)}`",
            f"- **Score:** {emp['score']}",
            "- **Prices:**",
            hip,
            cambio,
            fund,
            f"- **Link:** {emp['url']}",
            "",
        ])

    def fila(emp):
        return (
            f"| {emp['nombre']} | {emp['fecha']} "
            f"| {rating_en(emp)} | {emp['precio_fundamental'] or 'N/A'} "
            f"| {emp['score']} |"
        )

    lineas = [
        "# Investment Opportunities Report — Colombia (BVC)",
        "",
        f"**Generated:** {hoy}  ",
        f"**Period analysed:** studies since {fecha_corte.strftime('%B %Y')}  ",
        f"**Total companies analysed:** {len(todas)}  ",
        "**Ranking criterion:** Undervalued=10 · Neutral=5 · Overvalued=2 · Extremely Overvalued=0",
        "",
        "---",
        "",
        f"## Top {len(top_empresas)} Best Opportunities",
        "",
    ]
    for i, emp in enumerate(top_empresas, 1):
        lineas.append(seccion(i, emp))

    lineas += [
        "---",
        "",
        "## Full Table",
        "",
        "| Ticker | Last Updated | Rating | Fundamental Price | Score |",
        "|--------|-------------|--------|-------------------|-------|",
    ]
    for emp in sorted(todas, key=lambda x: x["score"], reverse=True):
        lineas.append(fila(emp))

    return "\n".join(lineas)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Arena Alfa investment studies scraper (Colombia)")
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Number of companies in the ranking (default: 5)",
    )
    parser.add_argument(
        "--meses",
        type=int,
        default=24,
        help="Months back to review (default: 24)",
    )
    args = parser.parse_args()

    if args.top < 1:
        print("ERROR: --top must be a number greater than 0.")
        sys.exit(1)
    if args.meses < 1:
        print("ERROR: --meses must be a number greater than 0.")
        sys.exit(1)

    hoy = date.today()
    mes_corte  = hoy.month - (args.meses % 12)
    anio_corte = hoy.year  - (args.meses // 12)
    if mes_corte <= 0:
        mes_corte  += 12
        anio_corte -= 1
    fecha_corte = date(anio_corte, mes_corte, hoy.day)

    debug_dir = Path("debug_html")
    debug_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )

        storage = str(SESSION_FILE) if SESSION_FILE.exists() else None
        context = browser.new_context(
            storage_state=storage,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()

        try:
            step_login(page, context, debug_dir)                                          # 1
            step_go_to_listing(page, debug_dir)                                            # 2
            empresas   = step_extract_companies(page, debug_dir, fecha_corte, args.meses)    # 3
            resultados = step_analyze_companies(context, empresas, debug_dir)             # 4
            step_save_report(resultados, args.top, fecha_corte)                       # 5
        except Exception as e:
            print(f"\n[ERROR] Script failed: {e}")
        finally:
            step_logout(page, context, debug_dir)                                  # 6 — always runs
            input("\nPresiona ENTER para cerrar el navegador...")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
