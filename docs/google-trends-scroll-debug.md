# Google Trends 滚动调试记录

## 问题描述

在 Google Trends Actor 中，需要滚动页面以加载所有下载按钮（Interest Over Time、Top Queries、Rising Queries 等）。但代码自动滚动时，页面没有移动，导致只能找到 1 个按钮。

## 尝试过的滚动方法

### 1. mouse.wheel() 方法 ❌

```python
for i in range(20):
    await task.page.mouse.wheel(0, 500)
    await asyncio.sleep(0.3)
```

**结果**：失败，页面没有滚动

**原因**：
- 鼠标滚轮方法可能需要页面有焦点才能生效
- 在 Google Trends 这种单页应用中，鼠标事件可能被拦截或不生效

---

### 2. JavaScript window.scrollTo() 方法 ❌

```python
await task.page.evaluate(f"window.scrollTo({{top: {distance}, behavior: 'smooth'}})")
# 或
await task.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
```

**结果**：失败，页面没有滚动

**原因**：
- Google Trends 使用了自定义滚动容器，不是标准的 window 滚动
- 主内容区域可能在特定的 DIV 元素内，而不是 document.body

---

### 3. scrollTop 直接设置 ❌

```python
await task.page.evaluate("document.body.scrollTop = 10000")
await task.page.evaluate("document.documentElement.scrollTop = 10000")
```

**结果**：失败，页面没有滚动

**原因**：
- 同上，页面使用了自定义滚动容器
- 直接设置 scrollTop 属性对当前页面结构无效

---

### 4. 查找主容器滚动 ❌

```python
await task.page.evaluate("""
    const main = document.querySelector('[role="main"]') ||
                 document.querySelector('main') ||
                 document.body;
    if(main) { main.scrollTop = main.scrollHeight; }
""")
```

**结果**：失败，页面没有滚动

**原因**：
- 即使找到了主容器，直接设置 scrollTop 可能不触发懒加载
- Google Trends 可能监听的是滚动事件而不是位置变化

---

### 5. PageDown 键 ❌

```python
for i in range(5):
    await task.page.keyboard.press("PageDown")
    await asyncio.sleep(0.5)
```

**结果**：失败，只找到 1 个按钮

**原因**：
- 页面没有焦点，键盘事件没有被正确接收
- 需要先让页面获得焦点，键盘操作才能生效

---

### 6. 检查可滚动元素 ⚠️

```python
scrollable_elements = await task.page.evaluate("""
    () => {
        const allElements = document.querySelectorAll('*');
        const scrollableElements = [];
        allElements.forEach(el => {
            if (el.scrollHeight > el.clientHeight) {
                scrollableElements.push({...});
            }
        });
        return scrollableElements;
    }
""")
```

**结果**：找到 118 个可滚动元素，但无法确定哪个是正确的

**原因**：
- 页面结构复杂，有多个可滚动元素
- 难以确定应该滚动哪个元素来触发懒加载

---

### 7. End 键 + 获取焦点 ✅

```python
# 先点击页面主体获取焦点
await task.page.click("body")
await asyncio.sleep(0.5)

# 使用 End 键滚动到底部
await task.page.keyboard.press("End")
await asyncio.sleep(2)
await task.page.keyboard.press("End")
await asyncio.sleep(2)
```

**结果**：成功！找到 3 个按钮，下载 151 条数据

**原因**：
- **关键步骤**：先点击 `body` 让页面获得焦点
- 使用 `End` 键是真实的用户操作，会触发浏览器的原生滚动行为
- 原生滚动会正确触发页面的懒加载机制
- Google Trends 监听的是真实的用户滚动事件

## 最终解决方案

```python
async def _click_download_button(self, task, keyword: str) -> Dict[str, Any]:
    """查找并点击所有下载按钮"""
    # ... 省略其他代码 ...

    # 滚动页面以加载所有内容
    logger.info("Scrolling to load all content...")

    # 关键：先点击页面主体获取焦点
    await task.page.click("body")
    await asyncio.sleep(0.5)

    # 使用 End 键滚动到底部（触发懒加载）
    await task.page.keyboard.press("End")
    await asyncio.sleep(2)
    await task.page.keyboard.press("End")
    await asyncio.sleep(2)

    # 可选：回到顶部
    await task.page.keyboard.press("Home")
    await asyncio.sleep(2)
```

## 经验总结

1. **焦点很重要**：在模拟键盘/鼠标操作前，确保页面或元素已获得焦点
2. **优先模拟真实用户操作**：`End`/`Home` 键比 JavaScript 滚动更可靠
3. **单页应用的特性**：现代 SPA 应用可能拦截或重写标准滚动行为
4. **懒加载触发**：某些内容的加载需要真实的滚动事件，而不是简单的位置变化
5. **等待时间**：滚动后需要给页面足够时间加载新内容（2-3秒）

## 测试结果

| 方法 | 按钮数量 | 数据条数 | 状态 |
|------|---------|---------|------|
| 无滚动 | 1 | 51 | ❌ |
| mouse.wheel() | 1 | 51 | ❌ |
| window.scrollTo() | 1 | 51 | ❌ |
| PageDown (无焦点) | 1 | 51 | ❌ |
| **End + 获取焦点** | **3** | **151** | ✅ |

## 下载的数据类型

使用正确的滚动方法后，成功下载：

1. **Interest Over Time** - 时间趋势数据（51条）
2. **Top Queries** - 热门查询（50条）
3. **Rising Queries** - 上升查询（50条）
