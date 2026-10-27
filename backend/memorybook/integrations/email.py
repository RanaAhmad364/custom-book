from __future__ import annotations

import json
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from flask import current_app

from memorybook.errors import ServiceUnavailableError


def email_delivery_is_configured() -> bool:
    if current_app.extensions.get("auth_email_sender") is not None:
        return True
    mode = current_app.config.get("AUTH_EMAIL_MODE", "smtp")
    if mode == "file":
        return current_app.config.get("ENVIRONMENT") == "development"
    return bool(current_app.config.get("SMTP_HOST") and current_app.config.get("SMTP_FROM_EMAIL"))


def send_verification_code(email: str, code: str) -> None:
    send_email(
        email,
        "Verify your MemoryBook email",
        f"Your MemoryBook verification code is {code}. It expires in "
        f"{current_app.config['AUTH_OTP_TTL_MINUTES']} minutes.",
    )


def send_password_reset(email: str, token: str) -> None:
    reset_url = f"{current_app.config['PUBLIC_APP_URL'].rstrip('/')}/reset-password?token={quote(token)}"
    send_email(
        email,
        "Reset your MemoryBook password",
        f"Use this link to reset your password: {reset_url}\n"
        f"The link expires in {current_app.config['AUTH_RESET_TTL_MINUTES']} minutes. "
        "If you did not request a reset, you can ignore this email.",
    )


def send_email(recipient: str, subject: str, body: str) -> None:
    sender = current_app.extensions.get("auth_email_sender")
    if sender is not None:
        sender(recipient, subject, body)
        return

    config = current_app.config
    if config.get("AUTH_EMAIL_MODE", "smtp") == "file":
        if config.get("ENVIRONMENT") != "development":
            raise ServiceUnavailableError("The local email mailbox is available only in development.")
        mailbox = Path(current_app.instance_path) / "dev-mailbox.jsonl"
        try:
            mailbox.parent.mkdir(parents=True, exist_ok=True)
            with mailbox.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "recipient": recipient,
                    "subject": subject,
                    "body": body,
                }) + "\n")
        except OSError as failure:
            current_app.logger.exception("Local development email delivery failed.")
            raise ServiceUnavailableError("The local email mailbox could not accept this message.") from failure
        return

    if not config.get("SMTP_HOST") or not config.get("SMTP_FROM_EMAIL"):
        raise ServiceUnavailableError("Email delivery is not configured. Contact the site administrator.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["SMTP_FROM_EMAIL"]
    message["To"] = recipient
    message.set_content(body)
    try:
        if config.get("SMTP_USE_SSL"):
            connection = smtplib.SMTP_SSL(
                config["SMTP_HOST"],
                config["SMTP_PORT"],
                timeout=10,
                context=ssl.create_default_context(),
            )
        else:
            connection = smtplib.SMTP(config["SMTP_HOST"], config["SMTP_PORT"], timeout=10)
        with connection as client:
            if config.get("SMTP_USE_TLS") and not config.get("SMTP_USE_SSL"):
                client.starttls()
            username = config.get("SMTP_USERNAME")
            if username:
                client.login(username, config.get("SMTP_PASSWORD", ""))
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as failure:
        current_app.logger.exception("Authentication email delivery failed.")
        raise ServiceUnavailableError("Email delivery failed. Please try again later.") from failure
