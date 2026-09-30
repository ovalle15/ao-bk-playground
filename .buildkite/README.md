# Buildkite pipelines

This repository has three Buildkite pipeline definitions:

| File | Queue | Purpose |
| --- | --- | --- |
| `pipeline.yaml` | `webhook-acquire` | Build and publish the frontend and server images. |
| `pipeline.kube.yaml` | `kube` | Validate the Helm chart and deploy the images to Rancher Desktop Kubernetes. |
| `pipeline.cache.yaml` | `cache` | Run the containerized E2E suite with Python wheels saved through Buildkite Cache. |

## Buildkite pipeline configuration

Configure the image-publishing pipeline with:

```yaml
steps:
  - label: ":pipeline: Upload image pipeline"
    command: buildkite-agent pipeline upload .buildkite/pipeline.yaml
```

Configure the Kubernetes deployment pipeline with:

```yaml
steps:
  - label: ":pipeline: Upload Kubernetes pipeline"
    command: buildkite-agent pipeline upload .buildkite/pipeline.kube.yaml
agents:
  queue: "${QUEUE}"
```

The triggering pipeline supplies `QUEUE`. For a manually created build, add a
`QUEUE` build environment variable containing an existing queue key such as
`kube`.

Configure the cache pipeline with an upload step on the `cache` queue:

```yaml
steps:
  - label: ":pipeline: Upload E2E cache pipeline"
    command: buildkite-agent pipeline upload .buildkite/pipeline.cache.yaml
    agents:
      queue: "cache"
```

The upload job and its generated E2E job both target the literal `cache` queue.
The queue must have a connected agent with Docker, Python 3, and access to the
S3 store configured in `pipeline.cache.yaml`. For a Mac webhook watcher, start
it with `BUILDKITE_TARGET_QUEUE=cache` and an authenticated AWS profile that
can read and write the bucket prefix.

The Python runner in `scripts/run-cached-e2e.py` restores
`.buildkite-cache/e2e-wheels`, downloads Linux Python wheels on a miss, saves
them through Buildkite Cache, and runs the Docker Compose E2E suite. It
downloads inside a Linux container so the wheels match the E2E image. The
cache key includes the agent architecture, pipeline, and checksum of
`requirements-e2e.txt`; changing that file creates a new entry. The wheel
directory is ignored by Git. Its checked-in `.gitkeep` lets a manual Docker
Compose build fall back to the package index when no wheels are present.

Run two builds with the same requirements. The first should log `Cache miss`,
download wheels, and save an entry. The second should log an exact cache hit
and `Using restored Python wheels`. In the image build log, `Looking in links:
/wheels` confirms pip installed from the cache without contacting the package
index. The E2E job should finish with three passing browser tests. Check
**Agents → cluster → Cache Registries → Default → Entries** for the entry.
The runner uses Buildkite job credentials, so run it as a pipeline job rather
than directly from a terminal. Set an S3 lifecycle rule on the `buildkite/`
prefix to expire old objects after three days and clean incomplete uploads.

## Image publishing

`pipeline.yaml` builds and pushes these images to Buildkite Packages:

- `packages.buildkite.com/spacecamp/ao-bk-playground/app:latest`
- `packages.buildkite.com/spacecamp/ao-bk-playground/server:latest`

The job requires Docker and a Buildkite agent that supports
`buildkite-agent oidc request-token`. The Buildkite Packages registry must have
an OIDC policy that permits this pipeline to publish images.

## Kubernetes setup with Rancher Desktop

Prerequisites:

- Rancher Desktop Kubernetes is running.
- `kubectl` and Helm are installed.
- The `kube` queue exists in the intended Buildkite cluster.
- The Agent Stack controller for `kube` is running and connected. Creating the
  queue alone is not enough; jobs remain scheduled when no agent is available
  for that queue.
- You have an agent token created in that same Buildkite cluster. The token
  determines which cluster the Agent Stack joins.

Select Rancher Desktop and confirm the context before installing anything:

