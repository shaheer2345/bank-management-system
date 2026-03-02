import requests
from django.conf import settings


class PaymentGateway:
    """Simple wrapper around an external payment gateway API.

    The integration is intentionally generic so that real gateways (Stripe,
    PayPal, etc.) can be plugged in by updating settings and request payloads.
    For testing we mock ``requests.post`` to avoid hitting a real service.
    """

    def __init__(self, api_url=None, api_key=None, timeout=10):
        self.api_url = api_url or getattr(settings, "GATEWAY_API_URL", "https://example.com/pay")
        self.api_key = api_key or getattr(settings, "GATEWAY_API_KEY", "")
        self.timeout = timeout

    def charge(self, amount, currency, source, description=None):
        """Charge a payment source (card token, bank account id, etc.).

        Returns the parsed JSON payload from the gateway on success.  Raises a
        ``requests.HTTPError`` on failure which callers may catch.
        """
        payload = {
            "amount": str(amount),
            "currency": currency,
            "source": source,
        }
        if description:
            payload["description"] = description

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
