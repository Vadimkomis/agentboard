import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.config import settings
from src.database import get_db
from src.models.team import Team, TeamMember
from src.models.user import User

router = APIRouter(prefix="/billing", tags=["billing"])

# Plan definitions
PLANS = {
    "free": {
        "name": "Free",
        "execution_quota": 50,
        "price_monthly": 0,
        "features": ["5 projects", "50 executions/month", "Community support"],
    },
    "pro": {
        "name": "Pro",
        "execution_quota": 500,
        "price_monthly": 29,
        "features": [
            "Unlimited projects",
            "500 executions/month",
            "Priority support",
            "Custom agent configs",
        ],
    },
    "team": {
        "name": "Team",
        "execution_quota": 2000,
        "price_monthly": 79,
        "features": [
            "Everything in Pro",
            "2000 executions/month",
            "Team management",
            "Role-based access",
            "Audit logs",
        ],
    },
}


class PlanResponse(BaseModel):
    id: str
    name: str
    execution_quota: int
    price_monthly: int
    features: list[str]


class UsageResponse(BaseModel):
    plan_tier: str
    execution_quota: int
    executions_used: int
    remaining: int


class CheckoutRequest(BaseModel):
    plan_id: str
    team_id: uuid.UUID | None = None


class CheckoutResponse(BaseModel):
    checkout_url: str


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans():
    return [
        PlanResponse(id=plan_id, **plan_data)
        for plan_id, plan_data in PLANS.items()
    ]


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current plan usage for the user or their team."""
    # Check if user belongs to a team
    member_result = await db.execute(
        select(TeamMember).where(TeamMember.user_id == current_user.id).limit(1)
    )
    member = member_result.scalar_one_or_none()

    if member:
        team_result = await db.execute(select(Team).where(Team.id == member.team_id))
        team = team_result.scalar_one_or_none()
        if team:
            return UsageResponse(
                plan_tier=team.plan_tier,
                execution_quota=team.execution_quota,
                executions_used=team.executions_used,
                remaining=max(0, team.execution_quota - team.executions_used),
            )

    # Fallback to user-level plan
    plan = PLANS.get(current_user.plan_tier, PLANS["free"])
    return UsageResponse(
        plan_tier=current_user.plan_tier,
        execution_quota=plan["execution_quota"],
        executions_used=0,
        remaining=plan["execution_quota"],
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe checkout session for plan upgrade."""
    if data.plan_id not in PLANS or data.plan_id == "free":
        raise HTTPException(status_code=400, detail="Invalid plan")

    stripe_key = getattr(settings, "stripe_secret_key", "")
    if not stripe_key:
        raise HTTPException(
            status_code=503,
            detail="Billing is not configured. Set STRIPE_SECRET_KEY.",
        )

    try:
        import stripe

        stripe.api_key = stripe_key

        plan = PLANS[data.plan_id]
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=current_user.email,
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "recurring": {"interval": "month"},
                        "unit_amount": plan["price_monthly"] * 100,
                        "product_data": {"name": f"AgentBoard {plan['name']}"},
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "user_id": str(current_user.id),
                "team_id": str(data.team_id) if data.team_id else "",
                "plan_id": data.plan_id,
            },
            success_url=f"{settings.cors_origins[0]}/settings?billing=success",
            cancel_url=f"{settings.cors_origins[0]}/settings?billing=cancelled",
        )
        return CheckoutResponse(checkout_url=session.url)
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Stripe SDK not installed",
        )


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    stripe_webhook_secret = getattr(settings, "stripe_webhook_secret", "")

    if not stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")

    try:
        import stripe

        stripe.api_key = getattr(settings, "stripe_secret_key", "")
        event = stripe.Webhook.construct_event(body, sig, stripe_webhook_secret)
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe SDK not installed")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        plan_id = metadata.get("plan_id")
        user_id = metadata.get("user_id")
        team_id = metadata.get("team_id")

        if plan_id and plan_id in PLANS:
            async with (await _get_session()) as db:
                plan = PLANS[plan_id]
                if team_id:
                    result = await db.execute(
                        select(Team).where(Team.id == uuid.UUID(team_id))
                    )
                    team = result.scalar_one_or_none()
                    if team:
                        team.plan_tier = plan_id
                        team.execution_quota = plan["execution_quota"]
                        team.stripe_subscription_id = session.get("subscription")
                        team.stripe_customer_id = session.get("customer")
                        await db.commit()
                elif user_id:
                    result = await db.execute(
                        select(User).where(User.id == uuid.UUID(user_id))
                    )
                    user = result.scalar_one_or_none()
                    if user:
                        user.plan_tier = plan_id
                        await db.commit()

    return {"status": "ok"}


async def _get_session():
    from src.database import async_session
    return async_session()
