"""Allow `python -m czytajpdf` invocation."""

from ._cli import main

if __name__ == "__main__":
    raise SystemExit(main())
