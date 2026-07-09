# Local Kubernetes (kind)

Phase 6's "done when" allows either a real cloud cluster or a local
kind/minikube one — this repo targets **local kind**, so there's no
Terraform here (see `infra/terraform/README.md` for why).

This has been run end-to-end on a real kind cluster: cluster up → images
loaded → `helm upgrade --install --wait` → alembic migrated a real Postgres
to head → Celery worker connected to Redis and registered its tasks →
backend `/health` and frontend `/` both returned 200 through their
ClusterIP services. The worker's `HorizontalPodAutoscaler` (CPU-based) was
also verified against a real `metrics-server` install — `kubectl get hpa`
showed an actual reported CPU percentage, not just an accepted manifest.

## 1. Prerequisites

- Docker
- [`kind`](https://kind.sigs.k8s.io/docs/user/quick-start/#installation)
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/#kubectl)
- [`helm`](https://helm.sh/docs/intro/install/)

## 2. Create the cluster

```
kind create cluster --config infra/k8s/kind-config.yaml --name codereviewai
```

The config labels the node `ingress-ready=true` and publishes host ports
80/443, matching [kind's documented ingress-nginx setup](https://kind.sigs.k8s.io/docs/user/ingress/).

Install ingress-nginx:

```
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

Install `metrics-server` — kind doesn't ship it, but the worker's
`HorizontalPodAutoscaler` (`values.yaml`'s `worker.autoscaling`) needs it
to read any CPU numbers at all; without it, `kubectl get hpa` just shows
`<unknown>` forever instead of scaling anything:

```
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# kind's kubelet cert isn't signed by a CA metrics-server trusts by default:
kubectl patch deployment metrics-server -n kube-system --type=json \
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl wait --for=condition=available deployment/metrics-server -n kube-system --timeout=90s
```

## 3. Build and load the images

kind can't pull from your local Docker daemon directly — build, then
`kind load docker-image` to hand them to the cluster's containerd:

```
docker build -t codereviewai-backend:local apps/backend
docker build -t codereviewai-frontend:local -f apps/frontend/Dockerfile.prod \
  --build-arg NEXT_PUBLIC_API_URL=http://api.codereviewai.local apps/frontend

kind load docker-image codereviewai-backend:local codereviewai-frontend:local --name codereviewai
```

`NEXT_PUBLIC_API_URL` is baked into the frontend bundle at build time
(Next.js inlines `NEXT_PUBLIC_*` vars) — it must match the backend's
ingress host below, and changing it means rebuilding this image.

To use the GHCR images the `docker-publish` workflow pushes instead of a
local build, override `*.image.repository`/`*.image.tag` at install time
(see `values.yaml`'s comment at the top).

## 4. Install the chart

```
helm upgrade --install codereviewai infra/k8s/helm/codereviewai \
  --set secrets.jwtSecret="$(openssl rand -hex 32)" \
  --set secrets.githubAppWebhookSecret="$(openssl rand -hex 32)" \
  --set secrets.githubAppId=... \
  --set secrets.githubAppClientId=... \
  --set secrets.githubAppClientSecret=... \
  --set-file secrets.githubAppPrivateKey=path/to/your-app.pem \
  --set secrets.openaiApiKey=sk-... \
  --wait
```

Prefer a gitignored `values-secrets.yaml` (`-f values-secrets.yaml`) over a
long `--set` list once you have real values — see `values.yaml`'s
`secrets:` block for the full key list. Don't commit it.

Add to `/etc/hosts` (kind doesn't do DNS for you):

```
127.0.0.1 codereviewai.local
127.0.0.1 api.codereviewai.local
```

Then open `http://codereviewai.local/`.

## 5. Redeploying after a code change

```
docker build -t codereviewai-backend:local apps/backend
kind load docker-image codereviewai-backend:local --name codereviewai
kubectl rollout restart deployment codereviewai-backend codereviewai-worker
```

(Substitute frontend similarly. `kubectl rollout restart` reuses the
existing Helm-installed spec — if you changed the chart's templates or
`values.yaml`, run `helm upgrade` instead so the new spec actually applies.)

## Notes

- Postgres and Qdrant use `PersistentVolumeClaim`s (kind's default
  StorageClass provisions local-path volumes automatically) — data survives
  pod restarts but not `kind delete cluster`.
- The GitHub App private key is mounted from a Secret at
  `/etc/secrets/github-app/github-app-private-key.pem` — deliberately not
  `/run/secrets`, which collides with Kubernetes' own automatic
  service-account-token mount on Debian-based images (`/var/run` is a
  symlink to `/run`) and silently prevents the container from starting at
  all.
- `SONARQUBE_ENABLED` defaults to `false`; the chart doesn't deploy a
  SonarQube pod — run it separately (e.g. `docker compose --profile
  sonarqube up sonarqube`) and point `config.sonarqubeUrl` /
  `secrets.sonarqubeToken` at it if you want that integration in-cluster.
- Backend serves Prometheus metrics at `GET /metrics` on its normal port;
  the worker serves its own at `<release>-worker-metrics:9200` (Celery's
  prefork pool runs tasks in forked child processes, so its metrics use
  `prometheus_client`'s multiprocess mode rather than the single-process
  default — see the comment at the top of `app/workers/celery_app.py`).
  There's no Prometheus/Grafana deployed by this chart to scrape them —
  point your own at those two targets if you want dashboards.
- The worker autoscales on CPU (`worker.autoscaling`, on by default,
  1-5 replicas at 70% target) — requires `metrics-server` (step 2 above)
  or `kubectl get hpa` just shows `<unknown>` and never scales anything.
  `worker.replicaCount` is only the *initial* replica count once the HPA
  is enabled; it takes over from there.
