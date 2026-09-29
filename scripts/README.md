# Scripts

## Install Buildkite on a Rancher-managed Kubernetes cluster

`setup-buildkite-rancher.sh` installs or updates the official Buildkite Agent
Stack for Kubernetes. Rancher supplies the Kubernetes cluster and kubeconfig;
the script operates against the selected `kubectl` context just like any other
Kubernetes cluster.

Prerequisites:

- a kubeconfig downloaded from Rancher with access to the target cluster;
- `kubectl` and Helm 3.8 or later;
- an existing Buildkite cluster, self-hosted queue, and cluster agent token;
- permission to create a namespace, Secret, and Helm-managed resources.


Preview the installation:

```bash
export BUILDKITE_AGENT_TOKEN='bkct_replace_me'
scripts/rancher/setup-buildkite-rancher.sh \
  --context rancher-desktop \
  --queue kube \
  --dry-run
```

Install it:

```bash
scripts/rancher/setup-buildkite-rancher.sh \
  --context rancher-desktop \
  --queue kube
```

If `BUILDKITE_AGENT_TOKEN` is not exported, the script prompts for it without
echoing it. For automation, `--agent-token` is supported, but an environment
variable or secret-manager injection is preferable because command arguments
can be visible to other processes. The token is stored in a Kubernetes Secret,
not in Helm release values.

To update the agent token run 

```bash 
  helm upgrade agent-stack-k8s \
      oci://ghcr.io/buildkite/helm/agent-stack-k8s \
      -n buildkite \
      --reuse-values \
      --set-string agentStackSecret= \
      --set-string agentToken='bkct_TOKEN_FROM_CORRECT_CLUSTER' \
      --set-string config.queue='QUEUE_FROM_CORRECT_CLUSTER'
```

The queue must already exist in the same Buildkite cluster as the token. Target
it explicitly from a pipeline step:

```yaml
steps:
  - label: ":k8s: Rancher smoke test"
    command: "buildkite-agent --version"
    agents:
      queue: "kube"
```

Buildkite requires each Agent Stack controller in an organization to have a
unique stack ID. The Helm release name becomes that ID, so pass a unique
`--release` value if you operate more than one Kubernetes stack.

By default, the script installs or upgrades the existing `agent-stack-k8s`
release in the `buildkite` namespace.

Run `scripts/setup-buildkite-rancher.sh --help` for namespace, release,
concurrency, chart-version, and non-interactive options.

## Webhook-triggered agents

The watcher starts the `buildkite-agent` binary directly on the host when a
matching Buildkite `job.scheduled` event arrives. It does not use an agent
container or `BUILDKITE_AGENT_IMAGE`. Install `buildkite-agent` on the watcher
host and ensure it is on `PATH`.

Set `WEBHOOK_SITE_TOKEN` to the Webhook.site inbox token and
`BUILDKITE_AGENT_TOKEN` to the cluster queue token, then start the watcher:

```bash
python3 scripts/webhook-acquire-agent.py
```

The watcher defaults to queue `webhook-acquire`, matching `.buildkite/pipeline.yaml`.
Set `BUILDKITE_TARGET_QUEUE` if your pipeline uses another queue. Set
`BUILDKITE_PIPELINE_SLUG` to restrict events to one pipeline, and
`BUILDKITE_WEBHOOK_TOKEN` to verify the Buildkite webhook signature.

For PRs, GitHub must trigger a Buildkite build, and that build must schedule a
job on the target queue. The watcher responds to that scheduled job; it does
not consume GitHub pull request events directly. Keep the watcher running
before opening a PR or triggering a build. By default it ignores events that
were already in the inbox when it started.

For an SSH repository URL, the host user running the watcher needs an SSH key
authorized for the repository and a verified `known_hosts` entry. The agent
inherits that user's environment and SSH configuration.

The pipeline's Docker build and push commands still need Docker on the agent
host. They run after the agent starts and are separate from agent startup. The
pipeline uses a temporary `DOCKER_CONFIG` for each job and writes its short-lived
OIDC registry credential there without calling `docker login`. This avoids the
host's macOS Keychain. It initializes the config before `docker build` so Docker
does not auto-select the macOS credential helper while pulling public base
images. The temporary config is deleted when the job ends.

To inspect commands for existing events without launching agents, run:

```bash
python3 scripts/webhook-acquire-agent.py --once --replay-existing --dry-run
```
