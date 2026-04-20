"""
测试 TwitterUserActor 的多次滚动功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.twitter_user import TwitterUserActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_multiple_scroll():
    """测试多次滚动累加数据"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("github_daily_tweets")
    profile = get_profile(task_config.use_profile)

    actor = TwitterUserActor()
    task_id = f"test_task_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("浏览器连接成功")

        # 创建任务（使用 config.yaml 中的 url）
        logger.info("\n=== 创建任务 ===")
        await actor.action_create(task, {})  # 不传参数，使用 config 中的 url
        await asyncio.sleep(3)

        # 检查初始状态
        status = await actor.action_status(task, {})
        initial_count = status.get('resources_collected', 0)
        logger.info(f"初始收集数: {initial_count}")

        # 第一次滚动（累加模式，保留初始数据）
        logger.info("\n=== 第1次滚动（reset=False）===")
        result = await actor.action_scroll_and_extract(task, {
            "scroll_times": 5,
            "max": 50,
            "time_range": 168,  # 7天
            "reset": False
        })
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")
        if result.get('storage_stats'):
            stats = result['storage_stats']
            logger.info(f"  存储: added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

        # 第二次滚动（累加模式）
        logger.info("\n=== 第2次滚动（reset=False）===")
        result = await actor.action_scroll_and_extract(task, {
            "scroll_times": 5,
            "max": 50,
            "time_range": 168,
            "reset": False
        })
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")
        if result.get('storage_stats'):
            stats = result['storage_stats']
            logger.info(f"  存储: added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

        # 最终状态
        logger.info("\n=== 最终状态 ===")
        status = await actor.action_status(task, {})
        logger.info(f"总收集数: {status.get('resources_collected', 0)}")

        # 关闭任务
        logger.info("\n=== 关闭任务 ===")
        result = await actor.action_close(task, {})
        logger.info(f"关闭结果: {result}")

    except Exception as e:
        logger.error(f"测试出错: {e}", exc_info=True)

    finally:
        try:
            await task.close()
        except:
            pass


if __name__ == "__main__":
    print("""
    TwitterUserActor 多次滚动累加测试
    ===============================

    配置来源: config.yaml 中的 github_daily_tweets 任务
    运行前请确保:
    1. 已启动浏览器: python main.py --launch
    2. 已登录 Twitter/X
    3. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_multiple_scroll())
