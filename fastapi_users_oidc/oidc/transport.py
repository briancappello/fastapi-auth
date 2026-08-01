"""Custom transports for OIDC callback responses."""

from urllib.parse import quote

from fastapi.responses import RedirectResponse
from fastapi_users.authentication import BearerTransport, CookieTransport
from starlette.responses import Response


class CookieRedirectTransport(CookieTransport):
    """
    Sets an httpOnly auth cookie then redirects to a frontend URL.

    Used for OIDC callbacks where the frontend uses cookie-based auth.
    After the callback completes, the user is redirected to the app
    (already authenticated via the cookie).
    """

    def __init__(self, redirect_url: str = "/", **kwargs):
        super().__init__(**kwargs)
        self._redirect_url = redirect_url

    async def get_login_response(self, token: str) -> Response:
        response = RedirectResponse(
            self._redirect_url, status_code=302
        )
        response.set_cookie(
            self.cookie_name,
            token,
            max_age=self.cookie_max_age,
            path=self.cookie_path,
            domain=self.cookie_domain,
            secure=self.cookie_secure,
            httponly=self.cookie_httponly,
            samesite=self.cookie_samesite,
        )
        return response


class BearerRedirectTransport(BearerTransport):
    """
    Redirects to a frontend URL with the token in a URL fragment.

    Used for OIDC callbacks where the frontend uses bearer token auth.
    The token is placed in the URL fragment (not query string) so it
    is not sent to the server. The frontend reads it from
    ``window.location.hash`` on load.

    Example redirect: ``/#access_token=<token>``
    """

    def __init__(self, redirect_url: str = "/", **kwargs):
        super().__init__(**kwargs)
        self._redirect_url = redirect_url

    async def get_login_response(self, token: str) -> Response:
        separator = "&" if "#" in self._redirect_url else "#"
        url = (
            f"{self._redirect_url}{separator}"
            f"access_token={quote(token, safe='')}"
        )
        return RedirectResponse(url, status_code=302)
