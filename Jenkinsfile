pipeline {
  agent any
  options { disableConcurrentBuilds() }
  environment { COMPOSE_PROJECT_NAME = 'securehr-staging' }

  stages {
    stage('Lint') {
      parallel {
        stage('Backend') { steps { sh 'cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements-dev.txt && ruff check .' } }
        stage('Frontend') { steps { sh 'cd frontend && npm ci && npm run lint && npm run typecheck' } }
      }
    }
    stage('Unit tests') {
      steps { sh 'cd backend && . .venv/bin/activate && pytest -q tests --ignore=tests/integration --junitxml=report.xml' }
      post { always { junit 'backend/report.xml' } }
    }
    stage('Integration tests') {
      steps { sh 'bash scripts/run_integration_tests.sh' }
      post { always { junit allowEmptyResults: true, testResults: 'backend/integration-report.xml' } }
    }
    stage('Build images') {
      steps { sh 'docker build -t securehr/backend:${GIT_COMMIT} backend && docker build -t securehr/frontend:${GIT_COMMIT} frontend' }
    }
    stage('Security scans') {   // Milestone 7
cat > Jenkinsfile <<'EOF'
pipeline {
  agent any
  options { disableConcurrentBuilds() }
  environment { COMPOSE_PROJECT_NAME = 'securehr-staging' }

  stages {
    stage('Lint') {
      parallel {
        stage('Backend') { steps { sh 'cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -q -r requirements-dev.txt && ruff check .' } }
        stage('Frontend') { steps { sh 'cd frontend && npm ci && npm run lint && npm run typecheck' } }
      }
    }
    stage('Unit tests') {
      steps { sh 'cd backend && . .venv/bin/activate && pytest -q tests --ignore=tests/integration --junitxml=report.xml' }
      post { always { junit 'backend/report.xml' } }
    }
    stage('Integration tests') {
      steps { sh 'bash scripts/run_integration_tests.sh' }
      post { always { junit allowEmptyResults: true, testResults: 'backend/integration-report.xml' } }
    }
    stage('Build images') {
      steps { sh 'docker build -t securehr/backend:${GIT_COMMIT} backend && docker build -t securehr/frontend:${GIT_COMMIT} frontend' }
    }
    stage('Security scans') {   // Milestone 7
      parallel {
        stage('Python deps') { steps { sh 'cd backend && . .venv/bin/activate && pip-audit -r requirements.txt' } }
        stage('Container')   { steps { sh 'docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache aquasec/trivy:latest image --ignore-unfixed --exit-code 1 --severity HIGH,CRITICAL securehr/backend:${GIT_COMMIT}' } }
      }
    }
    stage('Deploy to staging') {
      when { branch 'main' }
      steps { sh 'cp .env.example .env && docker compose config -q' }
    }
  }
}
