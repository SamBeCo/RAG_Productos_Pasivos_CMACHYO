"""Guardas deterministas sobre la respuesta del LLM (criterio C6: seguridad, privacidad y guardas).

El LLM propone; este módulo decide. Ninguna regla de aquí consulta al modelo: son funciones puras sobre
el texto de la respuesta, el corpus ya ingestado y las páginas físicas del PDF.

Guardas:

  G0 · ALCANCE     Si la pregunta no toca nada del corpus, no hay respuesta que dar: abstención.
  G1 · CITAS       La página que declara una cita debe ser la página donde vive el texto citado. La ingesta
                   guarda la página donde empieza la sección, pero el texto de un fragmento se derrama a la
                   página siguiente: sin esta guarda, la cita miente.
  G2 · GROUNDING   Toda cifra de la respuesta debe existir en el corpus. Si el modelo calcula (TCEA, un
                   total, una diferencia) y ese número no está en el documento, no se publica.
  G3 · RESERVAS    El corpus separa el tarifario real (Banco A) de los supuestos ficticios (Banco B). La
                   respuesta debe decirlo, y debe decirlo aunque el modelo no lo haga.
  G4 · ABSTENCIÓN  Si G2 falla, se devuelve una abstención escrita en código, no una respuesta del modelo.
  G5 · DATO NO DISPONIBLE  Si el propio documento dice que esa magnitud no está disponible ("No se puede
                   calcular con la información disponible"), la respuesta honesta es la abstención.

El patrón es el de `app/guardas.py` (piso + más estricto) aplicado al lado de la respuesta: si el modelo
propone algo que el corpus no sostiene, el piso determinista manda.

Verificado sobre los 22 casos de `data/rag_gold.json` en `docs/specs/2026-11-05-c6-validacion-gold-22.md`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from app import metricas

ESTADO_PUBLICAR = "PUBLICAR"
ESTADO_CON_RESERVA = "PUBLICAR_CON_RESERVA"
ESTADO_ABSTENER = "ABSTENER"
ESTADOS = (ESTADO_PUBLICAR, ESTADO_CON_RESERVA, ESTADO_ABSTENER)

# --- qué dice el corpus sobre el origen de sus cifras ---------------------------------------------------------------
REAL_TARIFARIO = "tarifario compartido"      # "Banco A: tarifario compartido"
FICTICIO_SUPUESTO = "supuesto ficticio"       # "Banco B: supuesto ficticio"
FICTICIO_TEA = "tea ficticia"                 # "Banco A: TEA ficticia | Banco B: TEA ficticia"
FICTICIO_INVENTADAS = "tasas inventadas"      # "Son tasas inventadas para el ejercicio"

# Advertencias del propio documento: la fuente es incompleta y hay que decirlo. Cada advertencia se
# aplica a la fila donde vive (sus cifras), no a todo el documento.
ADVERTENCIAS_CORPUS = ("no permite confirmar", "no permite identificar")
VENTANA_AVISO = 60            # caracteres antes de la advertencia: las cifras de esa fila

# Advertencias FUERTES: el documento declara que esa magnitud no está disponible. Ahí la respuesta
# correcta es la abstención, no una respuesta con reserva.
MARCADORES_ABSTENCION = ("no se puede calcular", "no permite identificar una tabla")
MOTIVO_ABSTENCION = {
    "no se puede calcular": "el propio documento indica que no se puede calcular con la información disponible",
    "no permite identificar una tabla": "el propio documento advierte que no permite identificar una tabla completa de tasas",
}
VENTANA_DATO = 120          # caracteres antes del marcador donde se busca el nombre de la magnitud faltante

# Una fila del tarifario con el mismo valor repetido en todos los tramos no permite discriminar el monto.
RX_FILA_UNIFORME = re.compile(r"(\d+\.\d+%)(\s+\1){2,}")

# Palabras vacías: no son evidencia aunque aparezcan en pocas páginas.
STOPWORDS = {
    "con", "para", "por", "que", "como", "mas", "pero", "sus", "una", "uno", "dos", "tres", "cual",
    "cuales", "este", "esta", "esto", "ese", "esa", "entre", "sobre", "cuando", "donde", "hay", "son",
    "fue", "dan", "debe", "tengo", "tiene", "tienen", "hace", "muy", "todo", "toda", "todos", "todas",
    "mismo", "misma", "aquel", "cuanto", "cuanta", "segun", "según", "tambien", "también", "otro",
    "otra", "del", "las", "los", "sin", "nada", "algo", "algun", "alguna", "cada", "solo", "único",
}

RX_CITACION = re.compile(r"(?:art\.|p[áa]g\.?|p[áa]gs\.)\s*\d+(?:\.\d+)?", re.I)
RX_NUMERO = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
RX_PALABRA = re.compile(r"[a-z]+")
RX_TOKEN = re.compile(r"[a-z0-9]+")
RX_ACRONIMO = re.compile(r"\b[A-Z]{3,}\b")


def normalizar(texto: str) -> str:
    """Sin acentos, con guiones unificados y espacios colapsados. Todo el cotejo de textos pasa por aquí."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace(chr(0x2013), "-").replace(chr(0x2014), "-").replace(chr(0x2212), "-").replace(chr(0x00a0), " ")
    return re.sub(r"\s+", " ", t).strip()


