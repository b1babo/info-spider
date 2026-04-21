# Info-Spider

[English](README.md) | [中文文档](README.zh-CN.md)

<div align="center">

**一个灵活的模块化社交媒体平台爬虫框架**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

## 📖 简介

Info-Spider 是一个基于 **Python** 和 **Playwright** 构建的模块化网页爬虫框架，用于从以下社交媒体平台提取数据：

- 🐦 **Twitter/X** - 用户推文、热门话题、首页动态
- 📱 **Reddit** - 社区帖子和评论
- 🚀 **Product Hunt** - 每日产品和排名
- 📈 **Google Trends** - 趋势分析数据
- 🔍 **Google/Bing 搜索** - 搜索结果抓取

## ✨ 特性

- **AI 原生 CLI** - 为 AI 智能体（Claude、GPT 等）设计，可自主控制浏览器
- **持久化浏览器会话** - 跨多次自动化任务保持登录状态
- **模块化设计** - 每个平台独立封装，添加新平台只需创建新的处理器类
- **C/S 架构** - 长运行的服务器保持浏览器连接活跃
- **远程浏览器支持** - 连接到远程机器（Windows/Linux）上的浏览器
- **REST API** - 通过 HTTP API 控制 Actor

## 🤖 AI 原生设计

Info-Spider 专为 **AI 控制的自动化工具** 而设计。一旦登录平台（Twitter、Reddit 等），AI 即可在无需重新认证的情况下自主持续操控浏览器。

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/b1babo/info-spider.git
cd info-spider

# 安装依赖（需要 Python 3.13+）
pip install -e .

# 安装 Playwright 浏览器
playwright install
```

### 配置

复制示例配置并编辑 `config.yaml`：

```bash
cp config.yaml.example config.yaml
```

```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "127.0.0.1"  # 或远程 IP
    port: 9222
    browser_type: "chromium"

tasks:
  - name: "elonmusk_tweets"
    url: "https://x.com/elonmusk"
    actor: "twitter_user_actor"
    use_profile: "twitter"
    enable: true
    actions:
      - action: "create"
        params:
          url: "https://x.com/elonmusk"
        enabled: true
      - action: "scroll_and_extract"
        params:
          scroll_times: 20
          max: 100
          time_range: 24
        enabled: true
```

### 使用

```bash
# 启动服务器
python main.py --server start

# 列出可用的任务模板
python main.py --list-templates

# 从模板创建任务实例
python main.py --create-task elonmusk_tweets

# 执行 Action（会运行所有配置的 actions）
python main.py --task-id <task_id> --action create

# 关闭任务并保存数据
python main.py --close-task <task_id>

# 停止服务器
python main.py --server stop
```

### 远程浏览器设置

使用远程浏览器（例如在 Windows 上）：

**Windows:**
```bash
msedge.exe --remote-debugging-port=9222 --user-data-dir=./profiles/twitter
```

**Linux:**
```bash
chromium --remote-debugging-port=9222 --user-data-dir=./profiles/twitter
```

然后更新 `config.yaml`：
```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "192.168.1.100"  # 远程 IP
    port: 9222
    browser_type: "msedge"
```

## 📁 项目结构

```
info-spider/
├── main.py                 # CLI 入口
├── config.yaml             # 配置文件
├── core/
│   ├── models.py           # Pydantic 数据模型
│   ├── base_actor.py       # Actor 基类
│   ├── actor_server.py     # FastAPI 服务器
│   ├── task_instance.py    # 任务实例管理
│   ├── task_storage.py     # SQLite 存储
│   ├── actor_registry.py   # Actor 注册表
│   └── plugin_loader.py    # Actor 发现加载
├── actors/                 # 平台 Actors
│   ├── twitter_user.py
│   ├── reddit_community_actor.py
│   └── ...
├── data/
│   └── tasks/              # 任务专属数据目录
├── logs/                   # 日志文件（7 天轮转）
└── tests/                  # 测试文件
```

## 🔌 创建自定义 Actor

在 `actors/your_platform_actor.py` 中创建新的 Actor：

```python
import logging
from core.base_actor import BaseActor
from core.models import Resource

