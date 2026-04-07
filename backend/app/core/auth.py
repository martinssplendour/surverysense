from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import HTTPException, Request, status


SESSION_USER_KEY = "authenticated_user"


@dataclass(slots=True)
class AuthenticatedUser:
    email: str
    name: str | None = None
    picture: str | None = None


def get_authenticated_user(request: Request) -> AuthenticatedUser | None:
    session_payload = request.scope.get("session")
    if not isinstance(session_payload, dict):
        return None

    payload = session_payload.get(SESSION_USER_KEY)
    if not isinstance(payload, dict):
        return None

    email = str(payload.get("email", "")).strip()
    if not email:
        return None

    name = payload.get("name")
    picture = payload.get("picture")
    return AuthenticatedUser(
        email=email,
        name=str(name).strip() if isinstance(name, str) and name.strip() else None,
        picture=str(picture).strip() if isinstance(picture, str) and picture.strip() else None,
    )


def set_authenticated_user(request: Request, user: AuthenticatedUser) -> None:
    request.session[SESSION_USER_KEY] = asdict(user)


def clear_authenticated_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user
