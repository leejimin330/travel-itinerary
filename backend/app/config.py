from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://travel:travel@localhost:5432/travel"
    redis_url: str = "redis://localhost:6379/0"
    tourapi_key: str = ""
    holiday_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
