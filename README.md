# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

**Polskie i angielskie PDF-y oraz skany w jednym wywołaniu Pythona lub z wiersza poleceń.** CzytajPDF odczytuje dokument strona po stronie. Gdy pismo ma warstwę tekstową, a załącznik jest skanem (albo warstwa tekstowa jest uszkodzona i zawiera „krzaki”), dostajesz jeden wynik z informacją, skąd pochodzi tekst każdej strony. Opcjonalna korekta przywraca polskie znaki lub naprawia typowe błędy OCR po angielsku, zachowując oryginalny odczyt do porównania.

> **English summary:** Page-wise Python library and CLI (Apache-2.0) for hybrid Polish and English PDFs — reads embedded text from file paths, `bytes`, or `BinaryIO` via `pypdf`, automatically falls back to local OCR (`tesserocr` / `rapidocr`) on missing or garbled pages, and optionally repairs OCR spelling while preserving `source` and `raw_text`. Created on the basis of [odwolania2json](https://github.com/praha6248/odwolania2Json). See [README.en.md](README.en.md).

## Pakiety w repozytorium

Jedno repozytorium dostarcza wspólną bibliotekę bazową oraz dwie paczki językowe o prostszej konfiguracji domyślnej:

- **`czytajpdf`** — pełna biblioteka i CLI z parametrem `lang="pl"` (domyślnie) lub `lang="en"`
- **`readpdf-pl`** (`packages/readpdf-pl`) — paczka i CLI dla dokumentów polskich (domyślnie `lang="pl"`)
- **`readpdf-en`** (`packages/readpdf-en`) — paczka i CLI dla dokumentów angielskich (domyślnie `lang="en"`, bez zależności od `morfeusz2`)

## Pierwszy odczyt

Python 3.10+. Instalacja z PyPI z obsługą OCR i korekty:

```sh
# Polski i angielski (pełna instalacja)
python -m pip install 'czytajpdf[ocr,polish]'

# Tylko angielski (bez morfeusz2)
python -m pip install 'czytajpdf[ocr,english]'

# Lub bezpośrednio przez paczki językowe:
python -m pip install 'readpdf-pl[all]'
python -m pip install 'readpdf-en[all]'
```

### Wiersz poleceń (CLI)

```sh
czytajpdf pismo-z-zalacznikami.pdf --ocr --correct --json
cat skan.pdf | czytajpdf - --ocr --lang en
```

### Python (ścieżka, `bytes` lub strumień `BinaryIO`)

```python
from czytajpdf import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)

# Upload HTTP / S3 bez zapisu pliku tymczasowego:
with open("zalacznik.pdf", "rb") as f:
    z_bajtow = extract(f.read(), ocr=True, correct=True, lang="pl")
```

Do PDF-ów z warstwą tekstową wystarczy instalacja bez dodatków (`pip install czytajpdf`) i wywołanie `extract("pismo.pdf")`. Cały tekst jest dostępny jako `dokument.text`. Numeracja stron zaczyna się od 1. Z paczek językowych można korzystać przez `from readpdf_pl import extract` oraz `from readpdf_en import extract`.

## Przykład do RAG / LLM (z metadanymi pochodzenia)

```python
from czytajpdf import extract

doc = extract("akta-sprawy.pdf", ocr=True, correct=True)
chunks = [
    {
        "text": page.text,
        "metadata": {
            "page": page.number,
            "source": page.source,        # "pdf", "tesseract" lub "rapidocr"
            "raw_text": page.raw_text,    # oryginał sprzed korekty do audytu nazw własnych
        },
    }
    for page in doc.pages if page.text.strip()
]
```

## Przykład przed i po korekcie (na prawdziwych skanach)

- **Dz.U. 1945 nr 5 poz. 17** (strona mieszanego PDF-a): `ponadkontyugentowych` → `ponadkontyngentowych`
- **Dz.U. 1958 poz. 100** (ponowny odczyt 300/180 DPI): `KOZPORZĄDZENIE ... w sprawie skiadu` → `ROZPORZĄDZENIE ... w sprawie składu`
- **U.S. Reports — Brown v. Board of Education (1954)**: `Amendfnent` → `Amendment`; **Roe v. Wade (1973)**: `eriminal` → `criminal`
- **Uszkodzona warstwa tekstowa („krzaki”)**: strony ze znacznikami `(cid:...)`, znakami `\ufffd`, kontrolnymi/PUA lub bełkotem bez czytelnych słów są automatycznie kierowane do OCR nawet powyżej `min_chars`.

## Statystyki odczytu

| Dokument | Język | Strony | Strony z warstwy tekstowej | Strony z OCR | Znaki z OCR |
| --- | --- | ---: | ---: | ---: | ---: |
| [Dz.U. 2024 poz. 1](https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf) | `pl` | 8 | 8 | 0 | 0 |
| [Dz.U. 1945 nr 5 poz. 17](https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf) | `pl` | 2 | 2 | 0 | 0 |
| PDF mieszany z pierwszych stron obu polskich dokumentów | `pl` | 2 | 1 | 1 | 2716 |
| [SCOTUS No. 22-451](https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf) | `en` | 114 | 114 | 0 | 0 |
| [Brown v. Board of Education, 347 U.S. 483](https://cdn.loc.gov/service/ll/usrep/usrep347/usrep347483/usrep347483.pdf) | `en` | 14 | 14 | 0 | 0 |
| PDF mieszany z pierwszych stron obu angielskich dokumentów | `en` | 2 | 1 | 1 | 2204 |

## Skuteczność korekty polskiego OCR

Pomiar obejmuje nagłówki z 18 archiwalnych skanów Dziennika Ustaw. Na pierwotnej próbce 12 nagłówków **liczba błędów słów spadła z 79 do 2**. Do porównania użyto tych samych wycinków i transkrypcji.

| Próbka i wersja biblioteki | Błędy znaków (CER) po korekcie | Błędy słów (WER) po korekcie |
| --- | ---: | ---: |
| 12 pierwotnych nagłówków · 0.1.0, RapidOCR | 382 / 2129 · 17,94% | 79 / 293 · 26,96% |
| Te same 12 nagłówków · 0.2.0+, Tesseract | 2 / 2129 · 0,09% | 2 / 293 · 0,68% |
| 3 dodatkowe nagłówki użyte do sprawdzenia i poprawienia obsługi dzielenia słów · 0.2.0+ | 0 / 593 · 0,00% | 0 / 87 · 0,00% |
| 3 osobne nagłówki użyte do końcowej weryfikacji · 0.2.0+ | 1 / 430 · 0,23% | 1 / 67 · 1,49% |

Na pierwotnej próbce surowy Tesseract popełnił 5 błędów słów, a drugi odczyt z korektą usunął 3. Pozostały pomyłki `r.` → `r,` oraz `i` → `1`. W końcowej weryfikacji OCR dodał kropkę po słowie `lutego`.

CER i WER uwzględniają zamiany, wstawienia i pominięcia względem transkrypcji z obrazu. Ujednolicono białe znaki, zachowując interpunkcję i wielkość liter. Wynik dotyczy wycinków z drukowanymi nagłówkami. [Pomiar 0.1.0](benchmarks/rapidocr-0.1.0.json) · [Pomiar 0.2.0+](benchmarks/results.json) · [Próbka dodatkowa](benchmarks/holdout.json) · [Weryfikacja końcowa](benchmarks/validation.json) · [Skrypt pomiarowy](benchmarks/score.py)

## Skuteczność angielskiego OCR (`lang="en"`)

Pomiar obejmuje 9 archiwalnych skanów *United States Reports* z Library of Congress (lata 1937–1989). Na 6 dokumentach próbki głównej korekta naprawiła błędy `Amendfnent` → `Amendment` oraz `eriminal` → `criminal` (spadek WER z 17 do 15 na 897 słowach), a na 3 osobnych dokumentach walidacyjnych nie wprowadziła żadnych fałszywych poprawek.

| Próbka angielska (Tesseract `eng`) | Surowy CER / WER | Po korekcie CER | Po korekcie WER |
| --- | ---: | ---: | ---: |
| 6 skanów *U.S. Reports* (1937–1984) | 0,35% / 1,90% (17 / 897) | 17 / 5745 · 0,30% | 15 / 897 · 1,67% |
| 3 osobne skany walidacyjne (1943, 1964, 1989) | 0,32% / 1,99% (6 / 301) | 6 / 1871 · 0,32% | 6 / 301 · 1,99% |

[Pomiar angielski](benchmarks/english_results.json) · [Walidacja angielska](benchmarks/english_validation.json)

## Nowości w 0.5

### CLI wsadowe

```sh
czytajpdf akta/ --ocr --correct --workers 4 --preprocess -o wyniki/ --format md --progress
czytajpdf 'skany/**/*.pdf' --ocr --pages 1-5 --min-confidence 70 --skip-existing -o wyniki/
czytajpdf skan.pdf --ocr --searchable -o wyniki/      # wyniki/skan.searchable.pdf z warstwą tekstową
czytajpdf download-models --lang pl en --osd --dir ./tessdata
```

Argumentem może być plik, katalog (rekurencyjnie), wzorzec glob lub `-`. Błąd jednego pliku nie przerywa reszty (chyba że `--fail-fast`); kod wyjścia to `1`, gdy cokolwiek się nie udało. Bez `-o` kilka wejść trafia na stdout (`--json` daje JSON Lines). Formaty: `txt`, `json` (z `--words` także ramki słów), `md`.

### API

```python
from czytajpdf import extract, extract_iter, make_searchable, download_models

doc = extract("akta.pdf", ocr=True, correct="suggest", lang="auto", pages="1-20,25-",
              workers=4, preprocess=True, cache=True, password=None, backend="pdfium")
page = doc.pages[0]
page.confidence, page.lang, page.width, page.height      # średnia pewność OCR (0-100), język, rozmiar w pkt
page.words      # Word(text, bbox=(x0, y0, x1, y1) w pkt od lewego górnego rogu, confidence)
page.corrections  # Correction(raw, fixed, offset) - przy correct="suggest" text zostaje surowy
doc.low_confidence_pages(70)

for page in extract_iter("500-stron.pdf", ocr=True):      # strony na bieżąco, bez trzymania całości w pamięci
    ...

make_searchable("skan.pdf", "skan-ocr.pdf", lang="pl")    # niewidoczna warstwa tekstu na oryginalnych stronach
download_models(["pl", "en"], "./tessdata", include_osd=True)

chunks = doc.chunks(max_chars=1200, overlap=150)          # metadane: page, source, confidence, lang, corrected
docs = doc.to_langchain(max_chars=1200)                   # pip install 'czytajpdf[langchain]'
docs = doc.to_llamaindex()                                # pip install 'czytajpdf[llamaindex]'
```

- **Języki:** `lang="pl"`, `"en"`, `"pl+en"`, `"auto"` (polski+angielski, język wykrywany dla każdej strony) lub dowolny język Tesseract (`"de"`, `"fra"`, `"uk"`…; wbudowane sumy kontrolne: de, fr, es, it, cs, uk, ru, pt, nl, sk, la). Korekta pisowni działa dla `pl` i `en`; w tekstach mieszanych słowa poprawne w drugim języku są chronione.
- **Preprocessing:** `preprocess=True` prostuje obrót o 90/180/270° (OSD Tesseracta) i pochylenie skanu; można też wskazać `"rotate,deskew,denoise,binarize"`. Współrzędne `words` odnoszą się do obrazu po obróbce.
- **Wydajność:** `workers=N` uruchamia N procesów OCR (w skryptach wymagane `if __name__ == "__main__":`). `cache=True` (lub katalog) pomija ponowne OCR niezmienionych stron (klucz: zawartość PDF, strona i opcje).
- **Offline:** `czytajpdf download-models` pobiera i weryfikuje modele; potem `tessdata_dir=` / `CZYTAJPDF_TESSDATA` (katalog z `*.traineddata`, nigdy nie pobiera) albo `offline=True` / `CZYTAJPDF_OFFLINE=1`.
- **Backend tekstu:** `backend="pdfium"` (pypdfium2, Apache/BSD) bywa szybszy od `pypdf` i lepiej układa kolejność czytania. PyMuPDF celowo pominięto ze względu na licencję AGPL.
- **Błędy:** `CzytajPDFError` i podklasy (`InvalidPDFError`, `PasswordRequiredError`, `MissingDependencyError`, `ModelNotFoundError`) dziedziczą też po `ValueError`/`ImportError`/`OSError`. Szczegóły działania w logach (`logging.getLogger("czytajpdf")`, w CLI `-v`). PDF-y szyfrowane AES wymagają `czytajpdf[crypto]`.

### Test wytrzymałościowy (syntetyczne pełne strony)

CER po OCR Tesseract na wyrenderowanych stronach z typowymi wadami. [Skrypt](benchmarks/stress.py) · [wyniki](benchmarks/stress_results.json). Prawdziwe skany bywają trudniejsze: to test regresji i dowód działania preprocessingu, nie obietnica jakości.

| Przypadek | Język | Bez obróbki | `preprocess=True` | `rotate,deskew,denoise` |
| --- | --- | ---: | ---: | ---: |
| clean | `pl` | 0.36% | 0.36% | 0.36% |
| skew 2° | `pl` | 0.36% | 0.36% | 0.36% |
| skew 4° + blur | `pl` | 27.74% | 0.36% | 0.36% |
| rotated 90° | `pl` | 89.42% | 0.36% | 0.36% |
| upside down | `pl` | 89.78% | 0.36% | 0.36% |
| speckle noise | `pl` | 14.60% | 14.60% | 0.73% |
| low contrast | `pl` | 0.36% | 0.36% | 0.36% |
| clean | `en` | 0.00% | 0.00% | 0.00% |
| skew 3° + noise | `en` | 33.19% | 12.50% | 0.00% |

## Jak wybierany jest sposób odczytu

- Domyślnie działa pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków albo z uszkodzoną warstwą tekstową („krzakami”, np. znacznikami `(cid:...)`, znakami zastępczymi/PUA, niskim udziałem liter i cyfr, brakiem samogłosek lub niskim udziałem rozpoznawalnych słów przy dostępnym słowniku) trafiają do modelu Tesseract dla wybranego języka (`lang="pl"` albo `lang="en"`). Aby wybrać RapidOCR, przekaż `engine="rapidocr"`. Próg znaków zmienisz przez `min_chars`.
- `source` przyjmuje wartość `pdf`, `tesseract` lub `rapidocr`. Pusty wynik OCR pozostawia tekst z warstwy PDF. Wynik zachowuje podział na strony, bez współrzędnych słów ani struktury tabel.
- `correct=True` włącza korektę wyników OCR: dla `lang="pl"` używa `wordfreq` i `Morfeusza 2`, a dla `lang="en"` `wordfreq` i ostrożnych zamian typowych pomyłek OCR. Tesseract może ponownie odczytać stronę w rozdzielczości 180 DPI, aby zweryfikować nierozpoznane słowa. Pierwszy odczyt pozostaje dostępny w `raw_text`. Przy nazwiskach i nazwach własnych warto porównać wynik z `raw_text`.
- Rozpoznawanie odbywa się lokalnie. Przy pierwszym użyciu Tesseract pobiera odpowiedni model `tessdata_best` (około 12 MB dla `pol` lub 15 MB dla `eng`), sprawdza SHA-256 i zapisuje plik w pamięci podręcznej. Kolejne odczyty działają offline. RapidOCR korzysta z osobnych modeli.

## Licencja i pochodzenie

Kod biblioteki jest dostępny na [Apache-2.0](LICENSE). Biblioteka powstała na podstawie logiki ekstrakcji PDF, OCR i korekty pisowni stworzonej w projekcie [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach.
