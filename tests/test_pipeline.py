"""
Unit tests covering webhook mapping and rule engine without live credentials.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import ChannelType, DeclineReason, PaymentEvent
from src.rule_engine import decide


def _sample_webhook_body(error_code: str = "payment.authentication.failed") -> dict:
    return {
        "id": "evt_test123",
        "event": "payment.failed",
        "account_id": "acc_test",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123",
                    "order_id": "order_test123",
                    "amount": 249900,
                    "currency": "INR",
                    "method": "card",
                    "bank": "HDFC Bank",
                    "contact": "+919812345678",
                    "email": "test@example.com",
                    "error_code": error_code,
                    "error_description": "test decline",
                    "notes": {"customer_name": "Test User", "customer_phone": "+919812345678", "retry_count": 0},
                }
            }
        },
    }


def test_payment_event_from_webhook_maps_amount_correctly():
    event = PaymentEvent.from_razorpay_webhook(_sample_webhook_body(), merchant_id="acc_test")
    assert event.amount == 2499.0
    assert event.decline_reason == DeclineReason.AUTH_TIMEOUT
    assert event.customer_phone == "+919812345678"


def test_unknown_error_code_maps_to_unknown_reason():
    event = PaymentEvent.from_razorpay_webhook(_sample_webhook_body(error_code="some_new_code"), merchant_id="acc_test")
    assert event.decline_reason == DeclineReason.UNKNOWN


def test_rule_engine_routes_auth_timeout_to_upi():
    event = PaymentEvent.from_razorpay_webhook(_sample_webhook_body(), merchant_id="acc_test")
    strategy = decide(event)
    assert strategy.channel == ChannelType.UPI_ONE_TAP
    assert strategy.decided_by == "deterministic_fallback"


def test_rule_engine_offers_installments_for_large_soft_limit_decline():
    body = _sample_webhook_body(error_code="payment.limit.exceeded")
    body["payload"]["payment"]["entity"]["amount"] = 899900
    event = PaymentEvent.from_razorpay_webhook(body, merchant_id="acc_test")
    strategy = decide(event)
    assert strategy.channel == ChannelType.MICRO_INSTALLMENT
    assert strategy.installment_plan is not None
    assert abs(sum(strategy.installment_plan) - 8999.0) < 0.01


def test_repeated_retries_escalate_urgency():
    body = _sample_webhook_body()
    body["payload"]["payment"]["entity"]["notes"]["retry_count"] = 3
    event = PaymentEvent.from_razorpay_webhook(body, merchant_id="acc_test")
    strategy = decide(event)
    assert strategy.urgency_level.value == "CRITICAL"