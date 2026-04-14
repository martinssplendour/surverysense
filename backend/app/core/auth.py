from __future__ import annotations

from dataclasses import asdict, dataclass

from fastapi import HTTPException, Request, status


SESSION_USER_KEY = "authenticated_user"
SESSION_RESULT_IDS_KEY = "uploaded_result_ids"


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


def register_session_result_id(request: Request, result_id: str) -> None:
    existing_ids = request.session.get(SESSION_RESULT_IDS_KEY, [])
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()

    for raw_value in list(existing_ids) + [result_id]:
        normalized = str(raw_value).strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        normalized_ids.append(normalized)

    request.session[SESSION_RESULT_IDS_KEY] = normalized_ids


def pop_session_result_ids(request: Request) -> list[str]:
    stored_ids = request.session.pop(SESSION_RESULT_IDS_KEY, [])
    if not isinstance(stored_ids, list):
        return []

    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw_value in stored_ids:
        normalized = str(raw_value).strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        normalized_ids.append(normalized)
    return normalized_ids


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return user