def numeros(texto: str) -> set[str]:
    """Literales numéricos de un texto: 0.30%, S/ 5, US$ 1.06, S/ 300–3,000 -> {'0.30','5','1.06','300','3,000'}.

    Se ignoran los números de las citas ('Art. 1', 'pág. 2'): no son cifras de la respuesta."""
    limpio = RX_CITACION.sub(" ", normalizar(texto))
    return {m.group(0) for m in RX_NUMERO.finditer(limpio)}


def numeros_en_orden(texto: str) -> list[str]:
    """Los mismos literales numéricos, pero en el orden en que aparecen en el texto."""
    limpio = RX_CITACION.sub(" ", normalizar(texto))
    return [m.group(0) for m in RX_NUMERO.finditer(limpio)]


def palabras(texto: str) -> set[str]:
    """Palabras de longitud >= 3, sin acentos, en minúsculas."""
    return {w for w in RX_PALABRA.findall(normalizar(texto).lower()) if len(w) >= 3 and w not in STOPWORDS}


def ngrams(texto: str, n: int) -> set[tuple[str, ...]]:
    """Secuencias de n palabras consecutivas.

    Sirven para distinguir contextos que comparten los mismos números: '1080 días a más' (pág. 2 del PDF) no
    es lo mismo que '720–1080 días' (pág. 1), aunque ambas filas traigan 1.00%."""
    toks = RX_TOKEN.findall(normalizar(texto).lower())
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


@dataclass
class Resultado:
    """Lo que las guardas decida sobre una respuesta."""
    estado: str
    respuesta: str
    motivo: str = ""
    reservas: list[str] = field(default_factory=list)
    cifras_sin_grounding: list[str] = field(default_factory=list)
    citas: list[dict] = field(default_factory=list)

    @property
    def publicable(self) -> bool:
        return self.estado in (ESTADO_PUBLICAR, ESTADO_CON_RESERVA)


