"""
Twitter/X 趋势页面 Actor
"""
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from playwright.async_api import Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics
from core import utils

import jmespath

logger = logging.getLogger(__name__)


class TwitterTrendingActor(BaseActor):
    """Twitter/X趋势页面Actor"""

    actor_name = "twitter_trending_actor"
    actor_description = "Twitter/X趋势页面操作Actor"

    def setup_actions(self):
        """注册所有Twitter相关的Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="创建Twitter趋势任务并导航到趋势页面",
            params_schema={
                "params": [
                    {"name": "url", "type": "string", "required": True, "description": "趋势页面URL，如 https://x.com/i/trends"}
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
            "extract_trends",
            self.action_extract_trends,
            description="提取趋势数据",
            params_schema={
                "params": [
                    {"name": "max", "type": "integer", "required": False, "default": 50, "description": "最大提取数量"}
                ]
            }
        )

        self.register_action(
            "scroll_and_extract",
            self.action_scroll_and_extract,
            description="滚动页面并提取趋势",
            params_schema={
                "params": [
                    {"name": "scroll_times", "type": "integer", "required": False, "default": 10, "description": "滚动次数"},
                    {"name": "max", "type": "integer", "required": False, "default": 50, "description": "最大提取数量"},
                    {"name": "reset", "type": "boolean", "required": False, "default": True, "description": "是否重置已收集的数据"}
                ]
            }
        )

        # 初始化内部状态
        self.resources: List[Resource] = []
        self._response_handler_registered = False
        self.stop_scroll = False

    # ===== 任务管理Actions =====

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """创建任务并导航到趋势页面"""
        url = action_params.get('url')
        if not url:
            return {
                "status": "error",
                "message": "Missing required parameter: url"
            }

        # 先启用响应拦截（在导航之前）
        self._response_handler_registered = False
        await self.action_intercept_response(task, {"enable": True})

        logger.info(f"Navigating to: {url}")
        await task.page.goto(url)
        await asyncio.sleep(3)

        return {
            "status": "success",
            "message": "Twitter trending actor initialized",
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

    async def action_extract_trends(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """提取已收集的趋势数据"""
        max = action_params.get('max', 50)

        count = min(len(self.resources), max)

        result = {
            "status": "success",
            "total_collected": len(self.resources),
            "returned": count,
            "trends": []
        }

        for i, resource in enumerate(self.resources[:count]):
            trend_data = {
                "content": resource.resource_content,
                "description": resource.description,
                "url": resource.resource_url,
                "post_count": resource.analytics.reply_count if resource.analytics else 0
            }
            result["trends"].append(trend_data)

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
        """滚动页面并提取趋势"""
        scroll_times = action_params.get('scroll_times', 10)
        max = action_params.get('max', 50)
        reset = action_params.get('reset', True)

        # 确保响应拦截已启用
        if not self._response_handler_registered:
            await self.action_intercept_response(task, {"enable": True})

        # 根据 reset 参数决定是否重置收集器
        if reset:
            logger.info("重置收集器，开始新的抓取会话")
            self.resources = []
            self.stop_scroll = False
        else:
            logger.info(f"累加模式，当前已有 {len(self.resources)} 条数据")

        # 滚动
        for i in range(scroll_times):
            if self.stop_scroll:
                logger.info("已获取趋势数据，停止滚动")
                break

            logger.info(f"第 {i + 1} 次滚动...")
            from core.utils import HumanUtils
            await HumanUtils.smart_scroll(task.page, 1, 3)

        # 提取结果
        return await self.action_extract_trends(task, {"max": max})

    # ===== 响应拦截处理 =====

    async def _intercept_response(self, response: Response):
        """拦截API响应"""
        content_type = response.headers.get("content-type", "")

        if "application/json" in content_type:
            if "GenericTimelineById" in response.url:
                logger.info(f"[拦截] GenericTimelineById {response.url[:100]}...")
                try:
                    data = await response.json()
                    resources = self.parse_trending_data(data)
                    logger.info(f"[拦截] 解析到 {len(resources)} 条趋势")

                    for r in resources:
                        self.resources.append(r)

                    # 趋势页面一次请求就返回所有数据，可以停止滚动
                    self.stop_scroll = True
                    logger.info(f"[拦截] 趋势数据已获取完整，停止滚动")

                except Exception as e:
                    logger.error(f"[拦截] 解析响应失败: {e}")

    # ===== 数据解析方法 =====

    def parse_trending_data(self, data: dict) -> List[Resource]:
        """解析趋势数据"""
        instructions = jmespath.search('data.timeline.timeline.instructions', data)
        if not instructions:
            logger.info("No timeline instructions found")
            return []

        trends = []
        for instruction in instructions:
            instruction_type = instruction.get('type')

            if instruction_type == 'TimelineAddEntries':
                entries = instruction.get('entries', [])

                for entry in entries:
                    entry_id: str = entry.get("entryId", "")
                    item_content = entry.get("content", {}).get("itemContent", {})

                    # 跳过推广内容
                    promoted_metadata = item_content.get("promoted_metadata", {})
                    if promoted_metadata:
                        continue

                    trend = self._extract_trend_data(item_content)
                    if trend:
                        trends.append(trend)

        return trends

    def _extract_trend_data(self, item_content: dict) -> Optional[Resource]:
        """提取单条趋势数据"""
        resource_content = item_content.get("name", "")
        trend_url = item_content.get("trend_url", {})
        resource_url = trend_url.get("url", "")

        # 转换 URL 格式
        if resource_url.startswith("twitter://search/?query="):
            resource_url = "https://x.com/search/?q=" + resource_url[len("twitter://search/?query="):]

        trend_metadata = item_content.get("trend_metadata", {})
        description = trend_metadata.get("domain_context", "")

        # 解析推文数量
        analytics = Analytics()
        meta_description = trend_metadata.get("meta_description", "").split(" ")
        if len(meta_description) == 2:
            number = meta_description[0]
            analytics.reply_count = utils.convert_to_number(number)

        resource = Resource(
            description=description,
            resource_type="trend",
            resource_url=resource_url,
            resource_content=resource_content,
            resource_platform="X/Twitter",
            resource_platform_url="https://x.com",
            is_pinned=False,
            analytics=analytics,
        )

        return resource

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
