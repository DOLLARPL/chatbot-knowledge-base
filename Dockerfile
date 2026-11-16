FROM python:3.13-slim

# Obraz demo chatbota: FastAPI + uvicorn, jeden proces, jedna baza SQLite.
# Klucz OpenRouter NIE wchodzi do obrazu — ląduje na serwerze w pliku .env
# przekazywanym przez docker compose (env_file) i trzymanym z prawami 600.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install --no-cache-dir \
        "fastapi==0.141.1" \
        "uvicorn==0.53.0" \
        "httpx==0.28.1"

COPY app ./app
COPY dane ./dane

# Baza rozmów leży poza obrazem (wolumen), żeby przetrwała przebudowę kontenera.
ENV DB_PATH=/data/chatbot.db

VOLUME ["/data"]
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=4).status==200 else 1)"

# Jeden worker: limiter tempa siedzi w pamięci procesu, więc więcej workerów
# rozjechałoby licznik pytań na IP.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
