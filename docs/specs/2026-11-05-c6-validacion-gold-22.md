# Validación de los 22 casos de `data/rag_gold.json` contra Publicar / Publicar con reserva / Abstener

**Fecha:** 2026-11-05 · **Alcance:** criterio C6 (Seguridad, privacidad y guardas) · **Estado:** [PROBADO] — verificado ejecutando scripts sobre el corpus real y el set de oro real.

## 1. Tesis

Los 22 casos del set de oro de C7 se pueden clasificar de forma determinista en tres estados de salida (publicar / publicar con reserva / abstener) **sin intervención humana**, y esa clasificación sirve para calibrar las guardas deterministas de C6.

Consecuencia directa para el diseño: **el humano en el circuito no es necesario para el set de oro** (los 22 casos se resuelven solos). Su valor está en las consultas de generalización que el set de oro no cubre.

## 2. Método

Scripts ejecutados con el entorno local (`.venv-win`, Python 3.14.2):

1. Extracción del corpus real: `app.ingesta.extraer_fragmentos(Path('data/Benchmarking.pdf'))` → 3 fragmentos.
2. Verificación de citas: para cada caso, cada token de `fuentes_esperadas[].contiene` se busca en el texto normalizado (sin acentos, guiones unificados) de **cada página física** del PDF, leído con `pypdf` directamente.
3. Verificación de grounding: cada literal numérico de `respuesta_esperada` se busca en el corpus completo (3 fragmentos concatenados, normalizado).

## 3. Resultados mecanicos

| Comprobación | Resultado |
|---|---|
| Casos en `data/rag_gold.json` | 22 |
| `debe_abstenerse: true` | 3 (13.6 %) |
| `debe_abstenerse: false` | 19 (86.4 %) |
| Casos con **alguna cifra de la respuesta esperada ausente del corpus** | **0** |
| Casos cuya cita no puede resolverse en ninguna página física | **0** |
| Casos donde la página declarada ≠ página física real | **0** (el metadato `pagina` del set de oro es correcto) |

**[PROBADO] Hallazgo 1 — el grounding estricto no rompe el set de oro.** Las 22 respuestas esperadas usan exclusivamente cifras presentes en el corpus. Una guarda numérica que exija "toda cifra de la respuesta aparece en el corpus" produce 0 falsos positivos sobre las 22 respuestas esperadas. Es un argumento fuerte a favor de implementar esa guarda sinStakeholders.

## 4. Clasificación de los 22 casos

Criterio de la clasificación (derivado del encabezado de cada fragmento del corpus, no hardcodeado por caso):

- **Fragmento 1** «Operaciones pasivas»: encabezado `Banco A: tarifario compartido | Banco B: supuesto ficticio` → la segunda columna es ficticia.
- **Fragmento 2** «Operaciones activas»: encabezado `Banco A: TEA ficticia | Banco B: TEA ficticia` y la nota *«Son tasas inventadas para el ejercicio»* → **ambas** columnas son ficticias.
- **Fragmento 3** «ITF y comisiones»: encabezado `Banco A: tarifario compartido | Banco B: supuesto ficticio` → la segunda columna es ficticia.

Sobre esa base, cada respuesta esperada se clasifica según el origen de sus cifras:

