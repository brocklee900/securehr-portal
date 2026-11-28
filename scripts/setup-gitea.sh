#!/usr/bin/env bash
# Milestone 6: Gitea as the Git server, signing in through Keycloak (same SSO as the portal and Jenkins).
# Idempotent: safe to re-run. Does not touch the HR database or any existing volume.
#   1. generates GITEA_SECRET_KEY / GITEA_OIDC_SECRET in .env if missing
#   2. builds and starts the stack (Gitea, Nginx, Jenkins with the gitea plugin)
#   3. creates (or updates) the `gitea` client in the securehr realm, with a `roles` claim
#   4. registers Keycloak as Gitea's login source; the hr_admin role becomes Gitea site admin
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows would otherwise rewrite /opt/... paths

REALM=securehr
SOURCE=keycloak   # label on Gitea's sign-in button; also part of the callback URL registered below

[ -f .env ] || { echo "No .env found. Do README step 1 first."; exit 1; }

env_get() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '\r' || true; }
DOMAIN="$(env_get SECUREHR_DOMAIN)"; DOMAIN="${DOMAIN:-localhost}"

# Locally the services trust each other through the mkcert CA. On the shared server (a real domain with Let's Encrypt
# certificates) no extra CA is needed.
if [ "$DOMAIN" = localhost ] && [ ! -f jenkins/rootCA.pem ]; then
  echo "jenkins/rootCA.pem missing. Do README step 1 first (cp \"\$(mkcert -CAROOT)/rootCA.pem\" jenkins/rootCA.pem)."; exit 1
fi

echo "== 1/4 Secrets in .env"
for v in GITEA_SECRET_KEY GITEA_OIDC_SECRET; do
  if [ -z "$(env_get "$v")" ]; then
    sed -i "/^$v=/d" .env
    if [ -n "$(tail -c1 .env)" ]; then echo >> .env; fi
    val="$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    echo "$v=$val" >> .env
    echo "   generated $v"
  fi
done
SECRET="$(env_get GITEA_OIDC_SECRET)"

echo "== 2/4 Building and starting the stack"
if [ -f jenkins/rootCA.pem ]; then cp jenkins/rootCA.pem gitea/rootCA.pem; fi
docker compose up -d --build

echo "== 3/4 Keycloak client '$REALM/gitea'"
KCADM=/opt/keycloak/bin/kcadm.sh
login_ok=""
for _ in $(seq 1 60); do
  if docker compose exec -T keycloak sh -c "$KCADM config credentials --server http://localhost:8080 --realm master --user \"\$KC_BOOTSTRAP_ADMIN_USERNAME\" --password \"\$KC_BOOTSTRAP_ADMIN_PASSWORD\"" >/dev/null 2>&1; then
    login_ok=1; break
  fi
  sleep 5
done
if [ -z "$login_ok" ]; then
  echo "Could not log in to Keycloak's admin API (not ready yet, or the admin password was changed in the console)."
  echo "Create the client by hand instead: README step 7, 'Manual Keycloak client'."
  exit 1
fi

CLIENT_ID="$(docker compose exec -T keycloak $KCADM get clients -r $REALM -q clientId=gitea --fields id --format csv --noquotes | tr -d '\r' | head -1)"
if [ -z "$CLIENT_ID" ]; then
  docker compose exec -T keycloak $KCADM create clients -r $REALM -f - <<JSON
{
  "clientId": "gitea",
  "name": "Gitea",
  "protocol": "openid-connect",
  "enabled": true,
  "publicClient": false,
  "secret": "$SECRET",
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "redirectUris": ["https://gitea.$DOMAIN/user/oauth2/$SOURCE/callback"],
  "webOrigins": ["https://gitea.$DOMAIN"],
  "protocolMappers": [{
    "name": "roles",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-usermodel-realm-role-mapper",
    "config": {
      "claim.name": "roles",
      "multivalued": "true",
      "jsonType.label": "String",
      "id.token.claim": "true",
      "access.token.claim": "true",
      "userinfo.token.claim": "true"
    }
  }]
}
JSON
  echo "   created"
else
  # Client exists (earlier run): keep its secret and redirect URI in sync with .env
  docker compose exec -T keycloak $KCADM update "clients/$CLIENT_ID" -r $REALM -f - <<JSON
{ "secret": "$SECRET", "redirectUris": ["https://gitea.$DOMAIN/user/oauth2/$SOURCE/callback"], "webOrigins": ["https://gitea.$DOMAIN"] }
JSON
  echo "   already existed; secret and redirect URI re-synced"
fi

echo "== 4/4 Gitea login source '$SOURCE'"
healthy=""
for _ in $(seq 1 60); do
  if docker compose exec -T gitea curl -fsS http://localhost:3000/api/healthz >/dev/null 2>&1; then healthy=1; break; fi
  sleep 3
done
[ -n "$healthy" ] || { echo "Gitea did not become healthy: docker compose logs --no-log-prefix gitea | tail -40"; exit 1; }

# The secret is read from the container's own environment, not passed on this machine's command line.
# (Single quotes keep $GITEA_OIDC_SECRET for the container; the domain is spliced in from this script.)
ARGS='--name keycloak --provider openidConnect --key gitea --secret "$GITEA_OIDC_SECRET" --auto-discover-url https://auth.'"$DOMAIN"'/realms/securehr/.well-known/openid-configuration --scopes openid --scopes email --scopes profile --group-claim-name roles --admin-group hr_admin'   # one line: it is pasted into sh -c below
SRC_ID="$(docker compose exec -T -u git gitea gitea admin auth list | tr -d '\r' | awk -v n="$SOURCE" 'NR>1 && $2==n {print $1}')"
if [ -z "$SRC_ID" ]; then
  docker compose exec -T -u git gitea sh -c "gitea admin auth add-oauth $ARGS"
else
  docker compose exec -T -u git gitea sh -c "gitea admin auth update-oauth --id $SRC_ID $ARGS"
fi

cat <<MSG

Done. Next:
  * Jenkins was rebuilt, so re-open the Docker socket for builds:
      docker compose exec -u root jenkins chmod 666 /var/run/docker.sock
  * Open https://gitea.$DOMAIN -> "Sign in with keycloak" as alice.hr (she becomes Gitea site admin).
  * Then follow README step 7 (create the repo, add the Jenkins token, switch the job to Gitea).
MSG
