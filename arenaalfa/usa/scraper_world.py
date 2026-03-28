from playwright.sync_api import sync_playwright
import argparse
import re
import sys
from datetime import datetime, date
from pathlib import Path

URL_LOGIN = "https://sso.teachable.com/secure/1229078/identity/login/password?force=true"

MESES_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


# ─────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────

def parsear_fecha(texto):
    """Convierte '15-Ene-2026' o '02-Oct-25' en un objeto date."""
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


def texto_de_pagina(page):
    """Extrae el texto del body, buscando también dentro de iframes."""
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


# ─────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────

def hacer_login(page, email, password):
    print("\n[1/3] Abriendo página de login...")
    page.goto(URL_LOGIN, wait_until="networkidle")

    page.wait_for_selector("input#email", timeout=15000)
    page.locator("input#email").fill(email)
    print(f"[2/3] Credenciales ingresadas: {email}")

    page.locator("input#password").fill(password)

    page.locator("input[data-testid='login-button']").click()

    page.wait_for_load_state("networkidle", timeout=30000)
    print(f"[3/3] Login exitoso. URL: {page.url}\n")


# ─────────────────────────────────────────
# EXTRACCIÓN DE DATOS DE UNA EMPRESA
# ─────────────────────────────────────────

def extraer_datos_empresa(context, url, nombre, fecha, debug_dir=None):
    pagina = context.new_page()
    datos = {
        "nombre": nombre,
        "fecha": str(fecha),
        "url": url,
        "escenario_negativo": None,
        "cagr_negativo": None,
        "escenario_base": None,
        "cagr_base": None,
        "escenario_optimista": None,
        "cagr_optimista": None,
        "value": None,
        "deep_value": None,
        "valoracion_historica": None,
        "momento": "desconocido",
        "score": 0,
    }

    try:
        try:
            pagina.goto(url, wait_until="domcontentloaded", timeout=40000)
        except Exception:
            pass
        pagina.wait_for_load_state("load", timeout=20000)
        pagina.wait_for_timeout(2000)

        # Scroll completo para que cargue todo el contenido dinámico
        pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        pagina.wait_for_timeout(1500)
        pagina.evaluate("window.scrollTo(0, 0)")
        pagina.wait_for_timeout(500)

        # Guardar HTML y captura de cada empresa siempre
        if debug_dir is not None:
            slug = re.sub(r"[^\w\-]", "_", nombre)[:40]
            try:
                (debug_dir / f"empresa_{slug}.html").write_text(
                    pagina.content(), encoding="utf-8"
                )
                pagina.screenshot(path=str(debug_dir / f"empresa_{slug}.png"))
            except Exception:
                pass

        texto = texto_de_pagina(pagina)

        if not texto.strip():
            print(f"    Sin contenido — captura guardada en debug_html/empresa_{slug}.png")
            return datos

        # Extraer precios de escenarios
        # Soporta: "Escenario negativo: 120 USD", "Escenario Base: $150", etc.
        patron_precio = (
            r"(?i)escenario\s+(negativo|base|optimist[ao])"
            r"\s*[:\-–]\s*\$?\s*([\d,\.]+)\s*(USD|usd)?"
        )
        for m in re.finditer(patron_precio, texto):
            tipo = m.group(1).lower()
            precio = float(m.group(2).replace(",", ""))
            if "negativo" in tipo:
                datos["escenario_negativo"] = precio
            elif "base" in tipo:
                datos["escenario_base"] = precio
            elif "optimist" in tipo:
                datos["escenario_optimista"] = precio

        # Extraer valores CAGR en orden de aparición (negativo, base, optimista)
        cagrs = re.findall(r"CAGR\s*[:\s]\s*([\d\.]+)\s*%", texto, re.IGNORECASE)
        if len(cagrs) >= 1:
            datos["cagr_negativo"] = float(cagrs[0])
        if len(cagrs) >= 2:
            datos["cagr_base"] = float(cagrs[1])
        if len(cagrs) >= 3:
            datos["cagr_optimista"] = float(cagrs[2])

        # Extraer rangos de precio: VALUE, DEEP VALUE, VALORACION HISTORICA
        # Formato: "VALUE: 100 - 106 USD" o "DEEP VALUE: 75 - 85 USD"
        patron_zona = (
            r"(?i)(deep\s+value|value|valoraci[oó]n\s+hist[oó]rica)"
            r"\s*[:\-–]\s*([\d,\.]+)\s*[-–]\s*([\d,\.]+)\s*(USD|usd)?"
        )
        for m in re.finditer(patron_zona, texto):
            zona = m.group(1).lower().strip()
            rango = f"{m.group(2)} - {m.group(3)} USD"
            if "deep" in zona:
                datos["deep_value"] = rango
            elif "valor" in zona:
                datos["valoracion_historica"] = rango
            else:
                datos["value"] = rango

        # Detectar momento de inversión
        t = texto.lower()
        if "deep value" in t:
            datos["momento"] = "DEEP VALUE"
        elif "value" in t:
            datos["momento"] = "VALUE"
        elif "neutral" in t or "fair value" in t:
            datos["momento"] = "NEUTRAL"
        elif "cara" in t or "expensive" in t or "sobrevalorad" in t:
            datos["momento"] = "CARA"

        # Score combinado: CAGR base (40%) + CAGR optimista (30%) + momento (30%)
        score = 0.0
        if datos["cagr_base"]:
            score += datos["cagr_base"] * 0.40
        if datos["cagr_optimista"]:
            score += datos["cagr_optimista"] * 0.30

        momento_pts = {
            "DEEP VALUE": 10.0,
            "VALUE": 7.0,
            "NEUTRAL": 4.0,
            "CARA": 1.0,
            "desconocido": 3.0,
        }
        score += momento_pts.get(datos["momento"], 3.0) * 0.30
        datos["score"] = round(score, 2)

        print(
            f"    CAGR base: {datos['cagr_base']}% | "
            f"CAGR opt: {datos['cagr_optimista']}% | "
            f"Momento: {datos['momento']} | Score: {datos['score']}"
        )

    except Exception as e:
        print(f"    ERROR en {nombre}: {e}")
    finally:
        pagina.close()

    return datos


