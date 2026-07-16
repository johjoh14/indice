# Bot de aviso de índice - Matrícula UTP

Revisa tu índice académico en el portal de matrícula y te avisa por Telegram
cuando cambie (por ejemplo, cuando suben notas nuevas).

## 1. Instalar dependencias (una sola vez)

```bash
pip install playwright requests
playwright install chromium
```

## 2. Crear tu bot de Telegram (una sola vez, 2 minutos)

1. Abre Telegram y busca **@BotFather**.
2. Envíale `/newbot`, ponle un nombre y un usuario (debe terminar en "bot").
3. BotFather te dará un **token** parecido a `123456789:ABCdefGhIjKlmNoPQRstuVWxyZ`. Guárdalo.
4. Busca tu bot recién creado por su usuario y envíale cualquier mensaje (ej. "hola").
5. Abre en el navegador (reemplazando TU_TOKEN):
   `https://api.telegram.org/botTU_TOKEN/getUpdates`
6. Busca en la respuesta el campo `"chat":{"id": ...}` — ese número es tu **chat_id**.

## 3. Configurar el script

Copia `config.example.json` a `config.json` y llena:

- `cedula` y `password`: tus credenciales del portal (quedan solo en tu computadora).
- `telegram_bot_token` y `telegram_chat_id`: los que obtuviste en el paso 2.
- `indice_selector` (opcional pero recomendado): si sabes CSS, click derecho
  sobre el número del índice → "Inspeccionar" → click derecho en el HTML
  resaltado → "Copy" → "Copy selector". Pégalo aquí. Si lo dejas vacío, el
  script intentará adivinar buscando un patrón como "Índice: 3.86" en la página.

**Importante:** el script ya NO usa una URL fija para el índice, porque esas
URLs incluyen un token de sesión que expira apenas cierras tu sesión. En su
lugar, el script hace clic dentro de la misma sesión: inicia sesión → si
aparece la pantalla de elegir perfil, hace clic en "Estudiante" → hace clic
en el enlace de "Historial de Índice" → y toma el valor de la **última fila**
de la tabla (el semestre más reciente, según nos confirmaste). Si el enlace
del menú no se llama exactamente "Historial de Índice" o si la extracción
falla, revisa `ultima_captura.png` y avísame para ajustar el texto del
enlace o el selector.

## 4. Probar que funciona

```bash
python check_notas.py
```

Si algo falla, revisa el archivo `ultima_captura.png` que se genera junto al
script — es una foto de cómo quedó la página, útil para ver si el login
funcionó o si el selector está mal.

## 5. Programarlo para que corra solo cada cierto tiempo

### Windows (Programador de tareas)
1. Abre "Programador de tareas" → "Crear tarea básica".
2. Desencadenador: repetir cada, por ejemplo, 30 minutos.
3. Acción: iniciar un programa →
   Programa: ruta a tu `python.exe`
   Argumentos: `check_notas.py`
   Iniciar en: la carpeta donde está el script.

### Mac / Linux (cron)
```bash
crontab -e
```
Agrega (revisa cada 30 min):
```
*/30 * * * * cd /ruta/a/utp_bot && /usr/bin/python3 check_notas.py >> log.txt 2>&1
```

## 6. Alternativa gratis: correrlo en GitHub Actions (sin depender de tu PC)

Con esto el script corre solo, en los servidores de GitHub, cada 15 minutos,
sin que tu computadora esté prendida. Es gratis usando un repositorio
**público** (con privado, GitHub solo da 2,000 minutos gratis al mes y cada
15 min los consumirías todos antes de fin de mes).

**Importante:** con repo público, tu cédula y contraseña quedan protegidas
(como "Secrets" cifrados, nadie las puede ver), pero el número de tu índice
sí podría aparecer en los "logs" de cada ejecución, que son públicos.

### Pasos

1. Crea una cuenta en [github.com](https://github.com) si no tienes.
2. Crea un repositorio nuevo, **público**, por ejemplo llamado `indice-utp`.
3. Sube todos los archivos de esta carpeta a ese repositorio (arrástralos en
   la página de GitHub con "Add file" → "Upload files", o usa `git`).
   **NO subas tu `config.json`** (ya está en `.gitignore` para evitarlo).
4. En el repositorio, ve a **Settings → Secrets and variables → Actions →
   New repository secret** y crea estos 4 secrets, uno por uno:
   - `UTP_CEDULA` → tu cédula (ej. `8-975-418`)
   - `UTP_PASSWORD` → tu contraseña del portal
   - `TELEGRAM_BOT_TOKEN` → el token de tu bot
   - `TELEGRAM_CHAT_ID` → tu chat id
5. Ve a la pestaña **Actions** del repositorio y actívalas si te lo pide.
6. Ya debería empezar a correr solo cada 15 minutos. Para probarlo ahora
   mismo sin esperar: pestaña **Actions** → selecciona el workflow
   "Revisar Indice UTP" → botón **"Run workflow"**.
7. Si algo falla, entra a esa ejecución en la pestaña Actions y revisa el
   log, o descarga el archivo `ultima_captura` que se sube como "artifact".

### Nota importante (para no olvidar)

GitHub **desactiva automáticamente** los workflows programados (cron) de un
repositorio si pasan **60 días sin actividad** en el repo. Si ves que dejó de
avisarte, entra a la pestaña Actions y reactívalo con un clic, o haz
cualquier pequeño cambio/commit en el repo de vez en cuando.

## Notas importantes

- Tu cédula y contraseña quedan solo en tu archivo `config.json`, en tu
  computadora — nunca se envían a Anthropic ni a nadie más que al propio
  portal de la UTP.
- No compartas `config.json` con nadie.
- Si el portal cambia su diseño, es posible que el selector deje de funcionar
  y haya que ajustarlo.
