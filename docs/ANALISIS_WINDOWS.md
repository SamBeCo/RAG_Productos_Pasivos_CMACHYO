# Análisis profundo · Validación de comandos en Windows

**Laboratorio 06 · 2026-10-11**

Cada afirmación lleva su nivel de evidencia:

- **[MEDIDO]**: se ejecutó y se observó el resultado. Fue en macOS, simulando la condición de Windows cuando aplica.
- **[ANALIZADO]**: lo revisa un programa (el analizador de `_guide/build.py` o una prueba de pytest) en cada compilación o ejecución.
- **[GENERAL]**: comportamiento documentado de Windows/PowerShell, no reproducido aquí.

**Límite principal: nada se ejecutó en un Windows real ni en PowerShell.** En la máquina de preparación no hay `pwsh`.
Con PowerShell 7 instalado se podría verificar la sintaxis de cada bloque (`[System.Management.Automation.Language.Parser]::ParseInput`),
pero eso no reemplaza ejecutar en Windows PowerShell 5.1.

---

## 1. Inventario de comandos de la guía

| Paso | Comando (macOS/Linux) | Windows PowerShell 5.1 | Riesgo en Windows | Evidencia |
|---|---|---|---|---|
| 2 | `mkdir lab-06…` + `mkdir -p …` | `New-Item -ItemType Directory -Force …` | `-p` no existe | [ANALIZADO] el analizador rechaza `mkdir -p` en bloques Windows |
| 2 | `touch app/__init__.py …` | `New-Item -ItemType File -Force app\__init__.py, …` | `touch` no existe; `-Force` vacía un archivo existente (inocuo: deben estar vacíos) | [ANALIZADO] / [GENERAL] |
| 2 | `python3 -m venv .venv` | `py -3 -m venv .venv` | `python3` puede abrir la Microsoft Store | [ANALIZADO] |
| 2 | `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1` | La política de ejecución puede bloquearlo → `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` | [GENERAL] |
| 2 | `python -m pip install -r requirements-dev.txt` | idéntico | `pip` suelto podría ser de otra instalación | [ANALIZADO] |
| 2 | `cp .env.example .env` · `nano .env` | `Copy-Item …` · `notepad .env` | El Bloc de notas puede guardar `.env.txt` con las extensiones ocultas | [GENERAL] |
| 3 | `python -m scripts.normalizar_env` | idéntico | Ver §2.1 | [MEDIDO] |
| 3–12 | `python -m pytest tests/test_x.py` | idéntico | Python acepta `/` en rutas de Windows | [ANALIZADO] (simulación de alumno) |
| 4 | `python -m rules.generar_pdf` | idéntico | Imprime "·" y tildes: caben en cp1252 | [MEDIDO] con `PYTHONIOENCODING=cp1252` |
| 11 | `python -m scripts.verificar_claves` | idéntico | Imprime mensajes de error de terceros | [MEDIDO] cp1252 sin claves |
| 11 | `python -m app.ingesta` | idéntico | — | [MEDIDO] cp1252 |
| 11 | `python -m eval.eval_router --proveedor …` | idéntico | **Caía con `UnicodeEncodeError` por "→" al redirigir** | [MEDIDO] (ver §2.2): corregido |
| 11 | `python -m app` | idéntico | Ctrl+C: `KeyboardInterrupt` capturado; sin driver async (no hay problema de Proactor) | [ANALIZADO] |
| 11 | `curl http://127.0.0.1:8000/health` | `curl.exe …` | `curl` = alias de `Invoke-WebRequest` en 5.1 | [ANALIZADO] |
| 12 | `docker compose up -d --build` / `ps` / `logs app` / `down` / `down -v` | idénticos | Docker Desktop abierto, motor WSL 2 | [GENERAL] |
| 12 | `python -m loadgen.generar_carga` | idéntico | JSON enviado desde Python (no desde PowerShell, ver §2.4) | [MEDIDO] cp1252 |
| 14 | `lsof -i :8000` | `Get-NetTCPConnection -LocalPort 8000 -State Listen \| Select-Object OwningProcess` | — | [GENERAL] |

