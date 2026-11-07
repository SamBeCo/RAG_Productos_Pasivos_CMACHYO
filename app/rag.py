"""Recuperación vectorial de fragmentos del corpus persistente del Gestor de Productos Pasivos."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app import metricas
from app.embeddings import Embedder, sin_tildes


class IndiceError(RuntimeError):
    pass


STOPWORDS = {
    "que", "cual", "cuales", "como", "para", "por", "con", "una", "uno", "las", "los", "del", "des",
    "sobre", "entre", "esta", "este", "eso", "hay", "tiene", "tienen", "segun", "desde", "cuando",
}


def _tokens(texto: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", sin_tildes(texto)) if len(t) > 2 and t not in STOPWORDS]


def similitudes(matriz: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Coseno de q contra cada fila (todo está normalizado, así que coseno = producto punto).
    No usamos `matriz @ q`: con numpy 2.x en Mac con chip M, la librería BLAS del sistema emite advertencias falsas
    ('divide by zero encountered in matmul') aunque el resultado sea correcto. Multiplicar y sumar evita BLAS."""
    return (matriz * q).sum(axis=1)


@dataclass
class Fragmento:
    id: str
    titulo: str
    pagina: int | None
    texto: str
    score: float = 0.0
    documento: str = ""
    ubicacion: str = ""

    def cita(self) -> str:
        origen = self.documento or f"Art. {self.id}"
        lugar = self.ubicacion or (f"pág. {self.pagina}" if self.pagina is not None else self.titulo)
        return f"{origen} · {lugar}"


class RAG:
    def __init__(self, indice_path: Path, embedder: Embedder, min_score: float, top_k: int):
        if not indice_path.exists():
            raise IndiceError(f"No existe el índice {indice_path}. Ejecuta: python -m app.ingesta")
        with np.load(indice_path) as z:
            self.vectores = z["vectores"]
            nombre = str(z["embedder"])
            self.fragmentos = [Fragmento(**f) for f in json.loads(str(z["fragmentos"]))]
        if self.vectores.ndim != 2 or self.vectores.shape[0] != len(self.fragmentos):
            raise IndiceError("El índice tiene vectores o metadatos inconsistentes; vuelve a ejecutar python -m app.ingesta.")
        if nombre != embedder.nombre:
            raise IndiceError(f"El índice se creó con '{nombre}' y ahora usas '{embedder.nombre}'. "
                              f"Los vectores de modelos distintos no son comparables: ejecuta python -m app.ingesta")
        if getattr(embedder, "dim", 0) not in (0, self.vectores.shape[1]):
            raise IndiceError(f"Dimensión del índice ({self.vectores.shape[1]}) distinta de la esperada "
                              f"por el embedder ({embedder.dim}); ejecuta python -m app.ingesta")
        self.embedder = embedder
        self.min_score = min_score
        self.top_k = top_k
        self._por_id = {f.id: f for f in self.fragmentos}
        self._tokens_documento = [_tokens(f"{f.documento} {f.titulo} {f.texto}") for f in self.fragmentos]
        self._frecuencias = Counter(t for tokens in self._tokens_documento for t in set(tokens))
        self._longitud_media = (sum(map(len, self._tokens_documento)) / len(self._tokens_documento)
                                if self._tokens_documento else 0)

    def buscar(self, consulta: str, k: int | None = None) -> list[Fragmento]:
        q = self.embedder.embed([consulta])[0]
        if q.shape[0] != self.vectores.shape[1]:
            raise IndiceError(f"Dimensión de la consulta ({q.shape[0]}) distinta de la dimensión del índice ({self.vectores.shape[1]})")
        vector_scores = np.maximum(similitudes(self.vectores, q), 0)
        query_terms = Counter(_tokens(consulta))
        scores_lexicos = np.zeros(len(self.fragmentos), dtype=np.float32)
        total = len(self.fragmentos)
        if query_terms and self._longitud_media:
            for i, tokens in enumerate(self._tokens_documento):
                frecuencias = Counter(tokens)
                longitud = len(tokens)
                for termino, veces_consulta in query_terms.items():
                    frecuencia = frecuencias[termino]
                    if not frecuencia:
                        continue
                    documentos = self._frecuencias[termino]
                    idf = math.log(1 + (total - documentos + 0.5) / (documentos + 0.5))
                    normalizador = frecuencia + 1.5 * (1 - 0.75 + 0.75 * longitud / self._longitud_media)
                    scores_lexicos[i] += (veces_consulta * idf * frecuencia * 2.5 / normalizador)
            scores_lexicos = 1 - np.exp(-scores_lexicos / 8)
        peso_vectorial = 0.25 if self.embedder.nombre.startswith("hash-") else 0.7
        scores = peso_vectorial * vector_scores + (1 - peso_vectorial) * scores_lexicos
        orden = np.argsort(-scores)[: self.top_k if k is None else k]
        if len(orden):
            metricas.RAG_SCORE.observe(float(max(scores[orden[0]], 0)))
        res = [Fragmento(**{**vars(self.fragmentos[i]), "score": round(float(scores[i]), 4)})
               for i in orden if scores[i] >= self.min_score]
        if not res:
            metricas.RAG_SIN_CONTEXTO.inc()
        return res

    def por_id(self, articulo_id: str) -> Fragmento | None:
        """Recuperación EXACTA por artículo: la usa el agente para traer el texto de las reglas que activó una guarda."""
        f = self._por_id.get(articulo_id)
        return Fragmento(**{**vars(f), "score": 1.0}) if f else None
