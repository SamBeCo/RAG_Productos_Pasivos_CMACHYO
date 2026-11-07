# Gestor de Productos Pasivos · Caja Huancayo

Aplicación informativa para consultar los productos pasivos y las condiciones que aparecen en las fuentes incorporadas. El asistente recupera fragmentos, responde con referencias y se abstiene cuando no encuentra evidencia suficiente. No reemplaza los canales oficiales ni ofrece recomendaciones financieras personales.

## Alcance y fuentes

El corpus inicial está formado por:

- `data/Caracteristicas_SubProductos.xlsx`
- `data/Contrato de Depositos y Servicios Financieros V15 - 2025.pdf`
- `data/SUB_PRODUCTOS_CMACHYO.docx`
- `data/Tarifario_Caja_Huancayo.xlsx`

`documentos_caja_huancayo.pdf` queda excluido. El lector conserva párrafos y filas de tablas, y usa ubicaciones de sección, párrafo, hoja/fila o página. Las fuentes nuevas se agregan en el portal de administración como PDF con texto seleccionable; para sumar una fuente inicial `.xlsx` o `.docx`, copia el archivo a `data/`, añádelo a `DOCUMENTOS_INICIALES` en `app/ingesta.py`, reconstruye la imagen y reindexa.

## Arquitectura

Flujo: mensaje → guarda de inyección → router semántico → reformulador → agente (consulta o comparador) → guardas de respuesta → respuesta con citas. Las abstenciones y bloqueos pasan a la cola de revisión humana.

| Componente | Archivo | Rol |
|---|---|---|
| Router semántico | `app/router.py` | Elige `consulta_ahorros`, `comparar_productos` o `fuera_de_alcance`, con umbral y respaldo. |
| Agente de consulta | `app/agente_ahorro.py` (`responder_consulta`) | Busca en el RAG y responde con citas. |
| Agente comparador | `app/agente_ahorro.py` (`comparar_productos`) | Compara productos, tasas y condiciones con citas; no recomienda. |
| Reformulador | `app/agente_ahorro.py` (`reformular`) | Convierte seguimientos en consultas autónomas. |
| Guardas | `app/guardas_respuesta.py`, `app/conversacion.py` | Citas, cifras sin respaldo, no recomendación e inyección. |

Roles de acceso: el **usuario** chatea en `/` sin login; el **administrador/revisor** entra a `/admin` con `ADMIN_TOKEN`, carga PDF y resuelve revisiones. No hay cuentas individuales ni SSO.

1. **Ingesta:** `app/fuentes.py` extrae PDF, DOCX y XLSX. `app/ingesta.py` segmenta por unidad lógica y guarda id, documento y ubicación.
2. **Embeddings e índice:** `app/embeddings.py` ofrece OpenAI `text-embedding-3-small` (1536 dimensiones) y hash determinista para pruebas sin costo ni red. El índice local persistente incluye dimensión, proveedor y manifiesto SHA-256 de las fuentes; una dimensión o proveedor incompatible detiene la carga.
3. **Recuperación y respuesta:** `app/rag.py` aplica `RAG_TOP_K` y `RAG_MIN_SCORE`. Las respuestas muestran referencias; las guardas bloquean cifras sin soporte y el agente se abstiene si faltan citas o falla la generación.
4. **Chat y enrutamiento:** memoria limitada a seis mensajes, reformulación de seguimientos, router semántico con umbral y respaldo configurable; las rutas, decisiones y referencias se guardan para trazabilidad. Rutas: `consulta_ahorros` (agente de consulta), `comparar_productos` (agente comparador: recupera evidencia por producto, compara con citas y una guarda determinista le impide recomendar; si lo hace, pasa a revisión humana) y `fuera_de_alcance`.
5. **Seguridad y revisión humana:** validación Pydantic, enmascarado de PII antes de llamadas externas, bloqueo determinista de patrones de prompt injection y grounding numérico. Las abstenciones y bloqueos llegan a una cola humana; un revisor autorizado puede aprobar, editar o retirar la respuesta, que vuelve al chat.
6. **Observabilidad:** Prometheus obtiene métricas desde `/metrics`; Grafana se provisiona con el tablero del gestor. Consultas, citas, abstenciones, fuentes, ingestas, revisiones, scores RAG y latencia se muestran en el tablero; los datos de Prometheus y Grafana usan volúmenes persistentes.

## Configuración e inicio

Requiere Docker Desktop con Compose; no hace falta instalar Python en el equipo. Copia `.env.example` a `.env` (nunca subas `.env` al repositorio) y define claves robustas para `ADMIN_TOKEN` y `GRAFANA_ADMIN_PASSWORD`. Las APIs administrativas quedan deshabilitadas si `ADMIN_TOKEN` está vacío.

```powershell
Copy-Item .env.example .env
```

Hay dos perfiles. El **local** (hash y mock) se ejecuta sin llamadas ni costos externos, y sus `top-k`, umbrales y embeddings se calibraron contra el set de oro del repositorio:

```env
ROUTER_PROVIDER=hash
EMBEDDINGS_PROVIDER=hash
LLM_PROVIDER=mock
ROUTER_MIN_SCORE=0.30
RAG_TOP_K=2
RAG_MIN_SCORE=0.25
ADMIN_TOKEN=un-token-largo-y-aleatorio
GRAFANA_ADMIN_PASSWORD=una-clave-larga-y-unica
```

El perfil **OpenAI** usa `text-embedding-3-small` y el modelo de `OPENAI_MODEL`. Define `ROUTER_PROVIDER=embeddings`, `EMBEDDINGS_PROVIDER=openai`, `LLM_PROVIDER=openai` y tu `OPENAI_API_KEY`, y recalibra los umbrales con las evaluaciones de más abajo. Al cambiar de proveedor de embeddings hay que reindexar, porque cambia la dimensión del índice.

