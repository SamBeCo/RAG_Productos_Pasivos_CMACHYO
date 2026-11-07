"""Pruebas de la API para el prototipo de ahorro de Caja Huancayo."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.agente_ahorro import AgenteRiesgo
from app.db import Repositorio
from app.llm import MockLLM
from app.main import Servicios, create_app
from app.router import ResultadoRuta


class RouterFijo:
    def enrutar(self, texto, historial=None):
        t = texto.lower()
        ruta = "consulta_ahorros" if any(k in t for k in ("ahorro", "depósito", "documentos", "requisito", "condición")) else "fuera_de_alcance"
        return ResultadoRuta(ruta, 0.9, "fijo", modelo="fijo")


@pytest.fixture
def cliente(settings, rag):
    s = Servicios(settings, RouterFijo(), AgenteRiesgo(rag, MockLLM()), Repositorio(settings.db_path))
    with TestClient(create_app(s)) as c:
        yield c


@pytest.fixture
def cliente_admin(settings, rag, tmp_path):
    settings.admin_token = "token-admin-prueba"
    settings.pdf_path = None
    settings.uploads_dir = tmp_path / "uploads"
    s = Servicios(settings, RouterFijo(), AgenteRiesgo(rag, MockLLM()), Repositorio(settings.db_path))
    with TestClient(create_app(s)) as c:
        yield c


def _pdf_bytes():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 760, "Manual de prueba para carga administrativa")
    pdf.save()
    return buffer.getvalue()


def test_consulta_de_ahorro_responde_directo_con_citas(cliente, sana):
    sana["pregunta"] = "¿Qué documentos mencionan cuentas de ahorro?"
    d = cliente.post("/api/solicitudes", json=sana).json()
    assert d["estado"] == "RESPONDIDA"
    assert d["citas"]


def test_fuera_de_alcance_se_deriva(cliente, sana):
    sana["pregunta"] = "¿A qué hora cierra la agencia?"
    d = cliente.post("/api/solicitudes", json=sana).json()
    assert d["estado"] == "DERIVADA" and "Caja Huancayo" in d["respuesta"]


def test_metricas_expuestas(cliente, sana):
    cliente.post("/api/solicitudes", json={**sana, "pregunta": "¿Qué información hay sobre ahorro?"})
    texto = cliente.get("/metrics").text
    assert 'gpp_consultas_total' in texto
    assert 'gpp_documentos_indexados' in texto
    assert 'lab06_rag_score_bucket' in texto


def test_paginas_html(cliente):
    pagina = cliente.get("/").text
    assert "Caja Huancayo" in pagina and "Gestor de Productos Pasivos" in pagina
    assert "referencia(s) de las fuentes" in pagina
    assert cliente.get("/health").json() == {"status": "ok"}


def test_api_admin_requiere_token(cliente_admin):
    assert cliente_admin.get("/api/admin/documentos").status_code == 401
    respuesta = cliente_admin.get(
        "/api/admin/documentos", headers={"X-Admin-Token": "token-admin-prueba"},
    )
    assert respuesta.status_code == 200


def test_carga_pdf_valida_y_reindexa_solo_con_token(cliente_admin):
    archivo = ("manual.pdf", _pdf_bytes(), "application/pdf")
    respuesta = cliente_admin.post(
        "/api/admin/documentos",
        headers={"X-Admin-Token": "token-admin-prueba"},
        files={"archivo": archivo},
    )
    assert respuesta.status_code == 200, respuesta.text
    documentos = cliente_admin.get(
        "/api/admin/documentos", headers={"X-Admin-Token": "token-admin-prueba"},
    ).json()["documentos"]
    assert any(documento["nombre"] == "manual.pdf" for documento in documentos)
    assert any(documento["nombre"] == "Tarifario_Caja_Huancayo.xlsx" for documento in documentos)


def test_upload_rechaza_pdf_invalido_de_forma_controlada(cliente_admin):
    respuesta = cliente_admin.post(
        "/api/admin/documentos",
        headers={"X-Admin-Token": "token-admin-prueba"},
        files={"archivo": ("invalido.pdf", b"%PDF-1.4 contenido invalido", "application/pdf")},
    )
    assert respuesta.status_code == 422
