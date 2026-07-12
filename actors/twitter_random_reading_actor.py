"""
Twitter/X 随机阅读（首页推荐）Actor
"""
import logging
import asyncio
from typing import List, Dict, Any
from playwright.async_api import Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils

import jmespath

logger = logging.getLogger(__name__)


class TwitterRandomReadingActor(BaseActor):
    """Twitter/X首页随机推荐Actor"""

    actor_name = "twitter_random_reading_actor"
    actor_description = "Twitter/X首页随机推荐Actor"

    def setup_actions(self):
        """注册所有Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="创建Twitter首页任务",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "首页URL"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动页面并提取内容（推文+文章），立即保存并返回统计信息",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10},
                    {"name": "max", "type": "integer", "required": False, "default": 100},
                    {"name": "time_range", "type": "integer", "required": False, "default": 24},
                    {"name": "reset", "type": "boolean", "required": False, "default": True}
                ]
            }
        )

        self.resources: List[Resource] = []
        self._response_handler_registered = False
        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = 24

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务"""
        url = action_params.get('url')
        await self.action_intercept_response(task, {"enable": True})

        logger.info(f"Navigating to: {url}")
        await task.page.goto(url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "url": task.page.url,
            "title": await task.page.title()
        }

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取内容（推文+文章），立即保存并返回统计信息"""
        scroll_times = action_params.get('scroll_times', 10)
        max = action_params.get('max', 100)
        time_range = action_params.get('time_range', 24)
        reset = action_params.get('reset', True)

        if reset:
            self.resources = []
        self.out_time_time_number = 0
        self.stop_scroll = False
        self.time_range = time_range

        from core.utils import HumanUtils
        for i in range(scroll_times):
            if self.stop_scroll:
                break
            logger.info(f"[首页推荐] Scroll {i + 1}")
            await HumanUtils.smart_scroll(task.page, 1, 3)

        # 保存数据并返回统计信息
        count = min(len(self.resources), max)

        # 保存数据
        saved_to = None
        stats = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            saved_to = str(raw_file)
            logger.info(f"[首页推荐] 保存完成: raw={raw_file.name}, added={stats['added']}, skipped={stats['skipped']}")

        # 统计类型
        tweet_count = len([r for r in self.resources if r.resource_type == "tweet"])
        article_count = len([r for r in self.resources if r.resource_type == "article"])

        return {
            "status": "success",
            "page_type": "home_timeline",
            "total_collected": count,
            "tweets": tweet_count,
            "articles": article_count,
            "time_range_hours": time_range,
            "saved_to": saved_to,
            "storage_stats": stats
        }

    async def action_intercept_response(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """拦截响应"""
        enable = action_params.get('enable', True)
        if enable:
            if not self._response_handler_registered:
                task.page.on("response", self._intercept_response)
                self._response_handler_registered = True
        return {"status": "success", "interception_enabled": enable}

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "resources_collected": len(self.resources),
            "interception_enabled": self._response_handler_registered
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务并关闭页面（数据已在 scroll_and_extract 中保存）"""
        try:
            await task.page.close()
            logger.info(f"[close] 页面已关闭")
        except Exception as e:
            logger.warning(f"[close] 关闭页面时出错: {e}")

        return {
            "status": "success",
            "message": "Twitter random reading actor 已关闭",
            "resources_collected": len(self.resources)
        }

    async def _intercept_response(self, response: Response):
        """拦截API响应"""
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            if "/HomeTimeline" in response.url or "/HomeLatestTimeline" in response.url:
                logger.info(f"[Intercept] {response.url[:80]}...")
                try:
                    data = await response.json()
                    resources = self.parse_home_timeline(data)
                    self._process_resources(resources)
                except Exception as e:
                    logger.error(f"[Intercept] Parse failed: {e}")

    def _process_resources(self, resources: List[Resource]):
        """处理资源"""
        for r in resources:
            if utils.time_within(r.resource_create_time, time_delta=self.time_range):
                self.resources.append(r)
            else:
                self.out_time_time_number += 1
                if self.out_time_time_number >= self.out_time_max:
                    self.stop_scroll = True

    def parse_home_timeline(self, data: dict) -> List[Resource]:
        """解析时间线"""
        instructions = jmespath.search('data.home.home_timeline_urt.instructions', data)
        if not instructions:
            return []

        tweets = []
        for instruction in instructions:
            if instruction.get('type') == 'TimelineAddEntries':
                for entry in instruction.get('entries', []):
                    entry_id = entry.get("entryId", "")
                    if entry_id.startswith("tweet"):
                        tweet_result = jmespath.search('content.itemContent.tweet_results.result', entry)
                        tweets.append(self._extract_tweet_data(tweet_result))
        return tweets

    def _extract_tweet_data(self, tweet_result) -> Resource:
        """提取推文/文章数据（自动判断类型）"""
        if not tweet_result:
            return None

        # 检查是否为文章
        if 'article' in tweet_result:
            return self._extract_article_data(tweet_result)
        else:
            return self._extract_tweet_only_data(tweet_result)

    def _extract_article_data(self, tweet_result) -> Resource:
        """提取文章数据"""
        try:
            article = jmespath.search('article.article_results.result', tweet_result)
            if not article:
                # 回退到推文处理
                return self._extract_tweet_only_data(tweet_result)

            # 提取用户信息
            user_result = tweet_result.get('core', {}).get('user_results', {}).get('result', {})
            user_legacy = user_result.get('legacy', {})
            user_core = user_result.get('core', {})
            screen_name = user_core.get('screen_name', '')

            author = Author(
                id=user_result.get('rest_id', ''),
                author_url=f"https://x.com/{screen_name}",
                author_name=screen_name,
                author_display_name=user_core.get('name', ''),
                followers_count=user_legacy.get("followers_count", 0),
                following_count=user_legacy.get("following_count", 0)
            )

            # 提取文章内容
            legacy = tweet_result.get('legacy', {})
            views = tweet_result.get('views', {})

            analytics = Analytics(
                view_count=int(views.get("count", "0") or 0),
                like_count=legacy.get("favorite_count", 0),
                reply_count=legacy.get("reply_count", 0),
                share_count=legacy.get("retweet_count", 0)
            )

            title = article.get('title', '') or ''
            summary = article.get('summary_text', '') or ''

            # 简化版文章内容提取（完整解析需要 Draft.js 处理）
            content_state = article.get('content_state', {})
            if content_state.get('blocks'):
                blocks = content_state.get('blocks', [])
                texts = [block.get('text', '') for block in blocks if block.get('text')]
                body_content = "\n\n".join(texts)
            else:
                body_content = legacy.get("full_text", "")

            # 拼接完整内容
            parts = []
            if title:
                parts.append(f"# {title}")
            if summary:
                parts.append(f"> {summary}".replace("\n", "\n> "))
            if body_content:
                parts.append(body_content)
            content = "\n\n".join(parts).strip()

            return Resource(
                id=tweet_result.get('rest_id', ''),
                resource_url=f"https://x.com/{screen_name}/status/{tweet_result.get('rest_id', '')}",
                resource_content=content[:5000],  # 文章可能更长
                resource_type="article",
                description=title,
                resource_platform="X/Twitter",
                resource_author_name=screen_name,
                resource_author_display_name=user_core.get('name', ''),
                is_pinned=False,
                analytics=analytics,
                resource_create_time=legacy.get("created_at", "")
            )
        except Exception as e:
            logger.error(f"[提取文章数据失败: {e}")
            return self._extract_tweet_only_data(tweet_result)

    def _extract_tweet_only_data(self, tweet_result) -> Resource:
        """提取普通推文数据"""
        # 提取用户信息
        user_result = tweet_result.get('core', {}).get('user_results', {}).get('result', {})
        user_legacy = user_result.get('legacy', {})
        user_core = user_result.get('core', {})
        screen_name = user_core.get('screen_name', '')

        author = Author(
            id=user_result.get('rest_id', ''),
            author_url=f"https://x.com/{screen_name}",
            author_name=screen_name,
            author_display_name=user_core.get('name', ''),
            followers_count=user_legacy.get("followers_count", 0),
            following_count=user_legacy.get("following_count", 0)
        )

        # 提取推文内容
        legacy = tweet_result.get('legacy', {})
        views = tweet_result.get('views', {})

        analytics = Analytics(
            view_count=int(views.get("count", "0")),
            like_count=legacy.get("favorite_count", 0),
            reply_count=legacy.get("reply_count", 0),
            share_count=legacy.get("retweet_count", 0)
        )

        note_tweet = tweet_result.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {})
        content = note_tweet.get("text", "") if note_tweet.get("text", "") else legacy.get("full_text", "")

        return Resource(
            id=tweet_result.get('rest_id', ''),
            resource_url=f"https://x.com/{screen_name}/status/{tweet_result.get('rest_id', '')}",
            resource_content=content[:1000],
            resource_type="tweet",
            resource_platform="X/Twitter",
            resource_author_name=screen_name,
            resource_author_display_name=user_core.get('name', ''),
            is_pinned=False,
            analytics=analytics,
            resource_create_time=legacy.get("created_at", "")
        )