class PaginasPDF:
    """Las páginas físicas del PDF, para resolver la página real de una cita.

    Se leen del PDF (no del índice) porque el índice solo guarda la página donde empieza cada sección:
    con 3 páginas leerlas de nuevo es más barato que cambiar el formato del índice.
    """

    def __init__(self, pdf_path: Path | str | None = None):
        self.textos: list[str] = []
        self.numeros: list[set[str]] = []
        self.palabras: list[set[str]] = []
        self._df: dict[str, int] | None = None
        self._ng: dict[tuple[int, int], set[tuple[str, ...]]] = {}
        if pdf_path is None:
            return
        try:
            from pypdf import PdfReader

            for hoja in PdfReader(str(pdf_path)).pages:
                t = normalizar(hoja.extract_text() or "")
                self.textos.append(t)
                self.numeros.append(numeros(t))
                self.palabras.append(palabras(t))
        except Exception:                       # sin PDF legible: el sistema funciona, sin corregir páginas
            self.textos = []
            self.numeros = []
            self.palabras = []

    @property
    def n(self) -> int:
        return len(self.textos)

    def _frecuencia(self) -> dict[str, int]:
        if self._df is None:
            df: dict[str, int] = {}
            for ps in self.palabras:
                for w in ps:
                    df[w] = df.get(w, 0) + 1
            self._df = df
        return self._df

    def df(self, palabra: str) -> int:
        """En cuántas páginas del PDF aparece la palabra. 1 = vive en una sola página."""
        return self._frecuencia().get(palabra, 0)

    def palabras_informativas(self, texto: str) -> set[str]:
        """Palabras del texto que no están en todas las páginas: son las que localizan la evidencia.

        'tasa' aparece en las 3 páginas -> no dice nada. 'TCEA' aparece en una -> sí dice."""
        df = self._frecuencia()
        return {w for w in palabras(texto) if df.get(w, 0) < self.n}

    def tokens(self, pagina: int) -> set[str]:
        """Cifras y palabras informativas de una página (1-indexada)."""
        i = pagina - 1
        if not (0 <= i < self.n):
            return set()
        return self.numeros[i] | {w for w in self.palabras[i] if self._frecuencia().get(w, 0) < self.n}

    def ngrams(self, pagina: int, n: int) -> set[tuple[str, ...]]:
        """Secuencias de n palabras de una página (1-indexada)."""
        i = pagina - 1
        if not (0 <= i < self.n):
            return set()
        clave = (i, n)
        if clave not in self._ng:
            self._ng[clave] = ngrams(self.textos[i], n)
        return self._ng[clave]


