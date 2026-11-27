"""Send a labeled test through local Alertmanager to the configured on-call receiver."""
from datetime import datetime, timedelta, timezone
import json
from urllib.request import Request, urlopen

now = datetime.now(timezone.utc)
payload = [{
    "labels": {"alertname": "SecureHRDiscordTest", "service": "securehr", "severity": "page"},
    "annotations": {
        "summary": "TEST: SecureHR on-call notification",
        "description": "Delivery check only; no employee search incident. This alert expires in one minute.",
        "first_step": "Inspect Nginx upstream logs and PostgreSQL query latency.",
        "runbook": "docs/MONITORING.md#incident-runbook",
    },
    "startsAt": now.isoformat(),
    "endsAt": (now + timedelta(minutes=1)).isoformat(),
}]
request = Request("http://127.0.0.1:9093/api/v2/alerts", data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
with urlopen(request, timeout=10) as response:
    print(f"Alertmanager accepted the test ({response.status}). Check Discord for the on-call mention.")
