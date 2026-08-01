from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select


def create_optional_user_dependency(
    async_session_factory,
    user_model: type,
    access_token_model: type,
):
    """
    Create a ``get_user_optional`` FastAPI dependency that resolves the
    current user from a Bearer token without requiring authentication.

    Returns None if no valid token is present.

    Usage::

        get_user_optional = create_optional_user_dependency(
            async_session_factory, User, AccessToken,
        )

        @app.get("/page/{slug}")
        async def get_page(
            slug: str,
            user: User | None = Depends(get_user_optional),
        ):
            ...
    """

    async def get_user_optional(request: Request) -> Any | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        async with async_session_factory() as session:
            result = await session.execute(
                select(access_token_model).where(
                    access_token_model.token == token
                )
            )
            access_token = result.scalar_one_or_none()
            if not access_token:
                return None
            user = access_token.user
            if not user.is_active:
                return None
            return user

    return get_user_optional
