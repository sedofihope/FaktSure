import json
import httpx

from app.ai.base import LLMProvider
from app.ai.prompts import EXTRACTION_PROMPT


class CloudflareProvider(LLMProvider):
    def __init__(self, account_id: str, api_token: str, model: str) -> None:
        if not account_id or not api_token or not model:
            raise RuntimeError("Cloudflare Workers AI credentials or model are not configured")
        self.account_id = account_id
        self.api_token = api_token
        self.model = model

    def extract_structured(self, text: str) -> dict:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
        payload = {
            "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:30000])}],
            "max_tokens": 4096,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        response = httpx.post(url, headers={"Authorization": f"Bearer {self.api_token}"}, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json().get("result")
        content = None
        if isinstance(result, dict):
            content = result.get("response")
            if not content:
                choices = result.get("choices")
                if isinstance(choices, list) and choices:
                    first_choice = choices[0]
                    message = first_choice.get("message") if isinstance(first_choice, dict) else None
                    content = message.get("content") if isinstance(message, dict) else None
        if not content:
            raise RuntimeError("Cloudflare returned no text")
        return json.loads(content)
