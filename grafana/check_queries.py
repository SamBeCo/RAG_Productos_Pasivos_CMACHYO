"""Ejecuta TODAS las consultas de los dashboards contra Prometheus, Loki y Tempo y reporta errores o paneles vacíos.

Uso (con el stack arriba):  python grafana/check_queries.py
Sirve como prueba de humo: si renombras una métrica en el código, esto te dice qué panel quedó ciego.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROM, LOKI, TEMPO = "http://localhost:9090", "http://localhost:3100", "http://localhost:3200"
SUBS = {"$__rate_interval": "1m", "$__range": "15m", "$tier": ".+", "${tier}": ".+"}


def sub(s: str) -> str:
    for k, v in SUBS.items():
        s = s.replace(k, v)
    return s


def get(url: str, params: dict) -> dict:
    with urllib.request.urlopen(f"{url}?{urllib.parse.urlencode(params)}", timeout=20) as r:
        return json.load(r)


def check(kind: str, expr: str):
    now = int(time.time())
    if kind == "prometheus":
        d = get(f"{PROM}/api/v1/query", {"query": sub(expr)})
        return d["status"] == "success", len(d["data"]["result"])
    if kind == "loki":
        d = get(f"{LOKI}/loki/api/v1/query", {"query": sub(expr), "limit": 5, "time": f"{now}000000000"}) \
            if expr.startswith(("topk", "sum", "count")) else \
            get(f"{LOKI}/loki/api/v1/query_range", {"query": sub(expr), "limit": 5, "start": f"{now - 900}000000000"})
        return d["status"] == "success", len(d["data"]["result"])
    if kind == "tempo":
        d = get(f"{TEMPO}/api/search", {"q": expr, "limit": 5, "start": now - 900, "end": now})
        return True, len(d.get("traces", []))
    return True, -1


bad, empty, ok = 0, 0, 0
for f in sorted((Path(__file__).parent / "dashboards").glob("*.json")):
    board = json.loads(f.read_text())
    print(f"\n== {board['title']}")
    for p in board["panels"]:
        for t in p.get("targets", []):
            kind = t["datasource"]["type"]
            expr = t.get("expr") or t.get("query")
            try:
                good, n = check(kind, expr)
                status = "OK   " if good and n else ("VACIO" if good else "ERROR")
            except Exception as e:
                good, n, status = False, 0, f"ERROR"
                expr = f"{expr}\n        -> {e}"
            bad += status == "ERROR"; empty += status == "VACIO"; ok += status == "OK   "
            if status != "OK   ":
                print(f"  [{status}] {kind:10} {p['title'][:52]:52} n={n}\n        {str(expr)[:170]}")
print(f"\nResumen: {ok} con datos, {empty} vacías, {bad} con error")
sys.exit(1 if bad else 0)