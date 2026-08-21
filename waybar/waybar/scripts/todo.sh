#!/usr/bin/env bash
set -eu
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/waybar"
tasks_file="$state_dir/tasks.json"
legacy_file="$state_dir/todo.txt"

if [[ -f "$tasks_file" ]]; then
    jq 'length' "$tasks_file" 2>/dev/null || echo 0
elif [[ -f "$legacy_file" ]]; then
    awk 'NF { count++ } END { print count + 0 }' "$legacy_file"
else
    echo 0
fi
