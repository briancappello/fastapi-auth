from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from fastapi import FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.router.common import ErrorCode
from sqladmin import Admin as BaseAdmin
from sqladmin._types import ENGINE_TYPE
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import sessionmaker
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request


if TYPE_CHECKING:
    from ..components import AuthComponents


class AdminAuth(AuthenticationBackend):
    """
    sqladmin AuthenticationBackend using fastapi-users.

    Requires superuser + is_active. Optionally requires is_verified.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        auth_components: "AuthComponents",
    ):
        super().__init__(secret_key=secret_key)
        self._auth = auth_components

    async def login(self, request: Request) -> bool:
        form = await request.form()
        async with self._auth.async_session_factory() as session:
            user_manager = self._auth.user_manager_factory(session)
            user = await user_manager.authenticate(
                OAuth2PasswordRequestForm(
                    username=form["username"],
                    password=form["password"],
                )
            )

            if user is None:
                return False

            if not all([user.is_active, user.is_superuser]):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="forbidden",
                )

            if (
                self._auth.config.require_verified
                and not user.is_verified
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ErrorCode.LOGIN_USER_NOT_VERIFIED,
                )

            from ..factories import db_strategy_factory

            db_strategy = db_strategy_factory(
                session,
                access_token_model=self._auth.access_token_model,
                config=self._auth.config,
            )
            token = await db_strategy.write_token(user)
            request.session.update({"token": token})
            return True

    async def authenticate(self, request: Request) -> bool:
        user, token = await self._authenticate_request(request)
        return bool(user) and bool(token)

    async def logout(self, request: Request) -> bool:
        await self._authenticate_request(request, logout=True)
        request.session.clear()
        return True

    async def _authenticate_request(
        self,
        request: Request,
        logout: bool = False,
    ) -> tuple:
        """Validate request token, optionally logging out the user."""
        token = request.session.get("token")
        if not token:
            return None, None

        async with self._auth.async_session_factory() as session:
            from ..factories import db_strategy_factory, user_manager_factory

            db_strategy = db_strategy_factory(
                session,
                access_token_model=self._auth.access_token_model,
                config=self._auth.config,
            )
            user_manager = self._auth.user_manager_factory(session)

            user, token = (
                await self._auth.fastapi_users.authenticator._authenticate(
                    user_manager=user_manager,
                    strategy_jwt=db_strategy,
                    jwt=token,
                    active=True,
                    verified=self._auth.config.require_verified,
                    superuser=True,
                )
            )

            if logout:
                await db_strategy.destroy_token(token, user)
                return user, None

            return user, token


class Admin(BaseAdmin):
    """
    Admin subclass supporting the init_app() factory pattern.

    Allows creating the Admin instance before the FastAPI app exists,
    then mounting it later via init_app().
    """

    def __init__(
        self,
        app: Starlette | None = None,
        engine: ENGINE_TYPE | None = None,
        session_maker: sessionmaker | async_sessionmaker | None = None,
        base_url: str = "/admin",
        title: str = "Admin",
        logo_url: str | None = None,
        favicon_url: str | None = None,
        middlewares: Sequence[Middleware] | None = None,
        debug: bool = False,
        templates_dir: str = "templates",
        authentication_backend: AuthenticationBackend | None = None,
    ) -> None:
        # fake app to allow using the application factory pattern
        class FakeNoopApp(Starlette):
            def mount(self, *args, **kwargs):
                pass

        super().__init__(
            app=app or FakeNoopApp(),
            engine=engine,
            session_maker=session_maker,
            base_url=base_url,
            title=title,
            logo_url=logo_url,
            favicon_url=favicon_url,
            middlewares=middlewares,
            debug=debug,
            templates_dir=templates_dir,
            authentication_backend=authentication_backend,
        )

    def init_app(self, app: FastAPI):
        self.app = app
        self.app.mount(
            self.base_url, app=self.admin, name="admin"
        )


__all__ = [
    "Admin",
    "AdminAuth",
]
