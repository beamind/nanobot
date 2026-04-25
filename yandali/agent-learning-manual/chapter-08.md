# 第8章：配置系统与部署

> **学习目标**：深入理解 nanobot 的配置系统架构，掌握从开发环境到生产环境的完整部署流程，理解安全最佳实践，并能够独立完成 Docker 和 systemd 两种部署方式。

---

## 8.1 引言：从开发到生产

在第3章中，我们完成了 nanobot 的本地环境搭建——运行了 `nanobot onboard`，配置了 API Key，通过 CLI 与 Agent 进行了第一次对话。但这只是起点。

当 Agent 从个人玩具变成团队工具、从本地实验变成 7×24 在线服务时，一系列新问题浮现：

- **秘密管理**：API Key 不能明文写在代码里，如何安全地注入配置？
- **配置版本**：团队成员如何共享配置而不泄露密钥？
- **部署方式**：Docker 还是 systemd？多服务如何编排？
- **安全加固**：如何防止未授权访问？Shell 命令如何隔离？
- **监控运维**：Agent 挂了怎么办？日志如何收集？

本章将回答这些问题，带你完成从"能跑"到"能扛"的跨越。

---

## 8.2 配置系统架构

nanobot 的配置系统在第3章已经初窥门径，现在我们深入其工程实现。

### 8.2.1 配置加载的完整流程

```
config.json (磁盘文件)
    │
    ▼
┌─────────────────────────────┐
│ 1. load_config()            │ ← nanobot/config/loader.py
│    - 读取 JSON              │
│    - _migrate_config()      │ ← 旧配置自动迁移
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ 2. Config.model_validate()  │ ← Pydantic 验证
│    - 类型检查               │
│    - 默认值填充             │
│    - 字段约束验证           │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ 3. resolve_config_env_vars()│ ← 环境变量注入
│    - ${VAR} → 实际值        │
└────────────┬────────────────┘
             ▼
┌─────────────────────────────┐
│ 4. _apply_ssrf_whitelist()  │ ← 网络安全配置
│    - SSRF 白名单应用到安全模块│
└─────────────────────────────┘
```

### 8.2.2 配置迁移：向后兼容的艺术

软件升级时，配置文件格式可能变化。nanobot 的 `_migrate_config()` 自动处理旧格式：

```python
def _migrate_config(data: dict) -> dict:
    # v0.1.x → v0.1.y: restrictToWorkspace 从 exec 子配置提升到 tools 根级
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")

    # v0.1.x → v0.1.y: myEnabled / mySet 扁平键 → tools.my 子对象
    if "myEnabled" in tools or "mySet" in tools:
        my_cfg = tools.setdefault("my", {})
        if "myEnabled" in tools and "enable" not in my_cfg:
            my_cfg["enable"] = tools.pop("myEnabled")
        if "mySet" in tools and "allowSet" not in my_cfg:
            my_cfg["allowSet"] = tools.pop("mySet")

    return data
```

**设计意图**：用户升级 nanobot 后，旧配置文件不需要手动修改。迁移逻辑在内存中进行，不会自动写回磁盘——只有当用户显式保存时，新格式才会持久化。

### 8.2.3 Provider 自动匹配

`Config._match_provider()` 是配置系统中最复杂的逻辑之一。它实现了**五层回退策略**：

```python
def _match_provider(self, model: str | None = None):
    # Layer 1: 用户强制指定 provider
    if forced != "auto":
        return getattr(self.providers, forced, None), forced

    # Layer 2: 模型名前缀匹配
    # e.g. "anthropic/claude-3" → anthropic provider
    for spec in PROVIDERS:
        if model_prefix == spec.name:
            return p, spec.name

    # Layer 3: 关键词匹配
    # e.g. "deepseek-chat" → deepseek provider
    for spec in PROVIDERS:
        if any(kw in model_name for kw in spec.keywords):
            return p, spec.name

    # Layer 4: 本地部署回退
    for spec in PROVIDERS:
        if spec.is_local and spec.detect_by_base_keyword in api_base:
            return p, spec.name

    # Layer 5: 网关/任意 provider 回退
    for spec in PROVIDERS:
        if p and p.api_key:  # 第一个有 API Key 的 provider
            return p, spec.name
```

**效果示例**：

| 配置 | 匹配结果 | 原因 |
|------|---------|------|
| `"model": "anthropic/claude-3.5-sonnet"` | Anthropic | 前缀匹配 |
| `"model": "deepseek-chat"` | DeepSeek | 关键词匹配 |
| `"model": "gpt-4o"` | OpenAI | 关键词匹配 |
| `"model": "llama3.2"`, `api_base="http://localhost:11434"` | Ollama | 本地部署回退 |
| `"model": "any-model"`, 只有 OpenRouter 有 key | OpenRouter | 默认回退 |

