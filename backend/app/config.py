from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://portal_app:portal_app@localhost:5432/employees"
    oidc_issuer: str = "https://auth.localhost/realms/securehr"
    oidc_jwks_url: str = "http://keycloak:8080/realms/securehr/protocol/openid-connect/certs"
    oidc_audience: str = "securehr-portal"
    cors_origins: list[str] = ["https://portal.localhost"]


settings = Settings()
