"""AuthComponents -- the main entry point for configuring auth."""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    CookieTransport,
)

from .config import AuthConfig, OIDCProviderConfig
from .dependencies import (
    create_get_db_strategy,
    create_get_user_manager,
)
from .factories import db_strategy_factory, user_manager_factory
from .mail import MailConfig, configure_mail, set_app_config
from .user_manager import BaseAppUserManager


logger = logging.getLogger(__name__)

# Path to bundled templates
_LIBRARY_TEMPLATE_DIR = str(
    Path(__file__).parent / "templates"
)


class AuthComponents:
    """
    Configured auth component container. Created once per app.

    Example::

        from fastapi_users_oidc import AuthComponents, AuthConfig

        auth = AuthComponents(
            user_model=User,
            access_token_model=AccessToken,
            config=AuthConfig(secret_key="..."),
        )

        require_user = auth.create_require_user()
        fastapi_users = auth.fastapi_users
    """

    def __init__(
        self,
        *,
        user_model: type,
        access_token_model: type,
        config: AuthConfig,
        user_manager_class: type[BaseAppUserManager] | None = None,
        oauth_account_model: type | None = None,
        oidc_providers: list[OIDCProviderConfig] | None = None,
        mail_config: MailConfig | None = None,
        async_session_factory: Any = None,
        async_session_dep: Any = None,
        user_read_schema: type | None = None,
        user_create_schema: type | None = None,
        user_update_schema: type | None = None,
        app_config_getter: Any | None = None,
    ):
        self.user_model = user_model
        self.access_token_model = access_token_model
        self.config = config
        self.oauth_account_model = oauth_account_model
        self.oidc_providers = oidc_providers or []
        self.async_session_factory = async_session_factory
        self.user_read_schema = user_read_schema
        self.user_create_schema = user_create_schema
        self.user_update_schema = user_update_schema

        # Determine user manager class
        if user_manager_class:
            self._user_manager_class = user_manager_class
        elif self.oidc_providers:
            # Auto-create a class with OIDC mixin
            from .oidc.mixin import OIDCGroupSyncMixin

            self._user_manager_class = type(
                "OIDCUserManager",
                (OIDCGroupSyncMixin, BaseAppUserManager),
                {},
            )
        else:
            self._user_manager_class = BaseAppUserManager

        # Resolve the async_session DI dependency
        # If not provided, try to create one from the factory
        self._async_session_dep = async_session_dep

        # Configure mail if provided
        if mail_config:
            configure_mail(mail_config)

        # Configure app config getter for email templates
        if app_config_getter:
            set_app_config(app_config_getter)

        # Set up OIDC clients
        self._oidc_clients: dict[str, Any] = {}
        self._oidc_backends: dict[str, AuthenticationBackend] = {}
        self._setup_oidc()

    def _setup_oidc(self) -> None:
        """Initialize OIDC clients and auth backends."""
        if not self.oidc_providers:
            return

        from .oidc.client import configure_oidc_client
        from .oidc.transport import (
            BearerRedirectTransport,
            CookieRedirectTransport,
        )

        for provider in self.oidc_providers:
            client = configure_oidc_client(provider)
            if client is None:
                continue

            self._oidc_clients[provider.name] = client

            # Create transport based on config
            if provider.transport == "cookie":
                transport = CookieRedirectTransport(
                    redirect_url=provider.redirect_url,
                    cookie_max_age=self.config.token_lifetime_seconds,
                )
            else:
                transport = BearerRedirectTransport(
                    redirect_url=provider.redirect_url,
                    tokenUrl="",
                )

            backend = AuthenticationBackend(
                name=provider.name,
                transport=transport,
                get_strategy=create_get_db_strategy(
                    self._async_session_dep,
                    self.access_token_model,
                    self.config,
                ),
            )
            self._oidc_backends[provider.name] = backend

        # Inject OIDC config into the user manager class if it has
        # the mixin
        from .oidc.mixin import OIDCGroupSyncMixin

        if issubclass(self._user_manager_class, OIDCGroupSyncMixin):
            # Store as class-level defaults so instances get them
            self._user_manager_class.oidc_providers = {
                p.name: p for p in self.oidc_providers
            }
            self._user_manager_class.oidc_clients = self._oidc_clients

    # -- Auth backends ------------------------------------------------

    @cached_property
    def _get_db_strategy(self):
        return create_get_db_strategy(
            self._async_session_dep,
            self.access_token_model,
            self.config,
        )

    @cached_property
    def jwt_auth_backend(self) -> AuthenticationBackend:
        jwt_bearer_transport = BearerTransport(
            tokenUrl=f"{self.config.url_prefix.lstrip('/')}/jwt/login"
        )
        return AuthenticationBackend(
            name="jwt",
            transport=jwt_bearer_transport,
            get_strategy=self._get_db_strategy,
        )

    @cached_property
    def cookie_auth_backend(self) -> AuthenticationBackend:
        cookie_transport = CookieTransport(
            cookie_max_age=self.config.token_lifetime_seconds
        )
        return AuthenticationBackend(
            name="cookie",
            transport=cookie_transport,
            get_strategy=self._get_db_strategy,
        )

    @cached_property
    def _all_auth_backends(self) -> list[AuthenticationBackend]:
        backends = [self.jwt_auth_backend, self.cookie_auth_backend]
        backends.extend(self._oidc_backends.values())
        return backends

    @cached_property
    def _get_user_manager(self):
        return create_get_user_manager(
            self._async_session_dep,
            self.user_model,
            self.config,
            self._user_manager_class,
            self.oauth_account_model,
        )

    @cached_property
    def fastapi_users(self) -> FastAPIUsers:
        return FastAPIUsers(
            self._get_user_manager,
            auth_backends=self._all_auth_backends,
        )

    # -- Factories (bound to configured models) -----------------------

    def user_manager_factory(
        self,
        session,
        background_tasks: BackgroundTasks | None = None,
        send_emails: bool = True,
    ) -> BaseAppUserManager:
        return user_manager_factory(
            session,
            user_model=self.user_model,
            config=self.config,
            user_manager_class=self._user_manager_class,
            oauth_account_model=self.oauth_account_model,
            background_tasks=background_tasks,
            send_emails=send_emails,
        )

    def db_strategy_factory(self, session):
        return db_strategy_factory(
            session,
            access_token_model=self.access_token_model,
            config=self.config,
        )

    # -- Builders -----------------------------------------------------

    def create_require_user(self, user_model=None):
        """Create a ``require_user`` decorator."""
        from .require_user import create_require_user

        return create_require_user(
            self.fastapi_users,
            require_verified=self.config.require_verified,
            user_model=user_model or self.user_model,
        )

    def create_optional_user(self):
        """Create a ``get_user_optional`` dependency."""
        from .optional_user import create_optional_user_dependency

        return create_optional_user_dependency(
            self.async_session_factory,
            self.user_model,
            self.access_token_model,
        )

    def create_admin_auth(self):
        """Create an AdminAuth backend."""
        from .admin import AdminAuth

        return AdminAuth(
            secret_key=self.config.secret_key,
            auth_components=self,
        )

    def register_auth_views(self, app: FastAPI) -> None:
        """Register all auth routes on the FastAPI app."""
        from .router import register_auth_views

        register_auth_views(app, self)

    def create_user_cli(
        self,
        user_create_schema,
        user_read_schema,
        user_update_schema,
        user_model_manager_class,
    ):
        """Create CLI user management commands."""
        from .cli.users import create_user_commands

        return create_user_commands(
            auth_components=self,
            user_create_schema=user_create_schema,
            user_read_schema=user_read_schema,
            user_update_schema=user_update_schema,
            user_model_manager_class=user_model_manager_class,
        )

    # -- OIDC accessors -----------------------------------------------

    def get_oidc_client(self, name: str):
        """Get an OIDC client by provider name."""
        return self._oidc_clients.get(name)

    def get_oidc_backend(self, name: str):
        """Get an OIDC auth backend by provider name."""
        return self._oidc_backends.get(name)
