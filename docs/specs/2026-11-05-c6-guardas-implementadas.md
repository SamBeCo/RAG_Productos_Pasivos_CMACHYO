# C6 — Guardas deterministas sobre la respuesta: lo implementado

**Criterio:** C6 · Seguridad, privacidad y guardas · **peso 10 %**
**Fecha:** 5 de noviembre de 2026
**Estado:** **implementado y verificado** sobre los 22 casos de `data/rag_gold.json`.
**Base:** `main` @ `4e4053d` ("C7").

Documentos relacionados:

- [`docs/specs/2026-11-05-c6-seguridad-privacidad-guardas-design.md`](2026-11-05-c6-seguridad-privacidad-guardas-design.md) — diseño completo de las cuatro piezas de C6 (propuesta; las piezas 2, 3 y 4 siguen pendientes).
- [`docs/specs/2026-11-05-c6-validacion-gold-22.md`](2026-11-05-c6-validacion-gold-22.md) — validación del set de oro que motivations este módulo.
- [`docs/plans/2026-11-05-c6-plan.md`](../plans/2026-11-05-c6-plan.md) — plan por fases.

---

## 1. Qué se implementó (y qué no)

| Pieza de C6 | Estado | Dónde |
|---|---|---|
| **Guardas deterministas sobre el LLM** | ✅ **Implementada en el flujo vivo** | `app/guardas_respuesta.py` (nuevo), `app/agente_ahorro.py:144-167` |
| Enmascarado de datos personales | 🟡 Parcial (lo heredado: email/RUC/teléfono/DNI) | `app/privacidad.py` — **fuera de este trabajo** |
| Protección contra prompt injection | 🔴 Solo la marca de Jev (heredada) | `app/router.py:149-152` — **fuera de este trabajo** |
| Humano en el circuito | 🔴 Eliminado en el pivote (`2f8eee7`) | andamiaje vivo en `app/db.py:119-139` — **fuera de este trabajo** |

**Alcance de este trabajo:** las guardas de **grounding**, **citas**, **reservas** y **abstención** sobre las 22
preguntas del set de oro, con su interpretación determinista. El humano en el circuito **queda fuera de alcance**:
los 22 casos se resuelven automáticamente (ver §5); su lugar es en generalizaciones semánticas, que el set de oro
no cubre.

## 2. Decisiones de diseño que difieren del diseño original

El diseño (§4 del documento de diseño) proponía `NIVELES = ("PUBLICABLE", "REVISAR", "NO_PUBLICABLE")` con
`HallazgoGuarda` y escalación al analista. Al implementarlo contra el set de oro aparecieron tres cosas que
obligaron a cambiar la forma:

1. **El set de oro no tiene una categoría "revisar".** Los 22 casos son exactamente tres estados: publicar,
   publicar con reserva y abstener. La reserva es una **etiqueta que acompaña a la respuesta**, no un estado que
   bloquee: 17 de 22 respuestas son correctas con una advertencia encima. Implementar "revisar" habría creado una
   cuarta categoría sin ningún caso que la justifique.
2. **La derivación aritmética no se necesita.** El diseño (§4.3) preveía aceptar como respaldada una cifra que
   fuera suma o resta de dos cifras del corpus. Al medirlo: **0 de las 22 respuestas esperadas contienen una cifra
   derivada**; todas citan las cifras tal cual. La regla "toda cifra de la respuesta tiene que existir en el
   corpus" (G2) basta y no produce falsos positivos.
3. **La página de la cita no se puede resolver por búsqueda literal.** El texto de un fragmento aparece partido
   entre dos páginas ("91–180 días" en la 2, "Banco B: rango ficticio" en la 1). Resolver la página exige puntuar
   páginas, no buscar un literal (§4).

**Interfaz implementada** (`app/guardas_respuesta.py:115-126`):

```python
@dataclass
class Resultado:
    estado: str                 # PUBLICAR | PUBLICAR_CON_RESERVA | ABSTENER
    respuesta: str              # la respuesta final (o la abstención escrita en código)
    motivo: str = ""            # por qué: cifra_sin_grounding | dato_no_disponible | sin_citas | fuera_de_alcance | reserva
    reservas: list[str] = field(default_factory=list)
    cifras_sin_grounding: list[str] = field(default_factory=list)
    citas: list[dict] = field(default_factory=list)   # con la página REAL de cada fragmento
```

## 3. Las guardas, una por una

