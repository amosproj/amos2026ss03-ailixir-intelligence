from __future__ import annotations

from dataclasses import dataclass

from kg_chat.config import AppConfig


class LlmConfigurationError(RuntimeError):
    pass


@dataclass
class LlmClient:
    config: AppConfig

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        raise NotImplementedError


class VertexGeminiClient(LlmClient):
    def __post_init__(self) -> None:
        try:
            import vertexai
            from vertexai.preview.generative_models import GenerativeModel
        except Exception as exc:
            raise LlmConfigurationError(
                "Vertex AI dependencies are missing. Install google-cloud-aiplatform."
            ) from exc

        vertexai.init(
            project=self.config.google_cloud_project,
            location=self.config.google_cloud_location,
        )
        self._model = GenerativeModel(model_name=self.config.gemini_model)

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        from vertexai.preview.generative_models import GenerationConfig

        response = self._model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=temperature
                if temperature is not None
                else self.config.gemini_temperature,
                max_output_tokens=max_output_tokens
                if max_output_tokens is not None
                else self.config.gemini_max_output_tokens,
            ),
        )
        return (response.text or "").strip()


class GoogleGenaiGeminiClient(LlmClient):
    def __post_init__(self) -> None:
        if not self.config.gemini_api_key:
            raise LlmConfigurationError("GEMINI_API_KEY is required for google-genai.")
        try:
            from google import genai
        except Exception as exc:
            raise LlmConfigurationError(
                "google-genai dependency is missing. Install google-genai."
            ) from exc

        self._client = genai.Client(api_key=self.config.gemini_api_key)

    def generate_text(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=self.config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature
                if temperature is not None
                else self.config.gemini_temperature,
                max_output_tokens=max_output_tokens
                if max_output_tokens is not None
                else self.config.gemini_max_output_tokens,
            ),
        )
        return (response.text or "").strip()


def build_llm_client(config: AppConfig) -> LlmClient:
    if config.llm_provider == "vertex":
        client = VertexGeminiClient(config)
        client.__post_init__()
        return client
    if config.llm_provider == "google-genai":
        client = GoogleGenaiGeminiClient(config)
        client.__post_init__()
        return client
    raise LlmConfigurationError(
        f"Unsupported LLM_PROVIDER={config.llm_provider!r}. Use 'vertex' or 'google-genai'."
    )

