#!/usr/bin/env bash
set -eu
todo_file="${XDG_STATE_HOME:-$HOME/.local/state}/waybar/todo.txt"
[[ -f "$todo_file" ]] || { echo 0; exit 0; }
awk 'NF { count++ } END { print count + 0 }' "$todo_file"
