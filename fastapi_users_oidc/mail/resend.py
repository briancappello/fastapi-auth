from __future__ import annotations

from typing import TYPE_CHECKING


try:
    import resend
except (ImportError, ModuleNotFoundError):
    resend = None


if TYPE_CHECKING:
    from . import Email, MailSender


class Resend:
    """
    Send emails with https://resend.com

    Requires: pip install fastapi-users-oidc[resend]
    """

    def __init__(self, api_key: str):
        if resend is None:
            raise RuntimeError(
                "Please install the resend library: "
                "pip install fastapi-users-oidc[resend]"
            )

        resend.api_key = api_key

    async def send_message(self, message: "Email") -> None:
        message.template_context = None
        d = message.model_dump(mode="json", by_alias=True)
        resend.Emails.send(
            {
                "from": d["from"],
                "to": d["recipients"],
                "subject": d["subject"],
                "cc": d["cc"],
                "bcc": d["bcc"],
                "reply_to": d["reply_to"],
                "html": d["html"],
            }
        )
