#!/usr/bin/env bash
# git-sync.sh
set -e

# Make sure git user is configured locally if not done globally
git config user.name "project-manager"
git config user.email "claw-bot-pm@nobresutton.com"

# Check if there are changes to commit
if [ -n "$(git status --porcelain)" ]; then
    echo "Staging and committing changes..."
    git add -A
    git commit -m "${1:-Agent auto-commit}"
else
    echo "No local changes to commit."
fi

# Pull latest updates (rebase to keep history clean)
echo "Pulling latest updates..."
git pull --rebase

# Push changes
echo "Pushing to remote..."
git push