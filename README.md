# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

**Polskie PDF-y i skany w jednym wywołaniu Pythona.** CzytajPDF odczytuje dokument strona po stronie. Gdy pismo ma warstwę tekstową, a załącznik jest skanem, dostajesz jeden wynik z informacją, skąd pochodzi tekst każdej strony. Opcjonalna korekta przywraca polskie znaki, a oryginalny odczyt pozostaje dostępny do porównania.

> **English summary:** Page-wise Python library (Apache-2.0) for hybrid Polish PDFs — reads embedded text via `pypdf`, automatically falls back to local OCR (`tesserocr` / `rapidocr`) on scanned pages, and optionally applies Polish morphological & frequency spelling repair (`morfeusz2` + `wordfreq`) with dual-resolution word reconciliation while preserving each page's `source` and `raw_text`. See [README.en.md](README.en.md).

## Pierwszy odczyt

Python 3.10+. Instalacja z GitHuba z obsługą OCR i polskiej korekty:

```sh
python -m pip install 'czytajpdf[ocr,polish] @ git+https://github.com/praha6248/CzytajPDF.git'
```

```python
from czytajpdf import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)
```

Do PDF-ów z warstwą tekstową wystarczy instalacja bez dodatków i wywołanie `extract("pismo.pdf")`. Cały tekst jest dostępny jako `dokument.text`. Numeracja stron zaczyna się od 1.

## Statystyki odczytu

| Dokument | Strony | Strony z warstwy tekstowej | Strony odczytane przez OCR | Znaki z OCR |
| --- | ---: | ---: | ---: | ---: |
| [Dz.U. 2024 poz. 1](https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf) | 8 | 8 | 0 | 0 |
| [Dz.U. 1945 nr 5 poz. 17](https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf) | 2 | 2 | 0 | 0 |
| PDF mieszany z pierwszych stron obu dokumentów | 2 | 1 | 1 | 2716 |

## Skuteczność korekty polskiego OCR

Pomiar obejmuje nagłówki z 18 archiwalnych skanów Dziennika Ustaw. Na pierwotnej próbce 12 nagłówków **liczba błędów słów spadła z 79 do 2**. Do porównania użyto tych samych wycinków i transkrypcji.

| Próbka i wersja biblioteki | Błędy znaków (CER) po korekcie | Błędy słów (WER) po korekcie |
| --- | ---: | ---: |
| 12 pierwotnych nagłówków · 0.1.0, RapidOCR | 382 / 2129 · 17,94% | 79 / 293 · 26,96% |
| Te same 12 nagłówków · 0.2.0, Tesseract | 2 / 2129 · 0,09% | 2 / 293 · 0,68% |
| 3 dodatkowe nagłówki użyte do sprawdzenia i poprawienia obsługi dzielenia słów · 0.2.0 | 0 / 593 · 0,00% | 0 / 87 · 0,00% |
| 3 osobne nagłówki użyte do końcowej weryfikacji · 0.2.0 | 1 / 430 · 0,23% | 1 / 67 · 1,49% |

Na pierwotnej próbce surowy Tesseract popełnił 5 błędów słów, a drugi odczyt z korektą usunął 3. Pozostały pomyłki `r.` → `r,` oraz `i` → `1`. W końcowej weryfikacji OCR dodał kropkę po słowie `lutego`.

CER i WER uwzględniają zamiany, wstawienia i pominięcia względem transkrypcji z obrazu. Ujednolicono białe znaki, zachowując interpunkcję i wielkość liter. Wynik dotyczy wycinków z drukowanymi nagłówkami. [Pomiar 0.1.0](benchmarks/rapidocr-0.1.0.json) · [Pomiar 0.2.0](benchmarks/results.json) · [Próbka dodatkowa](benchmarks/holdout.json) · [Weryfikacja końcowa](benchmarks/validation.json) · [Skrypt pomiarowy](benchmarks/score.py)

## Jak wybierany jest sposób odczytu

- Domyślnie działa pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków trafiają do polskiego modelu Tesseract. Aby wybrać RapidOCR, przekaż `engine="rapidocr"`. Próg zmienisz przez `min_chars`. Długa, uszkodzona warstwa tekstowa może przejść ten próg.
- `source` przyjmuje wartość `pdf`, `tesseract` lub `rapidocr`. Pusty wynik OCR pozostawia tekst z warstwy PDF. Wynik zachowuje podział na strony, bez współrzędnych słów ani struktury tabel.
- `correct=True` włącza korektę słownikową wyników OCR z użyciem wordfreq i Morfeusza 2. Tesseract może ponownie odczytać stronę w innej rozdzielczości, aby sprawdzić nierozpoznane słowa. Pierwszy odczyt pozostaje dostępny w `raw_text`. Przy nazwiskach i nazwach własnych warto porównać wynik z `raw_text`.
- Rozpoznawanie odbywa się lokalnie. Przy pierwszym użyciu Tesseract pobiera polski model tessdata_best (około 12 MB), sprawdza SHA-256 i zapisuje plik w pamięci podręcznej. Kolejne odczyty działają offline. RapidOCR korzysta z osobnych modeli.

## Licencja i pochodzenie

Kod biblioteki jest dostępny na [Apache-2.0](LICENSE). Projekt wykorzystuje logikę z [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach.
