# CLAUDE.md

Info-Spider 项目开发指南 - 给 Claude Code 的说明文档。

## 项目概述

Info-Spider 是一个C/S 架构的浏览器自动化系统，用于从社交平台（Twitter/X、Reddit、Product Hunt、Google Trends）抓取数据。采用服务器-客户端架构：服务器常驻进程保持浏览器连接，CLI 通过 HTTP API 交互式执行操作。

## 核心架构

### 服务器模式 (推荐)

**ActorServer** (`core/actor_server.py`): FastAPI 服务器，常驻进程保持所有浏览器连接

- 常驻内存，管理所有 `TaskInstance`
- 提供 REST API 执行 Actions
- 支持远程浏览器连接

**TaskInstance** (`core/task_instance.py`): 任务运行实例

- 包含 `task_id`、`task_config`、`profile`、`actor`
- 管理 BrowserContext 和 Page
- `get_data_dir()`: 返回任务专属目录 `data/tasks/{task_id}/`

**BaseActor** (`core/base_actor.py`): Actor 基类

- 所有平台 Actor 继承此类
- 注册 Actions (`setup_actions()`, `register_action()`)
- Action 处理函数签名: `async def handler(self, task, params) -> Dict`

### 数据模型 (`core/models.py`)

**配置模型:**
- `AppConfig`: 根配置
- `Profile`: 浏览器/API 配置 (mode, port, browser_host, browser_type)
- `TaskConfig`: 任务配置 (name, url, actor, use_profile, actions, cron, dedup)
- `ActionConfig`: Action 配置 (enabled, action, params)
- `DedupConfig`: 去重配置 (enabled, strategy, ttl_days, url_normalize)

**数据模型:**
- `Resource`: 基础资源 (url, content, author, analytics, hashtags)
- `Comment`: 评论资源
- `Author`: 作者信息
- `Analytics`: 统计数据 (view_count, like_count, etc.)

### 配置文件 (`config.yaml`)

```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "192.168.2.119"  # 远程浏览器IP
    port: 9222
    browser_type: "msedge"

  - name: "product_hunt"
    mode: "api"
    params:
      api_key: "..."

actors:
  - name: "twitter_user_actor"
    class: "TwitterUserActor"
    description: "..."

tasks:
  - name: "github_tweets"
    url: "https://x.com/GitHub_Daily"
    actor: "twitter_user_actor"
    use_profile: "twitter"
    enable: true
    actions:
      - action: "create"
        params:
          url: "https://x.com/GitHub_Daily"
        enabled: true
      - action: "scroll_and_extract"
        params:
          scroll_times: 20
          max: 100
        enabled: true
```

## 开发命令

### 服务器操作

```bash
# 启动服务器 (默认 http://127.0.0.1:7666)
python main.py --server start

# 查看服务器状态
python main.py --server status

# 停止服务器
python main.py --server stop
```

### Actor 交互

```bash
# 列出任务模板 (配置文件中定义的任务)
python main.py --list-templates

# 列出活跃的任务实例 (已创建的实例)
python main.py --list-instances

# 列出可用 Actors
python main.py --list-actors

# 创建任务实例 (使用任务模板名称)
python main.py --create-task github_tweets

# 执行 Action (使用 task_id)
python main.py --task-id task_abc123 --action scroll_and_extract

# 执行带参数的 Action
python main.py --task-id task_abc123 --action search_trends --action-params '{"keyword": "AI"}'

# 关闭任务实例并保存数据
python main.py --close-task task_abc123
```

## Actor 开发指南

### 创建新 Actor