| Id | Guarda | Qué comprueba | Qué hace al disparar | Código |
|---|---|---|---|---|
| **G0** | `fuera_de_alcance` | Ningún término de peso de la pregunta aparece en el corpus (títulos incluidos) | Abstención con texto de código | `guardas_respuesta.py:329-339` |
| **G1** | `_resolver_paginas` | La página donde vive el texto citado | Corrige la página de la cita y la registra en métrica | `guardas_respuesta.py:348-386` |
| **G2** | `cifras_sin_grounding` | Toda cifra de la respuesta existe en el corpus | Abstención con texto de código | `guardas_respuesta.py:244-246`, `436-445` |
| **G3** | `_reservas` | La respuesta dice qué es real y qué es ficticio | Añade la reserva que falte | `guardas_respuesta.py:271-295` |
| **G4** | abstención | Es el mecanismo que reemplaza la respuesta del modelo por un texto determinista | — | `guardas_respuesta.py:416-463` |
| **G5** | `dato_no_disponible` | El propio documento declara que esa magnitud no está disponible | Abstención con texto de código | `guardas_respuesta.py:297-327` |

### 3.1 G1 · la página real de la cita

`app/ingesta.py:54` etiqueta cada fragmento con la página de su **título**, pero el texto se derrama a la página
siguiente: **6 de 22 casos (27 %) recibirían una cita con la página equivocada** (validación §5). La resolución:

1. Cada fragmento ocupa el rango `[p_i, p_{i+1}]` (`_calcular_spans`, `guardas_respuesta.py:229-242`).
2. Para cada página del rango se puntúa la evidencia: **las cifras pesan el doble que las palabras**, y las
   **frases exactas de la pregunta** (n-gramas de 2 y 3 palabras) pesan más que las palabras sueltas.
3. Las frases se toman **de la pregunta, no de la respuesta**: el modelo puede citar de memoria una frase del
   documento que vive en otra página ("para comparar el costo real", pág. 3) mientras lo que se pregunta está en
   otra ("Préstamo personal", pág. 2).
4. Los **acrónimos de la pregunta** (`CTS`, `TCEA`) pesan 5: son la señal más específica de qué se pregunta.
5. Una segunda página se cita solo si tiene evidencia **específica** que la principal no tiene: un acrónimo de la
   pregunta o una frase que vive en una sola página del PDF (`_frase_propia`, `guardas_respuesta.py:341-346`).

> **Por qué no basta con los números:** el corpus tiene `4.00%` en dos sitios (la CTS de la pág. 1 y el rango
> ficticio `4.00%–4.60%` de la pág. 2). El número solo no puede decidir la página; el acrónimo de la pregunta sí.

### 3.2 G3 · las reservas, y a qué fila se aplican

Las reservas se derivan del **encabezado de columna** del fragmento citado, no de una tabla de casos hardcodeada:

| Encabezado | Tipo | Reserva |
|---|---|---|
| `Banco A: TEA ficticia` / `Son tasas inventadas para el ejercicio` | FICTICIO | "Las tasas de este apartado son ficticias…" |
| `Banco B: supuesto ficticio` | MIXTO | "Las cifras de Banco B… son un supuesto ficticio…" (solo si la respuesta las menciona) |
| Fila `1080 días a más → 1.00% × 6` | fila uniforme | "La fila del tarifario es uniforme en todos los tramos de monto…" |
| Advertencia del corpus (`no permite confirmar`) | fila incompleta | "El propio documento advierte que no permite confirmar…" |

**Cada advertencia se aplica a su propia fila, no a todo el documento.** La advertencia "la disposición original del
cuadro no permite confirmar otros detalles" pertenece a la fila del Ahorro Cash (0.10 %): si se aplicara a todo el
fragmento 1, el caso `cancelacion-anticipada` (pág. 2, regla real de Banco A) saldría con una reserva que no le
corresponde. Lo mismo con la fila uniforme: la comisión de S/ 1.00 del agente Kasnet menciona `1.00`, pero la fila
uniforme es la de `1080 días a más`.

### 3.3 G5 · abstención por dato no disponible

El corpus lo dice con sus palabras:

- «…conviene solicitar la **TCEA**, que incorpora intereses, comisiones y gastos aplicables. **No se puede calcular** con la información disponible.» (pág. 3)
- «**CTS** El documento describe modalidades y requisitos, pero **no permite identificar una tabla** completa de tasas…» (pág. 1)

La guarda toma el nombre de la magnitud (el último acrónimo en mayúsculas en los 120 caracteres anteriores al
marcador) y lo **busca en la pregunta**: si la pregunta pide esa magnitud, la respuesta honesta es la abstención.
Se comprueba contra la **pregunta**, no contra la respuesta, y por eso `tea-prestamo-personal` (que pide la TEA)
se publica con reserva mientras `tcea-prestamo` (que pide la TCEA) se abstiene.

