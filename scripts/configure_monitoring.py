"""Configure Discord locally, without putting the webhook in shell history or Git."""
import getpass
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def main():
    webhook = getpass.getpass("Discord incoming webhook URL (hidden): ").strip()
    if not re.fullmatch(r"https://discord\.com/api/webhooks/[0-9]+/[A-Za-z0-9_.-]+", webhook):
        raise SystemExit("Expected an https://discord.com/api/webhooks/<id>/<token> URL.")
    user_id = input("On-call engineer's Discord user ID (numeric; enable Developer Mode to copy it): ").strip()
    if not re.fullmatch(r"[0-9]+", user_id):
        raise SystemExit("The on-call user ID must contain only digits.")
    secrets = ROOT / "monitoring/secrets"
    secrets.mkdir(exist_ok=True)
    secret_file = secrets / "discord_webhook_url"
    secret_file.write_text(webhook + "\n", encoding="utf-8")
    config = ROOT / "monitoring/alertmanager"
    template = (config / "discord.yml.example").read_text(encoding="utf-8")
    (config / "discord.local.yml").write_text(
        template.replace("__DISCORD_ONCALL_USER_ID__", user_id), encoding="utf-8"
    )
    print("Saved the webhook and Discord configuration in git-ignored local files.")
    print("Build the monitoring-enabled edge first: docker compose build nginx")
    print("Start with: docker compose -f docker-compose.yml -f monitoring/discord.compose.yml "
          "--profile monitoring up -d nginx-log-exporter prometheus alertmanager")


if __name__ == "__main__":
    main()
