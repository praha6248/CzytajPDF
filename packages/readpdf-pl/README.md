# readpdf-pl

Pakiet Pythona do odczytu polskich dokumentów PDF i skanów strona po stronie (część projektu [CzytajPDF](https://github.com/praha6248/CzytajPDF)).

```sh
python -m pip install 'readpdf-pl[all]'
```

```python
from readpdf_pl import extract

dokument = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True)
for strona in dokument.pages:
    print(strona.number, strona.source, strona.text)
```

Do plików posiadających warstwę tekstową wystarczy instalacja podstawowa (`pip install readpdf-pl`) i wywołanie `extract("dokument.pdf")`. Pełna dokumentacja i wyniki benchmarków znajdują się w repozytorium [CzytajPDF](https://github.com/praha6248/CzytajPDF).
