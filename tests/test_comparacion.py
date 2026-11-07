"""Agente comparador: evidencia por producto, citas y regla de no recomendar."""
from app.agente_ahorro import AgenteRiesgo
from app.guardas_respuesta import detecta_recomendacion
from app.llm import MockLLM, RespuestaLLM


class LLMRecomienda(MockLLM):
    def generar(self, instrucciones, contexto, esquema, nombre):
        if nombre == "reformulacion":
            return super().generar(instrucciones, contexto, esquema, nombre)
        ids =  [r["id"] for r in contexto["reglas_del_manual"]][:1]
        return RespuestaLLM({"respuesta": "Te recomiendo la cuenta de ahorros porque es la mejor opción.",
                             "reglas_citadas": ids}, "falso")


def test_detecta_recomendacion():
    assert detecta_recomendacion("Te recomiendo abrir el plazo fijo")
    assert detecta_recomendacion("La mejor opción es la cuenta")
    assert not detecta_recomendacion("La cuenta de ahorros no exige plazo; el depósito sí.")


def test_comparar_cita_varias_fuentes(rag):
    r = AgenteRiesgo(rag, MockLLM()).comparar_productos("Compara los documentos de cuentas de ahorro")
    assert r["estado"] == "PUBLICAR"
    assert r["reglas_citadas"] and set(r["reglas_citadas"]) <= {x["id"] for x in r["reglas"]}
    assert r["citas"]


def test_comparador_no_recomienda(rag):
    r = AgenteRiesgo(rag, LLMRecomienda()).comparar_productos("Compara los documentos de cuentas de ahorro")
    assert r["estado"] == "ABSTENER" and r["motivo"] == "recomendacion_personalizada"
    assert "recomiendo" not in r["respuesta"].lower()


def test_consulta_simple_no_aplica_guarda_de_recomendacion(rag):
    r = AgenteRiesgo(rag, LLMRecomienda()).responder_consulta("¿Qué documentos hablan de cuentas de ahorro?")
    assert r["motivo"] != "recomendacion_personalizada"
