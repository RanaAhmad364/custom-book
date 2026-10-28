from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from flask import current_app
from sqlalchemy import select

from memorybook.errors import ServiceUnavailableError, ValidationError
from memorybook.extensions import db
from memorybook.models import Payment, PlatformSetting


class GatewayError(Exception):
    pass


@dataclass(frozen=True)
class CheckoutSession:
    url: str | None
    reference: str
    instructions: dict[str, str] | None = None


class PaymentGateway(Protocol):
    name: str

    def create_checkout(self, payment: Payment, title: str, idempotency_key: str) -> CheckoutSession: ...

    def verify_event(self, *args, **kwargs) -> dict: ...

    def handle_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict: ...

    def refund(self, payment: Payment, amount: Decimal, key: str) -> tuple[str, str]: ...


def available_payment_methods(currency: str) -> list[dict]:
    if currency.strip().upper() == "PKR":
        methods = []
        if current_app.config.get("MANUAL_PAYMENTS_ENABLED", False):
            methods.extend([
                {
                    "provider": "manual",
                    "method": "bank_transfer",
                    "label": "Bank transfer",
                    "instructions": _manual_instructions("bank_transfer"),
                },
                {
                    "provider": "manual",
                    "method": "jazzcash",
                    "label": "JazzCash",
                    "instructions": _manual_instructions("jazzcash"),
                },
                {
                    "provider": "manual",
                    "method": "easypaisa",
                    "label": "Easypaisa",
                    "instructions": _manual_instructions("easypaisa"),
                },
            ])
        if _paypal_is_configured():
            methods.append({
                "provider": "paypal",
                "method": "paypal_checkout",
                "label": "PayPal",
            })
        api_url = current_app.config.get("JAZZCASH_API_URL")
        return_url = current_app.config.get("PAYMENT_RETURN_URL")
        api_url_is_secure = isinstance(api_url, str) and urlparse(api_url).scheme == "https"
        return_url_is_secure = isinstance(return_url, str) and urlparse(return_url).scheme == "https"
        if (
            current_app.config.get("JAZZCASH_ENABLED")
            and current_app.config.get("JAZZCASH_CHECKOUT_CONTRACT_VERIFIED")
            and current_app.config.get("JAZZCASH_CALLBACK_CONTRACT_VERIFIED")
            and current_app.config.get("JAZZCASH_SERVER_INQUIRY_IMPLEMENTED")
            and api_url_is_secure
            and return_url_is_secure
            and all(current_app.config.get(key) for key in (
                "JAZZCASH_API_URL",
                "JAZZCASH_MERCHANT_ID",
                "JAZZCASH_PASSWORD",
                "JAZZCASH_INTEGRITY_SALT",
            ))
        ):
            configured_methods = _configured_methods(current_app.config.get("JAZZCASH_PAYMENT_METHODS"))
            if "jazzcash_wallet" in configured_methods:
                methods.append({
                    "provider": "jazzcash",
                    "method": "jazzcash_wallet",
                    "label": "JazzCash wallet",
                })
        if (
            current_app.config.get("STRIPE_ENABLED")
            and current_app.config.get("STRIPE_SECRET_KEY")
            and current_app.config.get("STRIPE_WEBHOOK_SECRET")
        ):
            methods.append({"provider": "stripe", "method": "card", "label": "Card"})
        return methods

    if (
        current_app.config.get("STRIPE_ENABLED")
        and current_app.config.get("STRIPE_SECRET_KEY")
        and current_app.config.get("STRIPE_WEBHOOK_SECRET")
    ):
        return [{"provider": "stripe", "method": "card", "label": "Card"}]
    return []


def provider_for(currency: str, preferred: str | None = None, method: str | None = None):
    if preferred is not None and not isinstance(preferred, str):
        raise ValidationError("Payment provider must be a string.", {"provider": "invalid"})
    if method is not None and not isinstance(method, str):
        raise ValidationError("Payment method must be a string.", {"paymentMethod": "invalid"})
    options = available_payment_methods(currency)
    if preferred is None:
        preferred = (
            current_app.config.get("PAYMENT_PRIMARY_GATEWAY", "paypal").strip().lower()
            if currency.upper() == "PKR"
            else "stripe"
        )
    name = preferred.strip().lower()
    selected = next(
        (
            option for option in options
            if option["provider"] == name and (method is None or option["method"] == method.strip().lower())
        ),
        None,
    )
    if selected is None:
        raise ServiceUnavailableError("No enabled, verified payment method is available for this currency.")
    if name == "manual":
        return ManualPaymentGateway()
    if name == "paypal":
        return PayPalGateway()
    if name == "jazzcash":
        return JazzCashGateway()
    if name == "stripe":
        return StripeGateway()
    raise ValidationError("Choose an enabled payment method for this currency.", {"provider": "unsupported"})


