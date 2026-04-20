"""
测试抓取 elonmusk 的推文
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


async def test_elonmusk():
    """测试抓取 elonmusk 的推文"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("elonmusk_tweets")
    profile = get_profile(task_config.use_profile)

    actor = TwitterUserActor()
    task_id = f"elonmusk_{uuid.uuid4().hex[:8]}"
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
        await asyncio.sleep(3)

        # 滚动并提取推文（使用 config.yaml 中定义的参数）
        logger.info("\n=== 滚动并提取推文 ===")
        result = await actor.action_scroll_and_extract(task, {})  # 使用预定义参数
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")

        # 显示推文
        tweets = result.get('tweets', [])
        if tweets:
            logger.info(f"\n前 10 条推文:")
            for i, tweet in enumerate(tweets[:10], 1):
                content = tweet.get('content', 'N/A')
                if len(content) > 80:
                    content = content[:80] + "..."
                logger.info(f"  [{i}] {content}")
                logger.info(f"      时间: {tweet.get('created_at', 'N/A')}")
                logger.info(f"      互动: 👍{tweet.get('likes', 0)} 💬{tweet.get('replies', 0)} 🔄{tweet.get('retweets', 0)}")
        else:
            logger.info("  没有收集到推文")

        # 最终状态
        logger.info("\n=== 最终状态 ===")
        status = await actor.action_status(task, {})
        logger.info(f"总收集数: {status.get('resources_collected', 0)}")

    except Exception as e:
        logger.error(f"测试出错: {e}", exc_info=True)

    finally:
        try:
            await task.close()
        except:
            pass


if __name__ == "__main__":
    print("""
    抓取 elonmusk 的推文
    ===================

    配置来源: config.yaml 中的 elonmusk_tweets 任务

    运行前请确保:
    1. 远程浏览器已启动并配置在 config.yaml 中
    2. 浏览器已登录 Twitter/X
    3. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_elonmusk())