class GuardasRespuesta:
    """Aplica las guardas a una respuesta del LLM, sobre un corpus ya ingestado."""

    def __init__(self, fragmentos, paginas: PaginasPDF | None = None):
        self.fragmentos = list(fragmentos)
        self.paginas = paginas if paginas is not None else PaginasPDF(None)
        self.texto_corpus = " ".join(f.texto for f in self.fragmentos)
        self.numeros_corpus = numeros(self.texto_corpus)
        # El vocabulario del corpus incluye los TÍTULOS de los fragmentos: en el manual de políticas el
        # artículo se titula 'Documentos' y el cuerpo empieza con 'Dependientes: DNI vigente...'.
        self.palabras_corpus = palabras(self.texto_corpus + " " + " ".join(f.titulo for f in self.fragmentos))
        self._por_id = {f.id: f for f in self.fragmentos}
        self._filas_uniformes = self._detectar_filas_uniformes()
        self._span = self._calcular_spans()

    def _detectar_filas_uniformes(self) -> list[tuple[str, str]]:
        """Filas del tarifario con el mismo valor repetido en todos los tramos: (porcentaje, rótulo de la fila).

        La fila anómala del corpus es '1080 días a más -> 1.00% x 6': el rótulo ('1080') es lo que
        distingue esa fila de cualquier otra que mencione 1.00% (por ejemplo, la comisión de S/ 1.00
        del agente Kasnet)."""
        texto = normalizar(self.texto_corpus)
        filas: list[tuple[str, str]] = []
        for m in RX_FILA_UNIFORME.finditer(texto):
            antes = numeros_en_orden(texto[max(0, m.start() - VENTANA_AVISO):m.start()])
            if antes:
                filas.append((m.group(1).rstrip("%"), antes[-1]))
        return filas

    # ------------------------------------------------------------------ páginas de cada fragmento
    def _calcular_spans(self) -> dict[str, tuple[int, int]]:
        """Rango de páginas que ocupa cada fragmento.

        La ingesta etiqueta el fragmento con la página de su TÍTULO (app/ingesta.py:45-57) y el texto sigue
        acumulándose en las páginas siguientes. El fragmento i ocupa [p_i, p_{i+1}]: con el corpus de
        benchmarking, el fragmento 1 ocupa las páginas 1-2 y el 2 las páginas 2-3."""
        orden = sorted(self.fragmentos, key=lambda f: (f.pagina, f.id))
        ultima = self.paginas.n or (orden[-1].pagina if orden else 1)
        spans: dict[str, tuple[int, int]] = {}
        for i, f in enumerate(orden):
            fin = orden[i + 1].pagina if i + 1 < len(orden) else ultima
            spans[f.id] = (f.pagina, max(f.pagina, min(fin, ultima)))
        return spans

    # ------------------------------------------------------------------ G2 · grounding
    def cifras_sin_grounding(self, respuesta: str) -> list[str]:
        return sorted(numeros(respuesta) - self.numeros_corpus)

    # ------------------------------------------------------------------ G3 · reservas
    def _tipo_fragmento(self, f) -> str:
        t = normalizar(f.texto).lower()
        if FICTICIO_TEA in t or FICTICIO_INVENTADAS in t:
            return "FICTICIO"
        if FICTICIO_SUPUESTO in t:
            return "MIXTO"
        return "REAL"

    def _avisos_del_fragmento(self, f) -> list[set[str]]:
        """Para cada advertencia del corpus, las cifras a las que se refiere (la fila donde vive).

        'no permite confirmar otros detalles' es una advertencia de la fila del Ahorro Cash (0.10%), no
        de todo el documento: si la respuesta habla de otra cosa, esa advertencia no va con ella."""
        texto = normalizar(f.texto)
        bajo = texto.lower()
        avisos: list[set[str]] = []
        for aviso in ADVERTENCIAS_CORPUS:
            i = bajo.find(aviso)
            while i != -1:
                avisos.append(numeros(texto[max(0, i - VENTANA_AVISO):i]))
                i = bajo.find(aviso, i + 1)
        return avisos

    def _reservas(self, respuesta: str, citados: list, pregunta: str = "") -> list[str]:
        reservas: list[str] = []
        texto = normalizar(respuesta).lower()
        cifras = numeros(respuesta)
        cifras_pregunta = numeros(pregunta)
        for f in citados:
            tipo = self._tipo_fragmento(f)
            frag = normalizar(f.texto).lower()
            if tipo == "FICTICIO":
                reservas.append("Las tasas de este apartado son ficticias: el documento las inventó para el "
                                "ejercicio. No son tarifas reales de ningún banco.")
            elif tipo == "MIXTO" and "banco b" in texto:
                reservas.append("Las cifras de Banco B de este apartado son un supuesto ficticio del ejercicio; "
                                "solo las de Banco A provienen del tarifario real.")
            for aviso in self._avisos_del_fragmento(f):
                if cifras & aviso:
                    reservas.append("El propio documento advierte que no permite confirmar toda la información de "
                                    "este apartado.")
                    break
        for pct, rotulo in self._filas_uniformes:
            if pct in cifras and (rotulo in cifras or rotulo in cifras_pregunta):
                reservas.append("La fila del tarifario es uniforme en todos los tramos de monto: el dato no "
                                "permite discriminar por monto y debe confirmarse con el tarifario original.")
        return list(dict.fromkeys(reservas))

    # ------------------------------------------------------------------ G5 · la magnitud no está disponible
    def _datos_no_disponibles(self, f) -> dict[str, str]:
        """Magnitudes que el propio documento declara no disponibles, con su motivo.

        El corpus lo dice con sus palabras: '...conviene solicitar la TCEA... No se puede calcular con la
        información disponible' y 'CTS ... no permite identificar una tabla completa de tasas'. Si la pregunta
        pide ESA magnitud, la respuesta honesta es la abstención."""
        texto = normalizar(f.texto)
        bajo = texto.lower()
        datos: dict[str, str] = {}
        for marcador in MARCADORES_ABSTENCION:
            i = bajo.find(marcador)
            while i != -1:
                antes = texto[max(0, i - VENTANA_DATO):i]
                acronimos = RX_ACRONIMO.findall(antes)
                if acronimos:
                    datos[acronimos[-1]] = marcador
                i = bajo.find(marcador, i + 1)
        return datos

    def _abstencion_por_dato(self, pregunta: str) -> tuple[str, str] | None:
        """(magnitud, motivo) si la pregunta pide algo que el documento declara no disponible.

        Se recorre TODO el corpus, no solo los fragmentos citados: el documento declara esa limitación a
        escala del documento (la advertencia de la TCEA está al final del apartado de créditos)."""
        consultada = normalizar(pregunta).lower()
        for f in self.fragmentos:
            for dato, marcador in self._datos_no_disponibles(f).items():
                if re.search(rf"\b{re.escape(dato.lower())}\b", consultada):
                    return dato, marcador
        return None

    # ------------------------------------------------------------------ G0 · la pregunta fuera del corpus
    def _fuera_de_corpus(self, pregunta: str) -> bool:
        """True si ningún término de peso de la pregunta aparece en el corpus.

        '¿A qué hora cierra la agencia de Huancayo?' no tiene ni una palabra en el documento de
        benchmarking: la respuesta honesta es abstención, no una invención."""
        toks = {t for t in RX_PALABRA.findall(normalizar(pregunta).lower())
                if len(t) >= 4 and t not in STOPWORDS}
        if len(toks) < 2:
            return False
        return not (toks & self.palabras_corpus)

    # ------------------------------------------------------------------ G1 · citas
    def _frase_propia(self, grams: set) -> bool:
        """True si alguna de las frases contiene una palabra que vive en una sola página del PDF.

        'préstamo personal' (pág. 2) es una frase de la pregunta que no está en ninguna otra página:
        identifica esa página. 'de banco' aparece en varias: no identifica nada."""
        return any(self.paginas.df(w) == 1 for g in grams for w in g)

    def _resolver_paginas(self, f, ev_num: set[str], ev_pal_q: set[str], ev_pal_full: set[str],
                          acronimos: set[str], ng2: set, ng3: set) -> list[int]:
        """Páginas donde vive el texto citado, no la página donde empieza la sección.

        La página principal es la que más evidencia tiene de LO QUE SE PREGUNTA: las palabras de la
        pregunta (más suyas que de la respuesta, porque el modelo puede citar de memoria una frase del
        documento que vive en otra página), las frases exactas de la pregunta, las cifras de la respuesta
        (que G2 ya verificó contra el corpus) y los acrónimos de la pregunta ('CTS', 'TCEA').

        Además cita una segunda página solo si en ella hay evidencia que la principal no tiene y que es
        específica de la pregunta: un acrónimo de la pregunta o una frase que solo vive en esa página."""
        if not self.paginas.n:
            return [f.pagina]
        ini, fin = self._span.get(f.id, (f.pagina, f.pagina))
        hits: dict[int, dict] = {}
        for p in range(ini, fin + 1):
            nums = self.paginas.numeros[p - 1]
            pals = self.paginas.palabras[p - 1]
            comunes = (ev_num & nums) | (ev_pal_q & pals)
            full = (ev_num & nums) | (ev_pal_full & pals)
            g2 = self.paginas.ngrams(p, 2) & ng2
            g3 = self.paginas.ngrams(p, 3) & ng3
            if not full and not g2 and not g3:
                continue
            score = (2 * len(comunes & nums) + len(comunes - nums) + len(g2) + 3 * len(g3)
                     + 5 * len(acronimos & pals))
            hits[p] = {"comunes": comunes, "full": full, "g2": g2, "g3": g3, "score": score}
        if not hits:
            return [f.pagina]
        top = max(hits.items(), key=lambda kv: (kv[1]["score"], -kv[0]))   # más evidencia; a empate, la menor página
        paginas = [top[0]]
        base = hits[top[0]]
        for p, h in sorted(hits.items()):
            if p == top[0]:
                continue
            exclusivos = h["full"] - base["full"]
            frases_propias = ((h["g2"] - base["g2"]) | (h["g3"] - base["g3"]))
            if (exclusivos & acronimos) or self._frase_propia(frases_propias):
                paginas.append(p)
        return sorted(paginas)

    def resolver_citas(self, respuesta: str, citas_ids: list[str], pregunta: str = "") -> list[dict]:
        """Citas de una respuesta con la página real de cada fragmento citado."""
        citados = [self._por_id[i] for i in (citas_ids or []) if i in self._por_id]
        return self._citas(respuesta, pregunta, citados)

    def _citas(self, respuesta: str, pregunta: str, citados: list) -> list[dict]:
        citas: list[dict] = []
        texto_evidencia = f"{pregunta} {respuesta}"
        acronimos = {a.lower() for a in RX_ACRONIMO.findall(normalizar(pregunta))}
        # Las frases se toman de la PREGUNTA, no de la respuesta: el modelo puede citar de memoria una
        # frase del documento que vive en otra página ('para comparar el costo real', pág. 3) mientras lo
        # que el asesor pregunta está en otra ('Préstamo personal', pág. 2).
        ng2 = ngrams(pregunta, 2)
        ng3 = ngrams(pregunta, 3)
        for f in citados:
            ev_num = numeros(texto_evidencia) & numeros(f.texto)
            ev_pal_q = self.paginas.palabras_informativas(pregunta) & palabras(f.texto)
            ev_pal_full = self.paginas.palabras_informativas(texto_evidencia) & palabras(f.texto)
            paginas = self._resolver_paginas(f, ev_num, ev_pal_q, ev_pal_full, acronimos, ng2, ng3)
            cita = {"id": f.id, "titulo": f.titulo, "pagina": paginas[0], "paginas": paginas,
                    "pagina_declarada": f.pagina, "texto": f.texto}
            if paginas != [f.pagina]:
                metricas.CITA_PAGINA_CORREGIDA.inc()
            citas.append(cita)
        return citas

    # ------------------------------------------------------------------ decisión
    def revisar(self, respuesta: str, citas_ids: list[str] | None = None, pregunta: str = "") -> Resultado:
        """Aplica las guardas a una respuesta. `citas_ids` son los ids de fragmento citados por el LLM."""
        citados = [self._por_id[i] for i in (citas_ids or []) if i in self._por_id]
        citas = self._citas(respuesta, pregunta, citados)

        # G0 · la pregunta no toca el corpus: no hay nada que publicar.
        if self._fuera_de_corpus(pregunta):
            texto = ("No encuentro en el documento de benchmarking ningún contenido que dé respuesta a esa "
                     "pregunta. Prefiero devolverte una abstención antes que inventar una respuesta.")
            metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
            return Resultado(ESTADO_ABSTENER, texto, "fuera_de_alcance", [], [], citas)

        # Sin citas no hay evidencia que verificar: la respuesta del modelo no se puede sostener.
        if not citados:
            texto = ("La respuesta no cita ningún artículo del documento de benchmarking, así que no hay "
                     "evidencia que verificar. Devuelvo una abstención en lugar de una afirmación sin respaldo.")
            metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
            return Resultado(ESTADO_ABSTENER, texto, "sin_citas", [], [], citas)

        # G5 · el propio documento declara que esa magnitud no está disponible.
        dato = self._abstencion_por_dato(pregunta)
        if dato:
            magnitud, marcador = dato
            texto = (f"No puedo determinar {magnitud} con la información del documento de benchmarking: "
                     f"{MOTIVO_ABSTENCION.get(marcador, marcador)}. Te devuelvo esa abstención en lugar de "
                     f"una cifra sin respaldo.")
            metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
            return Resultado(ESTADO_ABSTENER, texto, "dato_no_disponible", [], [], citas)

        # G2 · toda cifra de la respuesta tiene que existir en el corpus.
        sin_grounding = self.cifras_sin_grounding(respuesta)
        if sin_grounding:
            texto = ("No puedo sostener esa respuesta con el documento de benchmarking: incluye cifras que no "
                     "aparecen en el corpus (" + ", ".join(sin_grounding) + "). Prefiero devolverte una abstención "
                     "con la evidencia disponible antes que una afirmación sin respaldo.")
            metricas.GUARDA_CIFRAS.inc(len(sin_grounding))
            metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
            return Resultado(ESTADO_ABSTENER, texto, "cifra_sin_grounding", [], sin_grounding, citas)

        # G3 · reservas: el corpus es explícito sobre qué es real y qué es inventado.
        reservas = self._reservas(respuesta, citados, pregunta)
        if reservas:
            for r in reservas:
                metricas.GUARDA_RESERVAS.labels(_tipo_reserva(r)).inc()
        metricas.GUARDA_RESPUESTA.labels(ESTADO_CON_RESERVA if reservas else ESTADO_PUBLICAR).inc()
        return Resultado(ESTADO_CON_RESERVA if reservas else ESTADO_PUBLICAR, respuesta,
                         "reserva" if reservas else "", reservas, [], citas)


