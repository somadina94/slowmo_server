from __future__ import annotations

BRAND = {
    "name": "Slow Mo",
    "tagline": "Take one, take it slow.",
    "accent": "#3E2A6E",
    "ink": "#1A1425",
    "muted": "#6B6475",
    "bg": "#F7F4EF",
    "card": "#FFFFFF",
    "berry": "#9B2D4A",
}


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_email(
    *,
    title: str,
    greeting: str,
    body_html: str,
    cta_label: str | None = None,
    cta_url: str | None = None,
    footnote: str = "If you didn’t request this, you can ignore this email.",
) -> str:
    cta = ""
    if cta_label and cta_url:
        cta = f"""
        <p style="margin:28px 0 8px;">
          <a href="{_escape(cta_url)}" style="display:inline-block;background:{BRAND['accent']};color:#fff;text-decoration:none;padding:12px 22px;border-radius:999px;font-weight:600;font-size:14px;">
            {_escape(cta_label)}
          </a>
        </p>
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{_escape(title)}</title></head>
<body style="margin:0;padding:0;background:{BRAND['bg']};font-family:'DM Sans',Helvetica,Arial,sans-serif;color:{BRAND['ink']};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{BRAND['bg']};padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" style="max-width:560px;background:{BRAND['card']};border-radius:20px;overflow:hidden;box-shadow:0 12px 40px rgba(26,20,37,0.08);">
        <tr><td style="padding:28px 32px 12px;background:linear-gradient(135deg,#3E2A6E 0%,#6B4FA0 100%);">
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:28px;color:#fff;letter-spacing:0.02em;">{BRAND['name']}</div>
          <div style="color:rgba(255,255,255,0.82);font-size:13px;margin-top:4px;">{BRAND['tagline']}</div>
        </td></tr>
        <tr><td style="padding:28px 32px 8px;">
          <h1 style="margin:0 0 12px;font-family:Georgia,'Times New Roman',serif;font-size:24px;font-weight:500;color:{BRAND['ink']};">{_escape(title)}</h1>
          <p style="margin:0 0 16px;font-size:15px;line-height:1.55;color:{BRAND['ink']};">{_escape(greeting)}</p>
          <div style="font-size:15px;line-height:1.6;color:{BRAND['ink']};">{body_html}</div>
          {cta}
        </td></tr>
        <tr><td style="padding:8px 32px 28px;">
          <p style="margin:0;font-size:12px;line-height:1.5;color:{BRAND['muted']};">{_escape(footnote)}</p>
        </td></tr>
      </table>
      <p style="margin:18px 0 0;font-size:11px;color:{BRAND['muted']};">© Slow Mo · wellness, gently</p>
    </td></tr>
  </table>
</body>
</html>"""


def code_block(code: str) -> str:
    return (
        f'<p style="margin:20px 0;text-align:center;letter-spacing:0.35em;font-size:32px;font-weight:700;'
        f'color:{BRAND["accent"]};font-family:ui-monospace,Menlo,Consolas,monospace;">{_escape(code)}</p>'
    )


def welcome_html(name: str, app_url: str) -> tuple[str, str, str]:
    subject = "Welcome to Slow Mo"
    text = f"Hi {name},\n\nYour Slow Mo account is ready. Take one, take it slow.\n{app_url}\n"
    html = render_email(
        title="You’re in.",
        greeting=f"Hi {name},",
        body_html="<p>Your Slow Mo account is ready. Browse the preorder flow whenever you’re ready for slower evenings.</p>",
        cta_label="Start preorder",
        cta_url=f"{app_url.rstrip('/')}/preorder",
        footnote="Questions? Just reply to this email.",
    )
    return subject, text, html


def login_otp_html(name: str, code: str) -> tuple[str, str, str]:
    subject = "Your Slow Mo login code"
    text = f"Hi {name},\n\nYour login code is {code}. It expires in 10 minutes.\n"
    html = render_email(
        title="Verify it’s you",
        greeting=f"Hi {name},",
        body_html=f"<p>Use this 6-digit code to finish signing in. It expires in <strong>10 minutes</strong>.</p>{code_block(code)}",
        footnote="If you didn’t try to log in, change your password and contact support.",
    )
    return subject, text, html


def password_reset_html(name: str, reset_url: str) -> tuple[str, str, str]:
    subject = "Reset your Slow Mo password"
    text = f"Hi {name},\n\nReset your password: {reset_url}\nThis link expires in 30 minutes.\n"
    html = render_email(
        title="Reset your password",
        greeting=f"Hi {name},",
        body_html="<p>We received a request to reset your password. This link expires in <strong>30 minutes</strong>.</p>",
        cta_label="Choose a new password",
        cta_url=reset_url,
    )
    return subject, text, html


def password_changed_html(name: str) -> tuple[str, str, str]:
    subject = "Your Slow Mo password was changed"
    text = f"Hi {name},\n\nYour Slow Mo password was changed successfully.\n"
    html = render_email(
        title="Password updated",
        greeting=f"Hi {name},",
        body_html="<p>Your password was changed successfully. If this wasn’t you, contact support right away.</p>",
        footnote="Security notice from Slow Mo.",
    )
    return subject, text, html


def order_event_html(
    *,
    name: str,
    public_id: str,
    headline: str,
    detail: str,
    app_url: str,
    subject: str | None = None,
) -> tuple[str, str, str]:
    subject = subject or f"Slow Mo order {public_id}"
    text = f"Hi {name},\n\n{headline}\n{detail}\nOrder: {public_id}\n"
    html = render_email(
        title=headline,
        greeting=f"Hi {name},",
        body_html=f"<p>{_escape(detail)}</p><p style='margin-top:16px;font-size:13px;color:{BRAND['muted']};'>Order <strong>{_escape(public_id)}</strong></p>",
        cta_label="View order",
        cta_url=f"{app_url.rstrip('/')}/account/orders/{public_id}",
        footnote="We’ll keep you posted as your order moves along.",
    )
    return subject, text, html


def staff_alert_html(*, title: str, detail: str, public_id: str = "") -> tuple[str, str, str]:
    subject = f"[Slow Mo] {title}"
    extra = f" ({public_id})" if public_id else ""
    text = f"{title}{extra}\n\n{detail}\n"
    html = render_email(
        title=title,
        greeting="Team,",
        body_html=f"<p>{_escape(detail)}</p>"
        + (f"<p style='margin-top:12px;font-size:13px;color:{BRAND['muted']};'>Ref <strong>{_escape(public_id)}</strong></p>" if public_id else ""),
        footnote="Internal Slow Mo notification.",
    )
    return subject, text, html
