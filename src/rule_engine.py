from __future__ import annotations

import uuid
from typing import List, Optional

from .models import ChannelType, DeclineReason, PaymentEvent, RecoveryStrategy, UrgencyLevel

_HUMAN_REASONS = {
    DeclineReason.AUTH_TIMEOUT: "the bank's authentication step timed out",
    DeclineReason.SOFT_LIMIT_EXCEEDED: "a transaction limit was reached",
    DeclineReason.INSUFFICIENT_FUNDS: "available balance was short",
    DeclineReason.BANK_SERVER_ERROR: "the issuing bank's gateway had a transient error",
    DeclineReason.OTP_FAILURE: "OTP verification failed or expired",
    DeclineReason.CARD_EXPIRED: "the card has expired",
    DeclineReason.UNKNOWN: "an unclassified issue occurred",
}


def humanize_reason(reason: DeclineReason) -> str:
    return _HUMAN_REASONS.get(reason, "a temporary issue")


def _split_amount(amount: float) -> List[float]:
    parts = 3 if amount > 3000 else 2
    base = round(amount / parts, 2)
    plan = [base] * (parts - 1)
    plan.append(round(amount - base * (parts - 1), 2))
    return plan


def decide(event: PaymentEvent) -> RecoveryStrategy:
    reasoning: List[str] = [
        f"[fallback-engine] Classifying decline_reason={event.decline_reason.value} "
        f"for a ₹{event.amount:,.2f} {event.payment_method} transaction."
    ]
    installment_plan: Optional[List[float]] = None

    if event.decline_reason == DeclineReason.AUTH_TIMEOUT:
        channel, urgency, confidence = ChannelType.UPI_ONE_TAP, UrgencyLevel.HIGH, 0.82
        action = "UPI 1-Tap link — bypasses the 3DS/OTP redirect window that just expired."
    elif event.decline_reason == DeclineReason.SOFT_LIMIT_EXCEEDED:
        use_installment = event.amount > 3000
        channel = ChannelType.MICRO_INSTALLMENT if use_installment else ChannelType.ALT_PAYMENT_METHOD
        urgency, confidence = UrgencyLevel.MEDIUM, 0.68
        installment_plan = _split_amount(event.amount) if use_installment else None
        action = (
            "Split into micro-installments to stay under the per-transaction cap."
            if use_installment else "Suggest an alternate saved payment method."
        )
    elif event.decline_reason == DeclineReason.INSUFFICIENT_FUNDS:
        channel, urgency, confidence = ChannelType.MICRO_INSTALLMENT, UrgencyLevel.MEDIUM, 0.55
        installment_plan = _split_amount(event.amount)
        action = "Offer a 2-3 part micro-installment plan to reduce single-charge burden."
    elif event.decline_reason == DeclineReason.BANK_SERVER_ERROR:
        channel, urgency, confidence = ChannelType.UPI_ONE_TAP, UrgencyLevel.HIGH, 0.65
        action = "Route via UPI (NPCI rail) to avoid the same issuer gateway."
    elif event.decline_reason == DeclineReason.OTP_FAILURE:
        channel, urgency, confidence = ChannelType.UPI_ONE_TAP, UrgencyLevel.HIGH, 0.75
        action = "UPI 1-Tap link — removes the OTP step that just failed."
    elif event.decline_reason == DeclineReason.CARD_EXPIRED:
        channel, urgency, confidence = ChannelType.ALT_PAYMENT_METHOD, UrgencyLevel.LOW, 0.45
        action = "Prompt for an alternate method — this card needs manual reissue."
    else:
        channel, urgency, confidence = ChannelType.RETRY_SMS_REMINDER, UrgencyLevel.LOW, 0.35
        action = "Send a generic reminder with a fresh payment link."

    if event.retry_count >= 2:
        confidence = max(0.20, confidence - 0.15)
        urgency = UrgencyLevel.CRITICAL
        reasoning.append(f"{event.retry_count} prior retries — throttling confidence, escalating urgency.")

    reasoning.append(f"Decision: channel={channel.value}, confidence={confidence:.2f}, urgency={urgency.value}.")

    return RecoveryStrategy(
        strategy_id=f"strat_{uuid.uuid4().hex[:10]}",
        event_id=event.event_id,
        channel=channel,
        reasoning=reasoning,
        confidence_score=round(confidence, 2),
        recommended_action=action,
        installment_plan=installment_plan,
        urgency_level=urgency,
        decided_by="deterministic_fallback",
    )