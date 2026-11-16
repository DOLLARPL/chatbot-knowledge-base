# Szablon bazy wiedzy dla klienta

Ten plik to lista sekcji, które wypełnia się przy każdym wdrożeniu chatbota.
Kolejność ma znaczenie: pierwsze sekcje to pytania, o które klienci pytają najczęściej.
Wypełnienie zajmuje około 30 do 60 minut rozmowy z właścicielem firmy.

Celowo **nie ma tu marketingu**. Baza wiedzy dla bota to zestaw faktów, nie opis oferty.
Zdania typu „jesteśmy liderem na rynku" tylko zwiększają koszt i ryzyko zmyślenia.

---

## Zasady pisania wpisów

1. **Jeden temat na wpis.** „Godziny otwarcia" osobno, „godziny w święta" osobno.
2. **Konkret, nie ogólniki.** „od 250 zł", nie „w przystępnej cenie".
3. **Cena tylko jako „od".** Bot nigdy nie obiecuje ceny docelowej. Zawsze „od X zł"
   plus zdanie, że ostateczna cena po oględzinach.
4. **Pisz odpowiedź, nie pytanie.** Zamiast „godziny otwarcia?" napisz pełne zdanie,
   które bot może powtórzyć klientowi.
5. **Czego nie ma w bazie, tego bot nie wie.** Jeśli właściciel czegoś nie podaje (np. cen
   części), to znaczy, że bot ma tego nie podawać. To decyzja biznesowa, nie luka do załatania.
6. **Zaznacz tematy zakazane** w sekcji „Czego bot nie robi". To najczęściej ratuje reputację
   klienta przy pytaniach o bezpieczeństwo i porady techniczne.

---

## Sekcje do wypełnienia

### 1. Firma
Nazwa, czym się zajmuje w jednym zdaniu, od kiedy działa, czym się różni od innych (fakty, nie hasła).

### 2. Kontakt
Telefon, e-mail, adres, godziny odbierania telefonu, adres strony.

### 3. Godziny otwarcia
Dni powszednie, sobota, niedziela, święta (osobno, jeśli się różnią), przerwy.

### 4. Usługi
Lista usług z krótkim opisem. Dla każdej: co obejmuje i czy trzeba się umawiać.

### 5. Cennik
Pozycje z ceną „od". Pozycje, których ceny nie podajemy, też trzeba wypisać (żeby bot
wiedział, że ma odmówić, a nie zgadywać).

### 6. Realizacja i terminy
Jak szybko wykonywana jest typowa usługa, czy da się odebrać auto tego samego dnia,
czy trzeba zostawić auto, czy warsztat ściąga części.

### 7. Płatności i faktury
Gotówka, karta, przelew, faktura na firmę, zaliczki.

### 8. Dojazd i parking
Jak dojechać, parking, komunikacja miejska, czy jest auto zastępcze lub laweta.

### 9. Gwarancja, zwroty, reklamacje
Okres gwarancji, jak zgłaszać reklamację, w jakim terminie odpowiedź.

### 10. Czego bot nie robi
Stała sekcja, w każdym wdrożeniu wypełniona:
zakaz oceniania konkurencji, zakaz porad dotyczących bezpieczeństwa, zakaz wiążących cen
i terminów, zakaz obiecywania rabatów, zakaz rozmów poza tematem firmy.

### 11. Ton i forma odpowiedzi
Długość odpowiedzi (maksymalnie 2 do 3 zdania), forma (Pan/Pani lub na „ty"), język,
co robić przy braku wiedzy (zawsze podać telefon).

### 12. Pytania z rozmów
Sekcja rosnąca. Na start dziesięć pytań, które klienci zadają najczęściej, spisane
z pamięci właściciela. Potem dopisuje je panel, na podstawie listy pytań bez odpowiedzi.

---

## Przykład wypełnienia (fragment AutoExpert, firma fikcyjna)

```text
### 3. Godziny otwarcia
Poniedziałek-piątek: 8:00-17:00
Sobota: 9:00-13:00
Niedziela: zamknięte
Święta: zamknięte

### 5. Cennik (fragment)
Przegląd okresowy: od 250 zł
Wymiana oleju: od 180 zł
Diagnostyka komputerowa: 120 zł
Ceny części i robocizny przy złożonych naprawach podajemy po oględzinach pojazdu.
Nie podajemy cen wymiany rozrządu, sprzęgła i skrzyni biegów przez czat.

### 10. Czego bot nie robi
Nie ocenia innych warsztatów.
Nie udziela porad dotyczących bezpieczeństwa jazdy, tylko prosi o kontakt telefoniczny.
Nie podaje cen, których nie ma w sekcji 5.
Nie obiecuje rabatów ani skrócenia terminu.
```