```bash
kubectl config use-context rancher-desktop
kubectl config current-context
```

Use the workspace setup helper
[`setup-buildkite-rancher.sh`](../scripts/rancher/setup-buildkite-rancher.sh) to
install or update the official Buildkite Agent Stack chart:

```bash
./scripts/rancher/setup-buildkite-rancher.sh \
  --context rancher-desktop \
  --queue kube \
  --agent-token 'bkct_TOKEN_FROM_THE_INTENDED_CLUSTER'
```

The script installs the `agent-stack-k8s` Helm release in the `buildkite`
namespace, creates or updates its token Secret, and waits for the controller to
become ready. Run the same command with a new token to replace the token; the
release does not need to be deleted.

### Deployment permissions

Buildkite job pods need a dedicated ServiceAccount with permission to install
the application chart in the `nasa-image` namespace:

```bash
kubectl create namespace nasa-image
kubectl --namespace buildkite create serviceaccount buildkite-agent

kubectl --namespace nasa-image create role buildkite-nasa-image-deployer \
  --verb=get,list,watch,create,update,patch,delete \
  --resource=configmaps,secrets,services,deployments.apps,replicasets.apps,ingresses.networking.k8s.io

kubectl --namespace nasa-image create rolebinding buildkite-nasa-image-deployer \
  --role=buildkite-nasa-image-deployer \
  --serviceaccount=buildkite:buildkite-agent

helm upgrade agent-stack-k8s \
  oci://ghcr.io/buildkite/helm/agent-stack-k8s \
  --namespace buildkite \
  --reuse-values \
  --set-string config.pod-spec-patch.serviceAccountName=buildkite-agent \
  --set config.pod-spec-patch.automountServiceAccountToken=true \
  --set-json 'config.pod-spec-patch.containers=[]'
```

These are one-time creation commands. If a resource already exists, leave it
in place and continue with the next command. Existing job pods do not adopt a
new ServiceAccount; start a new build after changing this configuration.

Verify the controller and job configuration:

```bash
kubectl --namespace buildkite get deployment,pods,serviceaccounts
kubectl --namespace buildkite logs deployment/agent-stack-k8s --tail=100
helm --namespace buildkite get values agent-stack-k8s
```

The controller log should identify the intended Buildkite cluster and
`queue=kube`. The Helm values should show `serviceAccountName: buildkite-agent`.

## NASA API key

In **Buildkite > Agents > test-cluster > Secrets**, create:

```text
NASA_API_TOKEN=<your NASA API key>
```

The deployment step exposes this Buildkite secret to the job as `API_TOKEN` and
passes it to Helm. Helm creates the `nasa-image-api` Kubernetes Secret in the
`nasa-image` namespace. Do not put the API key in the pipeline or values file.

## Deploy the application

Run the pipelines in this order:

1. Run the image-publishing pipeline to build and push both `latest` images.
2. Run the Kubernetes pipeline to validate the chart and deploy the
   `nasa-image` Helm release.

The Kubernetes pipeline uses the chart in `helm/` and deploys:

- `nasa-image-app` on port `80`
- `nasa-image-server` on port `3000`

Check the deployment:

```bash
helm --namespace nasa-image status nasa-image
kubectl --namespace nasa-image get deployments,pods,services
```

## Access the application locally

The services are cluster-internal, so use port forwarding.

Frontend:

```bash
kubectl --namespace nasa-image port-forward service/nasa-image-app 8081:80
```

Open <http://localhost:8081>.

Server API:

```bash
kubectl --namespace nasa-image port-forward service/nasa-image-server 3000:3000
```

Open <http://localhost:3000>. If a local port is already occupied, change the
number before the colon; for example, use `3001:3000`.

## Current limitations

- Both application images use the mutable `latest` tag.
- The black-box test step in `pipeline.kube.yaml` is disabled.
- The image-publishing and Kubernetes pipelines are not automatically linked;
  run the image pipeline first.
