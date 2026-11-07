"""Paso 8: el LLM. Una interfaz (`generar`) y dos implementaciones.

- OpenAILLM: OpenAI real con la Responses API y SALIDA ESTRUCTURADA (JSON Schema estricto). El modelo no puede
  devolver texto libre ni inventar campos: o devuelve un JSON que cumple el esquema, o falla y lo tratamos.
- MockLLM: reglas fijas, sin red. NO es inteligencia; existe para que pytest corra sin clave ni costo.

`store=False`: por defecto la Responses API guarda la conversación en OpenAI; con datos de clientes no queremos eso.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from app import metricas
from app.privacidad import enmascarar


class LLMError(RuntimeError):
    """Fallo del proveedor: red, clave, límite, respuesta incompleta o JSON inválido."""


@dataclass
class RespuestaLLM:
    datos: dict
    modelo: str
    input_tokens: int = 0
    output_tokens: int = 0


ESQUEMA_DICTAMEN = {
    "type": "object", "additionalProperties": False,
    "required": ["dictamen", "justificacion", "reglas_citadas", "condiciones"],
    "properties": {
        "dictamen": {"type": "string", "enum": ["APROBAR", "OBSERVAR", "RECHAZAR"]},
        "justificacion": {"type": "string"},
        "reglas_citadas": {"type": "array", "items": {"type": "string"}},
        "condiciones": {"type": "array", "items": {"type": "string"}},
    },
}

ESQUEMA_RESPUESTA = {
    "type": "object", "additionalProperties": False,
    "required": ["respuesta", "reglas_citadas"],
    "properties": {"respuesta": {"type": "string"}, "reglas_citadas": {"type": "array", "items": {"type": "string"}}},
}


ESQUEMA_REFORMULA = {
    "type": "object", "additionalProperties": False, "required": ["consulta"],
    "properties": {"consulta": {"type": "string"}},
}


class OpenAILLM:
    nombre = "openai"

    def __init__(self, settings, client=None):
        from openai import OpenAI

        self.modelo = settings.openai_model
        self.esfuerzo = settings.openai_reasoning_effort
        self.max_tokens = settings.openai_max_output_tokens
        self.precio_in, self.precio_out = settings.precio_openai_input, settings.precio_openai_output
        self.client = client or OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_s, max_retries=2)

    def generar(self, instrucciones: str, contexto: dict, esquema: dict, nombre: str) -> RespuestaLLM:
        import openai

        kwargs = {"model": self.modelo, "instructions": instrucciones, "store": False,
                  "input": enmascarar(json.dumps(contexto, ensure_ascii=False, indent=1)),   # DNI, teléfonos… nunca salen
                  "text": {"format": {"type": "json_schema", "name": nombre, "schema": esquema, "strict": True}},
                  "max_output_tokens": self.max_tokens}
        if self.esfuerzo:
            kwargs["reasoning"] = {"effort": self.esfuerzo}
        t0 = time.perf_counter()
        try:
            r = self.client.responses.create(**kwargs)
        except openai.APIError as e:
            metricas.API_ERRORES.labels("openai_llm", type(e).__name__).inc()
            raise LLMError(f"OpenAI falló: {type(e).__name__}: {e}") from e
        finally:
            metricas.API_LATENCIA.labels("openai_llm").observe(time.perf_counter() - t0)

        uso_in = r.usage.input_tokens if r.usage else 0
        uso_out = r.usage.output_tokens if r.usage else 0
        metricas.TOKENS.labels("openai_llm", "input").inc(uso_in)
        metricas.TOKENS.labels("openai_llm", "output").inc(uso_out)
        metricas.COSTO.labels("openai_llm").inc((uso_in * self.precio_in + uso_out * self.precio_out) / 1e6)

        if r.status != "completed":          # p. ej. max_output_tokens agotado por el razonamiento
            metricas.API_ERRORES.labels("openai_llm", "incompleta").inc()
            raise LLMError(f"respuesta {r.status}: {r.incomplete_details}")
        try:
            datos = json.loads(r.output_text)  # vacío si el modelo se negó (refusal)
        except json.JSONDecodeError as e:
            metricas.API_ERRORES.labels("openai_llm", "json_invalido").inc()
            raise LLMError(f"JSON inválido: {r.output_text[:200]!r}") from e
        return RespuestaLLM(datos, r.model, uso_in, uso_out)


class MockLLM:
    """Simulador determinista: arma la respuesta con los hallazgos y los artículos recibidos."""
    nombre = "mock"
    modelo = "mock"

    def generar(self, instrucciones: str, contexto: dict, esquema: dict, nombre: str) -> RespuestaLLM:
        reglas = contexto.get("reglas_del_manual", [])
        if nombre == "reformulacion":
            # regla fija: un mensaje corto con historial se completa con la pregunta anterior del asesor
            actual = contexto["mensaje_actual"]
            previas = [m["texto"] for m in contexto.get("historial", []) if m["rol"] == "asesor"]
            consulta = f"{previas[-1]} {actual}" if previas and len(actual.split()) < 6 else actual
            return RespuestaLLM({"consulta": consulta}, self.modelo)
        if nombre == "dictamen":
            hallazgos = contexto.get("hallazgos_de_las_guardas", [])
            sev = [h["severidad"] for h in hallazgos]
            dictamen = "RECHAZAR" if "RECHAZAR" in sev else "OBSERVAR" if sev else "APROBAR"
            c = contexto["calculos"]
            texto = (f"Cuota estimada S/ {c['cuota']:,.2f} ({c['cuota_ingreso']:.1%} del ingreso), endeudamiento "
                     f"{c['endeudamiento']:.1%}. " + (" ".join(h["mensaje"] + "." for h in hallazgos) or "Cumple las reglas revisadas."))
            citas = list(dict.fromkeys([h["regla"] for h in hallazgos] + [r["id"] for r in reglas[:2]]))
            condiciones = ["Presentar aval con calificación Normal o garantía"] if "OBSERVAR" in sev else []
            return RespuestaLLM({"dictamen": dictamen, "justificacion": "[simulado] " + texto,
                                 "reglas_citadas": citas, "condiciones": condiciones}, self.modelo)
        top = reglas[0]
        if nombre == "comparacion":
            seleccion = reglas[:3]
            texto = " | ".join(f"{r['documento'] or r['titulo']}: {r['texto'][:220]}" for r in seleccion)
            return RespuestaLLM({"respuesta": f"[simulado] Comparación documentada: {texto}",
                                 "reglas_citadas": [r["id"] for r in seleccion]}, self.modelo)
        return RespuestaLLM({"respuesta": f"[simulado] {top['texto']}",
                             "reglas_citadas": [top["id"]]}, self.modelo)


def crear_llm(settings):
    return OpenAILLM(settings) if settings.llm_provider == "openai" else MockLLM()
