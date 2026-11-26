from pathlib import Path

import pymupdf as fitz


def classify_document(content: bytes, filename: str, mime_type: str) -> tuple[str, float, str]:
    """Classify a file by signature and page text/image content."""

    if content.startswith(b"%PDF"):
        try:
            pdf = fitz.open(stream=content, filetype="pdf")
            text_pages = 0
            image_pages = 0
            for page in pdf:
                if page.get_text("text").strip():
                    text_pages += 1
                if page.get_images(full=True):
                    image_pages += 1
            pdf.close()
            if text_pages and image_pages:
                return "MIXED_PDF", 0.95, "native-and-image"
            if text_pages:
                return "NATIVE_PDF", 0.98, "native-pdf"
            if image_pages:
                return "SCANNED_PDF", 0.98, "scanned-pdf"
            return "SCANNED_PDF", 0.70, "empty-pdf"
        except Exception:
            return "UNSUPPORTED", 0.20, "invalid-pdf"
    if mime_type.startswith("image/") or Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        return "IMAGE", 0.95, "image"
    return "UNSUPPORTED", 0.99, "extension-and-signature"
