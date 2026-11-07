"""Ejecuta los comandos de la guía y guarda su salida REAL en _guide/outputs/ (build.py la inyecta con {{OUT:nombre}}).

Uso (desde la raíz del laboratorio, con el entorno activo):
    python _guide/capture.py             pruebas y scripts (sin red, sin claves)
    python _guide/capture.py --docker    además: estado del stack y carga de prueba (requiere "docker compose up -d")

Se captura en MODO SIN CLAVES (router hash, LLM mock, embeddings hash) para que la guía sea reproducible y no gaste
dinero. La guía lo indica en cada salida; las salidas con Jev/OpenAI reales dependen de tus claves.
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

LAB = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "outputs"

ENV = {**os.environ, "PYTHONUTF8": "1", "ROUTER_PROVIDER": "hash", "LLM_PROVIDER": "mock", "EMBEDDINGS_PROVIDER": "hash",
       "TYPESAFE_API_KEY": "", "OPENAI_API_KEY": ""}    # variables vacías GANAN sobre tu .env (override=False)


def run(args: list[str], py: bool = True) -> str:
    cmd = [sys.executable, *args] if py else args
    p = subprocess.run(cmd, cwd=LAB, env=ENV, capture_output=True, text=True, encoding="utf-8")
    return ((p.stdout + p.stderr).replace("\r\n", "\n")).rstrip("\n") + "\n"


def guardar(nombre: str, texto: str) -> None:
    (OUT / f"{nombre}.txt").write_text(texto, encoding="utf-8", newline="\n")
    print(f"  {nombre}.txt  ({len(texto.splitlines())} líneas)")


def main() -> None:
    docker = "--docker" in sys.argv
    if not docker:
        shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)

    if not docker:
        for nombre, archivo in [("t_config", "test_config"), ("t_rag", "test_rag"), ("t_router", "test_router"),
                                ("t_guardas", "test_herramientas_guardas"), ("t_llm_agente", "test_llm_agente"),
                                ("t_db", "test_db"), ("t_api", "test_api"), ("t_higiene", "test_windows_hygiene"),
                                ("t_privacidad", "test_privacidad"), ("t_chat", "test_chat")]:
            guardar(nombre, run(["-m", "pytest", f"tests/{archivo}.py"]))
        guardar("t_todo", run(["-m", "pytest"]))
        guardar("pdf", run(["-m", "rules.generar_pdf"]))
        guardar("ingesta", run(["-m", "app.ingesta"]))
        guardar("ingesta_si_falta", run(["-m", "app.ingesta", "--si-falta"]))
        guardar("eval_hash", run(["-m", "eval.eval_router", "--proveedor", "hash"]))
        guardar("verificar_sin_claves", run(["-m", "scripts.verificar_claves"]))
        (LAB / "data" / "indice.npz").unlink(missing_ok=True)       # el índice real lo crea el alumno con SUS embeddings
    else:
        guardar("compose_ps", run(["docker", "compose", "ps", "--format", "table {{.Service}}\t{{.Status}}\t{{.Ports}}"], py=False))
        guardar("loadgen", run(["-m", "loadgen.generar_carga", "--n", "12"]))
        time.sleep(1)
    print("OK -> _guide/outputs/")


if __name__ == "__main__":
    main()
