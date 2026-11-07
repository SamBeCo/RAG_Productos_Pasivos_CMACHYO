"""Arranque local:   python -m app            (http://127.0.0.1:8000/)

Usado para levantar el prototipo de asistente de información sobre ahorros de Caja Huancayo.
"""
import os

import uvicorn

if __name__ == "__main__":
    try:
        uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
    except KeyboardInterrupt:          # Ctrl+C: salir sin traza de error
        pass
