# PayPal Sandbox Checkout Checklist

Use this checklist against a local or non-production deployment. PayPal Sandbox
payments are simulated; do not enter live credentials or use live buyer
accounts. Keep the PayPal client secret on the backend only.

## 1. Prepare PayPal Sandbox

1. Sign in to the [PayPal Developer Dashboard](https://developer.paypal.com/).
2. Open **Apps & Credentials**, select **Sandbox**, and create a REST app for
   the MemoryBook integration.
3. Copy the sandbox app's Client ID and Secret. Store them in the backend
   environment; do not put the secret in a frontend variable.
4. Open **Sandbox > Accounts** and create a **Personal** buyer account. Record
   its sandbox email and password for checkout. Keep the merchant app's
   credentials separate from the buyer login.
5. In `backend/.env`, configure:

   ```dotenv
   PAYPAL_MODE=sandbox
   PAYPAL_CLIENT_ID=<sandbox app client id>
   PAYPAL_CLIENT_SECRET=<sandbox app secret>
   ```

   Configure a webhook ID only if you are also exercising the optional backup
   webhook flow.
6. In `frontend/.env`, set the same sandbox app Client ID:

   ```dotenv
   VITE_PAYPAL_CLIENT_ID=<sandbox app client id>
   ```

   The `VITE_` value is public by design. Never set the PayPal secret in the
   frontend.
7. Restart the backend and frontend so they load the environment. Confirm
   `/api/v1/payments/methods?currency=USD` lists PayPal, sign in as a customer,
   and confirm the checkout displays the USD charge before opening PayPal.

## 2. PDF purchase and retry after cancellation

1. In the customer account, open a saved book and choose **Purchase PDF**.
   Submit the order and launch PayPal.
   - **Expected:** MemoryBook shows the server-calculated USD amount; PayPal
     opens a Sandbox approval window.
2. Sign in to PayPal with the Sandbox Personal buyer account and approve.
   - **Expected:** PayPal returns to MemoryBook, the backend captures the
     order, and the payment becomes successful only after server verification.
3. Wait for PDF generation, then open the order or dashboard downloads.
   - **Expected:** The project is unlocked, the PDF is marked ready, and the
     download begins with a valid PDF file.
4. Verify access while signed in as the purchasing customer. Sign out and sign
   in as a different customer, then try the original order/download URL.
   - **Expected:** The owner can download; the other customer receives
     not-found/forbidden access and cannot download the file.
5. For the cancellation/retry check, create another PDF order and launch
   PayPal. Close the approval popup without approving.
   - **Expected:** MemoryBook reports that checkout was cancelled and offers a
     retry. The payment/order remains retryable; no PDF is unlocked and no
     second order is created.
6. Retry that same payment and approve it with the Sandbox buyer.
   - **Expected:** One successful capture unlocks the original project and
     queues PDF generation. Repeated capture requests must not charge or
     unlock twice.

## 3. Print purchase and production

1. Open a saved book, choose print options, enter a delivery address, accept
   the required sharing-consent checkbox, and request a quote.
   - **Expected:** The quote shows the server-calculated price, including
     page-based charges and shipping. The customer cannot submit without
     consent.
2. Place the print order and pay using the Sandbox buyer account.
   - **Expected:** The order moves from pending payment to payment confirmed.
     The project revision and selected configuration are retained for print,
     and digital/print-profile PDF generation is queued.
3. Sign in to the admin account and open the production queue and order.
   - **Expected:** Only the paid order appears in production. The admin sees
     the order details, a **New paid print order** in-app notification, and a
     queued email. In local development with `AUTH_EMAIL_MODE=file`, the
     delivered email is available in the development mailbox.
4. Wait for the print-profile PDF to become ready. Use **Download print PDF**.
   - **Expected:** The admin receives the print PDF; the access is recorded in
     the admin activity log. An unpaid order or an unavailable PDF cannot be
     downloaded.
5. Edit the customer's project after the print order has been placed, then
   download the print PDF again.
   - **Expected:** The print file still reflects the revision frozen for the
     order, not the later customer edits.
6. Move the order through **Processing**, **Printed**, and **Shipped**. When
   shipping, enter a courier and tracking number. Continue through **Out for
   delivery** and **Delivered**.
   - **Expected:** The shipped transition requires a tracking number. The
     customer receives an in-app notification and email for payment received
     and each production/shipment milestone. The customer order timeline shows
     the same ordered statuses, timestamps, courier, tracking number, and
     delivery address.

## 4. Refund

1. From the admin payment or refund view, request a refund for a successful
   Sandbox payment using the available refund action.
   - **Expected:** The backend requests the refund for the captured amount and
     currency, records the provider result, and is safe to retry with the same
     idempotency key.
2. Refresh the customer dashboard and attempt to use the PDF download again.
   - **Expected:** The refunded PDF entitlement is revoked and the project is
     no longer in the ready/unlocked state.
3. Inspect the PayPal Sandbox merchant and buyer activity.
   - **Expected:** The capture and refund appear in Sandbox activity; no live
     funds were moved.

## 5. Results record

Record the environment (Sandbox), date, order numbers, observed statuses,
whether the local development mailbox received each message, and any errors.
Do not include credentials, cookies, access tokens, or signed download URLs in
the record. A successful manual run validates the browser SDK, Sandbox account,
and network integration in addition to the automated backend checks.
