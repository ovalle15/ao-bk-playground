#!/usr/bin/env bash

set -Eeuo pipefail

# The Agent Stack chart runs a controller that turns queued Buildkite jobs into
# short-lived Kubernetes Jobs in the selected Rancher-managed cluster.
readonly DEFAULT_CHART="oci://ghcr.io/buildkite/helm/agent-stack-k8s"

# Defaults can be overridden with the command-line options documented in usage().
namespace="buildkite"
release="agent-stack-k8s"
queue="kube"
secret_name="buildkite-agent-token"
max_in_flight="10"
kube_context=""
kubeconfig=""
chart="$DEFAULT_CHART"
chart_version=""
agent_token="${BUILDKITE_AGENT_TOKEN:-}"
assume_yes="false"
dry_run="false"

usage() {
  cat <<'USAGE'
Install or update the Buildkite Agent Stack in a Rancher-managed Kubernetes cluster.

Usage:
  setup-buildkite-rancher.sh [options]

Options:
  --context NAME          kubectl context for the Rancher-managed cluster
  --kubeconfig PATH       Rancher-downloaded kubeconfig file
  --namespace NAME        Kubernetes namespace (default: buildkite)
  --release NAME          Unique Helm release name (default: agent-stack-k8s)
  --queue NAME            Existing Buildkite self-hosted queue (default: kube)
  --secret-name NAME      Kubernetes Secret name (default: buildkite-agent-token)
  --max-in-flight NUMBER  Maximum concurrent Buildkite jobs (default: 10; 0 is unlimited)
  --agent-token TOKEN     Buildkite cluster agent token (prefer the environment or prompt)
  --chart-version VERSION Pin the Agent Stack Helm chart version
  --dry-run               Validate and render the Helm upgrade without changing the cluster
  --yes                   Do not ask for confirmation
  -h, --help              Show this help

Token input precedence:
  1. --agent-token
  2. BUILDKITE_AGENT_TOKEN
  3. a hidden interactive prompt

The token must be a cluster agent token (bkct_...), not a Buildkite REST API token.
USAGE
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_value() {
  local option="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || fail "$option requires a value"
}

# Parse options before checking dependencies so --help works on machines that do
# not have kubectl or Helm installed yet.
while (($# > 0)); do
  case "$1" in
    --context)
      require_value "$1" "${2:-}"
      kube_context="$2"
      shift 2
      ;;
    --kubeconfig)
      require_value "$1" "${2:-}"
      kubeconfig="$2"
      shift 2
      ;;
    --namespace)
      require_value "$1" "${2:-}"
      namespace="$2"
      shift 2
      ;;
    --release)
      require_value "$1" "${2:-}"
      release="$2"
      shift 2
      ;;
    --queue)
      require_value "$1" "${2:-}"
      queue="$2"
      shift 2
      ;;
    --secret-name)
      require_value "$1" "${2:-}"
      secret_name="$2"
      shift 2
      ;;
    --max-in-flight)
      require_value "$1" "${2:-}"
      max_in_flight="$2"
      shift 2
      ;;
    --agent-token)
      require_value "$1" "${2:-}"
      agent_token="$2"
      shift 2
      ;;
    --chart-version)
      require_value "$1" "${2:-}"
      chart_version="$2"
      shift 2
      ;;
    --dry-run)
      dry_run="true"
      shift
      ;;
    --yes)
      assume_yes="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1 (use --help)"
      ;;
  esac
done

require_command kubectl
require_command helm

# max-in-flight is passed to Helm as an integer, so reject shell expressions and
# other non-numeric input before constructing the Helm command.
[[ "$max_in_flight" =~ ^[0-9]+$ ]] || fail "--max-in-flight must be zero or a positive integer"

# Keep kubeconfig and context arguments in an array so paths containing spaces
# remain a single argument and every kubectl invocation targets the same cluster.
kubectl_args=()
if [[ -n "$kubeconfig" ]]; then
  [[ -r "$kubeconfig" ]] || fail "kubeconfig is not readable: $kubeconfig"
  kubectl_args+=(--kubeconfig "$kubeconfig")
fi
if [[ -n "$kube_context" ]]; then
  kubectl_args+=(--context "$kube_context")
fi

current_context="$(kubectl "${kubectl_args[@]}" config current-context)"
[[ -n "$current_context" ]] || fail "kubectl has no current context"

