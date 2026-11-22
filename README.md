# CzytajPDF

**Polskie PDF-y i skany w jednym wywołaniu Pythona.** CzytajPDF odczytuje dokument strona po stronie. Gdy pismo ma warstwę tekstową, a załącznik jest skanem, dostajesz jeden wynik z informacją, skąd pochodzi tekst każdej strony. Opcjonalna korekta przywraca polskie znaki, a oryginalny odczyt pozostaje dostępny do porównania.

## Pierwszy odczyt

Python 3.10+. Instalacja z GitHuba z obsługą OCR i polskiej korekty:

```sh
python -m pip install 'polpdf-text[ocr,polish] @ git+https://github.com/praha6248/CzytajPDF.git'
```

```python
from polpdf_text import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)
```

Do PDF-ów z warstwą tekstową wystarczy instalacja bez dodatków i wywołanie `extract("pismo.pdf")`. Cały tekst jest dostępny jako `dokument.text`. Numeracja stron zaczyna się od 1.

## Co pokazała próba na Dzienniku Ustaw

| Materiał | Wynik |
| --- | --- |
| [Dz.U. 2024 poz. 1](https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf) | 8 z 8 stron odczytanych z warstwy tekstowej |
| [Dz.U. 1945 nr 5 poz. 17](https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf) | 2 z 2 stron odczytane z istniejącej warstwy tekstowej archiwalnego skanu |
| Dokument mieszany złożony z pierwszych stron obu źródeł | Strona współczesna odczytana przez pypdf. Dla historycznej zachowano sam obraz, co uruchomiło RapidOCR i dało 2662 znaki |

Na historycznej stronie OCR odczytał nagłówek jako `TRESC:`. Po korekcie `strona.text` zawierał `TREŚĆ:`, a `strona.raw_text` zachował pierwotny zapis. Inny nagłówek, `DEKRETY`, pozostał błędnie odczytany jako `DEHRETY`. To próba działania na konkretnych dokumentach. Liczba rozpoznanych znaków nie mierzy dokładności.

Aby powtórzyć próbę z katalogu sklonowanego repozytorium:

```sh
python -m pip install '.[ocr,polish]' reportlab
python tests/public_pdfs.py
```

## Jak wybierany jest sposób odczytu

- Domyślnie działa pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków trafiają do RapidOCR. Próg zmienisz przez `min_chars`. Długa, uszkodzona warstwa tekstowa może przejść ten próg.
- `source` przyjmuje wartość `pdf` lub `rapidocr`. Pusty wynik OCR pozostawia tekst z warstwy PDF. Wynik zachowuje podział na strony, bez współrzędnych słów ani struktury tabel.
- `correct=True` włącza korektę słownikową wyników OCR z użyciem wordfreq i Morfeusza 2. Przy nazwiskach i nazwach własnych warto porównać wynik z `raw_text`.
- Rozpoznawanie odbywa się lokalnie. RapidOCR może pobrać brakujące modele przy pierwszym użyciu.

## Licencja i pochodzenie

Kod biblioteki jest dostępny na [Apache-2.0](LICENSE). Projekt wykorzystuje logikę z [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach.
