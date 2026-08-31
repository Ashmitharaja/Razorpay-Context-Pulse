from __future__ import annotations

import uuid
from typing import Any, Dict

from .models import DynamicPayload, PaymentEvent, RecoveryStrategy, UrgencyLevel
from .razorpay_client import RazorpayService


def _sms_copy(event: PaymentEvent, short_url: str) -> str:
    ref = (event.razorpay_order_id or event.razorpay_payment_id)[:14]
    return (
        f"RAZORPAY: Payment of Rs.{event.amount:,.0f} for {ref} failed. "
        f"Complete now: {short_url} - Ignore if already paid."
    )


def build_payload(
    event: PaymentEvent,
    strategy: RecoveryStrategy,
    razorpay_service: RazorpayService,
) -> DynamicPayload:
    notes: Dict[str, Any] = {
        "contextpulse_strategy_id": strategy.strategy_id,
        "contextpulse_channel": strategy.channel.value,
        "original_payment_id": event.razorpay_payment_id,
    }
    description = f"Recovery payment for order {event.razorpay_order_id or event.razorpay_payment_id}"

    link_response = razorpay_service.create_payment_link(
        amount_inr=event.amount,
        description=description,
        customer_name=event.customer_name,
        customer_email=event.customer_email,
        customer_phone=event.customer_phone,
        notes=notes,
    )

    short_url = link_response["short_url"]
    urgent = strategy.urgency_level in (UrgencyLevel.HIGH, UrgencyLevel.CRITICAL)

    return DynamicPayload(
        payload_id=f"pay_{uuid.uuid4().hex[:10]}",
        strategy_id=strategy.strategy_id,
        razorpay_payment_link_id=link_response["id"],
        order_reference=event.razorpay_order_id,
        amount=event.amount,
        payment_link=short_url,
        short_link=short_url,
        sms_message=_sms_copy(event, short_url),
        expires_at=DynamicPayload.build_expiry(urgent),
        is_live_razorpay_link=True,
    )
