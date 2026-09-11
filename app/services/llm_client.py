"""The single Groq Chat Completions structured-output adapter."""

from __future__ import annotations

import json
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.groq_api_key.get_secret_value() if settings.groq_api_key else None,
            base_url=str(settings.llm_base_url),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    def structured(self, *, system: str, user: str, schema: type[T]) -> T:
        """Use Groq's Chat Completions JSON Schema mode and validate locally."""
        if not self.settings.provider_configured:
            raise RuntimeError("GROQ_API_KEY is not configured")
        json_schema = schema.model_json_schema()
        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__.lower(),
                    "strict": True,
                    "schema": json_schema,
                },
            },
            temperature=0,
        )
        message = response.choices[0].message
        if getattr(message, "refusal", None):
            raise RuntimeError("provider refusal")
        if not message.content:
            raise RuntimeError("provider returned empty structured content")
        return schema.model_validate(json.loads(message.content))
