"""Punkt wejścia aplikacji. Adresy, limity i obsługa żądań.

Uruchomienie lokalne:
    .venv/bin/uvicorn app.main:app --reload --port 8090
Dokumentacja interfejsu (klikasz i testujesz):
    http://127.0.0.1:8090/docs
"""
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import admin, chat, config, db, seed_kb

# --- prosty limiter w pamięci procesu ---------------------------------------
# Wystarcza dla jednego kontenera z jednym procesem. Przy większym ruchu
# przenosimy licznik do bazy albo do Redisa.
_windows: dict[str, deque] = defaultdict(deque)


def rate_limit_ok(client_ip: str) -> bool:
    now = time.time()
    window = _windows[client_ip]
    while window and now - window[0] > 600:
        window.popleft()
    if len(window) >= config.RATE_LIMIT_PER_10MIN:
        return False
    window.append(now)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if db.count_kb(config.TENANT) == 0:
        try:
            seed_kb.load(config.TENANT, config.SEED_FILE)
        except SystemExit as exc:
            print(f"[start] baza wiedzy nie została wczytana: {exc}")
    yield


app = FastAPI(title=f"Chatbot {config.COMPANY_NAME}", version="0.1.0", lifespan=lifespan)

if config.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=config.MAX_QUESTION_CHARS)
    session_id: str = Field(default="", max_length=64)
    page_url: str = Field(default="", max_length=300)


def client_ip(request: Request) -> str:
    """Adres klienta. nginx przekazuje go w X-Forwarded-For (patrz konfiguracja serwera)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return (forwarded.split(",")[0].strip() if forwarded else
            (request.client.host if request.client else "nieznany"))


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "tenant": config.TENANT,
        "firma": config.COMPANY_NAME,
        "model": config.MODEL,
        "wpisy_w_bazie": db.count_kb(config.TENANT),
        "pytania_dzis": db.questions_today(config.TENANT),
        "dzienny_limit": config.DAILY_LIMIT,
        "klucz_api": bool(config.OPENROUTER_API_KEY),
    }


@app.get("/api/statystyki")
def statystyki() -> dict:
    return db.stats(config.TENANT)


@app.post("/api/chat")
def api_chat(payload: ChatRequest, request: Request):
    origin = request.headers.get("origin", "")

    if config.ALLOWED_ORIGINS and origin and origin not in config.ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Ta domena nie ma dostępu do tego bota.")

    if not config.OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="Brak klucza API na serwerze.")

    if db.questions_today(config.TENANT) >= config.DAILY_LIMIT:
        raise HTTPException(status_code=429,
                            detail="Dzienny limit pytań w demo został wyczerpany. Zapraszam jutro.")

    ip = client_ip(request)
    if not rate_limit_ok(ip):
        raise HTTPException(status_code=429, detail="Za dużo pytań w krótkim czasie. Spróbuj za chwilę.")

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Puste pytanie.")

    result = chat.ask(
        tenant=config.TENANT,
        question=question,
        session_id=payload.session_id or "brak-sesji",
        client_ip=ip,
        origin=origin,
    )
    result["session_id"] = payload.session_id
    return JSONResponse(result)


@app.get("/")
def index() -> dict:
    return {
        "co_to": f"Backend chatbota {config.COMPANY_NAME}",
        "adresy": ["/admin (panel: wiedza, rozmowy, luki, eksport CSV)",
                   "/demo (strona pokazowa warsztatu z widgetem)", "/widget.js",
                   "/static/wklejka-test.html (strona testowa wklejki)",
                   "/health", "/api/chat (POST)", "/api/statystyki", "/docs"],
        "info": "Etapy 0-5 zrobione: backend, widget, strona /demo, panel /admin, wdrożenie na VPS.",
    }


@app.get("/demo")
def demo() -> FileResponse:
    """Strona pokazowa warsztatu z wklejonym widgetem: https://chat.jnxautomation.pl/demo

    To wizytówka dla klienta nietechnicznego. Strona-wklejka z agresywnym CSS
    (`/static/wklejka-test.html`) zostaje jako dowód izolacji stylów dla nas.
    """
    plik = config.BASE_DIR / "app" / "static" / "demo.html"
    if not plik.exists():
        raise HTTPException(status_code=404, detail="Strona demo jeszcze nie istnieje.")
    return FileResponse(plik, media_type="text/html")


@app.get("/widget.js")
def widget_js() -> FileResponse:
    """Plik widgetu pod adresem z wklejki: https://chat.jnxautomation.pl/widget.js

    Ten sam plik leży też w /static/widget.js. Adres /widget.js jest krótszy i docelowy.
    """
    plik = config.BASE_DIR / "app" / "static" / "widget.js"
    if not plik.exists():
        raise HTTPException(status_code=404, detail="Widget jeszcze nie istnieje.")
    return FileResponse(plik, media_type="application/javascript",
                        headers={"Cache-Control": "public, max-age=300"})


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow: /api/\nDisallow: /admin\n"


app.include_router(admin.router)

app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "app" / "static")), name="static")
