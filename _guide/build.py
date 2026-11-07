"""Genera laboratorio_riesgo_aprobacion_utec.html a partir de _guide/parts/*.html.

El código que ve el estudiante NO se reescribe a mano: se INYECTA desde los archivos reales del laboratorio, y las
salidas esperadas se inyectan desde _guide/outputs/ (las produce _guide/capture.py ejecutando los comandos de verdad).

Marcadores:
  {{FILE:ruta}}                    archivo completo (escapado para HTML)
  {{SNIP:ruta::inicio::fin}}       desde la 1ª línea que contiene 'inicio' hasta la 1ª posterior que contiene 'fin' (inclusive)
  {{SNIP:ruta::inicio::fin::+N}}   igual, e incluye N líneas MÁS después de 'fin'
  {{HEAD:ruta::N}}                 las primeras N líneas de un archivo
  {{LINES:ruta}}                   número de líneas del archivo
  {{OUT:nombre}}                   salida capturada de _guide/outputs/nombre.txt
  {{TRACE:ruta}}                   un .jsonl convertido a un arreglo JSON (para el reproductor de traza)
  {{PASSED}}                       cantidad de pruebas que pasan (leída de la salida capturada de la suite completa)
  {{N:nombre}}                     cantidad de pruebas que pasan en _guide/outputs/nombre.txt
  {{IMG:ruta}}                     imagen JPEG del laboratorio en base64 (capturas reales)
  __BG__ / __LOGO__                imágenes en base64

La compilación FALLA si:
  - queda un marcador sin resolver o un enlace interno roto;
  - un bloque de comandos de Windows (o "todos los sistemas") usa sintaxis de bash o de PowerShell 7 que no existe en
    Windows PowerShell 5.1 (&&, touch, export, source, "\\" de continuación, python3, pip suelto…);
  - un bloque de macOS/Linux usa sintaxis de PowerShell;
  - los bloques macOS y Windows no vienen en pares.
"""
import base64
import html
import json
import re
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
GUIDE = Path(__file__).resolve().parent
SALIDA = "laboratorio_riesgo_aprobacion_utec.html"


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def read(rel: str) -> str:
    p = LAB / rel
    if not p.exists():
        sys.exit(f"ERROR: no existe {rel}")
    return p.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")


def out(nombre: str) -> str:
    p = GUIDE / "outputs" / f"{nombre}.txt"
    if not p.exists():
        sys.exit(f"ERROR: falta la salida capturada {p.name}. Ejecuta: python _guide/capture.py")
    return p.read_text(encoding="utf-8").rstrip("\n")


def snip(rel: str, start: str, end: str, extra: str = "") -> str:
    lines = read(rel).split("\n")
    i = next((k for k, l in enumerate(lines) if start in l), None)
    if i is None:
        sys.exit(f"ERROR: inicio '{start}' no encontrado en {rel}")
    j = next((k for k in range(i, len(lines)) if end in lines[k]), None)
    if j is None:
        sys.exit(f"ERROR: fin '{end}' no encontrado en {rel} después de la línea {i + 1}")
    return "\n".join(lines[i : j + 1 + (int(extra[1:]) if extra else 0)])


def trace_json(rel: str) -> str:
    eventos = [json.loads(l) for l in read(rel).split("\n") if l.strip()]
    return json.dumps(eventos, ensure_ascii=False).replace("<", "\\u003c")      # seguro dentro de <script>


def passed(nombre: str = "t_todo") -> str:
    m = re.search(r"(\d+) passed", out(nombre))
    if not m:
        sys.exit("ERROR: no se pudo leer la cantidad de pruebas de outputs/t_todo.txt")
    return m.group(1)


# ------------------------------------------------------------------------------------------------ revisión de comandos
SOLO_BASH = [  # sintaxis que NO existe (o significa otra cosa) en Windows PowerShell 5.1
    (r"&&", "'&&' no existe en PowerShell 5.1"), (r"\|\|", "'||' no existe en PowerShell 5.1"),
    (r"(?m)^\s*touch\b", "'touch' no existe en PowerShell"), (r"(?m)^\s*export\b", "'export' no existe en PowerShell"),
    (r"\bsource\b", "'source' no existe en PowerShell"), (r"(?m)\s\\\s*$", "'\\' al final de línea no continúa la línea en PowerShell"),
    (r"\bpython3\b", "'python3' en Windows abre la Microsoft Store"), (r"(?m)^\s*pip\b", "usa 'python -m pip' (evita el pip equivocado)"),
    (r"(?m)^\s*(cp|ls|cat|grep|head|mv|rm)\b", "comando de bash (usa su equivalente de PowerShell)"),
    (r"mkdir -p", "'mkdir -p' no existe en PowerShell"), (r"\$\(", "'$(…)' es de bash"), (r"/bin/", "ruta de macOS/Linux"),
    (r"\bsudo\b", "'sudo' no existe en Windows"),
    (r"(?m)^\s*curl\s", "en PowerShell 5.1 'curl' es un alias de Invoke-WebRequest: usa curl.exe o Invoke-RestMethod"),
    (r"(?m)^\s*(nano|vim|open|lsof)\b", "comando de macOS/Linux"),
    (r"python -c", "evita 'python -c' en PowerShell: las comillas internas se rompen; usa un script"),
]
SOLO_POWERSHELL = [
    (r"\\Scripts\\", "ruta de Windows en un bloque de macOS/Linux"), (r"New-Item|Copy-Item|Get-ChildItem|Get-Content|Get-Location|Select-String", "cmdlet de PowerShell en un bloque de macOS/Linux"),
    (r"\$env:", "'$env:' es de PowerShell"),
    (r"curl\.exe|Invoke-RestMethod|notepad|Get-NetTCPConnection", "comando de Windows en un bloque de macOS/Linux"),
]


