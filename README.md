# Info-Spider

[English](README.md) | [中文文档](README.zh-CN.md)

<div align="center">

**A flexible, actor-based web scraping framework for social media platforms**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

## 📖 Overview

Info-Spider is a modular web scraping framework built with **Python** and **Playwright**, designed to extract data from social media platforms including:

- 🐦 **Twitter/X** - User tweets, trending topics, home feed
- 📱 **Reddit** - Community posts and comments
- 🚀 **Product Hunt** - Daily posts and rankings
- 📈 **Google Trends** - Trend analysis data
- 🔍 **Google/Bing Search** - Search results scraping

## ✨ Features

- **Modular Design** - Each platform is independently encapsulated; adding new platforms only requires creating a new handler class
- **Server-Client Model** - Long-running server keeps browser connections alive
- **Remote Browser Support** - Connect to browsers on remote machines (Windows/Linux)
- **REST API** - Control actors via HTTP API

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/b1babo/info-spider.git
cd info-spider

# Install dependencies (requires Python 3.13+)
pip install -e .

# Install Playwright browsers
playwright install
```

### Configuration

Edit `config.yaml` to configure your profiles and tasks:

```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "127.0.0.1"  # or remote IP
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

### Usage

```bash
# Start the server
python main.py --server start

# List available task templates
python main.py --list-templates

# Create a task instance from template
python main.py --create-task elonmusk_tweets

# Execute actions (will run all configured actions)
python main.py --task-id <task_id> --action create

# Close task and save data
python main.py --close-task <task_id>

# Stop the server
python main.py --server stop
```

### Remote Browser Setup

To use a remote browser (e.g., on Windows):

**Windows:**
```bash
msedge.exe --remote-debugging-port=9222 --user-data-dir=./profiles/twitter
```

**Linux:**
```bash
chromium --remote-debugging-port=9222 --user-data-dir=./profiles/twitter
```

Then update `config.yaml`:
```yaml
profiles:
  - name: "twitter"
    mode: "browser"
    browser_host: "192.168.1.100"  # Remote IP
    port: 9222
    browser_type: "msedge"
```

## 📁 Project Structure

```
info-spider/
├── main.py                 # CLI entry point
├── config.yaml             # Configuration file
├── core/
│   ├── models.py           # Pydantic data models
│   ├── base_actor.py       # Base actor class
│   ├── actor_server.py     # FastAPI server
│   ├── task_instance.py    # Task instance management
│   ├── task_storage.py     # SQLite storage
│   ├── actor_registry.py   # Actor registry
│   └── plugin_loader.py    # Actor discovery
├── actors/                 # Platform actors
│   ├── twitter_user.py
│   ├── reddit_community_actor.py
│   └── ...
├── data/
│   └── tasks/              # Per-task data directories
├── logs/                   # Log files (7-day rotation)
└── tests/                  # Test files
```

## 🔌 Creating Custom Actors

Create a new actor in `actors/your_platform_actor.py`:

```python
import logging
from core.base_actor import BaseActor
from core.models import Resource

logger = logging.getLogger(__name__)

class YourPlatformActor(BaseActor):
    actor_name = "your_platform_actor"
    actor_description = "Your platform description"

    def setup_actions(self):
        self.register_action(
            "create",
            self.action_create,
            description="Navigate to page",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True}
                ]
            }
        )

        self.register_action(
            "extract_data",
            self.action_extract_data,
            description="Extract data",
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
        # Your extraction logic here
        resources = []
        # ...
        return {"status": "success", "count": len(resources), "resources": resources}
```

Then register it in `config.yaml`:

```yaml
actors:
  - name: "your_platform_actor"
    class: "YourPlatformActor"
    description: "Your platform actor"
```

## 📊 Data Models

All scraped data uses the following Pydantic models:

- **Resource** - Base resource with content, author, analytics, hashtags
- **Comment** - Comment resource
- **Author** - Author information
- **Analytics** - Engagement metrics (likes, shares, views)

## 🗄️ Data Storage

Data is stored in:
- **SQLite** (`data/data.db`) - Merged, deduplicated data
- **JSON** (`data/{task_name}/YYYY/MM/DD/raw/`) - Raw backups

Query the database:
```bash
sqlite3 data/data.db "SELECT * FROM resources WHERE resource_author_name='elonmusk' LIMIT 10;"
```

## 🛠️ Development

```bash
# Run tests
pytest tests/

# Format code
black .

# Type checking
mypy .
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Disclaimer

This tool is for educational and research purposes only. Please respect the terms of service of the platforms you are scraping.



## 🙏 Acknowledgments

- [Playwright](https://playwright.dev/) - Browser automation
- [FastAPI](https://fastapi.tiangolo.com/) - API framework
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation
