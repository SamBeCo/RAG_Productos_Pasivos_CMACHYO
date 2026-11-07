"""Paso 11: ¿qué tan bien enruta? Exactitud del router sobre un set de oro (data/router_gold.json).

Uso:   python -m eval.eval_router                      (el ROUTER_PROVIDER de tu .env)
       python -m eval.eval_router --proveedor hash     (jev | embeddings | hash)

Las frases del set de oro NO son los ejemplos de data/rutas.json: medir con los mismos ejemplos daría 100% falso.
El set es pequeño y escrito manualmente. Sirve para comparar proveedores y elegir un umbral razonable, no para
garantizar calidad. Con jev/embeddings se hace una llamada real por caso y el costo depende del tamaño del set.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from app.config import DATA_DIR, ConfigError, Settings
from app.embeddings import crear_embedder
from app.router import EmbeddingRouter, JevRouter, cargar_rutas


def crear(proveedor: str, settings: Settings):
    rutas = cargar_rutas()
    if proveedor == "jev":
        return JevRouter(settings, rutas)
    if proveedor == "hash":
        settings.embeddings_provider = "hash"
    return EmbeddingRouter(rutas, crear_embedder(settings), settings.router_min_score)


def main(argv: list[str]) -> None:
    settings = Settings()
    proveedor = argv[argv.index("--proveedor") + 1] if "--proveedor" in argv else settings.router_provider
    if proveedor == "embeddings":
        settings.embeddings_provider = "openai"
    elif proveedor == "hash":
        settings.embeddings_provider = "hash"
        settings.llm_provider = "mock"
    settings.router_provider = proveedor
    settings.validar()
    router = crear(proveedor, settings)
    oro = json.loads((DATA_DIR / "router_gold.json").read_text(encoding="utf-8"))

    filas, aciertos = [], 0
    for caso in oro:
        r = router.enrutar(caso["texto"])
        ok = r.ruta == caso["ruta"]
        aciertos += ok
        crudo = max(r.probabilidades, key=r.probabilidades.get) if r.probabilidades else r.ruta   # antes del umbral
        filas.append((ok, caso["ruta"], r.ruta, crudo, r.confianza, caso["texto"]))
        print(f"{'OK ' if ok else 'MAL'}  {r.confianza:5.2f}  esperado={caso['ruta']:<19} obtenido={r.ruta:<19} {caso['texto'][:60]}")

    print(f"\nProveedor: {proveedor} ({getattr(router, 'modelo', '') or router.embedder.nombre})")
    print(f"Exactitud: {aciertos}/{len(oro)} = {aciertos / len(oro):.0%}")
    errores = Counter((esp, obt) for ok, esp, obt, *_ in filas if not ok)
    if errores:
        print("Confusiones (esperado -> obtenido):")
        for (esp, obt), n in errores.most_common():
            print(f"  {esp} -> {obt}: {n}")

    minimo_actual = settings.router_min_confidence if proveedor == "jev" else settings.router_min_score
    print(f"\nBarrido de umbral (el actual es {minimo_actual}):")
    print("  umbral  exactitud  enviadas a fuera_de_alcance")
    for u in [0.0, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8]:
        rutas = [crudo if (conf >= u or crudo == "fuera_de_alcance") else "fuera_de_alcance" for _, _, _, crudo, conf, _ in filas]
        exact = sum(r == f[1] for r, f in zip(rutas, filas))
        print(f"  {u:6.2f}  {exact / len(filas):9.0%}  {rutas.count('fuera_de_alcance'):>27}")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except ConfigError as e:                       # sin clave: mensaje claro, sin traza de Python
        sys.exit(f"Configuración: {e}")
