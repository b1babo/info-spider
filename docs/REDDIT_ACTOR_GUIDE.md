# Reddit Actor 使用指南

## 概述

Info-Spider 的 Reddit 数据抓取功能采用模块化设计，提供了清晰明了的调用流程和统一的接口。

## Actor 类型

### 1. RedditCommunityActor（社区帖子 Actor）
专门用于抓取 Reddit 社区（subreddit）的帖子列表，支持多级评论提取。

### 2. RedditPostActor（单个帖子 Actor）
专门处理单个 Reddit 帖子 URL，提取详细内容和评论。

## RedditCommunityActor 调用流程

### 清晰的三步流程

#### 1. `create` - 创建任务并导航到社区
```yaml
- action: "create"
  params:
    url: "https://www.reddit.com/r/programming/"
```
**功能**: 导航到指定 subreddit（如 `https://www.reddit.com/r/programming/`）

#### 2. `scroll_and_extract` - 滚动并提取帖子
```yaml
- action: "scroll_and_extract"
  params:
    scroll_times: 10
    max: 50
    max_comments_depth: 2
    max_comments_per_level: 3
```
**功能**: 滚动当前页面并提取帖子数据
- 提取帖子标题、内容、作者等信息
- 支持多级评论提取（可配置深度和数量）
- **立即保存数据**并返回存储路径和统计数据
- 可多次调用，每次都会保存当前收集的数据

#### 3. `close` - 关闭任务
```yaml
- action: "close"
```
**功能**: 彻底关闭任务并关闭页面
- 只负责关闭页面，不保存数据（数据已在 `scroll_and_extract` 中保存）
- 释放浏览器资源

## RedditPostActor 使用

### 单个帖子处理

#### 简洁的两步流程

##### 1. `visit` - 访问帖子并提取内容
```yaml
- action: "visit"
  params:
    post_url: "https://www.reddit.com/r/ClaudeAI/comments/1uts1ra/claude_code_turned_off_my_wifi_to_test_something/"
    extract_comments: true
    max_comments: 50
```
**功能**: 访问指定的 Reddit 帖子并提取内容
- 提取帖子标题、正文、作者等信息
- 可选提取评论（支持配置数量）
- **立即保存数据**并返回存储路径和统计数据

##### 2. `close` - 关闭任务
```yaml
- action: "close"
```
**功能**: 关闭任务并释放资源
- 数据已在 `visit` 中保存
- 关闭页面释放浏览器资源

## 完整使用示例

### 示例1: 抓取社区帖子列表
```yaml
- name: "reddit_programming"
  url: "https://www.reddit.com/r/programming/"
  actor: "reddit_community_actor"
  use_profile: "reddit"
  enable: true
  actions:
    - action: "create"
      params:
        url: "https://www.reddit.com/r/programming/"
    - action: "scroll_and_extract"
      params:
        scroll_times: 10
        max: 50
        max_comments_depth: 2
        max_comments_per_level: 3
    - action: "close"
```

### 示例2: 抓取单个帖子
```yaml
- name: "reddit_single_post"
  url: "https://www.reddit.com/placeholder"
  actor: "reddit_post_actor"
  use_profile: "reddit"
  enable: true
  actions:
    - action: "visit"
      params:
        post_url: "https://www.reddit.com/r/ClaudeAI/comments/1uts1ra/claude_code_turned_off_my_wifi_to_test_something/"
        extract_comments: true
        max_comments: 50
    - action: "close"
```

### 示例3: 不提取评论的帖子访问
```yaml
- name: "reddit_post_no_comments"
  actor: "reddit_post_actor"
  use_profile: "reddit"
  enable: true
  actions:
    - action: "visit"
      params:
        post_url: "https://www.reddit.com/r/Python/comments/abc123/python_3_13_released/"
        extract_comments: false
    - action: "close"
```

### 示例4: 累加模式抓取
```yaml
- name: "reddit_accumulate"
  url: "https://www.reddit.com/r/MachineLearning/"
  actor: "reddit_community_actor"
  use_profile: "reddit"
  enable: true
  actions:
    - action: "create"
      params:
        url: "https://www.reddit.com/r/MachineLearning/"
    # 第一次抓取
    - action: "scroll_and_extract"
      params:
        scroll_times: 5
        max: 20
        reset: true  # 重置已有数据
    # 继续累加抓取
    - action: "scroll_and_extract"
      params:
        scroll_times: 5
        max: 20
        reset: false  # 累加模式
    - action: "close"
```

