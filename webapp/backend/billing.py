"""Stripe subscription billing.

Requires STRIPE_SECRET_KEY, STRIPE_PRICE_ID (a recurring Price for the paid
plan), and STRIPE_WEBHOOK_SECRET to be set in the environment. Without them,
the checkout/webhook endpoints return a clear 503 instead of silently
pretending to charge anyone.
"""

from __future__ import annotations

import os

import stripe

from . import database

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


def billing_configured() -> bool:
    return bool(STRIPE_SECRET_KEY and STRIPE_PRICE_ID)


def create_checkout_session(user_row, success_url: str, cancel_url: str) -> str:
    """Create a Stripe Checkout session for the paid plan and return its URL."""
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        customer_email=user_row["email"],
        client_reference_id=str(user_row["id"]),
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def handle_webhook_event(payload: bytes, sig_header: str) -> None:
    """Verify and apply a Stripe webhook event, upgrading/downgrading plans."""
    event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    data = event["data"]["object"]
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        user_id = int(data["client_reference_id"])
        database.set_user_plan(
            user_id,
            plan="pro",
            stripe_customer_id=data.get("customer"),
            stripe_subscription_id=data.get("subscription"),
        )
    elif event_type in ("customer.subscription.deleted", "customer.subscription.updated"):
        status = data.get("status")
        customer_id = data.get("customer")
        with database.get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE stripe_customer_id = ?", (customer_id,)
            ).fetchone()
        if row:
            plan = "pro" if status in ("active", "trialing") else "free"
            database.set_user_plan(row["id"], plan=plan)
