"""Paso 7: herramientas de cálculo del analista de riesgo. Funciones PURAS: sin red, sin LLM, sin azar.

Un LLM no debe hacer aritmética financiera "de cabeza": se equivoca con potencias y redondeos. El agente le entrega
los números ya calculados aquí, y el LLM solo los interpreta frente a las reglas del PDF.
"""
from __future__ import annotations

from app.modelos import Solicitud
from rules import politicas


def tasa_mensual(tea: float) -> float:
    """TEA → tasa mensual equivalente: (1 + TEA)^(1/12) − 1   (Art. 4.1)."""
    return (1 + tea) ** (1 / 12) - 1


def cuota_francesa(monto: float, tea: float, plazo_meses: int) -> float:
    """Cuota fija mensual: M · i / (1 − (1 + i)^−n)   (Art. 4.1)."""
    if plazo_meses <= 0:
        raise ValueError("el plazo debe ser mayor que cero")
    i = tasa_mensual(tea)
    if i == 0:
        return monto / plazo_meses
    return monto * i / (1 - (1 + i) ** -plazo_meses)


def calcular(s: Solicitud) -> dict:
    tea = politicas.PRODUCTOS[s.producto]["tea"]
    cuota = cuota_francesa(s.monto, tea, s.plazo_meses)
    return {
        "tea": tea,
        "tasa_mensual": round(tasa_mensual(tea), 6),
        "cuota": round(cuota, 2),
        "cuota_ingreso": round(cuota / s.ingreso_mensual, 4),                          # Art. 4.2
        "endeudamiento": round((s.deuda_mensual + cuota) / s.ingreso_mensual, 4),     # Art. 4.3
        "edad_al_vencimiento": round(s.edad + s.plazo_meses / 12, 1),                 # Art. 3.1
        "total_a_pagar": round(cuota * s.plazo_meses, 2),
    }