## Actions 参数说明

### RedditCommunityActor Actions

#### `create`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 是 | - | Subreddit URL |

#### `scroll_and_extract`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| scroll_times | integer | 否 | 10 | 滚动次数 |
| max | integer | 否 | 50 | 最大提取帖子数量 |
| max_comments_depth | integer | 否 | 2 | 评论层级深度（1-3） |
| max_comments_per_level | integer | 否 | 3 | 每层最大评论数量 |
| reset | boolean | 否 | true | 是否重置已收集的数据 |

#### `status`
无需参数，返回当前收集状态。

#### `close`
无需参数，保存数据并关闭任务。

### RedditPostActor Actions

#### `visit`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| post_url | string | 是 | - | 帖子完整 URL |
| extract_comments | boolean | 否 | true | 是否提取评论 |
| max_comments | integer | 否 | 50 | 最大评论数量 |

#### `close`
无需参数，关闭任务并释放资源。

## 返回数据格式

### `scroll_and_extract` 返回格式（RedditCommunityActor）
```json
{
  "status": "success",
  "total_collected": 25,
  "scroll_times": 10,
  "saved_to": "/path/to/data/raw/reddit_community_20250112.json",
  "storage_stats": {
    "total": 25,
    "added": 20,
    "skipped": 5,
    "errors": 0
  }
}
```

### `visit` 返回格式（RedditPostActor）
```json
{
  "status": "success",
  "post": {
    "id": "1uts1ra",
    "title": "Claude Code turned off my WiFi to test something...",
    "content": "Full post content here...",
    "author": "username",
    "url": "https://www.reddit.com/r/ClaudeAI/comments/1uts1ra/...",
    "likes": 1234,
    "comments_count": 56,
    "created_at": "2025-01-10T15:30:00Z"
  },
  "extracted_comments_count": 50,
  "comments": [
    {
      "index": 0,
      "author": "commenter1",
      "content": "Comment text...",
      "score": 45
    }
  ],
  "saved_to": "/path/to/data/raw/single_reddit_post.json",
  "storage_stats": {
    "total": 1,
    "added": 1,
    "skipped": 0,
    "errors": 0
  }
}
```

### `status` 返回格式
```json
{
  "status": "success",
  "resources_collected": 25,
  "processed_ids": 25
}
```

### `close` 返回格式（RedditCommunityActor）
```json
{
  "status": "success",
  "message": "Reddit community actor 已彻底关闭",
  "resources_collected": 25
}
```

**注意**: `close` 不再返回存储信息，因为数据已经在 `scroll_and_extract` 中保存。

### `close` 返回格式（RedditPostActor）
```json
{
  "status": "success",
  "message": "Reddit post actor 已关闭",
  "resources_collected": 1,
  "saved_to": "/path/to/data/raw/single_reddit_post.json",
  "storage_stats": {
    "total": 1,
    "added": 1,
    "skipped": 0,
    "errors": 0
  }
}
```

**注意**: RedditPostActor 的 `close` 仍然返回存储信息，因为数据在 `visit` 中保存。

## 关键特性

### 1. 多级评论提取
RedditCommunityActor 支持递归提取评论：
- 可配置评论层级深度（`max_comments_depth`）
- 可配置每层评论数量（`max_comments_per_level`）
- 自动构建评论树结构

### 2. 数据去重和合并
- 自动按帖子 ID 去重
- 支持累加模式（`reset: false`）
- 避免重复抓取相同内容

### 3. 灵活的评论控制
- 可以选择是否提取评论（`extract_comments`）
- 可控制评论数量（`max_comments`）
- 支持只提取帖子内容而不提取评论

### 4. 统一的存储接口
- 所有数据通过 `TaskStorage` 保存
- 返回存储路径和统计信息
- 支持数据库合并

## 命令行使用示例

