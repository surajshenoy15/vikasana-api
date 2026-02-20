import os
import httpx


async def send_activation_email(to_email: str, to_name: str, activate_url: str) -> None:
    api_key = os.getenv("SENDINBLUE_API_KEY", "")
    if not api_key:
        raise RuntimeError("SENDINBLUE_API_KEY not configured")

    from_email = os.getenv("EMAIL_FROM", "admin@vikasana.org")
    from_name  = os.getenv("EMAIL_FROM_NAME", "Vikasana Foundation")
    subject    = "You're invited — Activate your Faculty Account"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Activate your Faculty Account</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Helvetica,Arial,sans-serif;">

  <!-- Wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:40px 16px;">
    <tr>
      <td align="center">

        <!-- Card -->
        <table width="560" cellpadding="0" cellspacing="0"
               style="max-width:560px;width:100%;background:#ffffff;border-radius:20px;
                      overflow:hidden;box-shadow:0 4px 32px rgba(0,0,0,0.08);">

          <!-- Header band -->
          <tr>
            <td style="background:linear-gradient(135deg,#0f2557 0%,#1565c0 60%,#1976d2 100%);
                       padding:36px 40px 32px;text-align:center;">

              <!-- Logo row -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom:20px;">
                    <!-- Vikasana logo mark (SVG inline — no external image needed) -->
                    <div style="display:inline-flex;align-items:center;gap:10px;">
                      <!-- Shield / V mark -->
                      <svg width="42" height="42" viewBox="0 0 42 42" fill="none"
                           xmlns="http://www.w3.org/2000/svg">
                        <rect width="42" height="42" rx="12" fill="white" fill-opacity="0.15"/>
                        <path d="M21 8 L34 13 L34 22 C34 29 27.5 35 21 37 C14.5 35 8 29 8 22 L8 13 Z"
                              fill="none" stroke="white" stroke-width="2" stroke-linejoin="round"/>
                        <path d="M15 21 L19.5 27 L27 16"
                              stroke="#fbbf24" stroke-width="2.5"
                              stroke-linecap="round" stroke-linejoin="round"/>
                      </svg>
                      <div style="text-align:left;">
                        <div style="color:#ffffff;font-size:18px;font-weight:700;
                                    letter-spacing:0.3px;line-height:1.1;">
                          Vikasana
                        </div>
                        <div style="color:rgba(255,255,255,0.65);font-size:11px;
                                    letter-spacing:1.5px;text-transform:uppercase;">
                          Foundation
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </table>

              <!-- Headline -->
              <h1 style="margin:0;color:#ffffff;font-size:26px;font-weight:700;
                         line-height:1.3;letter-spacing:-0.3px;">
                Welcome to the team,<br/>{to_name}!
              </h1>
              <p style="margin:12px 0 0;color:rgba(255,255,255,0.75);font-size:15px;
                        line-height:1.5;">
                Your faculty account is ready — one click to get started.
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px 28px;">

              <!-- Info box -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#f8faff;border:1px solid #e3eaf7;
                            border-radius:12px;margin-bottom:28px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 6px;color:#64748b;font-size:12px;
                               text-transform:uppercase;letter-spacing:1px;font-weight:600;">
                      Account Details
                    </p>
                    <p style="margin:0;color:#0f172a;font-size:15px;font-weight:600;">
                      {to_email}
                    </p>
                    <p style="margin:6px 0 0;color:#64748b;font-size:13px;">
                      Role: <strong style="color:#1565c0;">Faculty Member</strong>
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 24px;color:#334155;font-size:15px;line-height:1.7;">
                You've been invited to join the <strong>Vikasana Foundation</strong> Social
                Activity Tracking platform. Click the button below to activate your account
                and set your password.
              </p>

              <!-- CTA Button -->
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" style="padding-bottom:28px;">
                    <a href="{activate_url}"
                       style="display:inline-block;background:linear-gradient(135deg,#1565c0,#1976d2);
                              color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;
                              letter-spacing:0.3px;padding:15px 40px;border-radius:12px;
                              box-shadow:0 4px 14px rgba(21,101,192,0.35);">
                      ✦ &nbsp; Activate My Account &nbsp; ✦
                    </a>
                  </td>
                </tr>
              </table>

              <!-- Expiry note -->
              <table width="100%" cellpadding="0" cellspacing="0"
                     style="background:#fffbeb;border:1px solid #fde68a;
                            border-radius:10px;margin-bottom:24px;">
                <tr>
                  <td style="padding:14px 18px;">
                    <p style="margin:0;color:#92400e;font-size:13px;line-height:1.5;">
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
                   style="color:#1565c0;word-break:break-all;font-size:11px;">
                  {activate_url}
                </a>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8faff;border-top:1px solid #e8eef6;
                       padding:20px 40px;text-align:center;">
              <p style="margin:0 0 4px;color:#94a3b8;font-size:12px;">
                You received this because an admin added you to the Vikasana platform.
              </p>
              <p style="margin:0;color:#cbd5e1;font-size:11px;">
                If you didn't expect this, safely ignore this email.
                &nbsp;·&nbsp;
                <a href="mailto:{from_email}" style="color:#94a3b8;text-decoration:none;">
                  Contact Support
                </a>
              </p>
              <p style="margin:12px 0 0;color:#cbd5e1;font-size:11px;letter-spacing:0.5px;">
                © 2026 Vikasana Foundation · Social Activity Tracking Platform
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

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to":     [{"email": to_email, "name": to_name}],
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
            raise RuntimeError(f"Brevo error {r.status_code}: {r.text}")