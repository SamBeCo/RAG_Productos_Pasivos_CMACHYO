"""Paso 3: configuración central. Todo lo ajustable vive aquí y se lee de .env.

Windows: el Bloc de notas guarda UTF-8 con BOM y PowerShell 5.1 (`echo X=1 > .env`) guarda UTF-16. python-dotenv, por sí
solo, lee mal (o no lee) esos archivos. Por eso `.env` se decodifica a mano antes de cargarlo.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # .../lab-06-riesgo-aprobacion
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"


class ConfigError(RuntimeError):
    """Configuración inválida o incompleta (falta una clave, proveedor desconocido…)."""


def decode_env_bytes(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):   # UTF-16 (con BOM)
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")                   # UTF-8, con o sin BOM


def load_env(path: Path | None = None) -> None:
    """Carga .env sin pisar variables que ya estén definidas en el sistema (override=False)."""
    path = path or BASE_DIR / ".env"
    if path.exists():
        load_dotenv(stream=io.StringIO(decode_env_bytes(path.read_bytes())), override=False)


def _txt(nombre: str, defecto: str = "") -> str:
    return os.getenv(nombre, defecto).strip()


def _num(nombre: str, defecto: float) -> float:
    valor = _txt(nombre)
    try:
        return float(valor) if valor else defecto
    except ValueError:
        raise ConfigError(f"{nombre}={valor!r} no es un número") from None


class Settings:
    """Se construye al llamar `Settings()`, así las pruebas pueden cambiar variables y crear otra."""

    def __init__(self) -> None:
        # --- proveedores -----------------------------------------------------------------------------------
        self.router_provider = _txt("ROUTER_PROVIDER", "jev").lower()            # jev | embeddings | hash
        self.llm_provider = _txt("LLM_PROVIDER", "openai").lower()               # openai | mock
        self.embeddings_provider = _txt("EMBEDDINGS_PROVIDER", "openai").lower() # openai | hash

        # --- Jev (TypeSafe) ------------------------------------------------------------------------------------
        self.typesafe_api_key = _txt("TYPESAFE_API_KEY")
        self.jev_base_url = _txt("JEV_BASE_URL", "https://api.typesafe.ai").rstrip("/")
        self.jev_model = _txt("JEV_MODEL", "jev-latest")
        self.jev_timeout_s = _num("JEV_TIMEOUT_S", 15)
        self.router_min_confidence = _num("ROUTER_MIN_CONFIDENCE", 0.55)   # Jev: por debajo → fuera_de_alcance
        self.router_min_score = _num("ROUTER_MIN_SCORE", 0.52)             # router por embeddings (respaldo); umbral semántico mínimo
        self.inyeccion_umbral = _num("INYECCION_UMBRAL", 0.8)              # Jev: probabilidad para marcar un mensaje

        # --- OpenAI --------------------------------------------------------------------------------------------
        self.openai_api_key = _txt("OPENAI_API_KEY")
        self.openai_model = _txt("OPENAI_MODEL", "gpt-5.4-mini")
        self.openai_embedding_model = _txt("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.openai_reasoning_effort = _txt("OPENAI_REASONING_EFFORT").lower()
        self.openai_timeout_s = _num("OPENAI_TIMEOUT_S", 60)
        self.openai_max_output_tokens = int(_num("OPENAI_MAX_OUTPUT_TOKENS", 2000))

        # --- RAG -----------------------------------------------------------------------------------------------
        self.rag_top_k = int(_num("RAG_TOP_K", 4))
        self.rag_min_score = _num("RAG_MIN_SCORE", 0.25)
        pdf_configurado = _txt("PDF_PATH")
        self.pdf_path = (Path(pdf_configurado) if pdf_configurado
                         and Path(pdf_configurado).name.lower() != "documentos_caja_huancayo.pdf" else None)
        self.uploads_dir = Path(_txt("UPLOAD_DIR") or DATA_DIR / "fuentes_cargadas")
        self.indice_path = Path(_txt("INDICE_PATH") or DATA_DIR / "indice.npz")

        # --- aplicación ----------------------------------------------------------------------------------------
        self.db_path = Path(_txt("DB_PATH") or DATA_DIR / "solicitudes.db")
        self.analista_token = _txt("ANALISTA_TOKEN")
        self.admin_token = _txt("ADMIN_TOKEN")
        self.upload_max_bytes = int(_num("UPLOAD_MAX_BYTES", 25 * 1024 * 1024))

        # --- costos (USD por millón de tokens) -----------------------------------------------------------------
        self.precio_jev_input = _num("PRECIO_JEV_INPUT", 0.042)
        self.precio_openai_input = _num("PRECIO_OPENAI_INPUT", 0)
        self.precio_openai_output = _num("PRECIO_OPENAI_OUTPUT", 0)
        self.precio_openai_embeddings = _num("PRECIO_OPENAI_EMBEDDINGS", 0)

    def validar(self) -> None:
        """Falla al arrancar con un mensaje claro, en vez de fallar en la primera solicitud."""
        opciones = {"router_provider": {"jev", "embeddings", "hash"}, "llm_provider": {"openai", "mock"},
                    "embeddings_provider": {"openai", "hash"}}
        for campo, validas in opciones.items():
            if getattr(self, campo) not in validas:
                raise ConfigError(f"{campo.upper()}={getattr(self, campo)!r}; opciones: {sorted(validas)}")
        if self.router_provider == "jev" and not self.typesafe_api_key:
            raise ConfigError("ROUTER_PROVIDER=jev pero TYPESAFE_API_KEY está vacío en .env "
                              "(sin clave de Jev usa ROUTER_PROVIDER=embeddings)")
        if "openai" in (self.llm_provider, self.embeddings_provider) and not self.openai_api_key:
            raise ConfigError("LLM_PROVIDER/EMBEDDINGS_PROVIDER=openai pero OPENAI_API_KEY está vacío en .env")
        if self.router_provider == "embeddings" and self.embeddings_provider == "hash":
            raise ConfigError("ROUTER_PROVIDER=embeddings con EMBEDDINGS_PROVIDER=hash: usa ROUTER_PROVIDER=hash")


load_env()
