FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 huiyan \
    && useradd --uid 10001 --gid huiyan --create-home huiyan

COPY --chown=huiyan:huiyan . .
RUN mkdir -p /app/data/uploads/inspections \
    && chown -R huiyan:huiyan /app/data

USER huiyan
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

CMD ["python", "scripts/start_production.py"]
