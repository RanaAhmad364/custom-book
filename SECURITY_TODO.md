# Security follow-up

## Rotate exposed credentials

- [ ] **Rotate this:** the PostgreSQL password included in `backend/.env.example`. It is present in Git history in commits `1e398e62e9bb` and `2af29e44c7df`. Replace it in the development database and any other environment where it was reused.
- [ ] **Rotate this:** a separate PostgreSQL password included in the README setup example. It is present in Git history in commits `2af29e44c7df` and `6e576342083b`. Replace it in the development database and any other environment where it was reused.

The two historical password values differ. Neither value is recorded here. Git history was not rewritten, so both historical examples remain available to repository users and existing clones.

## History scan notes

- Fixed password values in `backend/tests/test_dev_accounts.py` and test payment configuration in `backend/tests/test_payments.py` appear to be test fixtures, not service credentials. No rotation is needed unless any were reused outside tests.
- Secret-bearing settings in `backend/memorybook/config.py` read values from runtime configuration; the scan did not find literal provider credentials there.
