import json
from pathlib import Path

from app.rag import Fragmento
from app.config import Settings
from app.embeddings import HashEmbedder
from app.ingesta import construir_indice
from eval.eval_rag import medir
from app.rag import RAG


class RAGFalso:
    def __init__(self, resultados):
        self.resultados = resultados

    def buscar(self, pregunta, k=None):
        return self.resultados[pregunta][:k]


def _fragmento(documento, texto):
    return Fragmento("id", "titulo", None, texto, documento=documento)


def test_metricas_rag_calculan_precision_reciprocal_rank_y_abstencion():
    primera = "pregunta respondible"
    segunda = "pregunta respondible sin acierto"
    tercera = "pregunta sin evidencia"
    oro = [
        {"pregunta": primera, "answerable": True, "fuentes_esperadas": [
            {"documento": "fuente.docx", "contiene": ["evidencia"]},
        ]},
        {"pregunta": segunda, "answerable": True, "fuentes_esperadas": [
            {"documento": "otra.docx", "contiene": ["objetivo"]},
        ]},
        {"pregunta": tercera, "answerable": False, "fuentes_esperadas": []},
    ]
    rag = RAGFalso({
        primera: [
            _fragmento("irrelevante.docx", "texto ajeno"),
            _fragmento("fuente.docx", "evidencia verificable"),
        ],
        segunda: [_fragmento("irrelevante.docx", "sin coincidencia")],
        tercera: [],
    })
    metricas = medir(rag, oro, k=2)
    assert metricas == {
        "k": 2,
        "precision": 1 / 3,
        "hit_rate": 0.5,
        "mrr": 0.25,
        "abstention_accuracy": 1.0,
        "coverage": 2 / 3,
    }


def test_corpus_real_supera_minimos_del_set_de_oro(tmp_path):
    settings = Settings()
    settings.pdf_path = None
    settings.uploads_dir = tmp_path / "uploads"
    settings.indice_path = tmp_path / "indice.npz"
    embedder = HashEmbedder()
    construir_indice(settings, embedder)
    rag = RAG(settings.indice_path, embedder, min_score=0.25, top_k=2)
    gold_path = Path(__file__).resolve().parents[1] / "data" / "rag_gold.json"
    oro = json.loads(gold_path.read_text(encoding="utf-8"))

    resultados = medir(rag, oro, k=2)
    assert resultados["precision"] >= 0.60
    assert resultados["hit_rate"] == 1.0
    assert resultados["mrr"] >= 0.85
    assert resultados["abstention_accuracy"] == 1.0