# ─────────────────────────────────────────
# GENERAR MARKDOWN
# ─────────────────────────────────────────

def generar_markdown(top_empresas, todas, fecha_corte):
    hoy = datetime.now().strftime("%d-%m-%Y")

    def fila(emp):
        return (
            f"| {emp['nombre']} | {emp['fecha']} "
            f"| {emp['cagr_base']}% | {emp['cagr_optimista']}% "
            f"| {emp['momento']} | {emp['score']} |"
        )

    def seccion(i, emp):
        neg = (
            f"  - Negativo:   ${emp['escenario_negativo']} USD  — CAGR {emp['cagr_negativo']}%"
            if emp["escenario_negativo"]
            else "  - Negativo:   no disponible"
        )
        base = (
            f"  - Base:        ${emp['escenario_base']} USD  — CAGR {emp['cagr_base']}%"
            if emp["escenario_base"]
            else "  - Base:        no disponible"
        )
        opt = (
            f"  - Optimista:  ${emp['escenario_optimista']} USD  — CAGR {emp['cagr_optimista']}%"
            if emp["escenario_optimista"]
            else "  - Optimista:  no disponible"
        )
        val    = f"  - Value:               {emp['value']}"          if emp["value"]               else "  - Value:               no disponible"
        dval   = f"  - Deep Value:          {emp['deep_value']}"       if emp["deep_value"]          else "  - Deep Value:          no disponible"
        vhist  = f"  - Valoración histórica: {emp['valoracion_historica']}" if emp["valoracion_historica"] else "  - Valoración histórica: no disponible"

        return "\n".join(
            [
                f"### {i}. {emp['nombre']}",
                f"- **Ticker en bolsa:** `{emp['nombre']}`",
                f"- **Fecha del estudio:** {emp['fecha']}",
                f"- **Momento de inversión:** `{emp['momento']}`",
                f"- **Score combinado:** {emp['score']}",
                "- **Zonas de precio:**",
                val,
                dval,
                vhist,
                "- **Proyecciones:**",
                neg,
                base,
                opt,
                f"- **Link:** {emp['url']}",
                "",
            ]
        )

    lineas = [
        "# Resumen — Mejores Oportunidades de Inversión",
        "",
        f"**Generado:** {hoy}  ",
        f"**Período analizado:** estudios desde {fecha_corte.strftime('%B %Y')}  ",
        f"**Total empresas analizadas:** {len(todas)}  ",
        "**Criterio de ranking:** CAGR base ×0.4 + CAGR optimista ×0.3 + Momento de inversión ×0.3",
        "",
        "---",
        "",
        f"## Top {len(top_empresas)} Mejores Oportunidades",
        "",
    ]

    for i, emp in enumerate(top_empresas, 1):
        lineas.append(seccion(i, emp))

    lineas += [
        "---",
        "",
        "## Tabla Completa",
        "",
        "| Ticker | Fecha | CAGR Base | CAGR Opt. | Momento | Score |",
        "|--------|-------|-----------|-----------|---------|-------|",
    ]
    for emp in sorted(todas, key=lambda x: x["score"], reverse=True):
        lineas.append(fila(emp))

    return "\n".join(lineas)


