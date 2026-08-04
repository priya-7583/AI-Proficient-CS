from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import jwt
from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class AuthConfig:
    require_auth: bool
    api_key: str
    jwt_secret: str
    jwt_algorithm: str


class MutatingAuth:
    def __init__(self, config: AuthConfig) -> None:
        self.config = config

    def authorize(self, request: Request) -> dict[str, Any]:
        if not self.config.require_auth:
            return {"method": "disabled", "role": "writer"}

        api_key_header = request.headers.get("x-api-key", "").strip()
        if api_key_header and api_key_header == self.config.api_key:
            return {"method": "api_key", "role": "writer"}

        auth_header = request.headers.get("authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if not token:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
            try:
                payload = jwt.decode(
                    token,
                    self.config.jwt_secret,
                    algorithms=[self.config.jwt_algorithm],
                )
            except jwt.PyJWTError as exc:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token") from exc

            role = str(payload.get("role", ""))
            if role not in {"writer", "admin"}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient token role")
            return {"method": "jwt", "role": role, "sub": payload.get("sub")}

        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing mutating endpoint auth")
