"""
Google Search Actor - Google 搜索结果抓取

使用浏览器模式抓取 Google 搜索结果，包括：
- 网页列表（URL、标题、摘要）
- AI 总结
- 相关搜索（People also search for）
- People also ask
- Find related products & services

遵循标准的 create -> extract -> close 模式
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
            description="初始化任务并导航到搜索页面",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "Google 搜索 URL"}
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
        self.results: List[GoogleSearchResult] = []
        self.related_searches: List[RelatedSearch] = []
        self.people_also_ask: List[PeopleAlsoAsk] = []
        self.related_products: List[RelatedProduct] = []
        self.processed_urls = set()
        self.current_query = ""
        self.current_url = ""

    def _generate_result_id(self, url: str) -> str:
        """生成结果 ID"""
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
        return f"gs_{url_hash}"

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
            "message": "Google Search actor initialized",
            "actor": self.actor_name,
            "url": task.page.url,
            "title": await task.page.title(),
            "query": self.current_query
        }

    async def _scroll_page(self, task):
        """模拟人类滚动页面：滚动到底部再回到顶部"""
        try:
            logger.info("[_scroll_page] 滚动到底部...")

            # 分段滚动到底部，模拟人类行为
            for i in range(5):
                await task.page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
                await asyncio.sleep(0.3)

            # 等待底部加载
            await asyncio.sleep(1)

            logger.info("[_scroll_page] 滚动回顶部...")

            # 滚动回顶部
            await task.page.evaluate("window.scrollTo(0, 0)")

            # 等待顶部稳定
            await asyncio.sleep(1)

        except Exception as e:
            logger.debug(f"[_scroll_page] 滚动页面错误: {e}")

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
                logger.warning("[_parse_search_results] 未找到结果块")
                return results

            logger.info(f"[_parse_search_results] 找到 {len(result_blocks)} 个结果块")

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
                            logger.debug(f"  跳过: {result.url}")

                except Exception as e:
                    logger.debug(f"[_parse_search_results] 解析结果块 {idx} 失败: {e}")
                    continue

        except Exception as e:
            logger.error(f"[_parse_search_results] 解析错误: {e}")

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
            logger.debug(f"[_parse_result_block] 解析标准结果块错误: {e}")
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
            logger.debug(f"[_parse_rich_media_block] 解析富媒体结果块错误: {e}")
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
        """解析相关搜索（People also search for）"""
        results = []

        try:
            # 先检查 #bres 是否存在（相关搜索区域）
            bres = await task.page.query_selector("#botstuff #bres")
            if not bres:
                logger.debug("[_parse_related_searches] 未找到 #bres")
                return results

            # 在 #bres 中查找搜索链接：包含 /search 且包含 q= 参数
            links = await task.page.locator("#botstuff #bres a[href*='/search'][href*='q=']").all()

            if not links:
                logger.debug("[_parse_related_searches] 未找到相关搜索链接")
                return results

            logger.info(f"[_parse_related_searches] 找到 {len(links)} 个相关搜索链接")

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

                    logger.info(f"  相关搜索[{idx + 1}]: {query}")

                except Exception as e:
                    logger.debug(f"[_parse_related_searches] 解析相关搜索 {idx} 失败: {e}")
                    continue

        except Exception as e:
            logger.info(f"[_parse_related_searches] 错误: {e}")

        return results

    def _extract_query_from_href(self, href: str) -> str:
        """从 href 中提取查询参数"""
        try:
            if "q=" in href:
                q_index = href.find("q=")
                remaining = href[q_index + 2:]
                end_index = remaining.find("&")
                if end_index == -1:
                    query = remaining
                else:
                    query = remaining[:end_index]

                from urllib.parse import unquote
                decoded = unquote(query)
                return decoded.replace("+", " ")
        except Exception as e:
            logger.debug(f"[_extract_query_from_href] 错误: {e}")
        return ""

    async def _parse_people_also_ask(self, task) -> List[PeopleAlsoAsk]:
        """解析 People also ask"""
        results = []

        try:
            # 查找所有带 data-q 属性的 related-question-pair div
            questions = await task.page.locator("div.related-question-pair[data-q]").all()

            if not questions:
                logger.debug("[_parse_people_also_ask] 未找到 PAA 问题")
                return results

            logger.info(f"[_parse_people_also_ask] 找到 {len(questions)} 个 PAA 问题")

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
                    logger.debug(f"[_parse_people_also_ask] 解析 PAA 问题 {idx} 失败: {e}")
                    continue

        except Exception as e:
            logger.debug(f"[_parse_people_also_ask] 错误: {e}")

        return results

    async def _parse_related_products(self, task) -> List[RelatedProduct]:
        """解析 Find related products & services"""
        results = []

        try:
            logger.info("[_parse_related_products] 开始...")

            # 找到 disclaimer 元素
            disclaimer_patterns = [
                "These searches help you find relevant offers from advertisers",
                "These search suggestions help you find relevant offers from advertisers"
            ]

            disclaimer_element = None
            for pattern in disclaimer_patterns:
                try:
                    locator = task.page.locator('text=' + pattern).first
                    count = await locator.count()
                    if count > 0:
                        disclaimer_element = locator
                        logger.info(f"[_parse_related_products] 找到免责声明")
                        break
                except Exception as e:
                    continue

            if not disclaimer_element:
                logger.debug("[_parse_related_products] 未找到相关产品免责声明")
                return results

            # 使用 JavaScript 提取链接
            links_data = await disclaimer_element.evaluate("""el => {
                const parent = el.parentElement;
                if (!parent) return [];

                const prevSibling = parent.previousElementSibling;
                if (!prevSibling) return [];

                const links = Array.from(prevSibling.querySelectorAll('a[href]'));
                return links.map(a => ({
                    href: a.href,
                    text: a.textContent?.trim() || ''
                }));
            }""")

            logger.info(f"[_parse_related_products] 用 JavaScript 找到 {len(links_data)} 个链接")

            if not links_data:
                logger.debug("[_parse_related_products] 未找到相关产品链接")
                return results

            # 处理提取的链接数据
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

                    logger.info(f"  相关产品[{idx + 1}]: {query}")

                except Exception as e:
                    logger.debug(f"[_parse_related_products] 解析链接 {idx} 失败: {e}")
                    continue

        except Exception as e:
            logger.info(f"[_parse_related_products] 错误: {e}")

        return results

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
            resource.urls = [{"type": "search_result", "rank": result.rank, "display_url": result.display_url}]
            resources.append(resource)

        # 相关搜索结果
        for related in self.related_searches:
            from urllib.parse import urlencode
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

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取结果并保存到数据库"""
        scroll_times = action_params.get("scroll_times", 10)
        max_items = action_params.get("max", 100)

        logger.info(f"[scroll_and_extract] 滚动次数={scroll_times}, 最大={max_items}")

        # 清空之前的数据
        self.results = []
        self.related_searches = []
        self.people_also_ask = []
        self.related_products = []
        self.processed_urls = set()

        for i in range(scroll_times):
            if len(self.results) >= max_items:
                logger.info(f"[scroll_and_extract] 已达到最大数量 {max_items}，停止")
                break

            logger.info(f"[scroll_and_extract] 第 {i + 1}/{scroll_times} 次滚动")

            # 模拟人类滚动
            await self._scroll_page(task)

            # 提取当前可见的结果
            results = await self._parse_search_results(task, max_items)
            for result in results:
                if result.url not in self.processed_urls:
                    self.results.append(result)
                    self.processed_urls.add(result.url)

            # 提取相关搜索
            if i == 0:  # 只在第一次提取
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
                products = await self._parse_related_products(task)
                for item in products:
                    if item.query not in {p.query for p in self.related_products}:
                        self.related_products.append(item)

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

        logger.info(f"[scroll_and_extract] 提取完成: 结果={len(self.results)}, 相关={len(self.related_searches)}, PAA={len(self.people_also_ask)}, 产品={len(self.related_products)}")

        # 保存数据到数据库
        saved_to = None
        stats = None

        if self.results or self.related_searches or self.people_also_ask or self.related_products:
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
            "total_collected": len(self.results),
            "related_searches": len(self.related_searches),
            "people_also_ask": len(self.people_also_ask),
            "related_products": len(self.related_products),
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
            "related_products": len(self.related_products),
            "processed_urls": len(self.processed_urls)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务实例"""
        logger.info(f"[close] 关闭 Google Search actor")

        # 清空资源
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
            "message": "Google Search actor closed",
            "results_collected": results_count,
            "related_searches": related_count,
            "people_also_ask": paa_count,
            "related_products": products_count
        }
