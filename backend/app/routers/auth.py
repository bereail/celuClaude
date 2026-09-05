import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth import create_access_token, create_refresh_token, decode_token, verify_password
from ..config import get_settings
from ..schemas import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Simple in-memory sliding-window limiter: single-user MVP, no Redis needed.
# Resets on backend restart. Once this sits behind a real reverse proxy
# (Prioridad 2), move this to the proxy layer instead.
_LOGIN_WINDOW_SECONDS = 300
_LOGIN_MAX_ATTEMPTS = 5
_login_attempts: dict[str, list[float]] = {}


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    attempts = [t for t in _login_attempts.get(client_ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos. Esperá {_LOGIN_WINDOW_SECONDS // 60} minutos.",
        )
    attempts.append(now)
    _login_attempts[client_ip] = attempts


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request):
    _check_rate_limit(request.client.host if request.client else "unknown")
    if payload.email != settings.app_user_email or not verify_password(payload.password, settings.app_user_password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas")
    return TokenResponse(
        access_token=create_access_token(payload.email),
        refresh_token=create_refresh_token(payload.email),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest):
    decoded = decode_token(payload.refresh_token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido")
    subject = decoded["sub"]
    return TokenResponse(access_token=create_access_token(subject), refresh_token=create_refresh_token(subject))
