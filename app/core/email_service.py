import os
import httpx


async def send_activation_email(to_email: str, to_name: str, activate_url: str) -> None:
    api_key = os.getenv("SENDINBLUE_API_KEY", "")
    if not api_key:
        raise RuntimeError("SENDINBLUE_API_KEY not configured")

    from_email = os.getenv("EMAIL_FROM", "admin@vikasana.org")
    from_name = os.getenv("EMAIL_FROM_NAME", "Vikasana Foundation")

    subject = "Activate your Faculty Account"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px">
      <h2 style="margin:0 0 12px 0;">Welcome, {to_name}</h2>
      <p style="margin:0 0 16px 0;color:#444;line-height:1.5;">
        Your faculty account has been created. Please activate your account using the button below.
      </p>

      <a href="{activate_url}"
         style="display:inline-block;background:#0b5ed7;color:#fff;text-decoration:none;
                padding:12px 18px;border-radius:10px;font-weight:700;">
        ACTIVATE NOW
      </a>

      <p style="margin:18px 0 0 0;color:#666;font-size:12px;">
        If you did not request this, you can ignore this email.
      </p>
    </div>
    """

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Sendinblue error {r.status_code}: {r.text}")