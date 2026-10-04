#!/usr/bin/env bash
# Shared by the formal Runtime and sibling synthetic PoC. Source only.
image_options() {
  publish_image=1
  # Resolve the normal user's home before sudo; never discover/read auth files.
  docker_config="$HOME/.config/banfei/docker"
  while (( $# )); do
    case "$1" in
      --build-only) publish_image=0; shift ;;
      --docker-config)
        [[ $# -ge 2 ]] || { echo 'Missing --docker-config directory' >&2; return 2; }
        docker_config=$2; shift 2 ;;
      *) echo "Usage: bash $0 [--build-only] [--docker-config /absolute/directory]" >&2; return 2 ;;
    esac
  done
  repository=swr.cn-southwest-2.myhuaweicloud.com/banfei/banfei-runtime
  [[ "$docker_config" == /* && "$docker_config" != *$'\n'* ]] || {
    echo '--docker-config must be an absolute directory.' >&2; return 2;
  }
  printf 'Docker login directory: %s (explicit --docker-config overrides the fixed user default)\n' "$docker_config"
}
image_docker() { sudo docker --config "$docker_config" "$@"; }
image_new_tag() {
  local prefix=$1 nonce
  nonce=$(cat /proc/sys/kernel/random/uuid)
  [[ "$nonce" =~ ^[a-f0-9-]{36}$ ]] || return 1
  image_tag="banfei-runtime:$prefix-$(date -u +%Y%m%dT%H%M%SZ)-$nonce"
  target="$repository:${image_tag#*:}"
  if image_docker image inspect "$image_tag" >/dev/null 2>&1 ||
     image_docker image inspect "$target" >/dev/null 2>&1; then
    echo 'Generated tag already exists; no overwrite.' >&2; return 1
  fi
}
image_verify() {
  image_docker image inspect "$image_tag" | python3 -c '
import json,sys
items=json.load(sys.stdin)
if len(items)!=1: raise SystemExit("Expected one image")
x=items[0]
if (x.get("Os"),x.get("Architecture"))!=("linux","arm64"): raise SystemExit("Wrong architecture")
if x.get("Descriptor",{}).get("mediaType")!="application/vnd.docker.distribution.manifest.v2+json": raise SystemExit("Expected single Docker V2 manifest")
if x.get("Config",{}).get("User")!="10001:10001": raise SystemExit("Expected UID 10001:10001")
print(json.dumps({"checked":"ARM64, single Docker V2 manifest, UID 10001","image_id":x["Id"]}))
'
}
image_publish() {
  if [[ "$publish_image" == 0 ]]; then
    printf '\nBUILD ONLY: %s\n' "$image_tag"; return 0
  fi
  image_verify
  local probe push_log digest
  probe=$(mktemp /tmp/banfei-swr-manifest.XXXXXX)
  # Fail closed if registry lookup cannot distinguish absence from auth/network errors.
  if image_docker manifest inspect "$target" >"$probe" 2>&1; then
    rm -f -- "$probe"
    echo 'Remote tag already exists; refusing to overwrite it.' >&2; return 1
  fi
  if ! grep -Eiq 'manifest unknown|no such manifest|MANIFEST_UNKNOWN' "$probe"; then
    rm -f -- "$probe"
    echo 'SWR lookup failed (login, permission or network). No push or retry. Log in manually using --password-stdin and the same --config directory, then rerun.' >&2
    return 1
  fi
  rm -f -- "$probe"
  image_docker tag "$image_tag" "$target"
  push_log=$(mktemp /tmp/banfei-swr-push.XXXXXX)
  if ! image_docker push "$target" 2>&1 | tee "$push_log"; then
    rm -f -- "$push_log"
    echo 'SWR push failed; no automatic retry. If login expired, renew it manually using --password-stdin and the same --config directory.' >&2
    return 1
  fi
  digest=$(python3 - "$push_log" <<'PY_DIGEST'
import re,sys
from pathlib import Path
matches=set(re.findall(r"\bdigest:\s*(sha256:[0-9a-f]{64})\b",Path(sys.argv[1]).read_text()))
if len(matches)!=1: raise SystemExit("Push returned no unique digest; publication cannot be confirmed")
print(matches.pop())
PY_DIGEST
  ) || { rm -f -- "$push_log"; return 1; }
  rm -f -- "$push_log"
  printf '\nPUSHED_IMAGE=%s\nPUSHED_DIGEST=%s\nIMMUTABLE_IMAGE=%s@%s\n' "$target" "$digest" "$repository" "$digest"
}
