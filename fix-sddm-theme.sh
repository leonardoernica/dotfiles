#!/bin/bash
# Script para corrigir o problema do tema SDDM
# O SDDM não consegue acessar arquivos via symlink no diretório home

set -e

echo "🔧 Corrigindo acesso do tema SDDM..."
echo ""

# Remover o symlink atual
if [ -L "/usr/share/sddm/themes/eucalyptus-drop" ]; then
    echo "📌 Removendo symlink antigo..."
    sudo rm /usr/share/sddm/themes/eucalyptus-drop
    echo "   ✓ Symlink removido"
fi

# Copiar o tema para o local correto
echo "📌 Copiando tema eucalyptus-drop..."
sudo cp -r /home/lzin/projects/dotfiles/sddm/usr/share/sddm/themes/eucalyptus-drop /usr/share/sddm/themes/
echo "   ✓ Tema copiado"

# Verificar se Main.qml está acessível
if [ -f "/usr/share/sddm/themes/eucalyptus-drop/Main.qml" ]; then
    echo "   ✓ Main.qml encontrado"
else
    echo "   ✗ Main.qml NÃO encontrado"
    exit 1
fi

# Ajustar permissões
echo "📌 Ajustando permissões..."
sudo chown -R root:root /usr/share/sddm/themes/eucalyptus-drop
sudo chmod -R 755 /usr/share/sddm/themes/eucalyptus-drop
echo "   ✓ Permissões ajustadas"

echo ""
echo "✅ Tema corrigido!"
echo ""
echo "🔄 Reinicie o SDDM:"
echo "   sudo systemctl restart sddm"
echo ""
