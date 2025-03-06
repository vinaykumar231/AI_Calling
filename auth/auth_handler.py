from __future__ import annotations

import time
from typing import Any
import jwt
from decouple import config
from jwt import PyJWTError

JWT_SECRET = config('secret')
JWT_ALGORITHM = config('algorithm')


def token_response(token: str):
    return {
        "access_token": token
    }


def signJWT(user_id: str, user_type: str) -> tuple[Any, float]:
    expiration_time = time.time() + 30 * 24 * 60 * 60 
    payload = {
        "user_id": user_id,
        "user_type": user_type,
        "exp": expiration_time
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return token, expiration_time


def decodeJWT(token: str) -> Any | None:
    try:
        decoded_token = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if decoded_token.get("exp") and decoded_token["exp"] < time.time():
            return None
            # Check if the necessary claims are present
        if "user_id" not in decoded_token or "user_type" not in decoded_token:
            return None
        return decoded_token
    except PyJWTError:
        return None
