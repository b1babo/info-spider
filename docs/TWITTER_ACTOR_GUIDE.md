# Twitter Actor 使用指南

## 概述

Info-Spider 的 Twitter 数据抓取功能经过重构，现在提供了清晰明了的调用流程和统一的接口。

## Actor 类型

### 1. TwitterUserActor（用户主页 Actor）
专门用于抓取用户主页数据，包括推文和文章。

### 2. TwitterTweetActor（单条推文 Actor）
专门处理单条推文 URL，自动判断是推文还是文章。

## TwitterUserActor 调用流程

### 清晰的四步流程

#### 1. `create` - 创建任务并导航到主页
```yaml
- action: "create"
  params:
    url: "https://x.com/GitHub_Daily"
```
**功能**: 导航到用户主页（如 `https://x.com/GitHub_Daily`）

#### 2. `fetch_tweets` - 导航到帖子列表页面
```yaml
- action: "fetch_tweets"
```
**功能**: 导航到 `/with_replies` 页面，准备抓取推文

#### 3. `scroll_and_extract` - 滚动并提取内容
```yaml
- action: "scroll_and_extract"
  params:
    scroll_times: 20
    max: 100
    time_range: 48
```
**功能**: 滚动当前页面并提取数据
- 自动判断当前页面类型（推文页面或文章页面）
- **立即保存数据**并返回存储路径和统计数据
- 可多次调用，每次都会保存当前收集的数据

#### 4. `close` - 关闭任务
```yaml
- action: "close"
```
**功能**: 彻底关闭任务并关闭页面
- 只负责关闭页面，不保存数据（数据已在 `scroll_and_extract` 中保存）
- 释放浏览器资源

## 完整使用示例

### 示例1: 仅抓取用户推文
```yaml
- name: "user_tweets_only"
  url: "https://x.com/GitHub_Daily"
  actor: "twitter_user_actor"
  use_profile: "twitter"
  enable: true
  actions:
    - action: "create"
      params:
        url: "https://x.com/GitHub_Daily"
    - action: "fetch_tweets"
    - action: "scroll_and_extract"
      params:
        scroll_times: 20
        max: 100
        time_range: 48
    - action: "close"
```

### 示例2: 仅抓取用户文章
```yaml
- name: "user_articles_only"
  url: "https://x.com/heynavtoor"
  actor: "twitter_user_actor"
  use_profile: "twitter"
  enable: true
  actions:
    - action: "create"
      params:
        url: "https://x.com/heynavtoor"
    - action: "fetch_articles"
    - action: "scroll_and_extract"
      params:
        scroll_times: 30
        max: 20
        time_range: 720
        fetch_body: true
    - action: "close"
```

### 示例3: 同时抓取推文和文章
```yaml
- name: "user_complete_data"
  url: "https://x.com/GitHub_Daily"
  actor: "twitter_user_actor"
  use_profile: "twitter"
  enable: true
  actions:
    # 推文抓取
    - action: "create"
      params:
        url: "https://x.com/GitHub_Daily"
    - action: "fetch_tweets"
    - action: "scroll_and_extract"
      params:
        scroll_times: 20
        max: 100
        time_range: 48
    
    # 文章抓取
    - action: "fetch_articles"
    - action: "scroll_and_extract"
      params:
        scroll_times: 10
        max: 10
        time_range: 720
        fetch_body: true
    
    # 关闭任务
    - action: "close"
```

## TwitterTweetActor 使用

### 单条推文处理
```yaml
- name: "single_tweet"
  actor: "twitter_tweet_actor"
  use_profile: "twitter"
  enable: true
  actions:
    - action: "visit"
      params:
        tweet_url: "https://x.com/user/status/123456789"
        extract_replies: true
        max_replies: 20
```

**特性**:
- 自动判断 URL 是推文还是文章
- 支持回复提取
- 无需预先配置 URL，完全通过参数传入

## Actions 参数说明

### `create`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 否 | - | 用户主页 URL |

### `fetch_tweets`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 否 | - | 用户主页 URL（可选，从当前页面推断） |

### `fetch_articles`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| url | string | 否 | - | 用户主页 URL（可选，从当前页面推断） |

