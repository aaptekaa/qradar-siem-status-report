#!/usr/bin/env python3
"""
QRadar Hourly Status Reporter
Sends a full HTML status report to email every hour.
"""
import time
import logging
import smtplib
import ssl
import json
import base64
import urllib.request
import urllib.error
import ssl as _ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QRADAR_HOST = "192.168.2.70"
QRADAR_USER = "admin"
QRADAR_PASS = "AdminPass"

SMTP_HOST = "192.168.5.2"
SMTP_PORT = 587
SMTP_USER = "soar@test.com"
SMTP_PASS = "AdminPass"
SMTP_FROM = "soar@test.com"
SMTP_TO   = "administrator@test.com"

REPORT_INTERVAL = 3600   # seconds between reports (3600 = 1 hour)
LOG_FILE        = "/var/log/qradar-reporter.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE)]
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# QRadar API
# ---------------------------------------------------------------------------

_ssl_ctx = _ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode    = _ssl.CERT_NONE

_basic = base64.b64encode(f"{QRADAR_USER}:{QRADAR_PASS}".encode()).decode()

HEADERS = {
    "Version":       "20.0",
    "Accept":        "application/json",
    "Content-Type":  "application/json",
    "Allow-Hidden":  "true",
    "Authorization": f"Basic {_basic}",
}


def qradar_get(path):
    url = f"https://{QRADAR_HOST}{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=_ssl_ctx, timeout=20) as resp:
            return json.loads(resp.read().decode()), resp.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        log.warning(f"GET {path} failed: {e}")
        return None, 0


def collect_data():
    data = {}
    endpoints = {
        "about":        "/api/system/about",
        "licenses":     "/api/config/deployment/licenses",
        "license_pool": "/api/config/deployment/license_pool",
        "dr":           "/api/config/disaster_recovery/disaster_recovery_config",
        "backup":       "/api/config/backup_and_restore/scheduled_backup_configurations",
        "servers":      "/api/system/servers",
        "log_sources":  "/api/configuration/log_sources?fields=description,enabled",
        "apps":         "/api/gui_app_framework/applications",
        "health":       "/api/health_data/security_data_count",
    }
    for key, path in endpoints.items():
        result, status = qradar_get(path)
        data[key] = {"data": result, "status": status}
        log.debug(f"  {key}: HTTP {status}")
    return data


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def ts_to_date(ts_ms):
    if not ts_ms or ts_ms <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")
    except Exception:
        return str(ts_ms)


def nested(d, *keys, default="N/A"):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
            if d is None:
                return default
        else:
            return default
    return d if d is not None else default


def section_header(title):
    return f"""
    <tr>
      <td colspan="2" style="padding:20px 24px 6px;">
        <p style="margin:0;font-size:12px;font-weight:700;color:#1a1a2e;text-transform:uppercase;
                  letter-spacing:.8px;border-bottom:2px solid #0f3460;padding-bottom:6px;">{title}</p>
      </td>
    </tr>"""


def row(label, value, highlight=False):
    bg    = "#fff" if not highlight else "#e8f4f8"
    vstyle = "font-weight:600;color:#0f3460;" if highlight else "color:#333;"
    return f"""
    <tr style="background:{bg};">
      <td style="padding:7px 24px;font-size:13px;color:#555;width:38%;
                 border-bottom:1px solid #f0f0f0;">{label}</td>
      <td style="padding:7px 24px;font-size:13px;{vstyle}
                 border-bottom:1px solid #f0f0f0;">{value}</td>
    </tr>"""


