"""Baza SQLite: baza wiedzy i dziennik rozmów.

Jeden plik na dysku, bez serwera bazy. Tryb WAL, żeby zapisy nie blokowały odczytów.
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant        TEXT    NOT NULL,
    section       TEXT    NOT NULL,
    answer        TEXT    NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant      TEXT    NOT NULL,
    session_id  TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    question    TEXT    NOT NULL,
    answer      TEXT    NOT NULL,
    answered    INTEGER NOT NULL,
    sources     TEXT    NOT NULL DEFAULT '',
    model       TEXT    NOT NULL,
    latency_ms  INTEGER NOT NULL,
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    cost_usd    REAL    NOT NULL DEFAULT 0,
    client_ip   TEXT    NOT NULL DEFAULT '',
    origin      TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_messages_tenant_date ON messages (tenant, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_unanswered ON messages (tenant, answered);
CREATE INDEX IF NOT EXISTS idx_kb_tenant ON kb_entries (tenant, active);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


# --- baza wiedzy ------------------------------------------------------------

def kb_entries(tenant: str, only_active: bool = True) -> list[dict]:
    query = "SELECT * FROM kb_entries WHERE tenant = ?"
    if only_active:
        query += " AND active = 1"
    query += " ORDER BY id"
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, (tenant,)).fetchall()]


def kb_entries_all(tenant: str) -> list[dict]:
    return kb_entries(tenant, only_active=False)


def count_kb(tenant: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM kb_entries WHERE tenant = ? AND active = 1", (tenant,)
        ).fetchone()
    return int(row["n"])


def add_entry(tenant: str, section: str, answer: str, active: bool = True) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO kb_entries (tenant, section, answer, active, updated_at) VALUES (?,?,?,?,?)",
            (tenant, section, answer, 1 if active else 0, _now()),
        )
        return int(cur.lastrowid)


def update_entry(entry_id: int, section: str | None = None, answer: str | None = None,
                 active: bool | None = None) -> None:
    fields, values = [], []
    if section is not None:
        fields.append("section = ?"); values.append(section)
    if answer is not None:
        fields.append("answer = ?"); values.append(answer)
    if active is not None:
        fields.append("active = ?"); values.append(1 if active else 0)
    if not fields:
        return
    fields.append("updated_at = ?"); values.append(_now())
    values.append(entry_id)
    with connect() as conn:
        conn.execute(f"UPDATE kb_entries SET {', '.join(fields)} WHERE id = ?", values)


def delete_entry(entry_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM kb_entries WHERE id = ?", (entry_id,))


def kb_text(tenant: str) -> str:
    """Baza wiedzy jako tekst do promptu. Sekcja plus jej treść, jedna pod drugą."""
    parts = []
    for entry in kb_entries(tenant):
        parts.append(f"### {entry['section']}\n{entry['answer'].strip()}")
    return "\n\n".join(parts)


# --- dziennik rozmów --------------------------------------------------------

def log_message(tenant: str, session_id: str, question: str, answer: str, answered: bool,
                sources: str, model: str, latency_ms: int, tokens_in: int, tokens_out: int,
                cost_usd: float, client_ip: str, origin: str) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO messages (tenant, session_id, created_at, question, answer, answered,
                                     sources, model, latency_ms, tokens_in, tokens_out, cost_usd,
                                     client_ip, origin)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant, session_id, _now(), question, answer, 1 if answered else 0, sources, model,
             latency_ms, tokens_in, tokens_out, cost_usd, client_ip, origin),
        )
        return int(cur.lastrowid)


def questions_today(tenant: str) -> int:
    """Liczba pytań od początku dnia UTC. Używane do dziennego limitu kosztu."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE tenant = ? AND created_at LIKE ?",
            (tenant, f"{today}%"),
        ).fetchone()
    return int(row["n"])


def stats(tenant: str) -> dict:
    """Skrót dla panelu: liczba rozmów, koszt, odsetek pytań bez odpowiedzi."""
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN answered = 0 THEN 1 ELSE 0 END) AS unanswered,
                      COALESCE(SUM(cost_usd), 0) AS cost,
                      COALESCE(AVG(latency_ms), 0) AS avg_latency
               FROM messages WHERE tenant = ?""",
            (tenant,),
        ).fetchone()
    total = int(row["total"] or 0)
    return {
        "total": total,
        "unanswered": int(row["unanswered"] or 0),
        "unanswered_pct": round(100.0 * (row["unanswered"] or 0) / total, 1) if total else 0.0,
        "cost_usd": round(float(row["cost"] or 0), 4),
        "cost_pln": round(float(row["cost"] or 0) * config.USD_PLN, 2),
        "avg_latency_ms": int(row["avg_latency"] or 0),
    }


# --- panel (etap 3) ---------------------------------------------------------
# Czas trzymamy w bazie w UTC, a panel i filtry liczą w czasie warszawskim.
# Pole daty w panelu znaczy więc „dzień u Jana”, nie „dzień UTC”.

def strefa():
    """Strefa czasowa panelu. Gdy system nie ma bazy stref, zostaje stałe +2 (czas letni)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Warsaw")
    except Exception:
        return timezone(timedelta(hours=2))


