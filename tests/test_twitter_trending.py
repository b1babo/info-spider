"""
测试 TwitterTrendingActor 的数据抓取功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.twitter_trending_actor import TwitterTrendingActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_twitter_trending_actor():
    """测试 TwitterTrendingActor 基本功能"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("twitter_trending")
    profile = get_profile(task_config.use_profile)

    actor = TwitterTrendingActor()
    task_id = f"test_trend_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("浏览器连接成功")

        # 创建任务（使用 config.yaml 中的 url）
        logger.info("\n=== 创建任务 ===")
        result = await actor.action_create(task, {})  # 不传参数，使用 config 中的 url
        logger.info(f"页面标题: {result.get('title', 'N/A')}")
        logger.info(f"当前URL: {result.get('url', 'N/A')}")

        # 等待让 API 响应被处理
        await asyncio.sleep(5)

        # 检查状态
        logger.info("\n=== 检查状态 ===")
        status = await actor.action_status(task, {})
        logger.info(f"收集数: {status.get('resources_collected', 0)}")

        # 提取趋势（使用 config.yaml 中定义的参数）
        logger.info("\n=== 提取趋势 ===")
        extract_action = next((a for a in task_config.actions if a.action == "extract_trends"), None)
        extract_params = extract_action.params if extract_action else {"max": 20}
        result = await actor.action_extract_trends(task, extract_params)
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")

        # 显示趋势
        trends = result.get('trends', [])
        if trends:
            logger.info(f"\n前 10 条趋势:")
            for i, trend in enumerate(trends[:10], 1):
                content = trend.get('content', 'N/A')
                description = trend.get('description', 'N/A')
                posts = trend.get('post_count', 0)
                logger.info(f"  [{i}] {content}")
                if description:
                    logger.info(f"      分类: {description}")
                if posts > 0:
                    logger.info(f"      推文数: {posts}")
        else:
            logger.info("  没有收集到趋势")

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
    TwitterTrendingActor 测试脚本
    ==============================

    配置来源: config.yaml 中的 twitter_trending 任务
    运行前请确保:
    1. 已启动浏览器: python main.py --launch
    2. 已登录 Twitter/X
    3. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_twitter_trending_actor())
