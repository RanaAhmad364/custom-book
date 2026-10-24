# Payment gateway status

## Current behavior

The application exposes `GET /api/v1/payments/methods?currency=PKR`. Checkout
lists only methods that are implemented, explicitly enabled, configured, and
marked as having a verified merchant-specific checkout and callback contract.
PDF and print order creation checks availability before committing an order.
The browser redirect is not treated as proof of payment.

The public PayFast documentation describes API v2.3 token and transaction
operations, status inquiry, and a refund route for settled transactions. It
does not publish the hosted-checkout contract, environment base URLs, callback
authentication contract, supported merchant currencies, or account-specific
method activation. No PayFast adapter is enabled or advertised until these
details are verified with the merchant.

The existing JazzCash adapter remains disabled by default. Although the
merchant-specific checkout and callback flags are available, it is not exposed
because the current adapter does not implement the server-side transaction
inquiry documented by the provider. That missing implementation is a code
blocker, not a setting to override. After implementing inquiry against the
merchant contract and validating it in sandbox, the wallet method can be
enabled. The adapter does not automate refunds; approved refunds enter manual
processing.

No direct Easypaisa adapter is present. The public merchant portal does not
provide enough of a technical checkout, callback, status inquiry, and refund
contract to implement one safely.

Stripe remains available only when `STRIPE_ENABLED=true`, the server-side API
key and webhook secret are present, and the requested currency is not PKR.
The application default preserves the previous Stripe-enabled behavior for
existing deployments; the new `.env.example` sets it to `false` so a fresh
deployment does not enable payments until deliberately configured.

## Configuration

Use `backend/.env.example` as the configuration template. Never place merchant
credentials in frontend variables or commit them. The `*_CONTRACT_VERIFIED`
settings are operational attestations, not substitutes for provider-side
verification or sandbox testing. Do not enable live payments based only on
public documentation or a configured base URL.

The illustrative `PAYFAST_API_BASE_URL` is intentionally unused: the public
documentation reviewed does not establish a production URL. Likewise,
Easypaisa configuration placeholders do not mean an adapter exists.

## Merchant verification required before enabling a local gateway

Obtain and test the merchant-specific integration pack, including:

- Merchant eligibility, approval, account identifiers, credential rotation,
  and sandbox/production access.
- Exact checkout initiation endpoint, API version, authentication/signature
  construction, required payload fields, redirect behavior, and callback URL
  requirements.
- Enabled payment methods and currencies for this account.
- Callback authenticity rules and a server-side transaction inquiry contract
  that confirms amount, currency, merchant, reference, and final status.
- Refund availability, exact refund procedure/API contract, idempotency rules,
  and how to verify a refund before recording completion.
- Settlement currency, fees, settlement cadence, reconciliation reports, and
  dispute procedures.
- Successful, declined, cancelled, pending, duplicate, delayed, and malformed
  sandbox callback examples.

Official public references reviewed:

- [PayFast Pakistan developer documentation](https://premierpayfast.com/developers/)
- [PayFast Pakistan signup](https://premierpayfast.com/signup/)
- [JazzCash v4.2 sandbox documentation](https://sandbox.jazzcash.com.pk/SandboxDocumentation/v4.2/index.html)
- [Easypaisa merchant portal](https://merchantportal.easypaisa.com.pk/)
- [Easypaisa merchant signup](https://merchantportal.easypaisa.com.pk/sign-up/)
