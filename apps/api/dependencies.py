from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from libs.core.settings import Settings, get_settings


def require_internal_admin(
    x_admin_user_id: int = Header(...),
    x_internal_token: str = Header(...),
    settings: Settings = Depends(get_settings),
) -> int:
    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid internal token")
    if x_admin_user_id not in settings.telegram_admin_user_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not admin")
    return x_admin_user_id
