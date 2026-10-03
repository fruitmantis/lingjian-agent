#!/usr/bin/env bash
set -euo pipefail
# Run ONLY after separate approval for transient ARM64 binfmt + sudo Docker build.
# User authenticates sudo locally. No groups, sudoers, TCP, persistent binfmt or cloud push.
[[ $(id -u) != 0 ]] || { echo 'Run as the normal WSL user.'; exit 1; }
repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
[[ "$repo_root" == /home/yuan/project/lingjian-agent-agentarts ]] || { echo 'Unexpected worktree'; exit 1; }
cd -- "$repo_root"
qemu_source="$repo_root/.isolation/build-tools/qemu-extracted/usr/bin/qemu-aarch64-static"
qemu_config="$repo_root/.isolation/build-tools/qemu-extracted/usr/lib/binfmt.d/qemu-aarch64.conf"
expected_sha=e4f8d99e9ff69c3cefffab71cee358ce2af1ecba1282d04c3eeb44ef76f5a71e
[[ $(sha256sum "$qemu_source" | cut -d ' ' -f1) == "$expected_sha" ]] || { echo 'QEMU hash mismatch'; exit 1; }
[[ $(cat /proc/sys/fs/binfmt_misc/status) == enabled ]] || { echo 'binfmt_misc is not enabled; stop'; exit 1; }
evidence=$(mktemp -d /tmp/banfei-arm64-image-XXXXXX)
run_nonce=$(cat /proc/sys/kernel/random/uuid)
registration_name="banfei-aarch64-$run_nonce"
root_temp="/var/tmp/banfei-arm64.$run_nonce"
entry_path="/proc/sys/fs/binfmt_misc/$registration_name"
root_created=0
[[ ! -e "$entry_path" && ! -e "$root_temp" ]] || { echo "Generated recovery path already exists; stop without cleanup"; exit 1; }
record_state() {
  printf 'state=%s\nregistration=%s\nentry=%s\ninterpreter=%s/aarch64-binfmt-P\n' \
    "$1" "$registration_name" "$entry_path" "$root_temp" > "$evidence/.cleanup-state.next"
  sync -f "$evidence/.cleanup-state.next"
  mv -- "$evidence/.cleanup-state.next" "$evidence/cleanup-state.txt"
  sync -f "$evidence"
}
cleanup() {
  local result=$?
  trap - EXIT INT TERM
  record_state cleanup_started || result=1
  if [[ -e "$entry_path" ]]; then
    printf '%s\n' -1 | sudo tee "$entry_path" >/dev/null || result=1
  fi
  if [[ -e "$entry_path" ]]; then
    record_state registration_remains_interpreter_preserved || true
    printf '\nCleanup incomplete: %s remains. Interpreter preserved at %s/aarch64-binfmt-P\n' "$entry_path" "$root_temp" >&2
    result=1
  elif [[ "$root_created" == 1 ]]; then
    if sudo rm -f -- "$root_temp/aarch64-binfmt-P" && sudo rmdir -- "$root_temp"; then
      record_state cleaned || result=1
      printf '\nVerified: own registration and temporary interpreter removed.\n'
    else
      record_state interpreter_cleanup_incomplete || true
      printf '\nRegistration absent; temporary interpreter cleanup incomplete: %s\n' "$root_temp" >&2
      result=1
    fi
  elif [[ -d "$root_temp" ]]; then
    record_state directory_ownership_unconfirmed_preserved || true
    printf '\nNo registration; directory ownership could not be confirmed, preserved: %s\n' "$root_temp" >&2
    result=1
  else
    record_state no_registration_no_directory || result=1
  fi
  printf '\nEvidence and precise recovery paths: %s/cleanup-state.txt\n' "$evidence"
  exit "$result"
}
# Record exact paths before any privileged change; survives SIGKILL for manual recovery.
record_state prepared
printf 'Evidence and recovery paths: %s/cleanup-state.txt\n' "$evidence"
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
sudo -v
sudo docker version > "$evidence/docker-version.txt"
[[ "$root_temp" =~ ^/var/tmp/banfei-arm64\.[a-f0-9-]+$ ]] || exit 1
record_state directory_creation_requested
sudo mkdir -m 0700 -- "$root_temp"
root_created=1
record_state directory_created
sudo install -m 0755 "$qemu_source" "$root_temp/aarch64-binfmt-P"
# These values are from Ubuntu's signed-index-verified QEMU 8.2.2 package.
registration=$(cat "$qemu_config")
registration=${registration/:qemu-aarch64:/:$registration_name:}
registration=${registration/\/usr\/libexec\/qemu-binfmt\/aarch64-binfmt-P/$root_temp\/aarch64-binfmt-P}
record_state registration_requested
printf '%s\n' "$registration" | sudo tee /proc/sys/fs/binfmt_misc/register >/dev/null
[[ -e "$entry_path" ]] || { echo 'Registration not visible'; exit 1; }
record_state registered
cat "/proc/sys/fs/binfmt_misc/$registration_name" > "$evidence/binfmt.txt"
image_tag="banfei-runtime:agentarts-swr-$(date -u +%Y%m%d%H%M%S)"
printf '%s\n' "$image_tag" > "$evidence/image-tag.txt"
# SWR Basic compatibility: one ARM64 Docker V2 manifest, no OCI attestation index.
# The existing default Docker driver loads type=image into its local image store.
sudo docker buildx build --builder default --platform linux/arm64 --progress plain \
  --provenance=false --sbom=false \
  --output type=image,oci-mediatypes=false,push=false,store=true \
  -f deploy/agentarts/Dockerfile -t "$image_tag" . 2>&1 | tee "$evidence/build.log"
