import json
import httpx

from app.ai.base import LLMProvider
from app.ai.prompts import EXTRACTION_PROMPT


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.api_key = api_key
        self.model = model

    def extract_structured(self, text: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {"contents": [{"parts": [{"text": EXTRACTION_PROMPT.format(text=text[:30000])}]}], "generationConfig": {"responseMimeType": "application/json"}}
        response = httpx.post(url, params={"key": self.api_key}, json=payload, timeout=60)
        response.raise_for_status()
        candidates = response.json().get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned no candidates")
        return json.loads(candidates[0]["content"]["parts"][0]["text"])
