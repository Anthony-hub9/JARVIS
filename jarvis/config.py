from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    executor_model: str = "qwen2.5:1.5b"
    supervisor_model: str = "qwen2.5:1.5b"
    vision_model: str = "moondream"
    max_supervisor_retries: int = 2
    fast_supervisor: bool = True

    agenda_db_path: str = "jarvis_agenda.db"
    memory_db_path: str = "jarvis_memory.db"
    google_calendar_credentials_path: str = "credentials.json"
    google_calendar_token_path: str = "token.json"
    google_credentials_path: str = "credentials.json"
    google_token_path: str = "token.json"

    hub_host: str = "0.0.0.0"
    hub_port: int = 8000

    ntfy_topic: str = ""
    reminder_poll_seconds: float = 15.0


settings = Settings()
