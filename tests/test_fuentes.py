from reportlab.pdfgen import canvas

from app.fuentes import leer_fuente, leer_pdf
from app.ingesta import DOCUMENTOS_INICIALES, descubrir_fuentes


def test_corpus_inicial_usa_las_cuatro_fuentes_y_excluye_el_pdf_heredado(settings, tmp_path):
    settings.pdf_path = None
    settings.uploads_dir = tmp_path / "uploads"
    fuentes = descubrir_fuentes(settings)
    assert {ruta.name for ruta in fuentes} == set(DOCUMENTOS_INICIALES)
    assert all(ruta.suffix.lower() in {".docx", ".xlsx", ".pdf"} for ruta in fuentes)
    assert not any(ruta.name.lower() == "documentos_caja_huancayo.pdf" for ruta in fuentes)


def test_todas_las_fuentes_iniciales_extraen_texto_y_ubicacion(settings, tmp_path):
    settings.pdf_path = None
    settings.uploads_dir = tmp_path / "uploads"
    for ruta in descubrir_fuentes(settings):
        unidades = leer_fuente(ruta)
        assert unidades, ruta.name
        assert all(unidad["texto"].strip() for unidad in unidades), ruta.name
        assert all(unidad["ubicacion"] for unidad in unidades), ruta.name


def test_pdf_conserva_texto_y_pagina_de_la_seccion(tmp_path):
    ruta = tmp_path / "prueba.pdf"
    pdf = canvas.Canvas(str(ruta))
    pdf.drawString(72, 760, "Articulo 1 - Cuenta de ahorro")
    pdf.drawString(72, 730, "Texto de inicio de la unidad")
    pdf.showPage()
    pdf.drawString(72, 760, "Continuacion de la misma unidad")
    pdf.showPage()
    pdf.drawString(72, 760, "2. Seccion siguiente")
    pdf.drawString(72, 730, "Contenido de la segunda seccion")
    pdf.save()

    unidades = leer_pdf(ruta)
    assert len(unidades) == 2
    assert unidades[0]["pagina"] == 1
    assert unidades[0]["ubicacion"] == "pág. 1-2"
    assert "Texto de inicio" in unidades[0]["texto"]
    assert "Continuacion de la misma unidad" in unidades[0]["texto"]
    assert unidades[1]["pagina"] == 3
    assert "Contenido de la segunda seccion" in unidades[1]["texto"]