### 创建社区任务并抓取帖子
```bash
# 创建任务实例
python main.py --create-task reddit_programming

# 执行 actions
python main.py --task-id task_xxx --action create --action-params '{"url": "https://www.reddit.com/r/programming/"}'
python main.py --task-id task_xxx --action scroll_and_extract --action-params '{"scroll_times": 10, "max": 50}'
python main.py --task-id task_xxx --action close
```

### 单个帖子处理
```bash
# 创建单个帖子任务
python main.py --create-task my_reddit_post

# 访问帖子
python main.py --task-id task_xxx --action visit --action-params '{"post_url": "https://www.reddit.com/r/ClaudeAI/comments/1uts1ra/...", "extract_comments": true, "max_comments": 50}'

# 关闭任务
python main.py --task-id task_xxx --action close
```

### 查看任务状态
```bash
python main.py --task-id task_xxx --action status
```

## 最佳实践

1. **使用完整流程**: 按照推荐的三步/两步流程执行
2. **合理设置参数**:
   - 社区抓取：`scroll_times: 5-15`, `max: 20-100`
   - 评论深度：建议 `max_comments_depth: 2`（过深会影响性能）
   - 评论数量：建议 `max_comments_per_level: 3-5`
3. **注意数据量**: Reddit 帖子内容可能较长，注意存储空间
4. **数据去重**: 系统会自动去重，无需担心重复数据
5. **资源管理**: 使用 `close` 释放浏览器资源
6. **累加模式**: 使用 `reset: false` 可以分批抓取大量数据
7. **评论控制**: 不需要评论时设置 `extract_comments: false` 可以提高速度

## 数据保存机制

### RedditCommunityActor
- **数据保存时机**: 在 `scroll_and_extract` 中进行，每次调用都会保存当前收集的数据
- **多次调用支持**: 可以多次调用 `scroll_and_extract`，每次都会保存最新数据
- **累加模式**: 使用 `reset: false` 参数可以累加数据，避免重复抓取
- **close 的作用**: 只负责关闭页面，不涉及数据保存

### RedditPostActor
- **数据保存时机**: 在 `visit` 中立即保存
- **一次性操作**: 通常只需调用一次 `visit`
- **close 的作用**: 关闭任务释放资源（数据已保存）

## 故障排除

### 问题：未收集到帖子
**可能原因**:
1. Subreddit 在指定时间范围内没有新帖子
2. 页面加载失败
3. 网络连接问题

**解决方案**:
- 检查 subreddit 是否活跃
- 查看日志信息
- 确认浏览器连接状态
- 尝试增加 `scroll_times`

### 问题：评论提取失败
**可能原因**:
1. 帖子没有评论
2. 评论加载需要更多滚动
3. Reddit 页面结构变化

**解决方案**:
- 确认帖子确实有评论
- 增加 `max_comments` 参数
- 检查日志中的错误信息

### 问题：单个帖子访问失败
**可能原因**:
1. 帖子 URL 不正确
2. 帖子已被删除或设为私有
3. 网络连接问题

**解决方案**:
- 验证帖子 URL 格式
- 确认帖子可以正常访问
- 检查浏览器连接状态

## 架构设计

### 模块化设计
Reddit Actor 采用模块化设计，分离了不同场景的功能：

**RedditCommunityActor**:
- 专注于社区级别的批量抓取
- 支持多级评论提取
- 适合数据分析、趋势监控

**RedditPostActor**:
- 专注于单个帖子的深度提取
- 快速、轻量级
- 适合内容获取、评论分析

### 与 Twitter Actor 的对应关系

| 功能 | Twitter | Reddit |
|------|---------|---------|
| 用户/社区页面 | TwitterUserActor | RedditCommunityActor |
| 单条内容 | TwitterTweetActor | RedditPostActor |
| 滚动提取 | scroll_and_extract | scroll_and_extract |
| 访问单个 | visit | visit |

## 总结

重构后的 Reddit Actor 提供了：

1. **清晰的流程**: Community: create → scroll_and_extract → close | Post: visit → close
2. **模块化设计**: 社区抓取和单个帖子访问分离
3. **统一接口**: 与 Twitter Actor 保持一致的调用方式
4. **完整数据**: 支持帖子内容和多级评论提取
5. **灵活配置**: 通过参数控制各种行为
6. **数据去重**: 自动去重，支持累加模式

这样的设计使得 Reddit 数据抓取变得更加简单和强大！
