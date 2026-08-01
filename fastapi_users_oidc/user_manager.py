from inspect import isawaitable
from typing import Any, Callable

from fastapi import BackgroundTasks, Request
from fastapi_users import BaseUserManager, IntegerIDMixin
from fastapi_users.db import BaseUserDatabase
from fastapi_users.password import PasswordHelperProtocol

from .config import AuthConfig
from .mail import Email, get_fast_mail


class BaseAppUserManager(IntegerIDMixin, BaseUserManager[Any, int]):
    """
    Base user manager with email lifecycle hooks.

    Subclass in your app to customize email templates/subjects
    or add app-specific hooks.
    """

    def __init__(
        self,
        *,
        user_db: BaseUserDatabase[Any, int],
        config: AuthConfig,
        password_helper: PasswordHelperProtocol | None = None,
        background_tasks: BackgroundTasks | None = None,
        send_emails: bool = True,
    ):
        super().__init__(user_db=user_db, password_helper=password_helper)
        self.config = config
        self.reset_password_token_secret = config.secret_key
        self.verification_token_secret = config.secret_key
        self.background_tasks: BackgroundTasks | None = background_tasks
        self.send_emails = send_emails

    async def in_background(self, fn: Callable, *args, **kwargs) -> None:
        if self.background_tasks:
            self.background_tasks.add_task(fn, *args, **kwargs)
        else:
            r = fn(*args, **kwargs)
            if isawaitable(r):
                await r

    async def send_email(
        self,
        message: Email,
        request: Request | None = None,
    ) -> None:
        if not self.send_emails:
            return

        message.template_context["base_url"] = (
            str(request.base_url).rstrip("/")
            if request
            else self.config.base_url
        )
        await self.in_background(get_fast_mail().send_message, message)

    async def on_after_register(
        self,
        user: Any,
        request: Request | None = None,
    ) -> None:
        await self.send_email(
            Email(
                subject=f"Welcome to {self.config.site_name}",
                recipients=[user.email],
                template="email/user-registered.html",
                template_context={
                    "user": user,
                },
            ),
            request,
        )
        if not user.is_verified:
            await self.request_verify(user, request)

    async def on_after_request_verify(
        self,
        user: Any,
        token: str,
        request: Request | None = None,
    ) -> None:
        await self.send_email(
            Email(
                subject="Verify Your Email Address",
                recipients=[user.email],
                template="email/user-request-verify.html",
                template_context={
                    "user": user,
                    "token": token,
                },
            ),
            request,
        )

    async def on_after_forgot_password(
        self,
        user: Any,
        token: str,
        request: Request | None = None,
    ) -> None:
        await self.send_email(
            Email(
                subject="Forgot Password Request",
                recipients=[user.email],
                template="email/user-forgot-password.html",
                template_context={
                    "user": user,
                    "token": token,
                },
            ),
            request,
        )

    async def on_after_update(
        self,
        user: Any,
        update_dict: dict,
        request: Request | None = None,
    ) -> None:
        if "password" in update_dict:
            await self.send_email(
                Email(
                    subject="Your Password Has Been Changed",
                    recipients=[user.email],
                    template="email/user-password-changed.html",
                    template_context={
                        "user": user,
                    },
                ),
                request,
            )
