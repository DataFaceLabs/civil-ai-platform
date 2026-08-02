#!/usr/bin/env bash
# Single source of truth for OpenTofu environment config (H0-IACDRIFT).
#
# THE PROBLEM THIS SOLVES
#
# `terraform.tfvars` is gitignored -- correctly, it holds github_access_token and
# mapbox_access_token. That left production configuration and secrets living only
# as a file on one laptop: no backup, no history, unshareable, and invisible to CI.
# It is why the scheduled drift check could not run: without these values, 8 of 16
# variables fall back to defaults that differ from reality, and three of those are
# feature toggles (create_amplify_app et al) whose defaults would make `tofu plan`
# propose destroying live modules.
#
# So the file moves to SSM Parameter Store and becomes a *derived artifact*:
#
#     SSM (source of truth)  --pull-->  terraform.tfvars (generated, gitignored)
#
# WHY THE WHOLE FILE, NOT ONE PARAMETER PER VARIABLE
#
# Storing it as a single SecureString preserves HCL exactly -- multi-line lists,
# comments, and the reasoning embedded in those comments, which is load-bearing
# here (e.g. why ses_from_email is empty, why fe_production_branch_name must stay
# "main"). Splitting it would require an HCL parser in bash, lose the comments,
# and make updates non-atomic. At 2.8 KB it fits a Standard tier parameter (4 KB).
#
# WHY NOT REWRITE THE TERRAFORM TO READ SSM VIA data SOURCES
#
# That was the first instinct and it is worse: it would touch every `var.` reference
# across the root module and children, and any mistake changes the plan on live,
# customer-facing infrastructure. This approach leaves the Terraform byte-identical,
# so the generated plan is provably unchanged -- see `verify`.
#
# USAGE
#
#   ./scripts/tofu-config.sh push [env]    # local tfvars -> SSM (needs write access)
#   ./scripts/tofu-config.sh pull [env]    # SSM -> local tfvars (CI and laptops)
#   ./scripts/tofu-config.sh diff [env]    # show whether they disagree
#
# `env` defaults to uat.
set -euo pipefail

ENVIRONMENT="${2:-uat}"
AWS_REGION="${AWS_REGION:-us-east-1}"
PARAM_NAME="/civilai/${ENVIRONMENT}/tofu/terraform.tfvars"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TFVARS="${ROOT}/infra/opentofu/environments/${ENVIRONMENT}/terraform.tfvars"

aws_cli() {
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"
  else
    # CI assumes a role via OIDC and has no named profile.
    aws --region "$AWS_REGION" "$@"
  fi
}

# `--output text` appends a newline to the value, and the stored value already
# ends with one. Left alone, every round trip grows a blank line and `diff` reports
# DIVERGED forever -- a check that cries wolf is worse than no check. Command
# substitution strips ALL trailing newlines; printf puts back exactly one, so the
# result is byte-identical to a normal POSIX text file every time.
fetch() {
  local value
  value="$(aws_cli ssm get-parameter --name "$PARAM_NAME" --with-decryption \
    --query 'Parameter.Value' --output text)"
  printf '%s\n' "$value"
}

case "${1:-}" in
  push)
    [[ -f "$TFVARS" ]] || { echo "No local tfvars at $TFVARS" >&2; exit 1; }
    if remote="$(fetch 2>/dev/null)"; then
      if [[ "$remote" == "$(cat "$TFVARS")" ]]; then
        echo "SSM already matches local tfvars — nothing to push."
        exit 0
      fi
      echo "WARNING: this overwrites the stored config for '${ENVIRONMENT}'."
      echo "Differences (SSM -> local):"
      # Never print values: keys only. These lines can contain live tokens.
      diff <(grep -oE '^[a-z_]+' <<<"$remote" | sort -u) \
           <(grep -oE '^[a-z_]+' "$TFVARS" | sort -u) || true
      read -r -p "Type 'push' to overwrite: " reply
      [[ "$reply" == "push" ]] || { echo "Aborted."; exit 1; }
    fi
    aws_cli ssm put-parameter \
      --name "$PARAM_NAME" \
      --type SecureString \
      --value "file://${TFVARS}" \
      --overwrite \
      --description "OpenTofu tfvars for ${ENVIRONMENT}. Source of truth; terraform.tfvars is generated from this." \
      >/dev/null
    echo "Pushed $(wc -c <"$TFVARS" | tr -d ' ') bytes to ${PARAM_NAME}"
    ;;

  pull)
    mkdir -p "$(dirname "$TFVARS")"
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    fetch >"$tmp"
    # Written atomically so an interrupted pull cannot leave a half-file that
    # plans against partial config.
    mv -f "$tmp" "$TFVARS"
    trap - EXIT
    echo "Wrote ${TFVARS} ($(wc -c <"$TFVARS" | tr -d ' ') bytes) from ${PARAM_NAME}"
    ;;

  diff)
    [[ -f "$TFVARS" ]] || { echo "No local tfvars at $TFVARS (run: $0 pull)" >&2; exit 1; }
    if diff -q <(fetch) "$TFVARS" >/dev/null 2>&1; then
      echo "in sync: local tfvars matches ${PARAM_NAME}"
    else
      echo "DIVERGED: local tfvars differs from ${PARAM_NAME}" >&2
      echo "  (values withheld — they contain secrets. Keys differing:)" >&2
      diff <(fetch | grep -oE '^[a-z_]+' | sort -u) \
           <(grep -oE '^[a-z_]+' "$TFVARS" | sort -u) >&2 || true
      exit 1
    fi
    ;;

  *)
    sed -n '2,44p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
