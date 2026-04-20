import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from playwright.async_api import Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils
from core.utils import HumanUtils

import jmespath

logger = logging.getLogger(__name__)


class TwitterUserActor(BaseActor):
    """Twitter/X用户页面Actor"""

    actor_name = "twitter_user_actor"
    actor_description = "Twitter/X用户页面操作Actor"

    def setup_actions(self):
        """注册所有Twitter相关的Actions"""
        # 不再注册通用actions，只使用Twitter特定的actions

        # 注册Twitter特定的actions
        self.register_action(
            "create",
            self.action_create,
            description="创建Twitter任务实例并导航到用户页面",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "用户页面URL，如 https://x.com/GitHub_Daily"}
                ]
            }
        )

        self.register_action(
            "status",
            self.action_status,
            description="获取任务状态",
            params_schema={"params": []}
        )

        self.register_action(
            "close",
            self.action_close,
            description="关闭任务实例",
            params_schema={"params": []}
        )

        self.register_action(
            "intercept_response",
            self.action_intercept_response,
            description="拦截API响应",
            params_schema={
                "params": [
                    {"name": "enable", "type": "boolean", "required": False, "default": True, "description": "是否启用拦截"}
                ]
            }
        )

        self.register_action(
            "extract_tweets",
            self.action_extract_tweets,
            description="提取推文数据",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 100, "description": "最大提取数量"},
                    {"name": "time_range", "type": "integer", "required": False, "default": 24, "description": "时间范围(小时)"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动页面并提取推文",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10, "description": "滚动次数"},
                    {"name": "max", "type": "integer", "required": False, "default": 100, "description": "最大提取数量"},
                    {"name": "time_range", "type": "integer", "required": False, "default": 24, "description": "时间范围(小时)"},
                    {"name": "reset", "type": "boolean", "required": False, "default": True, "description": "是否重置已收集的数据"}
                ]
            }
        )

        # 初始化内部状态
        self.resources: List[Resource] = []
        self._response_handler_registered = False
        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = 24

    # ===== 任务管理Actions =====

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务并导航到用户页面"""
        # 优先使用 action_params 中的 url，否则使用 task_config.url
        url = action_params.get('url') or task.task_config.url
        if not url:
            return {
                "status": "error",
                "message": "Missing required parameter: url (not found in action_params or task_config)"
            }

        # 先启用响应拦截（在导航之前）
        self._response_handler_registered = False
        await self.action_intercept_response(task, {"enable": True})

        target_url = f"{url}/with_replies"
        logger.info(f"Navigating to: {target_url}")
        await task.page.goto(target_url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "Twitter user actor initialized",
            "actor": self.actor_name,
            "url": task.page.url,
            "title": await task.page.title()
        }

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "actor": self.actor_name,
            "resources_collected": len(self.resources),
            "interception_enabled": self._response_handler_registered
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务"""
        # 保存数据
        saved_path = None
        if self.resources:
            saved_path = await self._save_data(task)

        return {
            "status": "success",
            "message": "Twitter actor closed",
            "resources_collected": len(self.resources),
            "saved_to": saved_path
        }

    # ===== Twitter特定Actions =====

    async def action_intercept_response(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """启用/禁用响应拦截"""
        enable = action_params.get('enable', True)
        if enable:
            if not self._response_handler_registered:
                task.page.on("response", self._intercept_response)
                self._response_handler_registered = True
                logger.info("Response interception enabled")
        else:
            if self._response_handler_registered:
                task.page.remove_listener("response", self._intercept_response)
                self._response_handler_registered = False
                logger.info("Response interception disabled")

        return {
            "status": "success",
            "interception_enabled": enable
        }

    async def action_extract_tweets(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取已收集的推文数据"""
        max = action_params.get('max', 100)
        time_range = action_params.get('time_range', 24)

        count = min(len(self.resources), max)

        # 根据收集情况设置状态和消息
        if len(self.resources) == 0:
            result = {
                "status": "warning",
                "message": f"未收集到推文数据。可能原因：1) 账号在 {time_range} 小时内没有发推 2) time_range 设置过小 3) 页面加载失败",
                "total_collected": 0,
                "returned": 0,
                "tweets": [],
                "suggestion": f"建议增加 time_range 参数（当前: {time_range}h），或检查账号是否活跃"
            }
            logger.warning(f"[{task.task_config.name}] 未收集到推文数据，time_range={time_range}h")
            return result

        result = {
            "status": "success",
            "total_collected": len(self.resources),
            "returned": count,
            "tweets": []
        }

        # 添加时间范围信息
        if len(self.resources) > 0:
            oldest = self.resources[-1].resource_create_time
            newest = self.resources[0].resource_create_time
            result["time_range_info"] = {
                "time_range_hours": time_range,
                "oldest_tweet": oldest,
                "newest_tweet": newest
            }

        for i, resource in enumerate(self.resources[:count]):
            tweet_data = {
                "id": resource.id,
                "content": resource.resource_content,
                "author": resource.resource_author_name,
                "url": resource.resource_url,
                "created_at": resource.resource_create_time,
                "likes": resource.analytics.like_count if resource.analytics else 0,
                "replies": resource.analytics.reply_count if resource.analytics else 0,
                "retweets": resource.analytics.share_count if resource.analytics else 0
            }
            result["tweets"].append(tweet_data)

        # 使用 TaskStorage 保存
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            result["saved_to"] = str(raw_file)
            result["storage_stats"] = stats

        return result

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取推文"""
        scroll_times = action_params.get('scroll_times', 10)
        max = action_params.get('max', 100)
        time_range = action_params.get('time_range', 24)
        reset = action_params.get('reset', False)  # 默认保留已有数据

        # 确保响应拦截已启用
        if not self._response_handler_registered:
            await self.action_intercept_response(task, {"enable": True})

        # 根据 reset 参数决定是否重置收集器
        if reset:
            logger.info("重置收集器，开始新的抓取会话")
            self.resources = []
        else:
            logger.info(f"累加模式，当前已有 {len(self.resources)} 条数据")

        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = time_range

        # 滚动
        for i in range(scroll_times):
            if self.stop_scroll:
                logger.info(f"已获取{time_range}h内的数据，停止滚动")
                break

            logger.info(f"第 {i + 1} 次滚动...")
            await HumanUtils.smart_scroll(task.page, 1, 3)

        # 提取结果
        return await self.action_extract_tweets(task, {"max": max, "time_range": time_range})

    # ===== 响应拦截处理 =====

    async def _intercept_response(self, response: Response):
        """拦截API响应"""
        # 更灵活的 content-type 检查
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            if "/UserTweetsAndReplies" in response.url:
                logger.info(f"[拦截] /UserTweetsAndReplies {response.url[:100]}...")
                try:
                    data = await response.json()
                    resources = self.parse_user_tweets_and_replies(data)
                    logger.info(f"[拦截] 解析到 {len(resources)} 条推文")

                    if not resources:
                        return

                    # 统计时间范围过滤情况
                    time_range_hours = getattr(self, 'time_range', 24)
                    in_range_count = 0
                    out_of_range_count = 0

                    for r in resources:
                        if utils.time_within(r.resource_create_time, time_delta=time_range_hours):
                            self.resources.append(r)
                            in_range_count += 1
                        else:
                            self.out_time_time_number += 1
                            out_of_range_count += 1
                            logger.info(f"[拦截] 超出时间范围: {r.resource_create_time}")
                            if self.out_time_time_number >= self.out_time_max:
                                self.stop_scroll = True
                                logger.info(f"[拦截] 达到超时数量限制，停止滚动")

                    # 输出过滤统计
                    if out_of_range_count > 0:
                        logger.info(f"[拦截] 时间范围过滤: {in_range_count} 条在范围内，{out_of_range_count} 条超出范围 ({time_range_hours}h)")
                except Exception as e:
                    logger.error(f"[拦截] 解析响应失败: {e}")

    # ===== 数据解析方法 =====

    def parse_user_tweets_and_replies(self, data: dict) -> List[Resource]:
        """解析用户推文和回复"""
        instructions = jmespath.search('data.user.result.timeline_v2.timeline.instructions', data)
        if not instructions:
            instructions = jmespath.search('data.user.result.timeline.timeline.instructions', data)

        if not instructions:
            logger.info("No timeline instructions found")
            return []

        tweets = []
        for instruction in instructions:
            instruction_type = instruction.get('type')

            if instruction_type == 'TimelinePinEntry':
                pin_tweet_result = jmespath.search('entry.content.itemContent.tweet_results.result', instruction)
                tweet = self._extract_original_tweet_data(pin_tweet_result)
                tweet.is_pinned = True
                tweets.append(tweet)

            if instruction_type == 'TimelineAddEntries':
                entries = instruction.get('entries', [])

                for entry in entries:
                    entryId: str = entry.get("entryId", "")
                    if entryId.startswith("tweet"):
                        tweet_result = jmespath.search('content.itemContent.tweet_results.result', entry)
                        tweet_type = tweet_result.get('legacy', {}).get("retweeted_status_result", {})
                        if tweet_type != {}:
                            tweet = self._extract_share_tweet_data(tweet_result)
                        else:
                            tweet = self._extract_original_tweet_data(tweet_result)
                        tweets.append(tweet)

                    if entryId.startswith("profile-conversation"):
                        conversation_data = entry.get("content", {}).get("items", [])
                        tweet = self._extract_conversation_tweet_data(conversation_data)
                        tweets.append(tweet)

        return tweets

    def _extract_common_tweet_data(self, tweet_result) -> Resource:
        """提取推文公共数据"""
        tweet_id = tweet_result.get('rest_id', '')

        user_result = tweet_result.get('core', {}).get('user_results', {}).get('result', {})
        author = self._extract_user_result(user_result)

        legacy = tweet_result.get('legacy', {})
        views = tweet_result.get('views', {})

        analytics = Analytics(
            view_count=int(views.get("count", "0")),
            like_count=legacy.get("favorite_count", 0),
            reply_count=legacy.get("reply_count", 0),
            share_count=legacy.get("retweet_count", 0),
            bookmark_count=legacy.get("bookmark_count", 0),
            referenced_count=legacy.get("quote_count", 0)
        )

        media = []
        extended_entities = legacy.get('extended_entities', {})
        for media_item in extended_entities.get('media', []):
            media_info = ResourceMedia(
                media_type=media_item.get('type', ''),
                media_url=media_item.get('media_url_https', '')
            )

            if media_item.get('type') == 'video':
                variants = media_item.get('video_info', {}).get('variants', [])
                video_variants = [v for v in variants if v.get('content_type') == 'video/mp4']
                if video_variants:
                    media_info.media_url = max(video_variants, key=lambda x: x.get('bitrate', 0))['url']

            media.append(media_info)

        hashtags = [ht.get('text', '') for ht in legacy.get('entities', {}).get('hashtags', [])]

        urls = []
        for url_entity in legacy.get('entities', {}).get('urls', []):
            urls.append({
                'url': url_entity.get('url', ''),
                'expanded_url': url_entity.get('expanded_url', ''),
            })

        note_tweet = tweet_result.get('note_tweet', {}).get('note_tweet_results', {}).get('result', {})
        if note_tweet.get("text", ""):
            resource_content = note_tweet.get("text", "")
        else:
            resource_content = legacy.get("full_text", "")

        resource = Resource(
            urls=urls,
            resource_media=media,
            hashtags=hashtags,
            resource_type="",
            id=tweet_id,
            resource_url=f"{author.author_url}/status/{tweet_id}",
            resource_content=resource_content,
            resource_platform="X/Twitter",
            resource_platform_url="https://x.com",
            resource_author_name=author.author_name,
            resource_author_display_name=author.author_display_name,
            resource_author_url=author.author_url,
            is_pinned=False,
            analytics=analytics,
            resource_create_time=legacy.get("created_at", "")
        )
        return resource

    def _extract_original_tweet_data(self, tweet_result) -> Resource:
        """提取原创推文数据"""
        resource = self._extract_common_tweet_data(tweet_result)
        resource.resource_type = "original"

        quoted_status_result = tweet_result.get('quoted_status_result', {}).get("result", {})
        if quoted_status_result != {}:
            reference = self._extract_original_tweet_data(quoted_status_result)
            resource.reference_resource.append(reference)

        return resource

    def _extract_share_tweet_data(self, tweet_result) -> Resource:
        """提取转推推文数据"""
        resource = self._extract_common_tweet_data(tweet_result)
        resource.resource_type = "share"

        retweeted_status_result = tweet_result.get('legacy', {}).get("retweeted_status_result", {}).get("result", {})
        if retweeted_status_result != {}:
            shared_tweet = self._extract_original_tweet_data(retweeted_status_result)
            resource.share_resource.append(shared_tweet)

        return resource

    def _extract_conversation_tweet_data(self, conversation_data) -> Resource:
        """提取对话推文数据"""
        tweets = []
        for conversation_item in conversation_data:
            tweet_result = jmespath.search('item.itemContent.tweet_results.result', conversation_item)
            tweet_type = tweet_result.get('legacy', {}).get("retweeted_status_result", {})
            if tweet_type != {}:
                tweet = self._extract_share_tweet_data(tweet_result)
            else:
                tweet = self._extract_original_tweet_data(tweet_result)
            tweets.append(tweet)

        resource: Resource = tweets[-1]
        resource.resource_type = "conversation"
        resource.conversation_resource = tweets[0:-1]
        return resource

    def _extract_user_result(self, user_result) -> Author:
        """提取用户数据"""
        user_legacy = user_result.get('legacy', {})
        user_core = user_result.get('core', {})
        name = user_core.get('screen_name', '')
        display_name = user_core.get('name', '')

        return Author(
            id=user_result.get('rest_id', ''),
            author_url=f"https://x.com/{name}",
            author_name=name,
            author_display_name=display_name,
            followers_count=user_legacy.get("followers_count", 0),
            following_count=user_legacy.get("following_count", 0),
            description=""
        )

    # ===== 数据保存 =====

    async def _save_data(self, task) -> str:
        """保存收集的数据"""
        if not self.resources:
            logger.warning(f"[{self.actor_name}] No resources to save")
            return None

        try:
            from core.task_storage import TaskStorage
            storage = TaskStorage()

            # 1. 保存原始JSON
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)

            # 2. 合并到数据库
            stats = storage.merge_to_database(task.task_config.name, self.resources)

            logger.info(
                f"[{self.actor_name}] Data saved: "
                f"raw={raw_file.name}, "
                f"added={stats['added']}, "
                f"skipped={stats['skipped']}"
            )

            return str(raw_file)
        except Exception as e:
            logger.error(f"[{self.actor_name}] Error saving data: {e}")
            return None
