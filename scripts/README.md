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

## Webhook agent checkout over SSH

For an SSH repository URL, give the Docker agent access to a directory with
an authorized private key and a verified `known_hosts` file:

```bash
python3 scripts/webhook-acquire-agent.py --ssh-dir "$HOME/.ssh"
```

Alternatively, export `BUILDKITE_SSH_DIR` before starting the watcher. Without
either setting, the launcher does not mount SSH files.

For a key with a nonstandard filename, select it explicitly:

```bash
python3 scripts/webhook-acquire-agent.py \
  --ssh-dir "$HOME/.ssh" --ssh-key buildkite_spacecamp
```

Alternatively, export `BUILDKITE_SSH_KEY=buildkite_spacecamp`. The key must be
a file inside the SSH directory. This sets `GIT_SSH_COMMAND` inside the
container with the selected identity, batch mode, and strict host verification.

The directory is mounted read-only at `/root/.ssh`, matching the root user in
`ao-buildkite-acquire-agent:local`. Use a dedicated directory with a repository
deploy key to limit which credentials the job can access. Standard key names
such as `id_ed25519` work automatically; other names need `--ssh-key` or an
`IdentityFile` entry in the directory's `config`, using the path inside the container.
Any SSH configuration must work with Linux OpenSSH, including its file paths.

The launcher sets `BUILDKITE_NO_SSH_KEYSCAN=true` so checkout uses the supplied
host keys without trying to update the read-only directory. Ensure the Git
server's verified host key is already in `known_hosts`. Private key files
should have mode `600` and the directory mode `700`.

This option mounts files, not the host's SSH agent. Passphrase-protected keys
need a separate SSH agent setup for unattended checkout. Images running as a
different user need an appropriate mount target instead of `/root/.ssh`.

Start the watcher before triggering a fresh build. To inspect generated Docker
commands for existing events without launching agents, add
`--once --replay-existing --dry-run`; event filters and webhook verification
still apply.
