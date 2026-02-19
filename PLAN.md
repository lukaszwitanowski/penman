# Plan: Pobieranie i transkrypcja audio z YouTube

## Kontekst

Aplikacja **Penman** to desktopowe narzędzie GUI (tkinter) do transkrypcji plików audio/wideo za pomocą modelu Whisper. Obecnie obsługuje wyłącznie pliki lokalne. Paczka `yt-dlp` jest już w `requirements.txt`, ale nie jest wykorzystywana w kodzie.

Celem jest dodanie możliwości wklejenia URL-a YouTube, pobrania z niego audio i automatycznej transkrypcji — bez zmiany istniejącego flow dla plików lokalnych.

---

## Architektura zmian

```
[GUI: pole URL]  -->  [youtube_service.py: download_audio()]  -->  plik .wav/mp3 w temp  -->  [istniejący run_transcription()]
```

Nowy moduł `youtube_service.py` enkapsuluje całą logikę pobierania. GUI otrzymuje nową sekcję do wklejania URL-a. Worker thread obsługuje pobranie przed przekazaniem do `run_transcription()`.

---

## Krok 1: Nowy moduł `youtube_service.py`

Utworzyć plik `youtube_service.py` z następującymi funkcjami:

### `is_youtube_url(url: str) -> bool`
- Walidacja URL-a — sprawdzenie czy to domena YouTube/youtu.be.
- Regex na wzorce: `youtube.com/watch?v=`, `youtu.be/`, `youtube.com/shorts/`, `youtube.com/live/`.

### `fetch_video_info(url: str) -> dict`
- Pobranie metadanych bez ściągania pliku (tytuł, czas trwania, miniatura).
- Użycie `yt_dlp.YoutubeDL` z opcją `extract_flat` / `skip_download=True`.
- Zwraca dict: `{"title": str, "duration_seconds": int, "url": str}`.

### `download_audio(url: str, output_dir: Path, progress_callback, cancel_event) -> Path`
- Pobranie audio z YouTube w formacie najlepszej jakości audio.
- Opcje yt-dlp:
  - `format`: `bestaudio/best`
  - `postprocessors`: konwersja do WAV (16kHz, mono) przez ffmpeg — lub bezpośrednio do formatu obsługiwanego przez Whisper.
  - `outtmpl`: `output_dir / "{title}_{id}.%(ext)s"`
- Progress hook yt-dlp → `progress_callback` (mapowanie procentów).
- Sprawdzanie `cancel_event` w hooku progressu.
- Sanityzacja nazwy pliku (usunięcie znaków specjalnych).
- Zwraca ścieżkę do pobranego pliku audio.
- Obsługa błędów: `yt_dlp.DownloadError` → `TranscriptionError` z czytelnym komunikatem.

---

## Krok 2: Zmiany w `config.py`

Dodać stałe:

```python
DEFAULT_YT_DOWNLOAD_DIR = Path("yt_downloads")

YOUTUBE_URL_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=",
    r"(?:https?://)?youtu\.be/",
    r"(?:https?://)?(?:www\.)?youtube\.com/shorts/",
    r"(?:https?://)?(?:www\.)?youtube\.com/live/",
]
```

---

## Krok 3: Zmiany w GUI (`gui.py`)

### 3a. Nowa sekcja UI — pole URL YouTube

Dodać **nad** istniejącym polem "Input file" (lub jako osobną ramkę/separator) sekcję:

| Element | Typ | Opis |
|---------|-----|------|
| Label "YouTube URL" | `ttk.Label` | Etykieta |
| Pole tekstowe URL | `ttk.Entry` + `StringVar` (`yt_url_var`) | Wklejanie URL-a |
| Przycisk "Fetch info" | `ttk.Button` | Pobiera metadane i wyświetla tytuł/czas trwania |
| Label info | `ttk.Label` | Wyświetla tytuł i czas trwania wideo |
| Przycisk "Add YT to queue" | `ttk.Button` | Dodaje URL do kolejki |

### 3b. Rozszerzenie kolejki o elementy YouTube

