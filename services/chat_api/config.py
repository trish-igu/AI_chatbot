"""
Configuration and loading secrets from GCP Secret Manager with fallback to environment variables.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from google.cloud import secretmanager
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings with GCP Secret Manager integration and environment variable fallback."""
    
    # GCP Configuration
    gcp_project_id: str = "igethappy-dev"
    database_url_secret_name: str = "database-url"
    # Vertex AI (Gemini via Vertex)
    vertex_project_id_secret_name: str = "vertex-project-id"
    vertex_location_secret_name: str = "vertex-location"
    vertex_model_name_secret_name: str = "vertex-model"
    
    # ADD THIS: Configuration for the background service
    summarization_interval_seconds: int = 300 # Check every 5 minutes by default

    # Loaded secrets (will be populated from Secret Manager or environment)
    database_url: Optional[str] = None
    vertex_project_id: Optional[str] = None
    vertex_location: Optional[str] = None
    vertex_model_name: Optional[str] = None
    llm_provider: str = os.getenv("LLM_PROVIDER", "vertex")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Load secrets from GCP Secret Manager with fallback to environment variables
        self._load_secrets()

    def _load_secrets(self):
        """Load secrets from Google Cloud Secret Manager with fallback to environment variables."""
        try:
            # Initialize the Secret Manager client
            client = secretmanager.SecretManagerServiceClient()
            project_path = f"projects/{self.gcp_project_id}"
            
            print("Loading application secrets from Google Secret Manager...")
            
            # Load each secret with fallback
            self.database_url = self._get_secret_with_fallback(
                client, project_path, self.database_url_secret_name, "DATABASE_URL"
            )

            # Vertex AI settings (only)
            self.vertex_project_id = self._get_secret_with_fallback(
                client, project_path, self.vertex_project_id_secret_name, "VERTEX_PROJECT_ID"
            )
            self.vertex_location = self._get_secret_with_fallback(
                client, project_path, self.vertex_location_secret_name, "VERTEX_LOCATION"
            )
            self.vertex_model_name = self._get_secret_with_fallback(
                client, project_path, self.vertex_model_name_secret_name, "VERTEX_MODEL"
            )
            # (Removed other providers: OpenAI/Anthropic/xAI)
            
            print("Secrets loaded successfully.")
            
        except Exception as e:
            print(f"Warning: Could not load secrets from GCP Secret Manager: {e}")
            print("Falling back to environment variables...")
            # Fallback to environment variables
            self.database_url = os.getenv("DATABASE_URL")
            self.vertex_project_id = os.getenv("VERTEX_PROJECT_ID")
            self.vertex_location = os.getenv("VERTEX_LOCATION")
            self.vertex_model_name = os.getenv("VERTEX_MODEL")
            # (Removed other providers env fallbacks)

    def _get_secret_with_fallback(self, client, project_path: str, secret_name: str, env_var_name: str) -> str:
        """Get a secret value from Google Cloud Secret Manager with environment variable fallback."""
        try:
            secret_path = f"{project_path}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": secret_path})
            # Trim whitespace/newlines to avoid region/model parsing issues
            return response.payload.data.decode("UTF-8").strip()
        except Exception as e:
            print(f"Could not fetch secret '{secret_name}' from GCP Secret Manager: {e}")
            # Fallback to environment variable
            env_value = os.getenv(env_var_name)
            if env_value:
                print(f"Using environment variable {env_var_name} instead.")
                return env_value.strip()
            else:
                print(f"Warning: Neither GCP secret '{secret_name}' nor environment variable '{env_var_name}' found.")
                return ""

    def validate_secrets(self):
        """Validate that all required secrets are loaded, with fallbacks for local dev."""
        # --- Local-only override (skip in Cloud Run where K_SERVICE is present) ---
        running_in_cloud_run = bool(os.getenv("K_SERVICE"))
        if not running_in_cloud_run:
            # If database_url is not loaded or is the unix socket path, override it for local proxy.
            if not self.database_url or self.database_url.startswith("postgresql+asyncpg://postgres:aktmar@/mental_health_app?host=/cloudsql/"):
                self.database_url = "postgresql+asyncpg://postgres:aktmar@127.0.0.1:5432/mental_health_app"
                print(f"OVERRIDE: Using local Cloud SQL Auth Proxy DATABASE_URL: {self.database_url}")
        
        # Fallbacks for other secrets if not found (dev only)
        if self.llm_provider.lower() == "vertex":
            if not self.vertex_project_id:
                self.vertex_project_id = self.gcp_project_id
                print("Using default VERTEX_PROJECT_ID from gcp_project_id")
            if not self.vertex_location:
                self.vertex_location = "us-central1"
                print("Using default VERTEX_LOCATION=us-central1")
            if not self.vertex_model_name:
                self.vertex_model_name = "gemini-2.5-pro"
                print("Using default VERTEX_MODEL=gemini-2.5-pro")
        # Removed other provider fallbacks
        
        return True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.validate_secrets()
    return settings


# Global settings instance
settings = get_settings()


