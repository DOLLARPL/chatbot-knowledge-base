"""Wczytuje bazę wiedzy z pliku Markdown do SQLite.

Format pliku: sekcja jako nagłówek `##`, treść sekcji pod spodem (dowolnie: akapity lub listy).
Jeden nagłówek to jeden wpis w bazie wiedzy.

Uruchomienie:
    python -m app.seed_kb            # wypełnia tylko wtedy, gdy baza wiedzy jest pusta
    python -m app.seed_kb --force    # kasuje wpisy tenanta i wczytuje plik od nowa
    python -m app.seed_kb --plik inny.md
"""
import argparse
import re
import sys
from pathlib import Path

from . import config, db


def parse_markdown(text: str) -> list[tuple[str, str]]:
    """Zwraca listę (sekcja, treść). Nagłówki `##` dzielą wpisy, `#` jest ignorowany."""
    entries: list[tuple[str, str]] = []
    section: str | None = None
    buffer: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if section and "".join(buffer).strip():
                entries.append((section, "\n".join(buffer).strip()))
            section = line[3:].strip()
            buffer = []
        elif line.startswith("# "):
            continue
        else:
            buffer.append(line)

    if section and "".join(buffer).strip():
        entries.append((section, "\n".join(buffer).strip()))
    return entries


def load(tenant: str, path: Path, force: bool = False) -> int:
    if not path.exists():
        raise SystemExit(f"Nie ma pliku bazy wiedzy: {path}")

    existing = db.count_kb(tenant)
    if existing and not force:
        print(f"Baza wiedzy dla '{tenant}' ma już {existing} wpisów, nic nie zmieniam "
              f"(użyj --force, żeby nadpisać).")
        return 0

    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # komentarze w pliku pomijamy
    entries = parse_markdown(text)

    if force:
        with db.connect() as conn:
            conn.execute("DELETE FROM kb_entries WHERE tenant = ?", (tenant,))

    for section, answer in entries:
        db.add_entry(tenant, section, answer)

    print(f"Wczytano {len(entries)} wpisów dla '{tenant}' z {path}")
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description="Wczytanie bazy wiedzy z Markdown do SQLite")
    parser.add_argument("--plik", default=str(config.SEED_FILE))
    parser.add_argument("--tenant", default=config.TENANT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    db.init_db()
    count = load(args.tenant, Path(args.plik), force=args.force)
    if count == 0 and db.count_kb(args.tenant) == 0:
        sys.exit("Baza wiedzy jest pusta, a plik nie zawiera żadnych sekcji '##'.")


if __name__ == "__main__":
    main()
