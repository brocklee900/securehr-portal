FROM docker.gitea.com/gitea:28.1.0
# Trust the local mkcert CA so Gitea can call https://auth.localhost (Keycloak) and https://jenkins.localhost (webhooks).
# gitea/rootCA.pem is copied from jenkins/rootCA.pem by scripts/setup-gitea.sh (machine-specific, git-ignored).
COPY rootCA.pem /usr/local/share/ca-certificates/securehr-rootCA.crt
RUN update-ca-certificates
