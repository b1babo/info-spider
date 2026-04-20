"""
测试 ProductHuntActor 的数据抓取功能（纯API模式）
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.product_hunt_actor import ProductHuntActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_product_hunt_actor():
    """测试 ProductHuntActor 基本功能（无需浏览器）"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("product_hunt_daily")
    profile = get_profile(task_config.use_profile)

    actor = ProductHuntActor()
    task_id = f"test_ph_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        # API 模式不需要连接浏览器
        logger.info("ProductHunt API 模式 - 无需浏览器连接")

        # 获取产品（使用 config.yaml 中定义的参数）
        logger.info("\n=== 获取产品 ===")
        fetch_action = next((a for a in task_config.actions if a.action == "fetch_posts"), None)
        fetch_params = fetch_action.params if fetch_action else {"days_back": 1, "per_page": 15}
        result = await actor.action_fetch_posts(task, fetch_params)
        logger.info(f"结果: fetched={result.get('fetched', 0)}, total={result.get('total_collected', 0)}")

        # 提取产品（使用 config.yaml 中定义的参数）
        logger.info("\n=== 提取产品 ===")
        extract_action = next((a for a in task_config.actions if a.action == "extract_posts"), None)
        extract_params = extract_action.params if extract_action else {}
        result = await actor.action_extract_posts(task, extract_params)
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")

        # 显示产品
        posts = result.get('posts', [])
        if posts:
            logger.info(f"\n前 10 个产品:")
            for i, post in enumerate(posts[:10], 1):
                description = post.get('description', 'N/A')
                votes = post.get('votes', 0)
                comments = post.get('comments', 0)
                topics = post.get('topics', [])
                logger.info(f"  [{i}] {description[:60]}...")
                logger.info(f"      投票: {votes} | 评论: {comments}")
                if topics:
                    logger.info(f"      主题: {', '.join(topics[:3])}")
        else:
            logger.info("  没有收集到产品")

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


if __name__ == "__main__":
    print("""
    ProductHuntActor 测试脚本
    ========================

    配置来源: config.yaml 中的 product_hunt_daily 任务
    这是纯API模式，无需浏览器！

    开始测试...
    """)

    asyncio.run(test_product_hunt_actor())
