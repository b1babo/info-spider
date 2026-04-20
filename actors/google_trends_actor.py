"""
Google Trends Actor - 通过下载按钮获取CSV数据
"""
import logging
import json
import asyncio
import urllib.parse
import csv
from typing import List, Dict, Any
from playwright.async_api import Response
from datetime import datetime, timedelta
from pathlib import Path

from core.base_actor import BaseActor
from core.models import Resource, Analytics
from core import utils

logger = logging.getLogger(__name__)


class GoogleTrendsActor(BaseActor):
    """Google Trends Actor - 通过下载按钮获取CSV数据"""

    actor_name = "google_trends_actor"
    actor_description = "Google Trends趋势分析Actor（下载CSV）"

    def setup_actions(self):
        """注册所有Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="创建任务（导航到页面）",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True}
                ]
            }
        )

        self.register_action(
            "search_trends",
            self.action_search_trends,
            description="搜索关键词趋势并下载CSV",
            params_schema={
                "params": [
                    {"name": "keyword", "type": "string", "required": True},
                    {"name": "time_range", "type": "string", "required": False, "default": "today 12-m"},
                    {"name": "geo", "type": "string", "required": False, "default": ""}
                ]
            }
        )

        self.register_action(
            "extract_trends",
            self.action_extract_trends,
            description="提取已收集的趋势数据",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 100}
                ]
            }
        )

        self.register_action(
            "status",
            self.action_status,
            description="获取状态",
            params_schema={"params": []}
        )

        self.register_action(
            "close",
            self.action_close,
            description="关闭任务",
            params_schema={"params": []}
        )

        self.register_action(
            "compare_keywords",
            self.action_compare_keywords,
            description="比较多个关键词的趋势（最多5个）",
            params_schema={
                "params": [
                    {"name": "keywords", "type": "array", "required": True},
                    {"name": "time_range", "type": "string", "required": False, "default": "today 12-m"},
                    {"name": "geo", "type": "string", "required": False, "default": ""}
                ]
            }
        )

        self.register_action(
            "regional_interest",
            self.action_regional_interest,
            description="获取关键词的地区分布数据",
            params_schema={
                "params": [
                    {"name": "keyword", "type": "string", "required": True},
                    {"name": "geo", "type": "string", "required": False, "default": "US"},
                    {"name": "time_range", "type": "string", "required": False, "default": "today 12-m"}
                ]
            }
        )

        # 状态变量
        self.resources: List[Resource] = []
        self.trend_data = {}
        self.downloaded_files = []

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务 - 导航到 Google Trends 探索页面"""
        # 始终先进入探索页面，不带任何参数
        url = "https://trends.google.com/explore"

        try:
            logger.info(f"Navigating to Google Trends explore page: {url}")
            await task.page.goto(url, timeout=60000)
            await asyncio.sleep(3)

            title = await task.page.title()
            current_url = task.page.url

            logger.info(f"Page loaded: {title}")

            return {
                "status": "success",
                "url": current_url,
                "title": title
            }
        except Exception as e:
            logger.error(f"Create task failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def action_search_trends(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """搜索关键词趋势 - 通过 URL 直接访问"""
        keyword = action_params.get('keyword', '')
        time_range = action_params.get('time_range', 'today 12-m')
        geo = action_params.get('geo', '')

        if not keyword:
            return {"status": "error", "message": "keyword is required"}

        logger.info(f"Searching trends for: {keyword}")
        self.trend_data = {}

        # 创建下载目录（使用任务专属目录）
        download_dir = task.get_data_dir()
        download_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Download directory: {download_dir}")

        try:
            # 构造搜索 URL 并导航（使用新版 URL）
            encoded_keyword = urllib.parse.quote(keyword)
            trends_url = f"https://trends.google.com/explore?q={encoded_keyword}&date={time_range}"
            if geo:
                trends_url += f"&geo={geo}"

            logger.info(f"Navigating to: {trends_url}")
            await task.page.goto(trends_url, timeout=60000)
            await asyncio.sleep(5)

            # 点击下载按钮获取数据
            result = await self._click_download_button(task, keyword, download_dir)

            return result

        except Exception as e:
            logger.error(f"Search trends failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "keyword": keyword
            }

    async def action_compare_keywords(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """比较多个关键词的趋势"""
        keywords = action_params.get('keywords', [])
        time_range = action_params.get('time_range', 'today 12-m')
        geo = action_params.get('geo', '')

        if not keywords:
            return {"status": "error", "message": "keywords is required"}

        if len(keywords) > 5:
            return {"status": "error", "message": "Maximum 5 keywords allowed"}

        if len(keywords) < 2:
            return {"status": "error", "message": "At least 2 keywords required for comparison"}

        logger.info(f"Comparing keywords: {keywords}")
        self.trend_data = {}

        # 创建下载目录
        download_dir = task.get_data_dir()
        download_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 构造比较 URL：多个关键词用逗号分隔
            encoded_keywords = ','.join([urllib.parse.quote(kw) for kw in keywords])
            compare_url = f"https://trends.google.com/explore?date={time_range}&q={encoded_keywords}"
            if geo:
                compare_url += f"&geo={geo}"

            logger.info(f"Navigating to comparison URL: {compare_url}")
            await task.page.goto(compare_url, timeout=60000)
            await asyncio.sleep(5)

            # 点击下载按钮获取数据
            result = await self._click_download_button(task, f"compare_{'_'.join(keywords)}", download_dir)

            # 添加比较元数据
            result["keywords"] = keywords
            result["comparison_type"] = "multi_keyword"

            return result

        except Exception as e:
            logger.error(f"Compare keywords failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "keywords": keywords
            }

    async def action_regional_interest(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取关键词的地区分布数据"""
        keyword = action_params.get('keyword', '')
        geo = action_params.get('geo', 'US')
        time_range = action_params.get('time_range', 'today 12-m')

        if not keyword:
            return {"status": "error", "message": "keyword is required"}

        logger.info(f"Getting regional interest for: {keyword} in {geo}")
        self.trend_data = {}

        # 创建下载目录
        download_dir = task.get_data_dir()
        download_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 构造 URL 并导航
            encoded_keyword = urllib.parse.quote(keyword)
            trends_url = f"https://trends.google.com/explore?geo={geo}&date={time_range}&q={encoded_keyword}"

            logger.info(f"Navigating to: {trends_url}")
            await task.page.goto(trends_url, timeout=60000)
            await asyncio.sleep(5)

            # 尝试切换到地区分布视图
            # Google Trends 可能需要点击 "Regional interest" 或相关标签
            try:
                # 查找地区相关的下载按钮
                regional_button = await task.page.query_selector('button[aria-label*="regional" i][aria-label*="CSV" i]')
                if regional_button:
                    logger.info("Found regional download button")
                    await regional_button.scroll_into_view_if_needed()
                    await asyncio.sleep(1)

                    async with task.page.expect_download(timeout=30000) as download_info:
                        await regional_button.click()

                    download = await download_info.value
                    suggested_filename = download.suggested_filename
                    download_url = download.url
                    csv_file = download_dir / suggested_filename

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

                    import base64
                    content = base64.b64decode(base64_data.split(",")[1])
                    with open(str(csv_file), "wb") as f:
                        f.write(content)

                    logger.info(f"Regional data saved: {csv_file}")

                    # 解析地区数据
                    regional_data = self._parse_regional_csv(str(csv_file))
                    self.trend_data["regional"] = regional_data

                    return {
                        "status": "success",
                        "keyword": keyword,
                        "geo": geo,
                        "regional_data": regional_data,
                        "csv_file": str(csv_file)
                    }
            except Exception as e:
                logger.warning(f"Regional download button not found or failed: {e}")

            # 如果没有专门的地区下载按钮，返回通用数据
            result = await self._click_download_button(task, keyword, download_dir)
            result["regional_note"] = "Regional-specific data not available, returned general data"
            return result

        except Exception as e:
            logger.error(f"Regional interest failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "keyword": keyword,
                "geo": geo
            }

    async def _click_download_button(self, task, keyword: str, download_dir: Path) -> Dict[str, Any]:
        """查找并点击所有下载按钮 - 使用 aria-label 定位"""
        # 定义要下载的按钮类型
        download_types = [
            ("interest_over_time", '[aria-label="Download interest over time CSV"]', "Interest Over Time"),
            ("top_queries", '[aria-label="Download top queries CSV"]', "Top Queries"),
            ("rising_queries", '[aria-label="Download rising queries CSV"]', "Rising Queries"),
            ("related_topics", '[aria-label="Download related topics CSV"]', "Related Topics"),
            ("related_queries", '[aria-label="Download related queries CSV"]', "Related Queries"),
        ]

        downloaded_files = {}
        self.trend_data = {}

        try:
            # 等待页面完全加载
            await asyncio.sleep(3)

            # 滚动页面以加载所有内容
            logger.info("Scrolling to load all content...")

            # 先点击页面主体获取焦点
            try:
                await task.page.click("body")
                await asyncio.sleep(0.5)
            except:
                pass

            # 模拟真实用户滚动：使用 End 键滚动到底部
            await task.page.keyboard.press("End")
            await asyncio.sleep(2)
            await task.page.keyboard.press("End")
            await asyncio.sleep(2)

            # 再用 Home 回到顶部
            await task.page.keyboard.press("Home")
            await asyncio.sleep(2)

            await asyncio.sleep(2)

            # 调试：打印页面上所有按钮的信息
            logger.info("Debug: Checking all buttons on page...")
            all_buttons = await task.page.locator("button").all()
            logger.info(f"Total buttons found: {len(all_buttons)}")

            for i, btn in enumerate(all_buttons[:30]):  # 只看前30个
                try:
                    aria_label = await btn.get_attribute("aria-label")
                    if aria_label and ("download" in aria_label.lower() or "export" in aria_label.lower() or "csv" in aria_label.lower()):
                        logger.info(f"  Button {i+1}: aria-label='{aria_label}'")
                except:
                    pass

            # 先检查页面上有哪些可用的下载按钮
            logger.info("Scanning for available download buttons...")
            available_buttons = []
            all_download_buttons = await task.page.locator('button[aria-label*="Download" i][aria-label*="CSV" i]').all()
            for btn in all_download_buttons:
                try:
                    if await btn.is_visible():
                        aria_label = await btn.get_attribute("aria-label")
                        available_buttons.append(aria_label)
                        logger.info(f"  Found: {aria_label}")
                except:
                    pass

            if not available_buttons:
                logger.warning("No download buttons found on page")
                return {
                    "status": "error",
                    "message": "No download buttons found",
                    "keyword": keyword
                }

            logger.info(f"Total available download buttons: {len(available_buttons)}")

            # 遍历每种下载类型
            for data_type, selector, label in download_types:
                logger.info(f"Looking for {label} button...")

                try:
                    # 等待按钮出现（减少超时时间到 3 秒）
                    await task.page.wait_for_selector(selector, state="visible", timeout=3000)
                except:
                    logger.debug(f"{label} button not found (timeout)")
                    continue

                # 查找按钮
                button = await task.page.query_selector(selector)
                if not button:
                    logger.warning(f"{label} button query returned None, skipping...")
                    continue

                try:
                    await button.scroll_into_view_if_needed()
                    await asyncio.sleep(2)

                    # 下载文件
                    async with task.page.expect_download(timeout=30000) as download_info:
                        await button.click()

                    download = await download_info.value
                    suggested_filename = download.suggested_filename
                    download_url = download.url
                    logger.info(f"[{label}] Download started: {suggested_filename} {download_url}")
                    csv_file = download_dir / suggested_filename


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

                    # 解码并保存
                    import base64
                    content = base64.b64decode(base64_data.split(",")[1])
                    with open(str(csv_file), "wb") as f:
                        f.write(content)


                    # 保存文件
                    
                    # await download.save_as(str(csv_file))
                    logger.info(f"[{label}] CSV file saved: {csv_file}")

                    downloaded_files[data_type] = str(csv_file)
                    await asyncio.sleep(2)

                except Exception as e:
                    logger.error(f"[{label}] Failed to download: {e}")
                    continue

            # 如果没有下载任何文件，进行调试
            if not downloaded_files:
                logger.warning("No files downloaded, checking available buttons on page...")
                # 调试：查找所有包含 "Download" 的 aria-label 按钮
                all_buttons = await task.page.locator('button[aria-label*="Download"]').all()
                logger.info(f"Found {len(all_buttons)} buttons with 'Download' in aria-label")
                for i, btn in enumerate(all_buttons[:20]):
                    try:
                        aria_label = await btn.get_attribute("aria-label")
                        logger.info(f"  Button {i+1}: aria-label='{aria_label}'")
                    except:
                        pass

                return {
                    "status": "error",
                    "message": "No files downloaded",
                    "keyword": keyword
                }

            # 解析所有下载的文件
            total_entries = 0
            for data_type, csv_path in downloaded_files.items():
                try:
                    if data_type == "interest_over_time":
                        csv_data = self._parse_timeline_csv(csv_path)
                        if csv_data:
                            self.trend_data["timeline"] = csv_data
                            total_entries += len(csv_data)
                            logger.info(f"Parsed {len(csv_data)} timeline entries")
                    elif data_type in ("top_queries", "rising_queries"):
                        csv_data = self._parse_queries_csv(csv_path)
                        if csv_data:
                            self.trend_data[data_type] = csv_data
                            total_entries += len(csv_data)
                            logger.info(f"Parsed {len(csv_data)} {data_type}")
                    elif data_type in ("related_topics", "related_queries"):
                        csv_data = self._parse_queries_csv(csv_path)
                        if csv_data:
                            self.trend_data[data_type] = csv_data
                            total_entries += len(csv_data)
                            logger.info(f"Parsed {len(csv_data)} {data_type}")
                except Exception as e:
                    logger.error(f"Failed to parse {data_type}: {e}")

            # 保留下载的 CSV 文件到任务目录
            logger.info(f"Downloaded CSV files saved to: {download_dir}")

            # 构建资源对象
            resource = self._build_trend_resource(keyword, "today 12-m", "")
            if resource:
                self.resources.append(resource)

            return {
                "status": "success",
                "keyword": keyword,
                "has_data": True,
                "entries": total_entries,
                "downloaded_types": list(downloaded_files.keys()),
                "total_collected": len(self.resources)
            }

        except Exception as e:
            logger.error(f"Click download button failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "keyword": keyword
            }

    def _parse_timeline_csv(self, csv_path: str) -> list:
        """解析Google Trends CSV文件 - Interest Over Time格式"""
        timeline_data = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                lines = [line for line in csv.reader(f)]

            # Google Trends CSV 格式:
            # 第1行: 类别 (如 "Interest over time")
            # 第2行: 空行
            # 第3行: 列标题 (Week, Category: AI, ...)
            # 第4行开始: 数据

            if len(lines) < 4:
                logger.warning(f"CSV file too short: {len(lines)} lines")
                return []

            # 从第3行开始是数据，跳过最后空行
            data_lines = lines[2:-1] if len(lines) > 3 else []

            for row in data_lines:
                if len(row) >= 2:
                    try:
                        time_str = row[0].strip()
                        val_str = row[1].strip()

                        # 处理值（可能是 <1 或数字）
                        if val_str.startswith('<'):
                            val = 0  # 处理 "<1" 的情况
                        else:
                            val = int(val_str.replace(',', '').strip())

                        timeline_data.append({
                            "time": time_str,
                            "formattedTime": time_str,
                            "value": [val],
                            "formattedValue": [val_str]
                        })
                    except ValueError:
                        continue
                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")
                        continue

            logger.info(f"Parsed {len(timeline_data)} timeline entries from CSV")
            return timeline_data

        except Exception as e:
            logger.error(f"Error parsing CSV: {e}", exc_info=True)
            return []

    def _parse_queries_csv(self, csv_path: str) -> list:
        """解析Google Trends CSV文件 - Top/Rising Queries格式"""
        queries_data = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                lines = [line for line in csv.reader(f)]

            # Google Trends Queries CSV 格式:
            # 第1行: 类别 (如 "Top queries" 或 "Rising queries")
            # 第2行: 列标题 (通常包含查询词和百分比等)
            # 第3行开始: 数据

            if len(lines) < 3:
                logger.warning(f"CSV file too short: {len(lines)} lines")
                return []

            # 找到数据起始行（跳过标题行）
            data_lines = lines[1:] if len(lines) > 2 else []

            for row in data_lines:
                if not row or len(row) < 1:
                    continue

                try:
                    # 第一列通常是查询词
                    query = row[0].strip()

                    # 第二列可能是搜索量百分比（如果有）
                    value = None
                    if len(row) >= 2 and row[1]:
                        val_str = row[1].strip()
                        try:
                            # 处理百分比格式 (如 "50%") 或数字
                            if val_str.endswith('%'):
                                value = int(val_str[:-1].strip())
                            else:
                                value = int(val_str.replace(',', '').strip())
                        except ValueError:
                            value = val_str  # 保留原始字符串

                    if query:
                        queries_data.append({
                            "query": query,
                            "value": value
                        })
                except Exception as e:
                    logger.debug(f"Error parsing row: {e}")
                    continue

            logger.info(f"Parsed {len(queries_data)} queries from CSV")
            return queries_data

        except Exception as e:
            logger.error(f"Error parsing queries CSV: {e}", exc_info=True)
            return []

    def _parse_regional_csv(self, csv_path: str) -> dict:
        """解析Google Trends地区分布CSV文件"""
        regional_data = {
            "country": [],
            "city": [],
            "metro": []
        }

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                lines = [line for line in csv.reader(f)]

            if len(lines) < 3:
                logger.warning(f"Regional CSV file too short: {len(lines)} lines")
                return regional_data

            # 跳过标题行，解析数据
            data_lines = lines[1:] if len(lines) > 2 else []

            for row in data_lines:
                if not row or len(row) < 2:
                    continue

                try:
                    region_name = row[0].strip()
                    value_str = row[1].strip()

                    if not region_name:
                        continue

                    # 解析值（可能是数字或百分比）
                    try:
                        if value_str.endswith('%'):
                            value = int(value_str[:-1].strip())
                        else:
                            value = int(value_str.replace(',', '').strip())
                    except ValueError:
                        value = 0

                    regional_data["country"].append({
                        "region": region_name,
                        "value": value
                    })
                except Exception as e:
                    logger.debug(f"Error parsing regional row: {e}")
                    continue

            # 按值排序
            for key in regional_data:
                regional_data[key].sort(key=lambda x: x["value"], reverse=True)

            logger.info(f"Parsed regional data: {len(regional_data['country'])} regions")
            return regional_data

        except Exception as e:
            logger.error(f"Error parsing regional CSV: {e}", exc_info=True)
            return regional_data

    def _build_trend_resource(self, keyword: str, time_range: str, geo: str) -> Resource:
        """构建趋势资源对象"""
        timeline = self.trend_data.get("timeline", [])
        top_queries = self.trend_data.get("top_queries", [])
        rising_queries = self.trend_data.get("rising_queries", [])

        timeline_values = []
        timeline_data_formatted = []

        for item in timeline[:100]:  # 限制100条
            try:
                time_str = item.get("formattedTime", "")
                val = item.get("value", [0])
                if isinstance(val, list) and len(val) > 0:
                    value = val[0]
                else:
                    value = int(val) if val else 0

                if value > 0:
                    timeline_values.append(value)
                    timeline_data_formatted.append({"time": time_str, "value": value})
            except:
                continue

        # 计算统计信息
        avg_value = sum(timeline_values) / len(timeline_values) if timeline_values else 0
        peak_value = max(timeline_values) if timeline_values else 0

        # 构建内容
        content = f"""# Google Trends Analysis

## Keyword: {keyword}

## Time Range: {time_range}
## Geo: {geo or 'Worldwide'}

## Trend Statistics
- Average Interest: {avg_value:.1f}
- Peak Interest: {peak_value}
- Data Points: {len(timeline_values)}

## Timeline Data (Recent 10)
{self._format_timeline(timeline_data_formatted[-10:] if len(timeline_data_formatted) > 10 else timeline_data_formatted)}

## Top Queries (Top 10)
{self._format_queries(top_queries[:10])}

## Rising Queries (Top 10)
{self._format_queries(rising_queries[:10])}
"""

        # 合并查询作为 hashtags
        hashtags = []
        for q in top_queries[:5]:
            if isinstance(q, dict) and "query" in q:
                hashtags.append(q["query"])
        for q in rising_queries[:5]:
            if isinstance(q, dict) and "query" in q:
                hashtags.append(q["query"])

        return Resource(
            id=f"gt_{keyword}_{time_range}",
            resource_url=f"https://trends.google.com/explore?q={keyword}&date={time_range}",
            resource_content=content,
            description=f"Google Trends for: {keyword}",
            resource_platform="Google Trends",
            resource_platform_url="https://trends.google.com",
            resource_author_name="Google Trends",
            analytics=Analytics(
                like_count=int(peak_value),
                view_count=int(avg_value)
            ),
            hashtags=hashtags
        )

    def _format_timeline(self, timeline: list) -> str:
        """格式化时间线数据"""
        if not timeline:
            return "No data"
        lines = [f"- {t['time']}: {t['value']}" for t in timeline]
        return "\n".join(lines)

    def _format_queries(self, queries: list) -> str:
        """格式化查询数据"""
        if not queries:
            return "No data"
        lines = []
        for q in queries[:10]:
            if isinstance(q, dict):
                query = q.get("query", "")
                value = q.get("value", "")
                if value:
                    lines.append(f"- {query}: {value}")
                else:
                    lines.append(f"- {query}")
        return "\n".join(lines) if lines else "No data"

    def _format_related_queries(self, queries: list) -> str:
        """格式化相关查询（保留用于向后兼容）"""
        return self._format_queries(queries)

    async def action_extract_trends(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取已收集的趋势数据"""
        max_items = action_params.get('max', 100)
        count = min(len(self.resources), max_items)

        result = {
            "status": "success",
            "total_collected": len(self.resources),
            "returned": count,
            "trends": []
        }

        for i, resource in enumerate(self.resources[:count]):
            result["trends"].append({
                "id": resource.id,
                "keyword": resource.description.split(": ")[-1] if resource.description else "",
                "content": resource.resource_content[:300],
                "url": resource.resource_url,
                "avg_interest": resource.analytics.view_count if resource.analytics else 0,
                "peak_interest": resource.analytics.like_count if resource.analytics else 0,
                "related_topics": resource.hashtags
            })

        # 保存数据
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            result["saved_to"] = str(raw_file)
            result["storage_stats"] = stats

        return result

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "resources_collected": len(self.resources)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务"""
        saved_path = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            logger.info(f"Data saved: added={stats['added']}, skipped={stats['skipped']}")
            saved_path = str(raw_file)

        # 保留下载的 CSV 文件
        logger.info(f"CSV files preserved in task directories under data/tasks/")

        return {
            "status": "success",
            "resources_collected": len(self.resources),
            "saved_to": saved_path
        }
