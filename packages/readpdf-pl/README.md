# readpdf-pl

Pakiet Pythona i CLI do odczytu polskich dokumentów PDF i skanów strona po stronie (część projektu [CzytajPDF](https://github.com/praha6248/CzytajPDF), stworzonego na podstawie projektu [odwolania2json](https://github.com/praha6248/odwolania2Json)).

```sh
python -m pip install 'readpdf-pl[all]'
```

```sh
readpdf-pl pismo-z-zalacznikami.pdf --ocr --correct --json
```

```python
from readpdf_pl import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)
```

Funkcja `extract(...)` przyjmuje ścieżkę (`str | Path`), `bytes` lub strumień binarny `BinaryIO`. Do plików z poprawną warstwą tekstową wystarczy instalacja podstawowa (`pip install readpdf-pl`). Pełna dokumentacja i benchmarki: [CzytajPDF](https://github.com/praha6248/CzytajPDF).
