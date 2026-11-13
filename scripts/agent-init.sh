#!/bin/bash

set -euo pipefail

# The site's Vite dev server (corepack yarn start) listens here; see site/vite.config.ts.
get_default_app_url() {
  echo "http://localhost:5191"
}

if [ "$#" -gt 0 ]; then
  echo "Unknown argument: $1" >&2
  echo "Usage: ./scripts/agent-init.sh (set AGENT_APP_URL to check a non-default route)" >&2
  exit 1
fi

app_url="${AGENT_APP_URL:-$(get_default_app_url)}"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

echo "Repo root: $repo_root"
echo "App URL: $app_url"

if ! curl --max-time 10 -fsSk "$app_url" >/dev/null; then
  echo "No reachable task server. Start yarn start in an owned terminal, record its process/session, then rerun with AGENT_APP_URL set to its URL." >&2
  exit 1
fi

echo "Dev server is ready."
