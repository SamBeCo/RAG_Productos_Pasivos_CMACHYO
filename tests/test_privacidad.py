"""Los datos personales no salen hacia terceros. Se prueba en la función y en los TRES adaptadores de salida, con el
cuerpo HTTP que realmente se enviaría (servidores simulados)."""
import json

import httpx
import httpx2
import pytest
from openai import OpenAI

from app import metricas
from app.config import Settings
from app.embeddings import OpenAIEmbedder
from app.llm import ESQUEMA_RESPUESTA, OpenAILLM
from app.privacidad import enmascarar
from app.router import JevRouter, cargar_rutas


@pytest.mark.parametrize("texto, esperado", [
    ("mi cliente 40123456 quiere un crédito", "mi cliente [DNI] quiere un crédito"),
    ("cel 987654321 o 987 654 321 o +51 987-654-321", "cel [TELEFONO] o [TELEFONO] o [TELEFONO]"),
    ("RUC 20123456789", "RUC [RUC]"),
    ("escribe a rosa.quispe@correo.pe", "escribe a [EMAIL]"),
    ("cliente Rosa Quispe consulta", "cliente [NOMBRE] consulta"),
    ("domicilio Calle Real 341", "domicilio [DIRECCION]"),
])
def test_enmascara_datos_personales(texto, esperado):
    assert enmascarar(texto) == esperado


@pytest.mark.parametrize("texto", ["monto 10000000.0", "S/ 12000 a 24 meses", "cuenta 1234567890123", "ingreso 3500.50"])
def test_no_toca_montos_ni_numeros_de_otra_longitud(texto):
    assert enmascarar(texto) == texto


def test_cuenta_lo_enmascarado():
    antes = metricas.PII_ENMASCARADO.labels("dni")._value.get()
    enmascarar("40123456 y 41234567")
    assert metricas.PII_ENMASCARADO.labels("dni")._value.get() == antes + 2


def test_jev_nunca_recibe_el_dni(monkeypatch):
    enviado = []

    def servidor(request):
        enviado.append(request.content.decode())
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": {"ruta": {"choice": "consulta_ahorros",
                                         "probabilities": {"consulta_ahorros": 0.9, "fuera_de_alcance": 0.1}}}})
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-x")
    JevRouter(Settings(), cargar_rutas(), transport=httpx.MockTransport(servidor)).enrutar(
        "¿califica 40123456?", historial=["mi cliente 41234567, cel 987654321"])
    assert "40123456" not in enviado[0] and "41234567" not in enviado[0] and "987654321" not in enviado[0]
    assert "[DNI]" in json.loads(enviado[0])["state"]


def test_openai_llm_nunca_recibe_el_dni(monkeypatch):
    enviado = []
    respuesta = {"id": "r", "object": "response", "created_at": 0, "status": "completed", "model": "m", "parallel_tool_calls": True,
                 "tool_choice": "auto", "tools": [], "output": [{"type": "message", "id": "m1", "status": "completed", "role": "assistant",
                 "content": [{"type": "output_text", "text": '{"respuesta": "ok", "reglas_citadas": []}', "annotations": []}]}]}

    def servidor(request):
        enviado.append(json.loads(request.content)["input"])
        return httpx2.Response(200, json=respuesta)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    cliente = OpenAI(api_key="sk-x", http_client=httpx2.Client(transport=httpx2.MockTransport(servidor)), max_retries=0)
    OpenAILLM(Settings(), client=cliente).generar("i", {"conversacion_previa": [{"rol": "asesor", "texto": "DNI 40123456"}]},
                                                  ESQUEMA_RESPUESTA, "respuesta")
    assert "40123456" not in enviado[0] and "[DNI]" in enviado[0]


def test_openai_embeddings_nunca_recibe_el_dni(monkeypatch):
    enviado = []

    def servidor(request):
        enviado.append(json.loads(request.content)["input"])
        return httpx2.Response(200, json={"object": "list", "model": "text-embedding-3-small",
                                          "data": [{"object": "embedding", "index": 0, "embedding": [0.6, 0.8]}],
                                          "usage": {"prompt_tokens": 5, "total_tokens": 5}})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    cliente = OpenAI(api_key="sk-x", http_client=httpx2.Client(transport=httpx2.MockTransport(servidor)), max_retries=0)
    m = OpenAIEmbedder(Settings(), client=cliente).embed(["cliente 40123456"])
    assert enviado[0] == ["cliente [DNI]"] and m.shape == (1, 2)