def _tipo_reserva(reserva: str) -> str:
    if "inventó" in reserva or "inventadas" in reserva:
        return "ficticio_total"
    if "supuesto ficticio" in reserva:
        return "dato_ficticio"
    if "advierte" in reserva:
        return "documento_incompleto"
    if "uniforme" in reserva:
        return "fila_uniforme"
    return "otra"


def formatear_cita(cita: dict) -> str:
    """Formatea una referencia de PDF o de una fuente de oficina."""
    documento = cita.get("documento")
    ubicacion = cita.get("ubicacion")
    if documento:
        return f"{documento} · {ubicacion or cita.get('titulo', 'sección')}"
    paginas = cita.get("paginas") or [cita.get("pagina", 1)]
    if len(paginas) == 1:
        pag = f"pág. {paginas[0]}"
    elif paginas == list(range(paginas[0], paginas[-1] + 1)):
        pag = f"pág. {paginas[0]}-{paginas[-1]}"
    else:
        pag = "pág. " + ", ".join(str(p) for p in paginas)
    return f"Art. {cita['id']} ({cita['titulo']}, {pag})"


RX_RECOMENDACION = re.compile(
    r"\b(te recomiendo|le recomiendo|recomiendo (?:que|elegir|contratar|abrir)|te conviene|le conviene|"
    r"conviene (?:mas|más|elegir|contratar|abrir)|deberias|debería|deberia|mejor opcion|mejor opción|"
    r"la mejor (?:cuenta|alternativa|opcion|opción)|elige|elija|opta por|opte por|lo ideal es)\b",
    re.IGNORECASE)


