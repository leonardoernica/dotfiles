# Dotfiles

Este repositório contém todas as configurações do meu ambiente Hyprland, organizadas para uso com GNU Stow.

## Estrutura

- `hypr/` - Configurações do Hyprland (hyprland.conf, hyprpaper.conf, autostart.conf)
  - `hypr/hypr/` - Configurações principais (hyprland.conf, hyprpaper.conf)
  - `hypr/.config/hyprland/` - Autostart (autostart.conf)
- `kitty/` - Configurações do terminal Kitty
- `waybar/` - Configurações da barra Waybar
- `wlogout/` - Configurações do menu de logout
- `starship/` - Configurações do prompt Starship
- `zsh/` - Configurações do Zsh (.zshrc)
- `gtk-3.0/` - Configurações do GTK 3.0
- `gtk-4.0/` - Configurações do GTK 4.0
- `wallpapers/` - Papéis de parede
- `fastfetch/` - Configurações do Fastfetch (se houver)
- `wofi/` - Configurações do launcher Wofi (usado mas sem config customizado por enquanto)
- `sddm/` - Configurações do gerenciador de login SDDM (temas, configurações, scripts)

## Pré-requisitos

- **GNU Stow** - Para gerenciar os symlinks dos dotfiles
  ```bash
  # Arch Linux
  sudo pacman -S stow
  ```

## Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/leonardoernica/dotfiles.git ~/projects/dotfiles
cd ~/projects/dotfiles
```

### 2. Instalar usando Stow

O Stow criará symlinks automáticos dos arquivos de configuração para os locais corretos no sistema.

```bash
# Instalar todas as configurações
stow -t ~ hypr kitty waybar wlogout starship zsh gtk-3.0 gtk-4.0

# Para SDDM, precisa ser instalado com sudo (arquivos em /etc e /usr/share)
# IMPORTANTE: Após instalar com stow, execute fix-sddm-theme.sh para copiar o tema
# (SDDM não consegue acessar arquivos via symlink no diretório home)
sudo stow --adopt -t / sddm
./fix-sddm-theme.sh

# Ou instalar uma por uma
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

- `hypr/hypr/hyprpaper.conf` - Ajuste os caminhos dos wallpapers para o seu sistema:
  ```bash
  # Edite o arquivo e altere:
  # /home/lzin/Imagens/Wallpapers/ → /home/SEU_USUARIO/Imagens/Wallpapers/
  ```
- Ou copie os wallpapers para o local esperado:
  ```bash
  mkdir -p ~/Imagens/Wallpapers
  cp wallpapers/* ~/Imagens/Wallpapers/
  ```

## Desinstalação

Para remover os symlinks (sem deletar os arquivos originais):

```bash
stow -D -t ~ hypr kitty waybar wlogout starship zsh gtk-3.0 gtk-4.0
sudo stow -D -t / sddm
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
├── hypr/
│   └── hypr/
│       ├── hyprland.conf
│       ├── hyprpaper.conf
│       └── autostart.conf
├── kitty/
│   └── kitty/
│       └── kitty.conf
└── ...

# Após `stow -t ~ hypr`, será criado:
# ~/.config/hypr/hyprland.conf -> dotfiles/hypr/hypr/hyprland.conf
# ~/.config/hypr/hyprpaper.conf -> dotfiles/hypr/hypr/hyprpaper.conf
# ~/.config/hyprland/autostart.conf -> dotfiles/hypr/hypr/autostart.conf
```

## Wallpapers

Os wallpapers estão em `wallpapers/`. Você pode copiá-los para o local desejado:

```bash
cp -r wallpapers/* ~/Imagens/Wallpapers/
# Ou ajuste o caminho em hypr/hypr/hyprpaper.conf
```

## Scripts Auxiliares

- `install.sh` - Instala todos os dotfiles automaticamente usando stow
- `fix-sddm-theme.sh` - Corrige o problema de acesso do tema SDDM (necessário após stow, pois SDDM não consegue acessar arquivos via symlink no diretório home)
- `setup-remote.sh` - Configura o remote do git e faz push inicial

## Backup

Este repositório serve como backup completo das configurações. Ao trocar de computador:

1. Clone o repositório
2. Instale o Stow
3. Execute `./install.sh` para instalar tudo automaticamente
4. Execute `./fix-sddm-theme.sh` para corrigir o tema SDDM
5. Ajuste caminhos específicos se necessário (ex: wallpapers em hyprpaper.conf)

Pronto! Todas as configurações estarão restauradas.
