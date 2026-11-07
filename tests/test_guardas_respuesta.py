"""Guards deterministas del flujo RAG activo: referencias, grounding y abstención."""
from app.guardas_respuesta import ESTADO_ABSTENER, ESTADO_PUBLICAR, revisar_respuesta_documental
from app.rag import Fragmento


def _fragmento(texto: str = "Ahorro Corriente: tasa 0.30% anual.") -> Fragmento:
    return Fragmento(
        id="tarifario-7",
        titulo="Ahorro Corriente",
        pagina=None,
        texto=texto,
        score=0.82,
        documento="Tarifario_Caja_Huancayo.xlsx",
        ubicacion="Hoja Tarifario · fila 7",
    )


def test_respuesta_con_cifra_sustentada_devuelve_referencia():
    resultado = revisar_respuesta_documental(
        "La tasa indicada es 0.30%.",
        "¿Cuál es la tasa?",
        [_fragmento()],
    )
    assert resultado.estado == ESTADO_PUBLICAR
    assert resultado.citas[0]["id"] == "tarifario-7"
    assert resultado.citas[0]["documento"] == "Tarifario_Caja_Huancayo.xlsx"
    assert resultado.citas[0]["ubicacion"] == "Hoja Tarifario · fila 7"


def test_respuesta_con_cifra_no_sustentada_se_abstiene():
    resultado = revisar_respuesta_documental(
        "La tasa indicada es 9.99%.",
        "¿Cuál es la tasa?",
        [_fragmento()],
    )
    assert resultado.estado == ESTADO_ABSTENER
    assert resultado.motivo == "cifra_sin_grounding"
    assert resultado.cifras_sin_grounding == ["9.99"]


def test_no_publica_respuesta_sin_fragmentos_citados():
    resultado = revisar_respuesta_documental("Respuesta sin evidencia.", "¿Qué ofrece?", [])
    assert resultado.estado == ESTADO_ABSTENER
    assert resultado.motivo == "sin_citas"


def test_fallo_del_llm_abstiene_aunque_haya_contexto():
    resultado = revisar_respuesta_documental(
        "Respuesta incompleta.", "¿Cuál es la tasa?", [_fragmento()], fallo_llm=True,
    )
    assert resultado.estado == ESTADO_ABSTENER
    assert resultado.motivo == "fallo_llm"
    assert resultado.citas[0]["id"] == "tarifario-7"
