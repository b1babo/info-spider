"""
测试 Google 关键词研究功能

包括:
1. Google Suggest - 关键词扩展 (API 模式，无需浏览器)
2. Google Trends - 趋势分析和深度挖掘 (浏览器模式)
"""
import asyncio
import logging
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.plugin_loader import discover_actors
from core.task_instance import TaskInstance
from core.models import TaskConfig, Profile
from tests.test_helper import get_task_config, get_profile
from core import setup_logging

setup_logging.setup_logging()
logger = logging.getLogger(__name__)


# ==================== Google Suggest 测试 ====================

async def test_google_suggest():
    """测试 Google Suggest Actor 基本功能"""

    print("\n" + "="*60)
    print("测试 Google Suggest - 关键词扩展")
    print("="*60)

    # 从 config.yaml 加载配置
    task_config = get_task_config("google_suggest")
    profile = get_profile(task_config.use_profile)

    # 加载并注册 Actor
    actors = discover_actors()
    actor_class = actors.get("google_suggest_actor")
    if not actor_class:
        logger.error("google_suggest_actor not found")
        return

    actor = actor_class()
    task_id = f"suggest_test_{uuid.uuid4().hex[:8]}"
    task = TaskInstance(task_id, task_config, profile, actor)

    try:
        await task.connect()
        logger.info("Task connected successfully")

        # 使用 config.yaml 中定义的参数
        expand_action = next((a for a in task_config.actions if a.action == "expand_keywords"), None)
        expand_params = expand_action.params if expand_action else {"seed": "python"}

        logger.info(f"\n=== 扩展关键词 ===")
        logger.info(f"参数: {expand_params}")
        result = await actor.execute_action(task, "expand_keywords", expand_params)

        expand_result = result['results']
        logger.info(f"种子词: {expand_result['seed']}")
        logger.info(f"基础建议: {len(expand_result['base_suggestions'])}")
        logger.info(f"字母扩展: {len(expand_result['alphabet_expanded'])}")
        logger.info(f"问题扩展: {len(expand_result['question_expanded'])}")
        logger.info(f"修饰词扩展: {len(expand_result['modifier_expanded'])}")
        logger.info(f"总唯一: {expand_result['total_unique']}")

        # 显示一些示例关键词
        logger.info("\n=== 示例关键词 ===")
        all_keywords = list(set(
            expand_result['base_suggestions'] +
            expand_result['alphabet_expanded'] +
            expand_result['question_expanded'] +
            expand_result['modifier_expanded']
        ))
        logger.info(f"总关键词数: {len(all_keywords)}")
        logger.info(f"前 30 个关键词:")
        for i, kw in enumerate(all_keywords[:30], 1):
            logger.info(f"  {i}. {kw}")

        print("\n✅ Google Suggest 测试完成")

    except Exception as e:
        logger.error(f"测试出错: {e}", exc_info=True)
        print(f"\n❌ Google Suggest 测试失败: {e}")

    finally:
        try:
            # 调用 close action 保存数据到任务专属目录
            close_result = await actor.execute_action(task, "close", {})
            data_dir = task.get_data_dir()
            logger.info(f"数据已保存到任务目录: {data_dir}")
            if close_result.get("saved_to"):
                logger.info(f"保存文件: {close_result['saved_to']}")
            if close_result.get("storage_stats"):
                stats = close_result['storage_stats']
                logger.info(f"存储统计: added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")
            await task.close()
        except Exception as e:
            logger.error(f"关闭任务时出错: {e}")


# ==================== Google Trends 测试 ====================

async def test_trends_compare():
    """测试 Google Trends compare_keywords action"""
    print("\n" + "="*60)
    print("测试 Google Trends - 关键词比较")
    print("="*60)

    from actors.google_trends_actor import GoogleTrendsActor

    # 创建 actor
    actor = GoogleTrendsActor()

    # 创建测试配置
    profile = Profile(
        name="test_profile",
        mode="browser",
        port=9222,
        browser_host="192.168.2.119",
        browser_type="msedge"
    )

    task_config = TaskConfig(
        name="test_compare",
        url="https://trends.google.com",
        actor="google_trends_actor",
        use_profile="test_profile",
        enable=True,
        params={}
    )

    # 创建 playwright 连接
    async with async_playwright() as p:
        browser_url = "http://192.168.2.119:9222"
        print(f"连接到浏览器: {browser_url}")

        try:
            browser = await p.chromium.connect_over_cdp(browser_url)

            # 使用现有 context
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()

            page = await context.new_page()

            # 创建 TaskInstance
            task = TaskInstance(
                task_id="test_compare_001",
                task_config=task_config,
                profile=profile,
                actor=actor
            )
            task.browser = browser
            task.context = context
            task.page = page
            task.status = "running"

            # 测试 compare_keywords
            params = {
                "keywords": ["AI", "ML", "DL"],
                "time_range": "today 3-m",
                "geo": ""
            }

            print(f"执行 compare_keywords: {params['keywords']}")
            result = await actor.action_compare_keywords(task, params)

            print(f"\n结果状态: {result.get('status')}")
            print(f"关键词: {result.get('keywords', params['keywords'])}")
            print(f"下载的数据类型: {result.get('downloaded_types', [])}")
            print(f"数据条目数: {result.get('entries', 0)}")

            if result.get('status') == 'success':
                # 检查趋势数据
                if 'timeline' in actor.trend_data:
                    timeline = actor.trend_data['timeline']
                    print(f"\n时间线数据点: {len(timeline)}")
                    if timeline:
                        print(f"最新数据: {timeline[-1]}")
                        print(f"最早数据: {timeline[0]}")

            # 关闭页面
            await page.close()
            print("\n✅ compare_keywords 测试完成")

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


