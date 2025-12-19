# 连接远程 Git 仓库指南

## 📋 快速步骤

### 情况 1: 本地已有代码，需要连接到远程仓库

```bash
# 1. 初始化 git 仓库（如果还没有）
git init

# 2. 添加远程仓库
git remote add origin <你的远程仓库URL>

# 3. 添加所有文件
git add .

# 4. 创建初始提交
git commit -m "Initial commit: Add TradingAgents with seeking_alpha_analyst"

# 5. 推送到远程（如果是新仓库）
git branch -M main  # 将分支重命名为 main（如果远程使用 main）
git push -u origin main

# 或者如果远程使用 master
git push -u origin master
```

### 情况 2: 远程仓库已有代码，需要克隆并连接

```bash
# 1. 克隆远程仓库
git clone <你的远程仓库URL>

# 2. 进入目录
cd <仓库名>

# 3. 查看远程仓库
git remote -v
```

---

## 🔗 远程仓库 URL 格式

### HTTPS 方式（推荐新手）
```bash
git remote add origin https://github.com/username/repo-name.git
```

### SSH 方式（需要配置 SSH key）
```bash
git remote add origin git@github.com:username/repo-name.git
```

---

## 📝 完整示例

假设你的远程仓库是 `https://github.com/yourusername/TradingAgents.git`：

```bash
# 1. 初始化
git init

# 2. 添加远程
git remote add origin https://github.com/yourusername/TradingAgents.git

# 3. 检查远程配置
git remote -v
# 应该显示:
# origin  https://github.com/yourusername/TradingAgents.git (fetch)
# origin  https://github.com/yourusername/TradingAgents.git (push)

# 4. 添加文件
git add .

# 5. 提交
git commit -m "Initial commit: TradingAgents with seeking_alpha_analyst"

# 6. 推送到远程
git branch -M main
git push -u origin main
```

---

## 🔧 常用命令

### 查看远程仓库
```bash
git remote -v
```

### 修改远程仓库 URL
```bash
git remote set-url origin <新的URL>
```

### 删除远程仓库
```bash
git remote remove origin
```

### 重命名远程仓库
```bash
git remote rename origin upstream
```

### 拉取远程更新
```bash
git pull origin main
```

### 推送本地更新
```bash
git push origin main
```

---

## ⚠️ 常见问题

### 问题 1: 远程仓库已存在内容
如果远程仓库已经有代码，需要先拉取：

```bash
# 拉取远程代码
git pull origin main --allow-unrelated-histories

# 解决可能的冲突后
git add .
git commit -m "Merge remote and local"
git push origin main
```

### 问题 2: 认证失败
如果使用 HTTPS，可能需要配置 token：

1. GitHub: Settings → Developer settings → Personal access tokens
2. 生成 token 后，使用 token 作为密码

或者配置 SSH key（推荐）：
```bash
# 生成 SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# 添加到 ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 复制公钥到 GitHub/GitLab
cat ~/.ssh/id_ed25519.pub
```

### 问题 3: 分支名称不匹配
```bash
# 查看当前分支
git branch

# 重命名分支
git branch -M main  # 重命名为 main
# 或
git branch -M master  # 重命名为 master
```

---

## 🚀 使用提供的脚本

我已经创建了 `connect_remote_git.sh` 脚本，你可以这样使用：

```bash
# 使用脚本（需要提供远程 URL）
./connect_remote_git.sh https://github.com/username/repo.git

# 或者指定远程名称
./connect_remote_git.sh https://github.com/username/repo.git origin
```

---

## 📌 下一步

连接成功后，你可以：

1. **继续开发**: 正常使用 `git add`, `git commit`, `git push`
2. **创建分支**: `git checkout -b feature/new-feature`
3. **协作**: 其他人可以 `git clone` 你的仓库

---

## 💡 提示

- 首次推送使用 `-u` 参数设置上游分支: `git push -u origin main`
- 之后可以直接使用 `git push` 和 `git pull`
- 建议定期提交和推送，避免丢失代码

