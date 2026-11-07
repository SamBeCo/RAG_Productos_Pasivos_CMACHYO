"""Paso 4: genera data/politicas_riesgo.pdf a partir de rules/politicas.py.

Uso:   python -m rules.generar_pdf

En un banco real el PDF ya existe (lo publica el área de Riesgos). Aquí lo generamos para que el laboratorio sea
reproducible y para que el texto del PDF y las guardas del código salgan de la misma fuente.
`invariant=1` hace que el PDF sea idéntico byte a byte en cada ejecución (sin fecha de creación ni id aleatorio).
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from app.config import DATA_DIR
from rules import politicas

ENCABEZADO_ARTICULO = "Artículo {id} - {titulo}"   # app/ingesta.py corta el texto del PDF por este patrón


def _pie(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, 1.2 * cm, f"{politicas.ENTIDAD} · {politicas.VERSION}")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def generar(destino: Path) -> Path:
    estilos = getSampleStyleSheet()
    cap = ParagraphStyle("cap", parent=estilos["Heading1"], fontSize=15, spaceBefore=6, spaceAfter=8)
    art = ParagraphStyle("art", parent=estilos["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=3)
    cuerpo = ParagraphStyle("cuerpo", parent=estilos["BodyText"], fontSize=10, leading=14)

    historia = [Paragraph(politicas.TITULO, estilos["Title"]),
                Paragraph(f"{politicas.ENTIDAD} · {politicas.VERSION}", estilos["Italic"]),
                Spacer(1, 0.4 * cm),
                Paragraph("Documento ficticio creado para un laboratorio académico. No representa la política de "
                          "ninguna entidad financiera real.", cuerpo),
                Spacer(1, 0.6 * cm)]
    for i, capitulo in enumerate(politicas.CAPITULOS):
        if i in (2, 4):                      # saltos de página para que el RAG tenga artículos en varias páginas
            historia.append(PageBreak())
        historia.append(Paragraph(f"Capítulo {capitulo['numero']}. {capitulo['titulo']}", cap))
        for a in capitulo["articulos"]:
            historia.append(Paragraph(ENCABEZADO_ARTICULO.format(**a), art))
            historia.append(Paragraph(a["texto"], cuerpo))

    destino.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(destino), pagesize=A4, title=politicas.TITULO, author=politicas.ENTIDAD,
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm, invariant=1)
    doc.build(historia, onFirstPage=_pie, onLaterPages=_pie)
    return destino


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "politicas_riesgo.pdf"
    ruta = generar(destino)
    print(f"PDF generado: {ruta.relative_to(Path.cwd()) if ruta.is_relative_to(Path.cwd()) else ruta}")
    print(f"  {len(politicas.articulos())} artículos en {len(politicas.CAPITULOS)} capítulos, {ruta.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
