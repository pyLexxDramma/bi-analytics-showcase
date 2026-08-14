FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Written by deploy scripts every run → invalidates app layers even if BuildKit mis-caches.
COPY .build-id ./BUILD_ID
ARG GIT_SHA=unknown
ENV WEBAPP_GIT_SHA=$GIT_SHA

ENV PYTHONUNBUFFERED=1
ENV WEBAPP_DATA_MODE=synthetic
# 1 воркер ≈ 230 МБ RSS после прогрева матрицы девпроектов (ГДРС тяжелее — был OOM).
# Поднимать WEBAPP_API_WORKERS только после замера свободной памяти на VPS.
ENV WEBAPP_API_WORKERS=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEBAPP_API_WORKERS:-1} --timeout-keep-alive 75"]
