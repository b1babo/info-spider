"""
Bing Search Actor - Bing 搜索结果抓取

使用浏览器模式抓取 Bing 搜索结果，包括：
- 网页列表（URL、标题、摘要）
- 相关搜索
- 人们也在问

遵循标准的 create -> extract -> close 模式
"""
import logging
import asyncio
import hashlib
from typing import List, Dict, Any
from urllib.parse import urlencode, urlparse, parse_qs

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics

logger = logging.getLogger(__name__)


class BingSearchResult:
    """Bing 搜索结果数据类"""

    def __init__(
        self,
        url: str,
        title: str,
        snippet: str,
        rank: int = 0,
        display_url: str = ""
    ):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.rank = rank
        self.display_url = display_url or url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "snippet": self.snippet,
            "rank": self.rank,
            "display_url": self.display_url
        }


class RelatedSearch:
    """相关搜索数据类"""

    def __init__(
        self,
        query: str,
        display_text: str = "",
        rank: int = 0
    ):
        self.query = query
        self.display_text = display_text or query
        self.rank = rank

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "display_text": self.display_text,
            "rank": self.rank
        }


class PeopleAlsoAsk:
    """人们也在问数据类"""

    def __init__(
        self,
        question: str,
        rank: int = 0
    ):
        self.question = question
        self.rank = rank

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "rank": self.rank
        }


