from typing import Dict, Type, List, Optional
from core.base_actor import BaseActor
import logging

logger = logging.getLogger(__name__)


class ActorRegistry:
    """Actor注册器 - 管理所有可用的Actor类"""

    _actors: Dict[str, Type[BaseActor]] = {}

    @classmethod
    def register(cls, name: str, actor_class: Type[BaseActor]):
        """注册Actor类

        Args:
            name: Actor名称
            actor_class: Actor类
        """
        if name in cls._actors:
            logger.warning(f"Actor '{name}' already registered, overwriting")
        cls._actors[name] = actor_class
        logger.info(f"Registered actor: {name} -> {actor_class.__name__}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[BaseActor]]:
        """获取Actor类

        Args:
            name: Actor名称

        Returns:
            Actor类或None
        """
        return cls._actors.get(name)

    @classmethod
    def create(cls, name: str) -> Optional[BaseActor]:
        """创建Actor实例

        Args:
            name: Actor名称

        Returns:
            Actor实例或None
        """
        actor_class = cls.get(name)
        if actor_class is None:
            logger.error(f"Actor not found: {name}")
            return None
        return actor_class()

    @classmethod
    def list_actors(cls) -> List[Dict[str, str]]:
        """列出所有已注册的Actors

        Returns:
            Actor信息列表
        """
        return [
 {
                "name": name,
                "class": cls.__name__,
                "description": getattr(cls, "actor_description", "")
            }
            for name, cls in cls._actors.items()
        ]

    @classmethod
    def has_actor(cls, name: str) -> bool:
        """检查Actor是否已注册

        Args:
            name: Actor名称

        Returns:
            是否存在
        """
        return name in cls._actors

    @classmethod
    def clear(cls):
        """清空所有注册的Actor（主要用于测试）"""
        cls._actors.clear()
        logger.info("Actor registry cleared")
