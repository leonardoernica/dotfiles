# Dotfiles

Este repositório contém todas as configurações do meu ambiente Hyprland, organizadas para uso com GNU Stow.

## Estrutura

- `hyprland/` - Configurações do Hyprland (autostart.conf)
- `hypr/` - Configurações principais do Hyprland (hyprland.conf, hyprpaper.conf)
- `kitty/` - Configurações do terminal Kitty
- `waybar/` - Configurações da barra Waybar
- `wlogout/` - Configurações do menu de logout
- `starship/` - Configurações do prompt Starship
- `zsh/` - Configurações do Zsh (.zshrc)
- `gtk-3.0/` - Configurações do GTK 3.0
- `gtk-4.0/` - Configurações do GTK 4.0
- `wallpapers/` - Papéis de parede
- `fastfetch/` - Configurações do Fastfetch (se houver)
- `wofi/` - Configurações do launcher Wofi (se houver)
- `sddm/` - Configurações do gerenciador de login SDDM (se houver)

## Pré-requisitos

- **GNU Stow** - Para gerenciar os symlinks dos dotfiles
  ```bash
  # Arch Linux
  sudo pacman -S stow
  ```

## Instalação

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio> ~/projects/dotfiles
cd ~/projects/dotfiles
```

### 2. Instalar usando Stow

O Stow criará symlinks automáticos dos arquivos de configuração para os locais corretos no sistema.

```bash
# Instalar todas as configurações
stow -t ~ hyprland hypr kitty waybar wlogout starship zsh gtk-3.0 gtk-4.0

# Ou instalar uma por uma
stow -t ~ hyprland
stow -t ~ hypr
stow -t ~ kitty
stow -t ~ waybar
stow -t ~ wlogout
stow -t ~ starship
stow -t ~ zsh
stow -t ~ gtk-3.0
stow -t ~ gtk-4.0
```

**Nota:** Para configurações que vão em `~/.config/`, o stow criará os symlinks automaticamente baseado na estrutura de diretórios dentro de cada pacote.

### 3. Verificar instalação

Após instalar, verifique se os symlinks foram criados corretamente:

```bash
ls -la ~/.config/hyprland
ls -la ~/.config/kitty
ls -la ~/.config/waybar
ls -la ~/.zshrc
```

### 4. Ajustar caminhos (se necessário)

Alguns arquivos podem conter caminhos absolutos que precisam ser ajustados:

- `hypr/hypr/hyprpaper.conf` - Verifique os caminhos dos wallpapers
- Outros arquivos que referenciem caminhos específicos do sistema

## Desinstalação

Para remover os symlinks (sem deletar os arquivos originais):

```bash
stow -D -t ~ hyprland hypr kitty waybar wlogout starship zsh gtk-3.0 gtk-4.0
```

## Atualização

Para atualizar as configurações:

```bash
cd ~/projects/dotfiles
git pull
# Os symlinks já apontam para os arquivos atualizados automaticamente
```

## Estrutura do Stow

A estrutura está organizada para que o Stow crie os symlinks corretamente:

```
dotfiles/
├── hyprland/
│   └── hyprland/
│       └── autostart.conf
├── kitty/
│   └── kitty/
│       └── kitty.conf
└── ...

# Após `stow -t ~ hyprland`, será criado:
# ~/.config/hyprland/autostart.conf -> dotfiles/hyprland/hyprland/autostart.conf
```

## Wallpapers

Os wallpapers estão em `wallpapers/`. Você pode copiá-los para o local desejado:

```bash
cp -r wallpapers/* ~/Imagens/Wallpapers/
# Ou ajuste o caminho em hypr/hypr/hyprpaper.conf
```

## Backup

Este repositório serve como backup completo das configurações. Ao trocar de computador:

1. Clone o repositório
2. Instale o Stow
3. Execute os comandos de instalação acima
4. Ajuste caminhos específicos se necessário

Pronto! Todas as configurações estarão restauradas.
