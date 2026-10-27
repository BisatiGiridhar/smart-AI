FROM python:3.11-slim
ARG INSTALL_ML=true
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi
COPY . .
RUN useradd --create-home --uid 10001 saiha && mkdir -p /data && chown -R saiha /data /app
USER saiha
ENV STORAGE_DIR=/data/files DATASET_DIR=/data/datasets CHROMA_DIR=/data/chroma
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