logger = logging.getLogger(__name__)

class YourPlatformActor(BaseActor):
    actor_name = "your_platform_actor"
    actor_description = "你的平台描述"

    def setup_actions(self):
        self.register_action(
            "create",
            self.action_create,
            description="导航到页面",
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
        url = params.get('url')
        await task.page.goto(url)
        return {"status": "success", "url": task.page.url}

    async def action_extract_data(self, task, params):
        max_items = params.get('max', 100)
        # 你的提取逻辑
        resources = []
        # ...
        return {"status": "success", "count": len(resources), "resources": resources}
```

然后在 `config.yaml` 中注册：

```yaml
actors:
  - name: "your_platform_actor"
    class: "YourPlatformActor"
    description: "你的平台 Actor"
```

## 📊 数据模型

所有抓取的数据使用以下 Pydantic 模型：

- **Resource** - 基础资源（内容、作者、分析、标签）
- **Comment** - 评论资源
- **Author** - 作者信息
- **Analytics** - 互动指标（点赞、分享、浏览）

## 🗄️ 数据存储

数据存储在：
- **SQLite** (`data/data.db`) - 合并、去重的数据
- **JSON** (`data/{task_name}/YYYY/MM/DD/raw/`) - 原始备份

查询数据库：
```bash
sqlite3 data/data.db "SELECT * FROM resources WHERE resource_author_name='elonmusk' LIMIT 10;"
```

## 🛠️ 开发

```bash
# 运行测试
pytest tests/

# 格式化代码
black .

# 类型检查
mypy .
```

## 📝 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🤝 贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## ⚠️ 免责声明

本工具仅供教育和研究目的使用。请遵守你所抓取平台的服务条款。

## 🆚 与 Browser-Use 对比

| 特性 | Info-Spider | Browser-Use |
|------|-------------|-------------|
| **设计理念** | 数据抓取框架 | AI 智能体浏览器自动化 |
| **架构** | C/S 架构，服务器常驻 | Agent 模式，一次性任务 |
| **操作方式** | 预定义 Actions | AI 自主决策 |
| **配置方式** | YAML 配置文件 | Python 代码/CLI |
| **使用场景** | 持续数据采集 | 一次性自动化任务 |
| **数据存储** | 内置 SQLite + JSON | 无内置存储 |
| **平台支持** | Twitter, Reddit, PH, Trends | 任意网站 |
| **学习曲线** | 配置后简单 | 需要理解 Agent 概念 |
| **云服务** | 无 | Browser Use Cloud |

### 核心区别

**Info-Spider** 是**数据抓取工具**：
- 为特定社交平台优化
- 预定义的提取逻辑
- 持久化数据存储和去重
- 适合定时采集、数据监控
- **Actions 约束了 Agent 的操作空间**，使任务更有针对性
- **返回结构化数据**，便于后续处理和分析

**Browser-Use** 是**AI 自动化助手**：
- 通用浏览器操作
- AI 自主规划和执行
- 适合表单填写、购物、任务自动化
- Agent 完全自主，操作空间无限制
- 返回结果取决于任务，结构不固定

### 如何选择

**选择 Info-Spider：**
- 需要从 Twitter/Reddit 等平台持续采集数据
- 需要数据去重和历史存储
- 有固定的抓取需求

**选择 Browser-Use：**
- 需要灵活的浏览器自动化
- 任务复杂度高，需要 AI 自主决策
- 一次性任务（填表、下单、爬取任意网站）

## 🙏 致谢

- [Playwright](https://playwright.dev/) - 浏览器自动化
- [FastAPI](https://fastapi.tiangolo.com/) - API 框架
- [Pydantic](https://pydantic-docs.helpmanual.io/) - 数据验证
