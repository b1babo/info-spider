"""
测试 Google 搜索 - agent 安全评估
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在 import 之前）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import logging
import uuid

from actors.google_search_actor import GoogleSearchActor
from core.task_instance import TaskInstance
from tests.test_helper import get_task_config, get_profile

from core import setup_logging
setup_logging.setup_logging()
logger = logging.getLogger(__name__)


async def test_google_search():
    """测试 Google 搜索"""

    # 使用 google_search 配置，但修改搜索关键词
    task_config = get_task_config("google_search")
    profile = get_profile(task_config.use_profile)

    actor = GoogleSearchActor()
    task_id = f"google_search_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("浏览器连接成功")

        # 执行搜索 - 搜索"agent 安全评估"
        query = "agent 安全评估"
        logger.info(f"\n=== 执行搜索: {query} ===")

        result = await actor.action_create(task, {
            "query": query,
            "language": "zh-CN",
            "num": 10
        })

        logger.info(f"页面标题: {result.get('title', 'N/A')}")
        logger.info(f"当前URL: {result.get('url', 'N/A')}")

        # 等待页面加载
        await asyncio.sleep(3)

        # 提取搜索结果
        logger.info("\n=== 提取搜索结果 ===")
        result = await actor.action_extract_results(task, {"max": 20})

        logger.info(f"提取完成: extracted={result.get('extracted', 0)}, total={result.get('total_collected', 0)}")
        logger.info(f"相关搜索: {result.get('related_searches', 0)}")
        logger.info(f"相关问题(PAA): {result.get('people_also_ask', 0)}")
        logger.info(f"相关产品: {result.get('related_products', 0)}")

        # 显示搜索结果
        results = result.get('results', [])
        if results:
            logger.info(f"\n========== 搜索结果 ({len(results)} 条) ==========")
            for i, r in enumerate(results, 1):
                title = r.get('title', 'N/A')
                url = r.get('url', 'N/A')
                snippet = r.get('snippet', '')

                logger.info(f"\n[{i}] {title}")
                logger.info(f"    URL: {url}")
                if snippet:
                    # 截断过长的摘要
                    if len(snippet) > 150:
                        snippet = snippet[:150] + "..."
                    logger.info(f"    摘要: {snippet}")
        else:
            logger.info("  没有找到搜索结果")

        # 显示相关搜索
        related = result.get('related', [])
        if related:
            logger.info(f"\n========== 相关搜索 ({len(related)} 条) ==========")
            for i, r in enumerate(related, 1):
                logger.info(f"  [{i}] {r.get('display_text', r.get('query', 'N/A'))}")

        # 显示相关问题
        paa = result.get('paa', [])
        if paa:
            logger.info(f"\n========== 相关问题 ({len(paa)} 条) ==========")
            for i, q in enumerate(paa, 1):
                logger.info(f"  [{i}] {q.get('question', 'N/A')}")

        # 显示相关产品
        products = result.get('products', [])
        if products:
            logger.info(f"\n========== 相关产品/服务 ({len(products)} 条) ==========")
            for i, p in enumerate(products, 1):
                logger.info(f"  [{i}] {p.get('display_text', p.get('query', 'N/A'))}")

        # 最终状态
        logger.info("\n=== 最终状态 ===")
        status = await actor.action_status(task, {})
        logger.info(f"总结果数: {status.get('results_collected', 0)}")
        logger.info(f"相关搜索: {status.get('related_searches', 0)}")
        logger.info(f"相关问题: {status.get('people_also_ask', 0)}")
        logger.info(f"相关产品: {status.get('related_products', 0)}")

    except Exception as e:
        logger.error(f"测试出错: {e}", exc_info=True)

    finally:
        try:
            await task.close()
        except:
            pass


if __name__ == "__main__":
    print("""
    Google 搜索测试 - agent 安全评估
    =================================

    配置来源: config.yaml 中的 google_search 任务

    运行前请确保:
    1. 远程浏览器已启动并配置在 config.yaml 中
    2. CDP 端口可访问

    开始测试...
    """)

    asyncio.run(test_google_search())
