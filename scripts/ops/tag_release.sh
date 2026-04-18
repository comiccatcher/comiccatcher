#!/bin/bash

# Simple utility to tag a release based on the version in __init__.py

set -e

# 1. Identify paths
REPO_ROOT=$(git rev-parse --show-toplevel)
VERSION_FILE="$REPO_ROOT/src/comiccatcher/__init__.py"

if [ ! -f "$VERSION_FILE" ]; then
    echo "Error: Could not find version file at $VERSION_FILE"
    exit 1
fi

# 2. Extract version
VERSION=$(grep "__version__ =" "$VERSION_FILE" | cut -d '"' -f 2)

if [ -z "$VERSION" ]; then
    echo "Error: Could not extract version string from $VERSION_FILE"
    exit 1
fi

TAG="v$VERSION"

# 3. Check branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "Error: Tagging is only allowed on the 'main' branch (Current: $CURRENT_BRANCH)"
    exit 1
fi

# 4. Check if tag exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Error: Tag $TAG already exists locally."
    exit 1
fi

if git ls-remote --tags origin | grep -q "refs/tags/$TAG"; then
    echo "Error: Tag $TAG already exists on remote 'origin'."
    exit 1
fi

# 5. Confirmation
echo "Found version: $VERSION"
echo "Target tag:    $TAG"
echo "Branch:        $CURRENT_BRANCH"
echo ""
read -p "Create and push tag $TAG to origin? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Operation cancelled."
    exit 0
fi

# 6. Execute
echo "Tagging $TAG..."
git tag -a "$TAG" -m "Release $VERSION"

echo "Pushing $TAG to origin..."
git push origin "$TAG"

echo "Done! Version $VERSION has been tagged and pushed."
