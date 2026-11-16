"""Panel `/admin` (etap 3): edycja wiedzy, rozmowy, luki rozdzielone na cztery kupki, eksport CSV.

Jedno hasło z `.env` (`ADMIN_PASSWORD`), jedna sesja w ciasteczku, bez frameworka frontowego.
Ciasteczko jest podpisane kluczem liczonym z hasła, więc restart aplikacji nie wylogowuje
(stan trzyma się w podpisie, a nie w pamięci procesu). Hasło nigdy nie jedzie do przeglądarki.

Bezpieczeństwo:
- brak `ADMIN_PASSWORD` = panel zwraca 503 i nie istnieje żadna droga wejścia,
- 5 nieudanych prób logowania z jednego IP blokuje logowanie na 10 minut,
- `/admin` i `/api/admin` są wyłączone w `robots.txt`,
- wszystkie trasy panelu poza logowaniem wymagają ciasteczka; brak ciasteczka to 401 (API)
  albo przekierowanie na `/admin/login` (strona).

Pytanie testowe z panelu (`POST /api/admin/test`) przechodzi tę samą drogę co pytanie klienta,
ale nie trafia do dziennika — inaczej testy właściciela zaśmiecałyby listę luk.
"""
import csv
import hashlib
import hmac
import io
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import chat, config, db, luki

router = APIRouter()

CIASTECZKO = "jnx_admin"
SESJA_SEKUND = 8 * 3600
PROBY_LOGOWANIA = 5
BLOKADA_SEKUND = 600

_nieudane: dict[str, deque] = defaultdict(deque)


# --- sesja ------------------------------------------------------------------

def _sekret() -> bytes:
    """Klucz podpisu ciasteczka. Zmiana hasła unieważnia wszystkie sesje."""
    return hashlib.sha256(f"panel:{config.ADMIN_PASSWORD}".encode("utf-8")).digest()


def _podpis(do_kiedy: int) -> str:
    return hmac.new(_sekret(), str(do_kiedy).encode("utf-8"), hashlib.sha256).hexdigest()


def zrob_ciasteczko() -> str:
    koniec = int(time.time()) + SESJA_SEKUND
    return f"{koniec}.{_podpis(koniec)}"


def ciasteczko_ok(wartosc: str) -> bool:
    if not wartosc or "." not in wartosc or not config.ADMIN_PASSWORD:
        return False
    koniec, podpis = wartosc.rsplit(".", 1)
    if not koniec.isdigit() or int(koniec) < time.time():
        return False
    return hmac.compare_digest(podpis, _podpis(int(koniec)))


def _zalogowany(request: Request) -> bool:
    return ciasteczko_ok(request.cookies.get(CIASTECZKO, ""))


def _wymagaj(request: Request) -> None:
    """Strażnik dla tras API. 401 zamiast przekierowania, bo tu woła nas JavaScript."""
    if not config.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Panel nie ma ustawionego hasła (ADMIN_PASSWORD).")
    if not _zalogowany(request):
        raise HTTPException(status_code=401, detail="Sesja wygasła. Zaloguj się ponownie.")


def _ip(request: Request) -> str:
    przekazane = request.headers.get("x-forwarded-for", "")
    return (przekazane.split(",")[0].strip() if przekazane
            else (request.client.host if request.client else "nieznany"))


def _zablokowany(ip: str) -> bool:
    proby = _nieudane[ip]
    teraz = time.time()
    while proby and teraz - proby[0] > BLOKADA_SEKUND:
        proby.popleft()
    return len(proby) >= PROBY_LOGOWANIA


# --- strony -----------------------------------------------------------------

def _plik(nazwa: str) -> FileResponse:
    sciezka = config.BASE_DIR / "app" / "static" / nazwa
    if not sciezka.exists():
        raise HTTPException(status_code=404, detail=f"Brak pliku {nazwa}.")
    return FileResponse(sciezka, media_type="text/html")


@router.get("/admin")
def panel(request: Request):
    """Ekran panelu. Bez ciasteczka odsyła na logowanie."""
    if not _zalogowany(request):
        return RedirectResponse("/admin/login", status_code=303)
    if not config.ADMIN_PASSWORD:
        return _blad_panelu("Panel nie ma ustawionego hasła. Dodaj `ADMIN_PASSWORD` do `.env`.")
    return _plik("admin.html")


def _blad_panelu(komunikat: str):
    return Response(
        "<!doctype html><html lang='pl'><head><meta charset='utf-8'><title>Panel</title></head>"
        "<body style=\"font:15px system-ui;padding:40px;max-width:520px\">"
        f"<h1 style='font-size:18px'>Panel niedostępny</h1><p>{komunikat}</p></body></html>",
        status_code=503, media_type="text/html; charset=utf-8")


