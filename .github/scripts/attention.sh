#!/usr/bin/env bash
# Open, update or close the GitHub issue "Internship finder needs attention".
#
#   attention.sh open    <source> <body-file>   # add a comment (or open the issue) and tag it with the source
#   attention.sh resolve <source>               # drop the source's label; close the issue when no source is left
#
# <source> is "daily" (the daily run) or "verify" (the monthly feed check), so a healthy daily run
# does not close a problem the monthly check reported. GitHub emails the repo owner about new issues
# and comments, so no email secrets are needed. Needs GH_TOKEN (the workflow's github.token).
set -euo pipefail

TITLE="Internship finder needs attention"
ACTION="$1"; SOURCE="$2"; BODY="${3:-}"
LABEL="attention: $SOURCE"

gh label create "$LABEL" --color d93f0b --description "Set by the $SOURCE workflow" --force >/dev/null 2>&1 || true
NUM="$(gh issue list --state open --limit 100 --json number,title \
        --jq "map(select(.title == \"$TITLE\")) | .[0].number // empty")"

case "$ACTION" in
  open)
    if [ -n "$NUM" ]; then
      gh issue comment "$NUM" --body-file "$BODY" >/dev/null
      gh issue edit "$NUM" --add-label "$LABEL" >/dev/null
      echo "Updated issue #$NUM"
    else
      gh issue create --title "$TITLE" --body-file "$BODY" --label "$LABEL"
    fi
    ;;
  resolve)
    [ -z "$NUM" ] && { echo "No open attention issue."; exit 0; }
    LABELS="$(gh issue view "$NUM" --json labels --jq '[.labels[].name] | join(",")')"
    if [[ ",$LABELS," == *",$LABEL,"* ]]; then
      gh issue edit "$NUM" --remove-label "$LABEL" >/dev/null
    fi
    OTHERS="$(gh issue view "$NUM" --json labels --jq '[.labels[].name | select(startswith("attention: "))] | length')"
    if [ "$OTHERS" = "0" ]; then
      gh issue close "$NUM" --comment "Resolved: the latest $SOURCE run was healthy ($(date -u +%Y-%m-%d))." >/dev/null
      echo "Closed issue #$NUM"
    else
      echo "Issue #$NUM stays open: another check still reports a problem."
    fi
    ;;
  *) echo "usage: $0 open|resolve <source> [body-file]" >&2; exit 2 ;;
esac
