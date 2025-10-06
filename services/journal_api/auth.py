import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from jose import jwt, JWTError
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer
from config import settings


ALGORITHM = "HS256"


def verify_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_id_from_token(token: str) -> uuid.UUID:
    payload = verify_token(token)
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user id in token")


auth_scheme = HTTPBearer()


def get_current_user_id(authorization: str = Depends(auth_scheme)) -> uuid.UUID:
    token = authorization.credentials
    return get_user_id_from_token(token)


