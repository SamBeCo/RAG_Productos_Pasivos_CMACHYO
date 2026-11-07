import pytest

from app import guardas, herramientas
from app.modelos import Solicitud
from rules import politicas

P = politicas.PARAMETROS


def sol(sana, **cambios):
    return Solicitud(**{**sana, **cambios})


# ------------------------------------------------------------------------------------------------- herramientas
@pytest.mark.parametrize("monto, tea, n", [(12000, 0.35, 24), (80000, 0.30, 36), (500, 0.18, 6)])
def test_la_cuota_francesa_amortiza_exactamente_la_deuda(monto, tea, n):
    """Prueba INDEPENDIENTE de la fórmula: simulamos mes a mes y el saldo final debe quedar en cero."""
    cuota, i, saldo = herramientas.cuota_francesa(monto, tea, n), herramientas.tasa_mensual(tea), monto
    for _ in range(n):
        saldo = saldo * (1 + i) - cuota
    assert abs(saldo) < 0.01


def test_tasa_mensual_compuesta_doce_veces_es_la_tea():
    assert (1 + herramientas.tasa_mensual(0.35)) ** 12 == pytest.approx(1.35)


def test_tasa_cero_y_plazo_invalido():
    assert herramientas.cuota_francesa(1200, 0, 12) == 100
    with pytest.raises(ValueError):
        herramientas.cuota_francesa(1200, 0.3, 0)


def test_calcular_ratios(sana):
    c = herramientas.calcular(sol(sana))
    assert c["cuota_ingreso"] == pytest.approx(c["cuota"] / 3500, abs=1e-4)
    assert c["endeudamiento"] == pytest.approx((400 + c["cuota"]) / 3500, abs=1e-4)
    assert c["edad_al_vencimiento"] == 37.0


# ------------------------------------------------------------------------------------------------- guardas
def hallazgos(sana, **cambios):
    s = sol(sana, **cambios)
    return {(h.regla, h.severidad) for h in guardas.revisar(s, herramientas.calcular(s))}


def test_cliente_sano_no_tiene_hallazgos(sana):
    assert hallazgos(sana) == set()


@pytest.mark.parametrize("cambios, esperado", [
    ({"monto": 40000}, ("2.1", "RECHAZAR")),                                  # consumo: máximo 30 000
    ({"plazo_meses": 60}, ("2.1", "RECHAZAR")),
    ({"edad": 20}, ("3.1", "RECHAZAR")),
    ({"edad": 72, "plazo_meses": 48}, ("3.1", "RECHAZAR")),                  # 76 al vencimiento
    ({"antiguedad_meses": 3}, ("3.2", "OBSERVAR")),
    ({"tipo_trabajador": "independiente", "antiguedad_meses": 8}, ("3.2", "OBSERVAR")),
    ({"monto": 28000, "plazo_meses": 12}, ("4.2", "RECHAZAR")),
    ({"deuda_mensual": 1200}, ("4.3", "OBSERVAR")),                         # 54%
    ({"deuda_mensual": 1800}, ("4.3", "RECHAZAR")),
    ({"calificacion_sbs": "CPP"}, ("5.2", "OBSERVAR")),
    ({"calificacion_sbs": "Pérdida"}, ("5.3", "RECHAZAR")),
    ({"producto": "mype", "monto": 60000, "plazo_meses": 36, "ingreso_mensual": 15000}, ("6.1", "OBSERVAR")),
])
def test_cada_regla_dispara_su_hallazgo(sana, cambios, esperado):
    assert esperado in hallazgos(sana, **cambios)


def test_mype_exige_antiguedad_de_independiente_aunque_sea_dependiente(sana):
    assert ("3.2", "OBSERVAR") in hallazgos(sana, producto="mype", monto=5000, antiguedad_meses=8)


def test_limites_exactos_estan_permitidos(sana):
    """'No puede superar el 30%': exactamente 30% está permitido. Un > cambiado por >= rompería esta prueba."""
    s = sol(sana)
    cuota = herramientas.calcular(s)["cuota"]
    justo = sol(sana, ingreso_mensual=round(cuota / P["cuota_ingreso_max"], 2), deuda_mensual=0)
    c = herramientas.calcular(justo)
    assert c["cuota_ingreso"] <= P["cuota_ingreso_max"]
    assert not [h for h in guardas.revisar(justo, c) if h.regla == "4.2"]
    edad_justa = sol(sana, edad=73, plazo_meses=24)                            # 75.0 al vencimiento
    assert not [h for h in guardas.revisar(edad_justa, herramientas.calcular(edad_justa)) if h.regla == "3.1"]


def test_piso_y_mas_estricto():
    H = guardas.Hallazgo
    assert guardas.piso([]) == "APROBAR"
    assert guardas.piso([H("3.2", "OBSERVAR", ""), H("5.3", "RECHAZAR", "")]) == "RECHAZAR"
    assert guardas.mas_estricto("RECHAZAR", "APROBAR") == "RECHAZAR"
    assert guardas.mas_estricto("APROBAR", "OBSERVAR") == "OBSERVAR"       # el LLM puede endurecer


def test_cada_articulo_que_usan_las_guardas_existe_en_el_pdf():
    ids = {a["id"] for a in politicas.articulos()}
    assert set(guardas.REGLAS) <= ids
