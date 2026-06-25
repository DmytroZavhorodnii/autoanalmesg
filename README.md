# Mail@AI — Power Platform Message Center

Aplikacja desktopowa (Windows) do automatycznej analizy i klasyfikacji wiadomości
Microsoft Power Platform Message Center — z e-maila (IMAP/POP3) albo z eksportu
Excela — przy pomocy lokalnego modelu AI (Ollama, model `gemma3`).

Wynik klasyfikacji (typ, priorytet, serwis, wymagana akcja, status) jest
prezentowany na żywo w przeglądarce, z postępem przesyłanym przez WebSocket.

## Funkcje

- **Klasyfikacja AI** — każda wiadomość jest oceniana przez lokalny model Ollama
  (`app/app/classifier.py`), bez wysyłania danych poza komputer użytkownika.
- **Dwa źródła danych**:
  - import pliku Excel z komunikatami (`app/app/excel_loader.py`),
  - monitor skrzynki e-mail przez IMAP lub POP3, w czasie rzeczywistym
    (`app/app/email_reader.py`).
- **Cache wyników** po hashu treści, żeby nie analizować tej samej wiadomości
  dwa razy (`app/app/cache.py`).
- **Checkpointy** — przerwaną analizę można bezpiecznie wznowić
  (`app/app/checkpoint.py`).
- **Uczenie się na korektach administratora** (lekki mechanizm few-shot /
  in-context learning na bazie poprawek) — `app/app/feedback.py`.
- **Panel webowy** (`app/app/static/`) serwowany przez FastAPI/Uvicorn,
  otwierany automatycznie w domyślnej przeglądarce.
- **Instalator Windows** (`app/installer/`) — sprawdza/instaluje Python i
  Ollama, konfiguruje Defender i zaporę, tworzy skrót na pulpicie.

## Wymagania

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com) z modelem `gemma3` (pobierany automatycznie
  przy pierwszym uruchomieniu)

Zależności Python — patrz [app/requirements.txt](app/requirements.txt)
(FastAPI, Uvicorn, pandas, openpyxl, requests).

## Instalacja

Najprościej uruchomić instalator:

```
app/installer/Setup.bat
```

który wywołuje `install.ps1` — wykrywa/instaluje Pythona i Ollamę, instaluje
zależności z `requirements.txt`, konfiguruje wyjątki Defendera i regułę
zapory dla portu aplikacji, generuje `launch.vbs` i tworzy skrót na pulpicie.

## Uruchamianie ręczne

```
cd app
pip install -r requirements.txt
python main.py
```

Aplikacja wystartuje na `http://127.0.0.1:8765` i otworzy się w przeglądarce.

## Struktura repozytorium

```
app/
├── main.py                 punkt wejścia (uruchamia serwer)
├── requirements.txt
├── launch.vbs               launcher używany przez skrót na pulpicie
├── installer/                skrypty instalacyjne Windows
│   ├── Setup.bat
│   ├── run_setup.bat
│   ├── install.ps1
│   └── check_env.ps1
└── app/                      kod aplikacji
    ├── main.py                start FastAPI + otwarcie przeglądarki
    ├── server.py              endpointy REST/WebSocket, logika UI
    ├── classifier.py          wywołania modelu Ollama, logika klasyfikacji
    ├── config.py              stałe konfiguracyjne
    ├── email_reader.py        monitor IMAP/POP3
    ├── excel_loader.py        wczytywanie/filtrowanie pliku Excel
    ├── cache.py               cache wyników klasyfikacji
    ├── checkpoint.py          zapisywanie postępu / wznawianie
    ├── feedback.py            magazyn korekt administratora
    ├── rules.py               reguły/wzorce pomocnicze przy klasyfikacji
    └── static/                frontend (HTML/CSS/JS)
```

## Pochodzenie tego repozytorium

Repozytorium zostało zrekonstruowane z dystrybucyjnego instalatora `MailAI-Setup.exe`
(Inno Setup 6.7.0), w którym aplikacja była spakowana jako czyste pliki
źródłowe Pythona (nie skompilowane) — dzięki czemu kod jest identyczny
z oryginałem.

## Autor

**dimon.work**

## Licencja

Ten projekt jest udostępniony na tej samej licencji open source, na jakiej
jest udostępniane jądro Linux: **GNU General Public License v2.0 (GPL-2.0)**.
Pełny tekst licencji znajduje się w pliku [LICENSE](LICENSE).