| # | id | Pregunta (resumen) | Cifras de Banco A | Cifras de Banco B | Estado |
|---|---|---|---|---|---|
| 1 | `ahorro-soles-tea` | TEA del ahorro en soles | 0.30 % real | 0.40 % ficticio | **con reserva** |
| 2 | `apertura-ahorro-soles` | Mínimo de apertura en soles | S/ 5 real | S/ 10 ficticio | **con reserva** |
| 3 | `ahorro-dolares-tea` | TEA del ahorro en dólares | 0.35 % real | 0.50 % ficticio | **con reserva** |
| 4 | `apertura-ahorro-dolares` | Apertura en dólares | US$ 5 / US$ 0 real | US$ 10 ficticio | **con reserva** |
| 5 | `ahorro-cash-dolares` | TEA del Ahorro Cash | 0.10 % real **+ el documento advierte que no confirma el resto** | 0.20 % ficticio | **con reserva (doble)** |
| 6 | `ahorro-programado-180` | Interés e incentivo a 180 días | 0.50 % + 3.00 % real | 0.60 % + 2.50 % ficticio | **con reserva** |
| 7 | `ahorro-programado-210-330` | Condiciones 210–330 días | 0.90 % + 3.25 % real | 0.80 % + 3.00 % ficticio | **con reserva** |
| 8 | `ahorro-programado-720-1080` | Condiciones 720–1080 días | 1.20 % + 4.50 % real | 1.20 % + 4.00 % ficticio | **con reserva** |
| 9 | `plazo-fijo-91-180` | Tasas 91–180 días | 2.35 %–2.95 % real | 2.25 %–2.85 % ficticio | **con reserva** |
| 10 | `plazo-fijo-361-390` | Tasas 361–390 días | 3.80 %–4.40 % real | 3.70 %–4.30 % ficticio | **con reserva** |
| 11 | `plazo-fijo-1080` | TEA a 1080 días a más | 1.00 % real **fila uniforme en los 6 tramos** | 0.80 % ficticio | **con reserva + contexto anómalo** |
| 12 | `cancelacion-anticipada` | Cancelación anticipada | regla real de Banco A | — | **publicar** |
| 13 | `tea-prestamo-personal` | TEA del préstamo personal | 39.90 % **ficticia** | 35.90 % **ficticia** | **con reserva (total)** |
| 14 | `tea-credito-vehicular` | Tasas del crédito vehicular | 16.90 % **ficticia** | 15.90 % **ficticia** | **con reserva (total)** |
| 15 | `tcea-prestamo` | TCEA exacta del préstamo personal | — | — | **abstenerse** |
| 16 | `itf` | ITF y quién fija la tasa | 0.005 % real | 0.005 % real | **publicar** |
| 17 | `kasnet-consulta-saldo` | Consulta de saldo en Kasnet | S/ 1.20 real | S/ 1.00 ficticio | **con reserva** |
| 18 | `retiro-ventanilla` | Retiro en ventanilla | S/ 1.50 + US$ 0.50 real | S/ 1.00 ficticio | **con reserva** |
| 19 | `retiro-global-net` | Retiro en cajero Global Net | S/ 3.10 + US$ 1.06 real | S/ 2.50 + US$ 0.90 ficticio | **con reserva** |
| 20 | `transferencia-otros-bancos` | Transferencia hasta S/ 50,000 | S/ 40 real | S/ 35 ficticio | **con reserva** |
| 21 | `tasa-cts-banco-a` | Tasa exacta de CTS de Banco A | — | 4.00 % ficticio (no extrapolable) | **abstenerse** |
| 22 | `agencia-horario` | Horario de la agencia de Huancayo | — | — | **abstenerse** |

### Resultado agregado

| Estado | Casos | % |
|---|---|---|
| Publicar | 2 | 9.1 % |
| Publicar con reserva | 17 | 77.3 % |
| Abstener | 3 | 13.6 % |

**[PROBADO] Hallazgo 2 — "publicar con reserva" es el estado modal, no un caso borde.** 17 de 22 respuestas (77 %) involucran al menos una cifra del supuesto Banco B, o una advertencia del propio documento. La reserva no es un adorno: es la condición normal del sistema, y se puede derivar del encabezado de la columna citada, no de una tabla hardcodeada.

**[PROBADO] Hallazgo 3 — los 22 casos se resuelven sin humano.** Los 3 casos de abstención están determinados por falta de información en el corpus, y las 19 respuestas restantes tienen todas sus cifras verificadas. No hay ningún caso del set de oro que exija un juicio no numérico. Por tanto:

