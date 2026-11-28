"""Validate SLO rules and the Nginx -> metrics / Alertmanager -> Discord pipelines.

Uses isolated Docker resources and a mock Discord endpoint. No host bind mounts,
real webhook, live application services, or local secrets are needed (also works in Jenkins).
"""
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS = "prom/prometheus:v3.13.5"
ALERTMANAGER = "prom/alertmanager:v0.35.1"
EXPORTER = "quay.io/martinhelmich/prometheus-nginxlog-exporter:v1.11.0"


def docker(*args, capture=False, check=True):
    return subprocess.run(["docker", *map(str, args)], check=check, text=True,
                          stdout=subprocess.PIPE if capture else None)


def main():
    prefix = "securehr-slo-test-" + uuid.uuid4().hex[:10]
    network, volume = prefix + "-net", prefix + "-logs"
    containers = []

    def create(name, image, *command, options=()):
        container = prefix + "-" + name
        docker("create", "--name", container, *options, image, *command, capture=True)
        containers.append(container)
        return container

    def copy(source, container, dest):
        docker("cp", source, f"{container}:{dest}")

    def run_check(container):
        docker("start", "--attach", container)
        result = docker("inspect", "--format", "{{.State.ExitCode}}", container, capture=True)
        if result.stdout.strip() != "0":
            raise RuntimeError(f"Validation failed in {container}")

    try:
        docker("network", "create", network, capture=True)
        docker("volume", "create", volume, capture=True)
        prom = create("rules", PROMETHEUS, "test", "rules", "/etc/prometheus/tests/slo.test.yml",
                      "/etc/prometheus/tests/window.test.yml",
                      options=("--entrypoint", "/bin/promtool"))
        copy(str(ROOT / "monitoring/prometheus") + "/.", prom, "/etc/prometheus")
        copy(ROOT / "monitoring/tests", prom, "/etc/prometheus/tests")
        run_check(prom)
        config = create("prom-config", PROMETHEUS, "check", "config", "/etc/prometheus/prometheus.yml",
                        options=("--entrypoint", "/bin/promtool"))
        copy(str(ROOT / "monitoring/prometheus") + "/.", config, "/etc/prometheus")
        run_check(config)
        for filename in ("alertmanager.yml", "discord.yml.example"):
            am = create("config-" + filename.replace(".", "-"), ALERTMANAGER, "check-config", "/tmp/config.yml",
                        options=("--entrypoint", "/bin/amtool"))
            copy(ROOT / "monitoring/alertmanager" / filename, am, "/tmp/config.yml")
            run_check(am)

        pg = create("postgres", "postgres:16", "postgres", "-c", "shared_preload_libraries=pg_stat_statements",
                    options=("-e", "POSTGRES_PASSWORD=isolated-test-only", "-e", "POSTGRES_DB=employees"))
        docker("start", pg, capture=True)
        for _ in range(60):
            if docker("exec", pg, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", capture=True,
                      check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Test Postgres did not start")
        copy(ROOT / "db/post/06_query_statistics.sql", pg, "/tmp/query_statistics.sql")
        docker("exec", pg, "psql", "-U", "postgres", "-d", "employees", "-v", "ON_ERROR_STOP=1",
               "-f", "/tmp/query_statistics.sql", "-c", "SELECT count(*) FROM pg_stat_statements;")

        docker("build", "--quiet", "-t", "securehr/nginx-slo-test", ROOT / "nginx")
        with tempfile.TemporaryDirectory(prefix=prefix) as folder:
            temp = Path(folder)
            # Exercise the production server/location/log configuration over HTTP,
            # removing only TLS setup so the test never needs personal certificates.
            # The template's domain is filled in exactly as the nginx image does at startup (the fixture uses localhost).
            nginx_conf = (ROOT / "nginx/templates/nginx.conf.template").read_text()
            nginx_conf = nginx_conf.replace("${SECUREHR_DOMAIN}", "localhost")
            nginx_conf = "\n".join(line for line in nginx_conf.splitlines()
                                   if not line.strip().startswith(("ssl_certificate", "ssl_protocols")))
            nginx_conf = nginx_conf.replace("listen 443 ssl;", "listen 8080;").replace("listen 80 ", "listen 8081 ")
            (temp / "nginx.conf").write_text(nginx_conf)
            fixture = create("fixture", "python:3.12-slim", "python", "/tmp/fixture.py", "serve",
                             options=("--network", network, "--network-alias", "fixture",
                                      "--network-alias", "backend", "--network-alias", "frontend",
                                      "--network-alias", "keycloak", "--network-alias", "jenkins"))
            copy(ROOT / "monitoring/tests/fixture.py", fixture, "/tmp/fixture.py")
            docker("start", fixture, capture=True)
            nginx = create("nginx", "securehr/nginx-slo-test", options=("--network", network,
                           "--network-alias", "nginx", "-v", volume + ":/var/log/securehr"))
            copy(temp / "nginx.conf", nginx, "/etc/nginx/nginx.conf")
            copy(ROOT / "nginx/slo.conf", nginx, "/etc/nginx/slo.conf")
            docker("start", nginx, capture=True)
            exporter = create("exporter", EXPORTER, "-config-file", "/config.yml",
                              options=("--network", network, "--network-alias", "nginx-log-exporter",
                                       "-v", volume + ":/var/log/securehr:ro"))
            copy(ROOT / "monitoring/nginxlog-exporter.yml", exporter, "/config.yml")
            docker("start", exporter, capture=True)

            am_config = (ROOT / "monitoring/alertmanager/discord.yml.example").read_text()
            am_config = am_config.replace("__DISCORD_ONCALL_USER_ID__", "123456789")
            am_config = am_config.replace("/run/secrets/discord_webhook_url", "/tmp/discord_webhook_url")
            am_config = am_config.replace("group_interval: 5m", "group_interval: 1s")
            (temp / "alertmanager.yml").write_text(am_config)
            (temp / "discord_webhook_url").write_text("http://fixture:8000/discord\n")
            alertmanager = create("alertmanager", ALERTMANAGER, "--config.file=/tmp/config.yml",
                                  "--cluster.listen-address=", options=("--network", network,
                                                                      "--network-alias", "alertmanager"))
            copy(temp / "alertmanager.yml", alertmanager, "/tmp/config.yml")
            copy(temp / "discord_webhook_url", alertmanager, "/tmp/discord_webhook_url")
            docker("start", alertmanager, capture=True)
            for phase in ("pipeline", "rotation", "discord"):
                if phase == "rotation":
                    docker("exec", nginx, "logrotate", "--force", "/etc/logrotate.d/securehr")
                test = create(phase, "python:3.12-slim", "python", "/tmp/fixture.py", phase,
                              options=("--network", network, "-v", volume + ":/var/log/securehr"))
                copy(ROOT / "monitoring/tests/fixture.py", test, "/tmp/fixture.py")
                run_check(test)
        print("All monitoring checks passed.")
    except Exception:
        for container in containers:
            docker("logs", "--tail", "15", container, check=False)
        raise
    finally:
        # Only resources with this run's random prefix; never the live Compose project.
        for container in reversed(containers):
            docker("rm", "--force", "--volumes", container, capture=True, check=False)
        docker("volume", "rm", volume, capture=True, check=False)
        docker("network", "rm", network, capture=True, check=False)


if __name__ == "__main__":
    main()