---

## 8.3 环境变量与秘密管理

### 8.3.1 ${VAR} 语法

nanobot 支持在 `config.json` 中使用 `${VAR_NAME}` 引用环境变量：

```json
{
  "providers": {
    "openai": {
      "apiKey": "${OPENAI_API_KEY}"
    },
    "anthropic": {
      "apiKey": "${ANTHROPIC_API_KEY}"
    }
  },
  "channels": {
    "telegram": {
      "token": "${TELEGRAM_BOT_TOKEN}"
    }
  }
}
```

解析实现：

```python
_ENV_REF_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

def _resolve_in_place(obj):
    if isinstance(obj, str):
        return _ENV_REF_PATTERN.sub(_env_replace, obj)
    if isinstance(obj, BaseModel):
        # 递归解析 Pydantic 模型的每个字段
        ...
    if isinstance(obj, dict):
        return {k: _resolve_in_place(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_in_place(v) for v in obj]
    return obj

def _env_replace(match):
    name = match.group(1)
    value = os.environ.get(name)
    if value is None:
        raise ValueError(f"Environment variable '{name}' is not set")
    return value
```

**设计亮点**：
- **递归解析**：环境变量引用可以出现在任何嵌套层级
- **严格失败**：如果引用的变量未设置，启动时立即报错，而不是静默使用空字符串
- **身份保持**：如果没有 `${}` 引用，原对象不被复制，节省内存

### 8.3.2 生产环境的秘密管理

**方案一：systemd EnvironmentFile（推荐）**

```ini
# /etc/systemd/system/nanobot-gateway.service
[Service]
EnvironmentFile=/etc/nanobot/secrets.env
ExecStart=/usr/local/bin/nanobot gateway
```

```bash
# /etc/nanobot/secrets.env
OPENAI_API_KEY=sk-xxxxxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
```

```bash
chmod 600 /etc/nanobot/secrets.env
```

**方案二：Docker Secrets / Kubernetes Secrets**

```yaml
# docker-compose.yml
services:
  nanobot-gateway:
    environment:
      - OPENAI_API_KEY_FILE=/run/secrets/openai_key
    secrets:
      - openai_key

secrets:
  openai_key:
    file: ./secrets/openai_key.txt
```

**方案三：配置分层（开发/ staging / 生产）**

```
~/.nanobot/
├── config.json           # 公共配置（无密钥）
├── config.dev.json       # 开发环境覆盖
├── config.prod.json      # 生产环境覆盖
└── .env                  # 本地环境变量（gitignore）
```

---

## 8.4 Docker 部署

### 8.4.1 Dockerfile 分层构建

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Layer 1: 系统依赖（Node.js for WhatsApp bridge）
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git bubblewrap openssh-client && \
    ... && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean

# Layer 2: Python 依赖（缓存层）
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p nanobot bridge && touch nanobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf nanobot bridge

# Layer 3: 源码安装
COPY nanobot/ nanobot/
COPY bridge/ bridge/
RUN uv pip install --system --no-cache .

# Layer 4: Bridge 构建
WORKDIR /app/bridge
RUN npm install && npm run build

# Layer 5: 运行时配置
RUN useradd -m -u 1000 -s /bin/bash nanobot && \
    mkdir -p /home/nanobot/.nanobot && \
    chown -R nanobot:nanobot /home/nanobot /app
USER nanobot
ENV HOME=/home/nanobot
EXPOSE 18790
ENTRYPOINT ["entrypoint.sh"]
```

**分层设计意图**：

| 层 | 内容 | 缓存特性 |
|---|------|---------|
| Layer 1 | 系统依赖 | 极少变化，缓存时间最长 |
| Layer 2 | Python 依赖 | pyproject.toml 变化时重建 |
| Layer 3 | 源码 | 每次代码变更重建 |
| Layer 4 | Bridge 构建 | bridge/ 变化时重建 |
| Layer 5 | 运行时 | 始终最后执行 |

### 8.4.2 docker-compose 多服务编排

```yaml
x-common-config: &common-config
  build:
    context: .
    dockerfile: Dockerfile
  volumes:
    - ~/.nanobot:/home/nanobot/.nanobot
  cap_drop:
    - ALL          # 丢弃所有 capabilities
  cap_add:
    - SYS_ADMIN    # bubblewrap 沙箱需要
  security_opt:
    - apparmor=unconfined
    - seccomp=unconfined

