"""OIDC group sync mixin for UserManager."""

from __future__ import annotations

import logging

from typing import Any

from httpx_oauth.clients.openid import OpenID

from ..config import OIDCProviderConfig


logger = logging.getLogger(__name__)


class OIDCGroupSyncMixin:
    """
    Mixin for UserManager that syncs OIDC provider groups to local roles.

    Add to your UserManager class BEFORE BaseAppUserManager in MRO::

        class UserManager(OIDCGroupSyncMixin, BaseAppUserManager):
            pass

    Requires ``oidc_providers`` and ``oidc_clients`` to be set
    (done automatically by AuthComponents).
    """

    oidc_providers: dict[str, OIDCProviderConfig]
    oidc_clients: dict[str, OpenID]

    async def oauth_callback(
        self,
        oauth_name: str,
        access_token: str,
        account_id: str,
        account_email: str,
        expires_at: int | None = None,
        refresh_token: str | None = None,
        request: Any = None,
        *,
        associate_by_email: bool = False,
        is_verified_by_default: bool = False,
    ) -> Any:
        user = await super().oauth_callback(  # type: ignore[misc]
            oauth_name,
            access_token,
            account_id,
            account_email,
            expires_at=expires_at,
            refresh_token=refresh_token,
            request=request,
            associate_by_email=associate_by_email,
            is_verified_by_default=is_verified_by_default,
        )
        await self._sync_oidc_roles(user, access_token, oauth_name)
        return user

    async def _sync_oidc_roles(
        self,
        user: Any,
        access_token: str,
        oauth_name: str,
    ) -> None:
        """Sync roles/attributes from OIDC provider profile."""
        provider_config = self.oidc_providers.get(oauth_name)
        if not provider_config:
            return

        client = self.oidc_clients.get(oauth_name)
        if not client:
            return

        try:
            profile = await client.get_profile(access_token)
            updates = {}

            # Sync superuser status from group membership
            if provider_config.superuser_group:
                groups = profile.get("groups", [])
                should_be_super = (
                    provider_config.superuser_group in groups
                )
                if user.is_superuser != should_be_super:
                    updates["is_superuser"] = should_be_super

            # Mark as verified (OIDC provider has verified the email)
            if not user.is_verified:
                updates["is_verified"] = True

            # Sync name from OIDC claims if not set locally
            if (
                hasattr(user, "first_name")
                and not user.first_name
                and profile.get("given_name")
            ):
                updates["first_name"] = profile["given_name"]
            if (
                hasattr(user, "last_name")
                and not user.last_name
                and profile.get("family_name")
            ):
                updates["last_name"] = profile["family_name"]

            if updates:
                await self.user_db.update(user, updates)  # type: ignore[attr-defined]

        except Exception:
            logger.exception(
                "Failed to sync OIDC roles for user %s from provider %s",
                user.id,
                oauth_name,
            )
