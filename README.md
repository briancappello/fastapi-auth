# fastapi-users-oidc

Shared auth layer built on [fastapi-users](https://fastapi-users.github.io/fastapi-users/) with OIDC provider support, mail, admin panel auth, CLI user management, and test utilities.

## Installation

```bash
# From private index
uv add fastapi-users-oidc

# Or as a local editable dependency (development)
# In pyproject.toml:
# [tool.uv.sources]
# fastapi-users-oidc = { path = "../fastapi-users-oidc", editable = true }
```

Optional extras:

```bash
uv add "fastapi-users-oidc[resend]"   # Resend email sender
```

---

## Usage Guide

### 1. Define your models

The library does **not** provide concrete SQLAlchemy models (because each app has its own `Base` class with its own registry/type mappings). You define your own `User`, `AccessToken`, and optionally `OAuthAccount` models as usual.

```python
# app/db/models/user.py
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTable

from .base import Base, Mapped, mapped_column, pk, relationship

class User(SQLAlchemyBaseUserTable[int], Base):
    id: Mapped[pk]
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_superuser: Mapped[bool] = mapped_column(default=False)
    is_verified: Mapped[bool] = mapped_column(default=False)
    first_name: Mapped[str]  # or Mapped[str | None] if optional
    last_name: Mapped[str]

    access_tokens: Mapped[list["AccessToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )
    # Add if using OIDC:
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin",
    )
```

```python
# app/db/models/access_token.py
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTable

from .base import Base, Mapped, mapped_column, relationship, ForeignKey

class AccessToken(SQLAlchemyBaseAccessTokenTable[int], Base):
    __tablename__ = "access_token"
    token: Mapped[str] = mapped_column(String(43), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="cascade"))
    user: Mapped["User"] = relationship(back_populates="access_tokens", lazy="selectin")
```

```python
# app/db/models/oauth_account.py (only if using OIDC)
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseOAuthAccountTable

from .base import Base, Mapped, mapped_column, pk, ForeignKey

class OAuthAccount(SQLAlchemyBaseOAuthAccountTable[int], Base):
    __tablename__ = "oauth_account"
    id: Mapped[pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="cascade"), nullable=False, index=True
    )
```

### 2. Define your schemas

```python
# app/schema/user.py
from fastapi_users.schemas import BaseUser, BaseUserCreate, BaseUserUpdate

class UserRead(BaseUser[int]):
    first_name: str
    last_name: str

class UserCreate(BaseUserCreate):
    first_name: str
    last_name: str

class UserUpdate(BaseUserUpdate):
    first_name: str | None = None
    last_name: str | None = None
```

### 3. Configure AuthComponents

This is the single entry point. Create one instance and everything flows from it.

```python
# app/auth/__init__.py
from fastapi_users_oidc import AuthComponents, AuthConfig, OIDCProviderConfig
from fastapi_users_oidc.mail import set_app_config

from app.config import Config
from app.db import async_session, async_session_factory
from app.db.models import AccessToken, User
from app.schema import UserCreate, UserRead, UserUpdate

# Allow email templates to access your app config
set_app_config(lambda: Config)

auth = AuthComponents(
    user_model=User,
    access_token_model=AccessToken,
    config=AuthConfig(
        secret_key=Config.SECRET_KEY,
        url_prefix="/auth/v1",
        require_verified=False,
        token_lifetime_seconds=7 * 24 * 60 * 60,
        allow_registration=True,
        site_name=Config.SITE_NAME,
        base_url=Config.BASE_URL,
    ),
    mail_config=Config.MAIL_CONFIG,
    async_session_factory=async_session_factory,
    async_session_dep=async_session,
    user_read_schema=UserRead,
    user_create_schema=UserCreate,
    user_update_schema=UserUpdate,
)

# Re-export commonly used objects
UserManager = auth._user_manager_class
fastapi_users = auth.fastapi_users
require_user = auth.create_require_user()
register_auth_views = auth.register_auth_views
user_manager_factory = auth.user_manager_factory
```

### 4. Register routes

```python
# app/main.py
from app.auth import register_auth_views

app = FastAPI()
register_auth_views(app)
```

This registers the following routes (at the configured `url_prefix`):

| Route                           | Method    | Description                             |
|---------------------------------|-----------|-----------------------------------------|
| `/auth/v1/jwt/login`            | POST      | Login, returns bearer token             |
| `/auth/v1/jwt/logout`           | POST      | Logout (invalidates token)              |
| `/auth/v1/cookie/login`         | POST      | Login, sets httpOnly cookie             |
| `/auth/v1/cookie/logout`        | POST      | Logout (clears cookie)                  |
| `/auth/v1/register`             | POST      | Register (if `allow_registration=True`) |
| `/auth/v1/forgot-password`      | POST      | Request password reset email            |
| `/auth/v1/reset-password`       | POST      | Reset password with token               |
| `/auth/v1/request-verify-token` | POST      | Request email verification              |
| `/auth/v1/verify`               | POST      | Verify email with token                 |
| `/auth/v1/users/me`             | GET/PATCH | Current user profile                    |

### 5. Protect routes with `@require_user`

```python
from app.auth import require_user
from app.db.models import User

@app.get("/protected")
@require_user
async def protected(user: User):
    return {"email": user.email}

@app.get("/admin")
@require_user(is_superuser=True)
async def admin_only(user: User):
    return {"admin": True}
```

### 6. Set up the admin panel

```python
# app/admin/__init__.py
from fastapi_users_oidc.admin import Admin
from app.auth import auth
from app.config import Config
from app.db import async_session_factory

admin = Admin(
    title=f"{Config.SITE_NAME} Admin",
    session_maker=async_session_factory,
    templates_dir=Config.TEMPLATE_DIR,
    authentication_backend=auth.create_admin_auth(),
)

def register_admin_views(app):
    admin.init_app(app)
    admin.add_view(YourModelAdmin)
```

### 7. Configure mail

```python
# app/config.py
from fastapi_users_oidc.mail import MailConfig

class Config:
    MAIL_CONFIG = MailConfig(
        MAIL_SERVER="localhost",
        MAIL_PORT=1025,
        MAIL_USERNAME="",
        MAIL_PASSWORD="",
        USE_CREDENTIALS=False,
        MAIL_FROM="app@example.com",
        MAIL_FROM_NAME="My App",
        MAIL_STARTTLS=False,
        MAIL_SSL_TLS=False,
        VALIDATE_CERTS=False,
        TEMPLATE_FOLDER="app/templates",  # your templates dir
    )
```

The library ships default email templates. To override, place templates with the same names in your app's template folder. Jinja2 will find your templates first.

Email templates handle nullable `first_name`/`last_name` gracefully -- they fall back to the user's email address.

### 8. CLI user management

```python
# app/cli/groups.py
from fastapi_users_oidc.cli import async_command, click

@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(ctx.command.get_command(ctx, "dev"))

@main.group()
def users():
    """User management."""
    pass
```

Then define commands using `async_command` and `user_manager_factory`:

```python
# app/cli/users.py
from fastapi_users_oidc.cli import async_command, click
from app.auth import user_manager_factory
from app.db import async_session_factory

@users.command()
@click.option("-e", "--email", required=True)
@async_command
async def create(email):
    async with async_session_factory() as session:
        um = user_manager_factory(session, send_emails=False)
        user = await um.create(UserCreate(email=email, ...))
```

The library's `cli` module is a drop-in replacement for `click` with enhanced help formatting, `-h` support, and argument documentation.

### 9. Testing

```python
# tests/conftest.py
from fastapi_users_oidc.testing import TestClient

@pytest.fixture
async def client(session):
    from httpx import ASGITransport
    app.dependency_overrides[async_session] = lambda: session
    test_client = TestClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        session=session,
        access_token_model=AccessToken,
    )
    async with test_client:
        yield test_client

# In tests:
async def test_protected(client, user):
    response = await client.with_user(user).get("/protected")
    assert response.status_code == 200
```

---

## Adding OIDC (Authentik, Keycloak, Auth0, etc.)

### 1. Create the `OAuthAccount` model

See model definition above. Run an Alembic migration to create the table.

### 2. Add the model to your `AuthComponents`

```python
from app.db.models import OAuthAccount

auth = AuthComponents(
    ...,
    oauth_account_model=OAuthAccount,
    oidc_providers=[
        OIDCProviderConfig(
            name="authentik",
            client_id=os.getenv("AUTHENTIK_CLIENT_ID"),
            client_secret=os.getenv("AUTHENTIK_CLIENT_SECRET"),
            openid_configuration_endpoint=os.getenv("AUTHENTIK_OPENID_CONFIGURATION_ENDPOINT"),
            scopes=["openid", "email", "profile", "groups"],
            superuser_group="superusers",  # Authentik group name -> is_superuser=True
            transport="bearer",            # or "cookie"
            redirect_url="/",              # where to redirect after callback
            csrf_cookie_secure=False,      # set True in production with HTTPS
        ),
    ],
)
```

### 3. This registers additional routes

| Route | Method | Description |
|-------|--------|-------------|
| `/auth/v1/authentik/authorize` | GET | Returns `{"authorization_url": "..."}` |
| `/auth/v1/authentik/callback` | GET | Handles provider redirect, logs user in |

### 4. Configure your OIDC provider

For **Authentik**:

1. Create an OAuth2/OIDC Provider in Authentik
2. Set the **Redirect URI** to: `https://your-app.com/api/auth/v1/authentik/callback`
3. Under Scopes, ensure `openid`, `email`, `profile` are granted
4. To sync groups: add a `groups` scope or configure the userinfo endpoint to include the `groups` claim
5. Set the `openid_configuration_endpoint` env var to: `https://authentik.example.com/application/o/<app-slug>/.well-known/openid-configuration`

### 5. Transport modes

| Mode | Behavior | Use case |
|------|----------|----------|
| `"cookie"` | Sets httpOnly cookie, redirects to `redirect_url` | Server-rendered or cookie-based SPAs |
| `"bearer"` | Redirects to `redirect_url#access_token=<token>` | Bearer-token SPAs (read token from URL fragment) |

### 6. Group-to-role sync

On each OIDC login, the library:
- Fetches the user's profile from the provider's userinfo endpoint
- Checks if `superuser_group` is in the `groups` claim
- Sets `is_superuser` accordingly
- Marks the user as `is_verified=True` (provider verified the email)
- Populates `first_name`/`last_name` from `given_name`/`family_name` claims if not already set

### 7. Graceful degradation

If the OIDC env vars are empty/missing, no OIDC routes are registered. The app falls back to email/password login only. This means OIDC is optional -- the library and app function normally without it.

---

## AuthConfig reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `secret_key` | `str` | required | Used for token signing and admin session encryption |
| `url_prefix` | `str` | `/auth/v1` | Prefix for all auth routes |
| `require_verified` | `bool` | `False` | Require email verification for login |
| `token_lifetime_seconds` | `int` | `604800` (7d) | Database token TTL |
| `allow_registration` | `bool` | `True` | Enable/disable the register endpoint |
| `site_name` | `str` | `"App"` | Used in email templates |
| `base_url` | `str` | `http://localhost:8000` | Used in email templates for links |

## OIDCProviderConfig reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | URL slug and `oauth_name` in DB |
| `client_id` | `str` | required | OAuth2 client ID |
| `client_secret` | `str` | required | OAuth2 client secret |
| `openid_configuration_endpoint` | `str` | required | Provider's `.well-known/openid-configuration` URL |
| `scopes` | `list[str]` | `["openid", "email", "profile"]` | OAuth2 scopes to request |
| `superuser_group` | `str \| None` | `None` | Group name that maps to `is_superuser=True` |
| `transport` | `str` | `"cookie"` | `"cookie"` or `"bearer"` |
| `redirect_url` | `str` | `"/"` | Where to redirect after callback |
| `is_verified_by_default` | `bool` | `True` | Mark OIDC users as verified |
| `associate_by_email` | `bool` | `True` | Link to existing user by email |
| `csrf_cookie_secure` | `bool` | `True` | CSRF cookie Secure flag (set `False` for local HTTP dev) |

---

## Development

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
cd fastapi-users-oidc
uv venv
uv pip install -e ".[dev]"
```

### Project structure

```
fastapi_users_oidc/
    __init__.py           # Public API exports
    config.py             # AuthConfig, OIDCProviderConfig dataclasses
    components.py         # AuthComponents -- the main entry point
    user_manager.py       # BaseAppUserManager (lifecycle hooks, email sending)
    require_user.py       # create_require_user() factory
    optional_user.py      # create_optional_user_dependency()
    factories.py          # DB/strategy factory functions
    dependencies.py       # FastAPI DI generator factories
    router.py             # register_auth_views() logic
    admin/
        __init__.py       # AdminAuth + Admin (sqladmin integration)
    oidc/
        __init__.py
        client.py         # OpenID client instantiation
        transport.py      # CookieRedirectTransport, BearerRedirectTransport
        mixin.py          # OIDCGroupSyncMixin (role sync from provider groups)
    mail/
        __init__.py       # Email schema, MailConfig, FastMail, MailSender
        resend.py         # Resend.com sender (optional dep)
    cli/
        __init__.py       # Enhanced click module (drop-in replacement)
        users.py          # CLI user command factory
    testing/
        __init__.py       # TestClient with with_user() helper
    templates/
        email/            # Default Jinja2 email templates
```

### Key design decisions

- **Models are NOT provided** -- each consuming app defines its own models with its own `Base` class. This avoids SQLAlchemy registry/metadata conflicts.
- **`AuthComponents`** is a configured container. All factories, DI generators, and route registration are methods on this class. Consuming apps create one instance and derive everything from it.
- **No module-level imports of app code** -- the library never does `from app.config import Config`. Configuration is injected via `AuthConfig`, `MailConfig`, and `set_app_config()`.
- **OIDC is opt-in** -- if no `oidc_providers` are passed (or env vars are empty), OIDC routes are not registered. The library functions as a pure email/password auth layer.
- **`require_user` is a factory** -- it takes a `FastAPIUsers` instance and `user_model` as parameters, avoiding the old pattern of importing a module-level singleton.

### Running tests

```bash
uv run pytest
```

Note: integration tests require a running PostgreSQL instance. The test database is configured via environment or defaults to `{SQL_DB_NAME}_test`.

### Linting / formatting

```bash
uv run ruff check .
uv run ruff format .
```

### Publishing

The package is published to a private index. Build with:

```bash
uv build
```

Then upload the wheel/sdist to your private index.

### Consuming as a local editable dep

In consuming apps' `pyproject.toml`:

```toml
[project]
dependencies = [
    "fastapi-users-oidc",
    # ... other deps
]

[tool.uv.sources]
fastapi-users-oidc = { path = "../fastapi-users-oidc", editable = true }
```

Then `uv sync` will install it from the local path.
