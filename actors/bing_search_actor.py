"""
Bing Search Actor - Bing 搜索结果抓取

使用浏览器模式抓取 Bing 搜索结果，包括：
- 网页列表（URL、标题、摘要）
- 相关搜索
- 人们也在问
"""
import logging
import asyncio
import hashlib
from typing import List, Dict, Any
from urllib.parse import urlencode

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
            description="创建搜索任务",
            params_schema={
                "params": [
                    {"name": "query", "type": "string", "required": True, "description": "搜索关键词"},
                    {"name": "language", "type": "string", "required": False, "default": "en-us", "description": "语言代码"},
                    {"name": "count", "type": "integer", "required": False, "default": 10, "description": "每页结果数"}
                ]
            }
        )

        self.register_action(
            "extract_results",
            self.action_extract_results,
            description="提取当前页面的搜索结果",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 100, "description": "最大提取数量"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动页面并提取搜索结果",
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
            description="关闭任务并保存",
            params_schema={"params": []}
        )

        # 状态变量
        self.results: List[BingSearchResult] = []
        self.related_searches: List[RelatedSearch] = []
        self.people_also_ask: List[PeopleAlsoAsk] = []
        self.processed_urls = set()
        self.current_query = ""
        self.current_url = ""

    def _build_search_url(self, query: str, language: str = "en-us", count: int = 10) -> str:
        """构建搜索 URL"""
        params = {
            "q": query,
            "setlang": language,
            "count": count
        }
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _generate_result_id(self, url: str) -> str:
        """生成结果 ID"""
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
        return f"bs_{url_hash}"

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建搜索任务"""
        query = action_params.get("query", "")
        language = action_params.get("language", "en-us")
        count = action_params.get("count", 10)

        if not query:
            return {"status": "error", "message": "query is required"}

        self.current_query = query
        search_url = self._build_search_url(query, language, count)
        self.current_url = search_url

        logger.info(f"Searching Bing: {query}")
        logger.info(f"URL: {search_url}")

        await task.page.goto(search_url, timeout=60000)
        await asyncio.sleep(2)

        return {
            "status": "success",
            "query": query,
            "url": task.page.url,
            "title": await task.page.title()
        }

    async def action_extract_results(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取当前页面的搜索结果"""
        max_items = action_params.get("max", 100)

        try:
            # 模拟人类滚动
            await self._scroll_page(task)

            # 提取网页搜索结果
            results = await self._parse_search_results(task, max_items)

            for result in results:
                if result.url not in self.processed_urls:
                    self.results.append(result)
                    self.processed_urls.add(result.url)

            # 提取相关搜索
            related = await self._parse_related_searches(task)
            for item in related:
                if item.query not in {r.query for r in self.related_searches}:
                    self.related_searches.append(item)

            # 提取人们也在问
            paa = await self._parse_people_also_ask(task)
            for item in paa:
                if item.question not in {q.question for q in self.people_also_ask}:
                    self.people_also_ask.append(item)

            return {
                "status": "success",
                "extracted": len(results),
                "total_collected": len(self.results),
                "related_searches": len(self.related_searches),
                "people_also_ask": len(self.people_also_ask),
                "results": [r.to_dict() for r in results],
                "related": [r.to_dict() for r in related],
                "paa": [p.to_dict() for p in paa]
            }

        except Exception as e:
            logger.error(f"Extract results error: {e}")
            return {"status": "error", "message": str(e)}

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取结果"""
        scroll_times = action_params.get("scroll_times", 10)
        max_items = action_params.get("max", 100)

        logger.info(f"Scrolling {scroll_times} times...")

        for i in range(scroll_times):
            await self._scroll_to_bottom(task)
            await asyncio.sleep(1)

            # 每次滚动后提取结果
            results = await self._parse_search_results(task, max_items)
            for result in results:
                if result.url not in self.processed_urls:
                    self.results.append(result)
                    self.processed_urls.add(result.url)

            logger.info(f"Scroll {i+1}/{scroll_times}, total: {len(self.results)}")

        # 最后再提取一次相关搜索
        related = await self._parse_related_searches(task)
        for item in related:
            if item.query not in {r.query for r in self.related_searches}:
                self.related_searches.append(item)

        paa = await self._parse_people_also_ask(task)
        for item in paa:
            if item.question not in {q.question for q in self.people_also_ask}:
                self.people_also_ask.append(item)

        return {
            "status": "success",
            "scroll_times": scroll_times,
            "total_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask)
        }

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "query": self.current_query,
            "results_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask),
            "processed_urls": len(self.processed_urls)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务并保存"""
        if not self.results:
            return {"status": "success", "message": "No results to save"}

        # 转换为 Resource 格式
        resources = self.to_resources()

        # 保存到存储
        from core.task_storage import TaskStorage
        storage = TaskStorage()
        raw_file = storage.save_raw_result(self.actor_name, resources)
        stats = storage.merge_to_database(self.actor_name, resources)

        results_count = len(self.results)
        related_count = len(self.related_searches)
        paa_count = len(self.people_also_ask)

        # 清空状态
        self.results = []
        self.related_searches = []
        self.people_also_ask = []
        self.processed_urls = set()
        self.current_query = ""

        return {
            "status": "success",
            "results_saved": results_count,
            "related_searches_saved": related_count,
            "people_also_ask_saved": paa_count,
            "saved_to": str(raw_file),
            "storage_stats": stats
        }

    async def _scroll_page(self, task):
        """模拟人类滚动页面"""
        await self._scroll_to_bottom(task)
        await asyncio.sleep(1)
        await task.page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)

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
            logger.info("Starting to parse search results...")

            # Bing 主结果选择器
            elements = await task.page.locator("li.b_algo").all()
            logger.info(f"[_parse_search_results] Found {len(elements)} b_algo elements")

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

                    logger.debug(f"  Result[{len(results)}]: {title[:50]}...")

                except Exception as e:
                    logger.debug(f"Failed to parse element {idx}: {e}")
                    continue

            logger.info(f"Parsed {len(results)} search results")

        except Exception as e:
            logger.error(f"Parse search results error: {e}")

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
            logger.info("Starting to parse related searches...")

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
                    logger.info(f"[_parse_related_searches] Selector '{selector}': found {len(elements)} elements")

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

                            logger.debug(f"  RelatedSearch[{len(results)}]: {text}")

                        except Exception as e:
                            logger.debug(f"Failed to parse related link {idx}: {e}")
                            continue

                    if results:
                        break

                except Exception as e:
                    logger.debug(f"Selector '{selector}' failed: {e}")
                    continue

            logger.info(f"Parsed {len(results)} related searches")

        except Exception as e:
            logger.error(f"Parse related searches error: {e}")

        return results

    async def _parse_people_also_ask(self, task) -> List[PeopleAlsoAsk]:
        """解析人们也在问

        注意：Bing 可能没有此功能，此方法保留以保持与 Google Search Actor 的一致性。
        如果将来 Bing 添加了类似功能，可以在此添加选择器。
        """
        results = []

        try:
            logger.debug("People also ask not available for Bing (feature may not exist)")

        except Exception as e:
            logger.debug(f"Parse people also ask error: {e}")

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

    def to_resources(self) -> List[Resource]:
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
            resource = Resource(
                id=f"bs_rs_{hashlib.md5(related.query.encode('utf-8')).hexdigest()[:12]}",
                resource_type="related_search",
                resource_url="",
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
            resource = Resource(
                id=f"bs_paa_{hashlib.md5(paa.question.encode('utf-8')).hexdigest()[:12]}",
                resource_type="people_also_ask",
                resource_url="",
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
