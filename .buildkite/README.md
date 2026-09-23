# Buildkite pipelines

This repository has two active Buildkite pipeline definitions:

| File | Queue | Purpose |
| --- | --- | --- |
| `pipeline.yml` | `webhook-acquire` | Build and publish the frontend and server images. |
| `pipeline.kube.yaml` | `kube` | Validate the Helm chart and deploy the images to Rancher Desktop Kubernetes. |


## Buildkite pipeline configuration

Configure the image-publishing pipeline with:

```yaml
steps:
  - label: ":pipeline: Upload image pipeline"
    command: buildkite-agent pipeline upload .buildkite/pipeline.yml
```

Configure the Kubernetes deployment pipeline with:

```yaml
steps:
  - label: ":pipeline: Upload Kubernetes pipeline"
    command: buildkite-agent pipeline upload .buildkite/pipeline.kube.yaml
```

## Image publishing

`pipeline.yml` builds and pushes these images to Buildkite Packages:

- `packages.buildkite.com/tam-sandbox/ao-bk-playground/app:latest`
- `packages.buildkite.com/tam-sandbox/ao-bk-playground/server:latest`

The job requires Docker and a Buildkite agent that supports
`buildkite-agent oidc request-token`. The Buildkite Packages registry must have
an OIDC policy that permits this pipeline to publish images.

## Kubernetes setup with Rancher Desktop

Prerequisites:

- Rancher Desktop Kubernetes is running.
- `kubectl` and Helm are installed.
- The `kube` queue exists in the intended Buildkite cluster.
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
