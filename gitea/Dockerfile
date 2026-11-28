FROM docker.gitea.com/gitea:28.1.0
# Locally, trust the mkcert CA so Gitea can call https://auth.<domain> (Keycloak) and https://jenkins.<domain> (webhooks).
# gitea/rootCA.pem is copied from jenkins/rootCA.pem by scripts/setup-gitea.sh (machine-specific, git-ignored).
# On the shared server it is absent: Let's Encrypt certificates are already trusted. ("Dockerfile" is listed so the
# COPY always matches something; the [m] makes rootCA.pem optional.)
COPY Dockerfile rootCA.pe[m] /tmp/ca/
RUN if [ -f /tmp/ca/rootCA.pem ]; then \
      cp /tmp/ca/rootCA.pem /usr/local/share/ca-certificates/securehr-rootCA.crt && update-ca-certificates; \
    fi; rm -rf /tmp/ca
