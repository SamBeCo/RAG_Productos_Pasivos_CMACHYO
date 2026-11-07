import pytest

from app.embeddings import HashEmbedder
from app.ingesta import extraer_fragmentos
from app.rag import RAG, IndiceError
from rules import politicas


def test_el_pdf_devuelve_exactamente_las_reglas_de_la_fuente(pdf):
    """Si el texto del PDF y rules/politicas.py divergieran, el RAG y las guardas dirían cosas distintas."""
    fuente = {a["id"]: a for a in politicas.articulos()}
    fragmentos = extraer_fragmentos(pdf)
    assert [f["id"] for f in fragmentos] == list(fuente)
    for f in fragmentos:
        assert f["titulo"] == fuente[f["id"]]["titulo"]
        assert f["texto"] == fuente[f["id"]]["texto"]


def test_el_ruido_del_pdf_no_entra_al_indice(pdf):
    for f in extraer_fragmentos(pdf):
        assert "Página" not in f["texto"] and politicas.ENTIDAD not in f["texto"] and "Capítulo" not in f["texto"]


def test_los_articulos_estan_en_varias_paginas(pdf):
    assert {f["pagina"] for f in extraer_fragmentos(pdf)} == {1, 2, 3}


@pytest.mark.parametrize("pregunta, articulo", [
    ("calificación CPP", "5.2"),
    ("¿qué documentos pide un independiente?", "3.3"),
    ("máximo de cuota respecto al ingreso", "4.2"),
    ("¿cuál es la tasa del crédito vehicular?", "2.3"),
])
def test_busqueda_encuentra_el_articulo(rag, pregunta, articulo):
    assert rag.buscar(pregunta)[0].id == articulo


def test_por_id_es_exacto(rag):
    f = rag.por_id("4.3")
    assert f.titulo == "Endeudamiento total" and f.score == 1.0
    assert rag.por_id("9.9") is None


def test_pregunta_sin_relacion_no_devuelve_contexto(rag):
    assert rag.buscar("xqzv wkjh plmn") == []


def test_indice_de_otro_embedder_falla_con_mensaje_claro(rag, settings):
    with pytest.raises(IndiceError, match="python -m app.ingesta"):
        RAG(settings.indice_path, HashEmbedder(dim=512), 0.2, 3)


def test_sin_indice_falla_con_mensaje_claro(tmp_path):
    with pytest.raises(IndiceError, match="python -m app.ingesta"):
        RAG(tmp_path / "no_existe.npz", HashEmbedder(), 0.2, 3)