# Display the resolved destination before making any cluster changes. This is
# especially important when one kubeconfig contains several Rancher clusters.
printf 'Kubernetes context: %s\n' "$current_context"
printf 'Namespace:          %s\n' "$namespace"
printf 'Buildkite queue:    %s\n' "$queue"
printf 'Helm release:       %s\n' "$release"

kubectl "${kubectl_args[@]}" cluster-info >/dev/null

# Prefer an environment variable for automation. If none was supplied and the
# shell is interactive, read the token without echoing it to the terminal.
if [[ -z "$agent_token" && -t 0 ]]; then
  read -r -s -p "Buildkite cluster agent token (bkct_...): " agent_token
  printf '\n'
fi
[[ -n "$agent_token" ]] || fail "set BUILDKITE_AGENT_TOKEN, use --agent-token, or run interactively"
[[ "$agent_token" == bkct_* ]] || fail "the agent token must start with bkct_"

if [[ "$assume_yes" != "true" && "$dry_run" != "true" ]]; then
  [[ -t 0 ]] || fail "non-interactive execution requires --yes"
  read -r -p "Install or update Buildkite in this cluster? [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]] || {
    printf 'Cancelled.\n'
    exit 0
  }
fi

# Reference a Kubernetes Secret rather than passing the token through Helm. This
# keeps the new credential out of Helm release values and rendered manifests.
helm_args=(
  upgrade --install "$release" "$chart"
  --namespace "$namespace"
  --create-namespace
  --reuse-values
  --set-string "agentStackSecret=$secret_name"
  --set-string "config.queue=$queue"
  --set "config.max-in-flight=$max_in_flight"
  --wait
  --timeout 5m
)
if [[ -n "$kubeconfig" ]]; then
  helm_args+=(--kubeconfig "$kubeconfig")
fi
if [[ -n "$kube_context" ]]; then
  helm_args+=(--kube-context "$kube_context")
fi
if [[ -n "$chart_version" ]]; then
  helm_args+=(--version "$chart_version")
fi

if [[ "$dry_run" == "true" ]]; then
  printf 'Dry run: the token Secret would be created or updated; its value is not rendered.\n'
  helm "${helm_args[@]}" --dry-run=client
  exit 0
fi

# Create the namespace idempotently. Applying the generated manifest makes the
# command safe for both the first installation and subsequent updates.
kubectl "${kubectl_args[@]}" create namespace "$namespace" \
  --dry-run=client -o yaml | kubectl "${kubectl_args[@]}" apply -f - >/dev/null

# Write the token to a mode-0600 temporary file so it does not appear in the
# kubectl process arguments. The EXIT trap removes it if Secret creation fails.
token_file="$(mktemp)"
trap 'rm -f "$token_file"' EXIT
chmod 600 "$token_file"
printf '%s' "$agent_token" >"$token_file"

kubectl "${kubectl_args[@]}" --namespace "$namespace" create secret generic "$secret_name" \
  --from-file="BUILDKITE_AGENT_TOKEN=$token_file" \
  --dry-run=client -o yaml | kubectl "${kubectl_args[@]}" apply -f - >/dev/null

rm -f "$token_file"
trap - EXIT
# Remove the credential from this process before invoking Helm.
unset agent_token BUILDKITE_AGENT_TOKEN || true

# Install on the first run and upgrade on later runs. Explicit --set values take
# precedence over reused release values for the Secret, queue, and concurrency.
helm "${helm_args[@]}"

# The official chart names this controller Deployment after the Helm release.
# It does not provide an app.kubernetes.io/instance label, so looking it up with
# a release-label selector incorrectly returns an empty result.
deployment="deployment/$release"
kubectl "${kubectl_args[@]}" --namespace "$namespace" get "$deployment" >/dev/null || \
  fail "Helm succeeded, but $deployment is not present in namespace $namespace"

# An externally managed Secret change does not alter the Deployment template,
# so force a rollout to make the controller read the rotated token immediately.
kubectl "${kubectl_args[@]}" --namespace "$namespace" rollout restart "$deployment" >/dev/null
kubectl "${kubectl_args[@]}" --namespace "$namespace" rollout status "$deployment" --timeout=5m

printf '\nBuildkite Agent Stack is ready. Target this queue in pipeline YAML with:\n'
printf 'agents:\n  queue: %s\n' "$queue"
printf '\nController logs:\n'
printf 'kubectl --context %q --namespace %q logs %q --follow\n' \
  "$current_context" "$namespace" "$deployment"
