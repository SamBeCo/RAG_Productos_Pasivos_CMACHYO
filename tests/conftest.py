"""Las pruebas NUNCA llaman a Jev ni a OpenAI de verdad: no gastan dinero, no necesitan internet y siempre dan lo mismo.
Las llamadas reales se prueban aparte con:  python -m scripts.verificar_claves
"""
import os

import pytest

# Antes de importar app.*: que ningún .env del alumno cambie el comportamiento de las pruebas.
for k in ("ROUTER_PROVIDER", "LLM_PROVIDER", "EMBEDDINGS_PROVIDER", "TYPESAFE_API_KEY", "OPENAI_API_KEY", "ANALISTA_TOKEN",
          "PDF_PATH", "INDICE_PATH", "DB_PATH", "ROUTER_MIN_CONFIDENCE", "ROUTER_MIN_SCORE", "RAG_MIN_SCORE", "RAG_TOP_K", "INYECCION_UMBRAL"):
    os.environ.pop(k, None)
os.environ.update(ROUTER_PROVIDER="hash", LLM_PROVIDER="mock", EMBEDDINGS_PROVIDER="hash", ANALISTA_TOKEN="token-de-prueba")

# Los import de app.* van DENTRO de cada fixture: así las pruebas del paso 3 corren aunque todavía no hayas creado
# los archivos de los pasos siguientes (cada fixture solo importa lo que necesita).


@pytest.fixture(scope="session")
def pdf(tmp_path_factory):
    from rules.generar_pdf import generar
    return generar(tmp_path_factory.mktemp("pdf") / "politicas_riesgo.pdf")


@pytest.fixture
def settings(tmp_path, pdf, monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("PDF_PATH", str(pdf))
    monkeypatch.setenv("INDICE_PATH", str(tmp_path / "indice.npz"))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "solicitudes.db"))
    return Settings()


@pytest.fixture
def rag(settings):
    from app.embeddings import HashEmbedder
    from app.ingesta import construir_indice
    from app.rag import RAG
    construir_indice(settings, HashEmbedder())
    return RAG(settings.indice_path, HashEmbedder(), settings.rag_min_score, settings.rag_top_k)


# Solicitud ficticia usada en pruebas de guardas, herramientas y agente.
# Corresponde al manual educativo ficticio de rules/politicas.py; no es un producto real de Caja Huancayo.
SOLICITUD_SANA = {
    "dni": "40123456", "nombre": "Rosa Quispe", "edad": 35, "ingreso_mensual": 3500, "deuda_mensual": 400,
    "calificacion_sbs": "Normal", "antiguedad_meses": 24, "tipo_trabajador": "dependiente", "producto": "consumo",
    "monto": 12000, "plazo_meses": 24, "pregunta": "¿Cuáles son los requisitos para este producto de ahorro?",
}


@pytest.fixture
def sana():
    return dict(SOLICITUD_SANA)