- El humano en el circuito **no aporta exactitud** sobre el set de oro.
- Ponerlo en estos casos solo añade latencia y una dependencia operativa.
- Su lugar es en las consultas de **generalización**, que el set de oro no cubre (ej.: *«¿el Banco B es siempre más barato que el Banco A?»* → respuesta con todas las cifras correctas pero generalización falsa, refutada por Ahorro Cash en dólares 0.10 % vs 0.20 % y por la apertura digital US$ 0 vs US$ 10).

**[PROBADO] Hallazgo 4 — el caso `plazo-fijo-1080` no es una abstención.** La respuesta esperada del set de oro es *«Banco A indica 1.00 % para todos los rangos de monto de la tabla»*: el gold **publica** la fila, con la nota de que es uniforme. La fila `1080 días a más → 1.00% × 6` es un artefacto del cuadro original (la fila anterior, 721–1079 días, va de 4.30 % a 5.00 %), pero el gold no la trata como error. Si el sistema la marca para revisión humana, es una reserva adicional — no una abstención.

## 5. Hallazgo colateral con impacto en las citas: la página del fragmento no es la página de la cita

`app/ingesta.py:45-57` asigna `pagina` al fragmento en la **página donde aparece su título**. El texto del fragmento sigue acumulándose en las páginas siguientes. Consecuencia: `fragmento["pagina"]` es la *página de inicio de sección*, no la página donde vive cada cita.

Comprobado contra el PDF físico:

| Fragmento | `pagina` declarada | Páginas físicas que realmente ocupa |
|---|---|---|
| 1 «Operaciones pasivas: depósitos y ahorros» | 1 | 1 **y 2** (filas 91–180 / 361–390 / 1080+ y la Observación sobre cancelaciones anticipadas) |
| 2 «Operaciones activas: créditos» | 2 | 2 **y 3** (crédito vehicular y la nota de TCEA) |
| 3 «ITF y comisiones» | 3 | 3 |

Casos del set de oro cuya página física **no coincide** con la página que el sistema atribuiría a partir del fragmento:

| Caso | Página física real (según el gold) | Página que diría el sistema | Dato afectado |
|---|---|---|---|
| `plazo-fijo-91-180` | 2 | 1 | tasas 2.35 %–2.95 % |
| `plazo-fijo-361-390` | 2 | 1 | tasas 3.80 %–4.40 % |
| `plazo-fijo-1080` | 2 | 1 | fila 1.00 % |
| `cancelacion-anticipada` | 2 | 1 | regla de cancelación |
| `tea-credito-vehicular` | 3 | 2 | tasas 16.90 % / 15.90 % |
| `tcea-prestamo` | 3 | 2 | nota de TCEA |

**6 de 22 casos (27 %) recibirían una cita con la página equivocada.** El set de oro de C7 es correcto en este punto: declara la página física real.

### Decisión de diseño derivada

Añadir a C6 una guarda de integridad de cita, determinista y barata: **el texto citado debe existir en la página que la cita declara**. Con 3 páginas, resolver la página real de un fragmento es una búsqueda literal sobre los textos normalizados de las páginas — sin embeddings, sin coste.

Implementación recomendada: al construir la cita, localizar el literal citado en los textos de página y usar la página donde aparece; si el fragmento declara una página distinta, la cita usa la página real y se registra la discrepancia en métrica.

## 6. Consecuencias para el diseño de C6

1. **Guarda G2 (grounding numérico):** viable sin falsos positivos sobre el gold set. 22/22 limpias.
2. **Guarda de reserva:** determinista a partir de la columna citada (tarifario compartido vs. supuesto ficticio). Cubre 17/22 casos de forma automática, sin modelo.
3. **Abstención:** reutilizar el texto determinista ya escrito en el gold (`tcea-prestamo`, `tasa-cts-banco-a`, `agencia-horario`) y el `SIN_CONTEXTO` existente en `app/agente_ahorro.py:47-49`.
4. **Guarda de cita:** nueva, corrige el 27 % de casos mal citados.
5. **Humano en el circuito:** fuera de la ruta del set de oro; solo en generalizaciones semánticas. Debe medirse con un conjunto propio de casos adversarios, no con `rag_gold.json`.

