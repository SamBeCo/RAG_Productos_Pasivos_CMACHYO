"""Genera los dashboards de Grafana (JSON) desde Python. Ejecutar:  python grafana/build_dashboards.py

Por qué un generador: el JSON de Grafana es enorme y repetitivo; aquí cada panel es UNA llamada a una función
y los dashboards quedan versionados y revisables en git.
"""
import json
from pathlib import Path

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}
OUT = Path(__file__).resolve().parent / "dashboards"

SVC = 'job="rag-api"'
CHAT = 'stream="chat"'


class Board:
    def __init__(self, uid, title, description, variables=None):
        self.uid, self.title, self.description = uid, title, description
        self.panels, self._id, self.variables = [], 0, variables or []

    def _add(self, p):
        self._id += 1
        p["id"] = self._id
        self.panels.append(p)

    def row(self, title, y):
        self._add({"type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})

    def text(self, title, md, x, y, w, h):
        self._add({"type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "options": {"mode": "markdown", "content": md}})

    def stat(self, title, expr, x, y, w=4, h=4, unit="short", thresholds=None, decimals=None, desc="", mappings=None,
             color_mode="background", graph=True):
        steps = [{"color": c, "value": v} for v, c in (thresholds or [(None, "green")])]
        fc = {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}, "mappings": mappings or []}
        if decimals is not None:
            fc["decimals"] = decimals
        self._add({"type": "stat", "title": title, "description": desc, "datasource": PROM,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": PROM, "expr": expr, "refId": "A", "instant": False}],
                   "fieldConfig": {"defaults": fc, "overrides": []},
                   "options": {"colorMode": color_mode, "graphMode": "area" if graph else "none", "textMode": "auto",
                               "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}})

    def ts(self, title, targets, x, y, w=8, h=8, unit="short", desc="", stack=False, fill=12, minv=None, maxv=None,
           thresholds=None, exemplars=False, legend="list", style="line", soft_max=None):
        tg = []
        for i, t in enumerate(targets):
            expr, leg = t[0], t[1]
            d = {"datasource": PROM, "expr": expr, "legendFormat": leg, "refId": chr(65 + i)}
            if exemplars:
                d["exemplar"] = True
            tg.append(d)
        custom = {"drawStyle": style, "lineWidth": 2, "fillOpacity": fill, "showPoints": "never", "spanNulls": True,
                  "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
        if thresholds:
            custom["thresholdsStyle"] = {"mode": "line"}
        fc = {"unit": unit, "custom": custom}
        if soft_max is not None:
            custom["axisSoftMax"] = soft_max
        if minv is not None:
            fc["min"] = minv
        if maxv is not None:
            fc["max"] = maxv
        if thresholds:
            fc["thresholds"] = {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in thresholds]}
        self._add({"type": "timeseries", "title": title, "description": desc, "datasource": PROM,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h}, "targets": tg,
                   "fieldConfig": {"defaults": fc, "overrides": []},
                   "options": {"legend": {"displayMode": "list" if legend == "list" else "table", "placement": "bottom",
                                          "calcs": [] if legend == "list" else ["lastNotNull", "max"]},
                               "tooltip": {"mode": "multi", "sort": "desc"}}})

    def heatmap(self, title, expr, x, y, w=8, h=8, desc="", unit="short"):
        self._add({"type": "heatmap", "title": title, "description": desc, "datasource": PROM,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": PROM, "expr": expr, "format": "heatmap", "legendFormat": "{{le}}", "refId": "A"}],
                   "fieldConfig": {"defaults": {"custom": {"scaleDistribution": {"type": "linear"}}}, "overrides": []},
                   "options": {"calculate": False, "cellGap": 1, "yAxis": {"axisPlacement": "left", "unit": unit},
                               "color": {"mode": "scheme", "scheme": "Turbo", "fill": "dark-orange", "scale": "exponential",
                                         "exponent": 0.5, "steps": 64, "reverse": False},
                               "rowsFrame": {"layout": "auto"}, "tooltip": {"mode": "single", "yHistogram": False},
                               "legend": {"show": True}}})

    def bargauge(self, title, expr, legend, x, y, w=6, h=8, unit="short", desc=""):
        self._add({"type": "bargauge", "title": title, "description": desc, "datasource": PROM,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": "A", "instant": True}],
                   "fieldConfig": {"defaults": {"unit": unit, "min": 0, "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}}, "overrides": []},
                   "options": {"displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True,
                               "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}})

    def table_prom(self, title, expr, x, y, w=8, h=8, desc="", unit="short"):
        self._add({"type": "table", "title": title, "description": desc, "datasource": PROM,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": PROM, "expr": expr, "format": "table", "instant": True, "refId": "A"}],
                   "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True}}}],
                   "fieldConfig": {"defaults": {"unit": unit}, "overrides": []}, "options": {"showHeader": True}})

    def traces(self, title, traceql, x, y, w=12, h=8, desc=""):
        self._add({"type": "table", "title": title, "description": desc, "datasource": TEMPO,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": TEMPO, "queryType": "traceql", "query": traceql, "limit": 20,
                                "tableType": "traces", "refId": "A"}],
                   "options": {"showHeader": True}, "fieldConfig": {"defaults": {}, "overrides": []}})

    def logs(self, title, logql, x, y, w=12, h=8, desc=""):
        self._add({"type": "logs", "title": title, "description": desc, "datasource": LOKI,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": LOKI, "expr": logql, "queryType": "range", "refId": "A"}],
                   "options": {"showTime": True, "wrapLogMessage": True, "enableLogDetails": True,
                               "sortOrder": "Descending", "dedupStrategy": "none", "prettifyLogMessage": False}})

    def table_loki(self, title, logql, x, y, w=8, h=8, desc=""):
        self._add({"type": "table", "title": title, "description": desc, "datasource": LOKI,
                   "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "targets": [{"datasource": LOKI, "expr": logql, "queryType": "instant", "refId": "A"}],
                   "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": {"Value": "eventos"}}}],
                   "options": {"showHeader": True, "sortBy": [{"displayName": "eventos", "desc": True}]}, "fieldConfig": {"defaults": {}, "overrides": []}})

    def alerts(self, title, x, y, w=24, h=6):
        self._add({"type": "alertlist", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
                   "options": {"datasource": "Prometheus", "viewMode": "list", "groupMode": "default", "maxItems": 20,
                               "sortOrder": 1, "showInstances": True,
                               "stateFilter": {"firing": True, "pending": True, "normal": True, "noData": False, "error": True}}})

    def json(self):
        tmpl = [{"name": n, "label": n, "type": "custom", "multi": True, "includeAll": True, "allValue": ".+",
                 "query": q, "current": {"text": "All", "value": "$__all"}, "options": []} for n, q in self.variables]
        return {"uid": self.uid, "title": self.title, "description": self.description, "tags": ["lab04"],
                "timezone": "browser", "schemaVersion": 41, "version": 1, "editable": True, "refresh": "5s",
                "time": {"from": "now-15m", "to": "now"}, "graphTooltip": 1, "panels": self.panels,
                "templating": {"list": tmpl}, "annotations": {"list": []},
                "links": [{"type": "dashboards", "title": "Lab 04", "tags": ["lab04"], "asDropdown": True,
                           "includeVars": False, "keepTime": True}]}

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{self.uid}.json").write_text(json.dumps(self.json(), indent=1, ensure_ascii=False), encoding="utf-8")


def p95(bucket, by="le", extra="", win="2m"):
    return f"histogram_quantile(0.95, sum by ({by}) (rate({bucket}{{{extra}}}[{win}])))"


def q(bucket, quant, extra="", win="2m"):
    return f"histogram_quantile({quant}, sum by (le) (rate({bucket}{{{extra}}}[{win}])))"



TURNS = 'rag_chat_turns_total'
VALID = 'outcome=~"answered|no_context|error"'

# =============================================================================================
# 1) EXPERIENCIA DEL USUARIO: SLIs del chat
# =============================================================================================
b = Board("rag-overview", "RAG · Experiencia del usuario y SLIs del chat",
          "¿Está recibiendo el usuario buenas respuestas, rápido? Turnos, latencias por etapa, LLM, SSE, trazas y logs.")
b.row("SLIs del chat (lo que siente el usuario)", 0)
b.stat("Turnos / s", f'sum(rate({TURNS}[1m]))', 0, 1, 4, 4, unit="ops", decimals=2, desc="Preguntas por segundo (todas las salidas).")
b.stat("Turnos sin error (5 min)", '1 - lab:chat_error_ratio:rate5m', 4, 1, 4, 4, unit="percentunit", decimals=1,
       thresholds=[(None, "red"), (0.9, "orange"), (0.99, "green")],
       desc="SLI de NEGOCIO. HTTP responde 200 aunque el LLM falle DESPUÉS, dentro del stream: solo esta métrica lo ve. SLO del laboratorio: 99 %.")
b.stat("Sin contexto (5 min)", 'lab:chat_no_context_ratio:rate5m', 8, 1, 4, 4, unit="percentunit", decimals=1,
       thresholds=[(None, "green"), (0.3, "orange"), (0.5, "red")],
       desc="Preguntas sin evidencia suficiente: NO se llama al LLM (ahorra costo y evita alucinar). Un valor alto = corpus incompleto o usuarios preguntando otra cosa.")
b.stat("p95 primer token", 'lab:llm_ttft_p95:rate5m', 12, 1, 4, 4, unit="s", decimals=2, thresholds=[(None, "green"), (1, "orange"), (2, "red")],
       desc="TTFT: cuánto espera el usuario antes de ver la primera palabra. Es LA latencia de un chat en streaming.")
b.stat("p95 turno completo", 'lab:chat_duration_p95:rate5m', 16, 1, 4, 4, unit="s", decimals=2, thresholds=[(None, "green"), (4, "orange"), (6, "red")])
b.stat("Chats abiertos ahora", f'sum(sse_streams_active{{{CHAT}}})', 20, 1, 4, 4, thresholds=[(None, "blue")],
       desc="Conexiones SSE largas de chat en curso: cada una ocupa un socket, un slot del cliente y (con un LLM real) dinero.")
b.row("Turnos", 5)
b.ts("Turnos por resultado", [(f'sum by (outcome) (rate({TURNS}[1m]))', "{{outcome}}")], 0, 6, 8, 8, unit="ops", stack=True,
     desc="answered = respuesta con evidencia · no_context = 'no encuentro' (sin llamar al LLM) · error = falló · client_disconnected = el usuario cortó · invalid = error del cliente.")
b.ts("Tasa de error del chat vs. umbrales de quema del SLO",
     [("lab:chat_error_ratio:rate5m", "errores 5 min"), ("lab:chat_error_ratio:rate1h", "errores 1 h")], 8, 6, 8, 8, unit="percentunit",
     thresholds=[(None, "green"), (0.06, "orange"), (0.144, "red")], minv=0,
     desc="SLO 99 % => presupuesto 1 %. Línea naranja = quema 6x (lenta), roja = 14.4x (rápida). Lanza el escenario 'chaos'.")
b.ts("Duración del turno completo (p50 / p95 / p99)", [(q("rag_chat_duration_seconds_bucket", 0.5, 'outcome="answered"', "5m"), "p50"),
     (q("rag_chat_duration_seconds_bucket", 0.95, 'outcome="answered"', "5m"), "p95"), (q("rag_chat_duration_seconds_bucket", 0.99, 'outcome="answered"', "5m"), "p99")],
     16, 6, 8, 8, unit="s", desc="Pregunta -> último token, solo de turnos respondidos.")
b.row("¿Dónde se va el tiempo? Etapas de un turno", 14)
b.ts("Latencia p95 por etapa", [
     (q("rag_embed_duration_seconds_bucket", 0.95, 'kind="query"'), "1 · embedding de la pregunta"),
     (q("rag_retrieval_duration_seconds_bucket", 0.95), "2 · búsqueda vectorial"),
     (q("rag_llm_ttft_seconds_bucket", 0.95), "3 · LLM hasta el primer token"),
     (q("rag_llm_duration_seconds_bucket", 0.95), "4 · LLM generación completa")], 0, 15, 12, 8, unit="s", exemplars=True,
     desc="Si sube el TTFT del usuario, aquí ves qué etapa cambió. Los rombos son peticiones reales: clic -> su traza en Tempo.")
b.ts("Tiempo por etapa (medias apiladas)", [
     ("sum(rate(rag_embed_duration_seconds_sum{kind=\"query\"}[2m])) / clamp_min(sum(rate(rag_embed_duration_seconds_count{kind=\"query\"}[2m])), 1e-9)", "embedding"),
     ("sum(rate(rag_retrieval_duration_seconds_sum[2m])) / clamp_min(sum(rate(rag_retrieval_duration_seconds_count[2m])), 1e-9)", "búsqueda"),
     ("sum(rate(rag_llm_ttft_seconds_sum[2m])) / clamp_min(sum(rate(rag_llm_ttft_seconds_count[2m])), 1e-9)", "espera del 1.er token")],
     12, 15, 12, 8, unit="s", stack=True, desc="Suma de las esperas ANTES de que el usuario vea texto.")
b.row("LLM", 23)
b.ts("Tiempo hasta el primer token (p50 / p95 / p99) · con exemplars",
     [(q("rag_llm_ttft_seconds_bucket", 0.5), "p50"), (q("rag_llm_ttft_seconds_bucket", 0.95), "p95"), (q("rag_llm_ttft_seconds_bucket", 0.99), "p99")],
     0, 24, 8, 8, unit="s", exemplars=True, thresholds=[(None, "green"), (2, "red")])
b.ts("Ritmo de generación (tokens/s, p50)", [(q("rag_llm_token_rate_per_second_bucket", 0.5), "p50"), (q("rag_llm_token_rate_per_second_bucket", 0.95), "p95")], 8, 24, 8, 8,
     desc="Velocidad a la que el modelo emite tokens una vez que empezó.")
b.ts("Errores del proveedor por tipo", [('sum by (kind, provider) (rate(rag_llm_errors_total[1m]))', "{{provider}} · {{kind}}")], 16, 24, 8, 8, unit="ops", stack=True,
     desc="timeout / rate_limit (TU cuota con el proveedor) / auth / server / other. Un `kind` estable y de pocos valores: apto como etiqueta.")
b.row("Streaming SSE", 32)
b.ts("Streams abiertos por tipo", [('sum by (stream) (sse_streams_active)', "{{stream}}")], 0, 33, 8, 8, stack=True,
     desc="UpDownCounter: +1 al abrir, -1 al cerrar. Una fuga (nunca baja) delata streams que no se liberan.")
b.ts("Tiempo hasta el primer evento SSE (chat)", [(q("sse_time_to_first_event_seconds_bucket", 0.5, CHAT), "p50"), (q("sse_time_to_first_event_seconds_bucket", 0.95, CHAT), "p95")],
     8, 33, 8, 8, unit="s", desc="Llega el evento `meta` casi al instante; lo que importa al usuario es el 1.er `token` (panel de TTFT).")
b.ts("Cierres de stream por motivo", [('sum by (stream, close_reason) (rate(sse_streams_total[1m]))', "{{stream}} · {{close_reason}}")], 16, 33, 8, 8, unit="ops", stack=True,
     desc="completed = todo bien · client_disconnected = el usuario cortó (y el servidor CANCELA la generación) · server_error = fallo interno.")
b.row("Trazas y logs (mismo trace_id en ambos)", 41)
b.traces("Trazas de chat con ERROR (Tempo · TraceQL)", '{ resource.service.name = "rag-api" && name = "rag.turn" && status = error }', 0, 42, 12, 8,
         "El tail sampling conserva SIEMPRE las trazas con error. Clic en un traceID: verás rag.turn -> rag.search / rag.llm.generate.")
b.traces("Turnos lentos (> 3 s)", '{ resource.service.name = "rag-api" && name = "rag.turn" && duration > 3s }', 12, 42, 12, 8)
b.logs("Logs de turnos de chat (sin el texto de la pregunta)", '{service_name="rag-api"} |= "chat_turn"', 0, 50, 24, 9,
       "Cada turno registra outcome, tokens, TTFT y tamaño de la pregunta. NUNCA el texto: podría contener datos personales.")
b.row("Alertas (reglas de Prometheus)", 59)
b.alerts("Estado de alertas", 0, 60)
b.save()

# =============================================================================================
# 2) CALIDAD DE LA RECUPERACIÓN Y BASE VECTORIAL
# =============================================================================================
r = Board("rag-retrieval", "RAG · Calidad de la recuperación y base vectorial",
          "La calidad de un RAG se decide ANTES del LLM: ¿la búsqueda encuentra el fragmento correcto? Además, la salud de PostgreSQL + pgvector.")
r.row("Calidad: ¿la búsqueda encuentra evidencia?", 0)
r.stat("Mediana del mejor score", 'lab:retrieval_top_score_p50:rate5m', 0, 1, 4, 4, decimals=3, thresholds=[(None, "red"), (0.15, "orange"), (0.2, "green")],
       desc="Similitud coseno del MEJOR fragmento por pregunta. Umbral de corte del laboratorio: MIN_SCORE = 0.13.")
r.stat("Sin contexto (5 min)", 'lab:chat_no_context_ratio:rate5m', 4, 1, 4, 4, unit="percentunit", decimals=1, thresholds=[(None, "green"), (0.3, "orange"), (0.5, "red")])
r.stat("👍 sobre total valoraciones", '1 - lab:feedback_down_ratio:rate10m', 8, 1, 4, 4, unit="percentunit", decimals=0, thresholds=[(None, "red"), (0.5, "orange"), (0.7, "green")],
       desc="Señal de calidad DIRECTA del usuario (la más valiosa y la más escasa).")
r.stat("Fragmentos útiles por consulta", 'sum(rate(rag_retrieval_hits_sum[5m])) / clamp_min(sum(rate(rag_retrieval_hits_count[5m])), 1e-9)', 12, 1, 4, 4, decimals=1,
       desc="Media de fragmentos sobre el umbral. 0 = no se llamará al LLM.")
r.stat("Documentos / fragmentos", 'sum(rag_corpus_size{kind="chunks"})', 16, 1, 4, 4, thresholds=[(None, "blue")], desc="Fragmentos totales en pgvector (cache de 30 s).")
r.stat("p95 búsqueda vectorial", q("rag_retrieval_duration_seconds_bucket", 0.95, "", "5m"), 20, 1, 4, 4, unit="s", decimals=4, thresholds=[(None, "green"), (0.05, "orange"), (0.2, "red")])
r.heatmap("Distribución del mejor score de recuperación", 'sum by (le) (increase(rag_retrieval_top_score_bucket{le!="+Inf"}[$__rate_interval]))', 0, 5, 12, 9,
          "Calor cerca de 0 = preguntas sin evidencia. Una distribución BIMODAL (pico bajo y pico alto) es sana: 'sé' y 'no sé'. Un solo pico en el medio: umbral difícil de fijar.", unit="short")
r.ts("Mejor score: p10 / p50 / p90 vs. umbral", [(q("rag_retrieval_top_score_bucket", 0.1, "", "5m"), "p10"), (q("rag_retrieval_top_score_bucket", 0.5, "", "5m"), "p50"),
     (q("rag_retrieval_top_score_bucket", 0.9, "", "5m"), "p90")], 12, 5, 12, 9, minv=0, maxv=1, thresholds=[(None, "red"), (0.13, "green")],
     desc="La línea es MIN_SCORE. Todo lo que queda bajo la línea NO llega al LLM. Si p50 se acerca a la línea, casi todo empieza a rechazarse.")
r.ts("Valoraciones de usuarios", [('sum by (rating) (rate(rag_feedback_total[2m]))', "{{rating}}")], 0, 14, 8, 8, unit="ops", stack=True)
r.ts("Sin contexto vs. 👎 (¿coinciden?)", [("lab:chat_no_context_ratio:rate5m", "sin contexto"), ("lab:feedback_down_ratio:rate10m", "ratio 👎")], 8, 14, 8, 8,
     unit="percentunit", minv=0, maxv=1, desc="Si suben juntos, el problema es de COBERTURA del corpus. Si 👎 sube y sin-contexto no: la recuperación trae fragmentos que no responden.")
r.ts("Embeddings: latencia p95 por tipo", [(q("rag_embed_duration_seconds_bucket", 0.95, 'kind="query"'), "pregunta"), (q("rag_embed_duration_seconds_bucket", 0.95, 'kind="document"'), "documento (lote)")],
     16, 14, 8, 8, unit="s")
r.row("PostgreSQL + pgvector", 22)
r.ts("Latencia por operación (p95)", [('histogram_quantile(0.95, sum by (le, op) (rate(db_query_duration_seconds_bucket[2m])))', "{{op}}")], 0, 23, 12, 8, unit="s",
     desc="Busca aquí la consulta lenta. `search` es la vectorial; `store_chunks` es la inserción transaccional de la ingesta.")
r.ts("Pool de conexiones de la app", [('max by (state) (db_pool_connections)', "{{state}}")], 12, 23, 6, 8,
     desc="idle + en uso = total. `waiting` > 0 = el pool se SATURÓ: peticiones esperan conexión (la alerta PoolDeConexionesSaturado).")
r.ts("Conexiones en PostgreSQL", [('sum(pg_stat_database_numbackends{datname="rag"})', "en uso"), ('max(pg_settings_max_connections)', "máximo")], 18, 23, 6, 8, minv=0)
HIT = 'sum(rate(pg_stat_database_blks_hit{datname="rag"}[2m]))'
READ = 'sum(rate(pg_stat_database_blks_read{datname="rag"}[2m]))'
r.ts("Caché hit ratio", [(f"{HIT} / clamp_min({HIT} + {READ}, 1e-9)", "hit ratio")],
     0, 31, 8, 8, unit="percentunit", minv=0, maxv=1, thresholds=[(None, "red"), (0.9, "green")],
     desc="Si cae bajo ~90 %, el índice HNSW ya no cabe en memoria: cada búsqueda va a disco.")
r.ts("Filas leídas / escritas por segundo", [('sum(rate(pg_stat_database_tup_returned{datname="rag"}[1m]))', "devueltas"), ('sum(rate(pg_stat_database_tup_inserted{datname="rag"}[1m]))', "insertadas"),
     ('sum(rate(pg_stat_database_tup_deleted{datname="rag"}[1m]))', "borradas")], 8, 31, 8, 8, unit="ops")
r.ts("Tamaño de la base de datos", [('max(pg_database_size_bytes{datname="rag"})', "rag")], 16, 31, 8, 8, unit="bytes")
r.alerts("Alertas", 0, 39)
r.save()

# =============================================================================================
# 3) INGESTA Y COSTO
# =============================================================================================
c = Board("rag-ingest-cost", "RAG · Ingesta de documentos y costo de IA",
          "PDF → texto → fragmentos → vectores → PostgreSQL etapa por etapa, y cuánto cuestan los tokens.")
c.row("Ingesta (PDF → pgvector)", 0)
c.stat("Documentos indexados / min", 'sum(rate(rag_ingest_documents_total{outcome="completed"}[5m])) * 60', 0, 1, 4, 4, decimals=1)
c.stat("Fallos de ingesta (5 min)", 'lab:ingest_failure_ratio:rate5m', 4, 1, 4, 4, unit="percentunit", decimals=0, thresholds=[(None, "green"), (0.05, "orange"), (0.2, "red")])
c.stat("Duplicados evitados", 'sum(increase(rag_ingest_documents_total{outcome="duplicate"}[$__range]))', 8, 1, 4, 4, thresholds=[(None, "blue")],
       desc="Idempotencia: subir el MISMO PDF (misma huella SHA-256) no vuelve a gastar embeddings ni duplica fragmentos.")
c.stat("p95 duración de ingesta", q("rag_ingest_document_duration_seconds_bucket", 0.95, 'outcome="completed"', "10m"), 12, 1, 4, 4, unit="s", decimals=2)
c.stat("Fragmentos / s", 'sum(rate(rag_ingest_chunks_total[1m]))', 16, 1, 4, 4, decimals=1)
c.stat("Páginas / s", 'sum(rate(rag_ingest_pages_total[1m]))', 20, 1, 4, 4, decimals=1)
c.ts("Documentos por resultado", [('sum by (outcome) (rate(rag_ingest_documents_total[1m]))', "{{outcome}}")], 0, 5, 8, 8, unit="ops", stack=True)
c.ts("Duración por etapa (p95)", [('histogram_quantile(0.95, sum by (le, stage) (rate(rag_ingest_stage_duration_seconds_bucket[5m])))', "{{stage}}")], 8, 5, 8, 8, unit="s", stack=True,
     desc="extract (pypdf) · chunk · embed (lotes) · store (transacción). El cuello de botella suele ser embed cuando el proveedor es remoto.")
c.ts("Tamaño de PDF subido (p95)", [(q("pdf_upload_size_bytes_bucket", 0.95, "", "5m"), "p95")], 16, 5, 8, 8, unit="bytes")
c.traces("Trazas de ingesta (ingest.run)", '{ resource.service.name = "rag-api" && name = "ingest.run" }', 0, 13, 24, 8,
         "Cada ingesta es UNA traza: ingest.extract -> ingest.chunk -> ingest.embed -> ingest.store.")
c.row("Costo y tokens (estimado con precios de config)", 21)
c.stat("Costo estimado (USD / hora)", 'lab:llm_cost_usd_per_hour:rate5m', 0, 22, 6, 4, decimals=2, thresholds=[(None, "green"), (2, "orange"), (5, "red")],
       desc="Proyección a 1 hora del gasto de los últimos 5 min. Sirve para detectar ANOMALÍAS; la factura real es la del proveedor.")
c.stat("Costo por turno respondido", 'sum(rate(rag_llm_cost_total[5m])) / clamp_min(sum(rate(rag_chat_turns_total{outcome="answered"}[5m])), 1e-9)', 6, 22, 6, 4, unit="currencyUSD", decimals=5)
c.stat("Tokens de entrada por turno", 'sum(rate(rag_llm_tokens_total{direction="input"}[5m])) / clamp_min(sum(rate(rag_chat_turns_total{outcome="answered"}[5m])), 1e-9)', 12, 22, 6, 4, decimals=0,
       desc="Casi todo el costo de un RAG está en la ENTRADA (contexto + historial). Baja con menos fragmentos (top_k), chunks más pequeños o un umbral más exigente.")
c.stat("Ahorro: turnos sin LLM (5 min)", 'sum(rate(rag_chat_turns_total{outcome="no_context"}[5m])) / clamp_min(sum(rate(rag_chat_turns_total[5m])), 1e-9)', 18, 22, 6, 4, unit="percentunit", decimals=0,
       desc="Fracción de turnos que la compuerta de relevancia resolvió SIN llamar al LLM: costo 0.")
c.ts("Tokens por segundo", [('sum by (direction) (rate(rag_llm_tokens_total[1m]))', "{{direction}}")], 0, 26, 8, 8, unit="ops", stack=True)
c.ts("Costo estimado por hora", [('sum by (model) (rate(rag_llm_cost_total[2m])) * 3600', "{{model}}")], 8, 26, 8, 8, unit="currencyUSD", stack=True)
c.ts("Cuota de tokens: rechazos por plan", [('sum by (tier) (rate(api_ratelimit_decisions_total{limiter="tokens", outcome=~"rejected.*"}[1m]))', "{{tier}}")], 16, 26, 8, 8, unit="ops", stack=True,
     desc="El límite por COSTO protege tu factura: ningún usuario puede gastar sin tope.")
c.alerts("Alertas", 0, 34)
c.save()

# =============================================================================================
# 4) RATE LIMITING (con el limitador de tokens)
# =============================================================================================
rl = Board("rate-limiting", "Rate limiting · rechazos, saturación y quién los provoca",
           "Decisiones, holgura antes del 429, Retry-After, usuarios ruidosos y trazas rechazadas. Cuatro limitadores: requests, streams, pages, tokens.",
           variables=[("tier", "free,pro,anon")])
T = 'tier=~"$tier"'
rl.text("Cómo leer este tablero",
        "| limitador | protege |\n|---|---|\n| `requests` | velocidad (token bucket) |\n| `streams` | streams SSE simultáneos |\n"
        "| `pages` | trabajo de ingesta (páginas) |\n| `tokens` | **dinero**: tokens de LLM por minuto |\n\n"
        "**El 429 llega tarde; la holgura avisa antes.** El usuario concreto NO es etiqueta de métrica: se busca en logs/trazas por `user.id`.",
        0, 0, 8, 9)
rl.stat("Decisiones / s", f'sum(rate(api_ratelimit_decisions_total{{{T}}}[1m]))', 8, 0, 4, 4, unit="ops", decimals=2)
rl.stat("Rechazos / s", f'sum(rate(api_ratelimit_decisions_total{{{T},outcome=~"rejected.*"}}[1m])) or vector(0)', 12, 0, 4, 4, unit="ops", decimals=3, thresholds=[(None, "green"), (0.05, "orange"), (0.5, "red")])
rl.stat("% rechazado", f'(sum(rate(api_ratelimit_decisions_total{{{T},outcome=~"rejected.*"}}[1m])) or vector(0)) / clamp_min(sum(rate(api_ratelimit_decisions_total{{{T}}}[1m])), 1e-9)',
        16, 0, 4, 4, unit="percentunit", decimals=1, thresholds=[(None, "green"), (0.1, "orange"), (0.3, "red")])
rl.stat("Usuarios con estado en memoria", 'sum(api_ratelimit_clients_tracked)', 20, 0, 4, 4, thresholds=[(None, "blue")])
rl.ts("Decisiones por limitador y resultado", [(f'sum by (limiter, outcome) (rate(api_ratelimit_decisions_total{{{T}}}[1m]))', "{{limiter}} · {{outcome}}")], 8, 4, 16, 5, unit="ops", stack=True)
rl.row("Saturación: ver el problema ANTES del 429", 9)
rl.heatmap("Holgura de 'requests' (remaining/limit) en cada decisión", f'sum by (le) (increase(api_ratelimit_remaining_ratio_bucket{{limiter="requests",le!="+Inf",{T}}}[$__rate_interval]))',
           0, 10, 12, 9, "Calor cerca de 0 = usuarios al borde del límite.", unit="percentunit")
rl.ts("Fracción de decisiones con holgura ≤ 20 %", [('lab:ratelimit_near_limit_ratio:rate1m{tier=~"$tier"}', "{{limiter}} · {{tier}}")], 12, 10, 12, 9, unit="percentunit", minv=0, maxv=1,
      thresholds=[(None, "green"), (0.5, "orange")])
rl.row("Rechazos", 19)
rl.ts("Ratio de rechazo por limitador y plan", [('lab:ratelimit_rejection_ratio:rate1m{tier=~"$tier"}', "{{limiter}} · {{tier}}")], 0, 20, 8, 8, unit="percentunit", minv=0, maxv=1)
rl.ts("Retry-After enviado (p50 / p95)", [(q("api_ratelimit_retry_after_seconds_bucket", 0.5, T, "5m"), "p50"), (q("api_ratelimit_retry_after_seconds_bucket", 0.95, T, "5m"), "p95")], 8, 20, 8, 8, unit="s")
rl.bargauge("Rechazos por limitador (rango visible)", f'sum by (limiter) (increase(api_ratelimit_decisions_total{{{T},outcome=~"rejected.*"}}[$__range]))', "{{limiter}}", 16, 20, 8, 8)
rl.row("¿Quién? (logs y trazas: aquí SÍ hay identidad de usuario)", 28)
rl.table_loki("Top usuarios rechazados (Loki)", 'topk(10, sum by (user_id, limiter, tier) (count_over_time({service_name="rag-api"} |= "rate_limited" | user_id != "" [$__range])))', 0, 29, 8, 9)
rl.traces("Trazas rechazadas por el limitador (TraceQL)", '{ span.ratelimit.rejected = true }', 8, 29, 16, 9)
rl.logs("Logs 'rate_limited' con detalle", '{service_name="rag-api"} |= "rate_limited"', 0, 38, 24, 8)
rl.alerts("Alertas de límites", 0, 47)
rl.save()

# =============================================================================================
# 5) TUBERÍA DE OBSERVABILIDAD (igual que el laboratorio 03)
# =============================================================================================
o = Board("observability-pipeline", "Tubería de observabilidad · vigilando al vigilante",
          "Collector, Prometheus, Tempo y Loki: ¿están perdiendo datos? ¿cuánto cuesta (cardinalidad, series, volumen)?")
o.row("OpenTelemetry Collector", 0)
o.stat("Spans aceptados / s", 'sum(rate(otelcol_receiver_accepted_spans[1m]))', 0, 1, 4, 4, unit="ops", decimals=1)
o.stat("Métricas (puntos) / s", 'sum(rate(otelcol_receiver_accepted_metric_points[1m]))', 4, 1, 4, 4, unit="ops", decimals=1)
o.stat("Logs / s", 'sum(rate(otelcol_receiver_accepted_log_records[1m]))', 8, 1, 4, 4, unit="ops", decimals=1)
o.stat("Datos RECHAZADOS / s", 'sum(rate(otelcol_receiver_refused_spans[1m])) + sum(rate(otelcol_receiver_refused_metric_points[1m])) + sum(rate(otelcol_receiver_refused_log_records[1m])) or vector(0)',
       12, 1, 4, 4, thresholds=[(None, "green"), (0.001, "red")], decimals=3,
       desc="> 0 = el memory_limiter está descartando telemetría: estás perdiendo datos.")
o.stat("Memoria RSS del Collector", 'max(otelcol_process_memory_rss)', 16, 1, 4, 4, unit="bytes", thresholds=[(None, "green"), (3.5e8, "orange")])
o.stat("Cola del exportador (uso)", 'max(otelcol_exporter_queue_size / otelcol_exporter_queue_capacity)', 20, 1, 4, 4, unit="percentunit",
       thresholds=[(None, "green"), (0.5, "orange"), (0.8, "red")], desc="Cola llena = el backend (Tempo/Loki) no da abasto.")
o.ts("Volumen recibido por señal", [('sum(rate(otelcol_receiver_accepted_spans[1m]))', "spans/s"), ('sum(rate(otelcol_receiver_accepted_log_records[1m]))', "logs/s"),
                                    ('sum(rate(otelcol_receiver_accepted_metric_points[1m]))', "puntos métricos/s")], 0, 5, 12, 8, unit="ops")
o.ts("Tail sampling: trazas CONSERVADAS por política",
     [('sum by (policy) (rate(otelcol_processor_tail_sampling_count_traces_sampled{sampled="true"}[1m]))', "{{policy}}")], 12, 5, 12, 8, unit="ops",
     desc="Muestra cuántas trazas conserva cada política. Ahorras almacenamiento sin perder lo interesante.")
o.row("Prometheus: costo y cardinalidad", 13)
o.stat("Series activas (head)", 'prometheus_tsdb_head_series', 0, 14, 4, 4, thresholds=[(None, "green"), (50000, "orange")],
       desc="Cardinalidad total. Es lo que más encarece un stack de métricas.")
o.stat("Muestras / s", 'sum(rate(prometheus_tsdb_head_samples_appended_total[1m]))', 4, 14, 4, 4, unit="ops", decimals=0)
o.stat("Exemplars almacenados", 'prometheus_tsdb_exemplar_exemplars_in_storage', 8, 14, 4, 4)
o.stat("Targets caídos", 'count(up == 0) or vector(0)', 12, 14, 4, 4, thresholds=[(None, "green"), (1, "red")])
o.stat("Sonda sintética /health", 'probe_success{instance="http://api:8000/health"}', 16, 14, 4, 4, thresholds=[(None, "red"), (1, "green")],
       mappings=[{"type": "value", "options": {"0": {"text": "CAÍDA"}, "1": {"text": "OK"}}}],
       desc="Blackbox: la API vista DESDE FUERA, como un cliente.")
o.stat("Latencia de la sonda", 'probe_duration_seconds{instance="http://api:8000/health"}', 20, 14, 4, 4, unit="s", decimals=4)
o.table_prom("Top 10 métricas por número de series (cardinalidad)", 'topk(10, count by (__name__) ({__name__=~".+"}))', 0, 18, 12, 9,
             "Antes de añadir una etiqueta, mira aquí. Una etiqueta con un id de usuario multiplica las series.")
o.ts("Estado de scrapes (up)", [('up', "{{job}}")], 12, 18, 12, 9, minv=0, maxv=1, style="line", fill=0)
o.row("Tempo y Loki (backends)", 27)
o.ts("Tempo: spans recibidos / descartados", [('sum(rate(tempo_distributor_spans_received_total[1m]))', "recibidos/s"),
                                             ('sum(rate(tempo_discarded_spans_total[1m])) or vector(0)', "descartados/s")], 0, 28, 12, 8, unit="ops")
o.ts("Loki: líneas y bytes ingeridos", [('sum(rate(loki_distributor_lines_received_total[1m]))', "líneas/s"),
                                        ('sum(rate(loki_distributor_bytes_received_total[1m]))', "bytes/s")], 12, 28, 12, 8, unit="short")
o.save()

print("OK ->", *sorted(p.name for p in OUT.glob("*.json")))