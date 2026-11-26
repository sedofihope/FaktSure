from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface for structured document extraction providers."""

    @abstractmethod
    def extract_structured(self, text: str) -> dict:
        """Return validated provider JSON data or raise a provider error."""
