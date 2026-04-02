"""Stripe webhook handler for subscription events."""

import logging
import stripe
import httpx
from fastapi import APIRouter, Request, HTTPException

from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    settings = get_settings()

    if not settings.stripe_secret_key or not settings.stripe_webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    body = await request.body()
    signature = request.headers.get("stripe-signature")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(
            body,
            signature,
            settings.stripe_webhook_secret,
        )
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event["type"]
    data_object = event["data"]["object"]

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        await handle_subscription_update(settings, data_object)
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_deleted(settings, data_object)
    else:
        logger.info("Unhandled Stripe event: %s", event_type)

    return {"received": True}


async def handle_subscription_update(settings, subscription: dict):
    customer_id = subscription.get("customer", "")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id", "")

    sub_id = subscription.get("id", "")
    status = map_stripe_status(subscription.get("status", ""))
    plan = determine_plan(settings, subscription)
    period_end = subscription.get("current_period_end")

    update_data = {
        "stripe_subscription_id": sub_id,
        "plan": plan,
        "status": status,
    }
    if period_end:
        from datetime import datetime, timezone
        update_data["current_period_end"] = datetime.fromtimestamp(
            period_end, tz=timezone.utc
        ).isoformat()

    url = f"{settings.supabase_url}/rest/v1/subscriptions"
    params = {"stripe_customer_id": f"eq.{customer_id}"}
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    async with httpx.AsyncClient() as client:
        response = await client.patch(url, params=params, json=update_data, headers=headers)
        if response.status_code not in (200, 204):
            logger.error("Failed to update subscription for customer %s: %s", customer_id, response.text)


async def handle_subscription_deleted(settings, subscription: dict):
    customer_id = subscription.get("customer", "")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id", "")

    update_data = {
        "plan": "free",
        "status": "canceled",
        "stripe_subscription_id": None,
        "current_period_end": None,
    }

    url = f"{settings.supabase_url}/rest/v1/subscriptions"
    params = {"stripe_customer_id": f"eq.{customer_id}"}
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    async with httpx.AsyncClient() as client:
        response = await client.patch(url, params=params, json=update_data, headers=headers)
        if response.status_code not in (200, 204):
            logger.error("Failed to reset subscription for customer %s: %s", customer_id, response.text)


def determine_plan(settings, subscription: dict) -> str:
    items = subscription.get("items", {}).get("data", [])
    if not items:
        return "free"
    price_id = items[0].get("price", {}).get("id", "")
    # Compare with settings if available
    studio_price = getattr(settings, "stripe_studio_price_id", "")
    pro_price = getattr(settings, "stripe_pro_price_id", "")
    if studio_price and price_id == studio_price:
        return "studio"
    if pro_price and price_id == pro_price:
        return "pro"
    return "pro"  # Default paid plan


def map_stripe_status(stripe_status: str) -> str:
    if stripe_status in ("active", "trialing"):
        return "active"
    if stripe_status == "past_due":
        return "past_due"
    return "canceled"