## 7. Lo que este documento NO decide

> **Actualización:** estas tres decisiones ya se tomaron al implementar (§8): el formato final son tres estados
> (`PUBLICAR` / `PUBLICAR_CON_RESERVA` / `ABSTENER`) con la reserva como **etiqueta**, no como estado; y el 27 % de
> citas mal atribuidas se corrige en la **capa de citas** (resolver la página real al citar), no en la ingesta.
> El vocabulario de los casos adversarios sigue sin definirse.

- El formato final de la decisión (`PUBLICADA | ABSTENIDA | RECHAZADA`) y si la reserva se modela como estado o como etiqueta.
- El vocabulario de los casos adversarios que sí requieren humano.
- Si el 27 % de citas mal atribuidas se corrige en la ingesta (guardar páginas por fragmento) o en la capa de citas (resolver la página real al citar). Ambas opciones son válidas; la segunda es menos invasiva.

## 8. Implementación y resultado medido [PROBADO]

La clasificación de la §4 se implementó como código determinista en `app/guardas_respuesta.py` (módulo nuevo, sin
dependencias del modelo) y se cableó en el flujo vivo. El detalle del diseño y de las desviaciones respecto de la
propuesta original está en
[`docs/specs/2026-11-05-c6-guardas-implementadas.md`](2026-11-05-c6-guardas-implementadas.md).

### 8.1 Resultado sobre los 22 casos

`tests/test_guardas_respuesta.py` corre las guardas sobre el corpus real (`data/Benchmarking.pdf`) y los 22 casos de
`data/rag_gold.json`:

| Comprobación | Resultado | Etiqueta |
|---|---|---|
| Casos con el **estado** esperado (publicar / con reserva / abstener) | **22 / 22** | [PROBADO] |
| Casos con la **página real** de la cita esperada (no solo la declarada) | **22 / 22** | [PROBADO] |
| Reparto de estados obtenido | **2 `PUBLICAR` / 17 `PUBLICAR_CON_RESERVA` / 3 `ABSTENER`** | [PROBADO] |
| Falsos positivos de grounding (cifra real marcada como sin respaldo) | **0** | [PROBADO] |
| Citas con la página corregida respecto de la que declara `app/ingesta.py:54` | **6 / 22 (27 %)** | [PROBADO] |
| Casos con abstención en el lugar correcto (`debe_abstenerse: true`) | **3 / 3** | [PROBADO] |
| Casos que el gold marca publicables y el sistema abstiene (falso positivo de abstención) | **0** | [PROBADO] |

El reparto obtenido **coincide exactamente** con el que anticipaba esta validación en la §4 (2 / 17 / 3), y los
6 casos de página corregida son los mismos 6 de la §5. Es decir: la clasificación no se ajustó al código, el código
se ajustó a la clasificación.

Comando:

```powershell
.\.venv-win\Scripts\python.exe -m pytest tests\test_guardas_respuesta.py -q
```

### 8.2 Qué quedó confirmado y qué no

- **Confirmado por la implementación:** el hallazgo 1 (el grounding estricto no rompe el gold set), el hallazgo 2
  (la reserva es derivable del encabezado de columna, sin tabla hardcodeada), el hallazgo 3 (los 22 casos se resuelven
  sin humano) y el hallazgo 4 (la fila uniforme de `plazo-fijo-1080` es una reserva, no una abstención).
- **Confirmado en producción, no solo en el set de oro:** el bug de la página (§5) está corregido en el flujo vivo — la
  cita se construye con la página donde vive el texto, y la discrepancia se registra en
  `lab06_cita_pagina_corregida_total` (`app/metricas.py:42-47`).
- **No confirmado, y sigue fuera del alcance:** que las guardas detecten una generalización semántica falsa (todas las
  cifras correctas, la conclusión inventada). Ninguna regla de este módulo lo hace, y ningún caso de
  `rag_gold.json` lo exige. Medirlo requiere un conjunto de casos adversarios propio, con humano en el circuito.
