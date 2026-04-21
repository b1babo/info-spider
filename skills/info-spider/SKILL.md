---
name: info-spider
description: "Browser automation system for scraping data from Twitter/X, Reddit, Product Hunt, and Google Trends. Use when user requests data collection from social platforms, wants to manage scraping tasks, or needs to interact with the info-spider CLI."
---

# Info-Spider

Browser automation system for scraping data from social platforms. Uses a server-client architecture where the server manages browser connections and the CLI provides interactive control.

## Quick Start

```bash
# Start the server (required first step)
python main.py --server start

# Check server status
python main.py --server status

# Stop server when done
python main.py --server stop
```

## Workflow

1. **Start server**: `python main.py --server start`
2. **List templates**: `python main.py --list-templates`
3. **Create task**: `python main.py --create-task <template_name>`
4. **Execute actions**: `python main.py --task-id <id> --action <action_name>`
5. **Close task**: `python main.py --close-task <id>`

## Server Commands

| Command | Description |
|---------|-------------|
| `--server start` | Start the ActorServer (default: http://127.0.0.1:7666) |
| `--server stop` | Stop the running server |
| `--server status` | Check if server is running and list active tasks |

## Task Management Commands

| Command | Description |
|---------|-------------|
| `--list-templates` | List all task templates defined in config.yaml |
| `--list-instances` | List all active task instances |
| `--list-actors` | List all available platform actors |
| `--create-task <name>` | Create a task instance from a template |
| `--close-task <id>` | Close task instance and save data |

## Action Execution

```bash
# Execute action without parameters
python main.py --task-id <id> --action <action_name>

# Execute action with JSON parameters
python main.py --task-id <id> --action <action_name> --action-params '{"key": "value"}'
```

## Common Actions

Platform actors typically support these actions:

- `create` - Navigate to target page
- `scroll_and_extract` - Scroll and extract data (params: `scroll_times`, `max`)
- `search` - Search for content (params: `query`)
- `close` - Save data and close task

## Resources

See [CLI Reference](references/cli_reference.md) for complete command documentation and examples.
