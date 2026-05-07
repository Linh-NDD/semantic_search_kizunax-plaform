#!/usr/bin/env bash
set -euo pipefail
VERSION="${QDRANT_VERSION:-v1.17.1}"
BASE="${RAG_HOME:-/opt/rag}"
mkdir -p "$BASE/bin" "$BASE/storage" "$BASE/config"
if [ -x "$BASE/bin/qdrant" ]; then
  echo "Qdrant already exists: $BASE/bin/qdrant"
  "$BASE/bin/qdrant" --version || true
  exit 0
fi
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ASSET="qdrant-x86_64-unknown-linux-musl.tar.gz" ;;
  aarch64|arm64) ASSET="qdrant-aarch64-unknown-linux-musl.tar.gz" ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac
URL="https://github.com/qdrant/qdrant/releases/download/${VERSION}/${ASSET}"
echo "Downloading $URL"
tmp="$(mktemp -d)"
trap rm -rf  EXIT
curl -L --fail --retry 3 -o "$tmp/qdrant.tgz" "$URL"
tar -xzf "$tmp/qdrant.tgz" -C "$tmp"
install -m 0755 "$(find "$tmp" -maxdepth 2 -type f -name qdrant | head -n1)" "$BASE/bin/qdrant"
"$BASE/bin/qdrant" --version
