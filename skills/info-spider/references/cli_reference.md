# Info-Spider CLI Reference

Complete command reference for the info-spider browser automation system.

## Command Syntax

```bash
python main.py [OPTIONS]
```

## Options

### Server Management

```bash
--server {start|stop|status}    # Server operation
--server-host HOST              # Server address (default: 127.0.0.1)
--server-port PORT              # Server port (default: 7666)
```

### Task Management

```bash
--list-templates                # List all task templates
--list-instances                # List active task instances
--list-actors                   # List available actors
--create-task TASK_NAME         # Create task from template
--close-task TASK_ID            # Close task instance
```

### Action Execution

```bash
--task-id TASK_ID               # Task instance ID
--action ACTION_NAME            # Action to execute
--action-params JSON            # Action parameters (JSON string)
```

### Storage

```bash
--stats [TASK_NAME]             # Show task statistics
--query TASK_NAME               # Query task data
```

## Usage Examples

### Complete Workflow

```bash
# 1. Start server
python main.py --server start

# 2. View available templates
python main.py --list-templates

# 3. Create a task instance
python main.py --create-task github_tweets
# Output: task_id: task_abc123

# 4. Execute actions
python main.py --task-id task_abc123 --action create
python main.py --task-id task_abc123 --action scroll_and_extract \
  --action-params '{"scroll_times": 20, "max": 100}'

# 5. Close and save
python main.py --close-task task_abc123

# 6. Stop server
python main.py --server stop
```

### Platform-Specific Examples

**Twitter/X User Scraper:**
```bash
python main.py --create-task github_tweets
python main.py --task-id <id> --action create
python main.py --task-id <id> --action scroll_and_extract --action-params '{"max": 50}'
```

**Reddit Community:**
```bash
python main.py --create-task python_reddit
python main.py --task-id <id> --action create
python main.py --task-id <id> --action extract_posts
```

**Product Hunt:**
```bash
python main.py --create-task daily_hunt
python main.py --task-id <id> --action create
python main.py --task-id <id> --action extract_posts --action-params '{"max": 30}'
```

**Google Trends:**
```bash
python main.py --create-task ai_trends
python main.py --task-id <id> --action create
python main.py --task-id <id> --action extract_trends
```

## Server Output

### Start Server
```
INFO:正在启动Actor服务器: http://127.0.0.1:7666
INFO:API文档将提供在: http://127.0.0.1:7666/docs
```

### Server Status
```
✓ 服务器运行中: http://127.0.0.1:7666
  活跃的任务 (2):
    - task_abc123: github_tweets (running)
    - task_def456: python_reddit (running)
```

## Task Instance Output

### Create Task
```
Task实例创建成功!
  task_id: task_abc123
  task_name: github_tweets
  actor: TwitterUserActor

下一步执行 create action:
  python main.py --task-id task_abc123 --action create
```

### Execute Action
```
执行action: scroll_and_extract
执行成功
  Status: success
  Count: 50

完整结果:
{
  "status": "success",
  "count": 50,
  "resources": [...]
}
```

### Close Task
```
Task实例已关闭!
  task_id: task_abc123

保存统计:
  total: 50
  added: 45
  skipped: 5
  errors: 0
  保存到: /path/to/data/github_tweets_20250422.json
```

## Common Action Parameters

| Action | Parameters | Description |
|--------|------------|-------------|
| `create` | `url` | Target URL to navigate |
| `scroll_and_extract` | `scroll_times`, `max` | Scroll count and max items |
| `search` | `query`, `max` | Search query and max results |
| `extract_posts` | `max` | Maximum posts to extract |
