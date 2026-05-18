#!/usr/bin/env bash
# Upsert proxied A records for stay.hr API/admin hosts via Cloudflare API.
# Token: CF_DNS_API_TOKEN from Traefik .env (same token used for ACME DNS-01).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRAEFIK_ENV="${TRAEFIK_ENV:-/opt/stacks/traefik/.env}"
SCRIPTS_ENV="${ROOT_DIR}/scripts/.env"
ZONE_NAME="${CLOUDFLARE_ZONE_NAME:-stay.hr}"
DNS_HOSTS="${STAY_DNS_HOSTS:-api.stay.hr admin.stay.hr}"
CF_API="https://api.cloudflare.com/client/v4"

load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
}

load_env_file "$TRAEFIK_ENV"
load_env_file "$SCRIPTS_ENV"

CF_DNS_API_TOKEN="${CF_DNS_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
if [[ -z "$CF_DNS_API_TOKEN" ]]; then
  echo "CF_DNS_API_TOKEN is not set (expected in ${TRAEFIK_ENV})" >&2
  exit 1
fi

cf_api() {
  local method="$1"
  local path="$2"
  local data="${3:-}"
  local args=(-sS -X "$method" "${CF_API}${path}"
    -H "Authorization: Bearer ${CF_DNS_API_TOKEN}"
    -H "Content-Type: application/json")
  if [[ -n "$data" ]]; then
    args+=(--data "$data")
  fi
  curl "${args[@]}"
}

json_success() {
  python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("success") else 1)' <<<"$1"
}

json_get() {
  local expr="$1"
  python3 -c 'import json,sys; d=json.load(sys.stdin); '"$expr" <<<"$2"
}

echo "Verifying Cloudflare API token..."
verify_resp="$(cf_api GET /user/tokens/verify)"
if ! json_success "$verify_resp"; then
  echo "Token verify failed" >&2
  echo "$verify_resp" >&2
  exit 1
fi
echo "Token verify OK"

echo "Resolving zone ID for ${ZONE_NAME}..."
zones_resp="$(cf_api GET "/zones?name=${ZONE_NAME}&status=active")"
if ! json_success "$zones_resp"; then
  echo "Zone lookup failed" >&2
  echo "$zones_resp" >&2
  exit 1
fi
ZONE_ID="$(json_get 'print((d.get("result") or [{}])[0].get("id",""))' "$zones_resp")"
if [[ -z "$ZONE_ID" ]]; then
  echo "Zone ${ZONE_NAME} not found in Cloudflare account" >&2
  exit 1
fi
echo "Zone ID: ${ZONE_ID}"

if [[ -z "${TARGET_SERVER_IP:-}" ]]; then
  echo "TARGET_SERVER_IP not set; reading apex A record for ${ZONE_NAME}..."
  apex_resp="$(cf_api GET "/zones/${ZONE_ID}/dns_records?type=A&name=${ZONE_NAME}")"
  TARGET_SERVER_IP="$(json_get 'print(next((r.get("content") for r in (d.get("result") or []) if r.get("type")=="A"), ""))' "$apex_resp")"
fi
if [[ -z "${TARGET_SERVER_IP:-}" ]]; then
  echo "TARGET_SERVER_IP is required (set in scripts/.env or export before running)" >&2
  exit 1
fi
echo "Target IP: ${TARGET_SERVER_IP}"

upsert_record() {
  local fqdn="$1"
  local list_resp record_id payload upsert_resp

  list_resp="$(cf_api GET "/zones/${ZONE_ID}/dns_records?type=A&name=${fqdn}")"
  record_id="$(json_get 'print((d.get("result") or [{}])[0].get("id",""))' "$list_resp")"

  payload="$(python3 -c 'import json,sys; print(json.dumps({"type":"A","name":sys.argv[1],"content":sys.argv[2],"ttl":1,"proxied":True}))' "$fqdn" "$TARGET_SERVER_IP")"

  if [[ -n "$record_id" ]]; then
    echo "Updating ${fqdn} (id ${record_id})"
    upsert_resp="$(cf_api PUT "/zones/${ZONE_ID}/dns_records/${record_id}" "$payload")"
  else
    echo "Creating ${fqdn}"
    upsert_resp="$(cf_api POST "/zones/${ZONE_ID}/dns_records" "$payload")"
  fi

  if ! json_success "$upsert_resp"; then
    echo "DNS upsert failed for ${fqdn}" >&2
    echo "$upsert_resp" >&2
    exit 1
  fi
  echo "OK: ${fqdn} -> ${TARGET_SERVER_IP} (proxied)"
}

for host in $DNS_HOSTS; do
  upsert_record "$host"
done

echo "Done. Records: ${DNS_HOSTS}"
