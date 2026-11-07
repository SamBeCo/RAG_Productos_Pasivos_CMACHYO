"""Router Jev contra un servidor SIMULADO (httpx.MockTransport): se prueba el cuerpo que enviamos, cómo leemos la
respuesta y qué pasa con cada error HTTP. No prueba que Jev clasifique bien: eso lo mide eval/eval_router.py con la
API real."""
import json

import httpx
import pytest

from app import metricas
from app.config import DATA_DIR, Settings
from app.embeddings import HashEmbedder
from app.router import EmbeddingRouter, JevError, JevRouter, RouterConRespaldo, cargar_rutas

RUTAS = cargar_rutas()


def respuesta_jev(eleccion="consulta_ahorros", probs=None):
    probs = probs or {"consulta_ahorros": 0.91, "fuera_de_alcance": 0.09}
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 180, "output_tokens": 0},
            "answers": {"ruta": {"type": "choice", "choice": eleccion, "confidence": 0.88, "probabilities": probs}}}


class Servidor:
    """Devuelve las respuestas de la lista en orden y guarda cada petición recibida."""

    def __init__(self, *respuestas):
        self.respuestas, self.peticiones = list(respuestas), []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        estado, cuerpo, headers = self.respuestas.pop(0)
        return httpx.Response(estado, json=cuerpo, headers=headers)


def router(servidor, monkeypatch, **env):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-clave-de-prueba")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    esperas = []
    r = JevRouter(Settings(), RUTAS, transport=httpx.MockTransport(servidor), dormir=esperas.append)
    return r, esperas


def test_cuerpo_y_cabeceras_de_la_peticion(monkeypatch):
    srv = Servidor((200, respuesta_jev(), {}))
    r, _ = router(srv, monkeypatch)
    r.enrutar("¿Qué requisitos figuran para una cuenta de ahorro?")
    p = srv.peticiones[0]
    assert p.method == "POST" and p.url.path == "/v1/systemone"
    assert p.headers["authorization"]
    cuerpo = json.loads(p.content)
    assert cuerpo["model"] == "jev-latest" and cuerpo["state"] == "¿Qué requisitos figuran para una cuenta de ahorro?"
    q = cuerpo["questions"]["ruta"]
    assert q["type"] == "choice" and set(q["criteria"]) == set(RUTAS)


def test_lee_ruta_probabilidad_y_modelo(monkeypatch):
    r, _ = router(Servidor((200, respuesta_jev(), {})), monkeypatch)
    res = r.enrutar("x")
    assert (res.ruta, res.confianza, res.modelo, res.proveedor) == ("consulta_ahorros", 0.91, "jev-1.13.0", "jev")


def test_bajo_el_umbral_va_a_fuera_de_alcance(monkeypatch):
    probs = {"consulta_ahorros": 0.40, "fuera_de_alcance": 0.60}
    r, _ = router(Servidor((200, respuesta_jev(probs=probs), {})), monkeypatch)
    res = r.enrutar("algo ambiguo")
    assert res.ruta == "fuera_de_alcance" and res.bajo_umbral and res.confianza == 0.40


def test_sin_campo_choice_usa_la_opcion_mas_probable(monkeypatch):
    cuerpo = respuesta_jev(probs={"consulta_ahorros": 0.1, "fuera_de_alcance": 0.9})
    del cuerpo["answers"]["ruta"]["choice"]
    r, _ = router(Servidor((200, cuerpo, {})), monkeypatch)
    assert r.enrutar("x").ruta == "fuera_de_alcance"


def test_clave_invalida_no_reintenta(monkeypatch):
    srv = Servidor((401, {"error": "invalid key"}, {}))
    r, esperas = router(srv, monkeypatch)
    with pytest.raises(JevError) as e:
        r.enrutar("x")
    assert e.value.motivo == "auth" and len(srv.peticiones) == 1 and esperas == []


def test_limite_429_respeta_retry_after_y_reintenta(monkeypatch):
    srv = Servidor((429, {}, {"retry-after": "2"}), (200, respuesta_jev(), {}))
    r, esperas = router(srv, monkeypatch)
    assert r.enrutar("x").ruta == "consulta_ahorros"
    assert len(srv.peticiones) == 2 and esperas == [2.0]


