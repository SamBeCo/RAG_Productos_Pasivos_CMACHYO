"""Paso 3: las métricas que Prometheus lee en GET /metrics y que Grafana dibuja.

Convención de nombres de Prometheus: `<sistema>_<qué>_<unidad>` y `_total` para contadores.
Todas llevan el prefijo `lab06_` para no mezclarse con otras aplicaciones en el mismo Prometheus.

Cuidado con la CARDINALIDAD: cada combinación de etiquetas es una serie temporal nueva. Por eso las etiquetas son
valores de una lista cerrada (ruta, dictamen, proveedor…) y NUNCA el DNI, el id de la solicitud o el texto libre.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

RUTAS = ["evaluacion_credito", "consulta_producto", "consulta_ahorros", "comparar_productos", "fuera_de_alcance"]
DICTAMENES = ["APROBAR", "OBSERVAR", "RECHAZAR"]
DECISIONES = ["APROBADA", "RECHAZADA"]
PROVEEDORES_API = ["jev", "openai_llm", "openai_emb"]

PROB = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]

SOLICITUDES = Counter("lab06_solicitudes_total", "Solicitudes recibidas del asesor, por ruta", ["ruta"])
ROUTER_CONFIANZA = Histogram("lab06_router_confianza", "Confianza de la ruta elegida (Jev: probabilidad; embeddings: coseno)",
                             ["proveedor"], buckets=PROB)
ROUTER_RESPALDO = Counter("lab06_router_respaldo_total", "Veces que Jev falló y se usó el router de respaldo", ["motivo"])
RAG_SCORE = Histogram("lab06_rag_score", "Puntuación del mejor fragmento recuperado del corpus documental", buckets=PROB)
RAG_SIN_CONTEXTO = Counter("lab06_rag_sin_contexto_total", "Consultas sin ningún fragmento sobre el umbral")
API_LATENCIA = Histogram("lab06_api_latencia_segundos", "Latencia de cada llamada a un proveedor externo", ["proveedor"],
                         buckets=[0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60])
API_ERRORES = Counter("lab06_api_errores_total", "Errores de proveedores externos", ["proveedor", "tipo"])
TOKENS = Counter("lab06_tokens_total", "Tokens consumidos", ["proveedor", "tipo"])
COSTO = Counter("lab06_costo_estimado_usd_total", "Costo estimado en USD (precios de .env)", ["proveedor"])
DICTAMEN_AGENTE = Counter("lab06_dictamen_agente_total", "Dictamen final del agente (después de las guardas)", ["dictamen"])
GUARDA_ANULA = Counter("lab06_guarda_anulacion_total", "Veces que una guarda endureció la propuesta del LLM", ["regla"])
CITAS_INVALIDAS = Counter("lab06_citas_invalidas_total", "Artículos citados por el LLM que no estaban en el contexto")
DECISION_ANALISTA = Counter("lab06_decision_analista_total", "Decisiones del analista humano",
                            ["decision", "coincide_con_agente"])
CHAT_MENSAJES = Counter("lab06_chat_mensajes_total", "Mensajes del asesor en el chat, por ruta", ["ruta"])
CHAT_REFORMULADAS = Counter("lab06_chat_reformuladas_total", "Preguntas de seguimiento reescritas como consulta autónoma")
CHAT_ESCALADAS = Counter("lab06_chat_escaladas_total", "Conversaciones escaladas al analista de riesgo", ["origen"])
INYECCION = Counter("lab06_inyeccion_sospechosa_total", "Mensajes que Jev marcó como intento de manipular al sistema")
PII_ENMASCARADO = Counter("lab06_pii_enmascarado_total", "Datos personales enmascarados antes de salir a un tercero", ["tipo"])
COLA_PENDIENTE = Gauge("lab06_cola_pendiente", "Solicitudes esperando al analista")
GUARDA_RESPUESTA = Counter("lab06_guarda_respuesta_total", "Estado de la respuesta tras las guardas deterministas",
                            ["estado"])
GUARDA_RESERVAS = Counter("lab06_guarda_reservas_total", "Reservas aplicadas a la respuesta del LLM", ["tipo"])
GUARDA_CIFRAS = Counter("lab06_guarda_cifras_sin_grounding_total", "Cifras de la respuesta que no existen en el corpus")
CITA_PAGINA_CORREGIDA = Counter("lab06_cita_pagina_corregida_total",
                                 "Citas cuya página se corrigió porque el texto citado vive en otra página")
TIEMPO_APROBACION = Histogram("lab06_tiempo_aprobacion_segundos", "Desde que llega la solicitud hasta la decisión humana",
                              buckets=[5, 15, 30, 60, 120, 300, 600, 1800, 3600])
CONSULTAS = Counter("gpp_consultas_total", "Consultas atendidas por el gestor de productos pasivos", ["ruta"])
RESPUESTAS_CITADAS = Counter("gpp_respuestas_citadas_total", "Respuestas publicadas con al menos una referencia")
COMPARACIONES = Counter("gpp_comparaciones_total", "Consultas atendidas por el agente comparador de productos")
RESPUESTAS_ABSTENIDAS = Counter("gpp_respuestas_abstenidas_total", "Respuestas abstendidas por falta de evidencia o guardas")
DOCUMENTOS_INDEXADOS = Gauge("gpp_documentos_indexados", "Fuentes documentales presentes en el índice")
FRAGMENTOS_INDEXADOS = Gauge("gpp_fragmentos_indexados", "Fragmentos documentales presentes en el índice")
DOCUMENTOS_CARGADOS = Counter("gpp_documentos_cargados_total", "PDF cargados mediante el portal administrador")
REVISIONES_PENDIENTES = Gauge("gpp_revisiones_pendientes", "Respuestas pendientes de revisión humana")
REVISIONES_RESUELTAS = Counter("gpp_revisiones_resueltas_total", "Revisiones humanas resueltas", ["decision"])
INGESTA_LATENCIA = Histogram("gpp_ingesta_segundos", "Duración de la reindexación del corpus",
                              buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300])


def inicializar_series() -> None:
    """Un contador que nunca se incrementó NO aparece en /metrics, y Grafana muestra 'No data' en vez de 0.
    Crear las series conocidas en cero hace que los paneles muestren 0 desde el arranque."""
    for r in RUTAS:
        SOLICITUDES.labels(r)
    for d in DICTAMENES:
        DICTAMEN_AGENTE.labels(d)
    for d in DECISIONES:
        for c in ("si", "no"):
            DECISION_ANALISTA.labels(d, c)
    for p in ("jev", "embeddings", "hash"):
        ROUTER_CONFIANZA.labels(p)
    for p in PROVEEDORES_API:
        API_LATENCIA.labels(p)
        COSTO.labels(p)
        for t in ("input", "output"):
            TOKENS.labels(p, t)
    from app.guardas import REGLAS          # import tardío: metricas.py no depende de nada del proyecto al cargarse
    for regla in REGLAS:
        GUARDA_ANULA.labels(regla)
    for r in RUTAS:
        CHAT_MENSAJES.labels(r)
    for r in ("consulta_ahorros", "consulta_producto", "consulta_benchmark", "comparar_productos", "fuera_de_alcance",
              "bloqueada_por_seguridad"):
        CONSULTAS.labels(r)
    for o in ("router", "boton"):
        CHAT_ESCALADAS.labels(o)
    for t in ("email", "ruc", "telefono", "dni", "nombre", "direccion"):
        PII_ENMASCARADO.labels(t)
    for m in ("auth", "validacion", "limite", "servidor", "red"):
        ROUTER_RESPALDO.labels(m)
    for e in ("PUBLICAR", "PUBLICAR_CON_RESERVA", "ABSTENER"):
        GUARDA_RESPUESTA.labels(e)
    for t in ("ficticio_total", "dato_ficticio", "documento_incompleto", "fila_uniforme", "otra"):
        GUARDA_RESERVAS.labels(t)
    for d in ("APROBADA", "EDITADA", "RETIRADA"):
        REVISIONES_RESUELTAS.labels(d)
