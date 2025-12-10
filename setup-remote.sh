#!/bin/bash
# Script para configurar o remote e fazer push

set -e

echo "🔗 Configuração do repositório remoto"
echo ""
echo "Por favor, forneça a URL do seu repositório remoto:"
echo "  - GitHub: https://github.com/USERNAME/dotfiles.git"
echo "  - GitLab: https://gitlab.com/USERNAME/dotfiles.git"
echo "  - Outro: URL completa do repositório"
echo ""
read -p "URL do repositório: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ URL não fornecida. Saindo..."
    exit 1
fi

echo ""
echo "📌 Adicionando remote 'origin'..."
git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"

echo "✅ Remote configurado!"
echo ""
echo "🚀 Fazendo push para o repositório remoto..."
git push -u origin main

echo ""
echo "✅ Push concluído com sucesso!"

