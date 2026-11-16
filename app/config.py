"""Konfiguracja aplikacji. Czyta plik .env bez dodatkowych bibliotek.

Wszystkie ustawienia, które można zmienić bez dotykania kodu, są tutaj.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _load_env() -> None:
    """Wczytuje .env do zmiennych środowiskowych (istniejące zostawia w spokoju)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()

# --- model i dostawca -------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("MODEL", "google/gemini-2.5-flash-lite")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "deepseek/deepseek-v4-flash")

# Ceny za 1 mln tokenów w USD (zmierzone 20.09.2026, OpenRouter).
PRICE_IN = float(os.environ.get("PRICE_IN", "0.10"))
PRICE_OUT = float(os.environ.get("PRICE_OUT", "0.40"))
USD_PLN = float(os.environ.get("USD_PLN", "3.80"))

# --- dane firmy, której dotyczy ten kontener --------------------------------
TENANT = os.environ.get("TENANT", "demo")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "AutoExpert")
COMPANY_CONTACT = os.environ.get("COMPANY_CONTACT", "telefon 512 300 400")

# --- pliki i baza -----------------------------------------------------------
DB_PATH = Path(os.environ.get("DB_PATH", str(BASE_DIR / "chatbot.db")))
SEED_FILE = Path(os.environ.get("SEED_FILE", str(BASE_DIR / "dane" / "kb-autoexpert.md")))

# --- limity bezpieczeństwa --------------------------------------------------
MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", "500"))
RATE_LIMIT_PER_10MIN = int(os.environ.get("RATE_LIMIT_PER_10MIN", "20"))
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "300"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "300"))
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.2"))
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "60"))

# Domeny, z których wolno wołać API. Puste = bez sprawdzania (tryb lokalny).
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Hasło do panelu (etap 3).
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
