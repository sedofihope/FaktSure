from app.main import app


def test_every_api_operation_has_french_swagger_documentation():
    schema = app.openapi()
    operations = [
        operation
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]

    assert len(operations) == 47
    assert all(operation.get("summary") for operation in operations)
    assert all(len(operation.get("description", "")) >= 100 for operation in operations)
    assert all(operation.get("responses") for operation in operations)
    assert schema["info"]["description"].strip().startswith("## Bien démarrer")
    assert {tag["name"] for tag in schema["tags"]} >= {
        "authentication",
        "batches",
        "documents",
        "invoices",
        "settings",
    }


def test_swagger_documents_upload_fields_and_binary_responses():
    schema = app.openapi()
    upload = schema["paths"]["/api/batches/{batch_id}/documents"]["post"]
    upload_schema = upload["requestBody"]["content"]["multipart/form-data"]["schema"]
    upload_model = schema["components"]["schemas"][upload_schema["$ref"].rsplit("/", 1)[-1]]
    assert upload_model["properties"]["files"]["items"]["format"] == "binary"

    pdf_response = schema["paths"]["/api/invoices/{invoice_id}/pdf"]["get"]["responses"]["200"]
    assert "application/pdf" in pdf_response["content"]
    assert pdf_response["content"]["application/pdf"]["schema"]["format"] == "binary"

    fields_response = schema["paths"]["/api/documents/{document_id}/fields"]["get"]["responses"]["200"]
    assert fields_response["content"]["application/json"]["schema"]["items"]["$ref"].endswith(
        "/ExtractedFieldResponse"
    )
