"""
测试 GoogleTrendsActor 的数据抓取功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.google_trends_actor import GoogleTrendsActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_google_trends_actor():
    """测试 GoogleTrendsActor 基本功能"""

    # 从 config.yaml 加载配置
    task_config = get_task_config("google_trends")
    profile = get_profile(task_config.use_profile)

    actor = GoogleTrendsActor()
    task_id = f"test_gt_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("浏览器连接成功")

        # 搜索趋势（使用 config.yaml 中定义的参数）
        logger.info("\n=== 搜索趋势 ===")
        # 从 config 的 actions 中获取预定义参数
        search_action = next((a for a in task_config.actions if a.action == "search_trends"), None)
        search_params = search_action.params if search_action else {"keyword": "AI", "time_range": "today 12-m"}
        result = await actor.action_search_trends(task, search_params)
        logger.info(f"搜索结果: {result}")

        # 等待让 API 响应被处理
        await asyncio.sleep(5)

        # 提取趋势（使用 config.yaml 中定义的参数）
        logger.info("\n=== 提取趋势 ===")
        extract_action = next((a for a in task_config.actions if a.action == "extract_trends"), None)
        extract_params = extract_action.params if extract_action else {}
        result = await actor.action_extract_trends(task, extract_params)
        logger.info(f"结果: collected={result.get('total_collected', 0)}, returned={result.get('returned', 0)}")

        # 显示趋势数据
        trends = result.get('trends', [])
        if trends:
            logger.info(f"\n趋势数据:")
            for i, trend in enumerate(trends, 1):
                keyword = trend.get('keyword', 'N/A')
                avg_interest = trend.get('avg_interest', 0)
                peak_interest = trend.get('peak_interest', 0)
                related = trend.get('related_topics', [])
                logger.info(f"  [{i}] 关键词: {keyword}")
                logger.info(f"      平均热度: {avg_interest:.1f}")
                logger.info(f"      峰值热度: {peak_interest}")
                if related:
                    logger.info(f"      相关话题: {', '.join(related[:5])}")
        else:
            logger.info("  没有收集到趋势数据")

        # 显示原始内容（如果有）
        if trends and trends[0].get('content'):
            logger.info(f"\n原始数据预览:")
            content = trends[0]['content'][:500]
            logger.info(f"{content}...")

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
    GoogleTrendsActor 测试脚本
    =========================

    配置来源: config.yaml 中的 google_trends_test 任务
    运行前请确保:
    1. 已启动浏览器: python main.py --launch
    2. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_google_trends_actor())
