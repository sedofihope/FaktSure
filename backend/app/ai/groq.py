import json
import httpx

from app.ai.base import LLMProvider
from app.ai.prompts import EXTRACTION_PROMPT


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        self.api_key = api_key
        self.model = model

    def extract_structured(self, text: str) -> dict:
        payload = {"model": self.model, "messages": [{"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:30000])}], "response_format": {"type": "json_object"}, "temperature": 0}
        response = httpx.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {self.api_key}"}, json=payload, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