def spacer():
    return '<tr><td colspan="2" style="padding:4px;"></td></tr>'


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_html_report(data, generated_at):
    about       = data["about"]["data"]        or {}
    licenses    = data["licenses"]["data"]     or []
    lpool       = data["license_pool"]["data"] or {}
    dr          = data["dr"]["data"]           or {}
    backup_raw  = data["backup"]["data"]       or []
    servers     = data["servers"]["data"]      or []
    log_sources = data["log_sources"]["data"]  or []
    apps        = data["apps"]["data"]         or []
    health      = data["health"]["data"]       or {}

    # --- System ---
    build_ver = about.get("release_name", "N/A")
    ext_ver   = about.get("external_version", "N/A")

    # --- License pool (nested: eps.total, eps.allocated, fpm.total, fpm.allocated) ---
    eps_total = nested(lpool, "eps", "total")
    eps_alloc = nested(lpool, "eps", "allocated")
    fpm_total = nested(lpool, "fpm", "total")
    fpm_alloc = nested(lpool, "fpm", "allocated")

    # --- Licenses list ---
    lic_rows = ""
    if isinstance(licenses, list) and licenses:
        for lic in licenses:
            lic_type   = lic.get("license_type",    "N/A")
            lic_key    = lic.get("identifier_type", "N/A")
            lic_expiry = ts_to_date(lic.get("expiry_date"))
            lic_cat    = lic.get("category", "N/A")
            color = "#dc3545" if lic_type == "TEMPORARY" else "#155724"
            lic_rows += row(
                f'<span style="color:{color};font-weight:700;">{lic_type}</span> &mdash; {lic_cat}',
                f'{lic_key}<br><span style="font-size:12px;color:#888;">Expires: {lic_expiry}</span>'
            )
    else:
        lic_rows = row("License", "No license data available")

    # --- Health ---
    offenses  = health.get("offenses",        "N/A")
    assets    = health.get("assets",          "N/A")
    rules     = health.get("rules",           "N/A")
    vulns     = health.get("vulnerabilities", "N/A")

    # --- Log sources ---
    enabled_ls  = sum(1 for s in log_sources if s.get("enabled") is True)
    disabled_ls = sum(1 for s in log_sources if s.get("enabled") is False)
    total_ls    = len(log_sources)

    # --- Servers ---
    srv_rows = ""
    if isinstance(servers, list):
        for s in servers:
            hostname = s.get("hostname", s.get("server_id", "N/A"))
            status   = s.get("status", "N/A")
            col      = "#28a745" if status == "ACTIVE" else "#dc3545"
            srv_rows += row(
                str(hostname),
                f'<span style="color:{col};font-weight:700;">{status}</span>',
                highlight=True
            )
    if not srv_rows:
        srv_rows = row("Status", "N/A")

    # --- Backup ---
    backup = (backup_raw[0] if isinstance(backup_raw, list) and backup_raw
              else (backup_raw if isinstance(backup_raw, dict) else {}))
    backup_enabled  = backup.get("enabled",  False) if isinstance(backup, dict) else False
    backup_schedule = backup.get("schedule", "N/A") if isinstance(backup, dict) else "N/A"
    bak_badge = (
        '<span style="background:#28a745;color:#fff;font-size:11px;font-weight:700;'
        'padding:2px 10px;border-radius:12px;">Enabled</span>'
        if backup_enabled else
        '<span style="background:#dc3545;color:#fff;font-size:11px;font-weight:700;'
        'padding:2px 10px;border-radius:12px;">Disabled</span>'
    )

    # --- DR ---
    dr_enabled = dr.get("enabled", False)
    dr_mode    = dr.get("mode",    "N/A")
    dr_badge = (
        '<span style="background:#28a745;color:#fff;font-size:11px;font-weight:700;'
        'padding:2px 10px;border-radius:12px;">Enabled</span>'
        if dr_enabled else
        '<span style="background:#6c757d;color:#fff;font-size:11px;font-weight:700;'
        'padding:2px 10px;border-radius:12px;">Disabled</span>'
    )

    # --- Apps ---
    app_rows = ""
    if isinstance(apps, list):
        for a in apps:
            desc   = nested(a, "manifest",        "description", default="N/A")
            status = nested(a, "application_state","status",      default="N/A")
            col    = "#28a745" if status == "RUNNING" else "#dc3545"
            app_rows += row(
                str(desc)[:70],
                f'<span style="color:{col};font-weight:700;">{status}</span>'
            )
    if not app_rows:
        app_rows = row("Status", "No applications found")

    # --- Disabled log source list ---
    disabled_names = [s.get("description", "N/A") for s in log_sources if s.get("enabled") is False]
    ls_disabled_html = ""
    if disabled_names:
        names_str = "<br>".join(f"&bull; {n}" for n in disabled_names[:30])
        ls_disabled_html = row("Disabled Sources", names_str)

    # -------------------------------------------------------------------------
    # Summary cards
    # -------------------------------------------------------------------------
    cards_html = f"""
    <tr>
      <td style="padding:20px 24px 0;">
        <table width="100%" cellpadding="0" cellspacing="0"><tr>
          <td width="25%" style="padding:0 6px 12px 0;vertical-align:top;">
            <div style="background:#e8f0fe;border-radius:6px;padding:14px 16px;">
              <p style="margin:0 0 2px;font-size:10px;color:#666;text-transform:uppercase;
                        letter-spacing:.5px;">Version</p>
              <p style="margin:0;font-size:13px;font-weight:700;color:#0f3460;">{build_ver}</p>
            </div>
          </td>
          <td width="25%" style="padding:0 6px 12px;vertical-align:top;">
            <div style="background:#e6f9ee;border-radius:6px;padding:14px 16px;">
              <p style="margin:0 0 2px;font-size:10px;color:#666;text-transform:uppercase;
                        letter-spacing:.5px;">Log Sources</p>
              <p style="margin:0;font-size:13px;font-weight:700;color:#155724;">
                {enabled_ls} / {total_ls} active</p>
            </div>
          </td>
          <td width="25%" style="padding:0 6px 12px;vertical-align:top;">
            <div style="background:#fff3cd;border-radius:6px;padding:14px 16px;">
              <p style="margin:0 0 2px;font-size:10px;color:#666;text-transform:uppercase;
                        letter-spacing:.5px;">Active Offenses</p>
              <p style="margin:0;font-size:13px;font-weight:700;color:#856404;">{offenses}</p>
            </div>
          </td>
          <td width="25%" style="padding:0 0 12px 6px;vertical-align:top;">
            <div style="background:#e8f0fe;border-radius:6px;padding:14px 16px;">
              <p style="margin:0 0 2px;font-size:10px;color:#666;text-transform:uppercase;
                        letter-spacing:.5px;">Assets</p>
              <p style="margin:0;font-size:13px;font-weight:700;color:#0f3460;">{assets}</p>
            </div>
          </td>
        </tr></table>
      </td>
    </tr>"""

    # -------------------------------------------------------------------------
    # Assemble HTML
    # -------------------------------------------------------------------------
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f2f5;padding:32px 0;">
  <tr><td align="center">
    <table width="680" cellpadding="0" cellspacing="0"
           style="background:#fff;border-radius:10px;overflow:hidden;
                  box-shadow:0 2px 12px rgba(0,0,0,.12);">

      <!-- Header -->
      <tr>
        <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);
                   padding:24px 24px 20px;">
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td>
              <p style="margin:0;font-size:11px;color:#8899aa;text-transform:uppercase;
                        letter-spacing:1px;">Automated Status Report</p>
              <p style="margin:4px 0 0;font-size:22px;font-weight:700;color:#fff;">
                IBM QRadar SIEM</p>
            </td>
            <td align="right" style="vertical-align:top;">
              <p style="margin:0;font-size:12px;color:#aabbcc;">{generated_at}</p>
              <p style="margin:4px 0 0;font-size:11px;color:#667788;">{QRADAR_HOST}</p>
            </td>
          </tr></table>
        </td>
      </tr>

      <!-- Summary cards -->
      {cards_html}

      <!-- Sections -->
      <tr><td>
        <table width="100%" cellpadding="0" cellspacing="0">

          {section_header("System Information")}
          {row("Version", build_ver, highlight=True)}
          {row("External Version", ext_ver)}
          {row("Console Host", QRADAR_HOST)}
          {spacer()}

          {section_header("License")}
          {lic_rows}
          {row("EPS Limit / Allocated", f"{eps_total} / {eps_alloc}")}
          {row("FPM Limit / Allocated", f"{fpm_total} / {fpm_alloc}")}
          {spacer()}

          {section_header("Health & Activity")}
          {row("Active Offenses", str(offenses), highlight=True)}
          {row("Assets", str(assets))}
          {row("Rules", str(rules))}
          {row("Vulnerabilities", str(vulns))}
          {spacer()}

          {section_header("Log Sources")}
          {row("Total", str(total_ls), highlight=True)}
          {row("Enabled", f'<span style="color:#28a745;font-weight:700;">{enabled_ls}</span>')}
          {row("Disabled", f'<span style="color:{"#dc3545" if disabled_ls else "#333"};font-weight:{"700" if disabled_ls else "400"};">{disabled_ls}</span>')}
          {ls_disabled_html}
          {spacer()}

          {section_header("QRadar Servers")}
          {srv_rows}
          {spacer()}

          {section_header("Backup Configuration")}
          {row("Status", bak_badge)}
          {row("Schedule", str(backup_schedule))}
          {spacer()}

          {section_header("Disaster Recovery")}
          {row("Status", dr_badge)}
          {row("Mode", str(dr_mode))}
          {spacer()}

          {section_header("Installed Applications")}
          {app_rows}
          {spacer()}

        </table>
      </td></tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f8f9fa;border-top:1px solid #e9ecef;padding:14px 24px;">
          <p style="margin:0;font-size:11px;color:#999;">
            Automated hourly report &bull; IBM QRadar SIEM {QRADAR_HOST}
            &bull; Generated {generated_at}
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

    return html


