from pathlib import Path

from dotenv import load_dotenv

from app.agents.openai_client import OpenAIClient


def get_llm_client():
    """Initialize the configured LLM provider."""

    project_root = Path(__file__).resolve().parents[2]

    load_dotenv(
        dotenv_path=project_root / ".env",
        override=True,
        encoding="utf-8-sig",
    )

    provider = __import__("os").getenv(
        "LLM_PROVIDER",
        "verda",
    ).lower()

    if provider == "verda":
        return OpenAIClient()

    raise ValueError(
        f"Unsupported LLM provider: {provider}"
    )
