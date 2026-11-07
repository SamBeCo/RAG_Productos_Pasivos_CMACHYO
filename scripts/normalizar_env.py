"""Reescribe .env como UTF-8 sin BOM y con saltos de línea LF.

Uso:   python -m scripts.normalizar_env

¿Por qué? app/config.py entiende un .env en UTF-16 (el que crea `echo X=1 > .env` en PowerShell 5.1), pero
Docker Compose NO: `docker compose up` falla con 'unexpected character "�" in variable name'. Medido con Docker
Compose v5.1.4: UTF-8 con BOM y CRLF sí los acepta; UTF-16 no. Este script deja el archivo en el formato que
entienden todos. No imprime el contenido (tiene tus claves).
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import BASE_DIR, decode_env_bytes


def normalizar(path: Path) -> list[str]:
    crudo = path.read_bytes()
    cambios = []
    if crudo.startswith((b"\xff\xfe", b"\xfe\xff")):
        cambios.append("UTF-16 -> UTF-8")
    elif crudo.startswith(b"\xef\xbb\xbf"):
        cambios.append("se quitó el BOM")
    texto = decode_env_bytes(crudo)
    if "\r\n" in texto:
        cambios.append("CRLF -> LF")
    if cambios:
        path.write_text(texto.replace("\r\n", "\n"), encoding="utf-8", newline="\n")
    return cambios


def main() -> int:
    path = BASE_DIR / ".env"
    if not path.exists():
        print(f"No existe {path.name}. Créalo con: Copy-Item .env.example .env   (macOS/Linux: cp .env.example .env)")
        return 1
    cambios = normalizar(path)
    print(".env normalizado: " + ", ".join(cambios) if cambios else ".env ya está en UTF-8 sin BOM y con LF: sin cambios")
    return 0


if __name__ == "__main__":
    sys.exit(main())
