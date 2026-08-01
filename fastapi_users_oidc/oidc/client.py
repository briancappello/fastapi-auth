"""OIDC client setup."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING

from httpx_oauth.clients.openid import OpenID


if TYPE_CHECKING:
    from ..config import OIDCProviderConfig


logger = logging.getLogger(__name__)


def configure_oidc_client(
    provider: "OIDCProviderConfig",
) -> OpenID | None:
    """
    Create an OpenID client for the given provider config.

    Returns None if the provider config is incomplete.
    """
    if not all(
        [
            provider.client_id,
            provider.client_secret,
            provider.openid_configuration_endpoint,
        ]
    ):
        logger.warning(
            "OIDC provider %r is missing required config "
            "(client_id, client_secret, or discovery endpoint). "
            "Skipping.",
            provider.name,
        )
        return None

    return OpenID(
        client_id=provider.client_id,
        client_secret=provider.client_secret,
        openid_configuration_endpoint=provider.openid_configuration_endpoint,
        base_scopes=provider.scopes,
    )
