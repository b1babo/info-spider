"""
测试 TwitterRandomReadingActor 的数据抓取功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.twitter_random_reading_actor import TwitterRandomReadingActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_twitter_random_reading_actor():
    """测试 TwitterRandomReadingActor 基本功能"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("twitter_home_reading")
    profile = get_profile(task_config.use_profile)

    actor = TwitterRandomReadingActor()
    task_id = f"test_home_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("浏览器连接成功")

        # 创建任务（使用 config.yaml 中的 url）
        logger.info("\n=== 创建任务 ===")
        result = await actor.action_create(task, {})  # 不传参数，使用 config 中的 url
        logger.info(f"页面标题: {result.get('title', 'N/A')}")
        logger.info(f"当前URL: {result.get('url', 'N/A')}")
        logger.info(f"当前Tab: {result.get('current_tab', 'N/A')}")

        # 等待让 API 响应被处理
        await asyncio.sleep(3)

        # 检查状态
        logger.info("\n=== 检查状态 ===")
        status = await actor.action_status(task, {})
        logger.info(f"收集数: {status.get('resources_collected', 0)}")
        logger.info(f"当前Tab: {status.get('current_tab', 'N/A')}")

        # 滚动并提取推文（使用 config.yaml 中定义的参数）
        logger.info("\n=== 滚动并提取推文 ===")
        scroll_action = next((a for a in task_config.actions if a.action == "scroll_and_extract"), None)
        scroll_params = scroll_action.params if scroll_action else {"scroll_times": 3, "max": 20, "time_range": 72}
        scroll_params["reset"] = False  # 保留初始收集的数据
        result = await actor.action_scroll_and_extract(task, scroll_params)
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")

        # 显示推文
        tweets = result.get('tweets', [])
        if tweets:
            logger.info(f"\n前 5 条推文:")
            for i, tweet in enumerate(tweets[:5], 1):
                content = tweet.get('content', 'N/A')
                if len(content) > 60:
                    content = content[:60] + "..."
                logger.info(f"  [{i}] @{tweet.get('author', 'N/A')}: {content}")
                logger.info(f"      类型: {tweet.get('type', 'N/A')}")
                logger.info(f"      时间: {tweet.get('created_at', 'N/A')}")
                logger.info(f"      互动: 👍{tweet.get('likes', 0)} 💬{tweet.get('replies', 0)} 🔄{tweet.get('retweets', 0)}")
        else:
            logger.info("  没有收集到推文")

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
    TwitterRandomReadingActor 测试脚本
    =================================

    配置来源: config.yaml 中的 twitter_home_reading 任务
    运行前请确保:
    1. 已启动浏览器: python main.py --launch
    2. 已登录 Twitter/X
    3. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_twitter_random_reading_actor())
