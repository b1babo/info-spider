"""Reddit 单个帖子 Actor。

访问单个 Reddit 帖子并提取内容和评论。
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils
from core.utils import HumanUtils

logger = logging.getLogger(__name__)


class RedditPostActor(BaseActor):
    """Reddit 单个帖子 Actor"""

    actor_name = "reddit_post_actor"
    actor_description = "Reddit 单个帖子操作Actor"

    def setup_actions(self):
        """注册所有单个帖子相关的Actions"""

        self.register_action(
            "visit",
            self.action_visit,
            description="访问单个Reddit帖子URL并提取内容",
            params_schema={
                "params": [
                    {"name": "post_url", "type": "string", "required": True,
                     "description": "帖子URL，如 https://www.reddit.com/r/ClaudeAI/comments/1uts1ra/claude_code_turned_off_my_wifi_to_test_something/"},
                    {"name": "extract_comments", "type": "boolean", "required": False, "default": True,
                     "description": "是否提取评论"},
                    {"name": "max_comments", "type": "integer", "required": False, "default": 50,
                     "description": "最大评论数量"}
                ]
            }
        )

        self.register_action(
            "close",
            self.action_close,
            description="关闭任务实例并保存数据",
            params_schema={"params": []}
        )

        # 初始化内部状态
        self.resources: List[Resource] = []
        self.task_name: str = "single_reddit_post"  # 任务名称，用于保存数据

    async def action_visit(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """访问单个Reddit帖子并提取内容"""
        post_url = action_params.get('post_url')
        extract_comments = action_params.get('extract_comments', True)
        max_comments = action_params.get('max_comments', 50)

        if not post_url:
            return {
                "status": "error",
                "message": "Missing required parameter: post_url"
            }

        logger.info(f"[RedditPostActor] Visiting Reddit post: {post_url}")

        try:
            # 重置状态
            self.resources = []

            # 访问帖子页面
            await task.page.goto(post_url, timeout=60000)
            await asyncio.sleep(3)

            # 等待帖子加载
            try:
                await task.page.wait_for_selector('shreddit-post', timeout=10000)
            except:
                logger.warning("Reddit post selector not found")

            # 提取帖子内容
            post_data = await self._extract_single_post_from_page(task, post_url)

            if post_data:
                # 提取评论
                comments = []
                comment_resources = []
                if extract_comments:
                    comments, comment_resources = await self._extract_comments_from_single_post(task, max_comments)

                # 将评论资源添加到帖子数据中
                post_data.comment_resource = comment_resources
                self.resources.append(post_data)

                # 保存数据
                saved_to = None
                storage_stats = None
                if self.resources:
                    from core.task_storage import TaskStorage
                    storage = TaskStorage()
                    raw_file = storage.save_raw_result(self.task_name, self.resources)
                    stats = storage.merge_to_database(self.task_name, self.resources)
                    saved_to = str(raw_file)
                    storage_stats = {
                        "total": stats.get('total', len(self.resources)),
                        "added": stats.get('added', 0),
                        "skipped": stats.get('skipped', 0),
                        "errors": stats.get('errors', 0)
                    }
                    logger.info(f"[RedditPostActor] 保存完成: raw={raw_file.name}, added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

                return {
                    "status": "success",
                    "post": {
                        "id": post_data.id,
                        "title": post_data.resource_content[:200] if post_data.resource_content else "",
                        "content": post_data.resource_content,
                        "author": post_data.resource_author_name,
                        "url": post_data.resource_url,
                        "likes": post_data.analytics.like_count if post_data.analytics else 0,
                        "comments_count": post_data.analytics.reply_count if post_data.analytics else 0,
                        "created_at": post_data.resource_create_time
                    },
                    "extracted_comments_count": len(comments),
                    "comments": comments[:10],  # 返回前10条作为预览
                    "saved_to": saved_to,
                    "storage_stats": storage_stats
                }
            else:
                return {
                    "status": "warning",
                    "message": "Post page loaded but content extraction failed",
                    "url": post_url
                }

        except Exception as e:
            logger.error(f"[RedditPostActor] Error visiting Reddit post {post_url}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "url": post_url
            }

    async def _extract_single_post_from_page(self, task, url: str) -> Optional[Resource]:
        """从页面提取单个帖子内容（与 RedditCommunityActor 保持一致）"""
        try:
            # 查找主帖子 - 使用 locator 而不是 query_selector
            post_element = task.page.locator("shreddit-post").first

            try:
                await post_element.wait_for(timeout=5000)
            except:
                logger.warning(f"Post element load timeout: {task.page.url}")
                return None

            # 提取基础元数据 - 使用与 RedditCommunityActor 相同的方式
            post_id = await post_element.get_attribute("id") or ""
            if post_id:
                post_id = post_id.replace('t3_', '')

            post_title = await post_element.get_attribute("post-title") or await task.page.title()
            author_name = await post_element.get_attribute("author") or "unknown"
            score = await post_element.get_attribute("score") or "0"
            comment_count = await post_element.get_attribute("comment-count") or "0"
            created_at = await post_element.get_attribute("created-timestamp") or ""
            content_href = await post_element.get_attribute("content-href") or ""

            # 提取正文 - 使用 locator 而不是 query_selector
            content_body = ""
            body_elem = post_element.locator("div[slot='text-body']")
            if await body_elem.count() > 0:
                content_body = await body_elem.inner_text()

            full_content = f"{post_title}\n\n{content_body}".strip()

            # 提取媒体
            media = await self._extract_media(post_element)

            # 提取 Flair (作为 Tag)
            hashtags = await self._extract_flair(post_element)

            # 提取 subreddit
            subreddit = ""
            try:
                import re
                subreddit_match = re.search(r'/r/([^/]+)', url)
                if subreddit_match:
                    subreddit = subreddit_match.group(1)
            except:
                pass

            # 构建对象
            analytics = Analytics(
                like_count=utils.convert_to_number(score),
                reply_count=utils.convert_to_number(comment_count)
            )

            # 提取 URL
            urls = []
            if content_href:
                urls.append({"url": content_href, "expanded_url": content_href})

            resource = Resource(
                id=post_id,
                resource_url=url,
                resource_content=full_content[:1500],
                resource_type="original",
                resource_platform="Reddit",
                resource_platform_url="https://www.reddit.com",
                resource_author_name=author_name,
                resource_author_display_name=author_name,
                resource_author_url=f"https://www.reddit.com/user/{author_name}/",
                analytics=analytics,
                resource_media=media,
                resource_create_time=created_at,
                urls=urls,
                hashtags=hashtags
            )

            return resource

        except Exception as e:
            logger.error(f"Error extracting post from page: {e}")
            return None

    async def _extract_media(self, post_element) -> List[ResourceMedia]:
        """提取媒体（与 RedditCommunityActor 完全一致）"""
        media = []
        try:
            images = await post_element.locator("img.preview-img, img[alt='Post image']").all()
            for img in images:
                src = await img.get_attribute("src")
                if src:
                    media.append(ResourceMedia(media_type="image", media_url=src))

            post_type = await post_element.get_attribute("post-type")
            if post_type == "video":
                content_href = await post_element.get_attribute("content-href")
                if content_href:
                    media.append(ResourceMedia(media_type="video", media_url=content_href))
        except Exception as e:
            logger.warning(f"提取媒体失败: {e}")
        return media

    async def _extract_flair(self, post_element) -> List[str]:
        """提取 Flair 作为 Tag（与 RedditCommunityActor 完全一致）"""
        hashtags = []
        try:
            flair_elem = post_element.locator("shreddit-post-flair[slot='post-flair']")
            if await flair_elem.count() > 0:
                flair_text = await flair_elem.inner_text()
                if flair_text:
                    hashtags.append(flair_text.strip())
            hashtags = list(set(hashtags))
        except Exception as e:
            logger.warning(f"提取 Flair 失败: {e}")
        return hashtags

    async def _extract_comments_from_single_post(self, task, max_comments: int) -> tuple[List[Dict[str, Any]], List[Resource]]:
        """从单个帖子页面提取评论（与 RedditCommunityActor 保持一致）

        Returns:
            tuple: (简化的评论字典列表, 完整的Resource对象列表)
        """
        comments = []
        comment_resources = []

        try:
            # 滚动加载更多评论
            for _ in range(3):
                await HumanUtils.smart_scroll(task.page, 1, 2)
                await asyncio.sleep(1)

            # 查找评论元素 - 使用与 RedditCommunityActor 相同的选择器
            comment_elements = await task.page.query_selector_all('shreddit-comment')

            logger.info(f"[RedditPostActor] Found {len(comment_elements)} comment elements")

            # 使用与 RedditCommunityActor 相同的递归方法处理每个评论
            for i, comment_elem in enumerate(comment_elements[:max_comments]):
                try:
                    comment_resource = await self._parse_single_comment(comment_elem, max_depth=1, max_per_level=0, current_depth=1)
                    if comment_resource:
                        comment_resources.append(comment_resource)

                        # 添加到简化列表（用于返回预览）
                        comments.append({
                            "index": i,
                            "author": comment_resource.resource_author_name,
                            "content": comment_resource.resource_content[:500],
                            "score": comment_resource.analytics.like_count if comment_resource.analytics else 0
                        })

                except Exception as e:
                    logger.warning(f"[RedditPostActor] Error extracting comment {i}: {e}")
                    continue

        except Exception as e:
            logger.error(f"[RedditPostActor] Error extracting comments: {e}")

        return comments, comment_resources

    async def _parse_single_comment(self, comment_elem, max_depth: int, max_per_level: int, current_depth: int) -> Optional[Resource]:
        """解析单个评论（与 RedditCommunityActor 完全一致）"""
        if current_depth > max_depth:
            return None

        try:
            # 使用与 RedditCommunityActor 相同的属性提取方式
            c_id = await comment_elem.get_attribute("id") or await comment_elem.get_attribute("thingid") or ""
            c_author = await comment_elem.get_attribute("author") or ""
            c_score = await comment_elem.get_attribute("score") or "0"

            # 提取评论内容 - 使用与 RedditCommunityActor 相同的 selector
            c_text = ""
            try:
                c_body_div = await comment_elem.query_selector("div[slot='comment']")
                if c_body_div:
                    c_text = await c_body_div.inner_text()
                else:
                    # 回退到整个元素的文本
                    c_text = await comment_elem.inner_text()
            except Exception:
                try:
                    c_text = await comment_elem.inner_text()
                except:
                    pass

            if not c_text or len(c_text.strip()) == 0:
                return None

            # 递归解析子评论 - 使用与 RedditCommunityActor 相同的方式
            child_comments = []
            if current_depth < max_depth:
                try:
                    child_elems = await comment_elem.query_selector_all("shreddit-comment")
                    if child_elems and len(child_elems) > 0:
                        for child_elem in child_elems[:max_per_level]:
                            child_comment = await self._parse_single_comment(child_elem, max_depth, max_per_level, current_depth + 1)
                            if child_comment:
                                child_comments.append(child_comment)
                except Exception as e:
                    logger.debug(f"[RedditPostActor] 解析子评论失败: {e}")

            return Resource(
                id=c_id,
                resource_url=f"https://www.reddit.com/user/{c_author}/",
                resource_content=c_text,
                resource_type="comment",
                resource_platform="Reddit",
                resource_platform_url="https://www.reddit.com",
                resource_author_name=c_author,
                resource_author_display_name=c_author,
                resource_author_url=f"https://www.reddit.com/user/{c_author}/",
                analytics=Analytics(
                    like_count=utils.convert_to_number(c_score),
                    reply_count=len(child_comments)
                ),
                comment_resource=child_comments
            )

        except Exception as e:
            logger.debug(f"[RedditPostActor] 解析单个评论失败: {e}")
            return None

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务实例并保存数据"""
        # 保存数据
        saved_to = None
        storage_stats = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(self.task_name, self.resources)
            stats = storage.merge_to_database(self.task_name, self.resources)
            saved_to = str(raw_file)
            storage_stats = {
                "total": stats.get('total', len(self.resources)),
                "added": stats.get('added', 0),
                "skipped": stats.get('skipped', 0),
                "errors": stats.get('errors', 0)
            }
            logger.info(f"[RedditPostActor] 保存完成: raw={raw_file.name}, added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

        # 关闭页面
        try:
            await task.page.close()
            logger.info(f"[RedditPostActor] 页面已关闭")
        except Exception as e:
            logger.warning(f"[RedditPostActor] 关闭页面时出错: {e}")

        return {
            "status": "success",
            "message": "Reddit post actor 已关闭",
            "resources_collected": len(self.resources),
            "saved_to": saved_to,
            "storage_stats": storage_stats
        }
