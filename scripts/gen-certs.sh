#!/usr/bin/env bash
# Milestone 3: local CA + certs trusted by your browser. Requires mkcert (https://github.com/FiloSottile/mkcert)
set -euo pipefail
cd "$(dirname "$0")/../nginx/certs"
mkcert -install
mkcert -cert-file securehr.pem -key-file securehr-key.pem \
  portal.localhost auth.localhost jenkins.localhost localhost 127.0.0.1
echo "Certs written to nginx/certs/. Root CA: $(mkcert -CAROOT)/rootCA.pem"
echo "Share that rootCA.pem with other team members / mount it into services that call each other over HTTPS."