def _paypal_is_configured() -> bool:
    return bool(
        current_app.config.get("PAYPAL_MODE") in {"sandbox", "live"}
        and current_app.config.get("PAYPAL_CLIENT_ID")
        and current_app.config.get("PAYPAL_CLIENT_SECRET")
    )


def pkr_to_usd_rate() -> Decimal:
    setting = db.session.scalar(
        select(PlatformSetting).where(PlatformSetting.setting_key == "paypal_pkr_to_usd_rate")
    )
    raw_rate = (setting.setting_value or {}).get("rate") if setting else current_app.config.get(
        "PAYPAL_PKR_TO_USD_RATE",
        "0.0036",
    )
    try:
        rate = Decimal(str(raw_rate))
    except (InvalidOperation, ValueError, TypeError) as failure:
        raise ServiceUnavailableError("The PayPal currency conversion rate is not configured correctly.") from failure
    if not rate.is_finite() or rate <= 0 or rate > 1 or rate.as_tuple().exponent < -8:
        raise ServiceUnavailableError("The PayPal currency conversion rate is not configured correctly.")
    return rate


def pkr_amount_to_usd(amount: Decimal, rate: Decimal) -> Decimal:
    converted = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount > 0 and converted == 0:
        raise ValidationError("The order is too small to charge in USD.")
    return converted


class PayPalGateway:
    name = "paypal"

    def _api_base(self) -> str:
        mode = current_app.config.get("PAYPAL_MODE")
        if mode not in {"sandbox", "live"}:
            raise ServiceUnavailableError("PayPal mode must be sandbox or live.")
        return "https://api-m.sandbox.paypal.com" if mode == "sandbox" else "https://api-m.paypal.com"

    def _access_token(self) -> str:
        client_id = current_app.config.get("PAYPAL_CLIENT_ID")
        client_secret = current_app.config.get("PAYPAL_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ServiceUnavailableError("PayPal is not configured for this deployment.")
        request = Request(
            f"{self._api_base()}/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            method="POST",
            headers={
                "Authorization": "Basic "
                + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        token = _read_json_response(request, "PayPal").get("access_token")
        if not isinstance(token, str) or not token:
            raise ServiceUnavailableError("PayPal did not provide an API access token.")
        return token

    def _request(self, method: str, path: str, payload: dict | None = None, *, request_id: str | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else (b"{}" if method == "POST" else None)
        request = Request(
            f"{self._api_base()}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": "Bearer " + self._access_token(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                **({"PayPal-Request-Id": request_id} if request_id else {}),
            },
        )
        return _read_json_response(request, "PayPal")

    def create_checkout(self, payment: Payment, title: str, idempotency_key: str) -> CheckoutSession:
        raise ValidationError("PayPal checkout must be created through the Smart Buttons flow.")

    def create_smart_order(self, payment: Payment, reference_id: str, idempotency_key: str) -> str:
        if payment.usd_amount is None:
            raise ValidationError("A USD payment snapshot is required for PayPal.")
        payload = self._request(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": reference_id,
                    "custom_id": payment.id,
                    "invoice_id": "MB-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:24],
                    "amount": {"currency_code": "USD", "value": format(payment.usd_amount, ".2f")},
                }],
            },
            request_id=f"memorybook-smart-{idempotency_key}"[:108],
        )
        paypal_order_id = payload.get("id")
        if payload.get("status") != "CREATED" or not isinstance(paypal_order_id, str) or not paypal_order_id:
            raise ServiceUnavailableError("PayPal returned an invalid checkout order.")
        return paypal_order_id

    def capture_order(self, paypal_order_id: str, idempotency_key: str) -> dict:
        return self._request(
            "POST",
            f"/v2/checkout/orders/{paypal_order_id}/capture",
            {},
            request_id=f"memorybook-capture-{idempotency_key}"[:108],
        )

    def handle_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict:
        event = self.verify_event(raw_body, headers)
        return event

    def verify_event(self, raw_body: bytes, headers: dict[str, str]) -> dict:
        try:
            event = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as failure:
            raise ValidationError("PayPal webhook body is invalid.") from failure
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("event_type"), str):
            raise ValidationError("PayPal webhook event is incomplete.")
        required_headers = {
            "transmission_id": headers.get("PayPal-Transmission-Id"),
            "transmission_time": headers.get("PayPal-Transmission-Time"),
            "transmission_sig": headers.get("PayPal-Transmission-Sig"),
            "cert_url": headers.get("PayPal-Cert-Url"),
            "auth_algo": headers.get("PayPal-Auth-Algo"),
        }
        if not all(required_headers.values()):
            raise ValidationError("PayPal webhook signature headers are incomplete.")
        result = self._request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            {
                **required_headers,
                "webhook_id": current_app.config.get("PAYPAL_WEBHOOK_ID"),
                "webhook_event": event,
            },
        )
        if result.get("verification_status") != "SUCCESS":
            raise ValidationError("PayPal webhook signature is invalid.")
        return event

    def refund(self, payment: Payment, amount: Decimal, key: str) -> tuple[str, str]:
        if not payment.provider_capture_id or not payment.exchange_rate:
            raise ValidationError("The confirmed PayPal capture reference is unavailable.")
        usd_amount = pkr_amount_to_usd(amount, Decimal(payment.exchange_rate))
        result = self._request(
            "POST",
            f"/v2/payments/captures/{payment.provider_capture_id}/refund",
            {"amount": {"value": format(usd_amount, ".2f"), "currency_code": "USD"}},
            request_id=f"memorybook-refund-{key}"[:108],
        )
        refund_id = result.get("id")
        status = {"COMPLETED": "succeeded", "PENDING": "pending", "FAILED": "failed"}.get(result.get("status"))
        if not isinstance(refund_id, str) or status is None:
            raise ServiceUnavailableError("PayPal returned an invalid refund response.")
        return refund_id, status


