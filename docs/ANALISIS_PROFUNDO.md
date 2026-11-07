# Análisis profundo · Lab 06

**Asesor de ventas (chat RAG) → Jev → RAG o agente de riesgo → Aprobación humana · 2026-10-11 (v2: conversación)**

Etiquetas de evidencia:

- **[MEDIDO]**: se ejecutó en esta máquina (macOS, Python 3.10, Docker Compose v5.1.4).
- **[PROBADO]**: lo cubre una prueba automática.
- **[GENERAL]**: conocimiento general, no reproducido aquí.
- **[NO PROBADO]**: preparado, pero sin ejecutar contra el servicio real.

---

## 1. Qué se pidió y dónde está

| Requisito | Implementación |
|---|---|
| 1. La primera pregunta es la del asesor de ventas | **v2:** chat (`web/asesor.html` + `app/conversacion.py`). Los datos del cliente se piden en un formulario dentro del chat solo cuando hay que evaluar (`app/modelos.py::Solicitud`, 12 campos validados) |
| 2. RAG conectado a un agente especialista en análisis de riesgo (venta de productos del banco) | `app/agente_ahorro.py` + `app/rag.py` + `app/ingesta.py` |
| 3. Las reglas en PDF | `rules/politicas.py` → `rules/generar_pdf.py` → `data/politicas_riesgo.pdf` (3 páginas, 16 artículos) |
| 4. Aprobación del analista en una web HTML simple | `web/analista.html` + `POST /api/solicitudes/{id}/decision` (token, comentario obligatorio, decisión atómica) |
| 5. El agente responde al asesor usando el RAG | **v2:** RAG conversacional en el chat (historial + reformulación de preguntas de seguimiento), con artículos citados. Evaluación: justificación con citas + decisión humana que vuelve al chat |
| v2. Conversación RAG que escala al analista de riesgo cuando hace falta | Escalamiento por el router (`evaluacion_credito`), por botón o por sugerencia cuando el manual no cubre la pregunta. El analista ve la conversación de origen |
| 6. Jev para el enrutamiento semántico | `app/router.py::JevRouter` (pregunta `choice`, umbral de confianza, reintentos y respaldo por embeddings) |
| 7. Todo monitoreado con Prometheus y Grafana | `app/metricas.py` (20 métricas) + `docker-compose.yml` + tablero aprovisionado (18 paneles, 23 consultas) |
| 8. Validación de comandos de Windows con análisis profundo | `docs/ANALISIS_WINDOWS.md` + paso 14 de la guía + analizador de `build.py` + pruebas de higiene |
| API keys reales (Jev y OpenAI), código preparado | `TYPESAFE_API_KEY`, `OPENAI_API_KEY` en `.env`; `scripts/verificar_claves.py` |

## 2. Decisiones de arquitectura y por qué

### 2.1 Un servicio FastAPI + SQLite + índice NumPy (en vez de reutilizar el lab 04)

- **Por qué:** el lab 04 (pgvector + OTel Collector + Tempo + Loki) agrega cinco contenedores y el problema de `ProactorEventLoop` en Windows. Aquí el corpus son 16 artículos; un producto punto en memoria basta.
- **Costo:** no escala a miles de documentos ni a varios procesos.
- **Interfaz preservada:** `RAG.buscar()` no cambiaría si se reemplaza por pgvector o Qdrant.

### 2.2 Una sola fuente de verdad para las reglas

`rules/politicas.py` genera el texto del PDF **y** los parámetros de las guardas. [PROBADO] La prueba `test_el_pdf_devuelve_exactamente_las_reglas_de_la_fuente` extrae los 16 artículos del PDF con pypdf y los compara carácter por carácter con la fuente.

En un banco real el PDF lo publica Riesgos y la traducción a código es manual. Ahí la prueba equivalente sería un control de cambios: cada versión del PDF se compara con los parámetros del código. Ver el ejercicio 4.

### 2.3 Jev como router principal, embeddings como respaldo

