#!/usr/bin/env bash
set -euo pipefail
# User-approved, interactive sudo only. No docker group/sudoers/TCP/binfmt changes.
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_CODENAME" == noble ]] || { echo 'Expected Ubuntu noble'; exit 1; }
[[ $(id -u) != 0 ]] || { echo 'Run as your normal WSL user; sudo will prompt.'; exit 1; }
for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
    echo "Existing conflicting package $package: stop for review, do not uninstall automatically."; exit 1
  fi
done
[[ ! -e /etc/apt/sources.list.d/docker.sources && ! -e /etc/apt/sources.list.d/docker.list ]] || { echo 'Docker source already exists; inspect first.'; exit 1; }
task_tmp=$(mktemp -d)
trap 'rm -f "$task_tmp/docker.asc" "$task_tmp/docker.sources"; rmdir "$task_tmp"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 https://download.docker.com/linux/ubuntu/gpg -o "$task_tmp/docker.asc"
fingerprint=$(gpg --show-keys --with-colons "$task_tmp/docker.asc" | awk -F: '$1=="fpr" {print $10;exit}')
[[ "$fingerprint" == 9DC858229FC7DD38854AE2D88D81803C0EBFCD88 ]] || { echo 'Unexpected Docker signing key; stop for review.'; exit 1; }
printf 'Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: %s
Signed-By: /etc/apt/keyrings/docker.asc
' "$(dpkg --print-architecture)" > "$task_tmp/docker.sources"
sudo -v
sudo install -m 0755 -d /etc/apt/keyrings
sudo install -m 0644 "$task_tmp/docker.asc" /etc/apt/keyrings/docker.asc
sudo install -m 0644 "$task_tmp/docker.sources" /etc/apt/sources.list.d/docker.sources
sudo apt-get update
sudo apt-get install --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin
sudo systemctl start docker
sudo docker version
sudo docker buildx version
printf '
Installed. No docker group, remote TCP, passwordless sudo or binfmt registration configured.
'
