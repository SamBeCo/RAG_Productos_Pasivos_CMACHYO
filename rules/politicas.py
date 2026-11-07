"""Paso 4: las reglas de riesgo en UN solo lugar.

De aquí salen DOS cosas que nunca deben contradecirse:
  1. El PDF que lee el RAG (rules/generar_pdf.py lo imprime artículo por artículo).
  2. Los parámetros que verifican las guardas deterministas (app/guardas.py).
Si cambias un límite, cambia aquí y regenera el PDF: el texto y la guarda cambian juntos.

MATERIAL EDUCATIVO FICTICIO. No es la política de crédito de Caja Huancayo ni de ninguna entidad real.
"""
from __future__ import annotations

ENTIDAD = "Caja Demo Andina (entidad ficticia)"
TITULO = "Manual de Políticas de Riesgo Crediticio"
VERSION = "Versión 1.0 · material educativo ficticio"

CALIFICACIONES_SBS = ["Normal", "CPP", "Deficiente", "Dudoso", "Pérdida"]

PRODUCTOS = {
    "consumo": {"nombre": "Crédito Consumo", "monto_min": 500, "monto_max": 30000, "plazo_min": 6, "plazo_max": 48, "tea": 0.35},
    "mype": {"nombre": "Crédito MYPE", "monto_min": 1000, "monto_max": 100000, "plazo_min": 6, "plazo_max": 36, "tea": 0.30},
    "vehicular": {"nombre": "Crédito Vehicular", "monto_min": 10000, "monto_max": 150000, "plazo_min": 12, "plazo_max": 60, "tea": 0.18},
}

PARAMETROS = {
    "edad_min": 21,
    "edad_max_vencimiento": 75,
    "cuota_ingreso_max": 0.30,          # cuota nueva / ingreso mensual
    "endeudamiento_observar": 0.50,     # (deuda mensual actual + cuota nueva) / ingreso
    "endeudamiento_max": 0.60,
    "antiguedad_min_dependiente": 6,    # meses
    "antiguedad_min_independiente": 12,
    "monto_comite": 50000,              # desde este monto decide un comité, no un analista solo
}

P = PARAMETROS


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _soles(x: float) -> str:
    return f"S/ {x:,.0f}"


def _productos_texto() -> list[dict]:
    arts = []
    for i, (clave, p) in enumerate(PRODUCTOS.items(), 1):
        arts.append({
            "id": f"2.{i}", "titulo": f"{p['nombre']}: montos, plazos y tasa",
            "texto": (f"El {p['nombre']} (código '{clave}') se otorga desde {_soles(p['monto_min'])} hasta {_soles(p['monto_max'])}, "
                      f"con plazos de {p['plazo_min']} a {p['plazo_max']} meses. La tasa efectiva anual (TEA) referencial es "
                      f"{_pct(p['tea'])}, fija, con cuotas mensuales iguales (método francés). Una solicitud fuera de estos "
                      f"rangos de monto o plazo se RECHAZA; el asesor puede reformularla con otro monto o plazo."),
        })
    return arts


