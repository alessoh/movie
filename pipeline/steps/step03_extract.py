"""Step 3 - Text extraction.

Read the uploaded file (plain text, Word, or PDF) into one clean block of
plain text.  If the manuscript is very large it is truncated to a workable
size, since it is about to be compressed to a single paragraph anyway.
"""
from __future__ import annotations

from pathlib import Path

# Keep the LLM input bounded.  Far more than enough to capture a novel's spine.
MAX_CHARS = 60_000


def extract_text(upload_path: str) -> str:
    path = Path(upload_path)
    suffix = path.suffix.lower()

    if suffix in (".txt", ".md", ""):
        text = _read_txt(path)
    elif suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix in (".docx", ".doc"):
        text = _read_docx(path)
    else:
        # Best effort: try as text.
        text = _read_txt(path)

    text = _clean(text)
    if not text:
        raise RuntimeError("Could not extract any text from the uploaded file.")
    if len(text) > MAX_CHARS:
        # Keep the opening and the ending; novels resolve their arc at the end.
        head = text[: int(MAX_CHARS * 0.7)]
        tail = text[-int(MAX_CHARS * 0.3):]
        text = head + "\n\n[...]\n\n" + tail
    return text


def _read_txt(path: Path) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(chunks)


def _read_docx(path: Path) -> str:
    import docx

    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs)


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n")]
    # Collapse runs of blank lines.
    out = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()
