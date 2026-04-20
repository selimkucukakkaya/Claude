from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ms_tenant_id: str = "common"
    ms_client_id: str
    ms_client_secret: str
    ms_user_id: str = "me"
    ms_redirect_uri: str = "http://localhost:8000/auth/callback"

    public_base_url: str
    graph_webhook_client_state: str

    telegram_bot_token: str
    telegram_allowed_user_id: int

    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-6"

    db_path: str = "./data/state.db"
    archive_folder_name: str = "Arsiv"


settings = Settings()