# ─────────────────────────────────────────
# PASOS DEL SCRAPER
# ─────────────────────────────────────────

def guardar_debug(page, debug_dir, nombre):
    """Guarda el HTML y captura de la página actual en debug_html/<nombre>.*"""
    try:
        (debug_dir / f"{nombre}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(debug_dir / f"{nombre}.png"))
        print(f"  [debug] {nombre}.html/.png guardados")
    except Exception as e:
        print(f"  [debug] No se pudo guardar {nombre}: {e}")


def step_login(page, debug_dir):
    """Paso 1: Pide credenciales, hace login con email/password y guarda debug."""
    email = input(">>> Ingresa tu correo electrónico y presiona ENTER: ").strip()
    password = input(">>> Ingresa tu contraseña y presiona ENTER: ").strip()
    hacer_login(page, email, password)
    print(f"  [debug] URL tras login: {page.url}")
    guardar_debug(page, debug_dir, "01_after_login")


def step_ir_a_curriculum(page, debug_dir):
    """Paso 2: Navega al curriculum del curso donde está LISTADO DE ESTUDIOS."""
    COURSE_URL = "https://arenaalfa.teachable.com/courses/enrolled/1762706"
    print(f"Navegando al curriculum: {COURSE_URL}")
    try:
        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=40000)
    except Exception:
        pass
    page.wait_for_load_state("load", timeout=20000)
    page.wait_for_timeout(2000)
    print(f"  [debug] URL curriculum: {page.url}")
    guardar_debug(page, debug_dir, "02_curriculum")


def step_abrir_listado(page, debug_dir):
    """Paso 3: Hace click en el botón Start de la fila LISTADO DE ESTUDIOS
    (li[data-lecture-id='46603807']) y espera a que cargue la página del listado."""
    print("Haciendo click en Start — LISTADO DE ESTUDIOS...")

    # Usamos evaluate() para hacer click via JS, evitando comprobaciones de
    # visibilidad de Playwright (el elemento puede estar fuera del viewport).
    clicked = page.evaluate(
        """
        () => {
            const a = document.querySelector("li[data-lecture-id='46603807'] a");
            if (!a) return false;
            a.click();
            return true;
        }
        """
    )

    if not clicked:
        guardar_debug(page, debug_dir, "03_error_click_listado")
        print("ERROR: No se encontró li[data-lecture-id='46603807']. "
              "Captura guardada en debug_html/03_error_click_listado.*")
        sys.exit(1)

    page.wait_for_load_state("load", timeout=30000)
    page.wait_for_timeout(2000)
    print(f"  [debug] URL tras click LISTADO: {page.url}")
    guardar_debug(page, debug_dir, "03_listado_estudios")