```python
"""actors/my_platform_actor.py"""
from core.base_actor import BaseActor
from core.models import Resource
import logging

logger = logging.getLogger(__name__)

class MyPlatformActor(BaseActor):
    actor_name = "my_platform_actor"
    actor_description = "我的平台 Actor"

    def setup_actions(self):
        self.register_action(
            "create",
            self.action_create,
            description="创建任务并导航到页面",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True}
                ]
            }
        )

        self.register_action(
            "extract_data",
            self.action_extract_data,
            description="提取数据",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 100}
                ]
            }
        )

    async def action_create(self, task, params):
        """导航到目标页面"""
        url = params.get('url')
        await task.page.goto(url)
        return {"status": "success", "url": task.page.url}

    async def action_extract_data(self, task, params):
        """提取数据"""
        max_items = params.get('max', 100)
        # 使用 task.page 进行操作
        elements = await task.page.locator('.item').all()

        resources = []
        for el in elements[:max_items]:
            # 提取逻辑...
            resource = Resource(
                id=...,
                resource_url=...,
                resource_content=...,
                # ...
            )
            resources.append(resource)

        return {
            "status": "success",
            "count": len(resources),
            "resources": resources
        }
```

### 任务专属数据目录

Actor 可以使用 `task.get_data_dir()` 获取任务专属目录：

```python
async def action_download(self, task, params):
    download_dir = task.get_data_dir()  # data/tasks/{task_id}/
    download_dir.mkdir(parents=True, exist_ok=True)

    # 保存文件到任务目录
    csv_path = download_dir / "data.csv"
    # ...
```

### 数据存储

```python
from core.task_storage import TaskStorage

async def action_close(self, task, params):
    if self.resources:
        storage = TaskStorage()
        raw_file = storage.save_raw_result(task.task_config.name, self.resources)
        stats = storage.merge_to_database(task.task_config.name, self.resources)
    return {"status": "success", "saved_to": str(raw_file)}
```

## 项目结构

```
info-spider/
├── main.py                 # 入口点 (CLI/服务器)
├── config.yaml             # 配置文件
├── core/
│   ├── models.py           # Pydantic 数据模型
│   ├── base_actor.py       # Actor 基类
│   ├── actor_server.py     # FastAPI 服务器
│   ├── task_instance.py    # TaskInstance 管理
│   ├── task_storage.py     # SQLite 数据存储
│   ├── actor_registry.py   # Actor 注册表
│   ├── plugin_loader.py    # Actor 发现加载
│   ├── profile_manager.py  # 浏览器配置管理
│   └── setup_logging.py    # 日志配置
├── actors/                 # 平台 Actors
│   ├── twitter_user.py
│   ├── reddit_community_actor.py
│   ├── google_trends_actor.py
│   └── ...
├── data/
│   └── tasks/              # 任务专属数据
│       └── {task_id}/
├── logs/                   # 日志文件 (7天轮转)
└── tests/                  # 测试文件
```

## 重要约定

1. **命名**: Actor 类名使用 `CamelCase`，文件名使用 `snake_case`
2. **异步**: 所有 Action 处理函数必须是 `async`
3. **返回值**: Action 返回 `Dict[str, Any]`，至少包含 `"status"` 键
4. **目录**: 使用 `task.get_data_dir()` 获取任务专属目录
5. **日志**: 使用 `logger = logging.getLogger(__name__)`
6. **模型**: 所有数据使用 `core/models.py` 中的 Pydantic 模型

## 远程浏览器

支持连接到远程 Windows 机器上的浏览器：

```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "192.168.2.119"  # 远程 IP
    port: 9222
    browser_type: "msedge"
```

远程浏览器启动：
```bash
# Windows 上
msedge.exe --remote-debugging-port=9222 --user-data-dir=./profiles/twitter
```

## 去重策略

每个任务可配置去重策略：

```yaml
tasks:
  - name: "my_task"
    dedup:
      enabled: true
      strategy: "url"  # none | id | url | content | both
      url_normalize: true
      ttl_days: 7
```

- `id`: 使用资源 ID (tweet_id, post_id)
- `url`: 使用规范化 URL
- `content`: 使用内容哈希
- `both`: ID 或 URL 任一匹配即去重