@router.get("/admin/login")
def ekran_logowania(request: Request):
    if not config.ADMIN_PASSWORD:
        return _blad_panelu("Panel nie ma ustawionego hasła. Dodaj `ADMIN_PASSWORD` do `.env`.")
    if _zalogowany(request):
        return RedirectResponse("/admin", status_code=303)
    return _plik("admin-login.html")


@router.post("/admin/login")
async def logowanie(request: Request):
    """Logowanie hasłem z `.env`. Zwykły formularz, więc działa też bez JavaScriptu.

    Treść formularza (`application/x-www-form-urlencoded`) czytamy sami przez `parse_qs`,
    żeby nie dokładać zależności `python-multipart` do obrazu produkcyjnego.
    """
    if not config.ADMIN_PASSWORD:
        return _blad_panelu("Panel nie ma ustawionego hasła. Dodaj `ADMIN_PASSWORD` do `.env`.")
    ip = _ip(request)
    if _zablokowany(ip):
        return RedirectResponse("/admin/login?blad=blokada", status_code=303)

    cialo = (await request.body()).decode("utf-8", errors="replace")
    pola = parse_qs(cialo, keep_blank_values=True)
    haslo = (pola.get("haslo") or [""])[0]
    przekierowanie = (pola.get("przekierowanie") or ["/admin"])[0]

    if not hmac.compare_digest(haslo, config.ADMIN_PASSWORD):
        _nieudane[ip].append(time.time())
        return RedirectResponse("/admin/login?blad=haslo", status_code=303)

    _nieudane.pop(ip, None)
    cel = przekierowanie if przekierowanie.startswith("/admin") else "/admin"
    odpowiedz = RedirectResponse(cel, status_code=303)
    https = (request.url.scheme == "https"
             or request.headers.get("x-forwarded-proto", "") == "https")
    odpowiedz.set_cookie(CIASTECZKO, zrob_ciasteczko(), httponly=True, samesite="lax",
                         secure=https, max_age=SESJA_SEKUND, path="/")
    return odpowiedz


@router.get("/admin/logout")
def wylogowanie():
    odpowiedz = RedirectResponse("/admin/login", status_code=303)
    odpowiedz.delete_cookie(CIASTECZKO, path="/")
    return odpowiedz


# --- baza wiedzy ------------------------------------------------------------

@router.get("/api/admin/wiedza")
def wiedza(request: Request) -> dict:
    _wymagaj(request)
    wpisy = db.kb_entries_all(config.TENANT)
    return {"wpisy": wpisy, "aktywne": sum(1 for w in wpisy if w["active"])}


@router.post("/api/admin/wiedza")
async def dodaj_wpis(request: Request) -> dict:
    _wymagaj(request)
    dane = await request.json()
    sekcja = (dane.get("section") or "").strip()
    tresc = (dane.get("answer") or "").strip()
    if not sekcja or not tresc:
        raise HTTPException(status_code=422, detail="Wpis musi mieć sekcję i treść.")
    nowy_id = db.add_entry(config.TENANT, sekcja, tresc, bool(dane.get("active", True)))
    return {"id": nowy_id}


@router.post("/api/admin/wiedza/{wpis_id}")
async def zapisz_wpis(wpis_id: int, request: Request) -> dict:
    _wymagaj(request)
    dane = await request.json()
    sekcja, tresc = dane.get("section"), dane.get("answer")
    if sekcja is not None and not sekcja.strip():
        raise HTTPException(status_code=422, detail="Sekcja nie może być pusta.")
    if tresc is not None and not tresc.strip():
        raise HTTPException(status_code=422, detail="Treść wpisu nie może być pusta.")

    znane = {w["id"] for w in db.kb_entries_all(config.TENANT)}
    if wpis_id not in znane:
        raise HTTPException(status_code=404, detail="Nie ma takiego wpisu.")
    db.update_entry(wpis_id, section=sekcja.strip() if sekcja else None,
                    answer=tresc.strip() if tresc else None,
                    active=bool(dane["active"]) if "active" in dane else None)
    return {"ok": True}


@router.post("/api/admin/wiedza/{wpis_id}/usun")
def usun_wpis(wpis_id: int, request: Request) -> dict:
    _wymagaj(request)
    znane = {w["id"] for w in db.kb_entries_all(config.TENANT)}
    if wpis_id not in znane:
        raise HTTPException(status_code=404, detail="Nie ma takiego wpisu.")
    db.delete_entry(wpis_id)
    return {"ok": True}


