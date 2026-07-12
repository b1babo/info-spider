# Twitter Actor 统一规范

## 概述

所有 Twitter Actor 都遵循统一的设计模式和数据处理流程，确保一致性和可维护性。

## 统一的 Actor 行为规范

### 1. 数据保存时机

**原则**: 数据必须在 `scroll_and_extract` (或等效的主要数据提取 action) 中保存，**不能在 `close` 中保存**。

#### 正确模式：
```python
async def action_scroll_and_extract(self, task, action_params):
    # 1. 滚动并收集数据
    for i in range(scroll_times):
        await smart_scroll(task.page, 1, 3)
    
    # 2. 立即保存数据 ✅
    if self.resources:
        storage = TaskStorage()
        raw_file = storage.save_raw_result(task.task_config.name, self.resources)
        stats = storage.merge_to_database(task.task_config.name, self.resources)
        
        return {
            "status": "success",
            "saved_to": str(raw_file),
            "storage_stats": stats
        }

async def action_close(self, task, action_params):
    # 只关闭页面，不保存数据 ✅
    await task.page.close()
    return {"status": "success"}
```

#### 错误模式：
```python
async def action_close(self, task, action_params):
    # ❌ 不要在这里保存数据
    saved_path = await self._save_data(task)
    return {"saved_to": saved_path}
```

### 2. 统一的返回格式

所有主要数据提取 action 都应该返回统一的结构：

```python
{
    "status": "success",
    "page_type": "tweets|articles|home_timeline|trending",
    "total_collected": 100,
    "saved_to": "/path/to/data.json",
    "storage_stats": {
        "added": 95,
        "skipped": 5
    }
}
```

### 3. 内容类型检测

所有处理用户生成内容的 Actor 都应该能同时处理推文和文章：

#### TwitterUserActor
```python
# 自动检测当前页面类型
is_article_page = '/articles' in current_url
if is_article_page:
    return await self._scroll_and_extract_articles(...)
else:
    return await self._scroll_and_extract_tweets(...)
```

#### TwitterRandomReadingActor  
```python
# 首页推荐中可能同时出现推文和文章
def _extract_tweet_data(self, tweet_result):
    if 'article' in tweet_result:
        return self._extract_article_data(tweet_result)
    else:
        return self._extract_tweet_only_data(tweet_result)
```

#### TwitterTweetActor
```python
# 单条推文 URL 访问时自动判断类型
async def action_visit(self, task, params):
    # 检测 API 响应中的 'article' 字段
    if 'article' in api_response:
        return await self._extract_article(...)
    else:
        return await self._extract_tweet(...)
```

## 各 Actor 的标准模式

### TwitterUserActor
**主要 actions**:
- `create` - 导航到用户主页
- `fetch_tweets` - 导航到推文列表页面
- `fetch_articles` - 导航到文章列表页面  
- `scroll_and_extract` - 滚动并保存数据
- `close` - 关闭页面

**流程**: `create → fetch_tweets → scroll_and_extract → close`

### TwitterRandomReadingActor
**主要 actions**:
- `create` - 导航到首页
- `scroll_and_extract` - 滚动并保存数据（自动检测推文+文章）
- `close` - 关闭页面

**特性**: 首页推荐中可能同时包含推文和文章，自动处理两种类型

### TwitterTrendingActor
**主要 actions**:
- `create` - 导航到趋势页面
- `scroll_and_extract` - 滚动并保存数据
- `close` - 关闭页面

**特性**: 专注于趋势主题数据

### TwitterTweetActor
**主要 actions**:
- `visit` - 访问单条推文 URL，自动判断推文或文章

**特性**: 智能类型检测，单条推文处理

## 代码模式检查清单

### ✅ 必须具备的特征

- [ ] 数据在主要提取 action 中保存（不在 close 中）
- [ ] close 只关闭页面，不涉及数据保存
- [ ] 返回统一格式的统计信息
- [ ] 支持推文和文章（如果适用）
- [ ] 使用 TaskStorage 进行数据保存
- [ ] 提供清晰的日志信息

### ❌ 必须避免的模式

- [ ] 在 close 中保存数据
- [ ] 重复的保存逻辑
- [ ] 不一致的返回格式
- [ ] 忽略文章内容（如果应该处理）
- [ ] 缺少必要的日志

## 迁移指南

如果需要创建新的 Twitter Actor 或更新现有 Actor：

1. **数据处理**: 在主要提取 action 中进行数据保存
2. **资源清理**: close 只负责关闭页面
3. **类型支持**: 考虑是否需要支持推文和文章
4. **返回格式**: 使用统一的返回结构
5. **日志记录**: 添加清晰的日志，便于调试

## 示例：标准 Twitter Actor 结构

```python
class MyTwitterActor(BaseActor):
    def setup_actions(self):
        self.register_action("create", ...)
        self.register_action("scroll_and_extract", ...)
        self.register_action("close", ...)
    
    async def action_scroll_and_extract(self, task, params):
        # 1. 收集数据
        await self._collect_data(task, params)
        
        # 2. 保存数据（必须）
        if self.resources:
            storage = TaskStorage()
            raw_file = storage.save_raw_result(...)
            stats = storage.merge_to_database(...)
            
            return {
                "status": "success",
                "saved_to": str(raw_file),
                "storage_stats": stats
            }
    
    async def action_close(self, task, params):
        # 只关闭页面（不保存数据）
        await task.page.close()
        return {"status": "success"}
```

这种统一的模式确保了：
- 一致的用户体验
- 可预测的行为
- 易于维护和扩展
- 清晰的职责分离
