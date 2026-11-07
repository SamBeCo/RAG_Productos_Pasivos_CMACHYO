"""Paso 11: prueba de humo de las APIs REALES. Hace 3 llamadas mínimas (costo: fracciones de centavo).

Uso:   python -m scripts.verificar_claves

    1. Jev        → enruta una frase y muestra la ruta, las probabilidades y la versión del modelo
    2. OpenAI LLM → pide un JSON con esquema estricto
    3. OpenAI embeddings → embebe una frase y muestra la dimensión

Ejecútalo ANTES de levantar la aplicación: si una clave está mal, aquí lo ves en 5 segundos con un mensaje claro.
Nunca imprime las claves: solo sus últimos 4 caracteres.
"""
from __future__ import annotations

import sys
import time

from app.config import Settings


def oculto(clave: str) -> str:
    return f"…{clave[-4:]}" if len(clave) > 8 else "(vacía o muy corta)"


def probar(nombre: str, fn) -> bool:
    print(f"\n[{nombre}]")
    t0 = time.perf_counter()
    try:
        fn()
    except Exception as e:          # noqa: BLE001 - aquí queremos mostrar cualquier fallo, con su tipo
        print(f"  FALLÓ ({type(e).__name__}): {str(e)[:400]}")
        return False
    print(f"  OK en {time.perf_counter() - t0:.2f} s")
    return True


def main() -> int:
    s = Settings()
    print(f"TYPESAFE_API_KEY {oculto(s.typesafe_api_key)} · OPENAI_API_KEY {oculto(s.openai_api_key)} · OPENAI_MODEL {s.openai_model}")
    resultados = []

    def jev():
        from app.router import JevRouter, cargar_rutas
        r = JevRouter(s, cargar_rutas()).enrutar("¿Mi cliente con calificación Normal califica para un crédito de 10 mil?")
        print(f"  modelo={r.modelo}  ruta={r.ruta}  confianza={r.confianza}")
        print(f"  probabilidades={r.probabilidades}")

    def llm():
        from app.llm import ESQUEMA_RESPUESTA, OpenAILLM
        r = OpenAILLM(s).generar("Responde en español con un saludo breve.", {"pregunta_del_asesor": "Hola"},
                                 ESQUEMA_RESPUESTA, "respuesta")
        print(f"  modelo={r.modelo}  tokens entrada/salida={r.input_tokens}/{r.output_tokens}")
        print(f"  datos={r.datos}")

    def emb():
        from app.embeddings import OpenAIEmbedder
        m = OpenAIEmbedder(s).embed(["relación cuota ingreso"])
        print(f"  modelo={s.openai_embedding_model}  dimensión={m.shape[1]}")

    if s.typesafe_api_key:
        resultados.append(probar("1. Jev (TypeSafe)", jev))
    else:
        print("\n[1. Jev (TypeSafe)] omitido: TYPESAFE_API_KEY vacío")
    if s.openai_api_key:
        resultados.append(probar("2. OpenAI LLM (Responses API)", llm))
        resultados.append(probar("3. OpenAI embeddings", emb))
    else:
        print("\n[2-3. OpenAI] omitido: OPENAI_API_KEY vacío")
    if not resultados:
        print("\nResultado: no hay claves configuradas. Completa TYPESAFE_API_KEY y OPENAI_API_KEY en .env (paso 2)")
        return 1
    print("\nResultado:", "TODO OK" if all(resultados) else "HAY FALLOS (revisa los mensajes de arriba)")
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