Inicia los servicios:

```bash
docker compose up -d --build
docker compose ps
```

Para aplicar cambios de código o de `.env`: `docker compose up -d --build --force-recreate app`. Para detener conservando datos: `docker compose down` (no uses `down -v`, porque borra el índice, las revisiones y los datos de Grafana).

URLs locales:

- Chat: <http://127.0.0.1:8001/>
- Administración: <http://127.0.0.1:8001/admin>
- Prometheus: <http://127.0.0.1:9090/>
- Grafana: <http://127.0.0.1:3000/>

Los puertos de Compose se enlazan a `127.0.0.1`; no publiques el prototipo directamente en Internet. El visor anónimo de Grafana es solo de lectura y se mantiene para la demo local.

## Administración de fuentes y revisión humana

1. Abre `/admin` y escribe el valor de `ADMIN_TOKEN`.
2. Carga un PDF no cifrado con texto seleccionable. El límite predeterminado es 25 MiB (`UPLOAD_MAX_BYTES`).
3. El servidor valida formato y texto, guarda el archivo en el volumen persistente y reindexa el corpus. La UI informa errores en lugar de confirmar una carga fallida.
4. En la cola de revisión, un revisor puede aprobar, editar o retirar respuestas. La resolución se agrega a la conversación.

Al añadir o reemplazar una fuente, vuelve a generar el índice:

```bash
docker compose exec app python -m app.ingesta              # reindexa siempre
docker compose exec app python -m app.ingesta --si-falta   # solo si falta el índice o cambió el embedder
docker compose run --rm app python -m app.ingesta          # si la app no arranca por un índice incompatible
```

También puede hacerse por API: `curl.exe -X POST http://127.0.0.1:8001/api/admin/indexar -H "X-Admin-Token: TU_ADMIN_TOKEN"`. La carga o el botón **Reindexar todas las fuentes** de `/admin` actualiza el índice persistente del volumen `datos`. Los archivos de `data/` se copian a la imagen: tras editarlos, ejecuta `docker compose up -d --build app` antes de reindexar.

## Pruebas y evaluación

Las pruebas usan proveedores locales y no llaman a OpenAI ni a Jev. No requieren Python instalado:

```powershell
docker run --rm -v "${PWD}:/app" -w /app -e ROUTER_PROVIDER=hash -e EMBEDDINGS_PROVIDER=hash -e LLM_PROVIDER=mock python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Con Python local: `python -m pip install -r requirements-dev.txt` y `python -m pytest -q`.

El set revisable `data/rag_gold.json` contiene preguntas con fuentes y fragmentos esperados, además de casos sin respuesta. Mide recuperación, no la calidad semántica final de cada respuesta. Calcula precision@k, hit@k, MRR, exactitud de abstención y cobertura, y muestra un barrido de `RAG_MIN_SCORE`. `data/router_gold.json` contiene 28 frases etiquetadas por ruta:

```powershell
docker run --rm -v "${PWD}:/app" -w /app -e ROUTER_PROVIDER=hash -e EMBEDDINGS_PROVIDER=hash -e LLM_PROVIDER=mock python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m eval.eval_rag --proveedor hash && python -m eval.eval_router --proveedor hash"
```

Para medir con OpenAI (usa tu clave y consume crédito):

```powershell
docker run --rm --env-file .env -v "${PWD}:/app" -w /app -e UPLOAD_DIR=/tmp/up -e INDICE_PATH=/tmp/i.npz python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && python -m eval.eval_rag --proveedor openai && python -m eval.eval_router --proveedor embeddings"
```

En la última ejecución local (8 preguntas respondibles y 2 sin contexto), el perfil hash obtuvo precision@2 de 0.625, hit@2 de 1.000, MRR de 0.938 y exactitud de abstención de 1.000. El router hash obtuvo 27/28 (96%) con umbral 0.30, incluyendo la ruta `comparar_productos`. Estos resultados son reproducibles pero el set es pequeño; no equivalen a precisión de producción ni certifican embeddings OpenAI/Jev. Antes de sustentar métricas oficiales, ejecuta las evaluaciones con OpenAI, y revisa y amplía el set de oro con especialistas de Caja Huancayo.

## Límites

- La extracción depende de que el PDF contenga texto legible; documentos escaneados requieren OCR, que no está incluido.
- El índice es un archivo `.npz` en el volumen `datos`, no una base vectorial dedicada; para un corpus mayor conviene migrar a pgvector.
- No hay control de vigencia por fecha o versión del documento, ni filtros por producto o moneda.
- Un solo token administrador, sin roles individuales ni SSO. El enmascarado de PII no cubre nombres propios ni direcciones.
- La guarda de no recomendación del comparador se basa en patrones de texto y no detecta toda forma de recomendar.
- El enrutamiento puede confundir una consulta simple con una comparación (p. ej. "¿Cuál es la tasa vigente de Cuenta Futuro?" con el perfil hash).
- El set de oro inicial es pequeño y debe ser aprobado por expertos. Un score de similitud o una prueba automática no demuestra por sí solo que una respuesta sea correcta.
- El bloqueo determinista cubre patrones conocidos, no todos los ataques posibles. No cargues datos personales ni documentos que no estés autorizado a procesar.
- El grounding numérico detecta cifras sin soporte en los fragmentos citados; no sustituye una revisión semántica o legal.
- El proveedor `mock` y el embedder `hash` son para demo/pruebas. Para el modelo real se requiere configurar claves, cuotas, umbrales y políticas institucionales.
