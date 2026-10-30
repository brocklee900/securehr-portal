FROM docker:27-cli AS dockercli
FROM jenkins/jenkins:lts-jdk17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip nodejs npm ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY rootCA.pem /usr/local/share/ca-certificates/securehr-rootCA.crt
RUN keytool -importcert -noprompt -trustcacerts -alias securehr-local-ca \
      -file /usr/local/share/ca-certificates/securehr-rootCA.crt \
      -keystore "$JAVA_HOME/lib/security/cacerts" -storepass changeit
USER jenkins
RUN jenkins-plugin-cli --plugins configuration-as-code git workflow-aggregator github oic-auth role-strategy junit
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"