from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import Settings
from app.integrations import email_templates as templates


class Notifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sent: list[dict] = []

    def send_email(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        *,
        meta: dict | None = None,
    ) -> dict:
        recipient = (to or self.settings.mail_from).strip()
        message = {
            "channel": "email",
            "to": recipient,
            "subject": subject,
            "body": text,
            "html": html or "",
            "backend": self.settings.mail_backend,
            **(meta or {}),
        }
        if self.settings.mail_backend == "smtp":
            message["smtp_host"] = self.settings.smtp_host
            self._deliver_smtp(recipient, subject, text, html or text)
        self.sent.append(message)
        return message

    def _deliver_smtp(self, to: str, subject: str, text: str, html: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.settings.mail_from
        msg["To"] = to
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as server:
            server.starttls()
            if self.settings.smtp_user:
                server.login(self.settings.smtp_user, self.settings.smtp_password)
            server.sendmail(self.settings.mail_from, [to], msg.as_string())

    def send_sms(self, to: str, body: str) -> dict:
        message = {"channel": "sms", "to": to, "body": body}
        self.sent.append(message)
        return message

    def welcome(self, email: str, name: str) -> None:
        subject, text, html = templates.welcome_html(name, self.settings.web_app_url)
        self.send_email(email, subject, text, html)

    def login_otp(self, email: str, name: str, code: str) -> None:
        subject, text, html = templates.login_otp_html(name, code)
        self.send_email(email, subject, text, html, meta={"code": code})

    def password_reset(self, email: str, name: str, token: str) -> None:
        reset_url = f"{self.settings.web_app_url.rstrip('/')}/reset-password?token={token}"
        subject, text, html = templates.password_reset_html(name, reset_url)
        self.send_email(email, subject, text, html, meta={"token": token, "reset_url": reset_url})

    def password_changed(self, email: str, name: str) -> None:
        subject, text, html = templates.password_changed_html(name)
        self.send_email(email, subject, text, html)

    def order_placed(self, email: str, phone: str, public_id: str, name: str = "there") -> None:
        subject, text, html = templates.order_event_html(
            name=name or "there",
            public_id=public_id,
            headline="Preorder confirmed",
            detail="We’ve received your Slow Mo preorder. Next up: consult and prescription when needed.",
            app_url=self.settings.web_app_url,
            subject=f"Order {public_id} confirmed",
        )
        self.send_email(email or self.settings.mail_from, subject, text, html)
        if phone:
            self.send_sms(phone, f"Slow Mo order {public_id} confirmed.")
        self.staff_alert("New order", f"A new preorder was placed.", public_id)

    def order_paid(self, email: str, public_id: str, name: str = "there") -> None:
        subject, text, html = templates.order_event_html(
            name=name or "there",
            public_id=public_id,
            headline="Payment received",
            detail="Thanks — your prepaid payment cleared. We’ll continue with your consult flow.",
            app_url=self.settings.web_app_url,
            subject=f"Payment received for {public_id}",
        )
        self.send_email(email or self.settings.mail_from, subject, text, html)

    def order_status(self, email: str, public_id: str, status: str, name: str = "there") -> None:
        labels = {
            "confirmed": ("Order confirmed", "Your order is confirmed and moving toward dispatch."),
            "cancelled": ("Order cancelled", "Your order was cancelled. Reach out if this was unexpected."),
            "hold": ("Order on hold", "Your order is temporarily on hold while we review details."),
            "dispatched": ("Order dispatched", "Your Slow Mo order is on its way."),
            "delivered": ("Order delivered", "Your Slow Mo order was marked delivered. Enjoy the slower nights."),
            "consult": ("Consult upcoming", "Your consult step is next — keep an eye on your inbox."),
        }
        headline, detail = labels.get(status, (f"Order update: {status}", f"Your order status is now {status}."))
        subject, text, html = templates.order_event_html(
            name=name or "there",
            public_id=public_id,
            headline=headline,
            detail=detail,
            app_url=self.settings.web_app_url,
            subject=f"{headline} · {public_id}",
        )
        self.send_email(email or self.settings.mail_from, subject, text, html)

    def rx_decision(self, email: str, public_id: str, accepted: bool, name: str = "there") -> None:
        if accepted:
            headline, detail = "Prescription accepted", "Your prescription was verified. We’ll prepare the next steps."
        else:
            headline, detail = "Prescription needs attention", "We couldn’t accept the uploaded prescription. Please upload a clearer copy or book a consult."
        subject, text, html = templates.order_event_html(
            name=name or "there",
            public_id=public_id,
            headline=headline,
            detail=detail,
            app_url=self.settings.web_app_url,
            subject=f"{headline} · {public_id}",
        )
        self.send_email(email or self.settings.mail_from, subject, text, html)

    def consult_update(self, email: str, public_id: str, detail: str, name: str = "there") -> None:
        subject, text, html = templates.order_event_html(
            name=name or "there",
            public_id=public_id,
            headline="Consult update",
            detail=detail,
            app_url=self.settings.web_app_url,
            subject=f"Consult update · {public_id}",
        )
        self.send_email(email or self.settings.mail_from, subject, text, html)

    def staff_alert(self, title: str, detail: str, public_id: str = "") -> None:
        subject, text, html = templates.staff_alert_html(title=title, detail=detail, public_id=public_id)
        self.send_email(self.settings.seed_founder_email or self.settings.mail_from, subject, text, html)