- `file_queue` zmienia typ na `list[dict]` lub równoległa lista `yt_queue: list[str]` dla URL-i.
- **Proponowane podejście**: Zachować `file_queue: list[str]` ale oznaczyć URL-e YouTube prefiksem `yt://` lub osobnym typem.
  - Alternatywnie: `list[str]` gdzie elementy zaczynające się od `https://` / `http://` to URL-e YouTube.
- W `queue_listbox` URL-e YouTube wyświetlane z prefixem `[YT]`.

### 3c. Logika wzajemnego wykluczania

- Gdy użytkownik wklei URL YouTube i kliknie "Add YT to queue", URL jest walidowany (`is_youtube_url`), pobierane info (`fetch_video_info`) i dodawany do kolejki.
- Pole "Input file" i "YouTube URL" działają niezależnie — oba mogą dodawać do tej samej kolejki.

### 3d. Przesunięcie wierszy UI

Istniejące elementy przesuną się o ~2 wiersze w dół. Aktualizacja `row=` w `_build_ui()`.

---

## Krok 4: Zmiany w workerze (`gui.py` → `_run_worker`)

Przed wywołaniem `run_transcription()` dla każdego elementu kolejki:

```python
for index, item in enumerate(input_files, start=1):
    if _is_youtube_item(item):
        # 1. Pobierz audio z YouTube
        local_path = download_audio(
            url=item,
            output_dir=yt_download_dir,
            progress_callback=...,
            cancel_event=self.cancel_event,
        )
        input_file = str(local_path)
        # 2. Ustaw input_format na "auto"
    else:
        input_file = item

    # 3. Istniejące wywołanie run_transcription()
    output_path = run_transcription(input_path=input_file, ...)
```

- Katalog pobierania: `output_dir / "yt_downloads"` (tymczasowy, czyszczony po transkrypcji).
- Progress: Faza pobierania = 0-30%, faza transkrypcji = 30-100% (przeskalowanie).

---

## Krok 5: Sprzątanie plików tymczasowych

- Po zakończeniu transkrypcji elementu YouTube, usunąć pobrany plik audio (chyba że użytkownik włączy opcję "Zachowaj pobrane pliki").
- Opcjonalnie: checkbox w UI "Keep downloaded files" (domyślnie OFF).

---

## Krok 6: Obsługa błędów

Nowe scenariusze błędów do obsłużenia:

| Błąd | Obsługa |
|------|---------|
| Nieprawidłowy URL YouTube | Walidacja w GUI przed dodaniem do kolejki |
| Wideo niedostępne / prywatne / usunięte | `yt_dlp.DownloadError` → komunikat w logu + przejście do następnego elementu kolejki |
| Brak internetu | Timeout + komunikat |
| Wideo zbyt długie (>4h) | Ostrzeżenie w logu (nie blokuje) |
| Wideo tylko z obrazem (bez audio) | Komunikat o braku ścieżki audio |

---

## Krok 7: Metadane YouTube w wyniku transkrypcji

Rozszerzyć `payload["metadata"]` o pola YouTube (gdy źródłem jest URL):

```python
"youtube": {
    "url": "https://...",
    "title": "Tytuł wideo",
    "duration_seconds": 1234,
}
```

Wymaga drobnej zmiany w `transcription_service.py` — dodanie opcjonalnego parametru `extra_metadata: dict | None` do `run_transcription()`.

---

## Podsumowanie plików do zmiany

| Plik | Typ zmiany |
|------|-----------|
| `youtube_service.py` | **NOWY** — logika pobierania z YouTube |
| `config.py` | Dodanie stałych YT |
| `gui.py` | Nowa sekcja UI + rozszerzenie workera |
| `transcription_service.py` | Dodanie `extra_metadata` do payloadu |
| `exporters.py` | Opcjonalnie: renderowanie metadanych YT w MD/JSON |
| `requirements.txt` | Bez zmian (`yt-dlp` już jest) |

---

## Kolejność implementacji

1. `youtube_service.py` — nowy moduł (samodzielny, testowalny niezależnie)
2. `config.py` — stałe
3. `transcription_service.py` — `extra_metadata`
4. `exporters.py` — renderowanie metadanych YT
5. `gui.py` — UI + integracja workera
6. Testy manualne end-to-end
