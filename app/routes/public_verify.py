from fastapi import APIRouter, Query, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, cast, String
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cert_sign import verify_sig
from app.models.certificate import Certificate

router = APIRouter(prefix="/public/certificates", tags=["Public - Certificates"])


def _fmt_dt(dt):
    try:
        return dt.strftime("%d %b %Y, %I:%M %p") if dt else "—"
    except Exception:
        return str(dt) if dt else "—"


def _html_page(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --navy-900: #0a1628;
      --navy-800: #0f1f3d;
      --navy-700: #162444;
      --navy-600: #1e3260;
      --navy-500: #243a72;
      --gold-400: #f4c842;
      --gold-500: #d4a017;
      --gold-300: #fad96a;
      --gold-glow: rgba(244,200,66,.18);
      --green: #22c55e;
      --red: #ef4444;
      --amber: #f59e0b;
      --text: #f0f4ff;
      --muted: rgba(210,220,255,.62);
      --border: rgba(255,255,255,.09);
      --border-gold: rgba(244,200,66,.25);
      --card-bg: rgba(15,31,61,.72);
      --radius: 20px;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'DM Sans', sans-serif;
      background: var(--navy-900);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 32px 16px;
      overflow-x: hidden;
    }}

    /* ── background decoration ── */
    body::before {{
      content: '';
      position: fixed; inset: 0; pointer-events: none;
      background:
        radial-gradient(ellipse 900px 600px at 15% 0%, rgba(36,58,114,.75) 0%, transparent 65%),
        radial-gradient(ellipse 700px 500px at 85% 100%, rgba(244,200,66,.10) 0%, transparent 60%),
        radial-gradient(ellipse 600px 400px at 50% 50%, rgba(22,36,68,.6) 0%, transparent 70%);
      z-index: 0;
    }}

    /* subtle grid pattern */
    body::after {{
      content: '';
      position: fixed; inset: 0; pointer-events: none;
      background-image:
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
      background-size: 44px 44px;
      z-index: 0;
    }}

    .wrap {{
      position: relative; z-index: 1;
      width: 100%; max-width: 860px;
      animation: fadeUp .5s ease both;
    }}

    @keyframes fadeUp {{
      from {{ opacity:0; transform: translateY(22px); }}
      to   {{ opacity:1; transform: translateY(0); }}
    }}

    /* ── brand header ── */
    .brand {{
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 18px;
      flex-wrap: wrap; gap: 10px;
    }}
    .brand-left {{ display: flex; align-items: center; gap: 14px; }}
    .logo {{
      width: 46px; height: 46px; border-radius: 14px;
      background: linear-gradient(135deg, var(--navy-600) 0%, var(--navy-800) 100%);
      border: 1.5px solid var(--border-gold);
      display: grid; place-items: center;
      box-shadow: 0 6px 20px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.08);
      font-size: 22px;
    }}
    .brand-text h1 {{
      font-family: 'Playfair Display', serif;
      font-size: 17px;
      color: var(--text);
      letter-spacing: .3px;
    }}
    .brand-text p {{
      font-size: 12.5px;
      color: var(--muted);
      margin-top: 2px;
    }}
    .badge {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 6px 12px; border-radius: 999px;
      background: rgba(244,200,66,.08);
      border: 1px solid var(--border-gold);
      color: var(--gold-400);
      font-size: 12px; font-weight: 500;
    }}
    .badge::before {{ content: '🔒'; font-size: 11px; }}

    /* ── card ── */
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      box-shadow:
        0 30px 80px rgba(0,0,0,.5),
        inset 0 1px 0 rgba(255,255,255,.07);
      overflow: hidden;
    }}

    /* ── status top bar ── */
    .top {{
      padding: 24px 24px 18px;
      display: flex; align-items: flex-start; gap: 16px;
      position: relative;
    }}
    .top::after {{
      content: '';
      position: absolute; bottom: 0; left: 24px; right: 24px;
      height: 1px;
      background: linear-gradient(90deg, transparent, var(--border), transparent);
    }}

    .status-icon {{
      width: 52px; height: 52px; border-radius: 16px;
      display: grid; place-items: center; flex: 0 0 auto;
      font-size: 22px;
    }}
    .status-icon.good {{
      background: linear-gradient(135deg, rgba(34,197,94,.18), rgba(34,197,94,.08));
      border: 1.5px solid rgba(34,197,94,.35);
      box-shadow: 0 0 24px rgba(34,197,94,.15);
    }}
    .status-icon.bad {{
      background: linear-gradient(135deg, rgba(239,68,68,.18), rgba(239,68,68,.08));
      border: 1.5px solid rgba(239,68,68,.35);
      box-shadow: 0 0 24px rgba(239,68,68,.15);
    }}
    .status-icon.warn {{
      background: linear-gradient(135deg, rgba(245,158,11,.18), rgba(245,158,11,.08));
      border: 1.5px solid rgba(245,158,11,.35);
      box-shadow: 0 0 24px rgba(245,158,11,.15);
    }}

    .title-block {{ flex: 1; }}
    .title-block h2 {{
      font-family: 'Playfair Display', serif;
      font-size: 22px;
      letter-spacing: .2px;
    }}
    .title-block .sub {{
      margin-top: 6px;
      font-size: 13.5px;
      color: var(--muted);
      line-height: 1.5;
    }}

    .status-pill {{
      display: inline-flex; align-items: center; gap: 7px;
      padding: 7px 14px; border-radius: 999px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,.05);
      font-size: 12.5px; font-weight: 600;
      white-space: nowrap;
      letter-spacing: .3px;
    }}
    .status-pill .dot {{
      width: 7px; height: 7px; border-radius: 50%;
    }}

    .good-txt {{ color: var(--green); }}
    .bad-txt  {{ color: var(--red); }}
    .warn-txt {{ color: var(--amber); }}
    .gold-txt {{ color: var(--gold-400); }}

    /* ── grid sections ── */
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      padding: 20px 24px 24px;
    }}
    @media (max-width: 640px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .brand {{ flex-direction: column; align-items: flex-start; }}
      .top {{ flex-direction: column; }}
    }}

    .section {{
      background: rgba(255,255,255,.03);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px 16px 12px;
      position: relative;
      overflow: hidden;
    }}
    .section::before {{
      content: '';
      position: absolute; top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, rgba(244,200,66,.3), transparent);
    }}

    .section-header {{
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 12px;
    }}
    .section-icon {{
      width: 28px; height: 28px; border-radius: 8px;
      background: rgba(244,200,66,.1);
      border: 1px solid var(--border-gold);
      display: grid; place-items: center;
      font-size: 13px;
    }}
    .section h3 {{
      font-size: 11.5px;
      font-weight: 600;
      color: var(--gold-400);
      letter-spacing: 1px;
      text-transform: uppercase;
    }}

    .row {{
      display: flex; justify-content: space-between; align-items: flex-start;
      gap: 12px; padding: 10px 0;
      border-top: 1px solid rgba(255,255,255,.06);
    }}
    .row:first-of-type {{ border-top: none; }}
    .row-icon {{ font-size: 13px; flex: 0 0 auto; margin-top: 1px; }}
    .k {{
      color: var(--muted);
      font-size: 12.5px;
      display: flex; align-items: center; gap: 6px;
    }}
    .v {{
      font-size: 13.5px;
      text-align: right;
      word-break: break-word;
      font-weight: 500;
    }}

    code {{
      padding: 3px 8px;
      border-radius: 7px;
      background: rgba(244,200,66,.08);
      border: 1px solid rgba(244,200,66,.18);
      color: var(--gold-300);
      font-family: 'Courier New', monospace;
      font-size: 12px;
    }}

    /* ── valid checkmark animation ── */
    @keyframes checkPop {{
      0%   {{ transform: scale(0) rotate(-20deg); opacity:0; }}
      70%  {{ transform: scale(1.2) rotate(5deg); opacity:1; }}
      100% {{ transform: scale(1) rotate(0deg); }}
    }}
    .animate-check {{ animation: checkPop .45s cubic-bezier(.34,1.56,.64,1) .15s both; }}

    /* ── gold shimmer for valid banner ── */
    .valid-banner {{
      background: linear-gradient(135deg,
        rgba(244,200,66,.06) 0%,
        rgba(212,160,23,.04) 50%,
        rgba(244,200,66,.06) 100%);
      border-bottom: 1px solid rgba(244,200,66,.15);
      padding: 10px 24px;
      display: flex; align-items: center; gap: 10px;
      font-size: 12.5px; color: var(--gold-400);
    }}
    .valid-banner::before {{ content: '✦'; opacity:.7; }}

    /* ── footer ── */
    .footer {{
      padding: 16px 24px 20px;
      border-top: 1px solid var(--border);
      display: flex; justify-content: space-between;
      align-items: center; gap: 10px; flex-wrap: wrap;
    }}
    .hint {{
      font-size: 12.5px;
      color: var(--muted);
      line-height: 1.5;
      max-width: 480px;
    }}
    .hint strong {{ color: var(--text); }}

    .btn-row {{ display: flex; gap: 8px; }}
    .btn {{
      display: inline-flex; align-items: center; gap: 7px;
      padding: 9px 16px; border-radius: 11px;
      border: 1px solid var(--border);
      background: rgba(255,255,255,.05);
      color: var(--text);
      text-decoration: none;
      font-size: 13px; font-weight: 500;
      cursor: pointer;
      transition: background .2s, border-color .2s;
    }}
    .btn:hover {{ background: rgba(255,255,255,.09); border-color: rgba(255,255,255,.18); }}
    .btn-gold {{
      background: linear-gradient(135deg, rgba(244,200,66,.18), rgba(244,200,66,.08));
      border-color: var(--border-gold);
      color: var(--gold-400);
    }}
    .btn-gold:hover {{ background: linear-gradient(135deg, rgba(244,200,66,.28), rgba(244,200,66,.14)); }}
  </style>
