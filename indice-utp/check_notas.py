"""
Revisa el Índice Académico en Matrícula UTP y avisa por Telegram si cambió.

Requisitos (una sola vez):
    pip install playwright requests
    playwright install chromium

Uso:
    python check_notas.py

Este script está pensado para ejecutarse UNA VEZ por corrida.
La repetición periódica (cada X minutos/horas) se hace con el
Programador de Tareas de Windows, cron (Mac/Linux) o launchd (Mac).
Al final de este archivo hay instrucciones para eso.
"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

CONFIG_PATH = Path(__file__).parent / "config.json"
STATE_PATH = Path(__file__).parent / "state.json"

LOGIN_URL_DEFAULT = "https://matricula.utp.ac.pa/mprematr/menu/inicio/2026/OnhReSgXXkhQmbcaXlQghWhR$Ocd"


def cargar_config():
    """
    Carga la configuración desde config.json (uso local) y/o desde
    variables de entorno (uso en GitHub Actions con Secrets). Las
    variables de entorno tienen prioridad si están presentes.
    """
    config = {}
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    env_map = {
        "cedula": "UTP_CEDULA",
        "password": "UTP_PASSWORD",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id": "TELEGRAM_CHAT_ID",
        "login_url": "UTP_LOGIN_URL",
        "indice_selector": "UTP_INDICE_SELECTOR",
    }
    for clave, nombre_env in env_map.items():
        valor = os.environ.get(nombre_env)
        if valor:
            config[clave] = valor

    config.setdefault("login_url", LOGIN_URL_DEFAULT)
    config.setdefault("headless", True)

    faltantes = [
        campo for campo in ("cedula", "password", "telegram_bot_token", "telegram_chat_id")
        if not config.get(campo)
    ]
    if faltantes:
        print(f"Faltan datos de configuración: {', '.join(faltantes)}")
        print("Complétalos en config.json (uso local) o como Secrets de GitHub Actions.")
        sys.exit(1)

    return config


def cargar_estado():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"ultimo_indice": None}


def guardar_estado(estado):
    STATE_PATH.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def enviar_telegram(token, chat_id, mensaje):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, data={"chat_id": chat_id, "text": mensaje})
    if resp.status_code != 200:
        print("Error enviando a Telegram:", resp.text)
    else:
        print("Notificación enviada por Telegram.")


def obtener_indice(config):
    """
    Inicia sesión en el portal y devuelve el texto del índice académico
    encontrado en la página de notas/índice.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.get("headless", True))
        page = browser.new_page()

        # 1. Ir a la página de login
        page.goto(config["login_url"], wait_until="networkidle")

        # 2. Llenar cédula y contraseña.
        #    Se usan selectores genéricos (esto es lo que ya funcionaba
        #    antes: encuentra el primer campo de texto y el campo de
        #    contraseña de la página).
        campo_cedula = page.locator("input[type='text']")
        campo_cedula.first.fill(config["cedula"])

        campo_password = page.locator("input[type='password']")
        campo_password.first.fill(config["password"])

        # 3. Enviar el formulario. Se prioriza el input[type='submit'] (esto
        #    es lo que ya funcionaba antes), y solo si no existe se intenta
        #    encontrar un botón por texto.
        boton = page.locator("input[type='submit']")
        if boton.count() == 0:
            boton = page.get_by_role("button", name=re.compile("iniciar|ingresar|entrar|acceder", re.I))
        if boton.count() == 0:
            boton = page.get_by_text(re.compile("iniciar sesi[oó]n|ingresar|entrar", re.I))
        boton.first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)  # margen extra por si el redireccionamiento tarda

        # Verificación: si seguimos en una página con campo de contraseña
        # visible, el login no funcionó (credenciales incorrectas o algo
        # cambió en la página).
        if page.locator("input[type='password']:visible").count() > 0:
            page.screenshot(path=str(Path(__file__).parent / "ultima_captura.png"), full_page=True)
            # Intenta capturar cualquier mensaje de error visible en la página
            texto_pagina = page.locator("body").inner_text()
            posible_error = re.search(
                r"(incorrect[ao]s?|inv[aá]lid[ao]s?|no coincide|credenciales|clave errada)[^\n]{0,80}",
                texto_pagina, re.I,
            )
            detalle = f" Mensaje visto en la página: '{posible_error.group(0)}'." if posible_error else ""
            browser.close()
            raise RuntimeError(
                "El login no parece haber funcionado (seguimos en la página "
                "de contraseña). Revisa 'ultima_captura.png' y verifica tu "
                f"cédula/contraseña en config.json.{detalle}"
            )

        # 4. Pantalla intermedia de "elige tu perfil" (Estudiante / etc.)
        #    No siempre aparece, así que si no se encuentra el texto,
        #    simplemente se sigue de largo.
        try:
            opcion_estudiante = page.get_by_text(re.compile("estudiante", re.I))
            if opcion_estudiante.count() > 0:
                opcion_estudiante.first.click()
                page.wait_for_load_state("networkidle")
        except Exception:
            pass

        # 5. El índice aparece directo en una tabla del menú principal
        #    (etiqueta "Indice" en una celda, valor en la celda de al lado),
        #    pero esa tabla se carga por AJAX (se ve un spinner girando
        #    unos segundos), así que esperamos a que el texto "Indice"
        #    aparezca antes de intentar leerlo.
        try:
            page.wait_for_selector("text=Indice", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(1000)  # pequeño margen extra tras aparecer

        def buscar_por_etiqueta(pagina, patron_etiqueta):
            celdas = pagina.locator("td, th")
            total = celdas.count()
            for i in range(total):
                texto = celdas.nth(i).inner_text().strip()
                if patron_etiqueta.match(texto):
                    if i + 1 < total:
                        valor = celdas.nth(i + 1).inner_text().strip()
                        if valor:
                            return valor
            return None

        texto_indice = None
        selector = config.get("indice_selector")
        if selector:
            try:
                texto_indice = page.locator(selector).first.inner_text().strip()
            except Exception:
                texto_indice = None

        if not texto_indice:
            texto_indice = buscar_por_etiqueta(page, re.compile(r"^[IÍ]ndice$", re.I))

        # 6. Respaldo: si no se encontró en el menú principal, se intenta
        #    entrar a "Historial de Índice" y tomar la ÚLTIMA fila de esa
        #    tabla (el semestre más reciente). El enlace vive en un menú
        #    desplegable oculto, así que en vez de clic se navega directo
        #    por su href (dentro de la misma sesión ya iniciada).
        if not texto_indice:
            enlace_historial = page.locator("#mhind")
            if enlace_historial.count() == 0:
                enlace_historial = page.get_by_text(re.compile("historial.*ndice", re.I))
            if enlace_historial.count() == 0:
                enlace_historial = page.get_by_text(re.compile("ndice", re.I))

            if enlace_historial.count() > 0:
                href = enlace_historial.first.get_attribute("href")
                if href:
                    from urllib.parse import urljoin
                    page.goto(urljoin(page.url, href), wait_until="networkidle")
                else:
                    enlace_historial.first.click(force=True)
                    page.wait_for_load_state("networkidle")

                filas = page.locator("table tr")
                total_filas = filas.count()
                for i in range(total_filas - 1, -1, -1):
                    texto_fila = filas.nth(i).inner_text()
                    match = re.search(r"\b([0-5]\.\d{1,2})\b", texto_fila)
                    if match:
                        texto_indice = match.group(1)
                        break

        if not texto_indice:
            # Último respaldo: buscar el patrón "Índice: 3.86" en el texto
            # visible de la página completa.
            texto_pagina = page.locator("body").inner_text()
            match = re.search(r"[IÍ]ndice[^0-9]{0,15}([0-9]+[.,][0-9]+)", texto_pagina, re.I)
            if match:
                texto_indice = match.group(1)

        # Guarda una captura para depurar si algo falla
        page.screenshot(path=str(Path(__file__).parent / "ultima_captura.png"), full_page=True)

        browser.close()
        return texto_indice


def main():
    config = cargar_config()
    estado = cargar_estado()

    try:
        indice_actual = obtener_indice(config)
    except RuntimeError as e:
        print(str(e))
        enviar_telegram(config["telegram_bot_token"], config["telegram_chat_id"], f"⚠️ {e}")
        return

    if indice_actual is None:
        print("No se pudo encontrar el índice en la página. Revisa 'ultima_captura.png'.")
        enviar_telegram(
            config["telegram_bot_token"],
            config["telegram_chat_id"],
            "⚠️ No pude leer tu índice en el portal de la UTP. Revisa el script.",
        )
        return

    print("Índice encontrado:", indice_actual)

    if indice_actual != estado.get("ultimo_indice"):
        cambio = estado.get("ultimo_indice") is not None
        mensaje = (
            f"📊 Tu índice cambió: {indice_actual}"
            if cambio
            else f"📊 Índice actual: {indice_actual}"
        )
        enviar_telegram(config["telegram_bot_token"], config["telegram_chat_id"], mensaje)
        estado["ultimo_indice"] = indice_actual
        guardar_estado(estado)
    else:
        print("Sin cambios en el índice, no se envía notificación.")


if __name__ == "__main__":
    main()
