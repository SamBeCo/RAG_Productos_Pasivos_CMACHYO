"""Guardas deterministas para bloquear instrucciones de manipulación antes de usar servicios de IA."""
from __future__ import annotations

import re

PATRONES_INYECCION = (
    re.compile(r"\b(?:ignora|ignorar|omite|omitir|desobedece|olvida|ignore|disregard|skip|forget|override)\b"
               r".{0,80}\b(?:instrucciones|reglas|pol[ií]ticas|sistema|prompt|instructions|rules|policies|system)\b", re.I),
    re.compile(r"\b(?:revela|muestra|imprime|copia|reveal|show|print|copy)\b"
               r".{0,60}\b(?:prompt|instrucciones internas|clave|secreto|system prompt|internal instructions|key|secret)\b", re.I),
    re.compile(r"\b(?:act[uú]a|responde|comp[oó]rtate|act|respond|behave)\s+(?:como|as)\b"
               r".{0,60}\b(?:sin restricciones|administrador|sistema|without restrictions|administrator|system)\b", re.I),
    re.compile(r"\b(?:aprueba|autoriza|approve|authorize)\b"
               r".{0,50}\b(?:sin validar|aunque|ignora las reglas|without validation|even if|ignore the rules)\b", re.I),
)


def detectar_inyeccion(texto: str) -> bool:
    return any(p.search(texto) for p in PATRONES_INYECCION)
