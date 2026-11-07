FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONUTF8=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY rules ./rules
COPY web ./web
COPY data ./data
EXPOSE 8000
# Al arrancar: indexa el documento solo si falta el índice (o si cambiaste de embedder) y levanta la API.
CMD ["sh", "-c", "python -m app.ingesta --si-falta && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
