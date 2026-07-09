# Terraform — deferred

Phase 6's plan calls for "Terraform for the underlying cloud infra ... scope
to whatever provider is actually being used." No cloud provider is in use
yet — the current deployment target is a local kind cluster (see
`infra/k8s/README.md`), which is provisioned by `kind create cluster`, not
by Terraform: there's no cloud account, VPC, managed DB, or IAM to declare,
so a Terraform module here would either be an empty shell or a fake
abstraction over a single `docker run` that kind already does directly.
Same rationale as leaving the Ollama fallback unstarted in Phase 4 — it's
a real item in the plan, just nothing to build until the prerequisite
(a chosen cloud provider) exists.

This directory is the placeholder for when that changes. When a real cloud
target is picked (AWS/GCP/etc.), this is where to add modules for:

- A managed Kubernetes cluster (EKS/GKE/...) to replace kind.
- A managed Postgres instance to replace the in-cluster `postgres`
  Deployment (the chart's `postgres.yaml` template would then be dropped
  in favor of a `DATABASE_URL` pointing at the managed instance).
- A managed Redis instance to replace the in-cluster `redis` Deployment.
- Networking/IAM for whatever the chosen provider needs.

The Helm chart in `infra/k8s/helm/codereviewai` is written provider-agnostic
(no cloud-specific resources) so it should keep working against a real
cluster once one exists — only the datastore Deployments would need
swapping for managed equivalents.
