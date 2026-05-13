from __future__ import annotations

import logging
import smtplib
import socket
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

LOGGER = logging.getLogger("simulate.email")


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    tls_mode: str


def _redact(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def send_plain_text_email(
    config: SmtpConfig,
    *,
    sender_email: str,
    sender_name: str,
    recipients: list[str],
    subject: str,
    body: str,
    timeout_seconds: float = 15.0,
    max_attempts: int = 2,
) -> dict[str, Any]:
    if config.tls_mode not in {"starttls", "ssl"}:
        raise ValueError("SMTP_TLS_MODE must be 'starttls' or 'ssl'.")

    message = EmailMessage()
    from_header = sender_email if not sender_name else f"{sender_name} <{sender_email}>"
    message["From"] = from_header
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            if config.tls_mode == "ssl":
                with smtplib.SMTP_SSL(config.host, config.port, timeout=timeout_seconds) as client:
                    client.login(config.username, config.password)
                    client.send_message(message)
            else:
                with smtplib.SMTP(config.host, config.port, timeout=timeout_seconds) as client:
                    client.ehlo()
                    client.starttls()
                    client.ehlo()
                    client.login(config.username, config.password)
                    client.send_message(message)
            return {"ok": True, "attempt": attempt, "message_id": message.get("Message-ID")}
        except (smtplib.SMTPException, OSError, socket.timeout) as exc:
            last_error = exc
            LOGGER.warning(
                "email send attempt failed host=%s port=%s username=%s attempt=%s/%s error=%s",
                _redact(config.host),
                config.port,
                _redact(config.username),
                attempt,
                max_attempts,
                exc,
            )
    assert last_error is not None
    raise RuntimeError(f"SMTP send failed after {max_attempts} attempt(s): {last_error}") from last_error
