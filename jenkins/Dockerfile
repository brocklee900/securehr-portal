FROM docker:27-cli AS dockercli
FROM jenkins/jenkins:lts-jdk17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip nodejs npm ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
# Locally, trust the mkcert CA (jenkins/rootCA.pem, README step 1). On the shared server it is absent: Let's Encrypt
# certificates are already trusted. ("Dockerfile" is listed so the COPY always matches; the [m] makes rootCA.pem optional.)
COPY Dockerfile rootCA.pe[m] /tmp/ca/
RUN if [ -f /tmp/ca/rootCA.pem ]; then \
      cp /tmp/ca/rootCA.pem /usr/local/share/ca-certificates/securehr-rootCA.crt && update-ca-certificates \
      && keytool -importcert -noprompt -trustcacerts -alias securehr-local-ca \
           -file /usr/local/share/ca-certificates/securehr-rootCA.crt \
           -keystore "$JAVA_HOME/lib/security/cacerts" -storepass changeit; \
    fi; rm -rf /tmp/ca
USER jenkins
RUN jenkins-plugin-cli --plugins configuration-as-code git workflow-aggregator github oic-auth role-strategy junit gitea
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"