#!/bin/bash
set -e

# Project root
BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$BASE_DIR"

# 0. Help
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Usage: $(basename "$0")"
    echo ""
    echo "Promotes the current 'devel' branch to 'main' on origin and locally."
    echo "This script assumes a linear history (Fast-Forward only)."
    echo ""
    echo "Recommended Workflow:"
    echo "  1. git fetch origin"
    echo "  2. git rebase -i origin/main  # Squash your commits here"
    echo "  3. git push -f origin devel   # Update origin/devel with squashed history"
    echo "  4. ./scripts/ops/promote_to_main.sh"
    echo ""
    exit 0
fi

# 1. Verification
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "devel" ]; then
    echo "❌ Error: You must be on the 'devel' branch to run this script."
    exit 1
fi

if ! git diff-index --quiet HEAD --; then
    echo "❌ Error: Your working directory is not clean. Please commit or stash changes."
    exit 1
fi

echo "🔄 Fetching latest state from origin..."
git fetch origin

# 2. Check if devel is ahead of origin/main and is a fast-forward
# rev-list count A..B shows how many commits B has that A doesn't.
BEHIND_COUNT=$(git rev-list --count devel..origin/main)
AHEAD_COUNT=$(git rev-list --count origin/main..devel)

if [ "$BEHIND_COUNT" -gt 0 ]; then
    echo "❌ Error: 'devel' is behind 'origin/main' by $BEHIND_COUNT commits."
    echo "   Please rebase 'devel' onto 'main' before running this script."
    exit 1
fi

if [ "$AHEAD_COUNT" -gt 1 ]; then
    echo "❌ Error: 'devel' is ahead of 'main' by $AHEAD_COUNT commits."
    echo "   This script requires exactly 1 commit to promote for a clean history."
    echo "   Please squash your commits (e.g., git rebase -i origin/main) before running."
    exit 1
fi

if [ "$AHEAD_COUNT" -eq 0 ]; then
    echo "ℹ️  'main' is already up to date with 'devel'."
    exit 0
fi

# Get the commit message of the single commit for the PR body
COMMIT_MSG=$(git log -1 --pretty=%B)

echo "🚀 'devel' is ahead of 'main' by $AHEAD_COUNT commit."
echo "📡 Creating and merging promotion PR (Fast-Forward)..."

# 3. Use GitHub CLI to create and merge a rebase PR
# This satisfies "Require a pull request" branch protection
PR_URL=$(gh pr create --base main --head devel --title "Promote: $COMMIT_MSG" --body "$COMMIT_MSG" --draft=false)
echo "✅ PR Created: $PR_URL"

echo "⚙️ Merging PR with rebase..."
gh pr merge "$PR_URL" --rebase --delete-branch=false

# 4. Sync local main
echo "📥 Updating local 'main' branch to match..."
# This updates the local 'main' branch without needing to checkout
git fetch origin main:main

echo "✅ Success! 'main' is now synced with 'devel' on origin and locally."
echo "📍 Current branch: $CURRENT_BRANCH"
