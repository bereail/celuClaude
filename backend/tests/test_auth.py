import pytest
from fastapi import HTTPException

from app import auth as auth_mod


def test_create_and_decode_access_token():
    token = auth_mod.create_access_token("someone")
    payload = auth_mod.decode_token(token)
    assert payload["sub"] == "someone"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = auth_mod.create_refresh_token("someone")
    payload = auth_mod.decode_token(token)
    assert payload["type"] == "refresh"


def test_decode_garbage_token_raises_401():
    with pytest.raises(HTTPException) as exc:
        auth_mod.decode_token("not-a-real-token")
    assert exc.value.status_code == 401


def test_verify_password_roundtrip():
    hashed = auth_mod.hash_password("hunter2")
    assert auth_mod.verify_password("hunter2", hashed)
    assert not auth_mod.verify_password("wrong", hashed)


def test_verify_password_empty_hash_never_matches():
    # config sin APP_USER_PASSWORD_HASH todavia seteado no debe aceptar
    # "cualquier cosa" como password valida.
    assert not auth_mod.verify_password("anything", "")
