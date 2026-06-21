"""Twitter/X 文章 (Article) 抓取 Actor。

X 的「文章」长内容有独立的接口：
- 列表接口（访问 /{user}/articles 触发）：返回每篇文章的元数据
  （标题/摘要/封面/时间/阅读量），但正文 content_state 为空。
- 详情接口（访问单条 status URL 触发）：返回完整正文 content_state
  （Draft.js 格式）+ summary_text + media_entities。

因此本 Actor 分两步：滚动列表收集元数据 -> 逐篇抓取正文并重建为 Markdown。
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

import jmespath
from playwright.async_api import Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils
from core.utils import HumanUtils

logger = logging.getLogger(__name__)


class TwitterArticleActor(BaseActor):
    """Twitter/X 文章页面 Actor"""

    actor_name = "twitter_article_actor"
    actor_description = "Twitter/X 文章（Article）抓取Actor：列表+逐篇正文"

    def setup_actions(self):
        self.register_action(
            "create",
            self.action_create,
            description="创建任务并导航到用户文章页（/{user}/articles）",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True,
                     "description": "文章页URL，如 https://x.com/heynavtoor/articles"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动文章列表并逐篇抓取完整正文",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 30, "description": "列表滚动次数"},
                    {"name": "max", "type": "integer", "required": False, "default": 20, "description": "最多抓取文章数"},
                    {"name": "time_range", "type": "integer", "required": False, "default": 720, "description": "时间范围(小时)"},
                    {"name": "fetch_body", "type": "boolean", "required": False, "default": True, "description": "是否抓取完整正文"}
                ]
            }
        )

        # 内部状态
        self.resources: List[Resource] = []
        self._response_handler_registered = False
        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = 720
        # 逐篇正文抓取用
        self._detail_article: Optional[dict] = None
        self._detail_event: Optional[asyncio.Event] = None

    # ===== Actions =====

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """导航到用户文章页并开启列表响应拦截"""
        url = action_params.get('url') or task.task_config.url
        if not url:
            return {"status": "error",
                    "message": "Missing required parameter: url"}
        # 确保以 /articles 结尾
        if not url.rstrip("/").endswith("/articles"):
            base = url.split("/articles")[0]
            url = f"{base}/articles"

        self._response_handler_registered = False
        await self._enable_listing_intercept(task)

        logger.info(f"[article] Navigating to: {url}")
        await task.page.goto(url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "Twitter article actor initialized",
            "actor": self.actor_name,
            "url": task.page.url,
            "title": await task.page.title(),
        }

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        scroll_times = action_params.get('scroll_times', 30)
        max_items = action_params.get('max', 20)
        time_range = action_params.get('time_range', 720)
        fetch_body = action_params.get('fetch_body', True)

        if not self._response_handler_registered:
            await self._enable_listing_intercept(task)

        # 累加模式：保留 create 阶段已拦截到的文章（按 id 去重），滚动用于加载更多
        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = time_range

        # 1) 滚动列表，收集文章元数据
        for i in range(scroll_times):
            if self.stop_scroll or len(self.resources) >= max_items:
                logger.info(f"[article] 列表收集结束（已有 {len(self.resources)} 篇），停止滚动")
                break
            logger.info(f"[article] 第 {i + 1} 次滚动...")
            await HumanUtils.smart_scroll(task.page, 1, 3)

        # 用 max 限制最终处理数量
        self.resources = self.resources[:max_items]
        logger.info(f"[article] 列表收集完成，共 {len(self.resources)} 篇文章（上限 max={max_items}）")

        # 2) 逐篇抓取完整正文
        if fetch_body and self.resources:
            await self._fetch_all_bodies(task)

        # 3) 保存
        saved_to = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            saved_to = str(raw_file)
            logger.info(f"[article] 保存完成: raw={raw_file.name}, added={stats['added']}, skipped={stats['skipped']}")
            # 额外：每篇写一个 Markdown 文件
            self._write_markdown_files(task)
        else:
            logger.warning(f"[article] 未收集到文章数据")

        return {
            "status": "success",
            "total_collected": len(self.resources),
            "time_range_hours": time_range,
            "saved_to": saved_to,
        }

    # ===== 列表拦截 =====

    async def _enable_listing_intercept(self, task):
        if self._response_handler_registered:
            return
        task.page.on("response", self._intercept_listing)
        self._response_handler_registered = True
        logger.info("[article] 列表响应拦截已启用")

    async def _intercept_listing(self, response: Response):
        """拦截文章列表响应"""
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return
        if "/graphql/" not in response.url:
            return
        try:
            data = await response.json()
        except Exception:
            return

        instructions = (jmespath.search('data.user.result.timeline.timeline.instructions', data)
                        or jmespath.search('data.user.result.timeline_v2.timeline.instructions', data))
        if not instructions:
            return

        resources = self._parse_article_listing(instructions)
        if not resources:
            return

        logger.info(f"[article][列表] 解析到 {len(resources)} 篇文章")

        in_range = 0
        out_range = 0
        for r in resources:
            # 按文章 id 去重
            if any(existing.id == r.id for existing in self.resources):
                continue
            if utils.time_within(r.resource_create_time, time_delta=self.time_range):
                self.resources.append(r)
                in_range += 1
            else:
                self.out_time_time_number += 1
                out_range += 1
                logger.info(f"[article][列表] 超出时间范围: {r.resource_create_time} - {r.description[:40]}")
                if self.out_time_time_number >= self.out_time_max:
                    self.stop_scroll = True
                    logger.info("[article][列表] 达到超时数量限制，停止滚动")
        if out_range > 0:
            logger.info(f"[article][列表] 时间范围过滤: {in_range} 篇在范围内，{out_range} 篇超出范围 ({self.time_range}h)")

    def _parse_article_listing(self, instructions) -> List[Resource]:
        """解析文章列表 instructions -> Resource（仅元数据）"""
        resources: List[Resource] = []
        for instruction in instructions:
            if instruction.get('type') != 'TimelineAddEntries':
                continue
            for entry in instruction.get('entries', []):
                entry_id: str = entry.get('entryId', '')
                if not entry_id.startswith('tweet'):
                    continue
                result = jmespath.search('content.itemContent.tweet_results.result', entry)
                if not isinstance(result, dict) or 'article' not in result:
                    continue
                resource = self._build_article_resource(result, full_body=False)
                if resource:
                    resources.append(resource)
        return resources

    def _build_article_resource(self, tweet_result: dict, full_body: bool) -> Optional[Resource]:
        """从 tweet result 构建 Resource。full_body=True 时需 content_state 已就绪。"""
        try:
            article = jmespath.search('article.article_results.result', tweet_result)
            if not article:
                return None

            tweet_rest_id = tweet_result.get('rest_id', '')
            user_result = tweet_result.get('core', {}).get('user_results', {}).get('result', {})
            author = self._extract_user_result(user_result)
            legacy = tweet_result.get('legacy', {})
            views = tweet_result.get('views', {})

            analytics = Analytics(
                view_count=int(views.get("count", "0") or 0),
                like_count=legacy.get("favorite_count", 0),
                reply_count=legacy.get("reply_count", 0),
                share_count=legacy.get("retweet_count", 0),
                bookmark_count=legacy.get("bookmark_count", 0),
                referenced_count=legacy.get("quote_count", 0),
            )

            # 媒体：封面 + 正文图片
            media: List[ResourceMedia] = []
            cover_url = jmespath.search('cover_media.media_info.original_img_url', article)
            if cover_url:
                media.append(ResourceMedia(media_type="image", media_url=cover_url))

            title = article.get('title', '') or ''
            preview = article.get('preview_text', '') or ''
            summary = article.get('summary_text', '') or ''

            content_state = article.get('content_state', {}) or {}
            media_entities = article.get('media_entities', []) or []

            # 重建正文 Markdown
            body_md = ""
            inline_media: List[ResourceMedia] = []
            if full_body and content_state.get('blocks'):
                body_md, inline_media = draftjs_to_markdown(content_state, media_entities)
                media.extend(inline_media)

            # 拼接完整 Markdown
            parts = []
            if title:
                parts.append(f"# {title}")
            if summary:
                parts.append(f"> {summary}".replace("\n", "\n> "))
            if body_md:
                parts.append(body_md)
            resource_content = "\n\n".join(parts).strip()

            resource = Resource(
                id=tweet_rest_id,
                resource_type="article",
                resource_url=f"https://x.com/{author.author_name}/status/{tweet_rest_id}",
                resource_content=resource_content,
                description=preview,
                resource_platform="X/Twitter",
                resource_platform_url="https://x.com",
                resource_author_name=author.author_name,
                resource_author_display_name=author.author_display_name,
                resource_author_url=author.author_url,
                resource_media=media,
                analytics=analytics,
                resource_create_time=legacy.get("created_at", ""),
            )
            return resource
        except Exception as e:
            logger.error(f"[article] 构建 Resource 失败: {e}")
            return None

    def _extract_user_result(self, user_result) -> Author:
        user_legacy = user_result.get('legacy', {})
        user_core = user_result.get('core', {})
        name = user_core.get('screen_name', '')
        return Author(
            id=user_result.get('rest_id', ''),
            author_url=f"https://x.com/{name}",
            author_name=name,
            author_display_name=user_core.get('name', ''),
            followers_count=user_legacy.get("followers_count", 0),
            following_count=user_legacy.get("following_count", 0),
            description="",
        )

    # ===== 逐篇正文抓取 =====

    async def _fetch_all_bodies(self, task):
        total = len(self.resources)
        for idx, resource in enumerate(self.resources, 1):
            logger.info(f"[article][正文] ({idx}/{total}) 抓取: {resource.id} - {resource.description[:40]}")
            article_detail = await self._fetch_full_body(task, resource)
            if article_detail:
                updated = self._build_article_resource(article_detail, full_body=True)
                if updated:
                    # 保留原 metadata 字段，覆盖正文相关
                    resource.resource_content = updated.resource_content
                    resource.resource_media = updated.resource_media
                    logger.info(f"[article][正文] 成功: {resource.id} (正文 {len(updated.resource_content)} 字符)")
                    continue
            logger.warning(f"[article][正文] 失败（正文为空）: {resource.id}")

    async def _fetch_full_body(self, task, resource: Resource) -> Optional[dict]:
        """导航到单条文章 status 页，捕获详情响应，返回 tweet result（含完整 article）"""
        self._detail_article = None
        self._detail_event = asyncio.Event()

        async def on_resp(response: Response):
            ct = response.headers.get("content-type", "")
            if "application/json" not in ct or "/graphql/" not in response.url:
                return
            try:
                data = await response.json()
            except Exception:
                return
            result = self._find_article_tweet_result(data)
            blocks = jmespath.search('article.article_results.result.content_state.blocks', result) if result else None
            logger.debug(f"[article][正文] on_resp op={response.url.split('/graphql/')[-1].split('/')[0]} has_article={bool(result)} blocks={len(blocks) if blocks else 0}")
            if result and blocks:
                self._detail_article = result
                if self._detail_event:
                    self._detail_event.set()

        task.page.on("response", on_resp)
        try:
            try:
                await task.page.goto(resource.resource_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.debug(f"[article][正文] goto 提示: {e}")
            try:
                await asyncio.wait_for(self._detail_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning(f"[article][正文] 详情响应超时: {resource.id}")
            # 额外等待正文接口（有时延迟）
            await asyncio.sleep(1)
        finally:
            try:
                task.page.remove_listener("response", on_resp)
            except Exception:
                pass
        return self._detail_article

    def _find_article_tweet_result(self, data: dict) -> Optional[dict]:
        """从详情响应中定位含 article 的 tweet result"""
        # 路径1：data.tweetResult.result
        result = jmespath.search('data.tweetResult.result', data)
        if result and isinstance(result, dict) and 'article' in result:
            return result
        # 路径2：TweetDetail threaded_conversation
        results = jmespath.search(
            'data.threaded_conversation_with_injections_v2.instructions[].entries[].'
            'content.itemContent.tweet_results.result', data) or []
        for r in results:
            if isinstance(r, dict) and 'article' in r:
                return r
        return None

    # ===== 输出 Markdown 文件 =====

    def _write_markdown_files(self, task):
        data_dir = task.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        for resource in self.resources:
            if not resource.resource_content:
                continue
            md_path = data_dir / f"{resource.id}.md"
            try:
                md_path.write_text(resource.resource_content, encoding="utf-8")
            except Exception as e:
                logger.error(f"[article] 写 Markdown 失败 {md_path}: {e}")
        logger.info(f"[article] 已写入 {len(self.resources)} 个 Markdown 文件到 {data_dir}")


# ===== Draft.js -> Markdown 重建 =====

def draftjs_to_markdown(content_state: dict, media_entities: list) -> tuple:
    """将 X 文章的 Draft.js content_state 重建为 Markdown。

    Returns:
        (markdown_str, [ResourceMedia])  正文内引用的图片列表
    """
    blocks = content_state.get('blocks', []) or []
    # entityMap 是列表，entityRanges.key 是该列表的整数索引（不是实体的 "key" 字段）
    entity_map = {i: e.get('value', {}) for i, e in enumerate(content_state.get('entityMap', []) or [])}
    # media_id -> url
    media_url_by_id = {}
    for m in (media_entities or []):
        mid = m.get('media_id')
        url = jmespath.search('media_info.original_img_url', m)
        if mid and url:
            media_url_by_id[str(mid)] = url

    inline_media: List[ResourceMedia] = []
    out_lines: List[str] = []

    for block in blocks:
        line = _render_block(block, entity_map, media_url_by_id, inline_media)
        if line is not None:
            out_lines.append(line)

    return "\n\n".join(out_lines).strip(), inline_media


def _render_block(block: dict, entity_map: dict, media_url_by_id: dict, inline_media: list) -> Optional[str]:
    btype = block.get('type', 'unstyled')
    text = block.get('text', '')
    entity_ranges = block.get('entityRanges', []) or []

    # 整块特殊类型先处理
    if btype == 'atomic':
        return _render_atomic(block, entity_map, media_url_by_id, inline_media)

    if btype == 'code-block':
        return f"```\n{text}\n```"

    # 内联实体渲染（LINK / TWEMOJI / 内联 MEDIA）
    rendered = _apply_inline_entities(text, entity_ranges, entity_map, media_url_by_id, inline_media)

    if btype in ('header-one', 'header-two', 'header-three', 'header-four', 'header-five', 'header-six'):
        level = {'header-one': 1, 'header-two': 2, 'header-three': 3,
                 'header-four': 4, 'header-five': 5, 'header-six': 6}[btype]
        return f"{'#' * level} {rendered}"
    if btype == 'blockquote':
        return "\n".join(f"> {ln}" for ln in rendered.split("\n"))
    if btype == 'ordered-list-item':
        return f"1. {rendered}"
    if btype == 'unordered-list-item':
        return f"- {rendered}"
    # unstyled / default
    return rendered


def _apply_inline_entities(text, entity_ranges, entity_map, media_url_by_id, inline_media) -> str:
    """处理内联 entityRanges（按 offset 升序），返回带 Markdown 链接/图片的文本。"""
    if not entity_ranges:
        return text
    ranges = sorted(entity_ranges, key=lambda r: r.get('offset', 0))
    result = ""
    cursor = 0
    for r in ranges:
        offset = r.get('offset', 0)
        length = r.get('length', 0)
        key = r.get('key')
        entity = entity_map.get(key, {})
        etype = entity.get('type', '')
        edata = entity.get('data', {}) or {}

        result += text[cursor:offset]
        segment = text[offset:offset + length]

        if etype == 'LINK':
            url = edata.get('url', '')
            result += f"[{segment}]({url})" if url else segment
        elif etype == 'MEDIA':
            url = _resolve_media_url(entity, media_url_by_id)
            if url:
                inline_media.append(ResourceMedia(media_type="image", media_url=url))
                result += f"\n\n![image]({url})\n\n"
            else:
                result += segment
        else:
            # TWEMOJI / 其它：保留原文
            result += segment
        cursor = offset + length
    result += text[cursor:]
    return result


def _render_atomic(block, entity_map, media_url_by_id, inline_media) -> Optional[str]:
    """atomic 块：通常是图片/嵌入，取其 entityRange 对应的 MEDIA。"""
    entity_ranges = block.get('entityRanges', []) or []
    parts = []
    for r in entity_ranges:
        entity = entity_map.get(r.get('key'), {})
        etype = entity.get('type', '')
        edata = entity.get('data', {}) or {}
        if etype == 'MEDIA':
            url = _resolve_media_url(entity, media_url_by_id)
            if url:
                inline_media.append(ResourceMedia(media_type="image", media_url=url))
                parts.append(f"![image]({url})")
        elif etype == 'MARKDOWN':
            md = edata.get('markdown', '')
            if md:
                parts.append(md)
        elif etype == 'DIVIDER':
            parts.append("---")
    if parts:
        return "\n\n".join(parts)
    return None


def _resolve_media_url(entity: dict, media_url_by_id: dict) -> str:
    """从 MEDIA entity 解析图片 URL。"""
    media_items = (entity.get('data', {}) or {}).get('mediaItems', []) or []
    for mi in media_items:
        mid = str(mi.get('mediaId', '')) if isinstance(mi, dict) else ''
        if mid and mid in media_url_by_id:
            return media_url_by_id[mid]
    return ''
