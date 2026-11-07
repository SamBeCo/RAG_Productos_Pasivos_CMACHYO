"""Lectores locales para las fuentes de productos pasivos."""
from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from pypdf import PdfReader

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
RX_SECCION = re.compile(
    r"^(?:art[ií]culo\s+[\w.-]+(?:\s*[-.:]\s*.+)?|"
    r"(?:[IVXLCDM]+|\d+(?:\.\d+)*)\s*[.)-]\s+\S.*)$",
    re.IGNORECASE,
)


def _texto_parrafo(elemento: ET.Element) -> str:
    return " ".join((n.text or "").strip() for n in elemento.iter(W + "t") if (n.text or "").strip())


def leer_docx(ruta: Path) -> list[dict]:
    unidades: list[dict] = []
    with zipfile.ZipFile(ruta) as doc:
        raiz = ET.fromstring(doc.read("word/document.xml"))
    cuerpo = raiz.find(W + "body")
    if cuerpo is None:
        raise ValueError(f"{ruta.name}: no se encontró el cuerpo del documento.")
    seccion = ruta.stem
    numero_parrafo = 0
    numero_tabla = 0
    for hijo in cuerpo:
        if hijo.tag == W + "p":
            numero_parrafo += 1
            texto = _texto_parrafo(hijo)
            if not texto:
                continue
            estilo = hijo.find(f"{W}pPr/{W}pStyle")
            estilo_id = estilo.get(W + "val", "") if estilo is not None else ""
            es_titulo = estilo_id.lower().startswith(("heading", "title", "título", "titulo"))
            if es_titulo or RX_SECCION.match(texto) or (
                texto.isupper() and len(texto) <= 120 and any(c.isalpha() for c in texto)
            ):
                seccion = texto[:180]
                continue
            unidades.append({"titulo": seccion, "texto": texto, "pagina": None,
                             "ubicacion": f"{seccion} · párrafo {numero_parrafo}"})
        elif hijo.tag == W + "tbl":
            numero_tabla += 1
            for numero_fila, fila in enumerate(hijo.findall(f"{W}tr"), 1):
                celdas = []
                for celda in fila.findall(f"{W}tc"):
                    valor = " ".join(filter(None, (_texto_parrafo(p) for p in celda.findall(f"{W}p"))))
                    celdas.append(valor)
                texto = " | ".join(x for x in celdas if x)
                if texto:
                    if re.match(r"^(?:PRODUCTO|SUBPRODUCTO)\s*:\s*\|\s*[^|]{1,80}$", texto, re.IGNORECASE):
                        seccion = texto[:180]
                        continue
                    unidades.append({
                        "titulo": seccion, "texto": texto, "pagina": None,
                        "ubicacion": f"{seccion} · tabla {numero_tabla}, fila {numero_fila}",
                    })
    return unidades


def _shared_strings(libro: zipfile.ZipFile) -> list[str]:
    try:
        raiz = ET.fromstring(libro.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return ["".join(n.text or "" for n in si.iter(S + "t")) for si in raiz.findall(S + "si")]


def _valor_celda(celda: ET.Element, shared: list[str]) -> str:
    tipo = celda.get("t")
    if tipo == "inlineStr":
        return "".join(n.text or "" for n in celda.iter(S + "t")).strip()
    valor = celda.find(S + "v")
    if valor is None or valor.text is None:
        return ""
    if tipo == "s":
        return shared[int(valor.text)]
    return valor.text.strip()


def leer_xlsx(ruta: Path) -> list[dict]:
    unidades: list[dict] = []
    with zipfile.ZipFile(ruta) as libro:
        shared = _shared_strings(libro)
        workbook = ET.fromstring(libro.read("xl/workbook.xml"))
        try:
            relaciones = ET.fromstring(libro.read("xl/_rels/workbook.xml.rels"))
        except KeyError as e:
            raise ValueError(f"{ruta.name}: faltan las relaciones del libro.") from e
        destinos = {
            rel.get("Id"): rel.get("Target", "")
            for rel in relaciones.findall(PKG + "Relationship")
        }
        for hoja in workbook.findall(f"{S}sheets/{S}sheet"):
            relacion = hoja.get(R + "id")
            destino = destinos.get(relacion)
            if not destino:
                raise ValueError(f"{ruta.name}: hoja sin destino legible.")
            if destino.startswith("/"):
                archivo = destino.lstrip("/")
            else:
                archivo = posixpath.normpath(posixpath.join("xl", destino))
            raiz = ET.fromstring(libro.read(archivo))
            filas: list[tuple[int, dict[int, str]]] = []
            for fila in raiz.findall(f"{S}sheetData/{S}row"):
                numero = int(fila.get("r", "0"))
                valores = {}
                for celda in fila.findall(S + "c"):
                    referencia = celda.get("r", "")
                    letras = re.match(r"[A-Z]+", referencia)
                    if letras:
                        indice = 0
                        for letra in letras.group(0):
                            indice = indice * 26 + ord(letra) - ord("A") + 1
                        valores[indice - 1] = _valor_celda(celda, shared)
                if any(valores.values()):
                    filas.append((numero, valores))
            if not filas:
                continue
            encabezados = filas[0][1]
            for numero, valores in filas[1:]:
                campos = []
                for indice, valor in valores.items():
                    if not valor:
                        continue
                    encabezado = encabezados.get(indice) or f"Columna {indice + 1}"
                    campos.append(f"{encabezado}: {valor}")
                if campos:
                    nombre_hoja = hoja.get("name", "Hoja")
                    unidades.append({
                        "titulo": nombre_hoja, "texto": " | ".join(campos), "pagina": None,
                        "ubicacion": f"Hoja {nombre_hoja} · fila {numero}",
                    })
    return unidades


def leer_pdf(ruta: Path) -> list[dict]:
    unidades: list[dict] = []
    seccion = "Documento"
    texto_actual: list[str] = []
    pagina_inicio = 1
    paginas: list[int] = []

    def guardar() -> None:
        texto = " ".join(texto_actual).strip()
        if texto:
            paginas_unicas = sorted(set(paginas))
            lugar = f"pág. {paginas_unicas[0]}"
            if len(paginas_unicas) > 1:
                lugar += f"-{paginas_unicas[-1]}"
            unidades.append({"titulo": seccion, "texto": texto, "pagina": pagina_inicio,
                             "ubicacion": lugar})

    for numero, pagina in enumerate(PdfReader(str(ruta)).pages, 1):
        extraido = pagina.extract_text()
        if extraido is None:
            continue
        for linea in extraido.splitlines():
            linea = " ".join(linea.split())
            if not linea:
                continue
            if RX_SECCION.match(linea):
                guardar()
                seccion = linea[:180]
                texto_actual = []
                paginas = []
                pagina_inicio = numero
                texto_actual.append(linea)
                paginas.append(numero)
                continue
            if not texto_actual:
                pagina_inicio = numero
            texto_actual.append(linea)
            paginas.append(numero)
    guardar()
    return unidades


def leer_fuente(ruta: Path) -> list[dict]:
    sufijo = ruta.suffix.lower()
    if sufijo == ".pdf":
        return leer_pdf(ruta)
    if sufijo == ".docx":
        return leer_docx(ruta)
    if sufijo == ".xlsx":
        return leer_xlsx(ruta)
    raise ValueError(f"Formato no admitido: {ruta.suffix}")
