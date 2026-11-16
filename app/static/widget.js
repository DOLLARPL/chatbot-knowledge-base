/*! Widget czatu z bazą wiedzy — jnxautomation.pl (etap 2, v0.1)
 *
 *  Jeden plik, zero zależności. Wklejka u klienta:
 *
 *  <script src="https://chat.jnxautomation.pl/widget.js"
 *          data-tenant="demo" data-title="AutoExpert" data-color="#FF6B00"
 *          data-welcome="Cześć, w czym mogę pomóc?" defer></script>
 *
 *  Atrybuty: data-tenant, data-title, data-color, data-welcome.
 *  W kodzie nie ma klucza API ani adresów wewnętrznych: adres API bierze się
 *  z adresu tego pliku (widget i API to jedna subdomena).
 */
(function () {
  "use strict";

  if (window.__jnxWidgetWczytany) return;
  window.__jnxWidgetWczytany = true;

  var skrypt = document.currentScript;
  if (!skrypt) {
    var lista = document.querySelectorAll('script[src*="widget.js"]');
    skrypt = lista.length ? lista[lista.length - 1] : null;
  }

  function atrybut(nazwa, domyslna) {
    if (!skrypt) return domyslna;
    var v = skrypt.getAttribute("data-" + nazwa);
    return (v === null || v.trim() === "") ? domyslna : v.trim();
  }

  var TENANT = atrybut("tenant", "demo");
  var TYTUL = atrybut("title", "Czat");
  var POWITANIE = atrybut("welcome", "Cześć, w czym mogę pomóc?");
  var MAKS_ZNAKOW = 500;

  // Kolor z atrybutu przepuszczamy tylko w bezpiecznej postaci (bez wstrzyknięcia w CSS).
  var KOLOR = atrybut("color", "#FF6B00");
  if (!/^#[0-9a-fA-F]{3,8}$/.test(KOLOR)) KOLOR = "#FF6B00";

  // Adres API = źródło tego pliku. Jedna subdomena, żaden adres wewnętrzny w kodzie.
  var API = "https://chat.jnxautomation.pl/api/chat";
  try {
    if (skrypt && skrypt.src) API = new URL(skrypt.src, location.href).origin + "/api/chat";
  } catch (blad) { /* zostaje adres domyślny */ }

  // Identyfikator sesji w localStorage: wątek przeżywa odświeżenie strony.
  var KLUCZ_SESJI = "jnx-chat-sesja-" + TENANT;
  function idSesji() {
    var v = null;
    try { v = localStorage.getItem(KLUCZ_SESJI); } catch (blad) { v = null; }
    if (!v) {
      v = "w-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
      try { localStorage.setItem(KLUCZ_SESJI, v); } catch (blad) { /* tryb prywatny */ }
    }
    return v;
  }
  var SESJA = idSesji();

  // Kolor tekstu na kolorze marki: czytelny niezależnie od tego, co wybierze klient.
  // Liczymy prawdziwą jasność względną (WCAG) i wybieramy tekst o lepszym kontraście.
  function atrament(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(hex);
    if (!m) return "#FFFFFF";
    var n = parseInt(m[1], 16);
    function lin(v) { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    var L = 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
    // Punkt równego kontrastu czerni i bieli wypada przy jasności 0,179.
    return L > 0.179 ? "#14100C" : "#FFFFFF";
  }

  var CSS = [
    ":host { all: initial; }",
    "*, *::before, *::after { box-sizing: border-box; }",
    ".launcher { position: fixed; right: 20px; bottom: 20px; width: 56px; height: 56px;",
    "  border: 0; border-radius: 50%; background: var(--jnx); color: var(--ink); padding: 0;",
    "  cursor: pointer; pointer-events: auto; display: flex; align-items: center; justify-content: center;",
    "  box-shadow: 0 8px 24px rgba(0,0,0,.28); transition: transform .15s ease; }",
    ".launcher:hover { transform: scale(1.05); }",
    ".launcher:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }",
    ".panel { position: fixed; right: 20px; bottom: 92px; width: 380px;",
    "  height: min(560px, calc(100vh - 130px)); display: flex; flex-direction: column;",
    "  overflow: hidden; background: #121214; color: #EDEDED; border: 1px solid #2A2A2E;",
    "  border-radius: 16px; box-shadow: 0 24px 60px rgba(0,0,0,.45); pointer-events: auto;",
    "  font: 15px/1.5 system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif; }",
    ".panel[hidden] { display: none; }",
    ".head { display: flex; align-items: center; justify-content: space-between; gap: 8px;",
    "  padding: 12px 14px; background: #17171A; border-bottom: 1px solid #26262A; }",
    ".row { display: flex; align-items: center; gap: 9px; min-width: 0; }",
    ".head b { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden;",
    "  text-overflow: ellipsis; }",
    ".dot { width: 9px; height: 9px; border-radius: 50%; background: var(--jnx); flex: none; }",
    ".close { border: 0; background: transparent; color: #9A9AA2; cursor: pointer;",
    "  padding: 6px; border-radius: 8px; line-height: 0; }",
    ".close:hover { background: #232327; color: #EDEDED; }",
    ".thread { flex: 1; overflow-y: auto; padding: 14px; display: flex;",
    "  flex-direction: column; gap: 10px; }",
    ".bub { max-width: 84%; padding: 9px 12px; border-radius: 14px; font-size: 14.5px;",
    "  white-space: pre-wrap; overflow-wrap: anywhere; }",
    ".bub.bot { align-self: flex-start; background: #1E1E23; border: 1px solid #2C2C33;",
    "  border-bottom-left-radius: 5px; }",
    ".bub.klient { align-self: flex-end; background: var(--jnx); color: var(--ink);",
    "  border-bottom-right-radius: 5px; }",
    ".bub.blad { align-self: flex-start; background: #2A1F1F; border: 1px solid #4A2A2A;",
    "  color: #FFC9C9; }",
    ".ponow { margin-top: 8px; border: 1px solid #4A2A2A; background: #3A2424; color: #FFD9D9;",
    "  border-radius: 9px; padding: 6px 10px; font: inherit; font-size: 13px; cursor: pointer; }",
    ".typ { align-self: flex-start; display: flex; gap: 5px; padding: 13px; background: #1E1E23;",
    "  border: 1px solid #2C2C33; border-radius: 14px; border-bottom-left-radius: 5px; }",
    ".typ i { width: 6px; height: 6px; border-radius: 50%; background: #8A8A94;",
    "  animation: jnxskok 1.2s infinite; }",
    ".typ i:nth-child(2) { animation-delay: .15s; }",
    ".typ i:nth-child(3) { animation-delay: .3s; }",
    "@keyframes jnxskok { 0%, 60%, 100% { transform: translateY(0); opacity: .5; }",
    "  30% { transform: translateY(-4px); opacity: 1; } }",
    ".send { display: flex; gap: 8px; padding: 10px 12px calc(10px + env(safe-area-inset-bottom));",
    "  background: #17171A; border-top: 1px solid #26262A; }",
    ".send input { flex: 1; min-width: 0; padding: 11px 13px; border-radius: 11px;",
    "  border: 1px solid #303038; background: #0E0E10; color: #EDEDED; font: inherit;",
    "  font-size: 16px; }",
    ".send input::placeholder { color: #6E6E78; }",
    ".send input:focus { outline: 2px solid var(--jnx); outline-offset: 1px; }",
    ".send button { border: 0; border-radius: 11px; background: var(--jnx); color: var(--ink);",
    "  padding: 0 14px; cursor: pointer; display: flex; align-items: center; }",
    ".send button:disabled { opacity: .5; cursor: default; }",
    ".stopka { padding: 0 12px 10px; background: #17171A; color: #63636D; font-size: 11px;",
    "  text-align: center; }",
    "@media (max-width: 479.98px) {",
    "  .panel { left: 0; right: 0; top: 0; bottom: 0; width: auto; height: auto;",
    "    border: 0; border-radius: 0; }",
    "  .launcher { right: 16px; bottom: calc(16px + env(safe-area-inset-bottom)); }",
    "  .bub { max-width: 88%; }",
    "}",
    "@media (prefers-reduced-motion: reduce) { .typ i { animation: none; } }"
  ].join("\n");

  var HTML = [
    '<button class="launcher" type="button" aria-label="Otwórz czat" aria-expanded="false">',
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"',
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
    '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9.9 9.9 0 0 1-2.8-.4L4 21l1.4-4.2A8.3 8.3 0 0 1',
    ' 3 11.5 8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5z"/></svg></button>',
    '<section class="panel" role="dialog" aria-label="Czat" hidden>',
    '<div class="head"><span class="row"><span class="dot"></span><b class="ttl"></b></span>',
    '<button class="close" type="button" aria-label="Zamknij czat" title="Zamknij (Esc)">',
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"',
    ' stroke-width="2" stroke-linecap="round" aria-hidden="true">',
    '<path d="M18 6 6 18M6 6l12 12"/></svg></button></div>',
    '<div class="thread" role="log" aria-live="polite"></div>',
    '<form class="send">',
    '<input class="q" type="text" autocomplete="off" aria-label="Pytanie"',
    ' placeholder="Napisz pytanie...">',
    '<button class="go" type="submit" aria-label="Wyślij pytanie">',
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"',
    ' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">',
    '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button></form>',
    '<div class="stopka">Rozmowa jest zapisywana, żeby poprawiać jakość odpowiedzi.</div>',
    '</section>'
  ].join("\n");

  var host = document.createElement("div");
  host.setAttribute("data-jnx-widget", TENANT);
  host.style.cssText = "position:fixed;inset:0;z-index:2147483000;pointer-events:none;";

  function start() {
    (document.body || document.documentElement).appendChild(host);
    var cien = host.attachShadow({ mode: "open" });
    cien.innerHTML = "<style>\n:host { --jnx: " + KOLOR + "; --ink: " + atrament(KOLOR) +
      "; }\n" + CSS + "\n</style>\n" + HTML;

    var przycisk = cien.querySelector(".launcher");
    var panel = cien.querySelector(".panel");
    var watek = cien.querySelector(".thread");
    var pole = cien.querySelector(".q");
    var wyslij = cien.querySelector(".go");
    cien.querySelector(".ttl").textContent = TYTUL;
    pole.setAttribute("maxlength", String(MAKS_ZNAKOW));

    var otwarty = false;
    var ostatniePytanie = "";
    var powitaniePoszlo = false;

    function naDol() { watek.scrollTop = watek.scrollHeight; }

    function dymek(tekst, klasa) {
      var b = document.createElement("div");
      b.className = "bub " + klasa;
      b.textContent = tekst;          // textContent, nie innerHTML: treść od modelu nie wstrzykuje kodu
      watek.appendChild(b);
      naDol();
      return b;
    }

    function wskaznikPisania() {
      var el = document.createElement("div");
      el.className = "typ";
      el.setAttribute("aria-label", "Bot pisze");
      el.innerHTML = "<i></i><i></i><i></i>";
      watek.appendChild(el);
      naDol();
      return el;
    }

    function komunikatBledu(tekst) {
      var b = dymek(tekst, "blad");
      var p = document.createElement("button");
      p.type = "button";
      p.className = "ponow";
      p.textContent = "Spróbuj ponownie";
      p.addEventListener("click", function () {
        b.remove();
        if (ostatniePytanie) zapytaj(ostatniePytanie);
      });
      b.appendChild(p);
      return b;
    }

    function zapytaj(tekst) {
      ostatniePytanie = tekst;
      var pisze = wskaznikPisania();
      wyslij.disabled = true;
      fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: tekst,
          session_id: SESJA,
          tenant: TENANT,              // backend jeszcze tego pola nie używa (jedna baza), trafi w etapie 3
          page_url: location.href.slice(0, 300)
        })
      })
        .then(function (odp) {
          return odp.json().catch(function () { return {}; }).then(function (dane) {
            return { ok: odp.ok, status: odp.status, dane: dane };
          });
        })
        .then(function (w) {
          pisze.remove();
          if (!w.ok) {
            komunikatBledu((w.dane && w.dane.detail) || ("Błąd " + w.status + ". Spróbuj ponownie za chwilę."));
          } else {
            dymek(w.dane.answer || "Nie mam tej informacji.", "bot");
          }
        })
        .catch(function () {
          pisze.remove();
          komunikatBledu("Nie udało się połączyć. Spróbuj ponownie.");
        })
        .then(function () {
          wyslij.disabled = false;
          if (otwarty) pole.focus();
        });
    }

    function otworz() {
      if (otwarty) return;
      otwarty = true;
      panel.hidden = false;
      przycisk.setAttribute("aria-expanded", "true");
      if (!powitaniePoszlo) { powitaniePoszlo = true; dymek(POWITANIE, "bot"); }
      document.addEventListener("keydown", naEsc);
      setTimeout(function () { pole.focus(); }, 60);
    }

    function zamknijCzat() {
      if (!otwarty) return;
      otwarty = false;
      panel.hidden = true;
      przycisk.setAttribute("aria-expanded", "false");
      document.removeEventListener("keydown", naEsc);
      przycisk.focus();
    }

    function naEsc(e) {
      if (e.key === "Escape") { e.stopPropagation(); zamknijCzat(); }
    }

    przycisk.addEventListener("click", function () { otwarty ? zamknijCzat() : otworz(); });
    cien.querySelector(".close").addEventListener("click", zamknijCzat);

    cien.querySelector(".send").addEventListener("submit", function (e) {
      e.preventDefault();
      var t = pole.value.trim();
      if (!t || wyslij.disabled) return;
      dymek(t, "klient");
      pole.value = "";
      zapytaj(t);
    });
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