services:
  nanobot-gateway:
    container_name: nanobot-gateway
    <<: *common-config
    command: ["gateway"]
    restart: unless-stopped
    ports:
      - 18790:18790
    deploy:
      resources:
        limits:
          cpus: "1"
          memory: 1G
        reservations:
          cpus: "0.25"
          memory: 256M
```

**安全设计**：
- `cap_drop: [ALL]`：丢弃所有 Linux capabilities，最小权限原则
- `cap_add: [SYS_ADMIN]`：仅添加 bubblewrap 沙箱所需的 capability
- `security_opt`：禁用 AppArmor 和 Seccomp 的默认策略（因为沙箱需要创建命名空间）
- `restart: unless-stopped`：崩溃后自动重启
- 资源限制：防止单个容器耗尽主机资源

### 8.4.3 entrypoint 脚本

```bash
#!/bin/sh
dir="$HOME/.nanobot"
if [ -d "$dir" ] && [ ! -w "$dir" ]; then
    owner_uid=$(stat -c %u "$dir")
    cat >&2 <<EOF
Error: $dir is not writable (owned by UID $owner_uid, running as UID $(id -u)).

Fix (pick one):
  Host:   sudo chown -R 1000:1000 ~/.nanobot
  Docker: docker run --user \$(id -u):\$(id -g) ...
  Podman: podman run --userns=keep-id ...
EOF
    exit 1
fi
exec nanobot "$@"
```

**为什么需要这个检查？**

Docker 容器以 UID 1000（`nanobot` 用户）运行。如果宿主机上的 `~/.nanobot` 目录属于 UID 1001，容器内将无法写入。`entrypoint.sh` 在启动前检测这个问题，给出清晰的修复指引。

---

## 8.5 systemd 服务部署

对于不使用 Docker 的场景，systemd 用户服务是最佳选择。

### 8.5.1 用户服务配置

```ini
# ~/.config/systemd/user/nanobot-gateway.service
[Unit]
Description=Nanobot Gateway
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/nanobot gateway
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h

[Install]
WantedBy=default.target
```

**安全选项解析**：

| 选项 | 作用 |
|------|------|
| `NoNewPrivileges=yes` | 禁止进程提升权限（如 sudo） |
| `ProtectSystem=strict` | 除指定路径外，整个文件系统只读 |
| `ReadWritePaths=%h` | 允许写入用户主目录（存放配置和工作区） |
| `Restart=always` | 任何退出（包括崩溃）都自动重启 |

### 8.5.2 启用与日志

```bash
# 启用服务（开机自启 + 立即启动）
systemctl --user daemon-reload
systemctl --user enable --now nanobot-gateway

# 查看状态
systemctl --user status nanobot-gateway

# 查看日志
journalctl --user -u nanobot-gateway -f

# 重启（配置文件变更后）
systemctl --user restart nanobot-gateway
```

### 8.5.3 持久运行（logout 后不掉）

默认情况下，用户服务在注销后停止。要让 nanobot 在 logout 后继续运行：

```bash
loginctl enable-linger $USER
```

这会告诉 systemd 为该用户保留一个会话，即使用户没有主动登录。

---

## 8.6 生产安全最佳实践

### 8.6.1 通道访问控制

生产环境必须配置 `allowFrom`，防止机器人被恶意利用：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}",
      "allowFrom": ["123456789"]
    }
  }
}
```

**获取 Telegram 用户 ID**：向 `@userinfobot` 发送任意消息，它会回复你的用户 ID。

### 8.6.2 Shell 沙箱（bwrap）

Linux 上启用 bubblewrap 沙箱，实现内核级隔离：

```json
{
  "tools": {
    "exec": {
      "sandbox": "bwrap"
    }
  }
}
```

**隔离效果**：

| 资源 | 权限 |
|------|------|
| 工作区目录 | read-write |
| 媒体目录 | read-only |
| 系统目录（/usr, /bin） | read-only |
| 配置文件（含 API Key） | **隐藏**（tmpfs 覆盖） |
| 网络 | 继承父进程（需额外限制） |

### 8.6.3 文件系统限制

```bash
# 限制 .nanobot 目录权限
chmod 700 ~/.nanobot
chmod 600 ~/.nanobot/config.json
chmod 700 ~/.nanobot/whatsapp-auth
chmod 700 ~/.nanobot/workspace
```

### 8.6.4 SSRF 白名单

