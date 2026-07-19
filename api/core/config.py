"""
Configuration settings for the NightForge API (control-plane).
"""
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        env: Current environment (development, staging, production).
        debug: Whether debug mode is enabled.
        api_version: API version string.
        api_prefix: API prefix for routes.
        host: Server host address.
        port: Server port number.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    env: str = "development"
    debug: bool = True
    api_version: str = "v1"
    api_prefix: str = "/api/v1"
    api_base_url: str = Field(
        default="http://localhost:8010",
        alias="API_BASE_URL",
        description="Base URL for the API server",
    )

    host: str = "0.0.0.0"
    port: int = Field(default=8010, alias="PORT")

    cors_origins_str: Optional[str] = Field(
        default="http://localhost:3000,http://localhost:1420",
        alias="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins",
    )

    # Database
    database_url: str = Field(
        default="mysql+pymysql://root:root@localhost:3311/nightforge",
        alias="DATABASE_URL",
        description="Database connection URL",
    )

    # JWT
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        alias="SECRET_KEY",
        description="Secret key for JWT token signing",
    )
    algorithm: str = Field(default="HS256", description="Algorithm for JWT token signing")
    access_token_expire_minutes: int = Field(
        default=1440,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
        description="Access token expiration time in minutes",
    )

    # Admin user (seeded)
    admin_email: str = Field(
        default="contact@dibodev.fr",
        alias="ADMIN_EMAIL",
        description="Admin user email address",
    )
    admin_password: str = Field(
        default="admin123",
        alias="ADMIN_PASSWORD",
        description="Admin user password",
    )

    # Encryption (agent tokens / secrets)
    encryption_key: Optional[str] = Field(
        default=None,
        alias="ENCRYPTION_KEY",
        description="Fernet key for encrypting sensitive data (agent tokens)",
    )

    frontend_url: str = Field(
        default="http://localhost:3000",
        alias="FRONTEND_URL",
        description="Frontend URL for links/redirects",
    )

    # Groq — cloud LLM fallback for Aide prompts IA when no agent is online
    groq_api_key: Optional[str] = Field(
        default=None,
        alias="GROQ_API_KEY",
        description="Groq API key for ideas expansion fallback",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        alias="GROQ_MODEL",
        description="Groq model id for ideas expansion",
    )

    @property
    def cors_origins(self) -> List[str]:
        """
        Get CORS origins as a list from the comma-separated string.

        Returns:
            List of allowed CORS origins.
        """
        if not self.cors_origins_str:
            return []
        return [o.strip() for o in self.cors_origins_str.split(",") if o.strip()]

    @property
    def allowed_cors_origins(self) -> List[str]:
        """
        Get allowed CORS origins based on environment, including Tauri desktop origins.

        Returns:
            List of allowed origins for CORS.
        """
        origins = self.cors_origins.copy()

        # Tauri desktop app origins (constant across environments).
        desktop_origins = [
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ]
        for origin in desktop_origins:
            if origin not in origins:
                origins.append(origin)

        if self.env.lower() != "production":
            for origin in [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:3003",
                "http://localhost:1420",
                "http://127.0.0.1:1420",
            ]:
                if origin not in origins:
                    origins.append(origin)

        return origins

    @property
    def is_production(self) -> bool:
        """
        Determine if the application is running in production.

        Returns:
            True if production environment.
        """
        return self.env.lower() == "production"


# Global settings instance
settings = Settings()
