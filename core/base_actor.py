from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable, Awaitable, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from core.task_instance import TaskInstance

# Action Handler 函数类型定义（仅异步）
ActionHandler = Callable[["TaskInstance", Dict[str, Any]], Awaitable[Dict[str, Any]]]

logger = logging.getLogger(__name__)


class BaseActor(ABC):
    """Actor基类 - 定义平台特定的Actions"""

    actor_name: str = "base_actor"
    actor_description: str = ""

    def __init__(self):
        self.context: Dict[str, Any] = {}
        self._actions: Dict[str, Dict[str, Any]] = {}

        # 让子类注册他们的actions
        self.setup_actions()

    @abstractmethod
    def setup_actions(self):
        """注册此Actor支持的所有Actions"""
        pass

    def register_action(
        self,
        name: str,
        handler: ActionHandler,
        description: str = "",
        params_schema: Optional[Dict[str, Any]] = None
    ):
        """注册Action

        Args:
            name: Action名称
            handler: Action处理函数（异步）
            description: Action描述
            params_schema: 参数schema定义
        """
        self._actions[name] = {
            "handler": handler,
            "description": description,
            "schema": params_schema or {}
        }
        logger.debug(f"[{self.actor_name}] Registered action: {name}")

    async def execute_action(self, task, action_name: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """执行Action

        Args:
            task: TaskInstance实例
            action_name: Action名称
            action_params: Action参数

        Returns:
            Action执行结果
        """
        if action_name not in self._actions:
            available = ", ".join(self._actions.keys())
            raise ValueError(
                f"Unknown action '{action_name}'. "
                f"Available actions: {available}"
            )

        action_info = self._actions[action_name]
        handler = action_info["handler"]

        # 合并预定义参数和传入参数（传入参数优先）
        merged_params = self._merge_action_params(task, action_name, action_params)

        try:
            # 所有action处理器都是异步函数
            result = await handler(task, merged_params)
            return result
        except Exception:
            raise

    def _merge_action_params(self, task, action_name: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """合并预定义参数和传入参数

        Args:
            task: TaskInstance实例
            action_name: Action名称
            action_params: 用户传入的参数

        Returns:
            合并后的参数（传入参数优先）
        """
        # 从 task_config 中查找预定义的该 action 的 params
        predefined_params = {}
        for action_config in task.task_config.actions:
            if action_config.action == action_name and action_config.enabled:
                predefined_params = action_config.params
                break

        # 合并参数：预定义参数 + 传入参数（传入参数覆盖预定义参数）
        merged = {**predefined_params, **action_params}
        if predefined_params and action_params:
            logger.debug(
                f"[{self.actor_name}] Merged params for '{action_name}': "
                f"predefined={predefined_params}, "
                f"user_provided={action_params}, "
                f"merged={merged}"
            )

        return merged

    def list_actions(self) -> List[Dict[str, Any]]:
        """列出所有可用的Actions

        Returns:
            Actions列表，包含name、description、params信息
        """
        return [
            {
                "name": name,
                "description": info["description"],
                "params": info["schema"]
            }
            for name, info in self._actions.items()
        ]

    def get_action_schema(self, action_name: str) -> Optional[Dict[str, Any]]:
        """获取特定Action的schema

        Args:
            action_name: Action名称

        Returns:
            Action的schema定义
        """
        if action_name in self._actions:
            return self._actions[action_name]["schema"]
        return None

    def has_action(self, action_name: str) -> bool:
        """检查是否支持某个Action"""
        return action_name in self._actions
