"""
Thin wrapper around the official `razorpay` Python SDK.

Every method here makes a real HTTP call to Razorpay's API (Test Mode keys
work identically to Live Mode keys for Payment Links, so this is safe to
run end-to-end without moving real money). There is no local fabrication
of a payment link — `create_payment_link` returns whatever Razorpay's API
actually responds with, and `verify_webhook_signature` runs Razorpay's own
HMAC-SHA256 verification utility against your webhook secret.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import razorpay
from razorpay.errors import SignatureVerificationError

from .config import settings

logger = logging.getLogger("contextpulse.razorpay")


class RazorpayNotConfiguredError(RuntimeError):
    pass


class RazorpayService:
    def __init__(self) -> None:
        if settings.razorpay_configured():
            self.client: Optional[razorpay.Client] = razorpay.Client(
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
            )
            self.client.set_app_details({"title": "ContextPulse", "version": "1.0.0"})
        else:
            self.client = None
            logger.warning(
                "RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — Razorpay API calls will raise "
                "RazorpayNotConfiguredError until you add real Test Mode keys to .env"
            )

    def is_live(self) -> bool:
        return self.client is not None

    def create_payment_link(
        self,
        amount_inr: float,
        description: str,
        customer_name: str,
        customer_email: Optional[str],
        customer_phone: str,
        notes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a real Razorpay Payment Link via POST /v1/payment_links."""
        if not self.client:
            raise RazorpayNotConfiguredError(
                "Cannot create a live payment link — set RAZORPAY_KEY_ID/SECRET in .env "
                "(free Test Mode keys: https://dashboard.razorpay.com/app/keys)"
            )
        payload: Dict[str, Any] = {
            "amount": int(round(amount_inr * 100)),  # paise
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "customer": {
                "name": customer_name,
                "contact": customer_phone,
            },
            "notify": {"sms": True, "email": bool(customer_email)},
            "reminder_enable": True,
            "notes": notes,
        }
        if customer_email:
            payload["customer"]["email"] = customer_email

        response = self.client.payment_link.create(payload)
        logger.info("Razorpay payment link created: %s", response.get("id"))
        return response

    def fetch_payment_link(self, payment_link_id: str) -> Dict[str, Any]:
        if not self.client:
            raise RazorpayNotConfiguredError("Razorpay not configured")
        return self.client.payment_link.fetch(payment_link_id)

    def verify_webhook_signature(self, payload_body: str, signature: str) -> bool:
        """Verify an inbound webhook using Razorpay's HMAC utility — no shortcuts."""
        if not self.client or not settings.webhook_secret_configured():
            logger.warning("Webhook signature check skipped: Razorpay/webhook secret not configured")
            return False
        try:
            self.client.utility.verify_webhook_signature(
                payload_body, signature, settings.razorpay_webhook_secret
            )
            return True
        except SignatureVerificationError:
            logger.error("Webhook signature verification FAILED — rejecting payload")
            return False
