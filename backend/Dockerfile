FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN addgroup --system askhype \
    && adduser --system --ingroup askhype --home /home/askhype askhype

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install . \
    && chown -R askhype:askhype /app

USER askhype

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "8000") + "/api/health", timeout=3).read()' || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