def _granica(dzien: str, koniec_dnia: bool) -> str | None:
    """Data `RRRR-MM-DD` z panelu na granicę UTC. None, gdy data pusta albo błędna."""
    if not dzien:
        return None
    try:
        data = datetime.strptime(dzien.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    if koniec_dnia:
        data = data.replace(hour=23, minute=59, second=59)
    return data.replace(tzinfo=strefa()).astimezone(timezone.utc).isoformat(timespec="seconds")


def _filtr_czasu(od: str | None, do: str | None) -> tuple[str, list]:
    warunki, wartosci = [], []
    poczatek, koniec = _granica(od or "", False), _granica(do or "", True)
    if poczatek:
        warunki.append("created_at >= ?"); wartosci.append(poczatek)
    if koniec:
        warunki.append("created_at <= ?"); wartosci.append(koniec)
    return (" AND " + " AND ".join(warunki) if warunki else ""), wartosci


def luki_bez_odpowiedzi(tenant: str, od: str | None = None, do: str | None = None) -> list[dict]:
    """Pytania, na które bot nie miał wiedzy.

    Bierzemy wyłącznie wpisy z `sources = 'luka w wiedzy'`. Wiersz z awarią modelu
    (odpowiedź techniczna, `sources` = treść błędu) też ma `answered = 0`, ale luką
    w wiedzy nie jest — to awaria, a nie brakujący fakt.
    """
    zapytanie = ("SELECT id, session_id, created_at, question, answer FROM messages "
                 "WHERE tenant = ? AND answered = 0 AND sources = 'luka w wiedzy'")
    filtr, wartosci = _filtr_czasu(od, do)
    zapytanie += filtr + " ORDER BY created_at, id"
    with connect() as conn:
        return [dict(r) for r in conn.execute(zapytanie, (tenant, *wartosci)).fetchall()]


def rozmowy(tenant: str, od: str | None = None, do: str | None = None,
            fraza: str | None = None, limit: int = 300) -> list[dict]:
    """Dziennik rozmów dla panelu: najnowsze u góry, z filtrem po dacie i frazie."""
    zapytanie = ("SELECT id, session_id, created_at, question, answer, answered, model, "
                 "latency_ms, cost_usd, client_ip, origin FROM messages WHERE tenant = ?")
    wartosci: list = [tenant]
    filtr, wartosci_czasu = _filtr_czasu(od, do)
    zapytanie += filtr
    wartosci += wartosci_czasu
    if fraza and fraza.strip():
        zapytanie += " AND (question LIKE ? OR answer LIKE ?)"
        wzorzec = f"%{fraza.strip()}%"
        wartosci += [wzorzec, wzorzec]
    zapytanie += " ORDER BY id DESC LIMIT ?"
    wartosci.append(int(limit))
    with connect() as conn:
        return [dict(r) for r in conn.execute(zapytanie, wartosci).fetchall()]


def watek_sesji(tenant: str, session_id: str) -> list[dict]:
    """Wszystkie pytania jednej sesji, od najstarszego — pełny wątek rozmowy."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT id, created_at, question, answer, answered, latency_ms, cost_usd
               FROM messages WHERE tenant = ? AND session_id = ? ORDER BY id""",
            (tenant, session_id)).fetchall()]


def statystyki_panelu(tenant: str) -> dict:
    """Liczby do nagłówka panelu. Luki liczymy tak samo jak lista luk (bez awarii modelu)."""
    with connect() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN answered = 0 AND sources = 'luka w wiedzy' THEN 1 ELSE 0 END)
                        AS luki,
                      SUM(CASE WHEN answered = 0 AND sources <> 'luka w wiedzy' THEN 1 ELSE 0 END)
                        AS awarie,
                      COALESCE(SUM(cost_usd), 0) AS koszt,
                      COALESCE(AVG(latency_ms), 0) AS sredni_czas
               FROM messages WHERE tenant = ?""",
            (tenant,)).fetchone()
        wpisy = conn.execute(
            "SELECT COUNT(*) AS n FROM kb_entries WHERE tenant = ? AND active = 1",
            (tenant,)).fetchone()["n"]

    total, luki = int(row["total"] or 0), int(row["luki"] or 0)
    return {
        "wpisy": int(wpisy),
        "pytania": total,
        "luki": luki,
        "luki_pct": round(100.0 * luki / total, 1) if total else 0.0,
        "awarie_modelu": int(row["awarie"] or 0),
        "sredni_czas_ms": int(row["sredni_czas"] or 0),
        "koszt_usd": round(float(row["koszt"] or 0), 4),
        "koszt_pln": round(float(row["koszt"] or 0) * config.USD_PLN, 2),
    }
