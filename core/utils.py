import asyncio
import random
import json
from typing import List, Dict, Callable, Optional, Generator, Union, TYPE_CHECKING
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 使用异步 API
if TYPE_CHECKING:
    from playwright.async_api import Page, Response, Route, BrowserContext
else:
    Page = None
    Response = None
    Route = None
    BrowserContext = None

class HumanUtils:
    """模拟人类行为工具集（全异步版本）"""

    @staticmethod
    async def random_sleep(min_s: float = 1.0, max_s: float = 3.0):
        """随机等待，避免操作过于规律"""
        await asyncio.sleep(random.uniform(min_s, max_s))

    @staticmethod
    async def smart_scroll(page, min_wait: int = 2, max_wait: int = 5):
        """
        拟人化滚动：
        1. 随机滚动距离
        2. 随机停顿
        """
        try:
            # 随机滚动 400px 到 800px
            scroll_y = random.randint(400, 800)
            await page.mouse.wheel(0, scroll_y)

            # 偶尔回滚一点点（模拟人眼漏看）
            if random.random() < 0.3:
                await HumanUtils.random_sleep(0.5, 1)
                await page.mouse.wheel(0, -random.randint(50, 150))

            await HumanUtils.random_sleep(min_wait, max_wait)
        except Exception:
            # 直接重新抛出原始异常，不添加额外消息
            raise

    @staticmethod
    async def is_at_bottom(page):
        return await page.evaluate('''
                () => {
                    return window.innerHeight + window.scrollY >= document.body.scrollHeight - 100;
                }
            ''')

class NetworkUtils:
    """网络层工具集：拦截、加速、抓包（异步版本）"""

    @staticmethod
    async def block_media(page):
        """
        屏蔽图片、字体、媒体文件，大幅提升加载速度
        """
        async def abort_route(route):
            # 只屏蔽资源类型的请求
            if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
                await route.abort()
            else:
                await route.continue_()

        # 拦截所有请求进行检查
        await page.route("**/*", abort_route)

    @staticmethod
    @asynccontextmanager
    async def capture_json(page, url_substring: str):
        """
        XHR/Fetch 数据捕获（异步版本）

        用法:
            async with NetworkUtils.capture_json(page, "UserByScreenName") as data_list:
                await page.reload()
            print(data_list)
        """
        captured_data = []

        async def handle_response(response):
            # 1. 检查 URL 是否包含关键词
            if url_substring in response.url:
                try:
                    # 2. 尝试解析 JSON
                    data = await response.json()
                    captured_data.append(data)
                except Exception:
                    # 忽略非 JSON 响应
                    pass

        # 注册监听器
        page.on("response", handle_response)

        try:
            yield captured_data
        finally:
            # 清理监听器
            page.remove_listener("response", handle_response)

class BrowserHelper:
    """浏览器生命周期管理（异步版本）"""

    @staticmethod
    async def connect_existing(p, port: int) -> Optional:
        """连接到已打开的浏览器"""
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
            # 获取当前活跃的上下文
            context = browser.contexts[0]
            # 新开一个标签页
            page = await context.new_page()

            # 统一设置视口大小
            await page.set_viewport_size({"width": 1280, "height": 800})

            return page
        except Exception as e:
            logger.error(f"连接浏览器失败: {e}")
            return None

# ===== 以下工具函数保持不变（不涉及浏览器操作） =====

def to_datetime(date_string):
    if not date_string :
        return None

    format_string = "%a %b %d %H:%M:%S %z %Y"
    datetime_object = datetime.strptime(date_string, format_string)
    return datetime_object


def json_to_file(file_name, data):
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def create_str_by_datetime():
    now = datetime.now()
    date_path_str = now.strftime("%Y-%m-%d-%H-%M")
    return date_path_str


def create_dir_by_datetime(data_dir, task_name: str = "default"):
    directory_to_create = Path(data_dir) / Path(task_name)
    try:
        directory_to_create.mkdir(parents=True, exist_ok=True)
        print(f"成功创建目录: {directory_to_create}")
        return directory_to_create
    except OSError as e:
        print(f"创建目录时出错: {e}")
        return None


def time_within(date_str, time_delta=24):
    current_time_utc = datetime.now(timezone.utc)
    ret = to_datetime(date_str)
    if not ret:
        return True
    else:
        day = timedelta(hours=time_delta)
        if current_time_utc - ret < day:
            return True
        else:
            return False


def convert_to_number(amount_str):
    """将包含"万"的字符串转换为数字"""
    amount_str = amount_str.strip().replace(',', '')

    if "万" in amount_str:
        numeric_part = amount_str.replace("万", "")
        try:
            value = float(numeric_part) * 10000
        except ValueError:
            print(f"无效的输入：{amount_str}")
            return 0
    else:
        try:
            value = float(amount_str)
        except ValueError:
            print(f"无效的输入：{amount_str}")
            return 0

    return int(value)


from urllib.parse import urlsplit, urlunsplit

def remove_query_params(url):
    """从URL中移除查询参数"""
    parsed_url = urlsplit(url)
    url_without_query = parsed_url._replace(query="")
    r = urlunsplit(url_without_query)
    return f"{r}"


if __name__ == "__main__":
    date_str = "Sat Dec 06 10:00:06 +0000 2025"
    print(time_within(date_str))
    print(convert_to_number("100万"))
