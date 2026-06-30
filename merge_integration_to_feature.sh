#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:-develop}"   # use $1, default to develop if missing

echo "Get the latest remote branches..."
git fetch origin

echo "Update your feature branch $BRANCH"
git pull origin "$BRANCH"

echo "Bring Develop changes into feature branch $BRANCH"
git merge origin develop

echo "Push feature branch $BRANCH"
git push "$BRANCH"

echo "Run tests"
make gauntlet