async def test_trends_regional():
    """测试 Google Trends regional_interest action"""
    print("\n" + "="*60)
    print("测试 Google Trends - 地区分布")
    print("="*60)

    from actors.google_trends_actor import GoogleTrendsActor

    # 创建 actor
    actor = GoogleTrendsActor()

    # 创建测试配置
    profile = Profile(
        name="test_profile",
        mode="browser",
        port=9222,
        browser_host="192.168.2.119",
        browser_type="msedge"
    )

    task_config = TaskConfig(
        name="test_regional",
        url="https://trends.google.com",
        actor="google_trends_actor",
        use_profile="test_profile",
        enable=True,
        params={}
    )

    # 创建 playwright 连接
    async with async_playwright() as p:
        browser_url = "http://192.168.2.119:9222"
        print(f"连接到浏览器: {browser_url}")

        try:
            browser = await p.chromium.connect_over_cdp(browser_url)

            # 使用现有 context
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = await browser.new_context()

            page = await context.new_page()

            # 创建 TaskInstance
            task = TaskInstance(
                task_id="test_regional_001",
                task_config=task_config,
                profile=profile,
                actor=actor
            )
            task.browser = browser
            task.context = context
            task.page = page
            task.status = "running"

            # 测试 regional_interest
            params = {
                "keyword": "AI",
                "geo": "US",
                "time_range": "today 12-m"
            }

            print(f"执行 regional_interest: keyword={params['keyword']}, geo={params['geo']}")
            result = await actor.action_regional_interest(task, params)

            print(f"\n结果状态: {result.get('status')}")
            print(f"关键词: {result.get('keyword')}")
            print(f"地区: {result.get('geo')}")

            if result.get('regional_data'):
                regional = result['regional_data']
                print(f"\n地区数据:")
                print(f"  国家数: {len(regional.get('country', []))}")
                if regional.get('country'):
                    print(f"  热度前3:")
                    for i, r in enumerate(regional['country'][:3]):
                        print(f"    {i+1}. {r['region']}: {r['value']}")

            if result.get('csv_file'):
                print(f"\nCSV 文件: {result['csv_file']}")

            # 关闭页面
            await page.close()
            print("\n✅ regional_interest 测试完成")

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()


# ==================== 主测试入口 ====================

async def test_all():
    """运行所有 Google 关键词研究测试"""
    print("\n" + "="*60)
    print("Google 关键词研究功能测试套件")
    print("="*60)

    # 测试 Google Suggest (API 模式)
    await test_google_suggest()

    await asyncio.sleep(2)

    # 测试 Google Trends (浏览器模式)
    await test_trends_compare()

    await asyncio.sleep(2)

    await test_trends_regional()

    print("\n" + "="*60)
    print("所有测试完成")
    print("="*60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试 Google 关键词研究功能")
    parser.add_argument(
        "--test",
        choices=["all", "suggest", "trends-compare", "trends-regional"],
        default="all",
        help="选择要运行的测试"
    )

    args = parser.parse_args()

    print("""
========================================
Google 关键词研究功能测试
========================================

测试模块:
1. Google Suggest - 关键词扩展 (API模式)
2. Google Trends - 关键词比较 (浏览器模式)
3. Google Trends - 地区分布 (浏览器模式)
    """)

    if args.test == "all":
        asyncio.run(test_all())
    elif args.test == "suggest":
        asyncio.run(test_google_suggest())
    elif args.test == "trends-compare":
        asyncio.run(test_trends_compare())
    elif args.test == "trends-regional":
        asyncio.run(test_trends_regional())
