import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


class OpenAIClient:
    """Centralized OpenAI-compatible client for WikiGuardian."""

    def __init__(self):
        project_root = Path(__file__).resolve().parents[2]

        load_dotenv(
            dotenv_path=project_root / ".env",
            override=True,
            encoding="utf-8-sig",
        )

        api_key = os.getenv("OPENAI_COMPATIBLE_API_KEY")
        base_url = os.getenv("OPENAI_COMPATIBLE_URL")
        self.model = os.getenv("OPENAI_COMPATIBLE_MODEL")

        if not api_key:
            raise RuntimeError(
                "OPENAI_COMPATIBLE_API_KEY is missing from .env."
            )

        if not base_url:
            raise RuntimeError(
                "OPENAI_COMPATIBLE_URL is missing from .env."
            )

        if not self.model:
            raise RuntimeError(
                "OPENAI_COMPATIBLE_MODEL is missing from .env."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url.rstrip("/") + "/v1",
            timeout=120.0,
            max_retries=1,
        )

    def generate(self, agent_name: str, prompt: str) -> str:
        if not agent_name.strip():
            raise ValueError("Agent name cannot be empty.")

        if not prompt.strip():
            raise ValueError("Agent prompt cannot be empty.")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Return only a valid JSON object. "
                            "Do not include Markdown fences or extra text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=8192,
            )

            result = response.choices[0].message.content

            if not result or not result.strip():
                raise RuntimeError("The model returned an empty response.")

            return result.strip()

        except Exception as exc:
            raise RuntimeError(
                f"LLM generation failed for agent "
                f"'{agent_name}': {type(exc).__name__}: {exc}"
            ) from exc

    def __call__(self, agent_name: str, prompt: str) -> str:
        return self.generate(agent_name, prompt)
