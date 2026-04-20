"""
Task实例管理 - 服务器模式（常驻进程）
"""
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Any, List, TYPE_CHECKING
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from core.models import Profile, TaskConfig, AppConfig
from core.actor_registry import ActorRegistry
import logging

if TYPE_CHECKING:
    from core.base_actor import BaseActor

logger = logging.getLogger(__name__)


class TaskInstance:
    """Task运行实例 - 在服务器中常驻"""

    def __init__(
        self,
        task_id: str,
        task_config: TaskConfig,
        profile: Profile,
        actor: "BaseActor"
    ):
        self.task_id = task_id
        self.task_config = task_config
        self.profile = profile
        self.actor = actor

        # 浏览器连接（在服务器中常驻）
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None

        # 实例状态
        self.status: str = "created"
        self.created_at: float = time.time()
        self.data: Dict[str, Any] = {}

        logger.info(f"[{self.task_id}] Task instance created")

    async def connect(self):
        """连接到浏览器（服务器启动时调用一次）"""
        # API 模式不需要浏览器连接
        if self.profile.mode == "api":
            logger.info(f"[{self.task_id}] API mode - skipping browser connection")
            self.status = "running"
            return

        logger.info(f"[{self.task_id}] Starting connection...")
        try:
            # async_playwright is already imported at module level
            logger.info(f"[{self.task_id}] Starting async_playwright...")
            self._playwright = await async_playwright().start()
            logger.info(f"[{self.task_id}] async_playwright started")

            # 支持远程浏览器连接
            browser_host = self.profile.browser_host or "localhost"
            browser_url = f"http://{browser_host}:{self.profile.port}"
            logger.info(f"[{self.task_id}] Connecting to browser at {browser_url}")

            self.browser = await self._playwright.chromium.connect_over_cdp(browser_url)
            logger.info(f"[{self.task_id}] Connected to browser")

            # 使用现有 context 以保留登录信息
            if not self.browser.contexts:
                self.context = await self.browser.new_context()
            else:
                self.context = self.browser.contexts[0]

            self.page = await self.context.new_page()
            self.status = "running"
            logger.info(f"[{self.task_id}] Connected successfully, page ready")
        except Exception as e:
            self.status = "error"
            logger.error(f"[{self.task_id}] Failed to connect: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    async def execute_action(self, action_name: str, action_params: Dict[str, Any] = None) -> Dict[str, Any]: # type: ignore
        """执行Action"""
        if self.status == "stopped":
            raise RuntimeError(f"Task instance {self.task_id} is stopped")

        # API 模式不需要 page
        if self.profile.mode == "browser" and self.page is None:
            raise RuntimeError(f"Task instance {self.task_id} not connected")

        if action_params is None:
            action_params = {}

        # 传入 task (self)，让 action 可以访问 task.page, task.task_config 等
        result = await self.actor.execute_action(self, action_name, action_params)
        self.data[action_name] = result
        return result

    def get_status(self) -> Dict[str, Any]:
        """获取实例状态"""
        return {
            "task_id": self.task_id,
            "task_name": self.task_config.name,
            "actor": self.actor.actor_name,
            "profile": self.profile.name,
            "status": self.status,
            "created_at": self.created_at,
            "uptime_seconds": time.time() - self.created_at,
            "data_keys": list(self.data.keys()),
            "current_url": self.page.url if self.page else None
        }

    def get_data_dir(self) -> Path:
        """获取任务专属的数据目录"""
        # data/tasks/{task_id}/
        data_dir = Path("data") / "tasks" / self.task_id
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    async def close(self):
        """关闭实例"""
        logger.info(f"[{self.task_id}] Closing task instance")

        if self.page:
            try:
                await self.page.close()
            except:
                pass
            self.page = None

        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
            self.browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except:
                pass
            self._playwright = None

        self.status = "stopped"
        logger.info(f"[{self.task_id}] Task instance closed")


class TaskInstanceManager:
    """Task实例管理器（服务器模式，内存常驻）"""

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_manager(cls):
        """获取管理器单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        if TaskInstanceManager._instance is not None:
            return
        self._instances: Dict[str, TaskInstance] = {}
        self._lock = threading.Lock()
        logger.info("TaskInstanceManager initialized")

    async def create_instance(
        self,
        task_config: TaskConfig,
        profile: Profile,
        actor: "BaseActor"
    ) -> str:
        """创建Task实例"""
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        with self._lock:
            instance = TaskInstance(task_id, task_config, profile, actor)
            await instance.connect()  # 连接并保持
            self._instances[task_id] = instance

        logger.info(f"Created task instance: {task_id}")
        return task_id

    def get_instance(self, task_id: str) -> Optional[TaskInstance]:
        """获取Task实例"""
        return self._instances.get(task_id)

    async def close_instance(self, task_id: str):
        """关闭Task实例"""
        with self._lock:
            if task_id in self._instances:
                await self._instances[task_id].close()
                del self._instances[task_id]
                logger.info(f"Closed task instance: {task_id}")

    def list_instances(self) -> List[Dict[str, Any]]:
        """列出所有Task实例"""
        return [instance.get_status() for instance in self._instances.values()]

    async def cleanup_stopped_instances(self):
        """清理已停止的实例"""
        with self._lock:
            to_remove = [
                task_id for task_id, instance in self._instances.items()
                if instance.status == "stopped"
            ]
            for task_id in to_remove:
                await self._instances[task_id].close()
                del self._instances[task_id]
            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} stopped instances")
