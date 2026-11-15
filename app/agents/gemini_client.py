import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


class GeminiClient:
    """Centralized LLM adapter for WikiGuardian agents."""

    def __init__(self):
        project_root = Path(__file__).resolve().parents[2]
        env_path = project_root / ".env"

        load_dotenv(
            dotenv_path=env_path,
            override=True,
            encoding="utf-8-sig",
        )

        api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash",
        )

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing from the project .env file."
            )

        if not self.model:
            raise RuntimeError("GEMINI_MODEL cannot be empty.")

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=600000),
        )

    def generate(self, agent_name: str, prompt: str) -> str:
        """Generate structured JSON text for a specialized agent."""

        if not agent_name.strip():
            raise ValueError("Agent name cannot be empty.")

        if not prompt.strip():
            raise ValueError("Agent prompt cannot be empty.")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    max_output_tokens=8192,
                ),
            )

            result = response.text

            if not result or not result.strip():
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return result.strip()

        except Exception as exc:
            raise RuntimeError(
                f"Gemini generation failed for agent "
                f"'{agent_name}': {type(exc).__name__}: {exc}"
            ) from exc

    def __call__(self, agent_name: str, prompt: str) -> str:
        """Allow direct injection into run_verification()."""
        return self.generate(agent_name, prompt)