def _manual_instructions(method: str) -> dict[str, str]:
    if method == "bank_transfer":
        values = {
            "accountTitle": current_app.config.get("MANUAL_BANK_ACCOUNT_TITLE", ""),
            "bank": current_app.config.get("MANUAL_BANK_NAME", ""),
            "accountNumber": current_app.config.get("MANUAL_BANK_ACCOUNT_NUMBER", ""),
        }
    elif method == "jazzcash":
        values = {"accountNumber": current_app.config.get("MANUAL_JAZZCASH_NUMBER", "")}
    else:
        values = {"accountNumber": current_app.config.get("MANUAL_EASYPAISA_NUMBER", "")}
    return {
        key: value.strip() if isinstance(value, str) and value.strip() else
        ("Contact MemoryBook support for transfer details." if key == "accountNumber" else "")
        for key, value in values.items()
    }


class ManualPaymentGateway:
    name = "manual"

    def create_checkout(self, payment: Payment, title: str, idempotency_key: str) -> CheckoutSession:
        method = payment.payment_method or "bank_transfer"
        reference = f"MB-{payment.id.replace('-', '')[:16].upper()}"
        return CheckoutSession(
            url=None,
            reference=reference,
            instructions={
                **_manual_instructions(method),
                "amount": str(payment.amount),
                "currency": payment.currency,
                "orderReference": reference,
                "paymentMethod": method,
                "note": "Use the order reference in your transfer note, then submit your transaction reference for review.",
            },
        )


def _configured_methods(value) -> set[str]:
    if not isinstance(value, str):
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


