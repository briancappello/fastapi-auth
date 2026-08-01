"""
fastapi-users-oidc -- Shared fastapi-users auth layer with OIDC support.
"""

from .components import AuthComponents
from .config import AuthConfig, OIDCProviderConfig
from .mail import (
    Email,
    FastMail,
    MailConfig,
    MailSender,
    configure_mail,
    get_fast_mail,
    set_app_config,
)
from .user_manager import BaseAppUserManager


__all__ = [
    "AuthComponents",
    "AuthConfig",
    "BaseAppUserManager",
    "Email",
    "FastMail",
    "MailConfig",
    "MailSender",
    "OIDCProviderConfig",
    "configure_mail",
    "get_fast_mail",
    "set_app_config",
]
