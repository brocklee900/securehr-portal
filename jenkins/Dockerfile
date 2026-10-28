FROM jenkins/jenkins:lts-jdk17
USER root
RUN apt-get update && apt-get install -y --no-install-recommends docker.io python3 python3-venv python3-pip nodejs npm \
 && rm -rf /var/lib/apt/lists/*
USER jenkins
RUN jenkins-plugin-cli --plugins configuration-as-code git workflow-aggregator github oic-auth role-strategy
ENV JAVA_OPTS="-Djenkins.install.runSetupWizard=false"
