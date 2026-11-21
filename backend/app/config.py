from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://portal_app:portal_app@localhost:5432/employees"
    oidc_issuer: str = "https://auth.localhost/realms/securehr"
    oidc_jwks_url: str = "http://keycloak:8080/realms/securehr/protocol/openid-connect/certs"
    oidc_audience: str = "securehr-portal"
    cors_origins: list[str] = ["https://portal.localhost"]
    # Read-only LDAP account used to check whether an employee is an HR admin (app/hr_lookup.py).
    ldap_url: str = "ldap://ldap:389"
    ldap_bind_dn: str = "cn=readonly,dc=securehr,dc=local"
    ldap_bind_password: str = ""          # empty = not configured: salary changes are refused (fails closed)
    ldap_people_dn: str = "ou=people,dc=securehr,dc=local"
    ldap_hr_group_dn: str = "cn=hr-admins,ou=groups,dc=securehr,dc=local"


settings = Settings()