def revisar_comandos(pagina: str) -> None:
    errores = []
    todos = re.findall(r'<div class="(code[^"]*)"><div class="code-h">.*?</div><pre[^>]*><code([^>]*)>(.*?)</code></pre></div>', pagina, re.S)
    bloques = [(c, cuerpo) for c, atributos, cuerpo in todos if 'data-lang="sh"' in atributos]     # solo los bloques de comandos
    os_tags = []
    for clases, cuerpo in bloques:
        texto = html.unescape(cuerpo)
        tag = "win" if "os-win" in clases else "mac" if "os-mac" in clases else "todos"
        if tag != "todos":
            os_tags.append(tag)
        reglas = (SOLO_BASH if tag in ("win", "todos") else []) + (SOLO_POWERSHELL if tag in ("mac", "todos") else [])
        for rx, motivo in reglas:
            if re.search(rx, texto):
                errores.append(f"[{tag}] {motivo}:\n      {texto.strip().splitlines()[0][:100]}")
    if os_tags != ["mac", "win"] * (len(os_tags) // 2):
        errores.append(f"los bloques macOS/Windows deben ir en pares (mac, win, mac, win…); orden actual: {os_tags}")
    if errores:
        sys.exit("ERROR en los bloques de comandos:\n  - " + "\n  - ".join(errores))
    print(f"   comandos revisados: {len(bloques)} bloques ({os_tags.count('win')} de Windows) sin sintaxis ajena")


def revisar_enlaces(pagina: str) -> None:
    todos = re.findall(r'<section id="([^"]+)"', pagina)
    repetidos = sorted({i for i in todos if todos.count(i) > 1})
    if repetidos:
        sys.exit(f"ERROR: secciones con id repetido (rompe la navegación): {repetidos}")
    ids = set(todos)
    rotos = sorted({h for h in re.findall(r'href="#([^"]+)"', pagina) if h not in ids})
    if rotos:
        sys.exit(f"ERROR: enlaces internos rotos: {rotos}")


# ------------------------------------------------------------------------------------------------ construcción
page = "\n".join(p.read_text(encoding="utf-8") for p in sorted((GUIDE / "parts").glob("*.html")))
page = re.sub(r"\{\{FILE:([^}]+)\}\}", lambda m: html.escape(read(m.group(1)), quote=False), page)
page = re.sub(r"\{\{SNIP:([^}]+?)::(.+?)::(?!:)(.+?)(?:::(?!:)(\+\d+))?\}\}", lambda m: html.escape(snip(m.group(1), m.group(2), m.group(3), m.group(4) or ""), quote=False), page)
page = re.sub(r"\{\{HEAD:([^}:]+)::(\d+)\}\}", lambda m: html.escape("\n".join(read(m.group(1)).split("\n")[: int(m.group(2))]), quote=False), page)
page = re.sub(r"\{\{LINES:([^}]+)\}\}", lambda m: str(len(read(m.group(1)).split("\n"))), page)
page = re.sub(r"\{\{OUT:([^}]+)\}\}", lambda m: html.escape(out(m.group(1)), quote=False), page)
page = re.sub(r"\{\{TRACE:([^}]+)\}\}", lambda m: trace_json(m.group(1)), page)
page = page.replace("{{PASSED}}", passed())
page = re.sub(r"\{\{N:([^}]+)\}\}", lambda m: passed(m.group(1)), page)          # pruebas que pasan en un archivo

page = re.sub(r"\{\{IMG:([^}]+)\}\}", lambda m: data_uri(LAB / m.group(1), "image/jpeg"), page)
left = re.findall(r"\{\{[A-Z]+[:}][^}]*\}?\}?", page)
if left:
    sys.exit(f"ERROR: marcadores sin resolver: {left[:3]}")

revisar_comandos(page)
revisar_enlaces(page)

page = page.replace("__BG__", data_uri(GUIDE / "assets/bg.jpg", "image/jpeg"))
page = page.replace("__LOGO__", data_uri(GUIDE / "assets/logo_utec.png", "image/png"))

destino = LAB / SALIDA
destino.write_text(page, encoding="utf-8")
print(f"OK -> {destino.name}  {destino.stat().st_size / 1024:.0f} KB  ({len(list((GUIDE / 'parts').glob('*.html')))} partes)")
