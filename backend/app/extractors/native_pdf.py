import pymupdf as fitz


def extract_native_pdf(content: bytes) -> list[dict]:
    """Extract text and reliable text blocks page by page from a native PDF."""

    pages: list[dict] = []
    with fitz.open(stream=content, filetype="pdf") as pdf:
        for page_number, page in enumerate(pdf, start=1):
            blocks = []
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text = block[:5]
                if str(text).strip():
                    blocks.append({"text": str(text).strip(), "bbox": [x0, y0, x1, y1]})
            pages.append({"page": page_number, "text": page.get_text("text"), "blocks": blocks})
    return pages
