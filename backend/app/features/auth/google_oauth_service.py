from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

try:
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token
except ImportError:  # pragma: no cover - optional until dependencies are installed.
    GoogleRequest = None
    id_token = None


@dataclass(slots=True)
class GoogleOAuthClientConfig:
    client_id: str
    client_secret: str
    redirect_uris: list[str]
    javascript_origins: list[str]


@dataclass(slots=True)
class GoogleOAuthUser:
    email: str
    name: str | None = None
    picture: str | None = None


class GoogleOAuthConfigurationError(RuntimeError):
    """Raised when the Google OAuth client configuration is unavailable or invalid."""


class GoogleOAuthService:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uris: tuple[str, ...] | list[str],
        javascript_origins: tuple[str, ...] | list[str],
        client_json_path: str,
        allowed_domains: tuple[str, ...],
        clock_skew_seconds: int = 30,
    ) -> None:
        self.allowed_domains = tuple(
            sorted(
                {
                    domain.strip().casefold().lstrip("@")
                    for domain in allowed_domains
                    if domain.strip()
                }
            )
        )
        self.clock_skew_seconds = max(0, int(clock_skew_seconds))
        self._config = self._load_client_config(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=redirect_uris,
            javascript_origins=javascript_origins,
            client_json_path=client_json_path,
        )

    @property
    def is_configured(self) -> bool:
        return self._config is not None

    @property
    def client_id(self) -> str:
        return self._config.client_id if self._config is not None else ""

    @property
    def redirect_uris(self) -> list[str]:
        return self._config.redirect_uris if self._config is not None else []

    def verify_credential(self, credential: str) -> GoogleOAuthUser:
        if not credential.strip():
            raise ValueError("Missing Google credential.")
        if self._config is None:
            raise GoogleOAuthConfigurationError("Google OAuth is not configured.")
        if GoogleRequest is None or id_token is None:
            raise GoogleOAuthConfigurationError(
                "google-auth is not installed. Install backend dependencies again."
            )

        token_info = id_token.verify_oauth2_token(
            credential,
            GoogleRequest(),
            self._config.client_id,
            clock_skew_in_seconds=self.clock_skew_seconds,
        )
        email = str(token_info.get("email", "")).strip()
        email_verified = bool(token_info.get("email_verified"))
        if not email or not email_verified:
            raise ValueError("Google account email could not be verified.")
        if not self.is_allowed_email(email):
            domains = ", ".join(f"@{domain}" for domain in self.allowed_domains)
            raise PermissionError(f"Only {domains} accounts are allowed.")

        name = token_info.get("name")
        picture = token_info.get("picture")
        return GoogleOAuthUser(
            email=email,
            name=str(name).strip() if isinstance(name, str) and name.strip() else None,
            picture=str(picture).strip() if isinstance(picture, str) and picture.strip() else None,
        )

    def is_allowed_email(self, email: str) -> bool:
        candidate = email.strip().casefold()
        if "@" not in candidate:
            return False
        domain = candidate.rsplit("@", 1)[1]
        return domain in self.allowed_domains

    def _load_client_config(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uris: tuple[str, ...] | list[str],
        javascript_origins: tuple[str, ...] | list[str],
        client_json_path: str,
    ) -> GoogleOAuthClientConfig | None:
        env_client_id = client_id.strip()
        if env_client_id:
            return GoogleOAuthClientConfig(
                client_id=env_client_id,
                client_secret=client_secret.strip(),
                redirect_uris=[
                    str(uri).strip()
                    for uri in redirect_uris
                    if str(uri).strip()
                ],
                javascript_origins=[
                    str(origin).strip()
                    for origin in javascript_origins
                    if str(origin).strip()
                ],
            )

        resolved_path = self._resolve_client_json_path(client_json_path)
        if resolved_path is None:
            return None

        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
        web_config = payload.get("web")
        if not isinstance(web_config, dict):
            raise GoogleOAuthConfigurationError(
                f"Google OAuth client JSON at '{resolved_path}' does not contain a 'web' client config."
            )

        client_id = str(web_config.get("client_id", "")).strip()
        client_secret = str(web_config.get("client_secret", "")).strip()
        if not client_id:
            raise GoogleOAuthConfigurationError(
                f"Google OAuth client JSON at '{resolved_path}' does not contain a client_id."
            )

        return GoogleOAuthClientConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uris=[
                str(uri).strip()
                for uri in web_config.get("redirect_uris", [])
                if str(uri).strip()
            ],
            javascript_origins=[
                str(origin).strip()
                for origin in web_config.get("javascript_origins", [])
                if str(origin).strip()
            ],
        )

    def _resolve_client_json_path(self, configured_path: str) -> Path | None:
        candidate = configured_path.strip()
        if candidate:
            resolved = Path(candidate)
            if not resolved.is_absolute():
                resolved = self._repo_root() / resolved
            if not resolved.exists():
                raise GoogleOAuthConfigurationError(
                    f"Google OAuth client JSON was not found at '{resolved}'."
                )
            return resolved

        matches = sorted(self._repo_root().glob("client_secret_*.json"))
        return matches[0] if matches else None

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[3]