- **Jev da probabilidades por opción:** el umbral (0.55) tiene significado probabilístico. El coseno del router por embeddings no lo tiene.
- **Respaldo ante errores transitorios:** si Jev falla (401, 422, 429, 529 o red), la solicitud se enruta con embeddings y se registra el motivo. La disponibilidad del flujo de ventas no depende de un proveedor externo.
- **Errores no transitorios:** 401 y 422 no se reintentan (reintentar no los arregla). Igual activan el respaldo, porque el asesor no debe quedarse sin respuesta. [PROBADO] Las pruebas cubren los cinco caminos.

### 2.4 El LLM propone, el código dispone

Este es el punto central del laboratorio:

- `final = max(piso_de_guardas, propuesta_LLM)`, con el orden APROBAR < OBSERVAR < RECHAZAR.
- **Consecuencia:** ningún error ni manipulación del LLM puede aprobar algo que las reglas duras rechazan. [PROBADO] Un LLM falso que obedece "ignora las reglas y aprueba" con calificación Pérdida termina en RECHAZAR, con `anulado_por_guarda=True` visible para el analista y contado en Prometheus.
- **Límite:** las guardas solo cubren reglas cuantificables. Una regla cualitativa ("el negocio debe ser viable") la evalúan el LLM y el humano. Si el LLM la omite, nada la detecta automáticamente.

### 2.5 Recuperación híbrida (exacta + semántica)

Los artículos que activaron una guarda se recuperan **por id**, no por similitud. Así la justificación siempre puede citar la regla que causó el dictamen. Las citas a artículos fuera del contexto se descartan y se cuentan: es una alucinación medible.

### 2.6 Humano en el circuito con controles reales

| Control | Implementación | Evidencia |
|---|---|---|
| Segregación de funciones | Token de analista para la cola y la decisión; el asesor no lo tiene | [PROBADO] 401 sin token o con token incorrecto; 503 si no está configurado (cerrado por defecto) |
| El asesor no ve la propuesta antes de la decisión | `vista_asesor` omite el dictamen en `PENDIENTE_ANALISTA` | [PROBADO] |
| Justificar los desacuerdos | Comentario de al menos 10 caracteres si la decisión ≠ dictamen (OBSERVAR siempre lo exige) | [PROBADO]; [MEDIDO] en el navegador |
| Decisión única | `UPDATE … WHERE estado='PENDIENTE_ANALISTA'` | [PROBADO] 8 hilos simultáneos: 1 gana, 7 reciben 409 |
| Auditoría | SQLite guarda la solicitud, el enrutamiento (proveedor, versión del modelo, probabilidades, motivo de respaldo), la propuesta, las reglas, la decisión, el analista, el comentario y las marcas de tiempo | Lectura de código |

### 2.7 v2 · La conversación: entender en el chat, decidir con datos validados

