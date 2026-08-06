#!/usr/bin/env bash
# Deploy and operate Delta Station's K3s resources from the local checkout.
set -euo pipefail

REMOTE="${DELTA_REMOTE:-}"

if [[ -z "$REMOTE" ]]; then
  echo "Set DELTA_REMOTE, for example: DELTA_REMOTE=shine@shine.tail13b717.ts.net" >&2
  exit 2
fi

usage() {
  cat <<'EOF'
Usage: scripts/remote_k3s.sh <command>

Commands:
  deploy-dashboard  Build the local dashboard source on the server and apply its Deployment.
  deploy-importer   Build the local importer source on the server and apply its CronJob.
  run-importer      Create and follow a one-time importer Job.
  status            Show Delta Station pods, CronJobs, and Jobs.
  logs-dashboard    Follow dashboard logs when a KEDA-triggered Pod is running.
EOF
}

remote_stage=""

cleanup_stage() {
  if [[ -n "$remote_stage" ]]; then
    ssh "$REMOTE" "rm -rf '$remote_stage'" || true
  fi
}

create_stage() {
  remote_stage="$(ssh "$REMOTE" 'mktemp -d /tmp/delta-station-deploy.XXXXXX')"
  trap cleanup_stage EXIT
}

transfer() {
  tar -cf - "$@" | ssh "$REMOTE" "tar -xf - -C '$remote_stage'"
}

deploy_dashboard() {
  create_stage
  transfer Dockerfile.dashboard pyproject.toml uv.lock src/__init__.py src/visualization k3s-manifests/deployment.yaml
  ssh -tt "$REMOTE" "set -e
    cd '$remote_stage'
    docker build -f Dockerfile.dashboard -t localhost:5000/delta-station-dashboard:latest .
    docker push localhost:5000/delta-station-dashboard:latest
    sudo kubectl apply -f k3s-manifests/deployment.yaml
    sudo kubectl rollout restart deployment/delta-station-dashboard -n delta-station"
}

deploy_importer() {
  create_stage
  transfer Dockerfile.scraper pyproject.toml uv.lock src/__init__.py src/collector database scripts k3s-manifests/importer-cronjob.yaml
  ssh -tt "$REMOTE" "set -e
    cd '$remote_stage'
    docker build -f Dockerfile.scraper -t localhost:5000/delta-station-scraper:latest .
    docker push localhost:5000/delta-station-scraper:latest
    sudo kubectl apply -f k3s-manifests/importer-cronjob.yaml"
}

run_importer() {
  ssh -tt "$REMOTE" "set -e
    sudo kubectl delete job delta-station-importer-manual -n delta-station --ignore-not-found
    sudo kubectl create job delta-station-importer-manual --from=cronjob/delta-station-importer -n delta-station
    sudo kubectl logs -f job/delta-station-importer-manual -n delta-station"
}

case "${1:-}" in
  deploy-dashboard) deploy_dashboard ;;
  deploy-importer) deploy_importer ;;
  run-importer) run_importer ;;
  status)
    ssh -tt "$REMOTE" "sudo kubectl get pods,cronjobs,jobs -n delta-station"
    ;;
  logs-dashboard)
    ssh -tt "$REMOTE" "sudo kubectl logs -f deployment/delta-station-dashboard -n delta-station"
    ;;
  *) usage; exit 2 ;;
esac
