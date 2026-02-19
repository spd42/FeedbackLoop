from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import mimetypes
import smtplib

from .config import Settings


def send_email(
    settings: Settings, subject: str, body: str, attachments: list[Path]
) -> None:
    if not all(
        [
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from,
            settings.smtp_to,
        ]
    ):
        raise ValueError("SMTP settings are incomplete")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg.set_content(body)

    for path in attachments:
        mime, _ = mimetypes.guess_type(str(path))
        maintype, subtype = (
            mime.split("/", 1) if mime else ("application", "octet-stream")
        )
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=path.name,
            )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)
