# Dotfiles — Arch Linux + Hyprland

Configurações pessoais para Hyprland, Waybar, Kitty, Zsh, Starship, GTK,
Wlogout e SDDM. O Hyprland usa Lua como formato principal; o arquivo `.conf`
é mantido apenas como fallback para versões anteriores.

## Componentes

- `hypr/hypr/hyprland.lua`: configuração principal do Hyprland 0.55+
- `hypr/hypr/hyprland.conf`: fallback legado
- `hypr/hypr/hyprpaper.conf`: wallpaper
- `waybar/waybar`: barra, central de Wi-Fi e gerenciador de tarefas
- `wlogout/wlogout`: menu de sessão e bloqueio
- `kitty/kitty`: terminal Kitty
- `garimpo`: busca semântica local no SUPER+D (apps, arquivos, imagens, vídeos e código)
- `rofi/.config/rofi`: command palette translúcida com busca fuzzy (fallback)
- `applications/.local/share/applications`: ajustes locais do menu de aplicativos
- `zsh/.zshrc` e `starship/.config/starship`: shell e prompt
- `gtk-3.0` e `gtk-4.0`: aparência GTK
- `sddm`: configuração e temas do gerenciador de login

## Dependências

Pacotes centrais:

```bash
sudo pacman -S --needed \
  hyprland hyprpaper waybar xdg-desktop-portal xdg-desktop-portal-hyprland \
  xdg-desktop-portal-gtk networkmanager network-manager-applet \
  gtk4 libadwaita python-gobject kitty zsh starship stow \
  rofi-wayland wofi pavucontrol blueman brightnessctl \
  grim slurp wl-clipboard dolphin chromium polkit-kde-agent
```

A central de Wi-Fi usa `nmcli` e libnm, fornecidos por `networkmanager`,
cria perfis pessoais sem pedir administrador e inicia `nm-applet` para solicitar
segredos de conexão. Veja [diagnóstico e correção do Realtek](network/README.md).
Wi-Fi e tarefas
usam GTK 4, libadwaita e PyGObject. Instale `wlogout` pelo AUR.

## Instalação

```bash
git clone https://github.com/leonardoernica/dotfiles.git ~/projects/dotfiles
cd ~/projects/dotfiles
./install.sh
```

O instalador:

- cria links em `~/.config` para Waybar, Wlogout, Kitty, Rofi e GTK;
- instala Zsh e Starship com GNU Stow;
- oculta do menu o atalho Flatpak do Chromium, mantendo o Chromium nativo;
- ativa `~/.config/hypr/hyprland.lua`;
- mantém `hyprland.conf` disponível como fallback;
- remove links quebrados de scripts antigos da Waybar;
- oferece opcionalmente a instalação do quirk do touchpad e do SDDM.

Depois da instalação, encerre e abra novamente a sessão do Hyprland. Isso
garante que o compositor inicie diretamente com `hyprland.lua` e que o ambiente
exportado para D-Bus esteja completo.

## Portais Wayland

`xdg-desktop-portal` e `xdg-desktop-portal-hyprland` não são iniciados
manualmente. Eles são ativados pelo D-Bus quando necessários. A configuração do
Hyprland apenas exporta o ambiente da sessão com
`dbus-update-activation-environment --systemd --all`.

Para diagnosticar compartilhamento de tela ou seletores de arquivos:

```bash
systemctl --user status xdg-desktop-portal xdg-desktop-portal-hyprland
journalctl --user -b -u xdg-desktop-portal -u xdg-desktop-portal-hyprland
```

## Garimpo (SUPER+D)

