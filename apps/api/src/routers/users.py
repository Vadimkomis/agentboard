from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.database import get_db
from src.models.user import User
from src.schemas.user import UserResponse, UserUpdateKeys
from src.services.encryption import encrypt_key

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me/keys")
async def update_keys(
    data: UserUpdateKeys,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.anthropic_key is not None:
        current_user.encrypted_anthropic_key = (
            encrypt_key(data.anthropic_key) if data.anthropic_key else None
        )
    if data.openai_key is not None:
        current_user.encrypted_openai_key = (
            encrypt_key(data.openai_key) if data.openai_key else None
        )
    await db.commit()
    return {"ok": True}


@router.get("/me/keys/status")
async def keys_status(current_user: User = Depends(get_current_user)):
    return {
        "anthropic_key_set": current_user.encrypted_anthropic_key is not None,
        "openai_key_set": current_user.encrypted_openai_key is not None,
    }
