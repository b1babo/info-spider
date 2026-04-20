import logging
from typing import Dict, Type
from core.base_actor import BaseActor
from core.actor_registry import ActorRegistry

logger = logging.getLogger(__name__)


def discover_actors() -> Dict[str, Type[BaseActor]]:
    """
    手动加载并注册 Actor（用于服务器模式）

    Returns:
        Dict: { "actor_name": 类对象 }
    """
    actors = {}

    # 手动导入 TwitterUserActor（使用异步 API）
    try:
        from actors.twitter_user import TwitterUserActor
        ActorRegistry.register("twitter_user_actor", TwitterUserActor)
        actors["twitter_user_actor"] = TwitterUserActor
        logger.info("已注册 Actor: twitter_user_actor")
    except Exception as e:
        logger.error(f"加载 TwitterUserActor 失败: {e}")

    # 手动导入 TwitterTrendingActor（使用异步 API）
    try:
        from actors.twitter_trending_actor import TwitterTrendingActor
        ActorRegistry.register("twitter_trending_actor", TwitterTrendingActor)
        actors["twitter_trending_actor"] = TwitterTrendingActor
        logger.info("已注册 Actor: twitter_trending_actor")
    except Exception as e:
        logger.error(f"加载 TwitterTrendingActor 失败: {e}")

    # 手动导入 TwitterRandomReadingActor（使用异步 API）
    try:
        from actors.twitter_random_reading_actor import TwitterRandomReadingActor
        ActorRegistry.register("twitter_random_reading_actor", TwitterRandomReadingActor)
        actors["twitter_random_reading_actor"] = TwitterRandomReadingActor
        logger.info("已注册 Actor: twitter_random_reading_actor")
    except Exception as e:
        logger.error(f"加载 TwitterRandomReadingActor 失败: {e}")

    # 手动导入 RedditCommunityActor（使用异步 API）
    try:
        from actors.reddit_community_actor import RedditCommunityActor
        ActorRegistry.register("reddit_community_actor", RedditCommunityActor)
        actors["reddit_community_actor"] = RedditCommunityActor
        logger.info("已注册 Actor: reddit_community_actor")
    except Exception as e:
        logger.error(f"加载 RedditCommunityActor 失败: {e}")

    # 手动导入 ProductHuntActor（纯API模式，无需浏览器）
    try:
        from actors.product_hunt_actor import ProductHuntActor
        ActorRegistry.register("product_hunt_actor", ProductHuntActor)
        actors["product_hunt_actor"] = ProductHuntActor
        logger.info("已注册 Actor: product_hunt_actor")
    except Exception as e:
        logger.error(f"加载 ProductHuntActor 失败: {e}")

    # 手动导入 GoogleTrendsActor（浏览器模式）
    try:
        from actors.google_trends_actor import GoogleTrendsActor
        ActorRegistry.register("google_trends_actor", GoogleTrendsActor)
        actors["google_trends_actor"] = GoogleTrendsActor
        logger.info("已注册 Actor: google_trends_actor")
    except Exception as e:
        logger.error(f"加载 GoogleTrendsActor 失败: {e}")

    # 手动导入 GoogleSuggestActor（纯API模式，无需浏览器）
    try:
        from actors.google_suggest_actor import GoogleSuggestActor
        ActorRegistry.register("google_suggest_actor", GoogleSuggestActor)
        actors["google_suggest_actor"] = GoogleSuggestActor
        logger.info("已注册 Actor: google_suggest_actor")
    except Exception as e:
        logger.error(f"加载 GoogleSuggestActor 失败: {e}")

    # 手动导入 GoogleSearchActor（浏览器模式，搜索结果抓取）
    try:
        from actors.google_search_actor import GoogleSearchActor
        ActorRegistry.register("google_search_actor", GoogleSearchActor)
        actors["google_search_actor"] = GoogleSearchActor
        logger.info("已注册 Actor: google_search_actor")
    except Exception as e:
        logger.error(f"加载 GoogleSearchActor 失败: {e}")

    # 手动导入 BingSearchActor（浏览器模式，搜索结果抓取）
    try:
        from actors.bing_search_actor import BingSearchActor
        ActorRegistry.register("bing_search_actor", BingSearchActor)
        actors["bing_search_actor"] = BingSearchActor
        logger.info("已注册 Actor: bing_search_actor")
    except Exception as e:
        logger.error(f"加载 BingSearchActor 失败: {e}")

    return actors
