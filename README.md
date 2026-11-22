# CzytajPDF

**Polskie PDF-y i skany w jednym wywołaniu Pythona.** CzytajPDF odczytuje dokument strona po stronie. Gdy pismo ma warstwę tekstową, a załącznik jest skanem, dostajesz jeden wynik z informacją, skąd pochodzi tekst każdej strony. Opcjonalna korekta przywraca polskie znaki, a oryginalny odczyt pozostaje dostępny do porównania.

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
| PDF mieszany z pierwszych stron obu dokumentów | 2 | 1 | 1 | 2662 |

## Skuteczność korekty polskiego OCR

Porównanie obejmuje **12 nagłówków z 12 skanów Dziennika Ustaw** (293 słowa, 2129 znaków). Z każdego rocznika co cztery lata od 1950 do 1994 wybrano pozycję 100. Numer pozycji, nazwę aktu, datę i tytuł przepisano z obrazu pierwszej strony. Ten sam wycinek trafił do RapidOCR, a następnie do korekty słownikowej.

| Błędy względem transkrypcji | Surowy OCR | Po korekcie |
| --- | ---: | ---: |
| Na poziomie znaków (CER) | 391 / 2129 · 18,37% | 382 / 2129 · 17,94% |
| Na poziomie słów (WER) | 89 / 293 · 30,38% | 79 / 293 · 26,96% |

Korekta zmniejszyła liczbę błędów słów w 6 nagłówkach, w pozostałych 6 wynik był taki sam. Przywróciła m.in. zapis `działających` i `Żarach`. W skanie z 1994 r. zmieniła błędnie odczytane `stad` na równie błędne `stąd` w miejscu, gdzie wydrukowano `stanowisk`. Na skanach z 1978 i 1986 r. OCR pominął całą linię tytułu. Te pominięcia wliczono do wyniku.

CER i WER liczą wstawienia, usunięcia i zamiany względem transkrypcji, łącznie dla całej próbki. Ujednolicono odstępy i podział na wiersze, zachowując interpunkcję i wielkość liter. Wynik dotyczy drukowanych nagłówków aktów prawnych. [Odczyty, transkrypcje i źródłowe PDF-y](benchmarks/results.json) · [Skrypt pomiarowy](benchmarks/score.py)

## Jak wybierany jest sposób odczytu

- Domyślnie działa pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków trafiają do RapidOCR. Próg zmienisz przez `min_chars`. Długa, uszkodzona warstwa tekstowa może przejść ten próg.
- `source` przyjmuje wartość `pdf` lub `rapidocr`. Pusty wynik OCR pozostawia tekst z warstwy PDF. Wynik zachowuje podział na strony, bez współrzędnych słów ani struktury tabel.
- `correct=True` włącza korektę słownikową wyników OCR z użyciem wordfreq i Morfeusza 2. Przy nazwiskach i nazwach własnych warto porównać wynik z `raw_text`.
- Rozpoznawanie odbywa się lokalnie. RapidOCR może pobrać brakujące modele przy pierwszym użyciu.

## Licencja i pochodzenie

Kod biblioteki jest dostępny na [Apache-2.0](LICENSE). Projekt wykorzystuje logikę z [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach.