如果需要访问内部网络（如 Tailscale 的 `100.64.0.0/10`），配置 SSRF 白名单：

```json
{
  "tools": {
    "ssrfWhitelist": ["100.64.0.0/10", "10.0.0.0/8"]
  }
}
```

### 8.6.5 安全清单

部署前逐项检查：

```
□ API keys 存储安全（非代码/环境变量/0600 权限）
□ config.json 权限设为 0600
□ 所有通道配置 allowFrom（非 ["*"]）
□ 以非 root 用户运行
□ Linux 启用 bwrap 沙箱
□ 文件系统权限正确
□ 依赖更新到最新版本
□ 日志监控启用
□ API provider 侧启用速率限制和花费上限
□ 备份和灾难恢复计划
```

---

## 8.7 监控与可观测性

### 8.7.1 Loguru 日志

nanobot 使用 Loguru，通过环境变量控制日志级别：

```bash
export LOGURU_LEVEL=INFO   # 默认
export LOGURU_LEVEL=DEBUG  # 开发调试
export LOGURU_LEVEL=WARNING # 生产（减少噪音）
```

systemd 日志通过 `journalctl` 查看：

```bash
# 实时跟踪
journalctl --user -u nanobot-gateway -f

# 最近 100 行
journalctl --user -u nanobot-gateway -n 100

# 今天所有日志
journalctl --user -u nanobot-gateway --since today
```

### 8.7.2 Langfuse 集成

设置环境变量即可启用 LLM 调用追踪：

```bash
export LANGFUSE_SECRET_KEY=sk-lf-xxx
export LANGFUSE_PUBLIC_KEY=pk-lf-xxx
export LANGFUSE_HOST=https://cloud.langfuse.com
```

启用后，nanobot 会自动通过 `langfuse.openai` 包装客户端，记录每次 LLM 调用的延迟、Token 用量、成本等。

### 8.7.3 健康检查

nanobot gateway 提供 `/health` 端点：

```bash
curl http://localhost:18790/health
```

可用于负载均衡器的健康检查或监控系统的探针。

---

## 8.8 实战：完整的生产部署

让我们完成一次从 0 到 1 的完整生产部署。

### 步骤 1：准备服务器

```bash
# 创建专用用户
sudo useradd -m -s /bin/bash nanobot
sudo -u nanobot mkdir -p /home/nanobot/.nanobot

# 安装 nanobot
sudo -u nanobot pip install --user nanobot-ai
```

### 步骤 2：配置秘密

```bash
# 创建环境变量文件
sudo -u nanobot tee /home/nanobot/.nanobot/secrets.env << 'EOF'
OPENAI_API_KEY=sk-prod-xxxxxxxx
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
EOF

sudo -u nanobot chmod 600 /home/nanobot/.nanobot/secrets.env
```

### 步骤 3：创建配置文件

```bash
sudo -u nanobot tee /home/nanobot/.nanobot/config.json << 'EOF'
{
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o",
      "maxToolIterations": 50,
      "provider": "openai"
    }
  },
  "providers": {
    "openai": {
      "apiKey": "${OPENAI_API_KEY}"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}",
      "allowFrom": ["YOUR_USER_ID"]
    }
  },
  "tools": {
    "exec": {
      "sandbox": "bwrap"
    },
    "restrictToWorkspace": true
  }
}
EOF

sudo -u nanobot chmod 600 /home/nanobot/.nanobot/config.json
```

### 步骤 4：创建 systemd 服务

```bash
sudo tee /etc/systemd/system/nanobot-gateway.service << 'EOF'
[Unit]
Description=Nanobot Gateway
After=network.target

[Service]
Type=simple
User=nanobot
Group=nanobot
WorkingDirectory=/home/nanobot
Environment=HOME=/home/nanobot
Environment=LOGURU_LEVEL=INFO
EnvironmentFile=/home/nanobot/.nanobot/secrets.env
ExecStart=/home/nanobot/.local/bin/nanobot gateway
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/home/nanobot

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now nanobot-gateway
```

### 步骤 5：验证

```bash
# 检查服务状态
sudo systemctl status nanobot-gateway

# 查看日志
sudo journalctl -u nanobot-gateway -f

# 测试健康检查
curl http://localhost:18790/health
```

---

## 8.9 本章小结

本章覆盖了 nanobot 从开发到生产的完整部署路径：

1. **配置系统**：Pydantic 模型提供类型安全，`_migrate_config()` 实现向后兼容，`resolve_config_env_vars()` 支持 `${VAR}` 环境变量注入，`_match_provider()` 实现五层 Provider 自动匹配。

