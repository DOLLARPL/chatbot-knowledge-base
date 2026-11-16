"""Rozdzielanie pytań bez odpowiedzi na cztery kupki (etap 3).

Lista luk w wiedzy nie może być jedną listą zadań. Realne dane z dziennika demo mieszają
cztery różne rzeczy (ustalenie z 20.09.2026, makieta `assets/mapa-wiedzy.html`):

1. `dopisz`  — prawdziwy brak wiedzy. Klient odpowiada w dwie minuty i bot przestaje milczeć.
2. `decyzja` — temat, o którym firma świadomie nie mówi przez czat (ceny poza cennikiem).
               To nie brak wiedzy: baza ma to powiedzieć wprost, żeby bot odpowiedział,
               a nie mówił „nie mam informacji”.
3. `filtr`   — temat, który baza już rozstrzyga zasadą (odmowa przy próbie wyciągnięcia promptu,
               wymuszeniu ceny, pytaniu o bezpieczeństwo albo o konkurencję), plus próby zmiany roli.
               To nie luka w bazie, tylko sygnał o warstwie odmowy lub o prompcie.
4. `szum`    — klawiatura i test techniczny. Odsiewamy po kształcie pytania.

Klasyfikacja jest heurystyczna: działa na kształcie pytania i słowach kluczowych, nie na treści
odpowiedzi modelu. Dlatego każda pozycja w panelu niesie powód, a nie tylko etykietę kupki.
Reguły są niżej w tym pliku — przy nowym kliencie to pierwsze miejsce do przejrzenia.
"""
import re
import unicodedata
from collections import defaultdict

KUPKI = ("dopisz", "decyzja", "filtr", "szum")

NAZWY = {
    "dopisz": "Dopisz do bazy",
    "decyzja": "Decyzja klienta",
    "filtr": "Filtr, nie baza",
    "szum": "Szum",
}

OPISY = {
    "dopisz": "Prawdziwy brak wiedzy. Klient odpowie w 2 minuty i bot przestaje milczeć.",
    "decyzja": "Świadomie nie podajemy tej ceny przez czat — ale baza musi to mówić wprost, "
               "żeby bot odpowiedział, a nie milczał.",
    "filtr": "Próba wyciągnięcia promptu, wymuszenie ceny albo temat, który baza rozstrzyga "
             "zasadą. Nie nowy wpis, tylko warstwa odmowy.",
    "szum": "Klawiatura i test techniczny. Odsiać, żeby nie zaśmiecało listy.",
}

# --- reguły -----------------------------------------------------------------

# Kolejność ma znaczenie: przypadek z pierwszej pasującej reguły wygrywa.
FILTR_REGUŁY = (
    ("próba wyciągnięcia promptu lub zmiany roli",
     ("zignoruj", "ignoruj", "poprzednie instrukcj", "instrukcj", "prompt", "systemow",
      "jesteś teraz", "jestes teraz", "nowa rola", "zmień rolę", "zmien role", "udawaj",
      "wciel się", "odgrywaj", "przetłumacz", "streść", "stresc")),
    ("wymuszenie ceny",
     ("jakąkolwiek cen", "jakakolwiek cen", "jakąś cen", "nawet orientacyjn", "orientacyjną kwot",
      "nikt tego nie sprawdzi", "daj cen", "podaj mi cen", "musisz podać cen", "musisz podac cen")),
    ("pytanie o bezpieczeństwo (baza kieruje na telefon)",
     ("bezpieczeństw", "bezpieczenstw", "opona", "oponę", "opone", "guz", "wypadek",
      "uszkodzon", "jechać z", "jechac z", "uratować", "uratowac")),
    ("pytanie o konkurencję (baza zakazuje oceniania)",
     ("konkurencj", "inny warsztat", "innym warsztacie", "sąsiedniej ulicy", "sasiedniej ulicy",
      "lepszy od was", "porówna", "porowna")),
)

# Tematy, których cennik świadomie nie zawiera: wpis „Wycena napraw i oględziny” mówi,
# że te kwoty podajemy wyłącznie po oględzinach pojazdu.
DEZYCJA_TEMATY = ("rozrz", "sprzęg", "sprzeg", "skrzyn", "naprawa silnika", "naprawy silnika",
                  "remont silnika", "wymiana silnika")

SAMOGLOSKI = set("aąeęioóuy")
RZEDY_KLAWIATURY = ("qwertyuiop", "asdfghjkl", "zxcvbnm")


def _bez_ogonków(tekst: str) -> str:
    """Wersja bez polskich znaków, żeby reguły łapały też tekst pisany bez ogonków."""
    rozłożone = unicodedata.normalize("NFKD", tekst.lower())
    return "".join(c for c in rozłożone if not unicodedata.combining(c))


def _powtorzenia(tekst: str) -> bool:
    """Trzy identyczne znaki pod rząd to prawie zawsze klawiatura („aaaa”, „....”)."""
    return re.search(r"(.)\1\1", tekst) is not None


