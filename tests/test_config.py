import os

import pytest

from app import config
from app.config import ConfigError, Settings


@pytest.mark.parametrize("codificacion", ["utf-8", "utf-8-sig", "utf-16", "utf-16-be"])
def test_env_se_lee_con_cualquier_codificacion_de_windows(codificacion):
    """Bloc de notas = UTF-8 con BOM; PowerShell 5.1 (`echo X=1 > .env`) = UTF-16 con BOM."""
    texto = "ROUTER_PROVIDER=jev\r\nNOMBRE=María\r\n"
    crudo = texto.encode(codificacion)
    if codificacion == "utf-16-be":
        crudo = b"\xfe\xff" + crudo
    assert config.decode_env_bytes(crudo) == texto


def test_load_env_no_pisa_variables_del_sistema(tmp_path, monkeypatch):
    archivo = tmp_path / ".env"
    archivo.write_bytes("LAB06_NUEVA=desde_env\r\nLAB06_EXISTENTE=desde_env\r\n".encode("utf-16"))
    monkeypatch.setenv("LAB06_NUEVA", "x")
    monkeypatch.delenv("LAB06_NUEVA")
    monkeypatch.setenv("LAB06_EXISTENTE", "del_sistema")
    config.load_env(archivo)
    assert os.environ["LAB06_NUEVA"] == "desde_env"
    assert os.environ["LAB06_EXISTENTE"] == "del_sistema"
    monkeypatch.delenv("LAB06_NUEVA")


def test_jev_sin_clave_falla_al_arrancar_con_mensaje_claro(monkeypatch):
    monkeypatch.setenv("ROUTER_PROVIDER", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "")
    with pytest.raises(ConfigError, match="TYPESAFE_API_KEY"):
        Settings().validar()


def test_openai_sin_clave_falla_al_arrancar(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "  ")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Settings().validar()


def test_proveedor_desconocido(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gpt")
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        Settings().validar()


def test_numero_invalido_en_env(monkeypatch):
    monkeypatch.setenv("ROUTER_MIN_CONFIDENCE", "0,55")          # coma decimal: error típico con configuración regional en español
    with pytest.raises(ConfigError, match="ROUTER_MIN_CONFIDENCE"):
        Settings()


def test_modo_sin_claves_es_valido():
    Settings().validar()      # conftest: hash + mock


@pytest.mark.parametrize("codificacion, esperado", [("utf-16", "UTF-16 -> UTF-8"), ("utf-8-sig", "se quitó el BOM")])
def test_normalizar_env_deja_utf8_lf_para_docker(tmp_path, codificacion, esperado):
    """Docker Compose falla con un .env en UTF-16 (medido con Compose v5.1.4); este script lo arregla."""
    from scripts.normalizar_env import normalizar
    p = tmp_path / ".env"
    p.write_bytes("A=1\r\nB=ñandú\r\n".encode(codificacion))
    assert normalizar(p) == [esperado, "CRLF -> LF"]
    assert p.read_bytes() == "A=1\nB=ñandú\n".encode("utf-8")
    assert normalizar(p) == []                       # segunda vez: nada que cambiar
