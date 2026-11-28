#!/usr/bin/env bash
# Shared server only: real HTTPS certificates from Let's Encrypt (free) for portal./auth./gitea./jenkins.<domain>.
# Laptops keep using scripts/gen-certs.sh (mkcert). Safe to re-run, and re-running is also how certificates are
# renewed: Let's Encrypt certificates last 90 days, and this only asks for a new one in the last 30.
#
# Needs in .env: SECUREHR_DOMAIN (e.g. myteam.duckdns.org, already pointing at this server) and LETSENCRYPT_EMAIL.
# Port 80 must be open to the internet: Let's Encrypt checks ownership by fetching a file over plain HTTP.
set -euo pipefail
cd "$(dirname "$0")/.."

CERTBOT_IMAGE=certbot/certbot:v2.11.0
CERTS=nginx/certs
WEBROOT="$PWD/nginx/certbot/www"
LE_DIR="$PWD/nginx/certbot/conf"

[ -f .env ] || { echo "No .env found. Copy .env.example to .env and fill it in first."; exit 1; }
env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r' || true; }
DOMAIN="$(env_get SECUREHR_DOMAIN)"
EMAIL="$(env_get LETSENCRYPT_EMAIL)"
if [ -z "$DOMAIN" ] || [ "$DOMAIN" = localhost ]; then
  echo "Set SECUREHR_DOMAIN in .env to the server's public name (e.g. myteam.duckdns.org). On a laptop use scripts/gen-certs.sh."
  exit 1
fi
[ -n "$EMAIL" ] || { echo "Set LETSENCRYPT_EMAIL in .env (Let's Encrypt sends expiry warnings there)."; exit 1; }
HOSTS=(portal auth gitea jenkins)

echo "== 1/4 Checking that the names point at this server"
mine="$(curl -fsS --max-time 10 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
for h in "${HOSTS[@]}"; do
  got="$(getent ahostsv4 "$h.$DOMAIN" | awk 'NR==1 {print $1}' || true)"
  if [ -z "$got" ]; then echo "   $h.$DOMAIN does not resolve yet. Check the DuckDNS IP, wait a minute, re-run."; exit 1; fi
  if [ -n "$mine" ] && [ "$got" != "$mine" ]; then
    echo "   $h.$DOMAIN points at $got, but this server is $mine. Update the IP on duckdns.org, then re-run."; exit 1
  fi
done
echo "   ok"

echo "== 2/4 Starting Nginx (with a temporary certificate the first time)"
mkdir -p "$CERTS" "$WEBROOT" "$LE_DIR"
if [ ! -s "$CERTS/securehr.pem" ]; then
  # Nginx will not start without a certificate, and Let's Encrypt needs Nginx running to answer its check.
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=temporary" \
    -keyout "$CERTS/securehr-key.pem" -out "$CERTS/securehr.pem" 2>/dev/null
  echo "   created a temporary self-signed certificate"
fi
docker compose up -d nginx

echo "== 3/4 Requesting the certificate"
names=(); for h in "${HOSTS[@]}"; do names+=(-d "$h.$DOMAIN"); done
docker run --rm -v "$LE_DIR:/etc/letsencrypt" -v "$WEBROOT:/var/www/certbot" "$CERTBOT_IMAGE" \
  certonly --webroot -w /var/www/certbot --cert-name securehr \
  "${names[@]}" \
  --email "$EMAIL" --agree-tos --no-eff-email --non-interactive --keep-until-expiring

echo "== 4/4 Installing it for Nginx"
# Copied inside a container: the files belong to root, and the private key is not readable by other users.
docker run --rm -v "$LE_DIR:/etc/letsencrypt:ro" -v "$PWD/$CERTS:/out" --entrypoint sh "$CERTBOT_IMAGE" -c \
  'cp -L /etc/letsencrypt/live/securehr/fullchain.pem /out/securehr.pem &&
   cp -L /etc/letsencrypt/live/securehr/privkey.pem /out/securehr-key.pem && chmod 644 /out/securehr.pem'
docker compose exec nginx nginx -s reload

echo
echo "Done: https://portal.$DOMAIN now has a trusted certificate (valid 90 days)."
echo "Renew by re-running this script, e.g. monthly from cron:"
echo "  0 4 1 * * cd $PWD && bash scripts/get-public-certs.sh >> certs.log 2>&1"
