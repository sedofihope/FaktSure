def test_health_endpoint(client):
    """The health endpoint should be available and return OK."""

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_exposes_file_picker_for_multi_file_upload(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/batches/{batch_id}/documents"]["post"]
    body_ref = operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    body_schema = schema["components"]["schemas"][body_ref.rsplit("/", 1)[-1]]

    assert body_schema["properties"]["files"]["type"] == "array"
    assert body_schema["properties"]["files"]["items"]["type"] == "string"
    assert body_schema["properties"]["files"]["items"]["format"] == "binary"
