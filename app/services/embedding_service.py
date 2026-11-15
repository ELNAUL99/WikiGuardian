import math
import os

import requests
from dotenv import load_dotenv
from pathlib import Path


class EmbeddingService:
    """Generate WikiGuardian-compatible BGE-M3 embeddings through Ollama."""

    DIMENSIONS = 1024
    MODEL = "bge-m3"
    CONTEXT_LENGTH = 8192

    def __init__(self):
        project_root = Path(__file__).resolve().parents[2]

        load_dotenv(
            dotenv_path=project_root / ".env",
            override=True,
            encoding="utf-8-sig",
        )

        self.base_url = os.getenv(
            "OLLAMA_URL",
            "http://localhost:11434",
        ).rstrip("/")

        self.model = os.getenv(
            "OLLAMA_EMBEDDING_MODEL",
            self.MODEL,
        )

        self.timeout = 45

        self.options = {
            "num_ctx": self.CONTEXT_LENGTH,
            "num_batch": self.CONTEXT_LENGTH,
        }

        self.session = requests.Session()

    def embed(self, text: str) -> list[float]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Embedding text cannot be empty.")

        try:
            response = self.session.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": text,
                    "truncate": False,
                    "options": self.options,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()
            payload = response.json()

            embeddings = payload.get("embeddings")

            if not embeddings or len(embeddings) != 1:
                raise ValueError(
                    "Ollama did not return exactly one embedding."
                )

            vector = embeddings[0]

            if len(vector) != self.DIMENSIONS:
                raise ValueError(
                    f"Expected {self.DIMENSIONS} dimensions, "
                    f"received {len(vector)}."
                )

            vector = [float(value) for value in vector]

            if not all(math.isfinite(value) for value in vector):
                raise ValueError(
                    "Embedding contains non-finite values."
                )

            return vector

        except requests.RequestException as exc:
            raise RuntimeError(
                f"BGE-M3 embedding request failed: {exc}"
            ) from exc

    def __call__(self, text: str) -> list[float]:
        return self.embed(text)
