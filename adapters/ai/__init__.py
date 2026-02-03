"""AI adapters package for message formatting."""
from .ollama_ai import OllamaAI
from .openai_ai import OpenAICompatibleAI

__all__ = ["OllamaAI", "OpenAICompatibleAI"]