class StripeGateway:
    name = "stripe"

    def _api_key(self) -> str:
        key = current_app.config.get("STRIPE_SECRET_KEY")
        if not key or not current_app.config.get("STRIPE_WEBHOOK_SECRET"):
            raise ServiceUnavailableError("Stripe is not configured for this deployment.")
        return key

    def create_checkout(self, payment: Payment, title: str, idempotency_key: str) -> CheckoutSession:
        currency = payment.currency.lower()
        amount = _minor_units(payment.amount, currency)
        origin = current_app.config["PUBLIC_APP_URL"].rstrip("/")
        route = "pdf" if payment.pdf_order_id else "print"
        order_id = payment.pdf_order_id or payment.print_order_id
        result_url = f"{origin}/{route}/orders/{order_id}/processing"
        fields = {
            "mode": "payment",
            "client_reference_id": payment.id,
            "success_url": f"{result_url}?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{result_url}?payment=cancelled",
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency,
            "line_items[0][price_data][unit_amount]": str(amount),
            "line_items[0][price_data][product_data][name]": title[:200],
            "metadata[payment_id]": payment.id,
            "payment_intent_data[metadata][payment_id]": payment.id,
        }
        response = self._request(
            "POST",
            "/v1/checkout/sessions",
            fields,
            idempotency_key=f"memorybook-{idempotency_key}",
        )
        url = response.get("url")
        session_id = response.get("id")
        if not isinstance(url, str) or not url.startswith("https://checkout.stripe.com/") or not isinstance(session_id, str):
            raise ServiceUnavailableError("Stripe returned an invalid checkout session.")
        return CheckoutSession(url=url, reference=session_id)

    def refund(self, payment: Payment, amount: Decimal, key: str) -> tuple[str, str]:
        payment_intent = _latest_payment_intent(payment.id)
        if not payment_intent:
            raise ValidationError("The confirmed Stripe payment reference is unavailable.")
        response = self._request(
            "POST",
            "/v1/refunds",
            {"payment_intent": payment_intent, "amount": str(_minor_units(amount, payment.currency.lower()))},
            idempotency_key=key,
        )
        refund_id = response.get("id")
        status = response.get("status")
        if not isinstance(refund_id, str) or status not in {"pending", "succeeded", "failed", "canceled"}:
            raise ServiceUnavailableError("Stripe returned an invalid refund response.")
        return refund_id, status

    def verify_event(self, raw_body: bytes, signature: str | None) -> dict:
        secret = current_app.config.get("STRIPE_WEBHOOK_SECRET")
        if not secret or not signature:
            raise ValidationError("Payment webhook signature is missing.")
        timestamp, signatures = _stripe_signature_parts(signature)
        tolerance = int(current_app.config.get("PAYMENT_WEBHOOK_TOLERANCE_SECONDS", 300))
        if abs(int(time.time()) - timestamp) > tolerance:
            raise ValidationError("Payment webhook signature has expired.")
        signed = str(timestamp).encode() + b"." + raw_body
        expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, item) for item in signatures):
            raise ValidationError("Payment webhook signature is invalid.")
        try:
            event = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as failure:
            raise ValidationError("Payment webhook body is invalid.") from failure
        if not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("type"), str):
            raise ValidationError("Payment webhook event is incomplete.")
        return event

    def handle_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict:
        return self.verify_event(raw_body, headers.get("Stripe-Signature"))

    def _request(self, method: str, path: str, fields: dict, *, idempotency_key: str) -> dict:
        request = Request(
            f"https://api.stripe.com{path}",
            data=urlencode(fields).encode() if method == "POST" else None,
            method=method,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Idempotency-Key": idempotency_key,
            },
        )
        request.add_header("Authorization", "Bearer " + self._api_key())
        return _read_json_response(request, "Stripe")


class JazzCashGateway:
    name = "jazzcash"

    def _config(self) -> tuple[str, str, str, str]:
        url = current_app.config.get("JAZZCASH_API_URL")
        merchant_id = current_app.config.get("JAZZCASH_MERCHANT_ID")
        password = current_app.config.get("JAZZCASH_PASSWORD")
        salt = current_app.config.get("JAZZCASH_INTEGRITY_SALT")
        if not all((url, merchant_id, password, salt)):
            raise ServiceUnavailableError("JazzCash server-to-server checkout is not fully configured.")
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (current_app.testing and parsed.hostname in {"localhost", "127.0.0.1"}):
            raise ServiceUnavailableError("JazzCash API endpoint must use HTTPS.")
        return url, merchant_id, password, salt

    def create_checkout(self, payment: Payment, title: str, idempotency_key: str) -> CheckoutSession:
        url, merchant_id, password, salt = self._config()
        now = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        txn_ref = f"MB{hashlib.sha256(idempotency_key.encode()).hexdigest()[:20].upper()}"
        return_url = current_app.config.get("PAYMENT_RETURN_URL")
        if not return_url or not return_url.startswith("https://"):
            raise ServiceUnavailableError("A public HTTPS payment return URL is required for JazzCash.")
        payload = {
            "pp_Version": current_app.config.get("JAZZCASH_API_VERSION", "2.0"),
            "pp_TxnType": current_app.config.get("JAZZCASH_TXN_TYPE", "MPAY"),
            "pp_Language": "EN",
            "pp_MerchantID": merchant_id,
            "pp_Password": password,
            "pp_TxnRefNo": txn_ref,
            "pp_Amount": str(_minor_units(payment.amount, "pkr")),
            "pp_TxnCurrency": "PKR",
            "pp_TxnDateTime": now,
            "pp_TxnExpiryDateTime": time.strftime("%Y%m%d%H%M%S", time.gmtime(time.time() + 1800)),
            "pp_BillReference": f"MB-{payment.id[:16]}",
            "pp_Description": title[:100],
            "pp_ReturnURL": return_url,
            "pp_SecureHash": "",
        }
        payload["pp_SecureHash"] = jazzcash_secure_hash(payload, salt)
        request = Request(
            url,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Idempotency-Key": idempotency_key,
            },
        )
        response = _read_json_response(request, "JazzCash")
        redirect_url = response.get("pp_RedirectURL") or response.get("redirectUrl")
        response_reference = response.get("pp_TxnRefNo") or txn_ref
        if not isinstance(redirect_url, str) or not _valid_jazzcash_redirect(redirect_url):
            raise ServiceUnavailableError("JazzCash did not return a valid hosted checkout URL.")
        if response_reference != txn_ref:
            raise ServiceUnavailableError("JazzCash returned a mismatched transaction reference.")
        return CheckoutSession(url=redirect_url, reference=txn_ref)

    def verify_event(self, payload: dict) -> dict:
        _, _, _, salt = self._config()
        received_hash = payload.get("pp_SecureHash")
        if not isinstance(received_hash, str) or not hmac.compare_digest(
            jazzcash_secure_hash(payload, salt).lower(),
            received_hash.lower(),
        ):
            raise ValidationError("JazzCash callback signature is invalid.")
        if not isinstance(payload.get("pp_TxnRefNo"), str) or not isinstance(payload.get("pp_ResponseCode"), str):
            raise ValidationError("JazzCash callback is incomplete.")
        return payload

    def handle_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict:
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as failure:
            raise ValidationError("JazzCash callback body is invalid.") from failure
        if not isinstance(payload, dict):
            raise ValidationError("JazzCash callback payload is invalid.")
        return self.verify_event(payload)

    def refund(self, payment: Payment, amount: Decimal, key: str) -> tuple[str, str]:
        raise ServiceUnavailableError(
            "JazzCash refunds are unavailable until the merchant-specific refund API contract is verified."
        )


