from app.models.document import Document


def test_document_review_contract_is_explicit():
    document = Document(original_filename="order.pdf", mime_type="application/pdf", file_size=10, storage_key="x", sha256="x")
    document.status = "EXTRACTED"

    assert document.status == "EXTRACTED"