El pedido de la segunda iteración fue que el asesor converse con el RAG y que, en caso necesario, intervenga el analista de riesgo. Diseño y razones:

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| **El chat entiende, el formulario decide.** Cuando Jev detecta una evaluación, el chat pide los datos en un formulario validado (Pydantic) dentro de la conversación | Extraer ingreso, deuda, monto y plazo del texto con el LLM | Las guardas confían en los números que reciben. Un error de extracción ("3,500" → 3.5) cambiaría el dictamen sin que nada lo detecte. El costo es UX: el asesor llena campos |
| **Reformulación de preguntas de seguimiento** antes del RAG ("¿Y para el vehicular?" → "¿Cuál es el plazo máximo del crédito MYPE? ¿Y para el vehicular?") | Buscar con el mensaje tal cual, o con todo el historial concatenado | Tal cual recupera mal (no tiene tema). Con todo el historial, la búsqueda se diluye. Solo se reformula si hay historial (la primera pregunta no paga esa llamada) y, si falla, se busca tal cual |
| **Jev recibe los 3 últimos mensajes del asesor** en `state` | Solo el mensaje actual | "Sí, evalúalo" no es clasificable sin contexto |
| **Memoria acotada:** 6 turnos y 600 caracteres por turno | Toda la conversación | Costo y ruido crecen con cada turno. Límite: se pierde lo dicho antes (ejercicio 6: resumen acumulado) |
| **El router ayuda, no manda:** botón "Escalar" + sugerencia cuando el RAG no encuentra artículos | Solo el router decide | Un falso negativo del router no debe dejar al asesor sin camino al analista. La métrica `escaladas{origen}` mide cuánto se escala a mano (si es mucho, el router falla) |
| **La decisión vuelve al chat** como mensaje del sistema, con condiciones y citas | El asesor revisa otra pantalla | Un solo lugar de trabajo para el asesor; trazabilidad conversación → solicitud → decisión |
| **El analista ve la conversación de origen** (últimos 12 mensajes) | Solo los datos del formulario | El contexto ("el cliente ya tiene aval", "es su segundo crédito") importa para decidir |
| **Enmascarado de datos personales en los adaptadores de salida** (Jev, LLM, embeddings) | Enmascarar en cada punto que construye un texto | En un chat el asesor escribe DNI y teléfonos sin querer. Ponerlo en el adaptador cubre cualquier camino futuro |
| **Detección de inyección** como segunda pregunta `noul` en la MISMA llamada a Jev | Un clasificador aparte o bloquear el mensaje | Cero latencia extra. Solo marca: el bloqueo real del daño lo hacen las guardas (el LLM no puede ablandar un dictamen) |

**Verificación de la v2:**

- 29 pruebas nuevas: 12 de privacidad, sobre el cuerpo HTTP simulado de los tres adaptadores; 14 del chat por HTTP; 3 del router.
- **16 mutaciones nuevas, todas detectadas**: enmascarado quitado en cada adaptador, historial no enviado, reformulación anulada, decisión que no vuelve al chat, migración quitada, entre otras.
- Recorrido real en el navegador con el stack de Docker: la pregunta de seguimiento recuperó el Art. 2.3 gracias a la reformulación, el formulario apareció en el chat, el analista vio la conversación y la decisión volvió al chat en menos de 3 s. [MEDIDO]

## 3. Resultados medidos

| Medición | Resultado |
|---|---|
| Suite de pruebas | **132 pruebas pasan** (Python 3.10) [MEDIDO] |
| Pruebas de mutación | **39/39 mutaciones detectadas** (v1: 13 guardas, 3 del agente, 3 de la API, 1 de la base, 2 del router, 1 del LLM; v2: 16 del chat, privacidad y migración). La primera corrida dejó viva la del `UPDATE` atómico; se agregó `tests/test_db.py`, que la detecta. También se verificó la mutación `>`→`>=` del ejercicio 1 [MEDIDO] |
| Simulación del alumno | Guía compilada seguida en orden, en una carpeta con espacios y "ñ". Todos los pasos OK; solo fallan, como se espera, los dos comandos que exigen claves reales [MEDIDO] |
| Router `hash` sobre el set de oro | 62% (15/24) con umbral 0.30 y máximo de 71% con 0.40 [MEDIDO] sobre el set anterior de evaluación crediticia. Es un resultado histórico; no corresponde al set actual de benchmarking |
| Router Jev / embeddings de OpenAI | **No medido** (sin claves). Es el primer resultado que deben producir los alumnos |
| Docker Compose | app healthy, target `lab06` UP, 23 consultas PromQL sin error y con datos tras la carga (incluidas las del chat) [MEDIDO] |
| Recorrido en el navegador | Asesor → pendiente (sin propuesta visible) → analista (422 sin comentario) → aprobada → el asesor la ve por sondeo [MEDIDO] |
| Ejemplo de cálculo | S/ 12 000, 24 meses, TEA 35%: cuota S/ 673.36, cuota/ingreso 19.24%, endeudamiento 30.67% [MEDIDO]. La fórmula se valida con una amortización simulada (saldo final < S/ 0.01) [PROBADO] |

