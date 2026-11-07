"""Chat del Gestor de Productos Pasivos de Caja Huancayo.

El usuario consulta documentos indexados y el sistema responde con contexto y citas.
"""
from __future__ import annotations

from app import metricas
from app.db import NoExiste
from app.seguridad import detectar_inyeccion

HISTORIAL_MAX = 6          # mensajes previos que recibe el LLM: más contexto = más costo y más ruido
FUERA_DE_ALCANCE_CREDITICIO = ("El Gestor de Productos Pasivos consulta productos y condiciones documentadas de Caja Huancayo. "
                               "No brinda evaluación de crédito ni aprobaciones.")
DERIVAR = ("Esta consulta no corresponde al alcance del Gestor de Productos Pasivos de Caja Huancayo. "
           "Puedes preguntar por cuentas, requisitos, condiciones, plazos, tasas o productos documentados.")


class Chat:
    def __init__(self, router, agente, repo, umbral_inyeccion: float = 0.8):
        self.router, self.agente, self.repo = router, agente, repo
        self.umbral_inyeccion = umbral_inyeccion

    def _validar(self, conversacion_id: int) -> None:
        if not self.repo.existe_conversacion(conversacion_id):
            raise NoExiste

    def historial(self, conversacion_id: int) -> list[dict]:
        """Los últimos turnos, en el formato que recibe el LLM: [{rol, texto}]."""
        return [{"rol": m["rol"], "texto": m["texto"][:600]}
                for m in self.repo.mensajes(conversacion_id)[-HISTORIAL_MAX:]]

    def enviar(self, conversacion_id: int | None, texto: str) -> dict:
        if conversacion_id is None:
            conversacion_id = self.repo.crear_conversacion()
        else:
            self._validar(conversacion_id)
        previos = self.historial(conversacion_id)
        nuevo = self.repo.agregar_mensaje(conversacion_id, "usuario", texto)

        if detectar_inyeccion(texto):
            metricas.INYECCION.inc()
            metricas.CHAT_MENSAJES.labels("fuera_de_alcance").inc()
            meta = {"ruta": "bloqueada_por_seguridad", "inyeccion_sospechosa": True,
                    "bloqueada_por_guarda": True, "accion": "bloqueada_sin_llamar_a_ia"}
            asistente = self.repo.agregar_mensaje(
                conversacion_id, "asistente",
                "No puedo procesar instrucciones para ignorar las reglas o revelar información interna. "
                "La consulta no se envió al modelo. Puedes preguntar por productos pasivos documentados.",
                meta,
            )
            revision = self.repo.crear_revision(conversacion_id, asistente["id"], "Bloqueo determinista de seguridad")
            meta["revision_id"] = revision["id"]
            self.repo.actualizar_meta_mensaje(asistente["id"], meta)
            asistente["meta"] = meta
            metricas.CONSULTAS.labels("bloqueada_por_seguridad").inc()
            metricas.REVISIONES_PENDIENTES.set(len(self.repo.revisiones_pendientes()))
            return {"conversacion_id": conversacion_id, "mensajes": [nuevo, {**asistente, "meta": meta}]}

        ruta = self.router.enrutar(texto, [m["texto"] for m in previos if m["rol"] == "usuario"])
        metricas.CHAT_MENSAJES.labels(ruta.ruta).inc()
        sospechoso = ruta.inyeccion is not None and ruta.inyeccion >= self.umbral_inyeccion
        if sospechoso:
            metricas.INYECCION.inc()
        meta = {"ruta": ruta.ruta, "router": ruta.como_dict(), "inyeccion_sospechosa": sospechoso,
                "bloqueada_por_guarda": sospechoso, "accion": None}

        if sospechoso:
            respuesta = ("No puedo procesar esta consulta porque fue marcada como posible intento de manipulación. "
                         "Se derivó a revisión humana y no se envió al agente.")
            meta["accion"] = "bloqueada_y_enviada_a_revision_humana"
        elif ruta.ruta in {"consulta_ahorros", "consulta_producto", "consulta_benchmark", "comparar_productos"}:
            consultar = (self.agente.comparar_productos if ruta.ruta == "comparar_productos"
                         else self.agente.responder_consulta)
            r = consultar(texto, previos)
            meta.update(consulta=r["consulta"], llm_error=r["llm_error"], estado=r.get("estado"),
                        motivo=r.get("motivo"), reservas=r.get("reservas", []),
                        cifras_sin_grounding=r.get("cifras_sin_grounding", []),
                        citas=r.get("citas") or [x for x in r["reglas"] if x["id"] in r["reglas_citadas"]])
            respuesta = r["respuesta"]
            if r.get("estado") == "ABSTENER":
                meta["accion"] = "abstencion_derivada_a_revision_humana"
        else:
            respuesta = DERIVAR
        asistente = self.repo.agregar_mensaje(conversacion_id, "asistente", respuesta, meta)
        if sospechoso or meta.get("estado") == "ABSTENER":
            revision = self.repo.crear_revision(conversacion_id, asistente["id"], meta.get("accion", ""))
            meta["revision_id"] = revision["id"]
            self.repo.actualizar_meta_mensaje(asistente["id"], meta)
            asistente["meta"] = meta
            metricas.REVISIONES_PENDIENTES.set(len(self.repo.revisiones_pendientes()))
        metricas.CONSULTAS.labels(ruta.ruta).inc()
        if meta.get("citas"):
            metricas.RESPUESTAS_CITADAS.inc()
        if meta.get("estado") == "ABSTENER":
            metricas.RESPUESTAS_ABSTENIDAS.inc()
        return {"conversacion_id": conversacion_id, "mensajes": [nuevo, asistente]}
