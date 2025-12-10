# Mostrar Fastfetch no início
fastfetch

# ========== HISTÓRICO ZSH ==========
HISTFILE=~/.zsh_history
HISTSIZE=50000
SAVEHIST=50000

# Não sobrescrever o histórico
setopt APPEND_HISTORY
setopt INC_APPEND_HISTORY
setopt SHARE_HISTORY

# Melhorias no histórico
setopt HIST_IGNORE_DUPS
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_IGNORE_SPACE
setopt HIST_REDUCE_BLANKS
setopt HIST_FIND_NO_DUPS
# ====================================

# --- ZINIT CORE E PLUGINS ---
# Instalar o Zinit (se ele não estiver instalado, ele se instala sozinho)
if [ ! -d "${ZINIT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/zinit}/zinit.git" ]; then
    print -P "%F{33}Installing Zinit...%f"
    git clone https://github.com/zdharma-continuum/zinit.git "${ZINIT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/zinit}/zinit.git"
fi

# Carrega o core do Zinit
source "${ZINIT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/zinit}/zinit.git/zinit.zsh"

# Configurações do Zinit (Carrega os plugins essenciais de forma rápida)
zinit light-mode for \
    zsh-users/zsh-autosuggestions \
    zsh-users/zsh-syntax-highlighting

# --- FIM ZINIT ---


# --- CONFIGURAÇÃO STARSHIP (DEVE VIR NO FINAL) ---

# Ativar Starship prompt (o prompt de alta performance)
eval "$(starship init zsh)"


# --- OUTRAS CONFIGURAÇÕES GERAIS (Mantenha se necessário) ---

# Adicione seu Path do Flutter (Se ainda for necessário)
export PATH="$PATH:$HOME/development/flutter/bin"
