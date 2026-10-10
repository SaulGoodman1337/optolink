#!/usr/bin/env bash
# One LXC invocation for the reviewed optolink-p300-migration research batch.
# Defaults to a NO-HARDWARE plan. 'collect' never switches protocols.
set -euo pipefail
umask 077
PROJECT=/root/p300-trial-work/project
cd "$PROJECT"
if [[ "$(pwd -P)" != "$PROJECT" ]]; then
  echo "REFUSED: unexpected checkout path" >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != optolink-p300-migration ]]; then
  echo "REFUSED: only experimental optolink-p300-migration" >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "REFUSED: tracked developer checkout has local modifications" >&2
  git status --short
  exit 1
fi
git fetch --quiet origin optolink-p300-migration
git merge --ff-only FETCH_HEAD
printf 'P300_DEVELOPMENT_HEAD=%s\n' "$(git rev-parse HEAD)"
exec /opt/optolink/venv/bin/python \
  tools/wb2a-research-batch.py "$@"
