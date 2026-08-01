"""Auth route registration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI


if TYPE_CHECKING:
    from .components import AuthComponents


def register_auth_views(
    app: FastAPI,
    auth: "AuthComponents",
) -> None:
    """Register all auth-related routes on the FastAPI app."""
    config = auth.config

    # /auth/v1/jwt/login + /auth/v1/jwt/logout
    app.include_router(
        auth.fastapi_users.get_auth_router(
            auth.jwt_auth_backend,
            requires_verification=config.require_verified,
        ),
        prefix=f"{config.url_prefix}/jwt",
        tags=["auth"],
    )

    # /auth/v1/cookie/login + /auth/v1/cookie/logout
    app.include_router(
        auth.fastapi_users.get_auth_router(
            auth.cookie_auth_backend,
            requires_verification=config.require_verified,
        ),
        prefix=f"{config.url_prefix}/cookie",
        tags=["auth"],
    )

    # /auth/v1/register (optional)
    if config.allow_registration:
        app.include_router(
            auth.fastapi_users.get_register_router(
                auth.user_read_schema, auth.user_create_schema
            ),
            prefix=config.url_prefix,
            tags=["auth"],
        )

    # /auth/v1/forgot-password + /auth/v1/reset-password
    app.include_router(
        auth.fastapi_users.get_reset_password_router(),
        prefix=config.url_prefix,
        tags=["auth"],
    )

    # /auth/v1/request-verify-token + /auth/v1/verify
    app.include_router(
        auth.fastapi_users.get_verify_router(auth.user_read_schema),
        prefix=config.url_prefix,
        tags=["auth"],
    )

    # /auth/v1/users/me
    app.include_router(
        auth.fastapi_users.get_users_router(
            auth.user_read_schema, auth.user_update_schema
        ),
        prefix=f"{config.url_prefix}/users",
        tags=["users"],
    )

    # OIDC provider routes
    for provider_config in auth.oidc_providers or []:
        oauth_backend = auth.get_oidc_backend(provider_config.name)
        oauth_client = auth.get_oidc_client(provider_config.name)
        if oauth_backend and oauth_client:
            app.include_router(
                auth.fastapi_users.get_oauth_router(
                    oauth_client,
                    oauth_backend,
                    config.secret_key,
                    associate_by_email=provider_config.associate_by_email,
                    is_verified_by_default=provider_config.is_verified_by_default,
                ),
                prefix=f"{config.url_prefix}/{provider_config.name}",
                tags=["auth"],
            )
