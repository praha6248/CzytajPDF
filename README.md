# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

**Polskie i angielskie PDF-y oraz skany w jednym wywołaniu Pythona.** CzytajPDF odczytuje dokument strona po stronie. Gdy pismo ma warstwę tekstową, a załącznik jest skanem, dostajesz jeden wynik z informacją, skąd pochodzi tekst każdej strony. Opcjonalna korekta przywraca polskie znaki lub naprawia typowe błędy OCR po angielsku, zachowując oryginalny odczyt do porównania.

> **English summary:** Page-wise Python library (Apache-2.0) for hybrid Polish and English PDFs — reads embedded text via `pypdf`, automatically falls back to local OCR (`tesserocr` / `rapidocr`) on scanned pages, and optionally applies Polish (`morfeusz2` + `wordfreq`) or English (`wordfreq`) OCR repair with dual-resolution reconciliation while preserving `source` and `raw_text`. Also packaged as `readpdf-pl` and `readpdf-en` from the same repository. See [README.en.md](README.en.md).

## Pakiety w repozytorium

Jedno repozytorium dostarcza wspólną bibliotekę bazową oraz dwie paczki językowe o prostszej konfiguracji domyślnej:

- **`czytajpdf`** — pełna biblioteka z parametrem `lang="pl"` (domyślnie) lub `lang="en"`
- **`readpdf-pl`** (`packages/readpdf-pl`) — paczka dla dokumentów polskich (domyślnie `lang="pl"`)
- **`readpdf-en`** (`packages/readpdf-en`) — paczka dla dokumentów angielskich (domyślnie `lang="en"`, bez zależności od `morfeusz2`)

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

```python
from czytajpdf import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)

english_doc = extract("filing-with-exhibits.pdf", ocr=True, correct=True, lang="en")
```

Do PDF-ów z warstwą tekstową wystarczy instalacja bez dodatków i wywołanie `extract("pismo.pdf")`. Cały tekst jest dostępny jako `dokument.text`. Numeracja stron zaczyna się od 1. Z paczek językowych można korzystać przez `from readpdf_pl import extract` oraz `from readpdf_en import extract`.

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
| Te same 12 nagłówków · 0.2.0 / 0.3.0, Tesseract | 2 / 2129 · 0,09% | 2 / 293 · 0,68% |
| 3 dodatkowe nagłówki użyte do sprawdzenia i poprawienia obsługi dzielenia słów · 0.2.0 / 0.3.0 | 0 / 593 · 0,00% | 0 / 87 · 0,00% |
| 3 osobne nagłówki użyte do końcowej weryfikacji · 0.2.0 / 0.3.0 | 1 / 430 · 0,23% | 1 / 67 · 1,49% |

Na pierwotnej próbce surowy Tesseract popełnił 5 błędów słów, a drugi odczyt z korektą usunął 3. Pozostały pomyłki `r.` → `r,` oraz `i` → `1`. W końcowej weryfikacji OCR dodał kropkę po słowie `lutego`.

CER i WER uwzględniają zamiany, wstawienia i pominięcia względem transkrypcji z obrazu. Ujednolicono białe znaki, zachowując interpunkcję i wielkość liter. Wynik dotyczy wycinków z drukowanymi nagłówkami. [Pomiar 0.1.0](benchmarks/rapidocr-0.1.0.json) · [Pomiar 0.2.0/0.3.0](benchmarks/results.json) · [Próbka dodatkowa](benchmarks/holdout.json) · [Weryfikacja końcowa](benchmarks/validation.json) · [Skrypt pomiarowy](benchmarks/score.py)

## Skuteczność angielskiego OCR (`lang="en"`)

Pomiar obejmuje 9 archiwalnych skanów *United States Reports* z Library of Congress (lata 1937–1989). Na 6 dokumentach próbki głównej korekta naprawiła błędy `Amendfnent` → `Amendment` oraz `eriminal` → `criminal` (spadek WER z 17 do 15 na 897 słowach), a na 3 osobnych dokumentach walidacyjnych nie wprowadziła żadnych fałszywych poprawek.

| Próbka angielska (0.3.0, Tesseract `eng`) | Surowy CER / WER | Po korekcie CER | Po korekcie WER |
| --- | ---: | ---: | ---: |
| 6 skanów *U.S. Reports* (1937–1984) | 0,35% / 1,90% (17 / 897) | 17 / 5745 · 0,30% | 15 / 897 · 1,67% |
| 3 osobne skany walidacyjne (1943, 1964, 1989) | 0,32% / 1,99% (6 / 301) | 6 / 1871 · 0,32% | 6 / 301 · 1,99% |

[Pomiar angielski](benchmarks/english_results.json) · [Walidacja angielska](benchmarks/english_validation.json)

## Jak wybierany jest sposób odczytu

- Domyślnie działa pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków trafiają do modelu Tesseract dla wybranego języka (`lang="pl"` albo `lang="en"`). Aby wybrać RapidOCR, przekaż `engine="rapidocr"`. Próg zmienisz przez `min_chars`. Długa, uszkodzona warstwa tekstowa może przejść ten próg.
- `source` przyjmuje wartość `pdf`, `tesseract` lub `rapidocr`. Pusty wynik OCR pozostawia tekst z warstwy PDF. Wynik zachowuje podział na strony, bez współrzędnych słów ani struktury tabel.
- `correct=True` włącza korektę wyników OCR: dla `lang="pl"` używa `wordfreq` i `Morfeusza 2`, a dla `lang="en"` `wordfreq` i ostrożnych zamian typowych pomyłek OCR. Tesseract może ponownie odczytać stronę w rozdzielczości 180 DPI, aby zweryfikować nierozpoznane słowa. Pierwszy odczyt pozostaje dostępny w `raw_text`. Przy nazwiskach i nazwach własnych warto porównać wynik z `raw_text`.
- Rozpoznawanie odbywa się lokalnie. Przy pierwszym użyciu Tesseract pobiera odpowiedni model `tessdata_best` (około 12 MB dla `pol` lub 15 MB dla `eng`), sprawdza SHA-256 i zapisuje plik w pamięci podręcznej. Kolejne odczyty działają offline. RapidOCR korzysta z osobnych modeli.

## Licencja i pochodzenie

Kod biblioteki jest dostępny na [Apache-2.0](LICENSE). Projekt wykorzystuje logikę z [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach.
