"""Reglas que evitan los errores típicos de Windows. Si alguna falla, el código funcionaría en macOS/Linux y fallaría en Windows."""
import re

from app.config import BASE_DIR

FUENTES = sorted(p for carpeta in ("app", "rules", "eval", "scripts", "loadgen") for p in (BASE_DIR / carpeta).glob("*.py"))


def test_todo_acceso_a_archivos_de_texto_declara_encoding():
    """Sin encoding=, Python usa la página de códigos de Windows (cp1252): las tildes y la ñ se corrompen o fallan."""
    mal = []
    for f in FUENTES:
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            binario = re.search(r'\.open\(["\'][^"\']*b', linea)
            if re.search(r"\.(read_text|write_text)\(|\bopen\(", linea) and "encoding=" not in linea and not binario:
                mal.append(f"{f.relative_to(BASE_DIR)}:{n}: {linea.strip()}")
    assert not mal, "\n".join(mal)


def test_los_archivos_que_se_escriben_fijan_el_salto_de_linea():
    mal = [f.name for f in FUENTES if re.search(r'(write_text\(|open\([^)]*"[aw]")', f.read_text(encoding="utf-8"))
           and 'newline="\\n"' not in f.read_text(encoding="utf-8")]
    assert not mal, mal


def test_la_consola_no_usa_secuencias_ansi():
    for f in FUENTES:
        texto = f.read_text(encoding="utf-8")
        assert "\\x1b" not in texto and "\\033" not in texto, f.name


def test_archivos_que_lee_docker_tienen_finales_LF():
    """Si Git en Windows convierte a CRLF, un YAML o un script de shell dentro del contenedor (Linux) puede fallar."""
    for p in [BASE_DIR / "Dockerfile", BASE_DIR / "docker-compose.yml", *BASE_DIR.glob("prometheus/*.yml"),
              *BASE_DIR.glob("grafana/**/*.yml"), *BASE_DIR.glob("grafana/**/*.json")]:
        assert b"\r\n" not in p.read_bytes(), p.name
    assert "eol=lf" in (BASE_DIR / ".gitattributes").read_text(encoding="utf-8")


def test_los_textos_que_se_imprimen_caben_en_cp1252():
    """En Windows, si rediriges la salida (python -m eval.eval_router > r.txt) Python escribe en cp1252, no en UTF-8.
    Un carácter fuera de cp1252 ("→", "≠", "✓") hace caer el script con UnicodeEncodeError. Se verificó con
    PYTHONIOENCODING=cp1252: eval_router fallaba por "→" antes de esta prueba. Las tildes, la ñ, "·" y "…" sí caben."""
    import ast
    mal = []
    for f in FUENTES:
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(arbol)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
                try:
                    n.value.encode("cp1252")
                except UnicodeEncodeError:
                    mal.append(f"{f.relative_to(BASE_DIR)}:{n.lineno}: {n.value[:60]!r}")
    assert not mal, "\n".join(mal)
