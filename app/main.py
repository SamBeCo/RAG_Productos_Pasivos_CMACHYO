"""API del Gestor de Productos Pasivos de Caja Huancayo.

    GET  /                             interfaz del chat
    POST /api/chat                     consulta al chat con RAG
    POST /api/chat/nueva               nueva conversación
    GET  /api/chat/{id}?desde=N        mensajes nuevos de una conversación
    POST /api/solicitudes              consulta directa (compatibilidad con pruebas de integración)
    GET  /api/solicitudes/{id}         detalle de una respuesta
    GET  /metrics  ·  GET /health
"""
from __future__ import annotations

import asyncio
from io import BytesIO
import json
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app import metricas
from app.agente_ahorro import AgenteRiesgo
from app.config import WEB_DIR, Settings
from app.conversacion import Chat
from app.db import NoExiste, Repositorio, RevisionExistente, YaDecidida
from app.embeddings import EmbeddingError, HashEmbedder, OpenAIEmbedder, crear_embedder
from app.ingesta import construir_indice
from app.llm import crear_llm
from app.modelos import DecisionRevision, MensajeChat, Solicitud, SolicitudRevision
from app.rag import RAG
from app.router import crear_router

MENSAJE_DERIVACION = ("Esta consulta no corresponde a productos o condiciones de ahorro de Caja Huancayo. "
                      "Puedes preguntar por cuentas, plazos, requisitos, tasas o condiciones documentadas.")


@dataclass
class Servicios:
    settings: Settings
    router: object
    agente: AgenteRiesgo
    repo: Repositorio
    chat: Chat | None = None

    def __post_init__(self):
        if self.chat is None:
            self.chat = Chat(self.router, self.agente, self.repo, self.settings.inyeccion_umbral)


def _embedder_compatible(settings: Settings, preferido):
    if not settings.indice_path.exists():
        return preferido
    try:
        with np.load(settings.indice_path) as z:
            nombre = str(z["embedder"])
    except Exception:
        return preferido
    if nombre == preferido.nombre:
        return preferido
    if nombre.startswith("hash-"):
        return HashEmbedder(dim=int(nombre.split("-")[-1]))
    if nombre.startswith("openai-") and settings.openai_api_key:
        return OpenAIEmbedder(settings)
    return preferido


def construir_servicios(settings: Settings | None = None) -> Servicios:
    settings = settings or Settings()
    settings.validar()
    embedder = _embedder_compatible(settings, crear_embedder(settings))
    rag = RAG(settings.indice_path, embedder, settings.rag_min_score, settings.rag_top_k)
    return Servicios(settings, crear_router(settings, embedder), AgenteRiesgo(rag, crear_llm(settings), settings.pdf_path),
                     Repositorio(settings.db_path))


def vista_consulta(f: dict) -> dict:
    """Vista simplificada para el chat del asistente informativo."""
    r = f["resultado"]
    base = {"id": f["id"], "estado": f["estado"], "ruta": f["ruta"],
            "router": {k: f["enrutamiento"].get(k) for k in ("proveedor", "confianza", "modelo", "bajo_umbral")}}
    if f["estado"] == "RESPONDIDA":
        return {**base, "respuesta": r["respuesta"], "citas": [x for x in r.get("reglas", []) if x["id"] in r.get("reglas_citadas", [])]}
    return {**base, "respuesta": r.get("respuesta", "Consulta atendida en el contexto de ahorro de Caja Huancayo.")}


