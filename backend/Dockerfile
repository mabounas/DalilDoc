# Contexte de build : racine du monorepo (le backend importe rag/ et data/).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY rag/ rag/
COPY data/knowledge/ data/knowledge/
COPY backend/ backend/

WORKDIR /srv/backend
# /srv/cache/tts : volume du cache audio (créé ici pour appartenir à l'utilisateur applicatif).
RUN useradd --create-home --uid 1000 wathiqa && mkdir -p /srv/cache/tts && chown -R wathiqa /srv
ENV TTS_CACHE_DIR=/srv/cache/tts
USER wathiqa

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