Busca local inspirada no [DigUp](https://github.com/ARahim3/DigUp): descreva o que
procura e o Garimpo encontra pelo conteúdo — a página certa do PDF, a foto pelo que
ela mostra, a captura de tela pelo texto, o momento do vídeo. Também abre
aplicativos, faz contas e, com `code:`, busca código. Nada sai da máquina.

Como funciona:

- **Modelo:** [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2), o
  mesmo do DigUp, na build 8-bit do ggml-org (310 MB de texto + 555 MB de encoders de
  imagem e áudio). Texto, imagens e som ficam no mesmo espaço vetorial, em 100+ idiomas:
  buscar em português encontra documentos em inglês e fotos pelo que mostram;
- **Execução:** `llama-server` do llama.cpp em `127.0.0.1:8765`
  (`garimpo-embed.service`), só na CPU; a GPU integrada não foi mais rápida. O Ollama
  não serve aqui: todas as tags `embeddinggemma-2` dele exigem o runtime MLX da Apple;
- **Leitores:** `pdftotext` página a página (OCR com `tesseract` em páginas
  escaneadas), docx/odt/pptx/xlsx/epub, OCR de capturas, frames de vídeo e janelas de
  30 s de áudio (músicas, gravações e trilhas de vídeo) com `ffmpeg`;
- **Ranking:** cada sinal vira "quanto este trecho se destaca do resto *nesta busca*"
  (z-score por tipo: texto, imagens, som), em vez de um corte fixo de similaridade.
  Trechos que ficam perto de qualquer busca (livros longos, frames de vídeo, áudios
  curtos) são descontados pela proximidade média a sondas genéricas (correção de
  *hubness*, CSLS). Palavras exatas e nome do arquivo desempatam, por palavra
  inteira; prefixo só se a palavra ainda não existir inteira ("mochi" → mochila, mas
  "bota" não acha "Botão"). Cópias idênticas viram uma linha ("+2 cópias");
- **Mídia por confiança:** imagens, frames e áudio entram em "Imagens, vídeos e áudio"
  quando se destacam das demais mídias, na posição que a confiança indica (no máximo
  depois dos 3 primeiros documentos). Um vídeo com 40 frames tem 40 chances de parecer
  relevante por acaso e recebe um desconto por isso. Para imagens a busca é feita como
  legenda ("uma foto de mochila");
- **Aplicativos pelo significado:** nome, descrição e categorias de cada app passam pelo
  mesmo modelo, então "xadrez" acha o En Croissant e o Chess Overlay e "planilha" acha o
  LibreOffice Calc. Os vetores dos apps ficam no índice; um app novo é lido uma vez;
- **Erros de digitação:** uma palavra que nenhum arquivo ou app contém é buscada como foi
  digitada *e* como as grafias conhecidas mais próximas (1 letra trocada, faltando, sobrando
  ou invertida; 2 a partir de 8 letras): "croassant" acha o En Croissant, "contarto" acha
  contratos. Empates ficam todos ("pultão": Plutão e pulmão) e o ranking decide; manter a
  palavra digitada protege fotos ("gato" continua achando o gato, mesmo que vire "gado").
  `garimpo eval` também mede cada busca com um erro gerado automaticamente;
- **Pedir o tipo:** "foto…", "print…", "vídeo…", "música…" põem esse tipo primeiro;
- **Índice limpo:** JSON, logs, código colado em `.txt` e OCR de baixa confiança
  (palavras do tesseract abaixo de 60%) continuam achados por palavra exata, mas não
  recebem vetor — antes apareciam em qualquer busca;
- **Medido:** `garimpo eval -v` mostra onde o arquivo esperado caiu em buscas conhecidas:
  as de `~/.local/state/garimpo/eval.json` e, automaticamente, cada busca feita na paleta
  junto com o arquivo aberto (`searches.jsonl`, só local). Nas 43 buscas desta máquina o
  certo veio em 1º em 40 de 46 e entre os 5 primeiros em 45 (o ranking antigo: 1 de 30);
- **Índice:** um único SQLite em `~/.local/state/garimpo/index.db` com vetores
  float16 e FTS5 para palavras exatas (números de nota, códigos de erro, nomes);
- **Privacidade:** somente leitura e sem rede além do download inicial; ignora pastas
  ocultas, `~/.ssh`, `secrets/`, chaves, `.env`, senhas, `node_modules`, caches e
  pastas tipo dataset. Dentro de projetos de código só entram imagens, PDFs e documentos;
- **Tempo real:** inotify em todas as pastas indexadas; um arquivo baixado, criado,
  movido ou apagado reflete na busca em poucos segundos, com prioridade sobre a
  indexação em andamento. A cada 10 min uma varredura de segurança confere tudo;
- **Velocidade:** a janela fica residente e o SUPER+D só a acorda por D-Bus.

| Tecla | Ação |
|---|---|
| SUPER+D | abrir/fechar |
| ↑ ↓, Ctrl+J/K | navegar |
| Enter, duplo clique | abrir (PDF na página, vídeo no segundo, código na linha) |
| clique | selecionar e abrir a prévia |
| Ctrl+Enter | mostrar na pasta (Dolphin) |
| Ctrl+C | copiar o arquivo (ou o resultado da conta) |
| Tab | prévia: imagem, página do PDF ou frame do vídeo |
| Esc | limpar / fechar |

Instalação (sem root): `garimpo setup` baixa o llama.cpp `b11574` e o modelo, confere
o SHA-256 fixado em `config.py` e instala em `~/.local/opt/llama-cpp` e
`~/.cache/garimpo/models` (~950 MB). O OCR em português precisa de um pacote do sistema:

```bash
garimpo setup && garimpo doctor
sudo pacman -S --needed tesseract-data-por
```

O `install.sh` roda o setup e ativa `garimpo-embed.service` e `garimpo-indexer.service`
(com `nice` e I/O ociosa). Comandos:

```bash
garimpo search "contrato de aluguel com animais"   # busca no terminal
garimpo open "code: retry com backoff"             # abre a paleta já pesquisando
garimpo status                                     # progresso do índice
garimpo eval -v                                    # qualidade do ranking nas suas buscas
garimpo pause | garimpo resume
journalctl --user -u garimpo-indexer -u garimpo-embed -f
```

Configuração em `garimpo/.config/garimpo/config.toml` (pastas, busca de código,
modelo, OCR, vídeo). Testes: `python -m unittest tests.test_garimpo`.

## Waybar

- clique no módulo de rede para abrir a central nativa de Wi-Fi;
- clique em tarefas para abrir o gerenciador;
- clique com o botão direito na rede para abrir as configurações avançadas;
- a tarefa da Waybar fica verde sem pendências, amarela com prazo hoje e
  vermelha quando existe tarefa atrasada.

As tarefas ficam em `~/.local/state/waybar/tasks.json`. Esse arquivo contém
dados pessoais e propositalmente não é versionado.

Para recarregar a barra:

```bash
~/.config/waybar/launch.sh
```

## Wallpapers e portabilidade

O wallpaper padrão está versionado em `wallpapers/walpapper_tuyuu.png`. O
`hyprpaper.conf` atualmente espera o mesmo arquivo em
`~/Imagens/Wallpapers/walpapper_tuyuu.png`. Copie-o ou ajuste o caminho ao usar
estas configurações em outra conta.

## Atualização

```bash
cd ~/projects/dotfiles
git pull --ff-only
./install.sh
```

## Validação

```bash
Hyprland --verify-config -c hypr/hypr/hyprland.lua
python -m json.tool waybar/waybar/config.jsonc >/dev/null
python -m unittest tests.test_garimpo
zsh -n zsh/.zshrc
```

## Desinstalação

Remova apenas os links criados pelo projeto; os arquivos do repositório não são
apagados:

```bash
stow -D -t ~/.config kitty waybar wlogout gtk-3.0 gtk-4.0
stow -D -t ~ starship zsh garimpo
systemctl --user disable --now garimpo-indexer.service garimpo-embed.service
rm -rf ~/.local/opt/llama-cpp ~/.cache/garimpo ~/.local/state/garimpo
rm ~/.config/hypr/hyprland.lua ~/.config/hypr/hyprland.conf \
   ~/.config/hypr/hyprpaper.conf
```

SDDM e o quirk de libinput são instalados no sistema e devem ser removidos
separadamente com privilégios administrativos.
