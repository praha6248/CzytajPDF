# polpdf-text

Biblioteka Pythona do odczytu polskich PDF-ów. Zwraca strony w kolejności dokumentu. Opcjonalnie rozpoznaje skany przez RapidOCR i przywraca polskie znaki z pomocą wordfreq oraz Morfeusza 2.

## Instalacja z katalogu projektu

```sh
python -m pip install .
# Z obsługą skanów i korekty
python -m pip install '.[ocr,polish]'
```

## Przykład

```python
from polpdf_text import extract

document = extract("dokument.pdf", ocr=True, correct=True)
for page in document.pages:
    print(page.number, page.source, page.text)
    if page.raw_text != page.text:
        print("Przed korektą:", page.raw_text)
```

Domyślnie `extract("dokument.pdf")` odczytuje samą warstwę tekstową za pomocą pypdf. Przy `ocr=True` strony z mniej niż 40 znakami po pominięciu białych znaków trafiają do OCR. Próg można zmienić przez `min_chars`. Krótka strona tytułowa może więc trafić do OCR, a skan z długą, błędną warstwą tekstową może zostać pominięty. Pusty wynik OCR pozostawia pierwotny tekst strony.

`number` liczy strony od 1. `source` wskazuje źródło zwróconego tekstu (`pdf` albo `rapidocr`). `raw_text` zachowuje odczyt z tego źródła przed korektą. `correct=True` koryguje wyłącznie wynik OCR. Korekta może zmienić nazwy własne. `document.text` łączy strony znakiem nowej linii. Wynik jest tekstem bez współrzędnych i struktury tabel.

## Pochodzenie i licencja

Kod pakietu jest dostępny na Apache-2.0 i wykorzystuje logikę [odwolania2json](https://github.com/praha6248/odwolania2Json). Wagi OCR, słowniki i dane częstości są osobnymi zależnościami na własnych licencjach. RapidOCR może pobrać brakujące modele przy pierwszym użyciu.