def detecta_recomendacion(texto: str) -> bool:
    """El comparador describe diferencias documentadas; no aconseja qué producto contratar."""
    return bool(RX_RECOMENDACION.search(texto or ""))


def revisar_respuesta_documental(respuesta: str, pregunta: str, citados: list,
                                 fallo_llm: bool = False, comparacion: bool = False) -> Resultado:
    """Valida las citas y cifras de una respuesta contra los fragmentos que la sustentan."""
    if not citados:
        texto = "No puedo publicar una respuesta sin referencias verificables en las fuentes indexadas."
        metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
        return Resultado(ESTADO_ABSTENER, texto, "sin_citas")

    evidencia = " ".join(f"{f.titulo} {f.texto}" for f in citados)
    sin_grounding = sorted(numeros(respuesta) - numeros(evidencia))
    citas = [{
        "id": f.id,
        "titulo": f.titulo,
        "documento": f.documento or "",
        "pagina": f.pagina,
        "paginas": [f.pagina] if f.pagina is not None else [],
        "ubicacion": f.ubicacion or (f"pág. {f.pagina}" if f.pagina is not None else f.titulo),
        "texto": f.texto,
        "score": f.score,
    } for f in citados]
    if fallo_llm:
        metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
        return Resultado(
            ESTADO_ABSTENER,
            "No pude generar una respuesta verificable. La consulta quedó disponible para revisión humana.",
            "fallo_llm",
            [],
            [],
            citas,
        )
    if comparacion and detecta_recomendacion(respuesta):
        metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
        return Resultado(
            ESTADO_ABSTENER,
            "El comparador solo presenta diferencias documentadas y no recomienda qué producto contratar. "
            "La consulta quedó disponible para revisión humana.",
            "recomendacion_personalizada", [], [], citas)
    if sin_grounding:
        metricas.GUARDA_CIFRAS.inc(len(sin_grounding))
        metricas.GUARDA_RESPUESTA.labels(ESTADO_ABSTENER).inc()
        texto = ("No puedo sostener esa respuesta con los fragmentos citados: contiene cifras sin respaldo "
                 f"({', '.join(sin_grounding)}). Prefiero abstenerme antes que inventar un dato.")
        return Resultado(ESTADO_ABSTENER, texto, "cifra_sin_grounding", [],
                         sin_grounding, citas)
    metricas.GUARDA_RESPUESTA.labels(ESTADO_PUBLICAR).inc()
    return Resultado(ESTADO_PUBLICAR, respuesta, "", [], [], citas)