El analizador de `build.py` revisó **29 bloques de comandos (5 de Windows)**. La compilación falla si un bloque de Windows contiene cualquiera de estos:

- `&&` o `||`
- `touch`, `export` o `source`
- `\` de continuación de línea
- `python3` o `pip` suelto
- `cp`, `ls`, `cat`, `grep`, `head`, `mv` o `rm`
- `mkdir -p` o `$(…)`
- `/bin/` o `sudo`
- `curl` sin `.exe`
- `nano`, `vim`, `open` o `lsof`
- `python -c`

También falla si un bloque de macOS contiene cmdlets de PowerShell, `$env:`, `\Scripts\`, `curl.exe` o `notepad`, o si los bloques no van en pares mac/win.

---

## 2. Experimentos

### 2.1 Codificación de `.env` y Docker Compose [MEDIDO]

Con Docker Compose v5.1.4 se generó el mismo `.env` en cinco formatos y se leyó con `docker compose config`:

| Formato | ¿Cómo aparece en Windows? | Resultado de Compose |
|---|---|---|
| UTF-8 sin BOM, LF | VS Code; Bloc de notas moderno | OK |
| UTF-8 **con BOM** | Bloc de notas antiguo; algunos editores | OK: el BOM no se pegó al primer nombre (probado también con una variable en la primera línea) |
| UTF-8 con **CRLF** | Cualquier editor de Windows | OK: Compose descarta el `\r` |
| **UTF-16 LE con BOM** | `echo X=1 > .env` en PowerShell 5.1 | **FALLA**: `unexpected character "�" in variable name` |
| Valor con espacios (`token con espacios`) | — | OK, sin comillas |

**Consecuencia:** `app/config.py` sí entiende UTF-16, así que las pruebas pasan, pero `docker compose up` falla en el paso 11. Se creó `scripts/normalizar_env.py`, que reescribe a UTF-8 sin BOM con LF. Está probado: dos casos y una mutación detectada. La guía lo ejecuta en los pasos 3 y 12.

### 2.2 Salida redirigida en cp1252 [MEDIDO]

En Windows, Python escribe en la consola en UTF-16 (API de consola). Pero cuando la salida se **redirige** (`> archivo.txt`, `| Select-String`, o cuando PowerShell la captura), usa la codificación ANSI del sistema: **cp1252** en Windows en español.

Se simuló con `PYTHONIOENCODING=cp1252 PYTHONUTF8=0`:

- `eval.eval_router` **cayó** con `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'` (el "→" de "Confusiones (esperado → obtenido)").
- `scripts/normalizar_env.py` también imprimía "→". No falló solo porque, en esa corrida, el `.env` no necesitaba cambios.
- Un análisis del árbol sintáctico (AST) de los cinco paquetes encontró **6 textos** con caracteres fuera de cp1252 ("→", "≠"). Todos se reemplazaron.
- Se agregó la prueba `test_los_textos_que_se_imprimen_caben_en_cp1252`, que repite ese análisis en cada ejecución de pytest.
- Las tildes, la "ñ", "·" y "…" sí existen en cp1252.

Después de la corrección, `generar_pdf`, `ingesta`, `eval_router`, `verificar_claves` y `loadgen` terminan sin error bajo cp1252.

**No cubierto:** los mensajes de error que vienen de terceros (por ejemplo, el texto de una excepción de OpenAI) podrían traer caracteres fuera de cp1252. Ahí el riesgo es una excepción al *mostrar* el error, no un resultado incorrecto.

### 2.3 Rutas con espacios y caracteres no ASCII [MEDIDO]

La simulación del alumno se ejecutó en la carpeta `alumno con espacios y tildes ñ/`:

- Siguió la guía compilada en orden.
- Creó cada archivo solo cuando la guía lo pide.
- Ejecutó los comandos de cada paso.