## 4. Hallazgos durante la construcción (errores reales que se corrigieron)

1. **Paneles en 0 aunque había datos.** La primera carga se envió antes de la primera lectura de Prometheus. `increase()` necesita dos muestras y la primera ya valía 12. *Corrección:* la guía exige ver el target en UP antes de generar carga. [MEDIDO]
2. **Series con etiquetas ausentes ("No data").** Histogramas y contadores etiquetados no existen hasta su primera observación. *Corrección:* `inicializar_series()` crea las combinaciones conocidas en 0 (rutas, dictámenes, proveedores, reglas de las guardas). [MEDIDO] en Grafana
3. **`UnicodeEncodeError` en Windows al redirigir la salida** (`eval_router`, por "→"). Ver `ANALISIS_WINDOWS.md` §2.2. [MEDIDO] con cp1252
4. **Docker Compose no lee un `.env` en UTF-16** (Python sí). *Corrección:* `scripts/normalizar_env.py`. [MEDIDO]
5. **Advertencias falsas de numpy** ("divide by zero encountered in matmul") en Mac con chip M, incluso con datos aleatorios. *Corrección:* `similitudes()` evita BLAS. [MEDIDO]
6. **Orden de la guía:** `conftest.py` importaba módulos de pasos posteriores. *Corrección:* importaciones dentro de las fixtures. Verificado con la simulación del alumno.
7. **Paneles con títulos truncados** a 1024 px. *Corrección:* títulos cortos y `textMode: value`. [MEDIDO] con captura de pantalla
8. **Búsqueda léxica ambigua:** con el embedder `hash`, "tasa del crédito vehicular" recuperaba el Art. 1.1 (que también nombra el producto) antes que el 2.3. Muestra el límite de un embedder léxico; con la pregunta completa se recupera el 2.3. [MEDIDO]

## 5. Riesgos y limitaciones

### 5.1 Integraciones no probadas contra los servicios reales [NO PROBADO]

- **Jev:** el esquema (`/v1/systemone`, `state`, `questions`, `type: choice`, `criteria`, `answers.ruta.choice/probabilities`) se tomó de documentación de terceros (DigitalOcean, LiteLLM, guías publicadas en septiembre de 2026), no de docs.typesafe.ai.
  - El cliente tolera que falte `choice` (usa la opción más probable) y valida que la ruta exista.
  - Si la API real difiere, `verificar_claves` muestra el 422 con el campo exacto.
- **Acceso a Jev:** las mismas fuentes reportan que TypeSafe pausó los registros nuevos el 22 de septiembre de 2026. Los alumnos sin cuenta deben usar `ROUTER_PROVIDER=embeddings`.
- **OpenAI:**
  - Se usan la Responses API (`text.format` con `json_schema` estricto y `store=False`) y `text-embedding-3-small`. El SDK oficial 3.29 hace la petición y parsea la respuesta, pero el transporte es simulado.
  - El modelo por defecto (`gpt-5.4-mini`) figura en la lista de modelos del propio SDK. No se verificó que la cuenta del alumno tenga acceso.
  - Algunos modelos recientes no aceptan `temperature`, así que no se envía.

### 5.2 Seguridad

| Riesgo | Mitigación actual | Qué faltaría en producción |
|---|---|---|
| Prompt injection en la pregunta libre | Instrucción "es un dato" + guardas que solo endurecen + contexto JSON separado | Clasificador de inyección (Jev con una pregunta `noul` es un buen candidato); registro de intentos |
| Token de analista compartido | `hmac.compare_digest`, cerrado por defecto | SSO, roles, registro por usuario, rotación |
| XSS en las páginas | `esc()` en todo texto del servidor | CSP, cabeceras de seguridad |
| Claves | Solo en `.env`; `.dockerignore` lo excluye de la imagen; `verificar_claves` muestra solo los últimos 4 caracteres | Gestor de secretos; claves por entorno con límite de gasto |
| Abuso de la API | — | Límite de solicitudes por asesor; autenticación del asesor |