@router.post("/api/admin/test")
async def pytanie_testowe(request: Request) -> dict:
    """Pytanie testowe: ta sama droga co u klienta, ale bez wpisu w dzienniku."""
    _wymagaj(request)
    dane = await request.json()
    pytanie = (dane.get("question") or "").strip()
    if not pytanie:
        raise HTTPException(status_code=422, detail="Wpisz pytanie.")
    if len(pytanie) > config.MAX_QUESTION_CHARS:
        raise HTTPException(status_code=422,
                            detail=f"Pytanie może mieć maksymalnie {config.MAX_QUESTION_CHARS} znaków.")
    if not config.OPENROUTER_API_KEY:
        raise HTTPException(status_code=503, detail="Brak klucza API na serwerze.")

    wynik = chat.ask(tenant=config.TENANT, question=pytanie, session_id="panel-test",
                     client_ip=_ip(request), origin="panel-test", zapis=False)
    wynik["kupka"], wynik["powod"] = luki.kupka(pytanie)
    return JSONResponse(wynik)


# --- luki w wiedzy ----------------------------------------------------------

def _luki(od: str | None, do: str | None) -> dict:
    pytania = db.luki_bez_odpowiedzi(config.TENANT, od, do)
    zestawienie = luki.zestawienie(pytania)
    zestawienie["liczba_pytan"] = len(pytania)
    return zestawienie


@router.get("/api/admin/luki")
def lista_luk(request: Request, od: str = "", do: str = "") -> dict:
    _wymagaj(request)
    return _luki(od, do)


# --- rozmowy ----------------------------------------------------------------

@router.get("/api/admin/rozmowy")
def lista_rozmow(request: Request, od: str = "", do: str = "", fraza: str = "",
                 limit: int = 300) -> dict:
    _wymagaj(request)
    wiersze = db.rozmowy(config.TENANT, od, do, fraza, min(max(limit, 1), 1000))
    return {"rozmowy": wiersze, "liczba": len(wiersze),
            "statystyki": db.statystyki_panelu(config.TENANT)}


@router.get("/api/admin/rozmowy/watek")
def watek(request: Request, sesja: str = "") -> dict:
    _wymagaj(request)
    if not sesja:
        raise HTTPException(status_code=422, detail="Podaj identyfikator sesji.")
    return {"sesja": sesja, "wiadomosci": db.watek_sesji(config.TENANT, sesja)}


# --- eksport CSV ------------------------------------------------------------
# Średnik i BOM, bo plik otwiera się najczęściej w polskim Excelu.

def _csv(nazwa: str, naglowki: list[str], wiersze: list[list]) -> Response:
    bufor = io.StringIO()
    pisarz = csv.writer(bufor, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    pisarz.writerow(naglowki)
    pisarz.writerows(wiersze)
    tresc = ("\ufeff" + bufor.getvalue()).encode("utf-8")
    return Response(tresc, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nazwa}"'})


@router.get("/api/admin/eksport/rozmowy.csv")
def eksport_rozmow(request: Request, od: str = "", do: str = "", fraza: str = "") -> Response:
    _wymagaj(request)
    wiersze = db.rozmowy(config.TENANT, od, do, fraza, 1000)
    tabela = [[w["created_at"], w["session_id"], w["question"], w["answer"],
               "tak" if w["answered"] else "nie", w["model"], w["latency_ms"],
               f"{w['cost_usd']:.6f}", w["client_ip"], w["origin"]] for w in wiersze]
    naglowki = ["data_utc", "sesja", "pytanie", "odpowiedz", "odpowiedz_z_bazy", "model",
                "czas_ms", "koszt_usd", "ip", "origin"]
    return _csv("rozmowy.csv", naglowki, tabela)


@router.get("/api/admin/eksport/luki.csv")
def eksport_luk(request: Request, od: str = "", do: str = "") -> Response:
    _wymagaj(request)
    zestawienie = _luki(od, do)
    tabela = []
    for grupa, dane in zestawienie["kupki"].items():
        for pozycja in dane["pozycje"]:
            tabela.append([grupa, dane["nazwa"], pozycja["powod"], pozycja["fraza"],
                           pozycja["ile"], pozycja["ostatnio"], pozycja["odpowiedz"]])
    naglowki = ["kupka", "nazwa_kupki", "powod", "pytanie", "ile_razy", "ostatnio", "odpowiedz_bota"]
    return _csv("luki-w-wiedzy.csv", naglowki, tabela)
