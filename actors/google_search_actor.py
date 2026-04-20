"""
Google Search Actor - Google 搜索结果抓取

使用浏览器模式抓取 Google 搜索结果，包括：
- 网页列表（URL、标题、摘要）
- AI 总结
- 相关搜索（People also search for）
- People also ask
- Find related products & services
"""
import logging
import asyncio
import hashlib
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics

logger = logging.getLogger(__name__)


class GoogleSearchResult:
    """Google 搜索结果数据类"""

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
    """相关搜索数据类（People also search for）"""

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
    """People also ask 数据类"""

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


class RelatedProduct:
    """Find related products 数据类"""

    def __init__(
        self,
        query: str,
        display_text: str = "",
        rank: int = 0,
        url: str = ""
    ):
        self.query = query
        self.display_text = display_text or query
        self.rank = rank
        self.url = url

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "display_text": self.display_text,
            "rank": self.rank,
            "url": self.url
        }


class GoogleSearchActor(BaseActor):
    """Google 搜索 Actor - 搜索结果抓取"""

    actor_name = "google_search_actor"
    actor_description = "Google 搜索结果抓取（浏览器模式）"

    # Google 搜索 URL
    SEARCH_URL = "https://www.google.com/search"

    def setup_actions(self):
        """注册所有 Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="创建搜索任务",
            params_schema={
                "params": [
                    {"name": "query", "type": "string", "required": True, "description": "搜索关键词"},
                    {"name": "language", "type": "string", "required": False, "default": "en", "description": "语言代码"},
                    {"name": "num", "type": "integer", "required": False, "default": 10, "description": "每页结果数"}
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
        self.results: List[GoogleSearchResult] = []
        self.related_searches: List[RelatedSearch] = []
        self.people_also_ask: List[PeopleAlsoAsk] = []
        self.related_products: List[RelatedProduct] = []
        self.processed_urls = set()
        self.current_query = ""
        self.current_url = ""

    def _build_search_url(self, query: str, language: str = "en", num: int = 10) -> str:
        """构建搜索 URL"""
        params = {
            "q": query,
            "hl": language,
            "num": num
        }
        return f"{self.SEARCH_URL}?{urlencode(params)}"

    def _generate_result_id(self, url: str) -> str:
        """生成结果 ID"""
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
        return f"gs_{url_hash}"

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建搜索任务"""
        query = action_params.get("query", "")
        language = action_params.get("language", "en")
        num = action_params.get("num", 10)

        if not query:
            return {"status": "error", "message": "query is required"}

        self.current_query = query
        search_url = self._build_search_url(query, language, num)
        self.current_url = search_url

        logger.info(f"Searching: {query}")
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
            # 模拟人类滚动：先滚动到底部，再滚动回顶部
            await self._scroll_page(task)

            # 提取网页搜索结果
            results = await self._parse_search_results(task, max_items)

            for result in results:
                if result.url not in self.processed_urls:
                    self.results.append(result)
                    self.processed_urls.add(result.url)

            # 提取相关搜索（People also search for）
            related = await self._parse_related_searches(task)
            for item in related:
                if item.query not in {r.query for r in self.related_searches}:
                    self.related_searches.append(item)

            # 提取 People also ask
            paa = await self._parse_people_also_ask(task)
            for item in paa:
                if item.question not in {q.question for q in self.people_also_ask}:
                    self.people_also_ask.append(item)

            # 提取 Find related products
            logger.info("Starting to parse related products...")
            products = await self._parse_related_products(task)
            logger.info(f"Parsed {len(products)} related products")
            for item in products:
                if item.query not in {p.query for p in self.related_products}:
                    self.related_products.append(item)

            return {
                "status": "success",
                "extracted": len(results),
                "total_collected": len(self.results),
                "related_searches": len(self.related_searches),
                "people_also_ask": len(self.people_also_ask),
                "related_products": len(self.related_products),
                "results": [r.to_dict() for r in results],
                "related": [r.to_dict() for r in related],
                "paa": [p.to_dict() for p in paa],
                "products": [p.to_dict() for p in products]
            }

        except Exception as e:
            logger.error(f"Extract results failed: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    async def _scroll_page(self, task):
        """模拟人类滚动页面：滚动到底部再回到顶部"""
        try:
            logger.info("Scrolling to bottom...")

            # 分段滚动到底部，模拟人类行为
            for i in range(5):
                await task.page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                await asyncio.sleep(0.3)

            # 等待底部加载
            await asyncio.sleep(1)

            logger.info("Scrolling to top...")

            # 滚动回顶部
            await task.page.evaluate("window.scrollTo(0, 0)")

            # 等待顶部稳定
            await asyncio.sleep(1)

        except Exception as e:
            logger.debug(f"Scroll page error: {e}")

    async def _parse_search_results(self, task, max_items: int) -> List[GoogleSearchResult]:
        """解析搜索结果页面

        Google 搜索结果结构：
        1. div[data-rpos] - 每个搜索结果的容器
        2. div[data-rpos] > div[data-hveid] - 搜索结果块（直接子元素）
        3. 结果块中：
           - div[data-snhf="0"] - 标题和 URL（标准结果）
           - div[data-sncf="1"] - 摘要（标准结果）
           - 富媒体结果（YouTube 等）没有 data-snhf
        """
        results = []

        try:
            # 精确选择器：div[data-rpos] 的直接子元素 div[data-hveid]
            result_blocks = await task.page.locator("#search div[data-rpos] > div[data-hveid]").all()

            if not result_blocks:
                logger.warning("No result blocks found with selector: div[data-rpos] > div[data-hveid]")
                return results

            logger.info(f"Found {len(result_blocks)} result blocks")

            for idx, block in enumerate(result_blocks):
                if len(results) >= max_items:
                    break

                try:
                    # 先尝试标准结果解析
                    result = await self._parse_result_block(block, idx + 1)

                    # 如果标准解析失败，尝试富媒体结果解析
                    if not result:
                        result = await self._parse_rich_media_block(block, idx + 1)

                    if result and result.url:
                        if self._is_valid_web_result(result.url):
                            results.append(result)
                            logger.info(f"  [{len(results)}] {result.title[:50]}...")
                        else:
                            logger.debug(f"  Skipped: {result.url}")

                except Exception as e:
                    logger.debug(f"Failed to parse result block {idx}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Parse search results error: {e}")

        return results

    async def _parse_result_block(self, block, rank: int) -> Optional[GoogleSearchResult]:
        """解析标准搜索结果块

        标准结果结构：
        - div[data-snhf="0"] - 标题和 URL
        - div[data-sncf="1"] - 摘要
        """
        try:
            title = ""
            url = ""
            snippet = ""
            display_url = ""

            # 1. 从 data-snhf="0" 提取标题和 URL
            title_div = block.locator("div[data-snhf='0']").first
            if await title_div.count() == 0:
                return None

            # 提取 h3 标题
            h3_elem = title_div.locator("h3").first
            if await h3_elem.count() > 0:
                title = await h3_elem.inner_text()

            # 提取链接
            link_elem = title_div.locator("a[href]").first
            if await link_elem.count() > 0:
                href = await link_elem.get_attribute("href")
                if href:
                    url = self._clean_google_url(href)

            # 提取显示 URL (cite 元素)
            cite_elem = title_div.locator("cite").first
            if await cite_elem.count() > 0:
                display_url = await cite_elem.inner_text()
                display_url = display_url.replace(" › ", "/").replace(" ", "")

            # 2. 从 data-sncf="1" 提取摘要
            snippet_div = block.locator("div[data-sncf='1']").first
            if await snippet_div.count() > 0:
                snippet_content = snippet_div.locator("div[style*='-webkit-line-clamp']").first
                if await snippet_content.count() > 0:
                    snippet = await snippet_content.inner_text()
                    snippet = snippet.replace("Read more", "").strip()

            if not url:
                return None

            return GoogleSearchResult(
                url=url,
                title=title or "No title",
                snippet=snippet,
                rank=rank,
                display_url=display_url or url
            )

        except Exception as e:
            logger.debug(f"Parse standard result block error: {e}")
            return None

    async def _parse_rich_media_block(self, block, rank: int) -> Optional[GoogleSearchResult]:
        """解析富媒体结果块（如 YouTube 视频）

        特殊结果结构：
        - 没有 data-snhf，直接在 block 中查找 h3 和链接
        - snippet 在 div[style*='-webkit-line-clamp:3'] 中
        """
        try:
            title = ""
            url = ""
            snippet = ""
            display_url = ""

            # 直接在 block 中查找 h3 标题
            h3_elem = block.locator("h3").first
            if await h3_elem.count() > 0:
                title = await h3_elem.inner_text()

            # 提取链接
            link_elem = block.locator("a[href]").first
            if await link_elem.count() > 0:
                href = await link_elem.get_attribute("href")
                if href:
                    url = self._clean_google_url(href)

            # 提取显示 URL
            cite_elem = block.locator("cite").first
            if await cite_elem.count() > 0:
                display_url = await cite_elem.inner_text()

            # 提取 snippet（富媒体结果的 snippet 通常在 line-clamp:3 的 div 中）
            snippet_elem = block.locator("div[style*='-webkit-line-clamp:3']").first
            if await snippet_elem.count() > 0:
                snippet = await snippet_elem.inner_text()
                # 清理多余的空白
                snippet = " ".join(snippet.split())

            if not url:
                return None

            return GoogleSearchResult(
                url=url,
                title=title or "No title",
                snippet=snippet,
                rank=rank,
                display_url=display_url or url
            )

        except Exception as e:
            logger.debug(f"Parse rich media result block error: {e}")
            return None

    def _clean_google_url(self, url: str) -> str:
        """清理 Google 重定向 URL，获取真实 URL"""
        if not url:
            return ""

        # 处理 Google 重定向链接
        if url.startswith("/url?"):
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "url" in params:
                    return params["url"][0]
            except:
                pass

        # 移除 Google 跟踪参数
        if "google.com" in url and "url=" in url:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "url" in params:
                    return params["url"][0]
            except:
                pass

        return url

    def _is_valid_web_result(self, url: str) -> bool:
        """检查是否为有效的网页结果"""
        return bool(url)

    async def _parse_related_searches(self, task) -> List[RelatedSearch]:
        """解析相关搜索（People also search for）

        结构：
        - #botstuff #bres - 容器
        - href 格式: /search?sca_esv=...&q=... (q 参数在中间)
        """
        results = []

        try:
            # 先检查 #bres 是否存在（相关搜索区域）
            bres = await task.page.query_selector("#botstuff #bres")
            if not bres:
                logger.debug("No #bres found (related searches container)")
                return results

            # 在 #bres 中查找搜索链接：包含 /search 且包含 q= 参数
            links = await task.page.locator("#botstuff #bres a[href*='/search'][href*='q=']").all()

            if not links:
                logger.debug("No related search links found in #bres")
                return results

            logger.info(f"Found {len(links)} related search links in #bres")

            for idx, link in enumerate(links):
                try:
                    href = await link.get_attribute("href")
                    if not href:
                        continue

                    # 排除分页链接（包含 start= 参数）
                    if "start=" in href:
                        continue

                    # 从 href 中提取 q 参数
                    query = self._extract_query_from_href(href)
                    if not query:
                        continue

                    # 提取显示文本
                    display_text = ""
                    text_elem = link.locator("span").first
                    if await text_elem.count() > 0:
                        display_text = await text_elem.inner_text()
                        # 移除 HTML 标签和多余空白
                        display_text = display_text.replace("<b>", "").replace("</b>", "")
                        display_text = " ".join(display_text.split())

                    results.append(RelatedSearch(
                        query=query,
                        display_text=display_text or query,
                        rank=idx + 1
                    ))

                    logger.info(f"  Related[{idx + 1}]: {query}")

                except Exception as e:
                    logger.debug(f"Failed to parse related search {idx}: {e}")
                    continue

        except Exception as e:
            logger.info(f"Parse related searches error: {e}")

        return results

    def _extract_query_from_href(self, href: str) -> str:
        """从 href 中提取查询参数

        href 格式可能是：
        - /search?q=keyword
        - /search?sca_esv=...&q=keyword
        """
        try:
            # 直接解析 q 参数（不依赖 urlparse，因为可能是相对路径）
            if "q=" in href:
                # 找到 q= 的位置
                q_index = href.find("q=")
                # 从 q= 开始提取
                remaining = href[q_index + 2:]
                # 找到下一个 & 或字符串结束
                end_index = remaining.find("&")
                if end_index == -1:
                    query = remaining
                else:
                    query = remaining[:end_index]

                # URL 解码
                from urllib.parse import unquote
                decoded = unquote(query)
                # 将 + 替换为空格
                return decoded.replace("+", " ")
        except Exception as e:
            logger.debug(f"Extract query from href error: {e}")
        return ""

    async def _parse_people_also_ask(self, task) -> List[PeopleAlsoAsk]:
        """解析 People also ask

        结构：
        - div.related-question-pair[data-q] - 每个问题
        - data-q 属性包含问题文本
        """
        results = []

        try:
            # 查找所有带 data-q 属性的 related-question-pair div
            questions = await task.page.locator("div.related-question-pair[data-q]").all()

            if not questions:
                logger.debug("No People also ask questions found")
                return results

            logger.info(f"Found {len(questions)} People also ask questions")

            for idx, q_div in enumerate(questions):
                try:
                    # 从 data-q 属性提取问题
                    question = await q_div.get_attribute("data-q")
                    if not question:
                        continue

                    results.append(PeopleAlsoAsk(
                        question=question,
                        rank=idx + 1
                    ))

                    logger.info(f"  PAA[{idx + 1}]: {question}")

                except Exception as e:
                    logger.debug(f"Failed to parse PAA question {idx}: {e}")
                    continue

        except Exception as e:
            logger.debug(f"Parse People also ask error: {e}")

        return results

    async def _parse_related_products(self, task) -> List[RelatedProduct]:
        """解析 Find related products & services

        稳定特征（Google UI 文本）：
        说明文字: "These searches help you find relevant offers from advertisers"

        策略：
        1. 找到 disclaimer 元素
        2. 获取其上一个兄弟元素（包含链接的列表）
        3. 提取其中所有 a[href]
        """
        results = []

        try:
            logger.info("[_parse_related_products] Starting...")

            # 1. 找到 disclaimer 元素（使用文本匹配）
            disclaimer_patterns = [
                "These searches help you find relevant offers from advertisers",
                "These search suggestions help you find relevant offers from advertisers"
            ]

            disclaimer_element = None
            for pattern in disclaimer_patterns:
                try:
                    locator = task.page.locator('text=' + pattern).first
                    count = await locator.count()
                    logger.info(f"[_parse_related_products] Pattern '{pattern[:40]}...': count={count}")
                    if count > 0:
                        disclaimer_element = locator
                        logger.info(f"[_parse_related_products] Found disclaimer with pattern: {pattern[:50]}...")
                        break
                except Exception as e:
                    logger.info(f"[_parse_related_products] Error checking pattern: {e}")
                    continue

            if not disclaimer_element:
                logger.debug("[_parse_related_products] No disclaimer found for related products")
                return results

            # 2. 使用纯 JavaScript 提取链接数据
            # 直接在浏览器中执行 JavaScript 来获取上一个兄弟元素中的链接
            logger.info("[_parse_related_products] Extracting links with JavaScript...")

            links_data = await disclaimer_element.evaluate("""el => {
                // 获取父元素
                const parent = el.parentElement;
                if (!parent) return [];

                // 获取上一个兄弟元素
                const prevSibling = parent.previousElementSibling;
                if (!prevSibling) return [];

                // 查找所有链接
                const links = Array.from(prevSibling.querySelectorAll('a[href]'));
                return links.map(a => ({
                    href: a.href,
                    text: a.textContent?.trim() || ''
                }));
            }""")

            logger.info(f"[_parse_related_products] Found {len(links_data)} links with JavaScript")

            if not links_data:
                logger.debug("[_parse_related_products] No links found in related products container")
                return results

            # 3. 处理提取的链接数据
            for idx, link_data in enumerate(links_data):
                try:
                    href = link_data.get('href')
                    text = link_data.get('text', '')

                    if not href:
                        continue

                    # 只处理搜索链接
                    if "/search" not in href or "q=" not in href:
                        continue

                    # 提取查询参数
                    query = self._extract_query_from_href(href)
                    if not query:
                        continue

                    # 构建完整 URL
                    url = href if href.startswith("http") else f"https://www.google.com{href}"

                    results.append(RelatedProduct(
                        query=query,
                        display_text=text or query,
                        rank=idx + 1,
                        url=url
                    ))

                    logger.info(f"  RelatedProduct[{idx + 1}]: {query}")

                except Exception as e:
                    logger.debug(f"Failed to parse link {idx}: {e}")
                    continue

        except Exception as e:
            logger.info(f"Parse related products error: {e}")

        return results

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取结果"""
        scroll_times = action_params.get("scroll_times", 10)
        max_items = action_params.get("max", 100)

        logger.info(f"Scroll and extract: scroll_times={scroll_times}, max={max_items}")

        for i in range(scroll_times):
            if len(self.results) >= max_items:
                logger.info(f"Reached max items {max_items}, stopping")
                break

            logger.info(f"Scroll {i + 1}/{scroll_times}")

            # 提取当前可见的结果
            await self.action_extract_results(task, {"max": max_items})

            # 滚动到底部
            await task.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)

            # 尝试点击 "Show more results" 按钮
            if await task.page.locator("input[value='Show more results']").count() > 0:
                try:
                    await task.page.locator("input[value='Show more results']").first.click()
                    await asyncio.sleep(2)
                except:
                    pass

        return {
            "status": "success",
            "total_collected": len(self.results),
            "results": [r.to_dict() for r in self.results]
        }

    def _results_to_resources(self) -> List[Resource]:
        """将搜索结果转换为 Resource 对象"""
        resources = []

        # 网页搜索结果
        for result in self.results:
            resource = Resource(
                id=self._generate_result_id(result.url),
                resource_type="search_result",
                resource_url=result.url,
                resource_content=result.snippet,
                description=result.title,
                resource_platform="Google Search",
                resource_platform_url=self.current_url,  # 使用搜索 URL
                resource_author_name="",
                resource_author_display_name="",
                resource_author_url="",
                analytics=Analytics(
                    view_count=0,
                    like_count=0,
                    reply_count=0
                )
            )
            # 将 rank 存储在 urls 字段中
            resource.urls = [{"type": "search_result", "rank": result.rank, "display_url": result.display_url}]
            resources.append(resource)

        # 相关搜索结果
        for related in self.related_searches:
            # 生成相关搜索的搜索 URL
            from urllib.parse import urlencode, quote
            search_url = f"{self.SEARCH_URL}?{urlencode({'q': related.query})}"

            resource = Resource(
                id=f"gs_rel_{hashlib.md5(related.query.encode('utf-8')).hexdigest()[:12]}",
                resource_type="related_search",
                resource_url=search_url,
                resource_content="",
                description=related.display_text,
                resource_platform="Google Search",
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

        # People also ask 结果
        for paa in self.people_also_ask:
            # 生成搜索 URL（将问题作为搜索词）
            from urllib.parse import urlencode
            search_url = f"{self.SEARCH_URL}?{urlencode({'q': paa.question})}"

            resource = Resource(
                id=f"gs_paa_{hashlib.md5(paa.question.encode('utf-8')).hexdigest()[:12]}",
                resource_type="people_also_ask",
                resource_url=search_url,
                resource_content="",
                description=paa.question,
                resource_platform="Google Search",
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

        # Find related products 结果
        for product in self.related_products:
            resource = Resource(
                id=f"gs_rp_{hashlib.md5(product.query.encode('utf-8')).hexdigest()[:12]}",
                resource_type="related_product",
                resource_url=product.url,
                resource_content="",
                description=product.display_text,
                resource_platform="Google Search",
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
            resource.urls = [{"type": "related_product", "rank": product.rank, "query": product.query}]
            resources.append(resource)

        return resources

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "query": self.current_query,
            "results_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask),
            "related_products": len(self.related_products),
            "processed_urls": len(self.processed_urls)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务并保存"""
        saved_path = None
        stats = {"total": 0, "added": 0, "skipped": 0}

        if self.results:
            from core.task_storage import TaskStorage
            storage = TaskStorage()

            resources = self._results_to_resources()

            # 保存原始数据
            raw_file = storage.save_raw_result(task.task_config.name, resources)

            # 合并到数据库
            stats = storage.merge_to_database(task.task_config.name, resources)
            saved_path = str(raw_file)
            logger.info(f"Results saved: added={stats['added']}, skipped={stats['skipped']}")

        # 清理状态
        results_count = len(self.results)
        related_count = len(self.related_searches)
        paa_count = len(self.people_also_ask)
        products_count = len(self.related_products)
        self.results = []
        self.related_searches = []
        self.people_also_ask = []
        self.related_products = []
        self.processed_urls = set()
        self.current_query = ""

        return {
            "status": "success",
            "results_saved": results_count,
            "related_searches_saved": related_count,
            "people_also_ask_saved": paa_count,
            "related_products_saved": products_count,
            "saved_to": saved_path,
            "storage_stats": stats
        }
