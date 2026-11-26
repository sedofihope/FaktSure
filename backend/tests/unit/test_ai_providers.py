import json

from app.ai.cloudflare import CloudflareProvider
from app.ai.prompts import EXTRACTION_PROMPT


def test_cloudflare_provider_parses_openai_compatible_response(monkeypatch):
    payload = {"document_number": "TEST-42", "items": []}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "result": {
                    "choices": [{
                        "message": {"content": json.dumps(payload)},
                    }],
                },
            }

    request = {}

    def fake_post(*args, **kwargs):
        request.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.ai.cloudflare.httpx.post", fake_post)

    provider = CloudflareProvider("account", "token", "@cf/openai/gpt-oss-120b")
    assert provider.extract_structured("synthetic text") == payload
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["max_tokens"] == 4096


def test_extraction_prompt_formats_json_schema_and_document_text():
    prompt = EXTRACTION_PROMPT.format(text="synthetic invoice")
    assert '"document_number": "string|null"' in prompt
    assert '"client_rccm": "string|null"' in prompt
    assert prompt.endswith("synthetic invoice\n")
