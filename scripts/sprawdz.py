"""Małe narzędzie do sprawdzania, czy backend odpowiada - lokalnie albo przez tunel.

Użycie:
    .venv/bin/python scripts/sprawdz.py                        # lokalnie 127.0.0.1:8090
    .venv/bin/python scripts/sprawdz.py --adres http://127.0.0.1:8090
    .venv/bin/python scripts/sprawdz.py --pytanie "Czy pracujecie w sobotę?"
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def pobierz(url: str, timeout: int = 20) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as odpowiedz:
        return odpowiedz.read().decode("utf-8", "replace")


def zapytaj(adres: str, pytanie: str) -> dict:
    dane = json.dumps({"question": pytanie, "session_id": "sprawdz"}).encode("utf-8")
    zadanie = urllib.request.Request(f"{adres.rstrip('/')}/api/chat", data=dane,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(zadanie, timeout=120) as odpowiedz:
            return json.loads(odpowiedz.read().decode("utf-8"))
    except urllib.error.HTTPError as blad:
        return {"blad": f"HTTP {blad.code}", "tresc": blad.read().decode("utf-8", "replace")[:300]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adres", default="http://127.0.0.1:8090")
    parser.add_argument("--pytanie", default="")
    args = parser.parse_args()

    try:
        stan = json.loads(pobierz(f"{args.adres.rstrip('/')}/health"))
    except Exception as blad:  # noqa: BLE001
        sys.exit(f"Backend nie odpowiada pod {args.adres}: {type(blad).__name__}: {blad}")

    print("backend odpowiada")
    print(f"  firma: {stan['firma']}, tenant: {stan['tenant']}")
    print(f"  model: {stan['model']}, wpisy w bazie: {stan['wpisy_w_bazie']}")
    print(f"  pytania dzis: {stan['pytania_dzis']} z {stan['dzienny_limit']}")
    print(f"  klucz API na serwerze: {'jest' if stan['klucz_api'] else 'BRAK'}")

    if args.pytanie:
        wynik = zapytaj(args.adres, args.pytanie)
        print("\npytanie:", args.pytanie)
        if "blad" in wynik:
            print("  ", wynik["blad"], wynik.get("tresc", ""))
            sys.exit(1)
        print("  odpowiedz:", wynik.get("answer"))
        print(f"  z bazy wiedzy: {'tak' if wynik.get('answered') else 'nie (luka w wiedzy)'}")
        print(f"  czas: {wynik.get('latency_ms')} ms, model: {wynik.get('model')}")


if __name__ == "__main__":
    main()
