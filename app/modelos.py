"""Paso 7: el formulario del asesor como contrato de datos (Pydantic).

Si un campo viene mal (ingreso negativo, DNI con letras, producto inexistente), FastAPI responde 422 ANTES de llamar a
Jev u OpenAI: no se gasta un centavo en datos basura y no hay divisiones entre cero más adelante.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from rules import politicas

Producto = Literal["consumo", "mype", "vehicular"]
Calificacion = Literal["Normal", "CPP", "Deficiente", "Dudoso", "Pérdida"]
Dictamen = Literal["APROBAR", "OBSERVAR", "RECHAZAR"]

assert set(Calificacion.__args__) == set(politicas.CALIFICACIONES_SBS)   # el formulario y el manual usan la misma lista
assert set(Producto.__args__) == set(politicas.PRODUCTOS)


class Solicitud(BaseModel):
    dni: str = Field(pattern=r"^\d{8}$", description="DNI ficticio, 8 dígitos. NUNCA se envía a Jev ni a OpenAI")
    nombre: str = Field(min_length=2, max_length=80)
    edad: int = Field(ge=18, le=100)
    ingreso_mensual: float = Field(gt=0, le=1_000_000)
    deuda_mensual: float = Field(ge=0, le=1_000_000, description="Cuotas que ya paga en el sistema financiero")
    calificacion_sbs: Calificacion
    antiguedad_meses: int = Field(ge=0, le=600)
    tipo_trabajador: Literal["dependiente", "independiente"]
    producto: Producto
    monto: float = Field(gt=0, le=10_000_000)
    plazo_meses: int = Field(ge=1, le=360)
    pregunta: str = Field(min_length=3, max_length=500, description="Lo que el asesor pregunta, en sus palabras")


class MensajeChat(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)       # "   " queda vacío → 422
    conversacion_id: int | None = Field(default=None, description="Vacío = conversación nueva")
    mensaje: str = Field(min_length=1, max_length=1000)


class Decision(BaseModel):
    decision: Literal["APROBADA", "RECHAZADA"]
    analista: str = Field(min_length=2, max_length=60)
    comentario: str = Field(default="", max_length=1000)


class SolicitudRevision(BaseModel):
    mensaje_id: int = Field(gt=0)
    motivo: str = Field(default="", max_length=500)


class DecisionRevision(BaseModel):
    decision: Literal["APROBADA", "EDITADA", "RETIRADA"]
    revisor: str = Field(min_length=2, max_length=60)
    comentario: str = Field(min_length=5, max_length=1000)
    respuesta_final: str | None = Field(default=None, max_length=4000)
