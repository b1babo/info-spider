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
            description="滚动并提取推文",
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
        """滚动并提取推文"""
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
            logger.info(f"Scroll {i + 1}")
            await HumanUtils.smart_scroll(task.page, 1, 3)

        return await self.action_extract_tweets(task, {"max": max, "time_range": time_range})

    async def action_extract_tweets(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取推文"""
        max = action_params.get('max', 100)
        count = min(len(self.resources), max)

        result = {
            "status": "success",
            "total_collected": len(self.resources),
            "returned": count,
            "tweets": []
        }

        for i, resource in enumerate(self.resources[:count]):
            result["tweets"].append({
                "id": resource.id,
                "content": resource.resource_content,
                "author": resource.resource_author_name,
                "url": resource.resource_url
            })

        # 保存
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            result["saved_to"] = str(raw_file)
            result["storage_stats"] = stats

        return result

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
        """关闭任务"""
        saved_path = None
        if self.resources:
            saved_path = await self._save_data(task)
        return {
            "status": "success",
            "resources_collected": len(self.resources),
            "saved_to": saved_path
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
        """提取推文数据"""
        if not tweet_result:
            return None

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
            resource_content=content,
            resource_platform="X/Twitter",
            resource_author_name=screen_name,
            resource_author_display_name=user_core.get('name', ''),
            is_pinned=False,
            analytics=analytics,
            resource_create_time=legacy.get("created_at", "")
        )

    async def _save_data(self, task) -> str:
        """保存数据"""
        if not self.resources:
            return None

        try:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            logger.info(f"Data saved: added={stats['added']}, skipped={stats['skipped']}")
            return str(raw_file)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
            return None
