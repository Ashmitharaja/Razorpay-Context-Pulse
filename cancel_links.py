import razorpay

RAZORPAY_KEY_ID = "rzp_test_TUukndcnh54ams"
RAZORPAY_KEY_SECRET = "0YXZCAPMD4JBIbguwMEzP3m4"

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

total_cancelled = 0
skip_count = 0

while True:
    # Fetch links starting after previous pages
    response = client.payment_link.all({"count": 100, "skip": skip_count})
    links = response.get("items", [])

    if not links:
        break

    cancelled_in_batch = 0
    for link in links:
        if link.get("status") in ["created", "issued"]:
            try:
                client.payment_link.cancel(link["id"])
                print(f"Cancelled: {link['id']}")
                cancelled_in_batch += 1
                total_cancelled += 1
            except Exception as e:
                print(f"Error cancelling {link['id']}: {e}")

    # Advance pagination if no active links were in this batch
    if cancelled_in_batch == 0:
        skip_count += len(links)
        if len(links) < 100:
            break

print(f"\nDone! Total payment links cancelled: {total_cancelled}")