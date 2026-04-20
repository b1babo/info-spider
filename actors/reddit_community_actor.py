"""
Reddit Community Actor - 异步版本
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils
from core.utils import HumanUtils

import jmespath

logger = logging.getLogger(__name__)


class RedditCommunityActor(BaseActor):
    """Reddit社区帖子Actor"""

    actor_name = "reddit_community_actor"
    actor_description = "Reddit社区帖子操作Actor"

    def setup_actions(self):
        """注册所有Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="创建Reddit社区任务",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "社区URL"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动并提取帖子",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10},
                    {"name": "max", "type": "integer", "required": False, "default": 50},
                    {"name": "max_comments_depth", "type": "integer", "required": False, "default": 2},
                    {"name": "max_comments_per_level", "type": "integer", "required": False, "default": 3},
                    {"name": "reset", "type": "boolean", "required": False, "default": True}
                ]
            }
        )

        self.register_action(
            "extract_posts",
            self.action_extract_posts,
            description="提取已收集的帖子",
            params_schema={
                "params": [
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
            description="关闭任务",
            params_schema={"params": []}
        )

        # 状态变量
        self.resources: List[Resource] = []
        self.processed_ids = set()

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务"""
        url = action_params.get('url')

        logger.info(f"Navigating to: {url}")
        await task.page.goto(url, timeout=60000)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "url": task.page.url,
            "title": await task.page.title()
        }

    async def action_scroll_and_extract(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """滚动并提取帖子"""
        scroll_times = action_params.get('scroll_times', 10)
        max_items = action_params.get('max', 50)
        max_comments_depth = action_params.get('max_comments_depth', 2)
        max_comments_per_level = action_params.get('max_comments_per_level', 3)
        reset = action_params.get('reset', True)

        if reset:
            self.resources = []
            self.processed_ids = set()

        logger.info(f"开始抓取: scroll_times={scroll_times}, max={max_items}")

        for i in range(scroll_times):
            if len(self.resources) >= max_items:
                logger.info(f"已达到最大采集数量 {max_items}，停止滚动")
                break

            logger.info(f"Scroll {i + 1}")
            await self._process_current_posts(task, max_items, max_comments_depth, max_comments_per_level)

            if len(self.resources) < max_items:
                await HumanUtils.smart_scroll(task.page, 1, 2)
                await asyncio.sleep(2)

        return await self.action_extract_posts(task, {"max": max_items})

    async def _process_current_posts(self, task, max_items: int, max_comments_depth: int, max_comments_per_level: int):
        """处理当前可见的帖子"""
        try:
            posts_locators = await task.page.locator("shreddit-post").all()
            logger.info(f"   扫描到 {len(posts_locators)} 个帖子")

            for post_loc in posts_locators:
                if len(self.resources) >= max_items:
                    break

                try:
                    p_id = await post_loc.get_attribute("id")
                    permalink = await post_loc.get_attribute("permalink")

                    if not p_id or not permalink:
                        continue

                    if p_id in self.processed_ids:
                        continue

                    logger.info(f"   处理帖子: {p_id}")
                    resource = await self._fetch_post_detail(task, permalink, max_comments_depth, max_comments_per_level)

                    if resource:
                        self.resources.append(resource)
                        self.processed_ids.add(p_id)
                        logger.info(f"   ✅ 抓取成功 (正文长度: {len(resource.resource_content)})")

                    await asyncio.sleep(1)  # 速率限制

                except Exception as e:
                    logger.warning(f"   处理帖子失败: {e}")
                    continue

        except Exception as e:
            logger.error(f"扫描帖子列表失败: {e}")

    async def _fetch_post_detail(self, task, permalink: str, max_depth: int, max_per_level: int) -> Optional[Resource]:
        """获取帖子详情"""
        detail_url = f"https://www.reddit.com{permalink}"
        detail_page = None

        try:
            detail_page = await task.page.context.new_page()
            await detail_page.goto(detail_url, timeout=30000)
            await asyncio.sleep(1)

            resource = await self._parse_detail_page(detail_page, permalink, max_depth, max_per_level)
            return resource

        except Exception as e:
            logger.warning(f"获取详情失败 {detail_url}: {e}")
            return None
        finally:
            if detail_page:
                try:
                    await detail_page.close()
                except:
                    pass

    async def _parse_detail_page(self, page: Page, permalink: str, max_depth: int, max_per_level: int) -> Optional[Resource]:
        """解析详情页"""
        try:
            post_element = page.locator("shreddit-post").first

            try:
                await post_element.wait_for(timeout=5000)
            except:
                logger.warning(f"详情页加载超时: {page.url}")
                return None

            # 提取基础元数据
            post_id = await post_element.get_attribute("id") or ""
            post_title = await post_element.get_attribute("post-title") or await page.title()
            author_name = await post_element.get_attribute("author") or "unknown"
            score = await post_element.get_attribute("score") or "0"
            comment_count = await post_element.get_attribute("comment-count") or "0"
            created_at = await post_element.get_attribute("created-timestamp") or ""
            content_href = await post_element.get_attribute("content-href") or ""

            resource_url = f"https://www.reddit.com{permalink}"

            # 提取正文
            content_body = ""
            body_elem = post_element.locator("div[slot='text-body']")
            if await body_elem.count() > 0:
                content_body = await body_elem.inner_text()

            full_content = f"{post_title}\n\n{content_body}".strip()

            # 提取媒体
            media = await self._extract_media(post_element)

            # 提取 Flair (作为 Tag)
            hashtags = await self._extract_flair(post_element)

            # 构建对象
            analytics = Analytics(
                like_count=utils.convert_to_number(score),
                reply_count=utils.convert_to_number(comment_count)
            )

            author = Author(
                id=author_name,
                author_name=author_name,
                author_display_name=author_name,
                author_url=f"https://www.reddit.com/user/{author_name}/"
            )

            # 提取评论
            comments_tree = await self._parse_comments(page, max_depth, max_per_level)

            resource = Resource(
                comment_resource=comments_tree,
                hashtags=hashtags,
                id=post_id,
                resource_content=full_content,
                description=post_title,
                resource_url=resource_url,
                resource_type="original",
                resource_platform="Reddit",
                resource_platform_url="https://www.reddit.com",
                resource_author_name=author.author_name,
                resource_author_display_name=author.author_display_name,
                resource_author_url=author.author_url,
                analytics=analytics,
                resource_media=media,
                resource_create_time=created_at,
                urls=[{"url": content_href, "expanded_url": content_href}] if content_href else []
            )

            return resource

        except Exception as e:
            logger.error(f"解析详情页出错 {page.url}: {e}")
            return None

    async def _extract_media(self, post_element) -> List[ResourceMedia]:
        """提取媒体"""
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
        """提取 Flair 作为 Tag"""
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

    async def _parse_comments(self, page: Page, max_depth: int, max_per_level: int, current_depth: int = 1) -> List[Resource]:
        """递归解析评论"""
        if current_depth > max_depth:
            return []

        parsed_comments = []

        try:
            # 查找评论
            if current_depth == 1:
                comment_locators = await page.locator("shreddit-comment-tree > shreddit-comment").all()
            else:
                # 对于嵌套评论，使用不同的选择器
                comment_locators = await page.locator("shreddit-comment").all()

            if len(comment_locators) > max_per_level:
                comment_locators = comment_locators[:max_per_level]

            for comment_elem in comment_locators:
                try:
                    c_id = await comment_elem.get_attribute("id") or await comment_elem.get_attribute("thingid") or ""
                    c_author = await comment_elem.get_attribute("author") or ""
                    c_score = await comment_elem.get_attribute("score") or "0"

                    # 提取评论内容 - 使用 .first 只获取第一个匹配（评论自己的内容）
                    c_text = ""
                    try:
                        c_body_div = comment_elem.locator("div[slot='comment']").first
                        if await c_body_div.count() > 0:
                            c_text = await c_body_div.inner_text()
                    except Exception as e:
                        # 如果 first 也失败了，尝试用其他方式获取
                        try:
                            c_body_div = comment_elem.locator("div[slot='comment']").nth(0)
                            c_text = await c_body_div.inner_text()
                        except:
                            logger.debug(f"无法提取评论 {c_id} 的内容: {e}")

                    if not c_text:
                        continue

                    # 递归解析子评论 - 只处理当前评论的子评论
                    child_comments = []
                    if current_depth < max_depth:
                        try:
                            child_locators = await comment_elem.locator("shreddit-comment").all()
                            if child_locators:
                                # 为每个子评论创建资源对象
                                for child_elem in child_locators[:max_per_level]:
                                    child_comment = await self._parse_single_comment(child_elem, max_depth, max_per_level, current_depth + 1)
                                    if child_comment:
                                        child_comments.append(child_comment)
                        except Exception as e:
                            logger.debug(f"解析子评论失败: {e}")

                    comment_obj = Resource(
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
                    parsed_comments.append(comment_obj)

                except Exception as e:
                    logger.warning(f"解析单条评论失败: {e}")
                    continue

        except Exception as e:
            logger.warning(f"解析评论失败 (depth={current_depth}): {e}")

        return parsed_comments

    async def _parse_single_comment(self, comment_elem, max_depth: int, max_per_level: int, current_depth: int) -> Optional[Resource]:
        """解析单个评论（用于递归）"""
        if current_depth > max_depth:
            return None

        try:
            c_id = await comment_elem.get_attribute("id") or await comment_elem.get_attribute("thingid") or ""
            c_author = await comment_elem.get_attribute("author") or ""
            c_score = await comment_elem.get_attribute("score") or "0"

            # 提取评论内容
            c_text = ""
            try:
                c_body_div = comment_elem.locator("div[slot='comment']").first
                if await c_body_div.count() > 0:
                    c_text = await c_body_div.inner_text()
            except Exception:
                try:
                    c_body_div = comment_elem.locator("div[slot='comment']").nth(0)
                    c_text = await c_body_div.inner_text()
                except:
                    pass

            if not c_text:
                return None

            # 递归解析子评论
            child_comments = []
            if current_depth < max_depth:
                try:
                    child_locators = await comment_elem.locator("shreddit-comment").all()
                    if child_locators:
                        for child_elem in child_locators[:max_per_level]:
                            child_comment = await self._parse_single_comment(child_elem, max_depth, max_per_level, current_depth + 1)
                            if child_comment:
                                child_comments.append(child_comment)
                except:
                    pass

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
            logger.debug(f"解析单个评论失败: {e}")
            return None

    async def action_extract_posts(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取已收集的帖子"""
        max_items = action_params.get('max', 100)
        count = min(len(self.resources), max_items)

        result = {
            "status": "success",
            "total_collected": len(self.resources),
            "returned": count,
            "posts": []
        }

        for i, resource in enumerate(self.resources[:count]):
            result["posts"].append({
                "id": resource.id,
                "title": resource.description,
                "content": resource.resource_content[:200] + "..." if len(resource.resource_content) > 200 else resource.resource_content,
                "author": resource.resource_author_name,
                "url": resource.resource_url,
                "likes": resource.analytics.like_count if resource.analytics else 0,
                "comments": resource.analytics.reply_count if resource.analytics else 0,
                "hashtags": resource.hashtags
            })

        # 保存数据
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            result["saved_to"] = str(raw_file)
            result["storage_stats"] = stats

        return result

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "resources_collected": len(self.resources),
            "processed_ids": len(self.processed_ids)
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务"""
        saved_path = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(task.task_config.name, self.resources)
            stats = storage.merge_to_database(task.task_config.name, self.resources)
            logger.info(f"Data saved: added={stats['added']}, skipped={stats['skipped']}")
            saved_path = str(raw_file)

        return {
            "status": "success",
            "resources_collected": len(self.resources),
            "saved_to": saved_path
        }
