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
            "fetch_tweets",
            self.action_fetch_tweets,
            description="导航到用户帖子列表页面（/with_replies）",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": False, "description": "用户主页URL，如 https://x.com/GitHub_Daily"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动当前页面并提取内容，返回存储路径和统计数据",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10, "description": "滚动次数"},
                    {"name": "max", "type": "integer", "required": False, "default": 100, "description": "最大提取数量"},
                    {"name": "time_range", "type": "integer", "required": False, "default": 24, "description": "时间范围(小时)，推文默认24h，文章默认720h"},
                    {"name": "reset", "type": "boolean", "required": False, "default": True, "description": "是否重置已收集的数据"},
                    {"name": "fetch_body", "type": "boolean", "required": False, "default": True, "description": "是否抓取完整正文（仅文章页面有效）"}
                ]
            }
        )

        self.register_action(
            "fetch_articles",
            self.action_fetch_articles,
            description="抓取用户文章列表",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 20, "description": "最多抓取文章数"},
                    {"name": "time_range", "type": "integer", "required": False, "default": 720, "description": "时间范围(小时)"},
                    {"name": "fetch_body", "type": "boolean", "required": False, "default": True, "description": "是否抓取完整正文"},
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 30, "description": "列表滚动次数"}
                ]
            }
        )

        # 初始化内部状态
        self.resources: List[Resource] = []
        self._response_handler_registered = False
        self._article_intercept_registered = False  # 文章拦截器注册状态
        self.out_time_time_number = 0
        self.out_time_max = 5
        self.stop_scroll = False
        self.time_range = 24

    # ===== 任务管理Actions =====

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务并导航到用户主页"""
        # 优先使用 action_params 中的 url，否则使用 task_config.url
        url = action_params.get('url') or task.task_config.url
        if not url:
            return {
                "status": "error",
                "message": "Missing required parameter: url (not found in action_params or task_config)"
            }

        # 清理 URL，移除已有的路径
        import re
        clean_url = re.sub(r'(x\.com/[^/?]+).*', r'\1', url)
        if not clean_url.startswith('http'):
            clean_url = url

        logger.info(f"[create] 导航到用户主页: {clean_url}")
        await task.page.goto(clean_url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "Twitter user actor initialized",
            "actor": self.actor_name,
            "url": task.page.url,
            "title": await task.page.title()
        }

    async def action_fetch_tweets(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """导航到用户帖子列表页面（/with_replies）"""
        url = action_params.get('url') or task.task_config.url
        if not url:
            # 从当前页面 URL 提取用户名
            current_url = task.page.url
            if not current_url:
                return {
                    "status": "error",
                    "message": "无法确定用户页面，请提供 url 参数"
                }
            import re
            username_match = re.search(r'x\.com/([^/?]+)', current_url)
            if not username_match:
                return {
                    "status": "error",
                    "message": "无法从当前页面提取用户名"
                }
            username = username_match.group(1)
            url = f"https://x.com/{username}"

        # 清理 URL，移除已有的路径
        import re
        clean_url = re.sub(r'(x\.com/[^/?]+).*', r'\1', url)
        tweets_url = f"{clean_url}/with_replies"

        # 启用推文响应拦截
        if not self._response_handler_registered:
            await self.action_intercept_response(task, {"enable": True})

        logger.info(f"[fetch_tweets] 导航到帖子列表页面: {tweets_url}")
        await task.page.goto(tweets_url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "已导航到帖子列表页面",
            "url": task.page.url,
            "page_type": "tweets"
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
        """彻底关闭任务并关闭页面"""
        # 关闭页面
        try:
            await task.page.close()
            logger.info(f"[close] 页面已关闭")
        except Exception as e:
            logger.warning(f"[close] 关闭页面时出错: {e}")

        return {
            "status": "success",
            "message": "Twitter actor 已彻底关闭",
            "resources_collected": len(self.resources)
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

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动页面并提取内容（自动判断推文页面或文章页面）"""
        scroll_times = action_params.get('scroll_times', 10)
        max = action_params.get('max', 100)
        time_range = action_params.get('time_range', 24)
        reset = action_params.get('reset', False)  # 默认保留已有数据
        fetch_body = action_params.get('fetch_body', True)  # 仅对文章有效

        # 检测当前页面类型
        current_url = task.page.url
        is_article_page = current_url and '/articles' in current_url

        logger.info(f"[scroll_and_extract] 当前页面: {current_url}")
        logger.info(f"[scroll_and_extract] 页面类型: {'文章列表页面' if is_article_page else '推文页面'}")

        if is_article_page:
            # 文章页面处理逻辑
            return await self._scroll_and_extract_articles(task, {
                'scroll_times': scroll_times,
                'max': max,
                'time_range': time_range,
                'fetch_body': fetch_body,
                'reset': reset
            })
        else:
            # 推文页面处理逻辑
            return await self._scroll_and_extract_tweets(task, {
                'scroll_times': scroll_times,
                'max': max,
                'time_range': time_range,
                'reset': reset
            })

    async def _scroll_and_extract_tweets(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动推文页面并提取推文"""
        scroll_times = action_params.get('scroll_times', 10)
        max = action_params.get('max', 100)
        time_range = action_params.get('time_range', 24)
        reset = action_params.get('reset', False)

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

            logger.info(f"[推文] 第 {i + 1} 次滚动...")
            await HumanUtils.smart_scroll(task.page, 1, 3)

        # 提取结果并保存数据
        tweet_count = min(len(self.resources), max)

        # 保存数据
        saved_to = None
        stats = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            saved_to = str(raw_file)
            logger.info(f"[推文] 保存完成: raw={raw_file.name}, added={stats['added']}, skipped={stats['skipped']}")

        return {
            "status": "success",
            "page_type": "tweets",
            "total_collected": tweet_count,
            "time_range_hours": time_range,
            "saved_to": saved_to,
            "storage_stats": stats
        }

    async def _scroll_and_extract_articles(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动文章页面并提取文章"""
        scroll_times = action_params.get('scroll_times', 10)
        max_items = action_params.get('max', 20)
        time_range = action_params.get('time_range', 720)
        fetch_body = action_params.get('fetch_body', True)
        reset = action_params.get('reset', False)

        logger.info(f"[文章滚动] 开始抓取，max={max_items}, time_range={time_range}h, fetch_body={fetch_body}")

        # **关键修复**：设置实例变量供拦截器使用
        self.time_range = time_range

        # 根据 reset 参数决定是否重置收集器（仅重置文章类型的资源）
        if reset:
            logger.info("[文章滚动] 重置文章收集器")
            # 只移除文章类型的资源，保留推文
            self.resources = [r for r in self.resources if r.resource_type != "article"]
        else:
            article_count = len([r for r in self.resources if r.resource_type == "article"])
            logger.info(f"[文章滚动] 累加模式，当前已有 {article_count} 篇文章")

        # 滚动加载文章列表（拦截器已经在 fetch_articles 中注册）
        for i in range(scroll_times):
            article_resources = [r for r in self.resources if r.resource_type == "article"]
            if len(article_resources) >= max_items:
                logger.info(f"[文章滚动] 已达到最大数量 {max_items}，停止滚动")
                break
            logger.info(f"[文章滚动] 第 {i + 1} 次滚动...")
            await HumanUtils.smart_scroll(task.page, 1, 3)
            await asyncio.sleep(1)  # 等待拦截器处理响应

        # 限制最终数量
        article_resources = [r for r in self.resources if r.resource_type == "article"][:max_items]
        logger.info(f"[文章滚动] 列表收集完成，共 {len(article_resources)} 篇文章")

        # 逐篇抓取完整正文
        if fetch_body and article_resources:
            logger.info(f"[文章滚动] 开始抓取 {len(article_resources)} 篇文章的完整正文")
            await self._fetch_all_article_bodies(task, article_resources)

        # 保存数据
        saved_to = None
        stats = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            saved_to = str(raw_file)
            logger.info(f"[文章滚动] 保存完成: raw={raw_file.name}, added={stats['added']}, skipped={stats['skipped']}")

        return {
            "status": "success",
            "page_type": "articles",
            "total_collected": len(article_resources),
            "time_range_hours": time_range,
            "saved_to": saved_to,
            "storage_stats": stats
        }

    async def action_fetch_articles(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """导航到用户文章列表页面（/articles）"""
        # 获取用户名从当前URL或参数
        url = action_params.get('url') or task.task_config.url
        if not url:
            # 从当前页面 URL 提取用户名
            current_url = task.page.url
            if not current_url:
                return {
                    "status": "error",
                    "message": "无法确定用户页面，请先使用 create action 或提供 url 参数"
                }
            import re
            username_match = re.search(r'x\.com/([^/?]+)', current_url)
            if not username_match:
                return {
                    "status": "error",
                    "message": "无法从当前页面提取用户名"
                }
            username = username_match.group(1)
            url = f"https://x.com/{username}"

        # 清理 URL，移除已有的路径
        import re
        clean_url = re.sub(r'(x\.com/[^/?]+).*', r'\1', url)
        articles_url = f"{clean_url}/articles"

        # **关键修复**：在导航到文章页面之前就注册文章拦截器
        self._enable_article_intercept(task)

        logger.info(f"[fetch_articles] 导航到文章列表页面: {articles_url}")
        await task.page.goto(articles_url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "已导航到文章列表页面",
            "url": task.page.url,
            "page_type": "articles"
        }

    def _enable_article_intercept(self, task):
        """启用文章响应拦截器"""
        if self._article_intercept_registered:
            logger.info("[文章拦截] 拦截器已注册，跳过")
            return

        task.page.on("response", self._intercept_article_listing)
        self._article_intercept_registered = True
        logger.info("[文章拦截] 文章响应拦截已启用")

    async def _intercept_article_listing(self, response: Response):
        """拦截文章列表响应"""
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return
        if "/graphql/" not in response.url:
            return

        # **关键修复**：检查是否是文章响应
        if "UserArticlesTweets" not in response.url:
            return

        logger.info(f"[文章拦截] 📥 检测到文章响应 URL: {response.url[:80]}...")

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
            logger.debug(f"[文章拦截] ❌ 没有解析到文章数据")
            return

        logger.info(f"[文章拦截] ✅ 解析到 {len(resources)} 篇文章")

        in_range = 0
        out_range = 0
        for r in resources:
            # 按文章 id 去重
            if any(existing.id == r.id for existing in self.resources):
                logger.debug(f"[文章拦截] 跳过重复: {r.id}")
                continue

            # **暂时禁用时间范围检查，先验证数据抓取**
            # 文章发布时间通常较早，暂时使用90天范围
            if utils.time_within(r.resource_create_time, time_delta=2160):  # 90天
                self.resources.append(r)
                in_range += 1
                logger.info(f"[文章拦截] ✅ 添加文章: {r.id} - {r.description[:40] if r.description else 'N/A'}")
            else:
                self.out_time_time_number += 1
                out_range += 1
                logger.info(f"[文章拦截] ⏰ 超时间范围: {r.resource_create_time} (范围: 2160h)")
                if self.out_time_time_number >= self.out_time_max:
                    self.stop_scroll = True
        if out_range > 0:
            logger.info(f"[文章拦截] 时间范围过滤: {in_range} 篇在范围内，{out_range} 篇超出范围 (2160h)")

        logger.info(f"[文章拦截] 📊 处理结果: {in_range} 篇文章被添加，{out_range} 篇文章超出范围")

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

    # ===== 文章抓取方法 (从 TwitterArticleActor 迁移) =====

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

            # 重建正文 Markdown (简化版，不完整实现 Draft.js 转换)
            body_md = ""
            inline_media: List[ResourceMedia] = []
            if full_body and content_state.get('blocks'):
                # 简化处理：提取文本内容
                blocks = content_state.get('blocks', [])
                texts = [block.get('text', '') for block in blocks if block.get('text')]
                body_md = "\n\n".join(texts)

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
            logger.error(f"[build_article_resource] 构建文章 Resource 失败: {e}")
            return None

    async def _fetch_all_article_bodies(self, task, article_resources: List[Resource]):
        """逐篇抓取文章完整正文"""
        total = len(article_resources)
        for idx, resource in enumerate(article_resources, 1):
            logger.info(f"[fetch_articles] ({idx}/{total}) 抓取正文: {resource.id} - {resource.description[:40] if resource.description else ''}")
            article_detail = await self._fetch_full_article_body(task, resource)
            if article_detail:
                updated = self._build_article_resource(article_detail, full_body=True)
                if updated:
                    # 更新资源内容
                    resource.resource_content = updated.resource_content
                    resource.resource_media = updated.resource_media
                    logger.info(f"[fetch_articles] 成功: {resource.id} (正文 {len(updated.resource_content)} 字符)")
                    continue
            logger.warning(f"[fetch_articles] 失败（正文为空）: {resource.id}")

    async def _fetch_full_article_body(self, task, resource: Resource) -> Optional[dict]:
        """导航到单条文章 status 页，获取完整正文"""
        detail_article = None
        detail_event = asyncio.Event()

        async def on_resp(response: Response):
            nonlocal detail_article
            ct = response.headers.get("content-type", "")
            if "application/json" not in ct or "/graphql/" not in response.url:
                return
            try:
                data = await response.json()
                result = self._find_article_tweet_result(data)
                blocks = jmespath.search('article.article_results.result.content_state.blocks', result) if result else None
                logger.debug(f"[fetch_articles] on_resp has_article={bool(result)} blocks={len(blocks) if blocks else 0}")
                if result and blocks:
                    detail_article = result
                    if detail_event:
                        detail_event.set()
            except Exception as e:
                logger.debug(f"[fetch_articles] on_resp error: {e}")

        task.page.on("response", on_resp)
        try:
            try:
                await task.page.goto(resource.resource_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.debug(f"[fetch_articles] goto 提示: {e}")
            try:
                await asyncio.wait_for(detail_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning(f"[fetch_articles] 详情响应超时: {resource.id}")
            await asyncio.sleep(1)
        finally:
            try:
                task.page.remove_listener("response", on_resp)
            except Exception:
                pass
        return detail_article

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
