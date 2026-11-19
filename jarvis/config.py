from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    executor_model: str = "gemini-4-hydrogen-medium"
    supervisor_model: str = "gemini-4-argon-medium"
    max_supervisor_retries: int = 2

    hub_host: str = "0.0.0.0"
    hub_port: int = 8000

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"


settings = Settings()
