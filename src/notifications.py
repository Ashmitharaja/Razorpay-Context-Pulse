import logging

logger = logging.getLogger("contextpulse.notifications")

def send_notification(phone_number: str, message: str, send_via_twilio: bool = False) -> dict:
    """
    Notification handler designed to operate without Twilio paid/trial custom SMS blocks.
    Delegates SMS link delivery directly to Razorpay's native link dispatch feature.
    """
    if send_via_twilio:
        logger.warning(
            "Twilio custom SMS skipped: Free mode enabled. "
            "Razorpay native SMS system handles payment link delivery."
        )
        return {
            "status": "skipped",
            "reason": "Twilio trial restrictions bypassed. Native Razorpay delivery active."
        }

    logger.info(f"Notification request registered for {phone_number}. Native delivery utilized.")
    return {
        "status": "success",
        "channel": "razorpay_native"
    }