2. **秘密管理**：推荐使用 systemd `EnvironmentFile` 或 Docker Secrets，避免将密钥写入版本控制或配置文件。

3. **Docker 部署**：分层 Dockerfile 优化构建缓存，docker-compose 提供多服务编排和安全选项（`cap_drop: [ALL]` + `cap_add: [SYS_ADMIN]`），`entrypoint.sh` 提供权限诊断。

4. **systemd 部署**：用户服务配置简单，支持自动重启和资源限制。`loginctl enable-linger` 实现 logout 后持续运行。

5. **安全加固**：`allowFrom` 白名单控制通道访问，bwrap 沙箱实现内核级命令隔离，文件权限 0600/0700 保护敏感数据，SSRF 白名单控制内部网络访问。

6. **可观测性**：Loguru 日志通过 `journalctl` 查看，Langfuse 追踪 LLM 调用，内置 `/health` 端点支持健康检查。

---

## 8.10 动手实验

### 实验 1：配置环境变量注入

创建一个测试配置：

```json
{
  "test": "${TEST_VAR}"
}
```

在 Python 中测试解析：

```python
import os
os.environ["TEST_VAR"] = "hello"
from nanobot.config.loader import resolve_config_env_vars
from nanobot.config.schema import Config

config = Config()
resolved = resolve_config_env_vars(config)
print(resolved)
```

### 实验 2：测试配置迁移

创建一个"旧格式"配置：

```json
{
  "tools": {
    "exec": {
      "restrictToWorkspace": true
    },
    "myEnabled": true
  }
}
```

观察 `load_config()` 后，`restrictToWorkspace` 是否被提升到 `tools` 根级，`myEnabled` 是否变为 `tools.my.enable`。

### 实验 3：Docker 构建

```bash
cd /path/to/nanobot
docker build -t nanobot:test .
docker run --rm nanobot:test status
```

### 实验 4：测试 bwrap 沙箱

在 Linux 上安装 bubblewrap：

```bash
sudo apt install bubblewrap
```

配置 nanobot 启用沙箱，然后让 Agent 执行：

```
> 执行 "cat ~/.nanobot/config.json"
```

观察 Agent 是否被拒绝访问（因为沙箱隐藏了配置文件）。

### 实验 5：systemd 服务模板

将 8.8 节的 systemd 服务文件保存到 `/tmp/nanobot-test.service`，然后：

```bash
# 检查语法
systemd-analyze verify /tmp/nanobot-test.service

# 查看服务会使用的资源
systemd-analyze security /tmp/nanobot-test.service
```

---

## 8.11 思考题

1. `_migrate_config()` 在内存中修改配置但不写回磁盘。这种设计的利弊是什么？如果改为自动写回磁盘，可能会有什么问题？

2. Docker Compose 中 `cap_drop: [ALL]` 后只添加 `SYS_ADMIN`。为什么 bubblewrap 需要 `SYS_ADMIN`？如果不用沙箱，是否可以完全去掉所有 `cap_add`？

3. `entrypoint.sh` 检查目录可写性时，使用 `stat -c %u`（Linux）和 `stat -f %u`（macOS）两种命令。为什么需要这种跨平台兼容？Docker 容器内部还需要考虑 macOS 吗？

4. systemd 的 `ProtectSystem=strict` 会让除 `ReadWritePaths` 外的所有路径只读。如果 nanobot 需要写入 `/tmp` 目录，这会有问题吗？如何安全地处理？

5. 生产环境中，`LOGURU_LEVEL=WARNING` 可以减少日志噪音，但可能会遗漏重要的调试信息。如何在"减少噪音"和"保留关键信息"之间取得平衡？

---

## 参考阅读

- nanobot 源码：`nanobot/config/schema.py`（Pydantic 配置模型，335 行）
- nanobot 源码：`nanobot/config/loader.py`（配置加载器，172 行）
- nanobot 文档：`docs/deployment.md`（部署文档）
- nanobot 文档：`SECURITY.md`（安全策略）
- Dockerfile / docker-compose.yml / entrypoint.sh
- systemd 文档：https://www.freedesktop.org/software/systemd/man/
- bubblewrap 文档：https://github.com/containers/bubblewrap

---

> **下一章预告**：第9章《高级特性与设计哲学》将探讨 nanobot 的高级能力——Skills 系统、Heartbeat 服务、Cron 定时任务、以及"小而美"的架构设计哲学。你会理解为什么 nanobot 能在 4000 行核心代码中支撑起完整的 Agent 框架。
