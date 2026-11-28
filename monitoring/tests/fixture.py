"""Disposable backend, mock Discord receiver, and pipeline assertions (stdlib only)."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen


def request(url, method="GET", body=None, auth=True):
    headers = {"Host": "portal.localhost"}
    if auth:
        headers["Authorization"] = "Bearer test-only-credential"
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    try:
        with urlopen(Request(url, data=body, headers=headers, method=method), timeout=5) as response:
            return response.read().decode()
    except HTTPError as exc:
        return exc.read().decode()


def wait_for(check, seconds=45):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise AssertionError("Timed out waiting for test service or expected metric")


class Fixture(BaseHTTPRequestHandler):
    deliveries = []

    def do_GET(self):
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query)
        if "disconnect" in params:
            self.connection.close()
            self.close_connection = True
            return
        time.sleep(float(params.get("delay", ["0"])[0]))
        body = json.dumps(self.deliveries if parsed.path == "/deliveries" else {"items": []}).encode()
        self.send_response(int(params.get("status", ["200"])[0]))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/discord":
            self.deliveries.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204)
            self.end_headers()
        else:
            self.do_GET()

    def log_message(self, *_args):
        pass


def metrics():
    return request("http://nginx-log-exporter:4040/metrics")


def metric_sum(name, **labels):
    total = 0.0
    for line in metrics().splitlines():
        if line.startswith(name + "{") and all(f'{key}="{value}"' in line for key, value in labels.items()):
            total += float(line.rsplit(" ", 1)[1])
    return total


def pipeline():
    wait_for(lambda: request("http://nginx:8080/api/health"))
    wait_for(lambda: metrics())
    # Every request below is excluded, even though the fixture accepts fake tokens.
    request("http://nginx:8080/api/employees", auth=False)
    request("http://nginx:8080/api/employees", method="POST")
    for path in ("/api/health", "/api/employees/123", "/api/employees/123/salaries", "/api/employees/"):
        request("http://nginx:8080" + path)
    for status in (400, 401, 403, 404, 405, 413, 414, 422):
        request(f"http://nginx:8080/api/employees?status={status}")
    # Include fast/slow success, fast/slow server errors, an edge-generated 502,
    # and a fast 429 (the user's literal status < 500 criterion).
    for query in ("q=private-name", "delay=0.7", "status=500", "status=500&delay=0.7",
                  "disconnect=1", "status=429"):
        request("http://nginx:8080/api/employees?" + query)
    wait_for(lambda: metric_sum("securehr_search_http_response_count_total") == 6)
    assert metric_sum("securehr_search_http_response_time_seconds_hist_bucket", status="200", le="0.5") == 1
    assert metric_sum("securehr_search_http_response_count_total", status="502") == 1
    # Deterministic boundary checks use exact log durations; wall-clock sleeps cannot test 500 ms exactly.
    log = Path("/var/log/securehr/employee-search.log")
    contents = log.read_text()
    assert "private-name" not in contents and "test-only-credential" not in contents
    with log.open("a") as output:
        output.write('"GET /api/employees HTTP/1.1" 200 0 0.500\n')
        output.write('"GET /api/employees HTTP/1.1" 200 0 0.501\n')
    wait_for(lambda: metric_sum("securehr_search_http_response_count_total") == 8)
    assert metric_sum("securehr_search_http_response_time_seconds_hist_bucket", status="200", le="0.5") == 2
    assert "private-name" not in metrics()
    print("PASS: Nginx eligibility, edge 502, status/latency intersection, 500 ms boundary, log privacy")


def rotation():
    request("http://nginx:8080/api/employees?status=201")
    wait_for(lambda: metric_sum("securehr_search_http_response_count_total") == 9)
    assert metric_sum("securehr_search_http_response_count_total", status="201") == 1
    print("PASS: log rotation continues collection without replaying old requests")


def discord():
    wait_for(lambda: request("http://alertmanager:9093/-/ready"))
    alert = {
        "labels": {"alertname": "EmployeeSearchSLOBurnRate", "service": "securehr", "severity": "page"},
        "annotations": {"summary": "Isolated SLO test", "description": "Both burn rates reached 14.4.",
                        "first_step": "Inspect Nginx upstream logs and PostgreSQL query latency.",
                        "runbook": "docs/MONITORING.md#incident-runbook"},
    }
    request("http://alertmanager:9093/api/v2/alerts", "POST", [alert])
    deliveries = wait_for(lambda: json.loads(request("http://fixture:8000/deliveries")))
    message = deliveries[0]
    assert message["content"] == "<@123456789>"
    assert "Nginx upstream logs and PostgreSQL query latency" in json.dumps(message)
    assert "FIRING" in json.dumps(message)
    alert["endsAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 1))
    alert["startsAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120))
    request("http://alertmanager:9093/api/v2/alerts", "POST", [alert])
    deliveries = wait_for(lambda: (items if len(items) >= 2 else None)
                          if (items := json.loads(request("http://fixture:8000/deliveries"))) else None)
    assert "RESOLVED" in json.dumps(deliveries[-1])
    assert not deliveries[-1].get("content")
    print("PASS: Alertmanager sends firing/resolved Discord payloads and mentions on-call only when firing")


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        ThreadingHTTPServer(("0.0.0.0", 8000), Fixture).serve_forever()
    else:
        {"pipeline": pipeline, "rotation": rotation, "discord": discord}[sys.argv[1]]()