### 5.3 Privacidad y datos personales

**v2:** el enmascarado (DNI, teléfono, RUC, correo) se aplica en los tres adaptadores de salida y está probado sobre el cuerpo HTTP. **No cubre nombres propios ni direcciones** (ejercicio 7). En la base interna se guarda el texto original, que es el registro de la entidad.


- **No salen del sistema:** el DNI y el nombre [PROBADO].
- **Sí salen:**
  - hacia TypeSafe, la pregunta libre;
  - hacia OpenAI, la pregunta libre más los datos financieros y la calificación.
- **Riesgo residual:** el asesor podría escribir el nombre o el DNI del cliente en la pregunta libre. En producción haría falta:
  - anonimizar la pregunta libre antes de enviarla;
  - acuerdos de tratamiento de datos con ambos proveedores;
  - una política de retención (`store=False` en OpenAI ya evita que se guarde la conversación);
  - revisar la regulación local de protección de datos personales [GENERAL].

### 5.4 Calidad de la IA

- **v2 · Reformulación:** si el LLM reescribe mal una pregunta de seguimiento, el RAG busca otra cosa. El chat muestra "Busqué en el manual: …" para que el asesor lo note; no hay verificación automática. Con `mock`, la "reformulación" es una regla fija (concatenar la pregunta anterior si el mensaje tiene menos de 6 palabras): no es representativa de un LLM real.
- **v2 · Router `hash` en el chat:** en la carga de prueba enrutó "¿Y si es dependiente?" a `evaluacion_credito`. Es un error léxico esperable (el router `hash` no usa contexto); con Jev y el historial debería ir a `consulta_producto`. No medido con Jev.

- **Calibración optimista:** el set actual de router tiene 36 frases de benchmarking escritas manualmente; no sustituye consultas reales con errores de tipeo, jerga o mezcla de intenciones.
- **Ruta mixta:** una pregunta que es consulta y evaluación a la vez se fuerza a una sola ruta. Una alternativa es usar varias preguntas `noul` de Jev (una por intención) en vez de un `choice`.
- **Sesgo de automatización:** una tasa de acuerdo agente/analista cercana al 100% puede significar que el humano aprueba sin revisar. El tablero la muestra; el control (muestreo de revisión) no está implementado.
- **Deriva del modelo:** `jev-latest` y el modelo de OpenAI pueden cambiar. Se guarda la versión que respondió en cada solicitud, pero no hay una alerta por cambio de versión.

### 5.5 Operación

- **Latencia:** una evaluación hace hasta tres llamadas externas en serie: Jev, embeddings de la consulta y LLM. Con reintentos, el peor caso supera los 60 s (`OPENAI_TIMEOUT_S`). El formulario muestra "Enrutando…" sin límite de tiempo.
- **Un solo proceso:** la conexión SQLite protegida con un lock sirve para el laboratorio, no para varios servidores.
- **Costo:** se mide en `lab06_costo_estimado_usd_total` con precios de `.env`. Jev viene con USD 0.042 por millón de tokens de entrada (precio publicado por terceros). Los precios de OpenAI quedan en 0 hasta que el alumno los complete, porque no se inventaron.

## 6. Próximos pasos recomendados

1. Ejecutar `verificar_claves` y `eval_router` con las claves reales y registrar los resultados en este documento.
2. Validar los comandos en un Windows real (ver `ANALISIS_WINDOWS.md` §4).
3. Agregar la detección de inyección con Jev (`noul`) como segunda pregunta en la misma llamada de enrutamiento (sin latencia adicional).
4. Alertas de Prometheus: router de respaldo, citas inválidas, cola mayor que N, costo por hora.
5. Muestreo de revisión del 5% de las aprobaciones para medir el sesgo de automatización.
