from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks
from fastapi_users.authentication.strategy import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyAccessTokenDatabase,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .config import AuthConfig
from .user_manager import BaseAppUserManager


def user_db_factory(
    session: AsyncSession,
    user_model: type,
    oauth_account_model: type | None = None,
) -> SQLAlchemyUserDatabase:
    if oauth_account_model:
        return SQLAlchemyUserDatabase(
            session, user_model, oauth_account_model
        )
    return SQLAlchemyUserDatabase(session, user_model)


def access_token_db_factory(
    session: AsyncSession,
    access_token_model: type,
) -> SQLAlchemyAccessTokenDatabase:
    return SQLAlchemyAccessTokenDatabase(session, access_token_model)


def user_manager_factory(
    session: AsyncSession,
    *,
    user_model: type,
    config: AuthConfig,
    user_manager_class: type[BaseAppUserManager] = BaseAppUserManager,
    oauth_account_model: type | None = None,
    background_tasks: BackgroundTasks | None = None,
    send_emails: bool = True,
    extra_kwargs: dict[str, Any] | None = None,
) -> BaseAppUserManager:
    user_db = user_db_factory(
        session, user_model, oauth_account_model
    )
    kwargs = dict(
        user_db=user_db,
        config=config,
        background_tasks=background_tasks,
        send_emails=send_emails,
    )
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    return user_manager_class(**kwargs)


def db_strategy_factory(
    session: AsyncSession,
    *,
    access_token_model: type,
    config: AuthConfig,
) -> DatabaseStrategy:
    return DatabaseStrategy(
        access_token_db_factory(session, access_token_model),
        lifetime_seconds=config.token_lifetime_seconds,
    )