</head>
<body>
  <div class="wrap">

    <!-- Brand Header -->
    <div class="brand">
      <div class="brand-left">
        <div class="logo">🎓</div>
        <div class="brand-text">
          <h1>Vikasana Foundation</h1>
          <p>Certificate Verification Portal &nbsp;·&nbsp; Scan QR to validate</p>
        </div>
      </div>
      <div class="badge">Public Verify &nbsp;·&nbsp; Read-only</div>
    </div>

    <!-- Main Card -->
    <div class="card">
      {body_html}
      <div class="footer">
        <div class="hint">
          If status shows <strong>Invalid</strong> or <strong>Revoked</strong>, the link may be tampered or the certificate was recalled.
          Contact the institution admin for support.
        </div>
        <div class="btn-row">
          <a class="btn btn-gold" href="javascript:window.print()">🖨 Print</a>
          <a class="btn" href="javascript:window.history.back()">← Back</a>
        </div>
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
    if not verify_sig(cert_id, sig):
        body = f"""
        <div class="top">
          <div class="status-icon bad"><span class="animate-check">✕</span></div>
          <div class="title-block">
            <h2 class="bad-txt">Invalid Certificate Link</h2>
            <div class="sub">Signature verification failed. The URL may have been modified or corrupted — please rescan the original QR code.</div>
          </div>
          <div class="status-pill">
            <span class="dot" style="background:var(--red);box-shadow:0 0 6px var(--red)"></span>
            <span class="bad-txt">INVALID</span>
          </div>
        </div>
        <div class="grid">
          <div class="section">
            <div class="section-header">
              <div class="section-icon">🔍</div>
              <h3>Lookup Details</h3>
            </div>
            <div class="row">
              <span class="k">🪪 Certificate ID</span>
              <span class="v"><code>{cert_id}</code></span>
            </div>
            <div class="row">
              <span class="k">🔐 Signature</span>
              <span class="v bad-txt">Failed</span>
            </div>
          </div>
          <div class="section">
            <div class="section-header">
              <div class="section-icon">💡</div>
              <h3>What To Do</h3>
            </div>
            <div class="row">
              <span class="k">📷 Action 1</span>
              <span class="v">Rescan the QR code on the original certificate</span>
            </div>
            <div class="row">
              <span class="k">📧 Action 2</span>
              <span class="v">Request a fresh certificate link from admin</span>
            </div>
          </div>
        </div>
        """
        return HTMLResponse(_html_page("Certificate Verification — Invalid", body), status_code=400)

    # 2) Fetch certificate
    stmt = (
        select(Certificate)
        .options(selectinload(Certificate.student), selectinload(Certificate.event))
    )
    stmt1 = stmt.where(Certificate.certificate_no == cert_id)
    res = await db.execute(stmt1)
    cert = res.scalar_one_or_none()

    if cert is None and cert_id.isdigit():
        res2 = await db.execute(stmt.where(Certificate.id == int(cert_id)))
        cert = res2.scalar_one_or_none()

    if not cert or cert.revoked_at is not None:
        reason = "Revoked" if (cert and cert.revoked_at is not None) else "Not Found"
        body = f"""
        <div class="top">
          <div class="status-icon warn"><span class="animate-check">!</span></div>
          <div class="title-block">
            <h2 class="warn-txt">Certificate Not Valid</h2>
            <div class="sub">The signature is cryptographically correct, but this certificate is marked as <b>{reason.lower()}</b> in our system.</div>
          </div>
          <div class="status-pill">
            <span class="dot" style="background:var(--amber);box-shadow:0 0 6px var(--amber)"></span>
            <span class="warn-txt">NOT VALID</span>
          </div>
        </div>
        <div class="grid">
          <div class="section">
            <div class="section-header">
              <div class="section-icon">🔍</div>
              <h3>Lookup Details</h3>
            </div>
            <div class="row">
              <span class="k">🪪 Certificate ID</span>
              <span class="v"><code>{cert_id}</code></span>
            </div>
            <div class="row">
              <span class="k">📋 Status</span>
              <span class="v warn-txt">{reason}</span>
            </div>
          </div>
          <div class="section">
            <div class="section-header">
              <div class="section-icon">🛠️</div>
              <h3>Next Steps</h3>
            </div>
            <div class="row">
              <span class="k">📧 Action</span>
              <span class="v">Contact the Vikasana admin to request a re-issue of this certificate</span>
            </div>
          </div>
        </div>
        """
        return HTMLResponse(_html_page("Certificate Verification — Not Valid", body), status_code=200)

    # 3) Valid
    student = cert.student
    event = cert.event

    body = f"""
    <div class="valid-banner">
      Authenticated by Vikasana Foundation &nbsp;·&nbsp; Cryptographic signature valid &nbsp;·&nbsp; Issued on {_fmt_dt(cert.issued_at)}
    </div>
    <div class="top">
      <div class="status-icon good"><span class="animate-check">✓</span></div>
      <div class="title-block">
        <h2 class="good-txt">Certificate Verified</h2>
        <div class="sub">This is an authentic certificate issued through the Vikasana Social Activity Tracking system. All details below are tamper-proof.</div>
      </div>
      <div class="status-pill">
        <span class="dot" style="background:var(--green);box-shadow:0 0 6px var(--green)"></span>
        <span class="good-txt">VALID</span>
      </div>
    </div>
    <div class="grid">
      <div class="section">
        <div class="section-header">
          <div class="section-icon">🏅</div>
          <h3>Certificate Info</h3>
        </div>
        <div class="row">
          <span class="k">🪪 Certificate No</span>
          <span class="v"><code>{cert.certificate_no}</code></span>
        </div>
        <div class="row">
          <span class="k">📅 Issued At</span>
          <span class="v">{_fmt_dt(cert.issued_at)}</span>
        </div>
        <div class="row">
          <span class="k">🎯 Event</span>
          <span class="v">{getattr(event, "title", None) or getattr(event, "name", None) or "—"}</span>
        </div>
      </div>
      <div class="section">
        <div class="section-header">
          <div class="section-icon">🎓</div>
          <h3>Student Details</h3>
        </div>
        <div class="row">
          <span class="k">👤 Name</span>
          <span class="v">{getattr(student, "name", None) or "—"}</span>
        </div>
        <div class="row">
          <span class="k">🪪 USN</span>
          <span class="v"><code>{getattr(student, "usn", None) or "—"}</code></span>
        </div>
        <div class="row">
          <span class="k">🏛️ College</span>
          <span class="v">{getattr(student, "college", None) or "—"}</span>
        </div>
        <div class="row">
          <span class="k">📚 Branch</span>
          <span class="v">{getattr(student, "branch", None) or "—"}</span>
        </div>
      </div>
    </div>
    """
    return HTMLResponse(_html_page("Certificate Verification — Valid ✓", body), status_code=200)