def jazzcash_secure_hash(fields: dict, integrity_salt: str) -> str:
    values = [
        str(value)
        for name, value in sorted(fields.items())
        if name != "pp_SecureHash" and value not in (None, "")
    ]
    message = f"{integrity_salt}&" + "&".join(values)
    return hmac.new(integrity_salt.encode(), message.encode(), hashlib.sha256).hexdigest().upper()


def _read_json_response(request: Request, provider: str) -> dict:
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(1024 * 1024)
            status = response.status
    except HTTPError as failure:
        failure.read(2048)
        current_app.logger.warning("%s request failed with HTTP %s.", provider, failure.code)
        raise ServiceUnavailableError(f"{provider} is temporarily unavailable.") from failure
    except (TimeoutError, URLError, OSError) as failure:
        current_app.logger.warning("%s request could not reach the provider.", provider)
        raise ServiceUnavailableError(f"{provider} is temporarily unavailable.") from failure
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as failure:
        raise ServiceUnavailableError(f"{provider} returned an invalid response.") from failure
    if status < 200 or status >= 300 or not isinstance(parsed, dict):
        raise ServiceUnavailableError(f"{provider} returned an unsuccessful response.")
    if parsed.get("error"):
        raise ServiceUnavailableError(f"{provider} could not start the payment.")
    return parsed


def _minor_units(amount: Decimal, currency: str) -> int:
    zero_decimal = {"bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf"}
    exponent = 0 if currency in zero_decimal else 2
    scaled = amount * (10**exponent)
    if scaled != scaled.to_integral_value():
        raise ValidationError("The amount cannot be represented in the selected currency.")
    return int(scaled)


def _stripe_signature_parts(header: str) -> tuple[int, list[str]]:
    try:
        parts = [part.split("=", 1) for part in header.split(",")]
        values = {key: value for key, value in parts if len(key) == 1}
        timestamp = int(values["t"])
        signatures = [value for key, value in parts if key == "v1"]
    except (KeyError, ValueError) as failure:
        raise ValidationError("Payment webhook signature format is invalid.") from failure
    if not signatures:
        raise ValidationError("Payment webhook signature is invalid.")
    return timestamp, signatures


def _valid_jazzcash_redirect(value: str) -> bool:
    parsed = urlparse(value)
    allowed = current_app.config.get(
        "JAZZCASH_REDIRECT_HOSTS",
        ["sandbox.jazzcash.com.pk", "jazzcash.com.pk"],
    )
    if isinstance(allowed, str):
        allowed = [item.strip().lower() for item in allowed.split(",") if item.strip()]
    return parsed.scheme == "https" and parsed.hostname and parsed.hostname.lower() in allowed


def _latest_payment_intent(payment_id: str) -> str | None:
    from sqlalchemy import select

    from memorybook.extensions import db
    from memorybook.models import PaymentAttempt

    latest = db.session.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.payment_id == payment_id, PaymentAttempt.status == "successful")
        .order_by(PaymentAttempt.created_at.desc())
    )
    return latest.provider_reference if latest and latest.provider_reference and latest.provider_reference.startswith("pi_") else None