def build_plain_report(data, generated_at):
    about       = data["about"]["data"]        or {}
    health      = data["health"]["data"]       or {}
    lpool       = data["license_pool"]["data"] or {}
    log_sources = data["log_sources"]["data"]  or []

    build_ver = about.get("release_name", "N/A")
    offenses  = health.get("offenses", "N/A")
    assets    = health.get("assets",   "N/A")
    eps_total = nested(lpool, "eps", "total")
    eps_alloc = nested(lpool, "eps", "allocated")
    enabled   = sum(1 for s in log_sources if s.get("enabled") is True)
    total     = len(log_sources)

    return (
        f"IBM QRadar SIEM — Hourly Status Report\n"
        f"{'='*50}\n"
        f"Generated       : {generated_at}\n"
        f"Host            : {QRADAR_HOST}\n\n"
        f"Version         : {build_ver}\n"
        f"Active Offenses : {offenses}\n"
        f"Assets          : {assets}\n"
        f"EPS             : {eps_alloc} / {eps_total}\n"
        f"Log Sources     : {enabled} / {total} enabled\n"
    )


# ---------------------------------------------------------------------------
# Email sender
# ---------------------------------------------------------------------------

def send_report(html_body, plain_body, generated_at):
    subject = f"[QRadar] Hourly Status Report — {generated_at}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = SMTP_TO
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body,  "html",  "utf-8"))

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode    = ssl.CERT_NONE

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_FROM, [SMTP_TO], msg.as_string())

    log.info(f"Report sent to {SMTP_TO}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_once():
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    log.info(f"Collecting QRadar data from {QRADAR_HOST}...")
    data = collect_data()

    ok_count = sum(1 for v in data.values() if v["status"] == 200)
    log.info(f"API responses: {ok_count}/{len(data)} OK")

    html  = build_html_report(data, generated_at)
    plain = build_plain_report(data, generated_at)
    send_report(html, plain, generated_at)


def main():
    import sys
    if "--once" in sys.argv:
        log.info("Manual run: collecting and sending report...")
        run_once()
        log.info("Done.")
        return

    log.info("QRadar Status Reporter started")
    log.info(f"Sending to: {SMTP_TO} | Interval: {REPORT_INTERVAL}s")

    while True:
        try:
            run_once()
        except Exception as e:
            log.error(f"Report cycle failed: {e}", exc_info=True)
        time.sleep(REPORT_INTERVAL)


if __name__ == "__main__":
    main()
