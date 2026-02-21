import os
import httpx


# ══════════════════════════════════════════════════════════════
#  Shared helpers
# ══════════════════════════════════════════════════════════════

def _brevo_cfg() -> tuple[str, str, str]:
    api_key = os.getenv("SENDINBLUE_API_KEY", "")
    if not api_key:
        raise RuntimeError("SENDINBLUE_API_KEY not configured")
    from_email = os.getenv("EMAIL_FROM", "admin@vikasana.org")
    from_name  = os.getenv("EMAIL_FROM_NAME", "Vikasana Foundation")
    return api_key, from_email, from_name


async def _send(api_key: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Brevo error {r.status_code}: {r.text}")


def _wrap(body_html: str) -> str:
    """Wrap content in a shared branded shell with dark outer bg and footer."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Vikasana Foundation</title>
</head>
<body style="margin:0;padding:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;
             background:#0f172a;">

  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#0f172a;padding:40px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="580" cellpadding="0" cellspacing="0"
               style="max-width:580px;width:100%;background:#ffffff;
                      border-radius:24px;overflow:hidden;
                      box-shadow:0 25px 60px rgba(0,0,0,0.45);">

          <!-- Rainbow top bar -->
          <tr>
            <td style="height:6px;background:linear-gradient(90deg,#6366f1,#8b5cf6,#ec4899);
                       font-size:0;line-height:0;">&nbsp;</td>
          </tr>

          {body_html}

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;border-top:1px solid #e2e8f0;
                       padding:20px 32px;text-align:center;">
              <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.7;">
                © 2026 Vikasana Foundation · Social Activity Tracking Platform<br/>
                You received this email because you were added to our platform.
              </p>
            </td>
          </tr>

        </table>
        <!-- /Card -->

      </td>
    </tr>
  </table>

</body>
</html>"""


def _store_buttons(play_url: str, apple_url: str) -> str:
    """Render Play Store + App Store CTA buttons (inline SVG, no external images)."""
    return f"""
    <tr>
      <td align="center" style="padding:28px 0 0;">
        <table cellpadding="0" cellspacing="0">
          <tr>
            <!-- Google Play -->
            <td style="padding-right:10px;">
              <a href="{play_url}" target="_blank"
                 style="display:inline-block;background:#1a1a2e;color:#fff;
                        text-decoration:none;border-radius:12px;padding:0;
                        border:1px solid #334155;overflow:hidden;">
                <table cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:11px 16px;vertical-align:middle;">
                      <svg width="22" height="22" viewBox="0 0 512 512"
                           xmlns="http://www.w3.org/2000/svg">
                        <path d="M40 28L280 256 40 484V28Z" fill="#00C853"/>
                        <path d="M40 28L280 256 40 484C24 475 14 458 14 440V72C14 54 24 37 40 28Z"
                              fill="#00C853"/>
                        <path d="M280 256L40 28l214 123.5L280 256Z" fill="#FFEB3B"/>
                        <path d="M280 256l-26 110L40 484 280 256Z" fill="#F44336"/>
                        <path d="M280 256l178-103c14 8 23 23 23 40v114c0 17-9 32-23 40L280 256Z"
                              fill="#2196F3"/>
                      </svg>
                    </td>
                    <td style="padding:11px 16px 11px 0;vertical-align:middle;">
                      <div style="font-size:9px;color:#94a3b8;font-weight:400;
                                  letter-spacing:.5px;line-height:1.2;">GET IT ON</div>
                      <div style="font-size:13px;color:#fff;font-weight:700;
                                  line-height:1.3;white-space:nowrap;">Google Play</div>
                    </td>
                  </tr>
                </table>
              </a>
            </td>

            <!-- App Store -->
            <td style="padding-left:10px;">
              <a href="{apple_url}" target="_blank"
                 style="display:inline-block;background:#1a1a2e;color:#fff;
                        text-decoration:none;border-radius:12px;padding:0;
                        border:1px solid #334155;overflow:hidden;">
                <table cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding:11px 16px;vertical-align:middle;">
                      <svg width="22" height="22" viewBox="0 0 814 1000" fill="white"
                           xmlns="http://www.w3.org/2000/svg">
                        <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5
                                 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9
                                 -42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.3-164-39.3
                                 c-76.5 0-103.7 40.8-165.9 40.8s-105-42.4-148.2-107
                                 C46.2 791.2 0 666.3 0 546.8 0 343.9 126.4 236.1 250.8 236.1
                                 c66.1 0 121.2 43.4 162.7 43.4 39.5 0 101.1-46 176.3-46
                                 28.5 0 130.9 2.6 198.3 99.2zm-234-181.5
                                 c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1
                                 -50.6 1.9-110.8 33.7-147.1 75.8-28.5 32.4-55.1 83.6-55.1 135.5
                                 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3
                                 45.4 0 102.5-30.4 135.5-71.3z"/>
                      </svg>
                    </td>
                    <td style="padding:11px 16px 11px 0;vertical-align:middle;">
                      <div style="font-size:9px;color:#94a3b8;font-weight:400;
                                  letter-spacing:.5px;line-height:1.2;">DOWNLOAD ON THE</div>
                      <div style="font-size:13px;color:#fff;font-weight:700;
                                  line-height:1.3;white-space:nowrap;">App Store</div>
                    </td>
                  </tr>
                </table>
              </a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    """


def _otp_digits(otp: str) -> str:
    """Render each OTP digit in its own styled box."""
    boxes = "".join([
        f"""<td style="padding:0 4px;">
              <div style="width:44px;height:52px;line-height:52px;text-align:center;
                          font-size:26px;font-weight:800;background:#f1f5f9;
                          border-radius:10px;border:2px solid #e2e8f0;
                          color:#1e1b4b;">{d}</div>
            </td>"""
        for d in otp
    ])
    return f"""
    <table cellpadding="0" cellspacing="0" style="margin:0 auto;">
      <tr>{boxes}</tr>
    </table>
    """


# ══════════════════════════════════════════════════════════════
#  1. Faculty — Activation / Invite Email
# ══════════════════════════════════════════════════════════════

async def send_activation_email(to_email: str, to_name: str, activate_url: str) -> None:
    api_key, from_email, from_name = _brevo_cfg()
    subject = "You're invited — Activate your Faculty Account"

    body = f"""
          <!-- Hero -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 60%,#312e81 100%);
                       padding:48px 40px 40px;text-align:center;">

              <!-- Logo -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom:22px;">
                    <table cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="padding-right:12px;vertical-align:middle;">
                          <svg width="44" height="44" viewBox="0 0 42 42" fill="none"
                               xmlns="http://www.w3.org/2000/svg">
                            <rect width="42" height="42" rx="12"
                                  fill="white" fill-opacity="0.15"/>
                            <path d="M21 8L34 13L34 22C34 29 27.5 35 21 37C14.5 35 8 29 8 22L8 13Z"
                                  fill="none" stroke="white" stroke-width="2"
                                  stroke-linejoin="round"/>
                            <path d="M15 21L19.5 27L27 16"
                                  stroke="#fbbf24" stroke-width="2.5"
                                  stroke-linecap="round" stroke-linejoin="round"/>
                          </svg>
                        </td>
                        <td style="vertical-align:middle;text-align:left;">
                          <div style="color:#fff;font-size:18px;font-weight:700;
                                      letter-spacing:.3px;line-height:1.1;">Vikasana</div>
                          <div style="color:rgba(255,255,255,.6);font-size:11px;
                                      letter-spacing:1.5px;text-transform:uppercase;">Foundation</div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <h1 style="margin:0;color:#fff;font-size:26px;font-weight:800;
                         line-height:1.3;letter-spacing:-.3px;">
                Welcome to the team,<br/>{to_name}!
              </h1>
              <p style="margin:12px 0 0;color:rgba(255,255,255,.75);font-size:15px;
                        line-height:1.5;">
                Your faculty account is ready — one click to get started.
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px 32px;">

              <!-- Account details card -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f8faff;border:1px solid #e3eaf7;
                            border-radius:14px;margin-bottom:28px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 4px;color:#64748b;font-size:11px;
                               text-transform:uppercase;letter-spacing:1px;font-weight:600;">
                      Account Details
                    </p>
                    <p style="margin:0;color:#0f172a;font-size:15px;font-weight:700;">
                      {to_email}
                    </p>
                    <p style="margin:6px 0 0;color:#64748b;font-size:13px;">
                      Role: <strong style="color:#6366f1;">Faculty Member</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 28px;color:#334155;font-size:15px;line-height:1.75;">
                You've been invited to join the <strong>Vikasana Foundation</strong> Social
                Activity Tracking platform. Click the button below to activate your account
                and set your password.
              </p>

              <!-- CTA -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom:28px;">
                    <a href="{activate_url}"
                       style="display:inline-block;
                              background:linear-gradient(135deg,#6366f1,#8b5cf6);
                              color:#ffffff;text-decoration:none;font-size:15px;
                              font-weight:700;letter-spacing:.3px;padding:16px 44px;
                              border-radius:14px;
                              box-shadow:0 6px 20px rgba(99,102,241,0.4);">
                      ✦ &nbsp; Activate My Account &nbsp; ✦
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Expiry note -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#fffbeb;border:1px solid #fde68a;
                            border-radius:12px;margin-bottom:24px;">
                <tr>
                  <td style="padding:14px 18px;">
                    <p style="margin:0;color:#92400e;font-size:13px;line-height:1.6;">
                      ⏱ &nbsp;<strong>This link expires in 48 hours.</strong>
                      If it expires, contact your admin for a new invite.
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Fallback URL -->
              <p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.6;">
                Button not working? Paste this link into your browser:<br/>
                <a href="{activate_url}"
                   style="color:#6366f1;word-break:break-all;font-size:11px;">
                  {activate_url}
                </a>
              </p>
            </td>
          </tr>
    """

    payload = {
        "sender":      {"name": from_name, "email": from_email},
        "to":          [{"email": to_email, "name": to_name}],
        "subject":     subject,
        "htmlContent": _wrap(body),
    }
    await _send(api_key, payload)


# ══════════════════════════════════════════════════════════════
#  2. Faculty — OTP Email  (used after activation link click)
# ══════════════════════════════════════════════════════════════

async def send_faculty_otp_email(to_email: str, to_name: str, otp: str) -> None:
    api_key, from_email, from_name = _brevo_cfg()
    subject = "Your OTP Code — Vikasana Faculty Activation"

    body = f"""
          <!-- Hero -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 60%,#312e81 100%);
                       padding:48px 40px 40px;text-align:center;">
              <div style="font-size:40px;line-height:1;margin-bottom:14px;">🔐</div>
              <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800;">
                Faculty Verification Code
              </h1>
              <p style="margin:10px 0 0;color:rgba(255,255,255,.7);font-size:14px;">
                Vikasana Foundation · Account Activation
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;text-align:center;">
              <p style="margin:0 0 6px;color:#475569;font-size:15px;">
                Hello, <strong>{to_name}</strong>!
              </p>
              <p style="margin:0 0 32px;color:#64748b;font-size:14px;line-height:1.7;">
                Use the one-time code below to continue activating your faculty account.
              </p>

              {_otp_digits(otp)}

              <!-- Expiry badge -->
              <table cellpadding="0" cellspacing="0" style="margin:26px auto;">
                <tr>
                  <td style="background:#fef3c7;border-radius:100px;padding:9px 20px;">
                    <p style="margin:0;font-size:13px;color:#92400e;font-weight:600;">
                      ⏱ &nbsp;Expires in <strong>10 minutes</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Security note -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;">
                <tr>
                  <td style="padding:18px 20px;text-align:left;">
                    <p style="margin:0;font-size:13px;color:#64748b;line-height:1.6;">
                      🛡️ <strong>Security tip:</strong> Vikasana will never ask you to share
                      this code. If you didn't request this, safely ignore this email —
                      your account is safe.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:22px 0 0;font-size:12px;color:#94a3b8;">
                Activating account for <strong>{to_email}</strong>
              </p>
            </td>
          </tr>
    """

    payload = {
        "sender":      {"name": from_name, "email": from_email},
        "to":          [{"email": to_email, "name": to_name}],
        "subject":     subject,
        "htmlContent": _wrap(body),
    }
    await _send(api_key, payload)


# ══════════════════════════════════════════════════════════════
#  3. Student — Welcome / Download Email
# ══════════════════════════════════════════════════════════════

async def send_student_welcome_email(
    to_email: str,
    to_name: str,
    app_download_url: str,
    *,
    play_store_url: str = "https://play.google.com/store/apps/details?id=org.vikasana",
    app_store_url: str  = "https://apps.apple.com/app/vikasana/id000000000",
) -> None:
    api_key, from_email, from_name = _brevo_cfg()
    subject = "Welcome to Vikasana Foundation 🎉"

    steps = [
        ("1", "Download the app from <strong>Play Store</strong> or <strong>App Store</strong> below."),
        ("2", f"Open the app and enter your email: <strong>{to_email}</strong>"),
        ("3", "Receive an OTP in this inbox and log in instantly — no password needed!"),
    ]
    steps_html = "".join([
        f"""<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
              <tr>
                <td width="32" style="vertical-align:top;padding-top:2px;">
                  <div style="width:28px;height:28px;line-height:28px;text-align:center;
                              border-radius:50%;font-size:13px;font-weight:700;color:#fff;
                              background:linear-gradient(135deg,#6366f1,#8b5cf6);">{n}</div>
                </td>
                <td style="padding-left:12px;vertical-align:top;">
                  <p style="margin:0;color:#334155;font-size:14px;line-height:1.65;">{t}</p>
                </td>
              </tr>
            </table>"""
        for n, t in steps
    ])

    body = f"""
          <!-- Hero -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 60%,#312e81 100%);
                       padding:48px 40px 40px;text-align:center;">
              <div style="width:64px;height:64px;line-height:64px;text-align:center;
                          font-size:30px;border-radius:18px;margin:0 auto 18px;
                          background:linear-gradient(135deg,#6366f1,#8b5cf6);">🎓</div>
              <h1 style="margin:0;color:#fff;font-size:26px;font-weight:800;
                         line-height:1.3;letter-spacing:-.3px;">
                Welcome aboard, {to_name}!
              </h1>
              <p style="margin:10px 0 0;color:rgba(255,255,255,.75);font-size:14px;">
                Vikasana Foundation Student Platform
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px 32px;">

              <!-- Email highlight card -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#ede9fe;border-radius:12px;margin-bottom:28px;">
                <tr>
                  <td style="padding:14px 18px;">
                    <table cellpadding="0" cellspacing="0">
                      <tr>
                        <td style="font-size:20px;padding-right:12px;vertical-align:middle;">📧</td>
                        <td style="vertical-align:middle;">
                          <p style="margin:0;font-size:11px;color:#7c3aed;font-weight:700;
                                     text-transform:uppercase;letter-spacing:.5px;">Your login email</p>
                          <p style="margin:2px 0 0;font-size:14px;color:#1e1b4b;font-weight:700;">
                            {to_email}
                          </p>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 22px;color:#334155;font-size:15px;line-height:1.75;">
                Your faculty has added you to the <strong>Vikasana Foundation</strong> learning
                platform. Download the app and log in using OTP — no password required!
              </p>

              <p style="margin:0 0 16px;font-size:12px;font-weight:700;color:#64748b;
                        text-transform:uppercase;letter-spacing:.7px;">How to get started</p>

              {steps_html}

              <!-- Store buttons -->
              <table width="100%" cellpadding="0" cellspacing="0">
                {_store_buttons(play_store_url, app_store_url)}
              </table>

              <!-- Fallback URL -->
              <p style="text-align:center;margin:16px 0 0;font-size:12px;color:#94a3b8;">
                Or visit:&nbsp;
                <a href="{app_download_url}"
                   style="color:#6366f1;font-weight:600;text-decoration:none;">
                  {app_download_url}
                </a>
              </p>

              <p style="margin:28px 0 0;font-size:12px;color:#cbd5e1;text-align:center;">
                Didn't expect this email? You can safely ignore it.
              </p>
            </td>
          </tr>
    """

    payload = {
        "sender":      {"name": from_name, "email": from_email},
        "to":          [{"email": to_email, "name": to_name}],
        "subject":     subject,
        "htmlContent": _wrap(body),
    }
    await _send(api_key, payload)


# ══════════════════════════════════════════════════════════════
#  4. Student — OTP Email
# ══════════════════════════════════════════════════════════════

async def send_student_otp_email(to_email: str, to_name: str, otp: str) -> None:
    api_key, from_email, from_name = _brevo_cfg()
    subject = "Your Login OTP — Vikasana Foundation"

    body = f"""
          <!-- Hero -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 60%,#312e81 100%);
                       padding:48px 40px 40px;text-align:center;">
              <div style="font-size:40px;line-height:1;margin-bottom:14px;">🔐</div>
              <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800;">
                Verification Code
              </h1>
              <p style="margin:10px 0 0;color:rgba(255,255,255,.7);font-size:14px;">
                Vikasana Foundation · Student Login
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;text-align:center;">
              <p style="margin:0 0 6px;color:#475569;font-size:15px;">
                Hello, <strong>{to_name}</strong>!
              </p>
              <p style="margin:0 0 32px;color:#64748b;font-size:14px;line-height:1.7;">
                Use the one-time code below to sign in to your Vikasana account.
              </p>

              {_otp_digits(otp)}

              <!-- Expiry badge -->
              <table cellpadding="0" cellspacing="0" style="margin:26px auto;">
                <tr>
                  <td style="background:#fef3c7;border-radius:100px;padding:9px 20px;">
                    <p style="margin:0;font-size:13px;color:#92400e;font-weight:600;">
                      ⏱ &nbsp;Expires in <strong>10 minutes</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <!-- Security note -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;">
                <tr>
                  <td style="padding:18px 20px;text-align:left;">
                    <p style="margin:0;font-size:13px;color:#64748b;line-height:1.6;">
                      🛡️ <strong>Security tip:</strong> Vikasana will never ask you to share
                      this code with anyone. If you didn't request this, safely ignore this
                      email — your account is safe.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:22px 0 0;font-size:12px;color:#94a3b8;">
                Signing in as <strong>{to_email}</strong>
              </p>
            </td>
          </tr>
    """

    payload = {
        "sender":      {"name": from_name, "email": from_email},
        "to":          [{"email": to_email, "name": to_name}],
        "subject":     subject,
        "htmlContent": _wrap(body),
    }
    await _send(api_key, payload)