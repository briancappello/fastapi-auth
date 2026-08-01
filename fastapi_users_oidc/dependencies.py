"""
FastAPI dependency injection generators.

These are created dynamically by AuthComponents and bound to the
configured models/config. They are not used directly.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from fastapi import BackgroundTasks, Depends
from fastapi_users.authentication.strategy import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyAccessTokenDatabase,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .config import AuthConfig
from .factories import (
    access_token_db_factory,
    db_strategy_factory,
    user_db_factory,
    user_manager_factory,
)
from .user_manager import BaseAppUserManager


def create_get_user_db(
    async_session_dep,
    user_model: type,
    oauth_account_model: type | None = None,
):
    """Create a get_user_db DI generator."""

    async def get_user_db(
        session: AsyncSession = Depends(async_session_dep),
    ) -> AsyncGenerator[SQLAlchemyUserDatabase, None]:
        yield user_db_factory(session, user_model, oauth_account_model)

    return get_user_db


def create_get_access_token_db(
    async_session_dep,
    access_token_model: type,
):
    """Create a get_access_token_db DI generator."""

    async def get_access_token_db(
        session: AsyncSession = Depends(async_session_dep),
    ) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase, None]:
        yield access_token_db_factory(session, access_token_model)

    return get_access_token_db


def create_get_user_manager(
    async_session_dep,
    user_model: type,
    config: AuthConfig,
    user_manager_class: type[BaseAppUserManager],
    oauth_account_model: type | None = None,
    extra_kwargs: dict[str, Any] | None = None,
):
    """Create a get_user_manager DI generator."""

    async def get_user_manager(
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(async_session_dep),
    ) -> AsyncGenerator[BaseAppUserManager, None]:
        yield user_manager_factory(
            session,
            user_model=user_model,
            config=config,
            user_manager_class=user_manager_class,
            oauth_account_model=oauth_account_model,
            background_tasks=background_tasks,
            extra_kwargs=extra_kwargs,
        )

    return get_user_manager


def create_get_db_strategy(
    async_session_dep,
    access_token_model: type,
    config: AuthConfig,
):
    """Create a get_db_strategy DI generator."""

    async def get_db_strategy(
        session: AsyncSession = Depends(async_session_dep),
    ) -> DatabaseStrategy:
        return db_strategy_factory(
            session,
            access_token_model=access_token_model,
            config=config,
        )

    return get_db_strategy