def create_app(servicios: Servicios | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.s = servicios or construir_servicios()
        metricas.inicializar_series()
        metricas.COLA_PENDIENTE.set(app.state.s.repo.contar_pendientes())
        metricas.REVISIONES_PENDIENTES.set(len(app.state.s.repo.revisiones_pendientes()))
        metricas.DOCUMENTOS_INDEXADOS.set(len({f.documento for f in app.state.s.agente.rag.fragmentos}))
        metricas.FRAGMENTOS_INDEXADOS.set(len(app.state.s.agente.rag.fragmentos))
        yield

    app = FastAPI(title="Caja Huancayo | Gestor de Productos Pasivos", lifespan=lifespan)

    def svc(request: Request) -> Servicios:
        return request.app.state.s

    def admin_auth(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
        token = request.app.state.s.settings.admin_token
        if not token:
            raise HTTPException(503, "El portal administrador está deshabilitado: configura ADMIN_TOKEN.")
        if not x_admin_token or not secrets.compare_digest(x_admin_token, token):
            raise HTTPException(401, "Token de administrador inválido.")

    def reindexar(s: Servicios) -> dict:
        inicio = time.perf_counter()
        datos = construir_indice(s.settings, s.agente.rag.embedder)
        nuevo_rag = RAG(s.settings.indice_path, s.agente.rag.embedder,
                        s.settings.rag_min_score, s.settings.rag_top_k)
        s.agente.rag = nuevo_rag
        s.agente._guardas = None
        metricas.INGESTA_LATENCIA.observe(time.perf_counter() - inicio)
        metricas.DOCUMENTOS_INDEXADOS.set(len({f.documento for f in nuevo_rag.fragmentos}))
        metricas.FRAGMENTOS_INDEXADOS.set(len(nuevo_rag.fragmentos))
        return datos

    @app.get("/", include_in_schema=False)
    def pagina_principal():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/admin", include_in_schema=False)
    def pagina_administrador():
        return FileResponse(WEB_DIR / "admin.html")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/admin/documentos", dependencies=[Depends(admin_auth)])
    def listar_documentos(s: Servicios = Depends(svc)):
        documentos: dict[str, dict] = {}
        for f in s.agente.rag.fragmentos:
            nombre = f.documento or "Fuente sin nombre"
            datos = documentos.setdefault(nombre, {"nombre": nombre, "fragmentos": 0, "referencias": []})
            datos["fragmentos"] += 1
            if len(datos["referencias"]) < 3:
                datos["referencias"].append(f.ubicacion or f.titulo)
        return {"documentos": sorted(documentos.values(), key=lambda d: d["nombre"].lower()),
                "total_fragmentos": len(s.agente.rag.fragmentos)}

    @app.post("/api/admin/documentos", dependencies=[Depends(admin_auth)])
    def cargar_documento(archivo: UploadFile = File(...), s: Servicios = Depends(svc)):
        nombre_original = (archivo.filename or "").replace("\\", "/").split("/")[-1].strip()
        nombre_seguro = re.sub(r"[^A-Za-z0-9._ -]", "_", nombre_original)[:120]
        if not nombre_seguro or Path(nombre_seguro).suffix.lower() != ".pdf":
            raise HTTPException(415, "Solo se admiten archivos PDF.")
        contenido = bytearray()
        while bloque := archivo.file.read(1024 * 1024):
            contenido.extend(bloque)
            if len(contenido) > s.settings.upload_max_bytes:
                raise HTTPException(413, f"El PDF supera el límite de {s.settings.upload_max_bytes} bytes.")
        if not contenido.startswith(b"%PDF-"):
            raise HTTPException(422, "El archivo no tiene una cabecera PDF válida.")
        try:
            pdf = PdfReader(BytesIO(contenido))
            if not pdf.pages or not any((p.extract_text() or "").strip() for p in pdf.pages):
                raise HTTPException(422, "El PDF está vacío, escaneado o no contiene texto extraíble.")
        except HTTPException:
            raise
        except (PdfReadError, ValueError, OSError) as e:
            raise HTTPException(422, f"No se pudo leer el PDF: {type(e).__name__}.") from e

        s.settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        ruta = s.settings.uploads_dir / f"{uuid.uuid4().hex}_{nombre_seguro}"
        with ruta.open("xb") as destino:
            destino.write(contenido)
        reindexado = False
        try:
            resultado = reindexar(s)
            reindexado = True
        except (EmbeddingError, PdfReadError, OSError, ValueError) as e:
            raise HTTPException(502, f"No se pudo actualizar el índice: {type(e).__name__}: {e}") from e
        finally:
            if not reindexado and ruta.exists():
                ruta.unlink()
        metricas.DOCUMENTOS_CARGADOS.inc()
        return {"mensaje": "PDF cargado e indexado.", "fuente": nombre_seguro, **resultado}

    @app.post("/api/admin/indexar", dependencies=[Depends(admin_auth)])
    def reindexar_documentos(s: Servicios = Depends(svc)):
        try:
            resultado = reindexar(s)
        except (EmbeddingError, PdfReadError, OSError, ValueError) as e:
            raise HTTPException(502, f"No se pudo reindexar: {type(e).__name__}: {e}") from e
        return {"mensaje": "Corpus reindexado.", **resultado}

    @app.get("/api/admin/revisiones", dependencies=[Depends(admin_auth)])
    def revisiones_pendientes(s: Servicios = Depends(svc)):
        return {"revisiones": s.repo.revisiones_pendientes()}

    @app.post("/api/admin/revisiones/{id_}", dependencies=[Depends(admin_auth)])
    def resolver_revision(id_: int, decision: DecisionRevision, s: Servicios = Depends(svc)):
        if decision.decision == "EDITADA" and not (decision.respuesta_final or "").strip():
            raise HTTPException(422, "Una respuesta editada requiere respuesta_final.")
        try:
            resultado = s.repo.resolver_revision(
                id_, decision.decision, decision.revisor, decision.comentario, decision.respuesta_final,
            )
        except NoExiste:
            raise HTTPException(404, f"No existe la revisión {id_}.") from None
        except YaDecidida as e:
            raise HTTPException(409, str(e)) from e
        metricas.REVISIONES_RESUELTAS.labels(decision.decision).inc()
        metricas.REVISIONES_PENDIENTES.set(len(s.repo.revisiones_pendientes()))
        return resultado

    @app.post("/api/solicitudes")
    def crear_solicitud(sol: Solicitud, s: Servicios = Depends(svc)):
        """Endpoint de compatibilidad usado en pruebas de integración. Recibe Solicitud (formulario ficticio)
        y responde con la consulta RAG sobre ahorros; no evalúa riesgo crediticio."""
        ruta = s.router.enrutar(sol.pregunta)
        if ruta.inyeccion is not None and ruta.inyeccion >= s.settings.inyeccion_umbral:
            metricas.INYECCION.inc()
        metricas.SOLICITUDES.labels(ruta.ruta).inc()
        if ruta.ruta in {"consulta_ahorros", "consulta_producto", "consulta_benchmark", "comparar_productos"}:
            consultar = s.agente.comparar_productos if ruta.ruta == "comparar_productos" else s.agente.responder_consulta
            estado, resultado = "RESPONDIDA", consultar(sol.pregunta)
        else:
            estado, resultado = "DERIVADA", {"respuesta": MENSAJE_DERIVACION}
        id_ = s.repo.crear(estado, ruta.ruta, sol.model_dump(), ruta.como_dict(), resultado)
        metricas.COLA_PENDIENTE.set(s.repo.contar_pendientes())
        return vista_consulta(s.repo.obtener(id_))

    @app.get("/api/solicitudes/{id_}")
    def ver_solicitud(id_: int, s: Servicios = Depends(svc)):
        try:
            return vista_consulta(s.repo.obtener(id_))
        except NoExiste:
            raise HTTPException(404, f"No existe la solicitud {id_}") from None

    @app.post("/api/chat")
    def chat_enviar(m: MensajeChat, s: Servicios = Depends(svc)):
        try:
            return s.chat.enviar(m.conversacion_id, m.mensaje)
        except NoExiste:
            raise HTTPException(404, f"No existe la conversación {m.conversacion_id}") from None

    @app.post("/api/chat/{conversacion_id}/revisiones")
    def solicitar_revision(conversacion_id: int, solicitud: SolicitudRevision, s: Servicios = Depends(svc)):
        try:
            revision = s.repo.crear_revision(conversacion_id, solicitud.mensaje_id, solicitud.motivo)
        except NoExiste:
            raise HTTPException(404, "No existe la respuesta seleccionada en esta conversación.") from None
        except RevisionExistente as e:
            raise HTTPException(409, str(e)) from e
        metricas.REVISIONES_PENDIENTES.set(len(s.repo.revisiones_pendientes()))
        return {"mensaje": "La respuesta quedó en la cola de revisión humana.", "revision_id": revision["id"]}

    @app.post("/api/chat/stream")
    async def chat_stream(m: MensajeChat, s: Servicios = Depends(svc)):
        try:
            resultado = s.chat.enviar(m.conversacion_id, m.mensaje)
        except NoExiste:
            raise HTTPException(404, f"No existe la conversación {m.conversacion_id}") from None

        texto = resultado["mensajes"][1]["texto"]

        async def gen():
            yield "data: " + json.dumps({"type": "start", "conversacion_id": resultado["conversacion_id"]}, ensure_ascii=False) + "\n\n"
            partes = texto.split()
            if not partes:
                partes = [""]
            for i, parte in enumerate(partes):
                delta = (parte + (" " if i < len(partes) - 1 else ""))
                await asyncio.sleep(0.03)
                yield "data: " + json.dumps({"type": "chunk", "conversacion_id": resultado["conversacion_id"], "delta": delta}, ensure_ascii=False) + "\n\n"
            yield "data: " + json.dumps({"type": "done", "conversacion_id": resultado["conversacion_id"], "mensajes": resultado["mensajes"]}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/chat/nueva")
    def chat_nueva(s: Servicios = Depends(svc)):
        return {"conversacion_id": s.repo.crear_conversacion()}

    @app.get("/api/chat/{id_}")
    def chat_leer(id_: int, desde: int = Query(0, ge=0), s: Servicios = Depends(svc)):
        if not s.repo.existe_conversacion(id_):
            raise HTTPException(404, f"No existe la conversación {id_}")
        return {"conversacion_id": id_, "mensajes": s.repo.mensajes(id_, desde)}

    return app


app = create_app()
