import threading

import pytest

from app.db import NoExiste, Repositorio, YaDecidida


@pytest.fixture
def repo(tmp_path):
    return Repositorio(tmp_path / "s.db")


def nueva(repo):
    return repo.crear("PENDIENTE_ANALISTA", "evaluacion_credito", {"nombre": "Ñuño"}, {"ruta": "evaluacion_credito"},
                      {"dictamen": "APROBAR"})


def test_guarda_y_lee_json_con_tildes(repo):
    f = repo.obtener(nueva(repo))
    assert f["solicitud"]["nombre"] == "Ñuño" and f["estado"] == "PENDIENTE_ANALISTA"


def test_decidir_dos_veces_lanza_ya_decidida(repo):
    """La API revisa el estado antes de llamar a decidir(); esta prueba va directo al repositorio, que es la ÚLTIMA
    defensa cuando dos analistas leen la misma solicitud al mismo tiempo."""
    id_ = nueva(repo)
    repo.decidir(id_, "APROBADA", "Ana", "")
    with pytest.raises(YaDecidida):
        repo.decidir(id_, "RECHAZADA", "Beto", "otro criterio")
    assert repo.obtener(id_)["analista"] == "Ana"


def test_dos_analistas_a_la_vez_solo_uno_gana(repo):
    id_ = nueva(repo)
    resultados, barrera = [], threading.Barrier(8)

    def analista(nombre):
        barrera.wait()
        try:
            repo.decidir(id_, "APROBADA", nombre, "")
            resultados.append("ok")
        except YaDecidida:
            resultados.append("409")

    hilos = [threading.Thread(target=analista, args=(f"A{i}",)) for i in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == ["409"] * 7 + ["ok"]


def test_inexistente(repo):
    with pytest.raises(NoExiste):
        repo.obtener(42)
    with pytest.raises(NoExiste):
        repo.decidir(42, "APROBADA", "Ana", "")


def test_pendientes_y_contador(repo):
    a, b = nueva(repo), nueva(repo)
    repo.decidir(a, "APROBADA", "Ana", "")
    assert [f["id"] for f in repo.pendientes()] == [b] and repo.contar_pendientes() == 1
