#!/usr/bin/env bash
# Shared helpers for ops scripts (benchmark, load test).

resolve_git_sha() {
  local root="${1:-.}"
  if [[ -n "${STAY_GIT_SHA:-}" ]]; then
    printf '%s' "$STAY_GIT_SHA"
  elif command -v git >/dev/null 2>&1 && git -C "$root" rev-parse --short HEAD 2>/dev/null; then
    git -C "$root" rev-parse --short HEAD
  else
    printf 'unknown'
  fi
}

benchmark_header() {
  local label="${1:-}"
  local root="${2:-.}"
  printf 'timestamp=%s\n' "$(date -Iseconds)"
  printf 'git_sha=%s\n' "$(resolve_git_sha "$root")"
  [[ -n "$label" ]] && printf 'label=%s\n' "$label"
}

status_active_sse() {
  local status_url="$1"
  local token="$2"
  curl -sS --max-time 5 -H "Authorization: Bearer ${token}" "$status_url" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['sse']['active_connections'])"
}

ci_artifact_path() {
  local prefix="$1"
  local artifact_dir="${OPS_CI_ARTIFACT_DIR:-}"
  [[ -z "$artifact_dir" ]] && return 1
  mkdir -p "$artifact_dir"
  printf '%s/%s-%s.txt' "$artifact_dir" "$prefix" "$(date +%Y%m%dT%H%M%S)"
}

setup_ci_artifact_tee() {
  local prefix="$1"
  local artifact_file
  artifact_file="$(ci_artifact_path "$prefix")" || return 0
  exec > >(tee "$artifact_file") 2>&1
  printf 'ci_artifact=%s\n' "$artifact_file"
}

is_truthy() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1 | true | yes | on) return 0 ;;
    *) return 1 ;;
  esac
}
