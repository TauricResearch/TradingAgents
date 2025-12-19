#!/bin/bash
# 连接远程 Git 仓库的脚本

# 步骤 1: 初始化 git 仓库（如果还没有）
if [ ! -d .git ]; then
    echo "初始化 git 仓库..."
    git init
    echo "✅ Git 仓库已初始化"
fi

# 步骤 2: 添加远程仓库
# 请将 YOUR_REMOTE_URL 替换为你的实际远程仓库 URL
# 例如: https://github.com/username/repo.git 或 git@github.com:username/repo.git

REMOTE_URL="${1:-YOUR_REMOTE_URL}"
REMOTE_NAME="${2:-origin}"

if [ "$REMOTE_URL" = "YOUR_REMOTE_URL" ]; then
    echo "⚠️  请提供远程仓库 URL"
    echo ""
    echo "使用方法:"
    echo "  ./connect_remote_git.sh <remote_url> [remote_name]"
    echo ""
    echo "示例:"
    echo "  ./connect_remote_git.sh https://github.com/username/repo.git"
    echo "  ./connect_remote_git.sh git@github.com:username/repo.git origin"
    echo ""
    echo "或者手动执行:"
    echo "  git remote add origin <your_remote_url>"
    exit 1
fi

# 检查是否已有远程仓库
if git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "远程仓库 '${REMOTE_NAME}' 已存在，更新 URL..."
    git remote set-url ${REMOTE_NAME} ${REMOTE_URL}
else
    echo "添加远程仓库 '${REMOTE_NAME}'..."
    git remote add ${REMOTE_NAME} ${REMOTE_URL}
fi

echo "✅ 远程仓库已添加/更新"
echo ""
echo "当前远程仓库:"
git remote -v

echo ""
echo "下一步操作:"
echo "1. 添加文件: git add ."
echo "2. 提交: git commit -m 'Initial commit'"
echo "3. 推送到远程: git push -u origin main  (或 git push -u origin master)"

