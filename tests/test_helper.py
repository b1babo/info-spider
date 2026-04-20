"""
测试辅助函数 - 从 config.yaml 加载配置
"""
import yaml
import logging
from pathlib import Path
from pydantic import ValidationError

from core.models import AppConfig, Profile, TaskConfig

logger = logging.getLogger(__name__)

# 全局配置缓存
_config_cache: AppConfig = None
CONFIG_PATH = "config.yaml"


def load_config(config_path: str = CONFIG_PATH) -> AppConfig:
    """加载并缓存配置文件"""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    config_file = Path(config_path)
    if not config_file.exists():
        # 尝试相对于项目根目录的路径
        project_root = Path(__file__).parent.parent
        config_file = project_root / config_path

    if not config_file.exists():
        raise FileNotFoundError(f"配置文件未找到: {config_path}")

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            _config_cache = AppConfig(**yaml.safe_load(f))
        return _config_cache
    except ValidationError as e:
        logger.error(f"配置文件校验失败: {e}")
        raise
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        raise


def get_profile(profile_name: str) -> Profile:
    """获取指定的 Profile 配置"""
    config = load_config()
    profile = config.get_profile(profile_name)
    if not profile:
        available = [p.name for p in config.profiles]
        raise ValueError(f"Profile '{profile_name}' 不存在。可用: {available}")
    return profile


def get_task_config(task_name: str) -> TaskConfig:
    """获取指定的 Task 配置"""
    config = load_config()
    task = config.get_task(task_name)
    if not task:
        available = [t.name for t in config.tasks]
        raise ValueError(f"Task '{task_name}' 不存在。可用: {available}")
    return task


def list_profiles() -> list[str]:
    """列出所有可用的 Profile 名称"""
    config = load_config()
    return [p.name for p in config.profiles]


def list_tasks() -> list[str]:
    """列出所有可用的 Task 名称"""
    config = load_config()
    return [t.name for t in config.tasks]


def list_enabled_tasks() -> list[str]:
    """列出所有启用的 Task 名称"""
    config = load_config()
    return [t.name for t in config.tasks if t.enable]


def reload_config():
    """重新加载配置（清除缓存）"""
    global _config_cache
    _config_cache = None
