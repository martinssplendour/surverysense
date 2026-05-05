"""Session-based authentication helpers: read/write the authenticated user and manage idle timeouts."""
from __future__ import annotations

import secrets
import time
from dataclasses import asdict, dataclass

from fastapi import HTTPException, Request, status

from app.core.settings import get_settings

SESSION_USER_KEY = "authenticated_user"
SESSION_RESULT_IDS_KEY = "uploaded_result_ids"
SESSION_LAST_ACTIVITY_KEY = "last_activity_at"
SESSION_ROTATION_NONCE_KEY = "session_rotation_nonce"


@dataclass(slots=True)
class AuthenticatedUser:
    """Minimal profile stored in the server-side session after a successful OAuth login."""

    email: str
    name: str | None = None
    picture: str | None = None


def get_authenticated_user(request: Request) -> AuthenticatedUser | None:
    """Return the authenticated user from the session, or None if missing or idle-expired."""
    session_payload = request.scope.get("session")
    if not isinstance(session_payload, dict):
        return None

    if _is_session_idle_expired(session_payload):
        # Expire the server-side session in-place so the next browser request no
        # longer carries stale auth state after an idle timeout.
        request.session.clear()
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
    """Rotate the session (invalidates the old cookie) then write the user profile and activity timestamp."""
    _rotate_authenticated_session(request)
    request.session[SESSION_USER_KEY] = asdict(user)
    _touch_session_activity(request)


def clear_authenticated_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)
    request.session.pop(SESSION_LAST_ACTIVITY_KEY, None)
    request.session.pop(SESSION_ROTATION_NONCE_KEY, None)


def register_session_result_id(request: Request, result_id: str) -> None:
    """Append a result_id to the session's list of uploaded results, deduplicating as needed."""
    normalized_ids = _normalize_result_ids(list(get_session_result_ids(request)) + [result_id])

    # Track result ids in the session so logout can delete only this user's
    # in-memory uploads instead of flushing the whole process cache.
    request.session[SESSION_RESULT_IDS_KEY] = normalized_ids


def replace_session_result_id(request: Request, result_id: str) -> list[str]:
    """Set this session's active result_id, returning any previous ids for deletion."""
    previous_ids = pop_session_result_ids(request)
    normalized = str(result_id).strip()
    request.session[SESSION_RESULT_IDS_KEY] = [normalized] if normalized else []
    return [previous_id for previous_id in previous_ids if previous_id != normalized]


def get_session_result_ids(request: Request) -> list[str]:
    stored_ids = request.session.get(SESSION_RESULT_IDS_KEY, [])
    if not isinstance(stored_ids, list):
        return []
    return _normalize_result_ids(stored_ids)


def pop_session_result_ids(request: Request) -> list[str]:
    stored_ids = request.session.pop(SESSION_RESULT_IDS_KEY, [])
    if not isinstance(stored_ids, list):
        return []
    return _normalize_result_ids(stored_ids)


def require_session_result_access(request: Request, result_id: str) -> str:
    """Ensure the current signed session was issued the requested result_id."""
    normalized_result_id = str(result_id).strip()
    if normalized_result_id and normalized_result_id in get_session_result_ids(request):
        return normalized_result_id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This result is not available in the current session.",
    )


def require_authenticated_user(request: Request) -> AuthenticatedUser:
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    # Any authenticated API hit extends the idle timeout window.
    _touch_session_activity(request)
    return user


def _rotate_authenticated_session(request: Request) -> None:
    """Clear all session data and set a new nonce to prevent session fixation attacks."""
    request.session.clear()
    request.session[SESSION_ROTATION_NONCE_KEY] = secrets.token_urlsafe(16)


def _touch_session_activity(request: Request) -> None:
    request.session[SESSION_LAST_ACTIVITY_KEY] = int(time.time())


def _normalize_result_ids(raw_values: list[object]) -> list[str]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw_value in raw_values:
        normalized = str(raw_value).strip()
        if not normalized or normalized in seen_ids:
            continue
        seen_ids.add(normalized)
        normalized_ids.append(normalized)
    return normalized_ids


def _is_session_idle_expired(session_payload: dict) -> bool:
    """Return True if the session has been idle longer than the configured timeout."""
    last_activity_raw = session_payload.get(SESSION_LAST_ACTIVITY_KEY)
    if last_activity_raw is None:
        return False

    try:
        last_activity = int(last_activity_raw)
    except (TypeError, ValueError):
        return True

    timeout_seconds = max(60, get_settings().session_idle_timeout_seconds)  # floor at 60 s to prevent accidental lock-out
    return int(time.time()) - last_activity > timeout_seconds