def _zbitka_klawiatury(tekst: str) -> bool:
    """Wyraz złożony wyłącznie z liter jednego rzędu klawiatury: „asdfghjkl”.

    Liczymy litery jednego wyrazu, nie całego zdania — zwykły polski tekst ma słowa,
    które przypadkiem trafiają w jeden rząd klawiatury, i to nie jest klawiatura.
    """
    for wyraz in re.findall(r"[a-z;']+", tekst):
        litery = [c for c in wyraz if c.isalpha()]
        if len(litery) < 5:
            continue
        samogloski = sum(c in SAMOGLOSKI for c in litery) / len(litery)
        # „asdfghjkl” to jeden rząd klawiatury i prawie zero samogłosek. Słowo z jednego rzędu,
        # ale z samogłoskami na miejscu („rowery”, „typowo”), jest zwykłym słowem.
        if samogloski < 0.34 and any(all(c in rzad for c in litery) for rzad in RZEDY_KLAWIATURY):
            return True
    return False


def czy_szum(pytanie: str) -> bool:
    """Klawiatura, tester, przypadkowe znaki. Liczy się kształt pytania, nie jego treść."""
    tekst = pytanie.strip()
    if len(tekst) < 3:
        return True
    if _powtorzenia(tekst.lower()):
        return True

    litery = [c for c in tekst.lower() if c.isalpha()]
    if not litery:
        return True
    if len(litery) >= 6 and sum(c in SAMOGLOSKI for c in litery) / len(litery) < 0.2:
        return True

    return _zbitka_klawiatury(tekst.lower())


def kupka(pytanie: str) -> tuple[str, str]:
    """Zwraca (kupka, powód). Powód jest krótkim uzasadnieniem widocznym w panelu."""
    if czy_szum(pytanie):
        return "szum", "klawiatura albo test techniczny"

    bez_ogonków = _bez_ogonków(pytanie)
    for powód, słowa in FILTR_REGUŁY:
        if any(słowo in bez_ogonków for słowo in słowa):
            return "filtr", powód

    for temat in DEZYCJA_TEMATY:
        if temat in bez_ogonków:
            return "decyzja", f"cena poza cennikiem ({temat}), podajemy ją po oględzinach"

    return "dopisz", "brak wpisu w bazie wiedzy"


def klucz_frazy(pytanie: str) -> str:
    """Postać pytania do łączenia w jedną pozycję listy (wielkość liter i interpunkcja bez znaczenia)."""
    tekst = _bez_ogonków(pytanie).lower()
    tekst = re.sub(r"[^a-z0-9 ]+", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip()


def zestawienie(pytania: list[dict]) -> dict:
    """Grupuje pytania bez odpowiedzi po frazie i rozkłada na cztery kupki.

    `pytania` to wiersze z `db.luki_bez_odpowiedzi`. Zwraca gotową strukturę dla panelu i CSV.
    """
    zebrane: dict[str, dict[str, dict]] = {k: {} for k in KUPKI}

    for wiersz in pytania:
        tekst = (wiersz.get("question") or "").strip()
        if not tekst:
            continue
        grupa, powód = kupka(tekst)
        klucz = klucz_frazy(tekst) or tekst.lower()
        pozycja = zebrane[grupa].get(klucz)
        if pozycja is None:
            pozycja = {
                "fraza": tekst,
                "ile": 0,
                "ostatnio": wiersz.get("created_at", ""),
                "powod": powód,
                "odpowiedz": (wiersz.get("answer") or "").strip(),
            }
            zebrane[grupa][klucz] = pozycja
        pozycja["ile"] += 1
        if (wiersz.get("created_at") or "") > pozycja["ostatnio"]:
            pozycja["ostatnio"] = wiersz.get("created_at", "")
            pozycja["odpowiedz"] = (wiersz.get("answer") or "").strip()

    wynik, suma = {}, 0
    for grupa in KUPKI:
        # Dwie pieczenie w jednym: najczęstsze u góry, a przy tej samej liczbie — najnowsze.
        pozycje = sorted(zebrane[grupa].values(), key=lambda p: p["ostatnio"], reverse=True)
        pozycje.sort(key=lambda p: -p["ile"])
        ile_pytan = sum(p["ile"] for p in pozycje)
        suma += ile_pytan
        wynik[grupa] = {
            "nazwa": NAZWY[grupa],
            "opis": OPISY[grupa],
            "ile_pytan": ile_pytan,
            "ile_fraz": len(pozycje),
            "pozycje": pozycje,
        }
    return {"kupki": wynik, "razem_pytan": suma}


def podsumowanie_wg_kupki(pytania: list[dict]) -> dict[str, int]:
    """Liczba pytań w każdej kupce, bez budowania całego zestawienia (na potrzeby nagłówka panelu)."""
    liczniki = defaultdict(int)
    for wiersz in pytania:
        tekst = (wiersz.get("question") or "").strip()
        if tekst:
            liczniki[kupka(tekst)[0]] += 1
    return {grupa: liczniki.get(grupa, 0) for grupa in KUPKI}
