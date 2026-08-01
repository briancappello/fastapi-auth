from dataclasses import dataclass, field


@dataclass
class AuthConfig:
    """Configuration for the auth layer."""

    secret_key: str
    url_prefix: str = "/auth/v1"
    require_verified: bool = False
    token_lifetime_seconds: int = 7 * 24 * 60 * 60  # 7 days
    allow_registration: bool = True
    site_name: str = "App"
    base_url: str = "http://localhost:8000"


@dataclass
class OIDCProviderConfig:
    """Configuration for an OIDC provider (e.g. Authentik, Keycloak)."""

    name: str
    client_id: str
    client_secret: str
    openid_configuration_endpoint: str
    scopes: list[str] = field(
        default_factory=lambda: ["openid", "email", "profile"]
    )
    superuser_group: str | None = None
    transport: str = "cookie"  # "cookie" or "bearer"
    redirect_url: str = "/"
    is_verified_by_default: bool = True
    associate_by_email: bool = True
    csrf_cookie_secure: bool = True
