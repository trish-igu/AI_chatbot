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
    azure_openai_api_key_secret_name: str = "azure-openai-api-key"
    azure_openai_endpoint_secret_name: str = "azure-openai-endpoint"
    azure_openai_deployment_name_secret_name: str = "azure-openai-deployment-name"
    
    # ADD THIS: Configuration for the background service
    summarization_interval_seconds: int = 300 # Check every 5 minutes by default

    # Loaded secrets (will be populated from Secret Manager or environment)
    database_url: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment_name: Optional[str] = None
    
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
            self.azure_openai_api_key = self._get_secret_with_fallback(
                client, project_path, self.azure_openai_api_key_secret_name, "AZURE_OPENAI_API_KEY"
            )
            self.azure_openai_endpoint = self._get_secret_with_fallback(
                client, project_path, self.azure_openai_endpoint_secret_name, "AZURE_OPENAI_ENDPOINT"
            )
            self.azure_openai_deployment_name = self._get_secret_with_fallback(
                client, project_path, self.azure_openai_deployment_name_secret_name, "AZURE_OPENAI_DEPLOYMENT_NAME"
            )
            
            print("Secrets loaded successfully.")
            
        except Exception as e:
            print(f"Warning: Could not load secrets from GCP Secret Manager: {e}")
            print("Falling back to environment variables...")
            # Fallback to environment variables
            self.database_url = os.getenv("DATABASE_URL")
            self.azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
            self.azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            self.azure_openai_deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

    def _get_secret_with_fallback(self, client, project_path: str, secret_name: str, env_var_name: str) -> str:
        """Get a secret value from Google Cloud Secret Manager with environment variable fallback."""
        try:
            secret_path = f"{project_path}/secrets/{secret_name}/versions/latest"
            response = client.access_secret_version(request={"name": secret_path})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Could not fetch secret '{secret_name}' from GCP Secret Manager: {e}")
            # Fallback to environment variable
            env_value = os.getenv(env_var_name)
            if env_value:
                print(f"Using environment variable {env_var_name} instead.")
                return env_value
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
        
        # Fallbacks for other secrets if not found
        if not self.azure_openai_api_key:
            self.azure_openai_api_key = "YOUR_FALLBACK_API_KEY" # Replace if needed
            print("Using placeholder AZURE_OPENAI_API_KEY")
        
        if not self.azure_openai_endpoint:
            self.azure_openai_endpoint = "YOUR_FALLBACK_ENDPOINT" # Replace if needed
            print("Using placeholder AZURE_OPENAI_ENDPOINT")
        
        if not self.azure_openai_deployment_name:
            self.azure_openai_deployment_name = "YOUR_FALLBACK_DEPLOYMENT_NAME" # Replace if needed
            print("Using placeholder AZURE_OPENAI_DEPLOYMENT_NAME")
        
        return True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.validate_secrets()
    return settings


# Global settings instance
settings = get_settings()