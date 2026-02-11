from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import create_access_token
from src.database import get_db
from src.models.user import User
from src.schemas.auth import GitHubAuthRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/github", response_model=TokenResponse)
async def github_auth(request: GitHubAuthRequest, db: AsyncSession = Depends(get_db)):
    """Exchange GitHub OAuth token for API access token. Creates user if needed."""
    result = await db.execute(select(User).where(User.github_id == request.github_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=request.github_id,
            login=request.login,
            name=request.name,
            email=request.email,
            avatar_url=request.avatar_url,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.login = request.login
        user.name = request.name
        user.email = request.email
        user.avatar_url = request.avatar_url
        await db.commit()

    token = create_access_token(user.id)
    return TokenResponse(access_token=token)
