#!/usr/bin/env bash
# Publish this run's generated outputs on top of the *current* branch tip.
#
# Generated files are never merged line by line (merging JSON that way can conflict or
# even produce invalid JSON). Instead: keep this run's data files, move to the latest
# branch tip, rebuild the viewer there (latest template + data/user_state.json),
# commit, push. If the branch moves again before the push, start over (3 attempts).
set -euo pipefail

BRANCH="${1:-main}"
FILES=(data/jobs.json data/last_run.json data/new_today.md data/review.md)
SAVED="$(mktemp -d)"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for f in "${FILES[@]}"; do cp "$f" "$SAVED/$(basename "$f")"; done
if [ -d data/cache ]; then cp -r data/cache "$SAVED/cache"; fi   # JSON-LD page cache (keeps daily requests low)
if [ -d data/descriptions ]; then cp -r data/descriptions "$SAVED/descriptions"; fi   # job description archive

for attempt in 1 2 3; do
  git fetch --quiet origin "$BRANCH"
  git checkout --quiet --force -B "$BRANCH" "origin/$BRANCH"
  for f in "${FILES[@]}"; do cp "$SAVED/$(basename "$f")" "$f"; done
  if [ -d "$SAVED/cache" ]; then rm -rf data/cache && cp -r "$SAVED/cache" data/cache; fi
  if [ -d "$SAVED/descriptions" ]; then rm -rf data/descriptions && cp -r "$SAVED/descriptions" data/descriptions; fi
  python -m finder build
  git add "${FILES[@]}" docs/index.html
  if [ -d data/cache ]; then git add data/cache; fi
  if [ -d data/descriptions ]; then git add data/descriptions; fi
  if git diff --cached --quiet; then
    echo "No changes to commit."
    exit 0
  fi
  git commit --quiet -m "Daily update $(date -u +%Y-%m-%d)"
  if git push --quiet origin "HEAD:$BRANCH"; then
    echo "Pushed on attempt $attempt."
    exit 0
  fi
  echo "Push rejected because $BRANCH moved; retrying on the new tip..."
  sleep $((attempt * 5))
done
echo "Could not push after 3 attempts." >&2
exit 1
