"""
Product Hunt API Actor - 纯API模式（无需浏览器）
"""
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core import utils

from utils.product_hunt_api_client import ProductHunt

logger = logging.getLogger(__name__)


class ProductHuntActor(BaseActor):
    """Product Hunt API Actor - 无需浏览器，纯API调用"""

    actor_name = "product_hunt_actor"
    actor_description = "Product Hunt API操作Actor（无需浏览器）"

    def setup_actions(self):
        """注册所有Actions"""

        self.register_action(
            "fetch_posts",
            self.action_fetch_posts,
            description="获取产品列表",
            params_schema={
                "params": [
                    {"name": "days_back", "type": "integer", "required": False, "default": 1},
                    {"name": "per_page", "type": "integer", "required": False, "default": 20},
                    {"name": "topic", "type": "string", "required": False, "default": ""}
                ]
            }
        )

        self.register_action(
            "extract_posts",
            self.action_extract_posts,
            description="提取已收集的产品",
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
        self.api_client: ProductHunt = None

    async def action_fetch_posts(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取产品列表"""
        days_back = action_params.get('days_back', 1)
        per_page = action_params.get('per_page', 20)
        topic = action_params.get('topic', "")

        api_key = task.profile.params.get("api_key", "")
        if not api_key:
            return {
                "status": "error",
                "message": "API key not found in profile params"
            }

        logger.info(f"Fetching Product Hunt posts: days_back={days_back}, per_page={per_page}, topic={topic}")

        # 初始化 API 客户端
        if not self.api_client:
            self.api_client = ProductHunt(api_key=api_key)

        # 计算日期范围
        today = datetime.now(timezone.utc)
        date_from = today - timedelta(days=days_back)
        date_to = today

        # 调用 API
        product_list = self.api_client.query_posts_data(
            date_from=date_from,
            date_to=date_to,
            per_page=per_page,
            topic=topic
        )

        logger.info(f"API returned {len(product_list)} products")

        # 解析产品数据
        for product in product_list:
            resource = self._parse_product(product)
            if resource:
                self.resources.append(resource)

        return {
            "status": "success",
            "fetched": len(product_list),
            "total_collected": len(self.resources)
        }

    def _parse_product(self, product: dict) -> Resource:
        """解析单个产品数据"""
        try:
            # 解析媒体
            resource_media = []
            for media_item in product.get("media", []):
                if media_item.get("type", "") == "image":
                    resource_media.append(ResourceMedia(
                        media_type="image",
                        media_url=media_item.get("url", "")
                    ))
                elif media_item.get("type", "") == "video":
                    resource_media.append(ResourceMedia(
                        media_type="video",
                        media_url=media_item.get("videoUrl", "")
                    ))

            # 解析主题标签
            topics = []
            for tp in product.get("topics", {}).get("edges", []):
                topic = tp.get("node", {})
                topics.append(topic.get("slug"))

            # 解析评论
            comments = []
            for ct in product.get("comments", {}).get("edges", []):
                comment = ct.get("node", {})
                c_content = comment.get("body", "")
                c_url = utils.remove_query_params(comment.get("url", ""))

                c = Resource(
                    resource_content=c_content,
                    id=comment.get("id", ""),
                    resource_url=c_url,
                    analytics=Analytics(
                        like_count=comment.get('votesCount', 0),
                    ),
                    resource_author_name=comment.get("userId", ""),
                    resource_type="comment",
                    resource_platform="Product Hunt",
                    resource_platform_url="https://www.producthunt.com",
                )
                comments.append(c)

            # 构建产品内容
            w_url = utils.remove_query_params(product.get('website', ''))
            resource_content = f"#{product.get('name')} - {product.get('tagline')}\n## description\n  {product.get('description')}\n## website\n  {w_url}"

            r_url = utils.remove_query_params(product.get("url", ""))

            return Resource(
                resource_create_time=product.get("createdAt", ""),
                description=product.get('description', ''),
                id=product.get("id", ""),
                resource_url=r_url,
                resource_content=resource_content,
                hashtags=topics,
                resource_author_name=product.get("userId", ""),
                resource_platform="Product Hunt",
                resource_platform_url="https://www.producthunt.com",
                analytics=Analytics(
                    like_count=product.get('votesCount', 0),
                    reply_count=product.get('commentsCount', 0)
                ),
                comment_resource=comments,
                resource_media=resource_media
            )

        except Exception as e:
            logger.error(f"解析产品数据失败: {e}")
            return None

    async def action_extract_posts(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取已收集的产品"""
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
                "description": resource.description,
                "content": resource.resource_content[:200] + "..." if len(resource.resource_content) > 200 else resource.resource_content,
                "author": resource.resource_author_name,
                "url": resource.resource_url,
                "votes": resource.analytics.like_count if resource.analytics else 0,
                "comments": resource.analytics.reply_count if resource.analytics else 0,
                "topics": resource.hashtags
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
            "resources_collected": len(self.resources)
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
