"""Mide precision@k, hit@k, MRR y abstencion sobre el set de oro del corpus activo.

Uso: python -m eval.eval_rag --proveedor hash
"""
from __future__ import annotations

import argparse
import json
import sys

from app.config import DATA_DIR, ConfigError, Settings
from app.embeddings import HashEmbedder, crear_embedder
from app.ingesta import construir_indice, indice_vigente
from app.rag import RAG


def _es_relevante(fragmento, fuentes: list[dict]) -> bool:
    for fuente in fuentes:
        if fragmento.documento.casefold() != fuente["documento"].casefold():
            continue
        if any(termino.casefold() in fragmento.texto.casefold()
               for termino in fuente["contiene"]):
            return True
    return False


def medir(rag: RAG, oro: list[dict], k: int) -> dict:
    recuperados = aciertos = respuestas = abstenciones = 0
    relevantes_total = recuperados_answerable = 0
    reciprocal_rank = 0.0
    evaluables = sum(caso["answerable"] for caso in oro)
    sin_respuesta = len(oro) - evaluables
    for caso in oro:
        resultados = rag.buscar(caso["pregunta"], k=k)
        relevantes = [i for i, fragmento in enumerate(resultados, 1)
                      if _es_relevante(fragmento, caso["fuentes_esperadas"])]
        recuperados += len(resultados)
        respuestas += bool(resultados)
        if caso["answerable"]:
            relevantes_total += len(relevantes)
            recuperados_answerable += len(resultados)
            if relevantes:
                aciertos += 1
                reciprocal_rank += 1 / relevantes[0]
        elif not resultados:
            abstenciones += 1
    return {
        "k": k,
        "precision": relevantes_total / max(1, recuperados_answerable),
        "hit_rate": aciertos / max(1, evaluables),
        "mrr": reciprocal_rank / max(1, evaluables),
        "abstention_accuracy": abstenciones / max(1, sin_respuesta),
        "coverage": respuestas / max(1, len(oro)),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proveedor", choices=("hash", "openai"))
    parser.add_argument("--k", type=int)
    parser.add_argument("--detalle", action="store_true", help="Muestra los fragmentos recuperados por pregunta.")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.proveedor:
        settings.embeddings_provider = args.proveedor
    embedder = HashEmbedder() if settings.embeddings_provider == "hash" else crear_embedder(settings)
    if not indice_vigente(settings, embedder):
        resultado = construir_indice(settings, embedder)
        print(f"Indice reindexado: {resultado['fragmentos']} fragmentos, {resultado['dim']} dimensiones.")
    rag = RAG(settings.indice_path, embedder, settings.rag_min_score, settings.rag_top_k)
    oro = json.loads((DATA_DIR / "rag_gold.json").read_text(encoding="utf-8"))
    k = args.k or settings.rag_top_k
    actual = medir(rag, oro, k)
    print(f"Proveedor: {embedder.nombre} | k={k} | umbral={rag.min_score:.2f}")
    print(f"Precision@{k}: {actual['precision']:.3f}")
    print(f"Hit@{k}: {actual['hit_rate']:.3f} | MRR: {actual['mrr']:.3f}")
    print(f"Exactitud de abstencion: {actual['abstention_accuracy']:.3f} | cobertura: {actual['coverage']:.3f}")
    if args.detalle:
        print("\nDetalle:")
        for caso in oro:
            resultados = rag.buscar(caso["pregunta"], k=k)
            relevantes = any(_es_relevante(f, caso["fuentes_esperadas"]) for f in resultados)
            correcto = relevantes if caso["answerable"] else not resultados
            print(f"  {'OK' if correcto else 'MAL'} | {caso['pregunta']}")
            for f in resultados[:2]:
                marca = "*" if _es_relevante(f, caso["fuentes_esperadas"]) else "-"
                print(f"    {marca} {f.score:.3f} {f.documento} | {f.ubicacion} | {f.texto[:140]}")
    if args.k is None:
        print("\nBarrido de top-k (umbral actual):")
        for top_k in (1, 2, 3, 4, 5, 6):
            m = medir(rag, oro, top_k)
            print(f"  k={top_k} precision={m['precision']:.3f} hit={m['hit_rate']:.3f} "
                  f"mrr={m['mrr']:.3f} abstencion={m['abstention_accuracy']:.3f}")
        print("\nMatriz precision/hit/abstencion por umbral y top-k:")
        for umbral in (0.15, 0.25, 0.35, 0.50, 0.60):
            rag.min_score = umbral
            for top_k in (1, 2, 3, 4):
                m = medir(rag, oro, top_k)
                print(f"  umbral={umbral:.2f} k={top_k} "
                      f"precision={m['precision']:.3f} hit={m['hit_rate']:.3f} "
                      f"abstencion={m['abstention_accuracy']:.3f}")
        rag.min_score = settings.rag_min_score
    print("\nBarrido de umbral (precision / hit / abstencion):")
    for umbral in (0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, 0.60):
        rag.min_score = umbral
        m = medir(rag, oro, k)
        print(f"  {umbral:.2f}  {m['precision']:.3f}  {m['hit_rate']:.3f}  {m['abstention_accuracy']:.3f}")


if __name__ == "__main__":
    try:
        main()
    except ConfigError as e:
        sys.exit(f"Configuracion: {e}")
