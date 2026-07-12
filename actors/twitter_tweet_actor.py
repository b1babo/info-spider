"""Twitter/X 单条推文 Actor。

自动判断推文URL是普通推文还是文章，然后提取相应内容。
推文和文章使用相同的URL格式（/status/{id}），需要通过API响应检测。
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional

import jmespath
from playwright.async_api import Response

from core.base_actor import BaseActor
from core.models import Resource, Author, Analytics, ResourceMedia
from core.utils import HumanUtils

logger = logging.getLogger(__name__)


class TwitterTweetActor(BaseActor):
    """Twitter/X 单条推文 Actor"""

    actor_name = "twitter_tweet_actor"
    actor_description = "Twitter/X 单条推文操作Actor，自动判断推文或文章类型"

    def setup_actions(self):
        """注册所有单条推文相关的Actions"""

        self.register_action(
            "visit",
            self.action_visit,
            description="访问单条推文URL并自动判断类型（推文/文章）",
            params_schema={
                "params": [
                    {"name": "tweet_url", "type": "string", "required": True,
                     "description": "推文URL，如 https://x.com/Kristof_Poland/status/2075539011502817493"},
                    {"name": "extract_replies", "type": "boolean", "required": False, "default": False,
                     "description": "是否提取回复"},
                    {"name": "max_replies", "type": "integer", "required": False, "default": 20,
                     "description": "最大回复数量"}
                ]
            }
        )

        self.register_action(
            "close",
            self.action_close,
            description="关闭任务实例并保存数据",
            params_schema={"params": []}
        )

        # 初始化内部状态
        self.resources: List[Resource] = []
        self.detected_type: Optional[str] = None  # 'tweet' 或 'article'
        self.task_name: str = "single_tweet"  # 任务名称，用于保存数据

    async def action_visit(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """访问单条推文URL并自动判断类型"""
        tweet_url = action_params.get('tweet_url')
        extract_replies = action_params.get('extract_replies', False)
        max_replies = action_params.get('max_replies', 20)

        if not tweet_url:
            return {
                "status": "error",
                "message": "Missing required parameter: tweet_url"
            }

        logger.info(f"[TwitterTweetActor] Visiting: {tweet_url}")

        try:
            # 重置状态
            self.resources = []
            self.detected_type = None

            # 1. 启用响应拦截进行类型检测
            self._setup_type_detection(task)

            # 2. 访问页面
            await task.page.goto(tweet_url, timeout=60000)
            await asyncio.sleep(3)

            # 等待页面加载
            try:
                await task.page.wait_for_selector('[data-testid="tweet"]', timeout=10000)
            except:
                logger.warning("Tweet selector not found, page may have loaded differently")

            # 3. 根据检测到的类型提取内容
            if self.detected_type == "article":
                logger.info(f"[TwitterTweetActor] Detected as ARTICLE, using article extraction")
                result = await self._extract_article(task, tweet_url)
            else:
                logger.info(f"[TwitterTweetActor] Detected as TWEET, using tweet extraction")
                result = await self._extract_tweet(task, tweet_url, extract_replies, max_replies)

            # 4. 保存数据并返回结果
            saved_to = None
            storage_stats = None
            if self.resources:
                from core.task_storage import TaskStorage
                storage = TaskStorage()
                raw_file = storage.save_raw_result(self.task_name, self.resources)
                stats = storage.merge_to_database(self.task_name, self.resources)
                saved_to = str(raw_file)
                storage_stats = {
                    "total": stats.get('total', len(self.resources)),
                    "added": stats.get('added', 0),
                    "skipped": stats.get('skipped', 0),
                    "errors": stats.get('errors', 0)
                }
                logger.info(f"[TwitterTweetActor] 保存完成: raw={raw_file.name}, added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

            # 添加保存信息到结果中
            result["saved_to"] = saved_to
            result["storage_stats"] = storage_stats

            return result

        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error visiting {tweet_url}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "url": tweet_url
            }

    def _setup_type_detection(self, task):
        """设置类型检测响应拦截器"""
        detected_type = None

        async def detect_type(response: Response):
            nonlocal detected_type
            if detected_type:  # 已经检测到类型，不再处理
                return

            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return
            if "/graphql/" not in response.url:
                return

            try:
                data = await response.json()
                # 检测文章字段
                result = jmespath.search('data.tweetResult.result', data)
                if result and isinstance(result, dict) and 'article' in result:
                    detected_type = "article"
                    logger.info(f"[TwitterTweetActor] Type detection: ARTICLE")
                else:
                    # 检查是否是普通推文
                    if result or jmespath.search('data.threaded_conversation_with_injections_v2', data):
                        detected_type = "tweet"
                        logger.info(f"[TwitterTweetActor] Type detection: TWEET")
            except Exception as e:
                logger.debug(f"[TwitterTweetActor] Type detection error: {e}")

        task.page.on("response", detect_type)

        # 等待一小段时间让检测完成
        async def wait_for_detection():
            await asyncio.sleep(2)
            self.detected_type = detected_type

        # 创建后台任务等待检测
        asyncio.create_task(wait_for_detection())

    async def _extract_tweet(self, task, url: str, extract_replies: bool = False,
                           max_replies: int = 20) -> Dict[str, Any]:
        """提取普通推文内容"""
        try:
            tweet_data = await self._extract_tweet_from_page(task, url)

            if tweet_data:
                self.resources.append(tweet_data)

                # 提取回复
                replies = []
                if extract_replies:
                    replies = await self._extract_replies_from_page(task, max_replies)

                return {
                    "status": "success",
                    "type": "tweet",
                    "tweet": {
                        "id": tweet_data.id,
                        "content": tweet_data.resource_content,
                        "author": tweet_data.resource_author_name,
                        "url": tweet_data.resource_url,
                        "likes": tweet_data.analytics.like_count if tweet_data.analytics else 0,
                        "replies": tweet_data.analytics.reply_count if tweet_data.analytics else 0,
                        "retweets": tweet_data.analytics.share_count if tweet_data.analytics else 0,
                        "created_at": tweet_data.resource_create_time
                    },
                    "replies_count": len(replies),
                    "replies": replies[:5]  # 只返回前5条作为预览
                }
            else:
                return {
                    "status": "warning",
                    "message": "Tweet page loaded but content extraction failed",
                    "url": url
                }
        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting tweet: {e}")
            return {
                "status": "error",
                "message": str(e),
                "url": url
            }

    async def _extract_article(self, task, url: str) -> Dict[str, Any]:
        """提取文章内容"""
        try:
            # 使用文章特定的提取逻辑
            article_data = await self._extract_article_from_page(task, url)

            if article_data:
                self.resources.append(article_data)

                return {
                    "status": "success",
                    "type": "article",
                    "article": {
                        "id": article_data.id,
                        "title": article_data.description,  # 文章标题存储在 description 中
                        "content": article_data.resource_content,
                        "author": article_data.resource_author_name,
                        "url": article_data.resource_url,
                        "views": article_data.analytics.view_count if article_data.analytics else 0,
                        "likes": article_data.analytics.like_count if article_data.analytics else 0,
                        "created_at": article_data.resource_create_time
                    }
                }
            else:
                return {
                    "status": "warning",
                    "message": "Article page loaded but content extraction failed",
                    "url": url
                }
        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting article: {e}")
            return {
                "status": "error",
                "message": str(e),
                "url": url
            }

    async def _extract_tweet_from_page(self, task, url: str) -> Optional[Resource]:
        """从页面元素提取推文内容"""
        try:
            # 获取推文文本
            selectors = [
                '[data-testid="tweetText"]',
                '[data-testid="tweet"] div[lang]',
            ]

            content = ""
            for selector in selectors:
                try:
                    element = await task.page.query_selector(selector)
                    if element:
                        content = await element.inner_text()
                        break
                except:
                    continue

            # 获取作者信息
            author_name = ""
            author_display_name = ""
            author_url = ""
            try:
                author_elem = await task.page.query_selector('[data-testid="User-Name"] a')
                if author_elem:
                    author_url = await author_elem.get_attribute('href')
                    author_text = await author_elem.inner_text()
                    author_name = author_text.strip().lstrip('@')
            except:
                pass

            # 获取显示名称
            try:
                display_elem = await task.page.query_selector('[data-testid="User-Name"] span span')
                if display_elem:
                    author_display_name = await display_elem.inner_text()
            except:
                pass

            # 获取时间戳
            create_time = ""
            try:
                time_elem = await task.page.query_selector('time')
                if time_elem:
                    create_time = await time_elem.get_attribute('datetime')
            except:
                pass

            # 提取 analytics（点赞、转发等）
            analytics = Analytics()
            try:
                analytics_selectors = {
                    'reply_count': '[data-testid="reply"] span',
                    'retweet_count': '[data-testid="retweet"] span',
                    'like_count': '[data-testid="like"] span',
                }

                for key, selector in analytics_selectors.items():
                    try:
                        elem = await task.page.query_selector(selector)
                        if elem:
                            text = await elem.inner_text()
                            # 解析数字（支持 K, M 等单位）
                            import re
                            numbers = re.findall(r'[\d.]+[KMB]?', text)
                            if numbers:
                                num_str = numbers[0].upper()
                                if 'K' in num_str:
                                    value = float(num_str.replace('K', '')) * 1000
                                elif 'M' in num_str:
                                    value = float(num_str.replace('M', '')) * 1000000
                                elif 'B' in num_str:
                                    value = float(num_str.replace('B', '')) * 1000000000
                                else:
                                    value = float(num_str)
                                setattr(analytics, key, int(value))
                    except:
                        continue
            except:
                pass

            # 提取 URL
            urls = []
            try:
                link_elems = await task.page.query_selector_all('[data-testid="tweet"] a')
                for link in link_elems[:10]:
                    href = await link.get_attribute('href')
                    if href and href.startswith('http'):
                        urls.append({"url": href, "expanded_url": href})
            except:
                pass

            # 提取 hashtags
            hashtags = []
            try:
                hashtag_elems = await task.page.query_selector_all('a[href*="/hashtag/"]')
                for tag in hashtag_elems:
                    text = await tag.inner_text()
                    if text:
                        hashtags.append(text.lstrip('#'))
            except:
                pass

            # 从 URL 提取 tweet ID
            tweet_id = url.rstrip('/').split('/')[-1]

            resource = Resource(
                id=tweet_id,
                resource_url=url,
                resource_content=content[:1000],
                resource_author_name=author_name,
                resource_author_display_name=author_display_name,
                resource_author_url=author_url,
                resource_platform="X/Twitter",
                resource_platform_url="https://x.com",
                resource_type="tweet",
                resource_create_time=create_time,
                analytics=analytics,
                urls=urls,
                hashtags=hashtags
            )

            return resource

        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting tweet from page: {e}")
            return None

    async def _extract_article_from_page(self, task, url: str) -> Optional[Resource]:
        """从页面元素提取文章内容（使用API拦截）"""
        try:
            # 使用API拦截获取完整文章内容
            article_data = await self._fetch_article_data_via_api(task, url)
            if article_data:
                return self._build_article_resource_from_api(article_data, url)

            # 如果API拦截失败，回退到DOM提取
            return await self._extract_article_from_dom(task, url)

        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting article: {e}")
            return None

    async def _fetch_article_data_via_api(self, task, url: str) -> Optional[dict]:
        """通过API拦截获取文章数据"""
        article_result = None
        api_event = asyncio.Event()

        async def on_response(response):
            nonlocal article_result
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return
            if "/graphql/" not in response.url:
                return

            try:
                data = await response.json()
                # 查找包含article的tweet result
                result = jmespath.search('data.tweetResult.result', data)
                if result and 'article' in result:
                    # 检查是否有完整的内容
                    article = jmespath.search('article.article_results.result', result)
                    if article and article.get('content_state', {}).get('blocks'):
                        article_result = result
                        api_event.set()
                        logger.info("[TwitterTweetActor] 通过API获取到完整文章数据")
            except Exception as e:
                logger.debug(f"[TwitterTweetActor] API响应解析错误: {e}")

        task.page.on("response", on_response)

        try:
            # 导航到页面
            await task.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # 等待API响应（最多15秒）
            try:
                await asyncio.wait_for(api_event.wait(), timeout=15)
            except asyncio.TimeoutError:
                logger.warning("[TwitterTweetActor] 文章API响应超时")

            # 额外等待确保数据完整
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[TwitterTweetActor] 获取文章API数据时出错: {e}")
        finally:
            try:
                task.page.remove_listener("response", on_response)
            except Exception:
                pass

        return article_result

    def _build_article_resource_from_api(self, tweet_result: dict, url: str) -> Optional[Resource]:
        """从API数据构建文章Resource"""
        try:
            article = jmespath.search('article.article_results.result', tweet_result)
            if not article:
                return None

            tweet_rest_id = tweet_result.get('rest_id', '')
            user_result = tweet_result.get('core', {}).get('user_results', {}).get('result', {})

            # 提取作者信息
            author_info = self._extract_author_from_api(user_result)

            # 提取analytics
            legacy = tweet_result.get('legacy', {})
            views = tweet_result.get('views', {})

            analytics = Analytics(
                view_count=int(views.get("count", "0") or 0),
                like_count=legacy.get("favorite_count", 0),
                reply_count=legacy.get("reply_count", 0),
                share_count=legacy.get("retweet_count", 0),
                bookmark_count=legacy.get("bookmark_count", 0),
                referenced_count=legacy.get("quote_count", 0),
            )

            # 提取文章元数据
            title = article.get('title', '') or ''
            preview = article.get('preview_text', '') or ''
            summary = article.get('summary_text', '') or ''

            # 提取正文内容
            content_state = article.get('content_state', {}) or {}
            media_entities = article.get('media_entities', []) or []

            # 重建正文 Markdown
            body_md = ""
            if content_state.get('blocks'):
                # 这里需要一个函数来将draftjs转换为markdown
                # 为了简化，我们先尝试提取纯文本
                body_md = self._extract_text_from_blocks(content_state.get('blocks', []))

            # 拼接完整内容
            parts = []
            if title:
                parts.append(f"# {title}")
            if summary:
                parts.append(f"> {summary}".replace("\n", "\n> "))
            if body_md:
                parts.append(body_md)

            resource_content = "\n\n".join(parts).strip()

            # 提取媒体
            media = []
            cover_url = jmespath.search('cover_media.media_info.original_img_url', article)
            if cover_url:
                media.append(ResourceMedia(media_type="image", media_url=cover_url))

            resource = Resource(
                id=tweet_rest_id,
                resource_type="article",
                resource_url=url,
                resource_content=resource_content,
                description=preview,
                resource_platform="X/Twitter",
                resource_platform_url="https://x.com",
                resource_author_name=author_info.get('author_name', ''),
                resource_author_display_name=author_info.get('author_display_name', ''),
                resource_author_url=author_info.get('author_url', ''),
                resource_media=media,
                analytics=analytics,
                resource_create_time=legacy.get("created_at", ""),
            )
            return resource

        except Exception as e:
            logger.error(f"[TwitterTweetActor] 构建文章Resource失败: {e}")
            return None

    def _extract_author_from_api(self, user_result: dict) -> dict:
        """从API数据提取作者信息"""
        user_legacy = user_result.get('legacy', {})
        user_core = user_result.get('core', {})
        name = user_core.get('screen_name', '')
        return {
            'author_name': name,
            'author_display_name': user_core.get('name', ''),
            'author_url': f"https://x.com/{name}" if name else ''
        }

    def _extract_text_from_blocks(self, blocks: list) -> str:
        """从content_state blocks提取文本内容"""
        texts = []
        for block in blocks:
            if isinstance(block, dict):
                block_type = block.get('type', '')
                if block_type == 'text':
                    # 提取文本块内容
                    inline_text_ranges = block.get('inlineTextRanges', [])
                    text = ''.join([r.get('text', '') for r in inline_text_ranges])
                    texts.append(text)
                elif block_type == 'paragraph':
                    # 处理段落
                    inline_text_ranges = block.get('inlineTextRanges', [])
                    text = ''.join([r.get('text', '') for r in inline_text_ranges])
                    if text:
                        texts.append(text)
                elif block_type == 'header':
                    # 处理标题
                    text = block.get('text', '')
                    if text:
                        texts.append(f"## {text}")
                elif block_type == 'image':
                    # 处理图片
                    alt_text = block.get('altText', '')
                    texts.append(f"[图片: {alt_text}]" if alt_text else "[图片]")
                elif block_type == 'video':
                    texts.append("[视频]")
                elif block_type == 'divider':
                    texts.append("---")

        return '\n\n'.join(texts)

    async def _extract_article_from_dom(self, task, url: str) -> Optional[Resource]:
        """回退方法：从DOM提取文章内容（简化版）"""
        try:
            # 获取文章标题
            title = ""
            try:
                # 文章标题可能在不同的位置
                title_selectors = [
                    '[data-testid="tweetText"]',  # 某些情况下
                    'h1',
                    'h2',
                ]
                for selector in title_selectors:
                    try:
                        element = await task.page.query_selector(selector)
                        if element:
                            title = await element.inner_text()
                            if len(title) > 10:  # 确保是有效标题
                                break
                    except:
                        continue
            except:
                pass

            # 获取文章内容
            content = ""
            try:
                # 尝试获取完整的文章内容
                content_elem = await task.page.query_selector('[data-testid="tweetText"]')
                if content_elem:
                    content = await content_elem.inner_text()
            except:
                pass

            # 获取作者信息
            author_name = ""
            author_display_name = ""
            author_url = ""
            try:
                author_elem = await task.page.query_selector('[data-testid="User-Name"] a')
                if author_elem:
                    author_url = await author_elem.get_attribute('href')
                    author_text = await author_elem.inner_text()
                    author_name = author_text.strip().lstrip('@')
            except:
                pass

            # 获取显示名称
            try:
                display_elem = await task.page.query_selector('[data-testid="User-Name"] span span')
                if display_elem:
                    author_display_name = await display_elem.inner_text()
            except:
                pass

            # 获取时间戳
            create_time = ""
            try:
                time_elem = await task.page.query_selector('time')
                if time_elem:
                    create_time = await time_elem.get_attribute('datetime')
            except:
                pass

            # 提取 analytics
            analytics = Analytics()
            try:
                # 文章可能显示阅读量
                view_elem = await task.page.query_selector('[data-testid="view"] span')
                if view_elem:
                    text = await view_elem.inner_text()
                    import re
                    numbers = re.findall(r'[\d.]+[KMB]?', text)
                    if numbers:
                        num_str = numbers[0].upper()
                        if 'K' in num_str:
                            analytics.view_count = int(float(num_str.replace('K', '')) * 1000)
                        elif 'M' in num_str:
                            analytics.view_count = int(float(num_str.replace('M', '')) * 1000000)
                        else:
                            analytics.view_count = int(float(num_str))
            except:
                pass

            # 从 URL 提取 article ID
            article_id = url.rstrip('/').split('/')[-1]

            resource = Resource(
                id=article_id,
                resource_url=url,
                resource_content=content[:5000],  # 文章可能更长
                resource_author_name=author_name,
                resource_author_display_name=author_display_name,
                resource_author_url=author_url,
                resource_platform="X/Twitter",
                resource_platform_url="https://x.com",
                resource_type="article",
                resource_create_time=create_time,
                analytics=analytics,
                description=title  # 标题存储在 description 中
            )

            return resource

        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting article from page: {e}")
            return None

    async def _extract_replies_from_page(self, task, max_replies: int) -> List[Dict[str, Any]]:
        """从页面提取回复"""
        replies = []

        try:
            # 查找回复元素
            reply_selectors = [
                '[data-testid="reply"]',
                '[role="article"]',
            ]

            # 滚动加载更多回复
            for _ in range(2):
                await HumanUtils.smart_scroll(task.page, 1, 1)
                await asyncio.sleep(1)

            # 尝试提取回复
            reply_elements = await task.page.query_selector_all('[data-testid="tweet"]')

            # 跳过第一条（那是原推文）
            for i, elem in enumerate(reply_elements[1:max_replies+1]):
                try:
                    text = await elem.inner_text()
                    replies.append({
                        "index": i,
                        "content": text[:500],
                        "full_extract": False
                    })
                except:
                    continue

        except Exception as e:
            logger.error(f"[TwitterTweetActor] Error extracting replies: {e}")

        return replies

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务实例并保存数据"""
        # 保存数据
        saved_to = None
        storage_stats = None
        if self.resources:
            from core.task_storage import TaskStorage
            storage = TaskStorage()
            raw_file = storage.save_raw_result(self.task_name, self.resources)
            stats = storage.merge_to_database(self.task_name, self.resources)
            saved_to = str(raw_file)
            storage_stats = {
                "total": stats.get('total', len(self.resources)),
                "added": stats.get('added', 0),
                "skipped": stats.get('skipped', 0),
                "errors": stats.get('errors', 0)
            }
            logger.info(f"[TwitterTweetActor] 保存完成: raw={raw_file.name}, added={stats.get('added', 0)}, skipped={stats.get('skipped', 0)}")

        # 关闭页面
        try:
            await task.page.close()
            logger.info(f"[TwitterTweetActor] 页面已关闭")
        except Exception as e:
            logger.warning(f"[TwitterTweetActor] 关闭页面时出错: {e}")

        return {
            "status": "success",
            "message": "Twitter tweet actor 已关闭",
            "resources_collected": len(self.resources),
            "saved_to": saved_to,
            "storage_stats": storage_stats
        }
