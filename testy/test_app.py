"""Testy backendu. Nie łączą się z internetem: wywołanie modelu jest podmieniane.

Uruchomienie:
    .venv/bin/python -m pytest testy/test_app.py -v
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import chat, config, db, main, seed_kb  # noqa: E402

PRZYKLADOWA_BAZA = """# komentarz ignorowany
## Godziny otwarcia
Poniedziałek-piątek 8:00-17:00.
## Cennik
Przegląd okresowy od 250 zł.
"""


@pytest.fixture()
def srodowisko(tmp_path, monkeypatch):
    """Tymczasowa baza i plik wiedzy dla każdego testu."""
    baza = tmp_path / "test.db"
    plik = tmp_path / "kb.md"
    plik.write_text(PRZYKLADOWA_BAZA, encoding="utf-8")

    monkeypatch.setattr(config, "DB_PATH", baza)
    monkeypatch.setattr(config, "SEED_FILE", plik)
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "klucz-testowy")
    main._windows.clear()
    db.init_db()
    seed_kb.load(config.TENANT, plik)
    return {"baza": baza, "plik": plik}


def podmien_model(monkeypatch, odpowiedz: str, tokens_in: int = 100, tokens_out: int = 20):
    """Podstawia odpowiedź modelu zamiast prawdziwego wywołania sieciowego."""
    def falszywe(messages, model):
        return {"answer": odpowiedz, "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out}
    monkeypatch.setattr(chat, "call_model", falszywe)


def test_parser_dzieli_sekcje():
    wpisy = seed_kb.parse_markdown(PRZYKLADOWA_BAZA)
    assert [w[0] for w in wpisy] == ["Godziny otwarcia", "Cennik"]
    assert "250 zł" in wpisy[1][1]


def test_baza_wiedzy_wchodzi_do_sqlite(srodowisko):
    assert db.count_kb(config.TENANT) == 2
    tekst = db.kb_text(config.TENANT)
    assert "Godziny otwarcia" in tekst and "250 zł" in tekst


def test_zdrowie_aplikacji(srodowisko):
    with TestClient(main.app) as klient:
        dane = klient.get("/health").json()
    assert dane["ok"] is True
    assert dane["wpisy_w_bazie"] == 2
    assert dane["model"] == config.MODEL


def test_odpowiedz_z_bazy_i_zapis_do_dziennika(srodowisko, monkeypatch):
    podmien_model(monkeypatch, "Jesteśmy otwarci od poniedziałku do piątku, 8:00-17:00.")
    with TestClient(main.app) as klient:
        odp = klient.post("/api/chat", json={"question": "Kiedy otwieracie?", "session_id": "s1"})
    assert odp.status_code == 200
    dane = odp.json()
    assert dane["answered"] is True
    assert "8:00" in dane["answer"]
    assert dane["cost_usd"] > 0

    with db.connect() as conn:
        wiersz = conn.execute("SELECT * FROM messages").fetchone()
    assert wiersz["question"] == "Kiedy otwieracie?"
    assert wiersz["answered"] == 1
    assert wiersz["tokens_in"] == 100


def test_brak_wiedzy_jest_oznaczony_i_bez_prefiksu(srodowisko, monkeypatch):
    podmien_model(monkeypatch, "BRAK_WIEDZY: Nie mam tej informacji. Proszę dzwonić: 512 300 400.")
    with TestClient(main.app) as klient:
        dane = klient.post("/api/chat", json={"question": "Naprawiacie Tesle?"}).json()
    assert dane["answered"] is False
    assert dane["answer"].startswith("Nie mam tej informacji")
    assert "BRAK_WIEDZY" not in dane["answer"]
    assert db.stats(config.TENANT)["unanswered"] == 1


def test_limit_tempa_po_ip(srodowisko, monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_PER_10MIN", 3)
    podmien_model(monkeypatch, "Jesteśmy otwarci 8:00-17:00.")
    with TestClient(main.app) as klient:
        kody = [klient.post("/api/chat", json={"question": f"pytanie {i}"}).status_code
                for i in range(5)]
    assert kody[:3] == [200, 200, 200]
    assert kody[3] == 429 and kody[4] == 429


def test_dzienny_limit_pytan(srodowisko, monkeypatch):
    monkeypatch.setattr(config, "DAILY_LIMIT", 1)
    podmien_model(monkeypatch, "Odpowiedź z bazy.")
    with TestClient(main.app) as klient:
        assert klient.post("/api/chat", json={"question": "pierwsze"}).status_code == 200
        odp = klient.post("/api/chat", json={"question": "drugie"})
    assert odp.status_code == 429
    assert "limit" in odp.json()["detail"].lower()


def test_obca_domena_dostaje_403(srodowisko, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_ORIGINS", ["https://chat.jnxautomation.pl"])
    podmien_model(monkeypatch, "Odpowiedź.")
    with TestClient(main.app) as klient:
        odp = klient.post("/api/chat", json={"question": "Cześć"},
                          headers={"Origin": "https://obca-domena.pl"})
    assert odp.status_code == 403


def test_za_dlugie_pytanie_odrzucone(srodowisko, monkeypatch):
    podmien_model(monkeypatch, "Odpowiedź.")
    with TestClient(main.app) as klient:
        odp = klient.post("/api/chat", json={"question": "x" * (config.MAX_QUESTION_CHARS + 1)})
    assert odp.status_code == 422


def test_brak_klucza_api_daje_503(srodowisko, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    with TestClient(main.app) as klient:
        odp = klient.post("/api/chat", json={"question": "Cześć"})
    assert odp.status_code == 503


def test_awaria_modelu_nie_wysypuje_api(srodowisko, monkeypatch):
    def wybuch(messages, model):
        raise ValueError("model nie zwrócił treści odpowiedzi")
    monkeypatch.setattr(chat, "call_model", wybuch)
    with TestClient(main.app) as klient:
        odp = klient.post("/api/chat", json={"question": "Cześć"})
    assert odp.status_code == 200
    dane = odp.json()
    assert dane["answered"] is False
    assert "problem techniczny" in dane["answer"]
    assert dane["error"]


def test_robots_blokuje_api(srodowisko):
    with TestClient(main.app) as klient:
        tresc = klient.get("/robots.txt").text
    assert "Disallow: /api/" in tresc
