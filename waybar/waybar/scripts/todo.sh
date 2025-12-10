#!/bin/bash

TODO_FILE="$HOME/.todo_list"

if [ ! -f "$TODO_FILE" ]; then
    touch "$TODO_FILE"
fi

# Função para verificar comandos
has_cmd() {
    command -v "$1" &> /dev/null
}

# Função para abrir terminal com editor
open_terminal_editor() {
    EDITOR=${EDITOR:-nano}
    if has_cmd kitty; then
        kitty --title "To-Do List" -e $EDITOR "$TODO_FILE"
    elif has_cmd alacritty; then
        alacritty -T "To-Do List" -e $EDITOR "$TODO_FILE"
    elif has_cmd foot; then
        foot -T "To-Do List" $EDITOR "$TODO_FILE"
    else
        # Fallback genérico
        xdg-open "$TODO_FILE"
    fi
}

case "$1" in
    "count")
        count=$(wc -l < "$TODO_FILE")
        echo "$count"
        ;;
    "menu")
        # Tenta usar Walker, se não existir, usa Wofi/Rofi, se não, abre editor
        if has_cmd walker; then
            options=" Add Task\n$(cat "$TODO_FILE")"
            selected=$(echo -e "$options" | walker -d -p "To-Do")

            if [ "$selected" == " Add Task" ]; then
                # Adicionar tarefa via terminal (mais seguro)
                if has_cmd kitty; then
                    kitty --title "Add Task" sh -c "read -p 'Task: ' task; echo \"\$task\" >> \"$TODO_FILE\""
                else
                    open_terminal_editor
                fi
            elif [ -n "$selected" ]; then
                # Deletar tarefa
                action=$(echo -e "No\nYes" | walker -d -p "Delete '$selected'?")
                if [ "$action" == "Yes" ]; then
                    grep -vF "$selected" "$TODO_FILE" > "$TODO_FILE.tmp" && mv "$TODO_FILE.tmp" "$TODO_FILE"
                fi
            fi
        elif has_cmd wofi; then
            # Fallback para Wofi
            options=" Add Task\n$(cat "$TODO_FILE")"
            selected=$(echo -e "$options" | wofi --dmenu --prompt "To-Do")
             if [ "$selected" == " Add Task" ]; then
                open_terminal_editor
            elif [ -n "$selected" ]; then
                 grep -vF "$selected" "$TODO_FILE" > "$TODO_FILE.tmp" && mv "$TODO_FILE.tmp" "$TODO_FILE"
            fi
        else
            # Fallback final: abre o arquivo direto
            open_terminal_editor
        fi
        ;;
    "add")
        if has_cmd kitty; then
            kitty --title "Add Task" sh -c "read -p 'Task: ' task; echo \"\$task\" >> \"$TODO_FILE\""
        else
            open_terminal_editor
        fi
        ;;
    *)
        echo "Usage: $0 {count|menu|add}"
        exit 1
        ;;
esac
