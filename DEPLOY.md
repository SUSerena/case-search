# Render 部署指南

本系统已适配 Render 平台部署，支持 SQLite（自动初始化）和 PostgreSQL 两种数据库模式。

---

## 一、部署前准备

### 1. 注册 Render 账号
- 访问 https://render.com 注册账号（推荐用 GitHub 账号登录）

### 2. 将代码推送到 GitHub
```bash
# 在项目根目录执行
git init
git add .
git commit -m "初始化项目"
git remote add origin https://github.com/你的用户名/case-search-system.git
git push -u origin main
```

> 注意：`data/` 目录中的源文件（Excel、PDF）需要一起推送，它们是初始化样例数据的来源。

---

## 二、部署方式 A：SQLite 模式（最简，推荐先用这个）

SQLite 模式下，每次服务启动会自动创建数据库并导入样例数据。缺点是用户录入的新数据在服务重启后会丢失。

### 步骤：

1. 登录 Render → 点击 **New +** → 选择 **Web Service**
2. 连接 GitHub 仓库，选择 `case-search-system` 仓库
3. 填写配置：
   - **Name**: `case-search-system`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
   - **Instance Type**: `Free`
4. 点击 **Create Web Service**
5. 等待构建完成（首次构建需要安装依赖，约 2-3 分钟）
6. 部署成功后，Render 会分配一个域名：`https://case-search-system.onrender.com`

---

## 三、部署方式 B：PostgreSQL 模式（数据持久化）

如果需要数据持久化（重启不丢失），使用 Render 免费 PostgreSQL。

### 步骤：

1. 先按方式 A 创建 Web Service
2. 在 Render 控制台点击 **New +** → 选择 **PostgreSQL**
   - **Name**: `case-search-db`
   - **Database**: `case_search`
   - **Plan**: `Free`
   - 点击 **Create Database**
3. 创建完成后，在 PostgreSQL 页面找到 **Internal Database URL**，复制
4. 回到 Web Service → **Environment** → 添加环境变量：
   - **Key**: `DATABASE_URL`
   - **Value**: 粘贴上面的 Internal Database URL
5. 保存后服务会自动重新部署
6. 系统启动时会自动创建表并导入样例数据到 PostgreSQL

> 注意：Render 免费 PostgreSQL 有效期 90 天，到期后需要升级或重新创建。

---

## 四、使用 render.yaml 一键部署（Blueprint）

项目根目录已包含 `render.yaml` 配置文件，支持 Blueprint 一键部署：

1. 将代码推送到 GitHub
2. 在 Render 控制台进入 **Blueprints** → **New Blueprint Instance**
3. 选择 GitHub 仓库
4. Render 会自动读取 `render.yaml`，创建 Web Service + PostgreSQL
5. 确认后即可开始部署

> 如使用 Blueprint 部署，默认注释了 DATABASE_URL 环境变量（SQLite 模式）。
> 如需启用 PostgreSQL，编辑 `render.yaml`，取消 `DATABASE_URL` 部分的注释。

---

## 五、环境变量说明

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `PORT` | 服务端口（Render 自动注入） | 5000 |
| `DATABASE_URL` | 数据库连接字符串。未设置=SQLite，以 `postgres` 开头=PostgreSQL | 空（SQLite） |

---

## 六、本地开发验证

### 开发模式（Flask 开发服务器）
```bash
python app.py
# 访问 http://127.0.0.1:5000
```

### 生产模式（Gunicorn）
```bash
pip install gunicorn
gunicorn app:app --bind 0.0.0.0:5000 --workers 2 --timeout 120
# 访问 http://127.0.0.1:5000
```

---

## 七、常见问题排查

### Q: 部署后页面显示 "Internal Server Error"
**A**: 检查 Render 日志（Logs 标签页）。常见原因：
- 依赖未安装完整 → 确认 `requirements.txt` 包含所有依赖
- 数据库初始化失败 → 检查 `DATABASE_URL` 是否正确

### Q: SQLite 模式下数据丢失
**A**: 这是 Render 免费版的限制（临时文件系统）。每次重启/休眠唤醒后本地文件会丢失。系统已做自动初始化，重启后会自动恢复 10 个样例项目数据。如需持久化用户数据，请切换到 PostgreSQL 模式。

### Q: 图纸/照片文件 404
**A**: 随代码打包的文件（`data/tuzhi/`、`data/xiangmu/`）在部署时会一起上传，初始化时自动复制到 `static/uploads/`。用户新上传的文件在 SQLite 模式下重启会丢失。

### Q: 免费版服务休眠
**A**: Render 免费版服务 15 分钟无请求会自动休眠，首次请求需要等待约 30 秒唤醒。如需 24/7 运行，需升级到付费版。

### Q: PostgreSQL 连接失败
**A**: 
- 确认 `DATABASE_URL` 以 `postgres://` 或 `postgresql://` 开头
- 使用 **Internal Database URL**（内网地址，延迟更低）
- 检查 PostgreSQL 实例是否正常运行

### Q: gunicorn 启动报错
**A**: 
- 确认 `app:app` 中第一个 `app` 是 Python 文件名（`app.py`），第二个 `app` 是 Flask 变量名
- 确认 `requirements.txt` 中包含 `gunicorn`
- 检查是否有语法错误：`python -c "import app"`

---

## 八、文件结构说明

```
case_search/
├── app.py              # Flask 主应用（支持 PORT 环境变量）
├── requirements.txt    # 依赖清单（含 gunicorn、psycopg2-binary）
├── render.yaml         # Render Blueprint 配置
├── Procfile            # Procfile（备用启动配置）
├── .gitignore          # Git 忽略规则
├── DEPLOY.md           # 本文档
├── data/               # 源数据（Excel、PDF，随代码部署）
├── static/
│   ├── css/            # 样式文件
│   ├── js/             # 脚本文件
│   └── uploads/        # 上传文件目录（运行时自动创建）
├── templates/          # HTML 模板
└── utils/
    ├── db.py           # 数据库层（支持 SQLite/PostgreSQL 双模式）
    ├── parser.py       # 文件解析器
    ├── matcher.py      # 智能匹配算法
    ├── location.py     # 地域识别
    ├── tender_parser.py # 招标文件解析
    └── init_data.py    # 样例数据初始化
```
