import json, sys
DS = {"type": "prometheus", "uid": "prom"}
pid = 0
def panel(tipo, titulo, x, y, w, h, exprs, unit=None, desc="", **extra):
    global pid; pid += 1
    p = {"id": pid, "type": tipo, "title": titulo, "description": desc, "datasource": DS,
         "gridPos": {"x": x, "y": y, "w": w, "h": h},
         "targets": [{"refId": chr(65+i), "datasource": DS, "expr": e, "legendFormat": l} for i, (e, l) in enumerate(exprs)],
         "fieldConfig": {"defaults": {}, "overrides": []}, "options": {}}
    if unit: p["fieldConfig"]["defaults"]["unit"] = unit
    if tipo == "timeseries":
        p["fieldConfig"]["defaults"]["custom"] = {"lineWidth": 2, "fillOpacity": 10, "showPoints": "never", "spanNulls": True}
        p["options"] = {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}
    if tipo == "stat":
        p["options"] = {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "none", "graphMode": "none", "textMode": "value"}
    for k, v in extra.items():
        if k == "overrides": p["fieldConfig"]["overrides"] = v
        elif k == "defaults": p["fieldConfig"]["defaults"].update(v)
        else: p[k] = v
    return p

def color(nombre, c):
    return {"matcher": {"id": "byName", "options": nombre}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
ESTADO = [color("APROBAR", "#2e9e5b"), color("OBSERVAR", "#d99a1e"), color("RECHAZAR", "#d6453d"),
          color("APROBADA", "#2e9e5b"), color("RECHAZADA", "#d6453d")]
def row(t, y):
    global pid; pid += 1
    return {"id": pid, "type": "row", "title": t, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []}

R = "$__rate_interval"
panels = [
 row("Resumen", 0),
 panel("stat", "Consultas", 0, 1, 5, 4, [("sum(increase(lab06_chat_mensajes_total[$__range])) + sum(increase(lab06_solicitudes_total[$__range]))", "consultas")],
       desc="Mensajes del chat (incluye las preguntas solo sobre el PDF) + envíos de formulario y escalamientos al analista", defaults={"decimals": 0}),
 panel("stat", "En cola", 5, 1, 4, 4, [("lab06_cola_pendiente", "pendientes")], desc="Solicitudes esperando decisión humana ahora mismo",
       defaults={"decimals": 0, "thresholds": {"mode": "absolute", "steps": [{"color": "text", "value": None}, {"color": "#d99a1e", "value": 5}, {"color": "#d6453d", "value": 15}]}},
       options={"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none", "textMode": "value"}),
 panel("stat", "Acuerdo IA", 9, 1, 5, 4, [("sum(increase(lab06_decision_analista_total{coincide_con_agente=\"si\"}[$__range])) / (sum(increase(lab06_decision_analista_total[$__range])) > 0)", "acuerdo")],
       unit="percentunit", desc="Decisiones humanas que coinciden con el dictamen del agente. OBSERVAR nunca coincide: siempre exige criterio humano. Muestra «—» si todavía no hay decisiones.", defaults={"decimals": 0, "noValue": "—"}),
 panel("stat", "Respaldo", 14, 1, 5, 4, [("sum(increase(lab06_router_respaldo_total[$__range]))", "veces")],
       desc="Veces que Jev falló (clave, límite, caída, red) y se enrutó con embeddings", defaults={"decimals": 0}),
 panel("stat", "Costo (USD)", 19, 1, 5, 4, [("sum(increase(lab06_costo_estimado_usd_total[$__range]))", "USD")],
       unit="currencyUSD", desc="Con los precios por millón de tokens de .env (PRECIO_*). 0 si no los configuraste.", defaults={"decimals": 4}),

 row("Enrutamiento semántico (Jev)", 5),
 panel("timeseries", "Formularios y escalamientos por ruta", 0, 6, 12, 8, [(f"sum by (ruta) (rate(lab06_solicitudes_total[{R}])) * 60", "{{ruta}}")], unit="short",
       desc="Por minuto: envíos de formulario directo (/api/solicitudes) y escalamientos desde el chat. Las preguntas del chat están en la fila «Conversación del asesor»"),
 panel("timeseries", "Confianza del router (p50 y p10)", 12, 6, 12, 8,
       [(f"histogram_quantile(0.5, sum by (le, proveedor) (rate(lab06_router_confianza_bucket[{R}])))", "p50 {{proveedor}}"),
        (f"histogram_quantile(0.1, sum by (le, proveedor) (rate(lab06_router_confianza_bucket[{R}])))", "p10 {{proveedor}}")],
       unit="percentunit", desc="Probabilidad de la ruta elegida (Jev) o similitud coseno (respaldo). El p10 muestra las preguntas más dudosas.",
       defaults={"min": 0, "max": 1}),

 row("Agente de riesgo y aprobación humana", 14),
 panel("timeseries", "Dictamen del agente", 0, 15, 8, 8, [(f"sum by (dictamen) (increase(lab06_dictamen_agente_total[{R}]))", "{{dictamen}}")],
       desc="Después de aplicar las guardas", overrides=ESTADO, defaults={"decimals": 0}),
 panel("timeseries", "Decisiones del analista", 8, 15, 8, 8, [(f"sum by (decision) (increase(lab06_decision_analista_total[{R}]))", "{{decision}}")],
       overrides=ESTADO, defaults={"decimals": 0}),
 panel("timeseries", "Guardas que anularon al LLM", 16, 15, 8, 8, [(f"sum by (regla) (increase(lab06_guarda_anulacion_total[{R}]))", "Art. {{regla}}")],
       desc="El LLM propuso algo más favorable que lo que permiten las reglas duras. Si crece, revisa el prompt o el modelo.", defaults={"decimals": 0}),
 panel("timeseries", "Tiempo hasta la decisión humana (p50 y p90)", 0, 23, 12, 8,
       [(f"histogram_quantile(0.5, sum by (le) (rate(lab06_tiempo_aprobacion_segundos_bucket[{R}])))", "p50"),
        (f"histogram_quantile(0.9, sum by (le) (rate(lab06_tiempo_aprobacion_segundos_bucket[{R}])))", "p90")], unit="s"),
 panel("timeseries", "Similitud del mejor fragmento del PDF (RAG)", 12, 23, 12, 8,
       [(f"histogram_quantile(0.5, sum by (le) (rate(lab06_rag_score_bucket[{R}])))", "p50"),
        (f"histogram_quantile(0.1, sum by (le) (rate(lab06_rag_score_bucket[{R}])))", "p10")],
       unit="percentunit", desc="Si el p10 baja del umbral RAG_MIN_SCORE, hay preguntas que el manual no cubre", defaults={"min": 0, "max": 1}),

 row("Conversación del asesor (chat)", 31),
 panel("timeseries", "Mensajes del chat por ruta", 0, 32, 8, 8, [(f"sum by (ruta) (increase(lab06_chat_mensajes_total[{R}]))", "{{ruta}}")],
       desc="Cada mensaje del asesor, según la ruta que eligió el router", defaults={"decimals": 0}),
 panel("timeseries", "Seguimientos y escalamientos", 8, 32, 8, 8,
       [(f"sum(increase(lab06_chat_reformuladas_total[{R}]))", "preguntas reformuladas"),
        (f"sum by (origen) (increase(lab06_chat_escaladas_total[{R}]))", "escaladas ({{origen}})")],
       desc="Reformuladas: preguntas de seguimiento que se reescribieron con el historial. Escaladas: enviadas al analista desde el chat.",
       defaults={"decimals": 0}),
 panel("timeseries", "Privacidad y manipulación", 16, 32, 8, 8,
       [(f"sum by (tipo) (increase(lab06_pii_enmascarado_total[{R}]))", "enmascarado {{tipo}}"),
        (f"sum(increase(lab06_inyeccion_sospechosa_total[{R}]))", "inyección sospechosa")],
       desc="Datos personales que NO salieron hacia Jev/OpenAI; mensajes que Jev marcó como intento de manipulación", defaults={"decimals": 0}),

 row("Proveedores externos (Jev y OpenAI)", 40),
 panel("timeseries", "Latencia p95 por proveedor", 0, 41, 8, 8,
       [(f"histogram_quantile(0.95, sum by (le, proveedor) (rate(lab06_api_latencia_segundos_bucket[{R}])))", "{{proveedor}}")], unit="s"),
 panel("timeseries", "Tokens por minuto", 8, 41, 8, 8, [(f"sum by (proveedor, tipo) (rate(lab06_tokens_total[{R}])) * 60", "{{proveedor}} {{tipo}}")], unit="short"),
 panel("timeseries", "Errores de proveedores", 16, 41, 8, 8, [(f"sum by (proveedor, tipo) (increase(lab06_api_errores_total[{R}]))", "{{proveedor}} {{tipo}}")],
       defaults={"decimals": 0}),
]
dash = {"uid": "lab06", "title": "Lab 06 · Asesor → Jev → Agente de riesgo → Analista", "tags": ["lab06", "utec"],
        "timezone": "browser", "schemaVersion": 41, "version": 1, "refresh": "10s", "time": {"from": "now-30m", "to": "now"},
        "panels": panels, "templating": {"list": []}, "annotations": {"list": []}, "editable": True}
open(sys.argv[1], "w", encoding="utf-8", newline="\n").write(json.dumps(dash, ensure_ascii=False, indent=2) + "\n")
print(len(panels), "paneles")