class BingSearchActor(BaseActor):
    """Bing 搜索 Actor - 搜索结果抓取"""

    actor_name = "bing_search_actor"
    actor_description = "Bing 搜索结果抓取（浏览器模式）"

    # Bing 搜索 URL
    SEARCH_URL = "https://www.bing.com/search"

    def setup_actions(self):
        """注册所有 Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="初始化任务并导航到搜索页面",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "Bing 搜索 URL"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动页面并提取搜索结果并保存到数据库",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10},
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
            description="关闭任务实例",
            params_schema={"params": []}
        )

        # 状态变量
        self.results: List[BingSearchResult] = []
        self.related_searches: List[RelatedSearch] = []
        self.people_also_ask: List[PeopleAlsoAsk] = []
        self.processed_urls = set()
        self.current_query = ""
        self.current_url = ""

    def _generate_result_id(self, url: str) -> str:
        """生成结果 ID"""
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
        return f"bs_{url_hash}"

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """初始化任务并导航到搜索页面"""
        url = action_params.get("url", "")

        if not url:
            return {"status": "error", "message": "url is required"}

        self.current_url = url

        # 从 URL 中提取查询参数
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            self.current_query = params.get("q", [""])[0]
        except:
            self.current_query = ""

        logger.info(f"[create] 导航到: {url}")
        logger.info(f"[create] 查询: {self.current_query}")

        await task.page.goto(url, timeout=60000)
        await asyncio.sleep(2)

        return {
            "status": "success",
            "message": "Bing Search actor initialized",
            "actor": self.actor_name,
            "url": task.page.url,
            "title": await task.page.title(),
            "query": self.current_query
        }

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取结果并保存到数据库"""
        scroll_times = action_params.get("scroll_times", 10)
        max_items = action_params.get("max", 100)

        logger.info(f"[scroll_and_extract] 滚动次数={scroll_times}, 最大={max_items}")

        # 清空之前的数据
        self.results = []
        self.related_searches = []
        self.people_also_ask = []
        self.processed_urls = set()

        for i in range(scroll_times):
            if len(self.results) >= max_items:
                logger.info(f"[scroll_and_extract] 已达到最大数量 {max_items}，停止")
                break

            logger.info(f"[scroll_and_extract] 第 {i + 1}/{scroll_times} 次滚动")

            # 滚动到底部
            await self._scroll_to_bottom(task)
            await asyncio.sleep(1)

            # 提取当前可见的结果
            results = await self._parse_search_results(task, max_items)
            for result in results:
                if result.url not in self.processed_urls:
                    self.results.append(result)
                    self.processed_urls.add(result.url)

            logger.info(f"[scroll_and_extract] 当前总数: {len(self.results)}")

            # 只在第一次提取相关搜索
            if i == 0:
                related = await self._parse_related_searches(task)
                for item in related:
                    if item.query not in {r.query for r in self.related_searches}:
                        self.related_searches.append(item)

                paa = await self._parse_people_also_ask(task)
                for item in paa:
                    if item.question not in {q.question for q in self.people_also_ask}:
                        self.people_also_ask.append(item)

        logger.info(f"[scroll_and_extract] 提取完成: 结果={len(self.results)}, 相关={len(self.related_searches)}, PAA={len(self.people_also_ask)}")

        # 保存数据到数据库
        saved_to = None
        stats = None

        if self.results or self.related_searches or self.people_also_ask:
            from core.task_storage import TaskStorage
            storage = TaskStorage()

            resources = self._results_to_resources()

            # 保存原始数据
            raw_file = storage.save_raw_result(task.task_config.name, resources)

            # 合并到数据库
            stats = storage.merge_to_database(task.task_config.name, resources)
            saved_to = str(raw_file)
            logger.info(f"[scroll_and_extract] 保存完成: added={stats['added']}, skipped={stats['skipped']}")

        return {
            "status": "success",
            "query": self.current_query,
            "scroll_times": scroll_times,
            "total_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask),
            "saved_to": saved_to,
            "storage_stats": stats
        }

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "actor": self.actor_name,
            "query": self.current_query,
            "results_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask),
            "processed_urls": len(self.processed_urls)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务实例"""
        logger.info(f"[close] 关闭 Bing Search actor")

        # 清空资源
        results_count = len(self.results)
        related_count = len(self.related_searches)
        paa_count = len(self.people_also_ask)

        self.results = []
        self.related_searches = []
        self.people_also_ask = []
        self.processed_urls = set()
        self.current_query = ""

        return {
            "status": "success",
            "message": "Bing Search actor closed",
            "results_collected": results_count,
            "related_searches": related_count,
            "people_also_ask": paa_count
        }

    async def _scroll_to_bottom(self, task):
        """滚动到页面底部"""
        await task.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    async def _parse_search_results(self, task, max_items: int = 100) -> List[BingSearchResult]:
        """解析搜索结果

        Bing 搜索结果结构（根据实际 HTML 分析）：
        - 主结果容器: <li class="b_algo">
        - 标题链接: <h2><a href="...">
        - 描述: <p class="b_lineclamp2"> 或 .b_caption p
        """
        results = []

        try:
            logger.info("[_parse_search_results] 开始解析搜索结果...")

            # Bing 主结果选择器
            elements = await task.page.locator("li.b_algo").all()
            logger.info(f"[_parse_search_results] 找到 {len(elements)} 个 b_algo 元素")

            for idx, element in enumerate(elements):
                if len(results) >= max_items:
                    break

                try:
                    # 提取标题和链接 - 直接子元素 h2 > a
                    title_elem = element.locator("h2 > a").first
                    if await title_elem.count() == 0:
                        # 尝试 h2 a（非直接子元素）
                        title_elem = element.locator("h2 a").first

                    if await title_elem.count() == 0:
                        continue

                    title = await title_elem.inner_text()
                    url = await title_elem.get_attribute("href")

                    if not url or not title:
                        continue

                    # 提取描述 - 优先使用 b_lineclamp2 类
                    snippet = ""
                    snippet_selectors = [
                        "p.b_lineclamp2",
                        ".b_caption p.b_lineclamp2",
                        ".b_caption p",
                        "p"
                    ]

                    for snippet_sel in snippet_selectors:
                        snippet_elem = element.locator(snippet_sel).first
                        if await snippet_elem.count() > 0:
                            snippet_text = await snippet_elem.inner_text()
                            if snippet_text and len(snippet_text.strip()) > 10:
                                snippet = snippet_text.strip()
                                break

                    # 清理数据
                    title = title.strip()

                    # 过滤无效结果
                    if not self._is_valid_result(url, title):
                        continue

                    result = BingSearchResult(
                        url=url,
                        title=title,
                        snippet=snippet,
                        rank=len(results) + 1
                    )
                    results.append(result)

                    logger.debug(f"  结果[{len(results)}]: {title[:50]}...")

                except Exception as e:
                    logger.debug(f"[_parse_search_results] 解析元素 {idx} 失败: {e}")
                    continue

            logger.info(f"[_parse_search_results] 解析了 {len(results)} 个搜索结果")

        except Exception as e:
            logger.error(f"[_parse_search_results] 解析错误: {e}")

        return results

    async def _parse_related_searches(self, task) -> List[RelatedSearch]:
        """解析相关搜索

        Bing 相关搜索结构（根据实际 HTML 分析）：
        - 容器: li.rslist, .b_rrsr .b_vList li
        - 链接: <a href="/search?q=...">
        - 文本: .b_suggestionText
        """
        results = []

        try:
            logger.info("[_parse_related_searches] 开始解析相关搜索...")

            # Bing 相关搜索选择器（按优先级）
            selectors = [
                "li.rslist a",
                ".b_rrsr .b_vList li a",
                "#brsv3.rsExplr .b_vList li a",
                ".b_suggestionText"
            ]

            for selector in selectors:
                try:
                    elements = await task.page.locator(selector).all()
                    logger.info(f"[_parse_related_searches] 选择器 '{selector}': 找到 {len(elements)} 个元素")

                    if not elements:
                        continue

                    for idx, element in enumerate(elements):
                        try:
                            # 如果选择的是 .b_suggestionText，需要获取父级 a 元素
                            if selector == ".b_suggestionText":
                                parent = element.locator("xpath=..")
                                if await parent.count() == 0:
                                    continue
                                text = await element.inner_text()
                                href = await parent.get_attribute("href")
                            else:
                                text = await element.inner_text()
                                href = await element.get_attribute("href")

                            if not text:
                                continue

                            # 清理 HTML 标签和多余空格
                            text = text.strip()

                            # 避免重复
                            if any(r.query == text for r in results):
                                continue

                            results.append(RelatedSearch(
                                query=text,
                                display_text=text,
                                rank=len(results) + 1
                            ))

                            logger.debug(f"  相关搜索[{len(results)}]: {text}")

                        except Exception as e:
                            logger.debug(f"[_parse_related_searches] 解析链接 {idx} 失败: {e}")
                            continue

                    if results:
                        break

                except Exception as e:
                    logger.debug(f"[_parse_related_searches] 选择器 '{selector}' 失败: {e}")
                    continue

            logger.info(f"[_parse_related_searches] 解析了 {len(results)} 个相关搜索")

        except Exception as e:
            logger.error(f"[_parse_related_searches] 错误: {e}")

        return results

    async def _parse_people_also_ask(self, task) -> List[PeopleAlsoAsk]:
        """解析人们也在问

        注意：Bing 可能没有此功能，此方法保留以保持与 Google Search Actor 的一致性。
        如果将来 Bing 添加了类似功能，可以在此添加选择器。
        """
        results = []

        try:
            logger.debug("[_parse_people_also_ask] Bing 可能没有此功能")

        except Exception as e:
            logger.debug(f"[_parse_people_also_ask] 错误: {e}")

        return results

    def _is_valid_result(self, url: str, title: str) -> bool:
        """验证结果是否有效"""
        # 过滤掉非网页结果
        skip_prefixes = [
            "javascript:",
            "mailto:",
            "tel:",
            "#",
            "/search",
            "bing.com"
        ]

        for prefix in skip_prefixes:
            if url.startswith(prefix):
                return False

        # 标题不能为空
        if not title or len(title) < 2:
            return False

        return True

    def _results_to_resources(self) -> List[Resource]:
        """将结果转换为 Resource 格式"""
        resources = []

        # 网页搜索结果
        for result in self.results:
            resource = Resource(
                id=self._generate_result_id(result.url),
                resource_type="web_result",
                resource_url=result.url,
                resource_content=result.snippet,
                description=result.title,
                resource_platform="Bing Search",
                resource_platform_url=self.current_url,
                resource_author_name="",
                resource_author_display_name="",
                resource_author_url="",
                analytics=Analytics(
                    view_count=0,
                    like_count=0,
                    reply_count=0
                )
            )
            resource.urls = [{"type": "search_result", "rank": result.rank, "url": result.url}]
            resources.append(resource)

        # 相关搜索结果
        for related in self.related_searches:
            from urllib.parse import urlencode
            search_url = f"{self.SEARCH_URL}?{urlencode({'q': related.query})}"

            resource = Resource(
                id=f"bs_rs_{hashlib.md5(related.query.encode('utf-8')).hexdigest()[:12]}",
                resource_type="related_search",
                resource_url=search_url,
                resource_content="",
                description=related.display_text,
                resource_platform="Bing Search",
                resource_platform_url=self.current_url,
                resource_author_name="",
                resource_author_display_name="",
                resource_author_url="",
                analytics=Analytics(
                    view_count=0,
                    like_count=0,
                    reply_count=0
                )
            )
            resource.urls = [{"type": "related_search", "rank": related.rank, "query": related.query}]
            resources.append(resource)

        # 人们也在问结果
        for paa in self.people_also_ask:
            from urllib.parse import urlencode
            search_url = f"{self.SEARCH_URL}?{urlencode({'q': paa.question})}"

            resource = Resource(
                id=f"bs_paa_{hashlib.md5(paa.question.encode('utf-8')).hexdigest()[:12]}",
                resource_type="people_also_ask",
                resource_url=search_url,
                resource_content="",
                description=paa.question,
                resource_platform="Bing Search",
                resource_platform_url=self.current_url,
                resource_author_name="",
                resource_author_display_name="",
                resource_author_url="",
                analytics=Analytics(
                    view_count=0,
                    like_count=0,
                    reply_count=0
                )
            )
            resource.urls = [{"type": "people_also_ask", "rank": paa.rank, "question": paa.question}]
            resources.append(resource)

        return resources