def step_extraer_links(page, debug_dir, fecha_corte, meses):
    """Paso 4: Extrae los links y tickers desde .lecture-text-container.
    Devuelve lista de dicts {nombre, fecha, url}."""
    print("Extrayendo links de empresas desde .lecture-text-container...")

    def evaluar_en_frame(frame):
        try:
            return frame.evaluate(
                """
                () => {
                    const container = document.querySelector('.lecture-text-container');
                    if (!container) return null;
                    const paras = Array.from(container.querySelectorAll('p'));
                    const results = [];
                    for (const p of paras) {
                        const a = p.querySelector('a[href]');
                        if (!a || !/caso de estudio/i.test(a.textContent)) continue;
                        const anchorText = a.textContent.replace(/\\s+/g, ' ').trim();
                        const fullText = p.textContent.replace(/\\s+/g, ' ').trim();
                        const ticker = fullText
                            .replace(anchorText, '')
                            .replace(/^[\\s:–\\-]+/, '')
                            .trim();
                        results.push({ texto: anchorText, ticker: ticker, href: a.href });
                    }
                    return results;
                }
                """
            )
        except Exception:
            return None

    links_raw = None
    for frame in [page.main_frame] + page.frames:
        resultado = evaluar_en_frame(frame)
        if resultado is not None and len(resultado) > 0:
            links_raw = resultado
            print(f"  lecture-text-container encontrado en frame: {frame.url[:60]}")
            guardar_debug(page, debug_dir, "04_frame_links")
            break

    if not links_raw:
        guardar_debug(page, debug_dir, "04_error_no_links")
        print("ERROR: No se encontró .lecture-text-container con links. "
              "Captura guardada en debug_html/04_error_no_links.*")
        sys.exit(1)

    print(f"Total estudios encontrados: {len(links_raw)}")
    print("  [debug] Primeros 3 links extraídos:")
    for item in links_raw[:3]:
        print(f"    texto={item['texto']!r}  ticker={item['ticker']!r}  "
              f"href=...{item['href'][-40:]}")

    empresas = []
    for link in links_raw:
        texto = link["texto"]
        ticker = link["ticker"].strip()
        match = re.search(r"(\d{1,2}[-/]\w{3,}[-/]\d{2,4})", texto)
        if not match:
            continue
        fecha = parsear_fecha(match.group(1))
        if not fecha:
            continue
        if fecha < fecha_corte:
            break
        empresas.append({"nombre": ticker or texto, "fecha": fecha, "url": link["href"]})

    print(f"Estudios en los últimos {meses} meses: {len(empresas)}\n")

    if not empresas:
        guardar_debug(page, debug_dir, "04_error_sin_empresas")
        print("No se encontraron empresas en el período solicitado.")
        sys.exit(1)

    return empresas


def step_analizar_empresas(context, empresas, debug_dir):
    """Paso 5: Visita cada empresa y extrae sus datos financieros."""
    resultados = []
    for i, emp in enumerate(empresas, 1):
        print(f"  [{i}/{len(empresas)}] {emp['nombre']} ({emp['fecha']})")
        datos = extraer_datos_empresa(
            context, emp["url"], emp["nombre"], emp["fecha"], debug_dir
        )
        resultados.append(datos)
    return resultados


def step_guardar_reporte(resultados, top_n, fecha_corte):
    """Paso 6: Rankea, imprime el top N y guarda el Markdown."""
    resultados.sort(key=lambda x: x["score"], reverse=True)
    top_n = min(top_n, len(resultados))
    top_empresas = resultados[:top_n]

    print("\n" + "=" * 40)
    print(f"TOP {top_n} EMPRESAS:")
    for i, emp in enumerate(top_empresas, 1):
        print(f"  {i}. {emp['nombre']:8} Score: {emp['score']}  Momento: {emp['momento']}")
    print("=" * 40)

    markdown = generar_markdown(top_empresas, resultados, fecha_corte)
    output = Path(f"resumen_inversiones_{datetime.now().strftime('%Y-%m-%d')}.md")
    output.write_text(markdown, encoding="utf-8")
    print(f"\nArchivo guardado: {output.resolve()}")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scraper de estudios de inversión Arena Alfa")
    parser.add_argument("--top", type=int, default=5,
                        help="Cantidad de empresas en el ranking (default: 5)")
    parser.add_argument("--meses", type=int, default=24,
                        help="Meses hacia atrás a revisar (default: 24)")
    args = parser.parse_args()

    if args.top < 1:
        print("ERROR: --top debe ser un número mayor a 0.")
        sys.exit(1)
    if args.meses < 1:
        print("ERROR: --meses debe ser un número mayor a 0.")
        sys.exit(1)

    hoy = date.today()
    mes_corte = hoy.month - (args.meses % 12)
    anio_corte = hoy.year - (args.meses // 12)
    if mes_corte <= 0:
        mes_corte += 12
        anio_corte -= 1
    fecha_corte = date(anio_corte, mes_corte, hoy.day)

    debug_dir = Path("debug_html")
    debug_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
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

        step_login(page, debug_dir)                                          # 1
        step_ir_a_curriculum(page, debug_dir)                                # 2
        step_abrir_listado(page, debug_dir)                                  # 3
        empresas = step_extraer_links(page, debug_dir, fecha_corte, args.meses)  # 4
        resultados = step_analizar_empresas(context, empresas, debug_dir)    # 5
        step_guardar_reporte(resultados, args.top, fecha_corte)              # 6

        input("\nPresiona ENTER para cerrar el navegador...")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
