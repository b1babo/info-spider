"""
Google Suggest Actor - Google 搜索建议关键词挖掘

无需浏览器，直接调用 Google Suggest API 获取搜索建议。
遵循标准的 create -> extract -> close 模式
"""
import logging
import json
import time
import asyncio
import httpx
from typing import List, Dict, Any
from collections import Counter
from datetime import datetime

from core.base_actor import BaseActor
from core.models import Resource

logger = logging.getLogger(__name__)


class GoogleSuggestActor(BaseActor):
    """Google 搜索建议 Actor - 标准模式"""

    actor_name = "google_suggest_actor"
    actor_description = "Google 搜索建议关键词挖掘（纯API模式）"

    # Google Suggest API
    API_URL = "https://suggestqueries.google.com/complete/search"

    def setup_actions(self):
        """注册所有 Actions"""

        self.register_action(
            "create",
            self.action_create,
            description="初始化任务",
            params_schema={"params": []}
        )

        self.register_action(
            "get_suggestions",
            self.action_get_suggestions,
            description="获取单个关键词的搜索建议并保存到数据库",
            params_schema={
                "params": [
                    {"name": "keyword", "type": "string", "required": True},
                    {"name": "language", "type": "string", "required": False, "default": "en"}
                ]
            }
        )

        self.register_action(
            "expand_keywords",
            self.action_expand_keywords,
            description="扩展关键词并保存到数据库",
            params_schema={
                "params": [
                    {"name": "seed", "type": "string", "required": True},
                    {"name": "alphabet", "type": "boolean", "required": False, "default": True},
                    {"name": "questions", "type": "boolean", "required": False, "default": True},
                    {"name": "modifiers", "type": "boolean", "required": False, "default": True},
                    {"name": "language", "type": "string", "required": False, "default": "en"}
                ]
            }
        )

        self.register_action(
            "batch_expand",
            self.action_batch_expand,
            description="批量扩展多个种子词并保存到数据库",
            params_schema={
                "params": [
                    {"name": "seeds", "type": "array", "required": True},
                    {"name": "max_per_seed", "type": "integer", "required": False, "default": 100},
                    {"name": "delay", "type": "number", "required": False, "default": 1.0}
                ]
            }
        )

        self.register_action(
            "status",
            self.action_status,
            description="获取状态",
            params_schema={"params": []}
        )

        self.register_action(
            "close",
            self.action_close,
            description="关闭任务实例",
            params_schema={"params": []}
        )

        # 状态变量
        self.suggestions_data: Dict[str, Any] = {}
        self.expanded_keywords: List[str] = []
        self.resources: List[Resource] = []

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    async def _fetch_suggestions(self, task, keyword: str, language: str = "en") -> List[str]:
        """获取搜索建议（内部方法）"""
        params = {
            "output": "firefox",
            "client": "firefox",
            "q": keyword,
            "hl": language
        }

        # 获取代理配置
        proxy = None
        if task.profile and hasattr(task.profile, 'proxy'):
            proxy = task.profile.proxy
            if proxy:
                logger.info(f"Using proxy: {proxy}")

        try:
            async with httpx.AsyncClient(timeout=10.0, proxy=proxy) as client:
                response = await client.get(
                    self.API_URL,
                    params=params,
                    headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                return data[1] if len(data) > 1 else []
        except Exception as e:
            logger.error(f"Error fetching suggestions for '{keyword}': {e}")
            return []

    def _build_keyword_resources(self, keywords: List[str]) -> List[Resource]:
        """将关键词转换为 Resource 对象"""
        import hashlib
        resources = []
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

        for keyword in keywords:
            keyword_hash = hashlib.md5(keyword.encode('utf-8')).hexdigest()[:16]
            resource = Resource(
                id=f"kw_{keyword_hash}",
                resource_type="keyword",
                resource_url=f"https://www.google.com/search?q={keyword}",
                resource_content=keyword,
                description=f"Keyword: {keyword}",
                resource_platform="Google Suggest",
                resource_platform_url="https://www.google.com",
                resource_author_name="Google Suggest API",
                resource_create_time=timestamp,
            )
            resources.append(resource)

        return resources

    async def _save_data(self, task, keywords: List[str]) -> Dict[str, Any]:
        """保存关键词数据"""
        if not keywords:
            return {"saved_to": None, "storage_stats": None}

        # 构建 Resource 对象
        resources = self._build_keyword_resources(keywords)

        # 保存到数据库
        from core.task_storage import TaskStorage
        storage = TaskStorage()

        # 1. 保存原始JSON到任务专属目录
        data_dir = task.get_data_dir()
        raw_file = storage.save_raw_result_to_dir(data_dir, resources)

        # 2. 合并到数据库
        stats = storage.merge_to_database(task.task_config.name, resources)

        logger.info(f"[_save_data] Keywords saved: added={stats['added']}, skipped={stats['skipped']}")

        return {
            "saved_to": str(raw_file),
            "storage_stats": stats
        }

    async def _export_analysis(self, task, keywords: List[str]) -> str:
        """导出关键词分析结果到 JSON"""
        if not keywords:
            return None

        # 分析关键词
        keyword_analysis = self._analyze_keywords(keywords)

        export_data = {
            "keywords": keywords,
            "count": len(keywords),
            "analysis": keyword_analysis,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 保存到任务专属目录
        data_dir = task.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = data_dir / f"analysis_{timestamp}.json"

        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[_export_analysis] 分析结果已保存: {export_file}")
        return str(export_file)

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """初始化任务"""
        self.suggestions_data = {}
        self.expanded_keywords = []
        self.resources = []

        return {
            "status": "success",
            "message": "Google Suggest Actor initialized",
            "actor": self.actor_name
        }

    async def action_get_suggestions(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取单个关键词的搜索建议并保存"""
        keyword = action_params.get("keyword", "")
        language = action_params.get("language", "en")

        if not keyword:
            return {"status": "error", "message": "keyword is required"}

        logger.info(f"[get_suggestions] 获取建议: {keyword}")
        suggestions = await self._fetch_suggestions(task, keyword, language)

        # 保存数据
        self.suggestions_data[keyword] = {
            "suggestions": suggestions,
            "count": len(suggestions),
            "language": language
        }

        # 保存到数据库
        save_result = await self._save_data(task, suggestions)

        return {
            "status": "success",
            "keyword": keyword,
            "count": len(suggestions),
            "saved_to": save_result.get("saved_to"),
            "storage_stats": save_result.get("storage_stats")
        }

    async def action_expand_keywords(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """扩展关键词并保存"""
        seed = action_params.get("seed", "")
        use_alphabet = action_params.get("alphabet", True)
        use_questions = action_params.get("questions", True)
        use_modifiers = action_params.get("modifiers", True)
        language = action_params.get("language", "en")

        if not seed:
            return {"status": "error", "message": "seed is required"}

        logger.info(f"[expand_keywords] 扩展关键词: {seed}")

        results = {
            "seed": seed,
            "base_suggestions": [],
            "alphabet_expanded": [],
            "question_expanded": [],
            "modifier_expanded": [],
            "total_unique": 0
        }

        all_suggestions = []

        # 1. 基础建议
        logger.info(f"[expand_keywords] 获取基础建议: {seed}")
        base = await self._fetch_suggestions(task, seed, language)
        results["base_suggestions"] = base
        all_suggestions.extend(base)

        # 2. 字母扩展
        if use_alphabet:
            logger.info(f"[expand_keywords] 字母扩展")
            alphabet_results = []
            for letter in "abcdefghijklmnopqrstuvwxyz":
                expanded = await self._fetch_suggestions(task, f"{seed} {letter}", language)
                alphabet_results.extend(expanded)
                time.sleep(0.1)  # 避免速率限制
            results["alphabet_expanded"] = list(set(alphabet_results))
            all_suggestions.extend(results["alphabet_expanded"])

        # 3. 问题词扩展
        if use_questions:
            logger.info(f"[expand_keywords] 问题词扩展")
            question_prefixes = [
                "how to", "what is", "why", "where", "when", "who", "which",
                "can", "will", "do", "does", "are", "is", "best", "top"
            ]
            question_results = []
            for prefix in question_prefixes:
                questions = await self._fetch_suggestions(task, f"{prefix} {seed}", language)
                question_results.extend(questions)
                time.sleep(0.1)
            results["question_expanded"] = list(set(question_results))
            all_suggestions.extend(results["question_expanded"])

        # 4. 修饰词扩展
        if use_modifiers:
            logger.info(f"[expand_keywords] 修饰词扩展")
            modifiers = [
                "free", "cheap", "online", "near me", "tutorial", "guide",
                "review", "comparison", "vs", "alternative", "example",
                "course", "certification", "jobs", "salary", "tools"
            ]
            modifier_results = []
            for mod in modifiers:
                modified = await self._fetch_suggestions(task, f"{seed} {mod}", language)
                modifier_results.extend(modified)
                time.sleep(0.1)
            results["modifier_expanded"] = list(set(modifier_results))
            all_suggestions.extend(results["modifier_expanded"])

        # 去重统计
        unique_suggestions = list(set(all_suggestions))
        results["total_unique"] = len(unique_suggestions)

        # 保存到状态
        self.suggestions_data[seed] = results
        self.expanded_keywords = unique_suggestions

        logger.info(f"[expand_keywords] 扩展完成: {len(unique_suggestions)} 个唯一关键词")

        # 保存到数据库
        save_result = await self._save_data(task, unique_suggestions)

        # 导出分析结果
        export_file = await self._export_analysis(task, unique_suggestions)

        return {
            "status": "success",
            "seed": seed,
            "total_unique": results.get("total_unique", 0),
            "saved_to": save_result.get("saved_to"),
            "storage_stats": save_result.get("storage_stats"),
            "analysis_file": export_file
        }

    async def action_batch_expand(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """批量扩展多个种子词并保存"""
        seeds = action_params.get("seeds", [])
        max_per_seed = action_params.get("max_per_seed", 100)
        delay = action_params.get("delay", 1.0)

        if not seeds:
            return {"status": "error", "message": "seeds is required"}

        logger.info(f"[batch_expand] 批量扩展 {len(seeds)} 个种子词")

        all_results = {}
        all_keywords = []

        for i, seed in enumerate(seeds):
            logger.info(f"[batch_expand] 处理种子 {i+1}/{len(seeds)}: {seed}")

            result = await self.action_expand_keywords(task, {
                "seed": seed,
                "alphabet": True,
                "questions": True,
                "modifiers": True,
                "language": "en"
            })

            if result["status"] == "success":
                # 限制数量
                unique_keywords = list(set(
                    result["results"]["base_suggestions"] +
                    result["results"]["alphabet_expanded"] +
                    result["results"]["question_expanded"] +
                    result["results"]["modifier_expanded"]
                ))[:max_per_seed]

                all_results[seed] = {
                    "seed": seed,
                    "keywords": unique_keywords,
                    "count": len(unique_keywords)
                }
                all_keywords.extend(unique_keywords)

            # 延迟避免速率限制
            if i < len(seeds) - 1:
                await asyncio.sleep(delay)

        # 保存所有关键词
        save_result = await self._save_data(task, all_keywords)

        # 导出分析结果
        export_file = await self._export_analysis(task, all_keywords)

        return {
            "status": "success",
            "total_seeds": len(seeds),
            "total_keywords": len(all_keywords),
            "saved_to": save_result.get("saved_to"),
            "storage_stats": save_result.get("storage_stats"),
            "analysis_file": export_file
        }

    def _analyze_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        """分析关键词"""
        # 词频统计
        word_counter = Counter()
        for kw in keywords:
            words = kw.lower().split()
            word_counter.update(words)

        # 长度分布
        length_distribution = {"short": 0, "medium": 0, "long": 0}
        for kw in keywords:
            length = len(kw.split())
            if length <= 2:
                length_distribution["short"] += 1
            elif length <= 4:
                length_distribution["medium"] += 1
            else:
                length_distribution["long"] += 1

        return {
            "top_words": word_counter.most_common(20),
            "length_distribution": length_distribution,
            "avg_length": sum(len(kw.split()) for kw in keywords) / len(keywords) if keywords else 0
        }

    async def action_status(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取状态"""
        return {
            "status": "success",
            "actor": self.actor_name,
            "suggestions_count": len(self.suggestions_data),
            "keywords_collected": len(self.expanded_keywords),
            "seeds_processed": list(self.suggestions_data.keys())
        }

    async def action_close(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """关闭任务实例"""
        logger.info(f"[close] 关闭 Google Suggest actor")

        # 清空资源
        collected = len(self.expanded_keywords)
        self.expanded_keywords = []
        self.suggestions_data = {}
        self.resources = []

        return {
            "status": "success",
            "message": "Google Suggest actor closed",
            "keywords_collected": collected
        }
