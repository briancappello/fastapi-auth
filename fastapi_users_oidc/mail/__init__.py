from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable

from fastapi_mail import ConnectionConfig as BaseConnectionConfig
from fastapi_mail import FastMail as BaseFastMail
from fastapi_mail import MessageSchema as BaseMessageSchema
from fastapi_mail import MessageType
from pydantic import ConfigDict, Field, NameEmail, field_validator


try:
    from .resend import Resend
except (ImportError, ModuleNotFoundError):
    Resend = None  # type: ignore[assignment,misc]


# App config injector -- set by the consuming app via set_app_config()
_app_config_getter: Callable[[], Any] | None = None


def set_app_config(getter: Callable[[], Any]) -> None:
    """
    Register a callable that returns the app's Config class.

    This is called during app startup so that email templates
    can access app config values (e.g. SITE_NAME, BASE_URL).

    Example::

        from fastapi_users_oidc.mail import set_app_config
        set_app_config(lambda: Config)
    """
    global _app_config_getter
    _app_config_getter = getter


def get_app_config(copy: bool = False) -> Any:
    """
    Get the app config class. Returns None if not configured.
    """
    if _app_config_getter is None:
        return None

    config = _app_config_getter()

    if copy and config is not None:

        def copy_class(klass):
            return type(
                f"{klass.__name__}Copy",
                tuple(klass.__mro__[1:]),
                dict(klass.__dict__),
            )

        return copy_class(config)

    return config


class Email(BaseMessageSchema):
    """Pydantic schema for email messages."""

    model_config = ConfigDict(validate_by_name=True)

    recipients: list[str]
    subject: str
    template: str
    template_context: dict | None = Field(default_factory=dict)
    cc: list[str] | str = Field(default_factory=list)
    bcc: list[str] | str = Field(default_factory=list)
    reply_to: list[NameEmail | str] = Field(default_factory=list)

    # automatic defaults
    subtype: MessageType = MessageType.html

    # dump only; use from_email for input optionally with from_name
    # (if unspecified, uses defaults defined on MailConfig)
    sender: str | None = Field(alias="from", default=None)

    # dump only; stores the rendered template
    template_body: str | None = Field(alias="html", default=None)

    @field_validator("template_context", mode="after")
    @classmethod
    def add_app_config_to_template_context(
        cls, ctx: dict | None
    ) -> dict | None:
        if ctx is None:
            return None

        ctx.setdefault("now", datetime.now(timezone.utc))
        app_config = get_app_config(copy=True)
        if app_config is not None:
            ctx.setdefault("AppConfig", app_config)
        return ctx


class MailSender:
    """
    Abstract interface for custom email sending backends.
    """

    async def send_message(self, message: Email) -> None:
        raise NotImplementedError


class MailConfig(BaseConnectionConfig):
    """
    Configuration for FastMail. If MAIL_SENDER is defined, uses that
    backend instead of SMTP.
    """

    MAIL_SENDER: MailSender | None = None
    ADMIN_CONTACT_EMAIL: str | None = None


class FastMail(BaseFastMail):
    """Extended FastMail with pluggable sender support."""

    def __init__(self, config: MailConfig):
        super().__init__(config)

    async def send_message(self, message: Email) -> None:
        await self.send_messages(messages=[message])

    async def send_messages(self, messages: list[Email]) -> None:
        template_env = self.config.template_engine()
        for message in messages:
            template = template_env.get_template(message.template)
            message.template_body = template.render(
                **message.template_context
            )

        if self.config.MAIL_SENDER:
            for message in messages:
                message.sender = await self._FastMail__sender(message)
                await self.config.MAIL_SENDER.send_message(message)
        else:
            prepared_messages = []
            for message in messages:
                prepared_messages.append(
                    await self._FastMail__prepare_message(message)
                )

            await self._FastMail__send_prepared_messages(prepared_messages)


_fast_mail_instance: FastMail | None = None
_mail_config: MailConfig | None = None


def configure_mail(config: MailConfig) -> None:
    """Set the mail configuration. Must be called before get_fast_mail()."""
    global _mail_config, _fast_mail_instance
    _mail_config = config
    _fast_mail_instance = None  # reset cached instance


@lru_cache
def get_fast_mail() -> FastMail:
    """Get the singleton FastMail instance."""
    if _mail_config is None:
        raise RuntimeError(
            "Mail not configured. Call configure_mail() first, "
            "or pass mail_config to AuthComponents."
        )
    return FastMail(_mail_config)


__all__ = [
    "Email",
    "FastMail",
    "MailConfig",
    "MailSender",
    "Resend",
    "configure_mail",
    "get_app_config",
    "get_fast_mail",
    "set_app_config",
]
