#!/bin/bash
# Script para aplicar as configurações do SDDM

set -e

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOTFILES_DIR"

echo "🔧 Aplicando configurações do SDDM..."
echo ""

# Verificar se o diretório sddm existe
if [ ! -d "sddm" ]; then
    echo "❌ Diretório sddm não encontrado!"
    exit 1
fi

# Verificar se stow está instalado
if command -v stow &> /dev/null; then
    echo "📌 Instalando SDDM com stow (requer sudo)..."
    echo "   Usando --adopt para mover arquivos existentes para o pacote"
    echo "   Executando: sudo stow --adopt -t / sddm"
    sudo stow --adopt -t / sddm
else
    echo "⚠ GNU Stow não está instalado, copiando arquivos diretamente..."
    echo "   (Para usar stow no futuro, instale com: sudo pacman -S stow)"
    echo ""
    echo "📌 Copiando configurações do SDDM..."
    
    # Fazer backup dos arquivos existentes
    if [ -f "/etc/sddm.conf" ] && [ ! -L "/etc/sddm.conf" ]; then
        echo "   Fazendo backup de /etc/sddm.conf..."
        sudo cp /etc/sddm.conf /etc/sddm.conf.bak
    fi
    
    # Copiar arquivos
    echo "   Copiando /etc/sddm.conf..."
    sudo cp sddm/etc/sddm.conf /etc/sddm.conf
    
    echo "   Copiando temas e arquivos do SDDM..."
    sudo cp -r sddm/usr/share/sddm/* /usr/share/sddm/
    
    echo "   ✓ Arquivos copiados"
fi

echo ""
echo "✅ SDDM instalado!"
echo ""

# Verificar se os arquivos foram instalados
if [ -L "/etc/sddm.conf" ] || [ -f "/etc/sddm.conf" ]; then
    echo "✓ /etc/sddm.conf instalado"
else
    echo "⚠ /etc/sddm.conf não encontrado"
fi

if [ -f "/usr/share/sddm/themes/eucalyptus-drop/Backgrounds/David_-_The_Death_of_Socrates.jpg" ]; then
    echo "✓ Imagem de bloqueio instalada"
else
    echo "⚠ Imagem de bloqueio não encontrada"
fi

echo ""
echo "🔄 Reiniciando SDDM..."
if sudo systemctl restart sddm; then
    echo "✅ SDDM reiniciado com sucesso!"
    echo ""
    echo "📝 Próximo passo:"
    echo "   Reinicie o computador para ver a nova tela de bloqueio:"
    echo "   sudo reboot"
else
    echo "⚠ Não foi possível reiniciar o SDDM automaticamente"
    echo "   Você pode reiniciar manualmente com: sudo systemctl restart sddm"
    echo "   Ou reiniciar o computador: sudo reboot"
fi

echo ""

