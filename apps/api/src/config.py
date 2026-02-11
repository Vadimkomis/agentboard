from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://tempsaas:tempsaas@localhost:5432/tempsaas"
    redis_url: str = "redis://localhost:6379"
    secret_key: str = "dev-secret-key-change-in-production"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_webhook_secret: str = ""
    encryption_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