CAPITULOS = [
    {"numero": 1, "titulo": "Disposiciones generales", "articulos": [
        {"id": "1.1", "titulo": "Objeto y alcance",
         "texto": ("Este manual establece las reglas con las que el área de Riesgos evalúa las solicitudes de crédito que "
                   "registran los asesores de ventas. Aplica a los productos Crédito Consumo, Crédito MYPE y Crédito Vehicular.")},
        {"id": "1.2", "titulo": "Dictámenes posibles",
         "texto": ("Toda evaluación termina en uno de tres dictámenes: APROBAR (cumple todas las reglas), OBSERVAR (cumple "
                   "las reglas de rechazo pero requiere una condición, un documento o el criterio del analista) o RECHAZAR "
                   "(incumple al menos una regla de rechazo). El dictamen del sistema es una PROPUESTA: la decisión final "
                   "la toma siempre un analista de riesgos humano.")},
        {"id": "1.3", "titulo": "Segregación de funciones",
         "texto": ("El asesor de ventas que registra la solicitud no puede aprobarla. Solo un analista de riesgos con "
                   "credencial vigente registra la decisión final, y si se aparta de la propuesta del sistema debe "
                   "dejar un comentario que lo justifique.")},
    ]},
    {"numero": 2, "titulo": "Productos", "articulos": _productos_texto()},
    {"numero": 3, "titulo": "Requisitos del solicitante", "articulos": [
        {"id": "3.1", "titulo": "Edad",
         "texto": (f"El solicitante debe tener al menos {P['edad_min']} años al momento de la solicitud y no superar los "
                   f"{P['edad_max_vencimiento']} años al vencimiento de la última cuota (edad actual + plazo en años). "
                   f"El incumplimiento de cualquiera de los dos límites es causal de RECHAZO.")},
        {"id": "3.2", "titulo": "Antigüedad laboral o del negocio",
         "texto": (f"Se exige una antigüedad mínima de {P['antiguedad_min_dependiente']} meses para trabajadores "
                   f"dependientes y de {P['antiguedad_min_independiente']} meses para independientes o titulares de "
                   f"negocio (MYPE). Una antigüedad menor no rechaza la solicitud, pero la deja en OBSERVAR: el analista "
                   f"puede aprobarla con un aval o una garantía.")},
        {"id": "3.3", "titulo": "Documentos",
         "texto": ("Dependientes: DNI vigente y las tres últimas boletas de pago. Independientes: DNI vigente, declaración "
                   "de impuestos del último año y seis meses de movimientos bancarios. MYPE: además, licencia de "
                   "funcionamiento o RUC activo. Vehicular: además, proforma del vehículo.")},
    ]},
    {"numero": 4, "titulo": "Capacidad de pago y endeudamiento", "articulos": [
        {"id": "4.1", "titulo": "Cálculo de la cuota",
         "texto": ("La cuota mensual se calcula con el método francés: cuota = M × i / (1 - (1 + i)^-n), donde M es el "
                   "monto, n el plazo en meses e i la tasa mensual equivalente a la TEA: i = (1 + TEA)^(1/12) - 1.")},
        {"id": "4.2", "titulo": "Relación cuota / ingreso",
         "texto": (f"La cuota del nuevo crédito no puede superar el {_pct(P['cuota_ingreso_max'])} del ingreso mensual "
                   f"neto del solicitante. Superarlo es causal de RECHAZO; el asesor puede proponer un plazo mayor o un "
                   f"monto menor.")},
        {"id": "4.3", "titulo": "Endeudamiento total",
         "texto": (f"El endeudamiento total es (deuda mensual actual + cuota nueva) / ingreso mensual. Hasta "
                   f"{_pct(P['endeudamiento_observar'])} es aceptable. Entre {_pct(P['endeudamiento_observar'])} y "
                   f"{_pct(P['endeudamiento_max'])} la solicitud queda en OBSERVAR. Por encima de "
                   f"{_pct(P['endeudamiento_max'])} es causal de RECHAZO.")},
    ]},
    {"numero": 5, "titulo": "Calificación en el sistema financiero (SBS)", "articulos": [
        {"id": "5.1", "titulo": "Calificación Normal",
         "texto": "Un solicitante con calificación Normal en la central de riesgos no tiene restricción por este criterio."},
        {"id": "5.2", "titulo": "Calificación CPP",
         "texto": ("Con calificación CPP (con problemas potenciales) la solicitud queda en OBSERVAR: solo puede aprobarse "
                   "con un aval con calificación Normal o una garantía.")},
        {"id": "5.3", "titulo": "Calificación Deficiente, Dudoso o Pérdida",
         "texto": ("Una calificación Deficiente, Dudoso o Pérdida en cualquier entidad del sistema financiero es causal de "
                   "RECHAZO, sin excepción, hasta que el cliente regularice su situación.")},
    ]},
    {"numero": 6, "titulo": "Niveles de aprobación", "articulos": [
        {"id": "6.1", "titulo": "Analista y comité",
         "texto": (f"Un analista de riesgos puede decidir solicitudes de hasta {_soles(P['monto_comite'] - 1)}. Desde "
                   f"{_soles(P['monto_comite'])} la solicitud queda en OBSERVAR y requiere además la firma del comité "
                   f"de créditos.")},
    ]},
]


def articulos() -> list[dict]:
    """Todos los artículos en orden, cada uno con su capítulo. Lo usan el generador del PDF y las pruebas."""
    return [{**a, "capitulo": c["numero"], "capitulo_titulo": c["titulo"]} for c in CAPITULOS for a in c["articulos"]]