sudo docker image inspect "$image_tag" > "$evidence/image-inspect.json"
python3 - "$evidence/image-inspect.json" <<'PY_FORMAT' | tee "$evidence/format-check.log"
import json, sys
from pathlib import Path
images=json.loads(Path(sys.argv[1]).read_text())
if len(images)!=1:raise SystemExit('FORMAT FAILED: expected exactly one inspected image')
image=images[0]
media_type=image.get('Descriptor',{}).get('mediaType')
if media_type!='application/vnd.docker.distribution.manifest.v2+json':
    raise SystemExit('FORMAT FAILED: expected single Docker V2 manifest, observed '+str(media_type)+'; do not push')
if (image.get('Os'),image.get('Architecture'))!=('linux','arm64'):
    raise SystemExit('FORMAT FAILED: expected linux/arm64; do not push')
print(json.dumps({'status':'passed','mediaType':media_type,'platform':'linux/arm64',
    'image_id':image['Id'],'tags':image.get('RepoTags',[])}))
PY_FORMAT
# No network, published port, host data mount, real credential or valid model job.
sudo docker run --platform linux/arm64 --rm -i --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint python "$image_tag" -B - \
  <<'PY' 2>&1 | tee "$evidence/smoke.log"
import json, os, platform, sys, threading, time, urllib.error, urllib.request, uuid
assert platform.machine() == 'aarch64', platform.machine()
assert os.getuid() == 10001, os.getuid()
os.environ.update(BANFEI_RUNTIME_SHARED_KEY='synthetic-local-smoke-key-00000000000000',
 BANFEI_RUNTIME_MODEL_URL='https://example.invalid/v1',
 BANFEI_RUNTIME_MODEL_NAME='synthetic-no-call', BANFEI_RUNTIME_MODEL_KEY='synthetic-no-call')
from backend.agent_runtime.server import app
assert 'backend.app.database' not in sys.modules
import uvicorn
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8080,access_log=False,log_level='warning'))
thread=threading.Thread(target=server.run,daemon=True); thread.start()
for _ in range(200):
 if server.started: break
 time.sleep(.05)
assert server.started, 'Runtime did not start'
def call(path, headers=None, body=None):
 request=urllib.request.Request('http://127.0.0.1:8080'+path,headers=headers or {},data=body)
 try:
  with urllib.request.urlopen(request,timeout=5) as response: return response.status,response.read().decode()
 except urllib.error.HTTPError as error: return error.code,error.read().decode()
assert call('/ping')[0] == 200
assert call('/runtime-info')[0] == 401
headers={'X-Banfei-Runtime-Key':os.environ['BANFEI_RUNTIME_SHARED_KEY'],
 'X-Hw-Agentarts-Session-Id':str(uuid.uuid4()),'Content-Type':'application/json'}
status,body=call('/runtime-info',headers); assert status==200,(status,body)
assert call('/jobs',headers,b'{}')[0] == 422
server.should_exit=True; thread.join(timeout=5)
assert not thread.is_alive()
print(json.dumps({'architecture':platform.machine(),'uid':os.getuid(),
 'health':200,'unauthenticated':401,'authenticated':200,'invalid_job':422,
 'database_imported':False,'model_requests':0,'network':'none'}))
PY
printf '\nARM64 build and isolated smoke PASSED: %s\n' "$image_tag"
