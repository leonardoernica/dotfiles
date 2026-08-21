#!/usr/bin/env python3
import json, os
from datetime import date
from pathlib import Path

state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "waybar"
tasks_file = state / "tasks.json"
try:
    tasks = json.loads(tasks_file.read_text()) if tasks_file.exists() else []
except (json.JSONDecodeError, OSError):
    tasks = []

today = date.today().isoformat()
opened = [task for task in tasks if task.get("status", "open") == "open"]
overdue = sum(bool(task.get("due_date") and task["due_date"] < today) for task in opened)
due_today = sum(task.get("due_date") == today for task in opened)
css_class = "overdue" if overdue else "due-today" if due_today else "all-clear"
tooltip = f"{len(opened)} aberta(s)"
if overdue:
    tooltip += f" · {overdue} atrasada(s)"
elif due_today:
    tooltip += f" · {due_today} para hoje"
print(json.dumps({"text": str(len(opened)), "class": css_class, "tooltip": tooltip}, ensure_ascii=False))
