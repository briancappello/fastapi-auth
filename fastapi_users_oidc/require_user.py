import functools
import inspect

from fastapi import Depends


def create_require_user(
    fastapi_users_instance,
    *,
    require_verified: bool = False,
    user_model: type,
):
    """
    Create a ``require_user`` decorator bound to a FastAPIUsers instance.

    Usage::

        require_user = create_require_user(
            fastapi_users, require_verified=False, user_model=User,
        )

        @app.get("/protected")
        @require_user
        async def protected(user: User):
            return {"email": user.email}

        @app.get("/admin")
        @require_user(is_superuser=True)
        async def admin_only(user: User):
            return {"admin": True}
    """

    def require_user(
        func=None,
        *,
        is_active: bool = True,
        is_superuser: bool = False,
    ):
        """
        Authorization required decorator for views.

        If the decorated view has an arg/kwarg with a type annotation
        of the User model, the current user will be injected
        automatically.

        Raises 401 if no user, or 403 if insufficient permissions.
        """

        def decorator(func_inner):
            dependency = fastapi_users_instance.current_user(
                active=is_active,
                verified=require_verified,
                superuser=is_superuser,
            )

            @functools.wraps(func_inner)
            async def wrapper(*args, **kwargs):
                # Consume the injected dependency
                user_obj = kwargs.pop("__auth_user", None)

                # Inject user into arguments if expected
                sig = inspect.signature(func_inner)
                for name, param in sig.parameters.items():
                    if param.annotation == user_model:
                        kwargs[name] = user_obj
                        break

                if inspect.iscoroutinefunction(func_inner):
                    return await func_inner(*args, **kwargs)
                return func_inner(*args, **kwargs)

            sig = inspect.signature(func_inner)
            params = list(sig.parameters.values())

            # Remove parameters annotated with User from the wrapper
            # signature so FastAPI doesn't try to resolve them as
            # query/body parameters
            params = [
                p for p in params if p.annotation != user_model
            ]

            # Create a new parameter for the dependency
            new_param = inspect.Parameter(
                "__auth_user",
                inspect.Parameter.KEYWORD_ONLY,
                default=Depends(dependency),
                annotation=user_model,
            )

            # Add the new parameter to the signature
            new_params = params + [new_param]
            new_sig = sig.replace(parameters=new_params)
            wrapper.__signature__ = new_sig

            return wrapper

        if func:
            return decorator(func)

        return decorator

    return require_user