## 4. Cableado en el flujo vivo

| Archivo | Cambio |
|---|---|
| `app/guardas_respuesta.py` | **Nuevo.** Módulo completo, sin dependencias del modelo. |
| `app/agente_ahorro.py:65-76` | `AgenteRiesgo(rag, llm, pdf_path=None)`; propiedad `guardas` (se construye una vez). El tercer argumento es opcional: no rompe las llamadas existentes. |
| `app/agente_ahorro.py:144-167` | `responder_consulta()` devuelve además `estado`, `motivo`, `reservas`, `citas` y `cifras_sin_grounding`; si las guardas abstienen, la respuesta que sale es el texto determinista, no la del modelo. |
| `app/agente_ahorro.py:153-161` | Si el LLM falla, la respuesta es un texto determinista que cita los fragmentos: se marcan `PUBLICAR` / `fallo_llm` y **se resuelven igual las páginas** para no mostrar una página equivocada. |
| `app/conversacion.py:46-52` | El `meta` del mensaje lleva `estado`, `motivo`, `reservas` y `citas` (con la página real). |
| `app/main.py:73` | `AgenteRiesgo(rag, crear_llm(settings), settings.pdf_path)`: el PDF se lee para tener las páginas reales. |
| `app/metricas.py:42-47, 80-83` | `lab06_guarda_respuesta_total{estado}`, `lab06_guarda_reservas_total{tipo}`, `lab06_guarda_cifras_sin_grounding_total`, `lab06_cita_pagina_corregida_total`. |
| `web/index.html:194-197, 216-218` | La cita muestra la página real ("pág. 2" / "pág. 2, 3") y debajo del estado de las guardas y cada reserva. |

## 5. Resultado medido [PROBADO]

`tests/test_guardas_respuesta.py` (20 pruebas nuevas) corre las guardas sobre el corpus real
(`data/Benchmarking.pdf`) y los 22 casos de `data/rag_gold.json`:

- **22/22 casos** con el estado esperado y **con la página real esperada** (no solo la página declarada).
- Reparto de estados: **2 `PUBLICAR` / 17 `PUBLICAR_CON_RESERVA` / 3 `ABSTENER`** — exactamente el que anticipa
  la validación del set de oro (§4 de ese documento).
- **0 falsos positivos de grounding** sobre las 22 respuestas esperadas.
- **6 casos** (27 %) con la página corregida respecto de la que declara la ingesta.

Comando:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_guardas_respuesta.py -q
```

### 5.1 Línea base de la suite completa [PROBADO]

| | Pruebas | En rojo |
|---|---|---|
| Antes (línea base `4e4053d`) | 131 | 18 |
| Después (con este trabajo) | **151** | **18** (las mismas 18) |

Las 18 heredadas son las del approval loop de crédito eliminado (decisión previa del usuario, riesgo R1). **Este
trabajo no introduce ninguna prueba en rojo** y añade 20 pruebas en verde.

> Una prueba nueva sí rompió una heredada durante el desarrollo (`tests/test_llm_agente.py::test_consulta_con_mock`):
> la guarda G0 comparaba la pregunta solo con el **cuerpo** de los fragmentos y el manual de políticas titula su
> artículo "Documentos" y no "documentos" en el cuerpo. Corrección: el vocabulario del corpus incluye los **títulos**
> (`guardas_respuesta.py:202-210`). El corpus de benchmarking sigue sin affected (los 22 casos siguen abstieniéndose
> cuando toca).

## 6. Límites honestos

- **El humano sigue fuera del circuito.** Las guardas，决定; el asesor recibe la abstención. No hay bandeja de
  revisión: un caso que merezca juicio humano (una generalización semántica correcta en sus cifras pero falsa en su
  conclusión) no lo detecta ninguna regla de este módulo.
- **La reserva se deriva del encabezado de columna**, que es una convención del corpus de este ejercicio. Con otro
  PDF (o con otro autor del documento) hay que revisar `FICTICIO_TEA` / `FICTICIO_SUPUESTO` / `FICTICIO_INVENTADAS`.
- **G0 es heurística**: exige que *ningún* término de peso de la pregunta aparezca en el corpus. Con un corpus
  pequeño y una pregunta de otra disciplina puede equivocarse en ambos sentidos.
- **G5 depende de que el documento declare la limitación con esas palabras.** Un documento que diga "no disponible"
  o "a calcular" no dispara la guarda.
- **La página se resuelve con un puntaje, no con una verdad.** En este corpus (3 páginas, 3 fragmentos) el puntaje
  acierta 22/22; con un PDF de 50 páginas habría que recalibrarlo.