Todas las pruebas pasaron en cada paso. En macOS, solo fallaron los dos comandos que requieren claves reales, como se esperaba. Las rutas se arman con `pathlib` y nunca se concatenan con `"\\"`.

### 2.4 `Invoke-RestMethod` y cuerpos con tildes [GENERAL]

Windows PowerShell 5.1 codifica un `-Body` de tipo texto como ISO-8859-1 si el `-ContentType` no declara `charset`. Así, "Pérdida" llegaría como bytes inválidos en UTF-8 y FastAPI respondería 422. Por eso la guía **nunca** envía JSON desde PowerShell: usa el navegador o `loadgen` (Python, `httpx`). Si un alumno quiere usar PowerShell:

```powershell
$cuerpo = [System.Text.Encoding]::UTF8.GetBytes((Get-Content solicitud.json -Raw -Encoding UTF8))
Invoke-RestMethod http://localhost:8000/api/solicitudes -Method Post -ContentType "application/json; charset=utf-8" -Body $cuerpo
```

(No ejecutado.)

### 2.5 Bucle de eventos (lección del lab 04) [ANALIZADO]

El lab 04 fallaba en Windows porque psycopg asíncrono no funciona con `ProactorEventLoop`. Aquí no hay ningún driver asíncrono:

- SQLite se usa con `sqlite3`, que es síncrono.
- Jev se llama con `httpx.Client`, también síncrono.
- OpenAI se llama con el cliente síncrono del SDK.

Los endpoints son `def`, y FastAPI los ejecuta en un grupo de hilos. Por eso `python -m app` y `uvicorn` usan el bucle por defecto sin problema. Ningún `asyncio.run` toca la base.

### 2.6 Saltos de línea en archivos montados en Docker [ANALIZADO]

Con `core.autocrlf=true`, Git en Windows convierte a CRLF al hacer checkout. El formato YAML admite CRLF [GENERAL], pero un `#!/bin/sh` con CRLF falla dentro de Linux. `.gitattributes` fuerza `eol=lf` en `*.yml`, `*.json`, `*.py`, `*.sh` y `Dockerfile`, y la prueba `test_archivos_que_lee_docker_tienen_finales_LF` lo revisa. (No probado con un clon real en Windows.)

---

## 3. Riesgos residuales (lo que un alumno en Windows aún podría encontrar)

1. **Política de ejecución corporativa** (GPO) que bloquea incluso `-Scope Process`.
   - Solución: activar sin script, con `.\.venv\Scripts\python.exe -m …` en cada comando.
2. **Proxy corporativo** que bloquea `api.typesafe.ai` o `api.openai.com`.
   - `verificar_claves` lo muestra como `Jev [red]` o `APIConnectionError`.
   - Para que `httpx` y el SDK lo usen, se configuran `HTTPS_PROXY` y `NO_PROXY` en `.env`.
3. **Antivirus** que bloquea `.venv\Scripts\*.exe` o los puertos de Docker.
4. **Docker Desktop sin WSL 2** (Hyper-V antiguo) o sin virtualización en la BIOS.
5. **OneDrive**: carpeta del laboratorio dentro de "Documentos" sincronizado. Se recomienda `C:\labs`.
6. **Python de la Microsoft Store**: rutas largas y redirección de `%LOCALAPPDATA%`. Se recomienda el instalador de python.org.

## 4. Cómo completar la validación

1. **Sintaxis** (sin Windows): instalar PowerShell 7 y analizar cada bloque `os-win` del HTML compilado con `Parser::ParseInput`. Esto requiere permiso del responsable del curso para descargar PowerShell.
2. **Ejecución real**: un Windows 11 con Windows PowerShell 5.1, Python 3.10 o superior de python.org y Docker Desktop (WSL 2). Seguir la guía desde el paso 2 en `C:\labs`, con un `.env` creado por `echo` (para probar la conversión UTF-16) y redirigiendo `eval_router` a un archivo.
3. Registrar cada diferencia en este documento.
