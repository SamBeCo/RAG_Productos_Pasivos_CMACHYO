"""Paso 7: guardas deterministas. Las reglas duras del manual, escritas como código.

Principio de diseño:   el LLM solo puede ENDURECER la decisión, nunca ablandarla.
    piso   = lo que exigen las guardas (APROBAR < OBSERVAR < RECHAZAR)
    final  = lo más estricto entre el piso y la propuesta del LLM
Así, aunque el LLM "se convenza" de aprobar a un cliente con calificación Pérdida (por un prompt injection en la
pregunta libre, o por error), el resultado sigue siendo RECHAZAR. El LLM aporta la explicación y matices; la
regla dura no depende de él.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modelos import Solicitud
from rules import politicas

P = politicas.PARAMETROS
ORDEN = {"APROBAR": 0, "OBSERVAR": 1, "RECHAZAR": 2}
ARTICULO_PRODUCTO = {clave: f"2.{i}" for i, clave in enumerate(politicas.PRODUCTOS, 1)}
REGLAS = [*ARTICULO_PRODUCTO.values(), "3.1", "3.2", "4.2", "4.3", "5.2", "5.3", "6.1"]   # artículos que revisa este archivo


@dataclass
class Hallazgo:
    regla: str          # id del artículo del PDF: el agente trae su texto exacto con rag.por_id()
    severidad: str      # OBSERVAR | RECHAZAR
    mensaje: str


def revisar(s: Solicitud, calc: dict) -> list[Hallazgo]:
    h: list[Hallazgo] = []
    prod = politicas.PRODUCTOS[s.producto]
    art = ARTICULO_PRODUCTO[s.producto]

    if not prod["monto_min"] <= s.monto <= prod["monto_max"]:
        h.append(Hallazgo(art, "RECHAZAR", f"Monto S/ {s.monto:,.0f} fuera del rango del {prod['nombre']} "
                                           f"(S/ {prod['monto_min']:,} a S/ {prod['monto_max']:,})"))
    if not prod["plazo_min"] <= s.plazo_meses <= prod["plazo_max"]:
        h.append(Hallazgo(art, "RECHAZAR", f"Plazo de {s.plazo_meses} meses fuera del rango "
                                           f"({prod['plazo_min']} a {prod['plazo_max']} meses)"))

    if s.edad < P["edad_min"]:
        h.append(Hallazgo("3.1", "RECHAZAR", f"Edad {s.edad} menor a {P['edad_min']} años"))
    if calc["edad_al_vencimiento"] > P["edad_max_vencimiento"]:
        h.append(Hallazgo("3.1", "RECHAZAR", f"Edad al vencimiento {calc['edad_al_vencimiento']} mayor a {P['edad_max_vencimiento']} años"))

    minimo = P["antiguedad_min_dependiente"] if s.tipo_trabajador == "dependiente" and s.producto != "mype" else P["antiguedad_min_independiente"]
    if s.antiguedad_meses < minimo:
        h.append(Hallazgo("3.2", "OBSERVAR", f"Antigüedad de {s.antiguedad_meses} meses, menor al mínimo de {minimo}"))

    if calc["cuota_ingreso"] > P["cuota_ingreso_max"]:
        h.append(Hallazgo("4.2", "RECHAZAR", f"Cuota/ingreso {calc['cuota_ingreso']:.1%} supera el máximo de {P['cuota_ingreso_max']:.0%}"))

    if calc["endeudamiento"] > P["endeudamiento_max"]:
        h.append(Hallazgo("4.3", "RECHAZAR", f"Endeudamiento {calc['endeudamiento']:.1%} supera el máximo de {P['endeudamiento_max']:.0%}"))
    elif calc["endeudamiento"] > P["endeudamiento_observar"]:
        h.append(Hallazgo("4.3", "OBSERVAR", f"Endeudamiento {calc['endeudamiento']:.1%} entre {P['endeudamiento_observar']:.0%} y {P['endeudamiento_max']:.0%}"))

    if s.calificacion_sbs == "CPP":
        h.append(Hallazgo("5.2", "OBSERVAR", "Calificación CPP: requiere aval con calificación Normal o garantía"))
    elif s.calificacion_sbs in ("Deficiente", "Dudoso", "Pérdida"):
        h.append(Hallazgo("5.3", "RECHAZAR", f"Calificación {s.calificacion_sbs} en el sistema financiero"))

    if s.monto >= P["monto_comite"]:
        h.append(Hallazgo("6.1", "OBSERVAR", f"Monto desde S/ {P['monto_comite']:,}: requiere firma del comité de créditos"))
    return h


def piso(hallazgos: list[Hallazgo]) -> str:
    """El dictamen mínimo que exigen las reglas duras."""
    return max((x.severidad for x in hallazgos), key=ORDEN.get, default="APROBAR")


def mas_estricto(a: str, b: str) -> str:
    return a if ORDEN[a] >= ORDEN[b] else b