### `scroll_and_extract`
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| scroll_times | integer | 否 | 10 | 滚动次数 |
| max | integer | 否 | 100 | 最大提取数量 |
| time_range | integer | 否 | 24 | 时间范围（小时） |
| reset | boolean | 否 | true | 是否重置已收集的数据 |
| fetch_body | boolean | 否 | true | 是否抓取完整正文（仅文章有效） |

### `close`
无需参数，保存数据并关闭页面。

## 返回数据格式

### `scroll_and_extract` 返回格式
```json
{
  "status": "success",
  "page_type": "tweets",  // 或 "articles"
  "total_collected": 50,
  "time_range_hours": 48,
  "saved_to": "/path/to/data.json",
  "storage_stats": {
    "added": 45,
    "skipped": 5
  }
}
```

### `close` 返回格式
```json
{
  "status": "success",
  "message": "Twitter actor 已彻底关闭",
  "resources_collected": 100
}
```

**注意**: `close` 不再返回存储信息，因为数据已经在 `scroll_and_extract` 中保存。

## 关键特性

### 1. 智能页面类型检测
`scroll_and_extract` 会自动判断当前页面类型：
- 检测 URL 是否包含 `/articles`
- 自动选择相应的响应拦截器
- 返回对应的统计数据

### 2. 数据去重和合并
- 自动按资源 ID 去重
- 支持累加模式（`reset: false`）
- 推文和文章数据统一存储

### 3. 统一的存储接口
- 所有数据通过 `TaskStorage` 保存
- 返回存储路径和统计信息
- 支持数据库合并

## 命令行使用示例

### 创建任务并抓取推文
```bash
# 创建任务实例
python main.py --create-task github_tweets

# 执行 actions
python main.py --task-id task_xxx --action create --action-params '{"url": "https://x.com/GitHub_Daily"}'
python main.py --task-id task_xxx --action fetch_tweets
python main.py --task-id task_xxx --action scroll_and_extract --action-params '{"scroll_times": 20, "max": 100}'
python main.py --task-id task_xxx --action close
```

### 单条推文处理
```bash
# 创建单条推文任务
python main.py --create-test single_tweet --actor twitter_tweet_actor

# 访问推文（自动判断类型）
python main.py --action visit --action-params '{"tweet_url": "https://x.com/user/status/123", "extract_replies": true}'
```

## 最佳实践

1. **使用完整流程**: 按照推荐的四步流程执行
2. **合理设置参数**: 根据需要调整 `scroll_times` 和 `max`
3. **注意时间范围**: 推文通常用 24-48h，文章可用 720h
4. **数据去重**: 系统会自动去重，无需担心重复数据
5. **资源管理**: 使用 `close` 彻底关闭任务，释放资源
6. **数据保存时机**: 数据在每次 `scroll_and_extract` 调用时立即保存，无需等到 `close`

## 重要说明

### 数据保存机制
- **数据保存时机**: 在 `scroll_and_extract` 中进行，每次调用都会保存当前收集的数据
- **多次调用支持**: 可以多次调用 `scroll_and_extract`，每次都会保存最新数据
- **累加模式**: 使用 `reset: false` 参数可以累加数据，避免重复抓取
- **close 的作用**: 只负责关闭页面，不涉及数据保存

## 故障排除

### 问题：未收集到数据
**可能原因**:
1. 账号在指定时间范围内没有发推
2. `time_range` 设置过小
3. 页面加载失败

**解决方案**:
- 增加 `time_range` 参数
- 检查账号是否活跃
- 查看日志信息

### 问题：文章抓取失败
**可能原因**:
1. 用户没有发布文章
2. 网络连接问题

**解决方案**:
- 确认用户确实有文章内容
- 检查浏览器连接状态
- 尝试增加 `scroll_times`

## 总结

重构后的 Twitter Actor 提供了：

1. **清晰的流程**: create → fetch → scroll_and_extract → close
2. **智能判断**: 自动识别页面类型和内容类型
3. **统一接口**: 推文和文章使用相同的调用方式
4. **完整数据**: 支持同时抓取用户的所有内容
5. **灵活配置**: 通过参数控制各种行为

这样的设计使得 Twitter 数据抓取变得更加简单和强大！
