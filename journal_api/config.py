import os
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings
from google.cloud import secretmanager


class Settings(BaseSettings):
    # GCP
    gcp_project_id: str = "igethappy-dev"
    database_url_secret_name: str = "database-url"
    jwt_secret_key_secret_name: str = "jwt-secret-key"

    # Storage
    gcs_bucket_name_secret_name: str = "journal-attachments-bucket"

    # Resolved values
    database_url: Optional[str] = None
    jwt_secret_key: Optional[str] = None
    gcs_bucket_name: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_secrets()

    def _load_secrets(self) -> None:
        try:
            client = secretmanager.SecretManagerServiceClient()
            project_path = f"projects/{self.gcp_project_id}"

            def _get(name: str, env: str) -> str:
                try:
                    full = f"{project_path}/secrets/{name}/versions/latest"
                    resp = client.access_secret_version(request={"name": full})
                    return resp.payload.data.decode("utf-8")
                except Exception:
                    return os.getenv(env, "")

            self.database_url = _get(self.database_url_secret_name, "DATABASE_URL")
            self.jwt_secret_key = _get(self.jwt_secret_key_secret_name, "JWT_SECRET_KEY")
            self.gcs_bucket_name = _get(self.gcs_bucket_name_secret_name, "GCS_BUCKET_NAME")
        except Exception:
            # Fallback to env
            self.database_url = os.getenv("DATABASE_URL", "")
            self.jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
            self.gcs_bucket_name = os.getenv("GCS_BUCKET_NAME", "")

    def validate(self) -> None:
        if not self.database_url:
            # Local dev default (matches backend style)
            self.database_url = "postgresql+asyncpg://postgres:aktmar@127.0.0.1:5432/mental_health_app"


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    s.validate()
    return s


settings = get_settings()


