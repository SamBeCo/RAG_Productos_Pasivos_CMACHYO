"""Simula a un alumno: lee la guía COMPILADA, crea cada archivo solo cuando la guía lo pide y ejecuta los comandos de
cada paso en orden (bloques macOS / "todos los sistemas"), en una carpeta vacía.

Uso:   python _guide/simular_alumno.py "<carpeta destino vacía>"

Omite lo que no se puede automatizar aquí: crear el venv, pip install, editores, docker, curl y levantar la API.
Corre en modo sin claves; los dos comandos que exigen claves reales (eval_router con jev/embeddings) se esperan como MAL.
"""
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

GUIA = Path(__file__).resolve().parent.parent / "laboratorio_riesgo_aprobacion_utec.html"
OMITIR = ("python3 -m venv", "source ", "python -m pip install", "nano ", "pwd", "docker ", "curl ", "lsof ", "mkdir lab-06", "cd lab-06",
          "python -m loadgen")                     # loadgen necesita el stack de Docker levantado
ESPERADOS_MAL = ("--proveedor jev", "--proveedor embeddings")


def main() -> int:
    destino = Path(sys.argv[1])
    shutil.rmtree(destino, ignore_errors=True)
    destino.mkdir(parents=True)
    env = {**os.environ, "PYTHONUTF8": "1", "ROUTER_PROVIDER": "hash", "LLM_PROVIDER": "mock", "EMBEDDINGS_PROVIDER": "hash",
           "TYPESAFE_API_KEY": "", "OPENAI_API_KEY": ""}
    pagina = GUIA.read_text(encoding="utf-8")
    fallos = creados = 0
    for sid, cuerpo in re.findall(r'<section[^>]*id="([^"]+)"[^>]*>(.*?)</section>', pagina, re.S):
        bloques = re.findall(r'<div class="(code[^"]*)"><div class="code-h">(.*?)</div><pre[^>]*><code([^>]*)>(.*?)</code></pre></div>', cuerpo, re.S)
        for clases, cab, atributos, cod in bloques:                 # 1) archivos del paso, en el orden de la guía
            if '<span class="tag">crear</span>' in cab:
                fn = html.unescape(re.sub(r"<[^>]+>", "", re.search(r'<span class="fn">(.*?)</span>', cab, re.S).group(1)))
                ruta = destino / fn.split(" · ")[0].strip()
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(html.unescape(cod) + "\n", encoding="utf-8", newline="\n")
                creados += 1
        for clases, cab, atributos, cod in bloques:                 # 2) comandos del paso
            if 'data-lang="sh"' not in atributos or "os-win" in clases:
                continue
            for linea in (l.strip() for l in html.unescape(cod).splitlines()):
                if not linea or linea.startswith("#") or linea.startswith(OMITIR) or linea == "python -m app":
                    continue
                if linea.startswith(("mkdir -p", "touch ", "cp ")):
                    subprocess.run(linea, shell=True, cwd=destino, check=True)
                    continue
                if not linea.startswith("python "):
                    print(f"     [{sid}] (omitido) {linea}")
                    continue
                r = subprocess.run([sys.executable, *linea.split()[1:]], cwd=destino, env=env, capture_output=True, text=True)
                salida = (r.stdout + r.stderr).strip().splitlines() or [""]
                esperado = "verificar_claves" in linea or (r.returncode != 0 and linea.endswith(ESPERADOS_MAL))
                ok = r.returncode == 0 or esperado
                fallos += not ok
                marca = "OK " if r.returncode == 0 or "verificar_claves" in linea else "MAL (esperado: requiere clave)" if ok else "MAL"
                print(f"{marca:<4} [{sid:>4}] {linea:<55} -> {salida[-1][:70]}")
                if not ok:
                    print("\n".join(salida[-25:]))
    print(f"\nArchivos creados desde la guía: {creados} · fallos inesperados: {fallos}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