def test_sobrecarga_529_persistente_falla_tras_tres_intentos(monkeypatch):
    srv = Servidor(*[(529, {}, {})] * 3)
    r, esperas = router(srv, monkeypatch)
    with pytest.raises(JevError) as e:
        r.enrutar("x")
    assert e.value.motivo == "servidor" and len(srv.peticiones) == 3 and esperas == [0.5, 1.0]


def test_ruta_desconocida_es_error_de_validacion(monkeypatch):
    r, _ = router(Servidor((200, respuesta_jev(eleccion="hipotecario"), {})), monkeypatch)
    with pytest.raises(JevError, match="hipotecario"):
        r.enrutar("x")


def test_jev_falla_usa_respaldo_y_lo_cuenta(monkeypatch):
    r, _ = router(Servidor((401, {}, {})), monkeypatch)
    antes = metricas.ROUTER_RESPALDO.labels("auth")._value.get()
    combinado = RouterConRespaldo(r, EmbeddingRouter(RUTAS, HashEmbedder(), 0.3))
    res = combinado.enrutar("¿Qué tasa y condiciones tiene el depósito a plazo?")
    assert res.proveedor == "hash" and res.ruta == "consulta_ahorros" and "auth" in res.respaldo
    assert metricas.ROUTER_RESPALDO.labels("auth")._value.get() == antes + 1


def test_tokens_de_jev_se_cuentan(monkeypatch):
    r, _ = router(Servidor((200, respuesta_jev(), {})), monkeypatch)
    antes = metricas.TOKENS.labels("jev", "input")._value.get()
    r.enrutar("x")
    assert metricas.TOKENS.labels("jev", "input")._value.get() == antes + 180


@pytest.mark.parametrize("ruta", list(RUTAS))
def test_router_por_embeddings_reconoce_sus_propios_ejemplos(ruta):
    er = EmbeddingRouter(RUTAS, HashEmbedder(), 0.3)
    for ejemplo in RUTAS[ruta]["ejemplos"]:
        res = er.enrutar(ejemplo)
        assert res.ruta == ruta and res.confianza > 0.99


def test_router_por_embeddings_texto_sin_relacion_va_a_fuera_de_alcance():
    assert EmbeddingRouter(RUTAS, HashEmbedder(), 0.3).enrutar("zzqx wwpk").ruta == "fuera_de_alcance"


def test_router_por_embeddings_pregunta_geografica_va_a_fuera_de_alcance():
    """Con el umbral de producción (0.52), preguntas ajenas como '¿Dónde queda Huancayo?' deben derivarse."""
    er = EmbeddingRouter(RUTAS, HashEmbedder(), 0.52)
    res = er.enrutar("¿Dónde queda Huancayo?")
    assert res.ruta == "fuera_de_alcance"


def test_router_gold_hash_supera_el_umbral_calibrado():
    casos = json.loads((DATA_DIR / "router_gold.json").read_text(encoding="utf-8"))
    router = EmbeddingRouter(RUTAS, HashEmbedder(), 0.30)
    aciertos = sum(router.enrutar(caso["texto"]).ruta == caso["ruta"] for caso in casos)
    assert aciertos / len(casos) >= 0.95


def test_jev_recibe_el_historial_y_la_pregunta_de_inyeccion(monkeypatch):
    srv = Servidor((200, respuesta_jev(), {}))
    r, _ = router(srv, monkeypatch)
    r.enrutar("¿Y para el depósito a plazo?", historial=["a", "b", "¿Qué TEA tiene el ahorro en soles?", "c"])
    cuerpo = json.loads(srv.peticiones[0].content)
    assert cuerpo["state"].endswith("Mensaje actual:\n¿Y para el depósito a plazo?")
    assert "- a\n" not in cuerpo["state"] and "- c" in cuerpo["state"]        # solo los 3 últimos
    assert cuerpo["questions"]["inyeccion"]["type"] == "noul"


def test_lee_la_probabilidad_de_inyeccion(monkeypatch):
    cuerpo = respuesta_jev()
    cuerpo["answers"]["inyeccion"] = {"type": "noul", "noul": 0.93}
    r, _ = router(Servidor((200, cuerpo, {})), monkeypatch)
    assert r.enrutar("x").inyeccion == 0.93


def test_sin_respuesta_de_inyeccion_no_se_cae(monkeypatch):
    r, _ = router(Servidor((200, respuesta_jev(), {})), monkeypatch)
    assert r.enrutar("x").inyeccion is None
