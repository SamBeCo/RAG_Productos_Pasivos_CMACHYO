"""Paso 10: enmascarar datos personales ANTES de que salgan hacia Jev u OpenAI.

En el formulario el DNI tenía su propio campo y era fácil no enviarlo. En un chat el asesor escribe lo que quiere:
"mi cliente 40123456, Rosa, cel 987654321, ¿califica?". Por eso el enmascarado vive en los ADAPTADORES de salida
(JevRouter, OpenAILLM, OpenAIEmbedder): cualquier camino que llegue a un tercero pasa por aquí, aunque quien llama
se olvide. En la base de datos interna se guarda el texto original (es el registro de la entidad).

Los nombres y domicilios se reconocen cuando están introducidos por etiquetas inequívocas; no es un NER general.
"""
from __future__ import annotations

import re

from app import metricas

# (?<![\d.]) y (?![\d.]) evitan enmascarar parte de un número más largo o de un decimal (10000000.0 es un monto)
PATRONES = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ruc", re.compile(r"(?<![\d.])(10|15|17|20)\d{9}(?![\d.])")),          # RUC peruano: 11 dígitos
    ("telefono", re.compile(r"(?<![\d.])(\+?51[\s-]?)?9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?![\d.])")),
    ("dni", re.compile(r"(?<![\d.])\d{8}(?![\d.])")),
    ("nombre", re.compile(
        r"(?i)(?P<label>\b(?:cliente|titular|señor|señora|nombre(?: del cliente)?)\s+)"
        r"(?P<value>(?-i:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ'-]*(?:\s+[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ'-]*){1,3}))"
    )),
    ("direccion", re.compile(
        r"(?i)(?P<label>\b(?:domicilio|dirección|direccion|vive en|reside en)\s+)"
        r"(?P<value>[^,;\n]{4,100})"
    )),
]


def enmascarar(texto: str) -> str:
    for tipo, rx in PATRONES:
        if "label" in rx.groupindex:
            texto, n = rx.subn(lambda m: f"{m.group('label')}[{tipo.upper()}]", texto)
        else:
            texto, n = rx.subn(f"[{tipo.upper()}]", texto)
        if n:
            metricas.PII_ENMASCARADO.labels(tipo).inc(n)
    return texto
