"""Paso 5: convertir texto en vectores. Dos implementaciones con la MISMA interfaz.

- OpenAIEmbedder: real (text-embedding-3-small, 1536 dimensiones). Es el que usa la guía.
- HashEmbedder: sin red y sin costo. Hace "hashing" de palabras y trigramas de letras: parecido LÉXICO, no semántico
  ("préstamo" y "crédito" no se parecen para él). Existe para que pytest corra sin clave ni internet.

Ambos devuelven vectores normalizados (norma 1): así el producto punto ES la similitud coseno.
"""
from __future__ import annotations

import time
import unicodedata
import zlib
from typing import Protocol

import numpy as np

from app import metricas
from app.privacidad import enmascarar


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    nombre: str      # se guarda en el índice: si cambias de embedder, el índice viejo deja de servir
    dim: int

    def embed(self, textos: list[str]) -> np.ndarray: ...


def normalizar_filas(m: np.ndarray) -> np.ndarray:
    normas = np.linalg.norm(m, axis=1, keepdims=True)
    return (m / np.where(normas == 0, 1, normas)).astype(np.float32)


def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


class HashEmbedder:
    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.nombre = f"hash-{dim}"

    def _rasgos(self, texto: str) -> list[str]:
        palabras = "".join(c if c.isalnum() else " " for c in sin_tildes(texto)).split()
        rasgos = [f"w:{p}" for p in palabras]
        for p in palabras:
            p = f"<{p}>"
            rasgos += [f"g:{p[i:i + 3]}" for i in range(len(p) - 2)]
        return rasgos

    def embed(self, textos: list[str]) -> np.ndarray:
        m = np.zeros((len(textos), self.dim), dtype=np.float32)
        for fila, texto in enumerate(textos):
            for r in self._rasgos(texto):
                h = zlib.crc32(r.encode("utf-8"))           # crc32 y no hash(): hash() cambia en cada ejecución
                m[fila, h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        return normalizar_filas(m)


class OpenAIEmbedder:
    LOTE = 96
    MAX_TOKENS = 8192 - 512

    def __init__(self, settings, client=None):
        from openai import OpenAI

        self.modelo = settings.openai_embedding_model
        self.nombre = f"openai-{self.modelo}"
        self.dim = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536}.get(self.modelo, 0)
        self.precio = settings.precio_openai_embeddings
        self.client = client or OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_s, max_retries=2)

    def _contar_tokens(self, texto: str) -> int:
        if self.modelo:
            try:
                import tiktoken
                try:
                    encoder = tiktoken.encoding_for_model(self.modelo)
                except KeyError:
                    encoder = tiktoken.get_encoding("cl100k_base")
                return len(encoder.encode(texto))
            except Exception:
                pass
        palabras = len(texto.split())
        bytes_utf8 = len(texto.encode("utf-8"))
        return max(1, max(palabras, bytes_utf8 // 3))

    def embed(self, textos: list[str]) -> np.ndarray:
        import openai

        filas = []
        for i in range(0, len(textos), self.LOTE):
            lote = textos[i:i + self.LOTE]
            entradas = []
            for j, texto in enumerate(lote):
                texto_mascarado = enmascarar(texto)
                tokens = self._contar_tokens(texto_mascarado)
                print(f"[embed] lote={i // self.LOTE} idx={i + j} modelo={self.modelo} tokens={tokens}", flush=True)
                if tokens > self.MAX_TOKENS:
                    raise EmbeddingError(
                        f"OpenAI embeddings rechazó entrada {i + j} ({tokens} tokens > {self.MAX_TOKENS}). "
                        "El fragmento supera el límite del modelo; vuelve a segmentar antes de llamar a la API."
                    )
                entradas.append(texto_mascarado)
            t0 = time.perf_counter()
            try:
                r = self.client.embeddings.create(model=self.modelo, input=entradas)
            except openai.APIError as e:
                metricas.API_ERRORES.labels("openai_emb", type(e).__name__).inc()
                raise EmbeddingError(f"OpenAI embeddings falló: {type(e).__name__}: {e}") from e
            finally:
                metricas.API_LATENCIA.labels("openai_emb").observe(time.perf_counter() - t0)
            tokens = r.usage.prompt_tokens if r.usage else 0
            metricas.TOKENS.labels("openai_emb", "input").inc(tokens)
            metricas.COSTO.labels("openai_emb").inc(tokens * self.precio / 1e6)
            filas += [d.embedding for d in sorted(r.data, key=lambda d: d.index)]
        m = normalizar_filas(np.array(filas, dtype=np.float32))
        self.dim = m.shape[1]
        return m


def crear_embedder(settings) -> Embedder:
    return OpenAIEmbedder(settings) if settings.embeddings_provider == "openai" else HashEmbedder()
