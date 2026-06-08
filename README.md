# QRadar Hourly Status Reporter

Automatically sends a full HTML status report from **IBM QRadar SIEM** to email every hour. Runs as a systemd service.

## What it does

Every hour (and immediately on startup) the script:

1. Queries 9 QRadar REST API endpoints
2. Builds a complete HTML report
3. Sends it to the configured recipient via Exchange SMTP

The email is a self-contained HTML document — no attachments, opens directly in any mail client.

## Report Contents

**Summary cards (top of email):**

| Card | Value |
|------|-------|
| Version | QRadar release name (e.g. `7.5.0 UpdatePackage 13`) |
| Log Sources | Enabled / Total (e.g. `15 / 16 active`) |
| Active Offenses | Current open offenses count |
| Assets | Number of discovered assets |

**Detailed sections:**

| Section | Fields |
|---------|--------|
| System Information | Version, external version, host |
| License | All licenses with type (PERMANENT / TEMPORARY), key name, expiry date |
| License Pool | EPS limit / allocated, FPM limit / allocated |
| Health & Activity | Active offenses, assets, rules, vulnerabilities |
| Log Sources | Total, enabled, disabled count + list of disabled sources |
| QRadar Servers | Hostname, status (ACTIVE / other) |
| Backup Configuration | Enabled status, schedule |
| Disaster Recovery | Enabled status, mode |
| Installed Applications | App name, running status |

## Installation

### Requirements

- Python 3.6+ (standard library only — no pip install needed)
- IBM QRadar SIEM with REST API access
- Exchange Server with SMTP on port 587 (STARTTLS)
- RHEL / CentOS / Debian with systemd

### 1. Copy the script

```bash
cp qradar-reporter.py /opt/qradar-reporter.py
chmod +x /opt/qradar-reporter.py
```

### 2. Configure

Edit the variables at the top of `qradar-reporter.py`:

```python
QRADAR_HOST = "192.168.2.70"   # QRadar SIEM IP
QRADAR_USER = "admin"           # QRadar admin login
QRADAR_PASS = "password"        # QRadar admin password

SMTP_HOST = "192.168.5.2"       # Exchange server IP
SMTP_PORT = 587                  # SMTP port (STARTTLS)
SMTP_USER = "soar@example.com"  # Sender mailbox
SMTP_PASS = "password"           # Sender password
SMTP_FROM = "soar@example.com"  # From address
SMTP_TO   = "admin@example.com" # Recipient

REPORT_INTERVAL = 3600           # Interval in seconds (3600 = 1 hour)
```

### 3. Install systemd service

```bash
cp qradar-reporter.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable qradar-reporter.service
systemctl start qradar-reporter.service
```

### 4. Verify

```bash
systemctl status qradar-reporter.service
tail -f /var/log/qradar-reporter.log
```

## Manual Report (without waiting 1 hour)

Run a single report at any time:

```bash
python3 /opt/qradar-reporter.py --once
```

The report is sent immediately and the script exits. Safe to run while the service is running.

## Log Example

```
2026-06-08 13:09:00 [INFO] QRadar Status Reporter started
2026-06-08 13:09:00 [INFO] Sending to: admin@example.com | Interval: 3600s
2026-06-08 13:09:00 [INFO] Collecting QRadar data from 192.168.2.70...
2026-06-08 13:09:15 [INFO] API responses: 9/9 OK
2026-06-08 13:09:15 [INFO] Report sent to admin@example.com
```

## Log File

```
/var/log/qradar-reporter.log
```

## Exchange Prerequisites

1. Create a sender mailbox (`soar@domain.com`)
2. Enable Authenticated SMTP on port 587
3. Open port 587 in Windows Firewall for the QRadar server:

```
netsh advfirewall firewall add rule name="SMTP-587 QRadar" ^
  dir=in action=allow protocol=TCP localport=587 remoteip=192.168.2.0/24
```

## Stack

- **IBM QRadar SIEM** 7.5.0+
- **Microsoft Exchange** 2016+
- **Python** 3.6+ (stdlib only)
- **RHEL** 8.x / systemd

<img width="1037" height="831" alt="image" src="https://github.com/user-attachments/assets/ba2c5da1-19a7-456d-a417-6d6d0efbb4c9" />
<img width="1037" height="652" alt="image" src="https://github.com/user-attachments/assets/7c318809-3ec0-4d5c-b8ba-b88e51e2bbc2" />
<img width="937" height="218" alt="image" src="https://github.com/user-attachments/assets/da522e8d-164e-4d96-aa0f-8c901a7ee0e4" />



