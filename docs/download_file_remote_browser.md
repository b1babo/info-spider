# 远程浏览器下载文件处理

## 问题

在远程浏览器模式下，Playwright 的 `download.save_as()` 方法会失效。

当浏览器运行在远程机器（如 Windows）而 Python 代码运行在本地（如 Linux）时，`download.save_as()` 尝试将文件保存到本地路径，但由于浏览器进程在远程机器上，文件实际下载在远程机器上，导致本地无法访问。

## 解决方案

使用 `download.url` 获取下载链接，然后通过浏览器上下文的 `fetch` API 获取文件内容，转换为 base64 传回本地保存。

## 代码示例

### GoogleTrendsActor 实现

```python
# 点击下载按钮并等待下载事件
async with task.page.expect_download(timeout=30000) as download_info:
    await button.click()

download = await download_info.value
suggested_filename = download.suggested_filename
download_url = download.url  # 获取下载 URL

# 使用浏览器 fetch API 获取文件内容（转为 base64）
base64_data = await task.page.evaluate(f"""
    async () => {{
        const response = await fetch("{download_url}");
        const blob = await response.blob();
        return new Promise((resolve) => {{
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.readAsDataURL(blob);
        }});
    }}
""")

# 解码并保存到本地
import base64
content = base64.b64decode(base64_data.split(",")[1])
with open(str(csv_file), "wb") as f:
    f.write(content)
```

## 原理

1. `download.url` 是浏览器可访问的内部 URL（通常是 `blob:` 或特殊协议）
2. `page.evaluate()` 在浏览器上下文中执行 JavaScript
3. `fetch()` 在浏览器中获取文件内容
4. `FileReader.readAsDataURL()` 将文件转为 base64 数据 URL
5. base64 字符串传回 Python 进程
6. 解码后保存到本地文件系统

## 注意事项

- **大文件**: 此方法会将整个文件加载到内存，不适合大文件（>100MB）
- **跨域**: 确保 download_url 可被浏览器 fetch（通常是内部 URL，无跨域问题）
- **编码**: base64 数据 URL 格式为 `data:xxx/xxx;base64,<content>`，需去掉前缀

## 替代方案

如果文件很大，可以考虑：
1. 在远程机器上运行 Python 代码（避免跨机器）
2. 使用共享网络目录
3. 通过其他方式（HTTP 服务、SCP）传输文件
