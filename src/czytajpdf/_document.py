"""Document container, chunking, export, and RAG framework integrations."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ._errors import MissingDependencyError
from ._types import Correction, Page

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class Chunk:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def page_metadata(page: Page) -> dict[str, Any]:
    meta: dict[str, Any] = {"page": page.number, "source": page.source}
    if page.confidence is not None:
        meta["confidence"] = round(page.confidence, 2)
    if page.lang:
        meta["lang"] = page.lang
    if page.raw_text != page.text:
        meta["corrected"] = True
    return meta


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """Split one oversized paragraph at sentence, then word boundaries; every piece <= max_chars."""
    budget = max_chars - overlap
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > budget:
            cut = sentence.rfind(" ", 0, budget)
            cut = cut if cut > budget // 2 else budget
            head, sentence = sentence[:cut].strip(), sentence[cut:].strip()
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if current and len(current) + 1 + len(sentence) > budget:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}".strip() if current else sentence
    if current:
        pieces.append(current)
    if overlap:
        for i in range(len(pieces) - 1, 0, -1):
            previous = pieces[i - 1]
            tail = previous[-overlap:]
            if len(previous) > overlap and previous[-overlap - 1] != " ":
                tail = tail[tail.find(" ") + 1:] if " " in tail else ""
            if tail:
                pieces[i] = f"{tail.strip()} {pieces[i]}"
    return pieces


def chunk_page(page: Page, max_chars: int, overlap: int) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page.text) if p.strip()]
    texts: list[str] = []
    current = ""
    for paragraph in paragraphs:
        for piece in ([paragraph] if len(paragraph) <= max_chars else _split_long(paragraph, max_chars, overlap)):
            if current and len(current) + 2 + len(piece) > max_chars:
                texts.append(current)
                current = ""
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        texts.append(current)
    return [Chunk(t, {**page_metadata(page), "chunk": i}) for i, t in enumerate(texts)]


@dataclass(frozen=True)
class Document:
    pages: tuple[Page, ...]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)

    @property
    def corrections(self) -> tuple[tuple[int, Correction], ...]:
        """All spelling changes as ``(page_number, correction)``."""
        return tuple((p.number, c) for p in self.pages for c in p.corrections)

    def low_confidence_pages(self, threshold: float = 70.0) -> tuple[Page, ...]:
        """OCR pages whose mean confidence is below ``threshold`` (0-100): worth a manual look."""
        return tuple(p for p in self.pages if p.confidence is not None and p.confidence < threshold)

    # ---- export -----------------------------------------------------------------------------
    def to_dict(self, words: bool = False) -> dict[str, Any]:
        pages = []
        for page in self.pages:
            data = asdict(page)
            if not words:
                data.pop("words")
            pages.append(data)
        return {"pages": pages, "text": self.text}

    def to_json(self, words: bool = False, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(words), ensure_ascii=False, indent=indent)

    def to_markdown(self, title: str | None = None) -> str:
        parts = [f"# {title}"] if title else []
        for page in self.pages:
            detail = page.source if page.confidence is None else f"{page.source}, confidence {page.confidence:.0f}"
            parts.append(f"## Page {page.number} ({detail})\n\n{page.text.strip()}")
        return "\n\n".join(parts) + "\n"

    # ---- RAG --------------------------------------------------------------------------------
    def chunks(self, max_chars: int | None = None, overlap: int = 0) -> list[Chunk]:
        """One chunk per non-empty page, or paragraph-packed chunks of at most ``max_chars`` (never across pages)."""
        if max_chars is not None and max_chars < 1:
            raise ValueError("max_chars must be positive")
        if overlap < 0 or (max_chars is not None and overlap > max_chars // 2):
            raise ValueError("overlap must be between 0 and max_chars // 2")
        out: list[Chunk] = []
        for page in self.pages:
            if not page.text.strip():
                continue
            if max_chars is None:
                out.append(Chunk(page.text, page_metadata(page)))
            else:
                out.extend(chunk_page(page, max_chars, overlap))
        return out

    def to_langchain(self, max_chars: int | None = None, overlap: int = 0) -> list:
        """LangChain ``Document`` objects (requires ``langchain-core``)."""
        try:
            from langchain_core.documents import Document as LCDocument
        except ImportError as exc:
            raise MissingDependencyError("to_langchain() requires czytajpdf[langchain]") from exc
        return [LCDocument(page_content=c.text, metadata=c.metadata) for c in self.chunks(max_chars, overlap)]

    def to_llamaindex(self, max_chars: int | None = None, overlap: int = 0) -> list:
        """LlamaIndex ``Document`` objects (requires ``llama-index-core``)."""
        try:
            from llama_index.core import Document as LIDocument
        except ImportError as exc:
            raise MissingDependencyError("to_llamaindex() requires czytajpdf[llamaindex]") from exc
        return [LIDocument(text=c.text, metadata=c.metadata) for c in self.chunks(max_chars, overlap)]
