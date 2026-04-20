"""
Google Suggest Actor - Google 搜索建议关键词挖掘

无需浏览器，直接调用 Google Suggest API 获取搜索建议。
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
    """Google 搜索建议 Actor - 关键词挖掘"""

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
            description="获取单个关键词的搜索建议",
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
            description="扩展关键词（字母+修饰词）",
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
            description="批量扩展多个种子词",
            params_schema={
                "params": [
                    {"name": "seeds", "type": "array", "required": True},
                    {"name": "max_per_seed", "type": "integer", "required": False, "default": 100},
                    {"name": "delay", "type": "number", "required": False, "default": 1.0}
                ]
            }
        )

        self.register_action(
            "export_results",
            self.action_export_results,
            description="导出结果为 JSON",
            params_schema={
                "params": [
                    {"name": "format", "type": "string", "required": False, "default": "json"}
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
            description="关闭任务",
            params_schema={"params": []}
        )

        # 状态变量
        self.suggestions_data: Dict[str, Any] = {}
        self.expanded_keywords: List[str] = []

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

    async def action_create(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """初始化任务"""
        self.suggestions_data = {}
        self.expanded_keywords = []

        return {
            "status": "success",
            "message": "Google Suggest Actor initialized",
            "actor": self.actor_name
        }

    async def action_get_suggestions(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """获取单个关键词的搜索建议"""
        keyword = action_params.get("keyword", "")
        language = action_params.get("language", "en")

        if not keyword:
            return {"status": "error", "message": "keyword is required"}

        suggestions = await self._fetch_suggestions(task, keyword, language)

        # 保存数据
        self.suggestions_data[keyword] = {
            "suggestions": suggestions,
            "count": len(suggestions),
            "language": language
        }

        return {
            "status": "success",
            "keyword": keyword,
            "suggestions": suggestions,
            "count": len(suggestions)
        }

    async def action_expand_keywords(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """扩展关键词"""
        seed = action_params.get("seed", "")
        use_alphabet = action_params.get("alphabet", True)
        use_questions = action_params.get("questions", True)
        use_modifiers = action_params.get("modifiers", True)
        language = action_params.get("language", "en")

        if not seed:
            return {"status": "error", "message": "seed is required"}

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
        logger.info(f"Fetching base suggestions for: {seed}")
        base = await self._fetch_suggestions(task, seed, language)
        results["base_suggestions"] = base
        all_suggestions.extend(base)

        # 2. 字母扩展
        if use_alphabet:
            logger.info(f"Fetching alphabet expansions for: {seed}")
            alphabet_results = []
            for letter in "abcdefghijklmnopqrstuvwxyz":
                expanded = await self._fetch_suggestions(task, f"{seed} {letter}", language)
                alphabet_results.extend(expanded)
                time.sleep(0.1)  # 避免速率限制
            results["alphabet_expanded"] = list(set(alphabet_results))
            all_suggestions.extend(results["alphabet_expanded"])

        # 3. 问题词扩展
        if use_questions:
            logger.info(f"Fetching question expansions for: {seed}")
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
            logger.info(f"Fetching modifier expansions for: {seed}")
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

        logger.info(f"Keyword expansion complete: {len(unique_suggestions)} unique keywords")

        return {
            "status": "success",
            "results": results
        }

    async def action_batch_expand(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """批量扩展多个种子词"""
        seeds = action_params.get("seeds", [])
        max_per_seed = action_params.get("max_per_seed", 100)
        delay = action_params.get("delay", 1.0)

        if not seeds:
            return {"status": "error", "message": "seeds is required"}

        all_results = {}

        for i, seed in enumerate(seeds):
            logger.info(f"Processing seed {i+1}/{len(seeds)}: {seed}")

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
                ))
                all_results[seed] = {
                    "seed": seed,
                    "keywords": unique_keywords[:max_per_seed],
                    "count": len(unique_keywords[:max_per_seed])
                }

            # 延迟避免速率限制
            if i < len(seeds) - 1:
                await asyncio.sleep(delay)

        return {
            "status": "success",
            "results": all_results,
            "total_seeds": len(seeds),
            "total_keywords": sum(r["count"] for r in all_results.values())
        }

    async def action_export_results(self, task, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """导出结果到任务专属目录"""
        format_type = action_params.get("format", "json")

        if not self.expanded_keywords:
            return {"status": "error", "message": "No keywords to export"}

        # 分析关键词
        keyword_analysis = self._analyze_keywords(self.expanded_keywords)

        export_data = {
            "keywords": self.expanded_keywords,
            "count": len(self.expanded_keywords),
            "analysis": keyword_analysis,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if format_type == "json":
            # 保存到任务专属目录
            data_dir = task.get_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file = data_dir / f"export_{timestamp}.json"

            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Export data saved to: {export_file}")

            return {
                "status": "success",
                "data": export_data,
                "file": str(export_file)
            }

        return {"status": "error", "message": f"Unsupported format: {format_type}"}

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
        """关闭任务"""
        saved_path = None
        export_path = None
        stats = {"total": 0, "added": 0, "skipped": 0}

        # 保存数据到任务专属目录
        if self.expanded_keywords:
            from core.task_storage import TaskStorage
            storage = TaskStorage()

            # 将关键词转换为 Resource 对象
            import hashlib
            resources = []
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            for keyword in self.expanded_keywords:
                keyword_hash = hashlib.md5(keyword.encode('utf-8')).hexdigest()[:16]
                resource = Resource(
                    id=f"kw_{keyword_hash}",
                    resource_type="keyword",
                    resource_url=f"https://www.google.com/search?q={keyword}",
                    resource_content=keyword,
                    resource_platform="Google Suggest",
                    resource_author_name="Google Suggest API",
                    resource_create_time=timestamp,
                )
                resources.append(resource)

            # 保存到任务专属目录 data/tasks/{task_id}/
            data_dir = task.get_data_dir()
            raw_file = storage.save_raw_result_to_dir(data_dir, resources)

            # 合并到数据库
            stats = storage.merge_to_database(task.task_config.name, resources)
            saved_path = str(raw_file)
            logger.info(f"[{task.task_id}] Keywords saved: added={stats['added']}, skipped={stats['skipped']}")

            # 导出分析结果
            export_result = await self.action_export_results(task, {"format": "json"})
            if export_result.get("status") == "success":
                export_path = export_result.get("file")
                logger.info(f"[{task.task_id}] Export saved to: {export_path}")

        self.expanded_keywords = []
        self.suggestions_data = {}

        return {
            "status": "success",
            "message": "Actor closed",
            "saved_to": saved_path,
            "export_file": export_path,
            "storage_stats": stats
        }
