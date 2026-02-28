# app/routes/public_certificates.py (or wherever this router is)
from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cert_sign import verify_sig  # should verify against the SAME string you sign
from app.models.certificate import Certificate

router = APIRouter(prefix="/public/certificates", tags=["Public - Certificates"])


def _fmt_dt(dt):
    try:
        return dt.strftime("%d %b %Y, %I:%M %p") if dt else "—"
    except Exception:
        return str(dt) if dt else "—"


def _html_page(title: str, body_html: str) -> str:
    # Minimal, modern, mobile-friendly UI
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0b1220;
      --card: rgba(255,255,255,.06);
      --border: rgba(255,255,255,.12);
      --text: rgba(255,255,255,.92);
      --muted: rgba(255,255,255,.68);
      --good: #22c55e;
      --bad: #ef4444;
      --warn: #f59e0b;
      --chip: rgba(255,255,255,.08);
      --shadow: 0 20px 60px rgba(0,0,0,.45);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
      background: radial-gradient(1200px 700px at 20% 10%, rgba(59,130,246,.25), transparent 60%),
                  radial-gradient(900px 600px at 80% 30%, rgba(34,197,94,.16), transparent 60%),
                  radial-gradient(900px 600px at 60% 90%, rgba(245,158,11,.14), transparent 60%),
                  var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px 16px;
    }}
    .wrap {{ width: 100%; max-width: 860px; }}
    .brand {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 14px;
    }}
    .brand .left {{
      display:flex; gap:12px; align-items:center;
    }}
    .logo {{
      width: 42px; height: 42px; border-radius: 12px;
      background: linear-gradient(135deg, rgba(59,130,246,.85), rgba(34,197,94,.75));
      box-shadow: 0 10px 26px rgba(0,0,0,.35);
    }}
    .brand h1 {{ font-size: 16px; margin: 0; letter-spacing: .2px; }}
    .brand p {{ margin: 2px 0 0; font-size: 13px; color: var(--muted); }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .top {{
      padding: 22px 22px 14px;
      border-bottom: 1px solid var(--border);
      display:flex; gap:14px; align-items:flex-start;
    }}
    .statusIcon {{
      width: 46px; height: 46px; border-radius: 14px;
      display:grid; place-items:center; flex: 0 0 auto;
      border: 1px solid var(--border);
      background: rgba(255,255,255,.05);
    }}
    .statusIcon.good {{ outline: 2px solid rgba(34,197,94,.25); }}
    .statusIcon.bad {{ outline: 2px solid rgba(239,68,68,.25); }}
    .statusIcon.warn {{ outline: 2px solid rgba(245,158,11,.25); }}
    .title {{
      flex: 1 1 auto;
    }}
    .title h2 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: .2px;
    }}
    .title .sub {{
      margin-top: 6px;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .pill {{
      display:inline-flex; align-items:center; gap:8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: var(--chip);
      border: 1px solid var(--border);
      font-size: 12.5px;
      color: var(--muted);
      white-space: nowrap;
    }}
    .grid {{
      display:grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      padding: 18px 22px 22px;
    }}
    @media (max-width: 720px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .brand {{ flex-direction: column; align-items:flex-start; gap: 8px; }}
    }}
    .section {{
      border: 1px solid var(--border);
      background: rgba(255,255,255,.04);
      border-radius: 16px;
      padding: 14px 14px 10px;
    }}
    .section h3 {{
      margin: 0 0 10px;
      font-size: 13px;
      color: var(--muted);
      letter-spacing: .2px;
      text-transform: uppercase;
    }}
    .row {{
      display:flex; justify-content: space-between; gap: 12px;
      padding: 10px 0;
      border-top: 1px dashed rgba(255,255,255,.12);
    }}
    .row:first-of-type {{ border-top: none; }}
    .k {{ color: var(--muted); font-size: 13px; }}
    .v {{ font-size: 13.5px; text-align:right; word-break: break-word; }}
    .footer {{
      padding: 16px 22px 20px;
      border-top: 1px solid var(--border);
      display:flex; justify-content: space-between; gap: 10px; flex-wrap: wrap;
    }}
    .hint {{
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.4;
    }}
    a.btn {{
      display:inline-flex; align-items:center; justify-content:center;
      padding: 10px 14px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,.06);
      color: var(--text);
      text-decoration: none;
      font-size: 13px;
    }}
    .goodTxt {{ color: var(--good); }}
    .badTxt {{ color: var(--bad); }}
    .warnTxt {{ color: var(--warn); }}
    code {{
      padding: 2px 6px;
      border-radius: 8px;
      background: rgba(255,255,255,.06);
      border: 1px solid rgba(255,255,255,.10);
      color: rgba(255,255,255,.85);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="brand">
      <div class="left">
        <div class="logo"></div>
        <div>
          <h1>Vikasana Foundation — Certificate Verification</h1>
          <p>Scan / open the QR link to validate authenticity.</p>
        </div>
      </div>
      <div class="pill">Public verify • Read-only</div>
    </div>

    <div class="card">
      {body_html}
      <div class="footer">
        <div class="hint">
          If this page shows <span class="badTxt">Invalid</span>, the link may be tampered or the certificate is revoked.<br/>
          For support, contact the institution/admin.
        </div>
        <a class="btn" href="javascript:window.print()">Print</a>
      </div>
    </div>
  </div>
</body>
</html>"""


@router.get("/verify", response_class=HTMLResponse)
async def verify_certificate(
    request: Request,
    cert_id: str = Query(..., description="Certificate number (preferred) or numeric id"),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # 1) Signature check
    # IMPORTANT: verify against the SAME value you used in sign_cert().
    # In your PDF generation you sign cert.certificate_no, so verify against cert_id (string).
    if not verify_sig(cert_id, sig):
        body = f"""
        <div class="top">
          <div class="statusIcon bad">✕</div>
          <div class="title">
            <h2 class="badTxt">Invalid certificate link</h2>
            <div class="sub">Signature verification failed. The URL may be modified or corrupted.</div>
          </div>
          <div class="pill">Status: <span class="badTxt">INVALID</span></div>
        </div>
        <div class="grid">
          <div class="section">
            <h3>Details</h3>
            <div class="row"><div class="k">Provided cert_id</div><div class="v"><code>{cert_id}</code></div></div>
          </div>
          <div class="section">
            <h3>What to do</h3>
            <div class="row"><div class="k">Try</div><div class="v">Rescan the QR code</div></div>
            <div class="row"><div class="k">Or</div><div class="v">Request a fresh certificate link</div></div>
          </div>
        </div>
        """
        return HTMLResponse(_html_page("Certificate Verification — Invalid", body), status_code=400)

    # 2) Fetch certificate (prefer certificate_no; fallback numeric id)
    stmt = (
        select(Certificate)
        .options(selectinload(Certificate.student), selectinload(Certificate.event))
    )

    # Try certificate_no match first
    stmt1 = stmt.where(Certificate.certificate_no == cert_id)
    res = await db.execute(stmt1)
    cert = res.scalar_one_or_none()

    # Fallback: numeric id
    if cert is None and cert_id.isdigit():
        res2 = await db.execute(stmt.where(Certificate.id == int(cert_id)))
        cert = res2.scalar_one_or_none()

    if not cert or cert.revoked_at is not None:
        reason = "Revoked" if (cert and cert.revoked_at is not None) else "Not found"
        body = f"""
        <div class="top">
          <div class="statusIcon warn">!</div>
          <div class="title">
            <h2 class="warnTxt">Certificate not valid</h2>
            <div class="sub">The signature is correct, but the certificate is <b>{reason.lower()}</b>.</div>
          </div>
          <div class="pill">Status: <span class="warnTxt">NOT VALID</span></div>
        </div>
        <div class="grid">
          <div class="section">
            <h3>Lookup</h3>
            <div class="row"><div class="k">cert_id</div><div class="v"><code>{cert_id}</code></div></div>
            <div class="row"><div class="k">Result</div><div class="v">{reason}</div></div>
          </div>
          <div class="section">
            <h3>Next steps</h3>
            <div class="row"><div class="k">Action</div><div class="v">Contact admin for re-issue</div></div>
          </div>
        </div>
        """
        return HTMLResponse(_html_page("Certificate Verification — Not valid", body), status_code=200)

    # 3) Valid UI
    student = cert.student
    event = cert.event

    body = f"""
    <div class="top">
      <div class="statusIcon good">✓</div>
      <div class="title">
        <h2 class="goodTxt">Certificate verified</h2>
        <div class="sub">This certificate is authentic and was issued by the system.</div>
      </div>
      <div class="pill">Status: <span class="goodTxt">VALID</span></div>
    </div>

    <div class="grid">
      <div class="section">
        <h3>Certificate</h3>
        <div class="row"><div class="k">Certificate No</div><div class="v"><code>{cert.certificate_no}</code></div></div>
        <div class="row"><div class="k">Issued At</div><div class="v">{_fmt_dt(cert.issued_at)}</div></div>
        <div class="row"><div class="k">Event</div><div class="v">{getattr(event, "title", None) or getattr(event, "name", None) or "—"}</div></div>
      </div>

      <div class="section">
        <h3>Student</h3>
        <div class="row"><div class="k">Name</div><div class="v">{getattr(student, "name", None) or "—"}</div></div>
        <div class="row"><div class="k">USN</div><div class="v">{getattr(student, "usn", None) or "—"}</div></div>
        <div class="row"><div class="k">College</div><div class="v">{getattr(student, "college", None) or "—"}</div></div>
        <div class="row"><div class="k">Branch</div><div class="v">{getattr(student, "branch", None) or "—"}</div></div>
      </div>
    </div>
    """
    return HTMLResponse(_html_page("Certificate Verification — Valid", body), status_code=200)