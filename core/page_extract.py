"""任意页面正文抽取（通用，与站点无关）.

供搜索类 actor 注册 ``extract_page`` action 使用：create-task 已导航到任意 URL 后，
抽取 title、meta description、H2 章节（标题 + 其后正文要点），保存为 Resource 记录：

- ``page_meta``：description=页面标题，resource_content=meta description
- ``page_section``：每条 H2 章节，description=章节标题，resource_content=正文要点，
  ``urls=[{"type": "page_section", "rank", "heading"}]``

zed-agent 侧（serp.fetch_page_content）消费 saved_to 文件还原 {title, meta_description,
sections}。与搜索结果抽取（scroll_and_extract）互不干扰。
"""
import hashlib
import logging
from typing import Any, Dict, List

from core.models import Analytics, Resource

logger = logging.getLogger(__name__)

# 单章节正文上限（字符），防止超大页面撑爆 payload
_SECTION_BODY_LIMIT = 4000

# H2 章节抽取：沿 h2 的后续兄弟节点走到下一个 H1/H2；
# P/UL/OL/BLOCKQUOTE 直接取文本，DIV/SECTION/ARTICLE 取其中段落（全局去重防重复捕获）
_EXTRACT_JS = """
(maxSections) => {
  const seen = new Set();
  const grab = (el) => {
    if (!el || seen.has(el)) return '';
    seen.add(el);
    return (el.innerText || '').trim();
  };
  const sections = [];
  for (const h of document.querySelectorAll('h2')) {
    if (sections.length >= maxSections) break;
    const heading = (h.innerText || '').trim();
    if (!heading) continue;
    const parts = [];
    let node = h.nextElementSibling;
    while (node && node.tagName !== 'H1' && node.tagName !== 'H2') {
      if (!seen.has(node)) {
        if (['P', 'UL', 'OL', 'BLOCKQUOTE'].includes(node.tagName)) {
          const text = grab(node);
          if (text) parts.push(text);
        } else if (['DIV', 'SECTION', 'ARTICLE'].includes(node.tagName)) {
          for (const p of node.querySelectorAll('p, li, blockquote')) {
            const text = grab(p);
            if (text) parts.push(text);
          }
          seen.add(node);
        }
      }
      node = node.nextElementSibling;
    }
    const body = parts.join('\\n\\n').slice(0, 4000);
    if (body) sections.push({heading, body});
  }
  return sections;
}
"""


async def extract_page_content(task, max_sections: int = 20) -> Dict[str, Any]:
    """在当前已导航页面上抽取 title / meta description / H2 章节."""
    page = task.page
    title = await page.title()
    meta = ""
    try:
        meta_elem = page.locator("meta[name='description']").first
        if await meta_elem.count() > 0:
            meta = await meta_elem.get_attribute("content") or ""
    except Exception as e:
        logger.debug(f"[extract_page] meta description 读取失败: {e}")

    sections: List[Dict[str, str]] = []
    try:
        sections = await page.evaluate(_EXTRACT_JS, max_sections)
    except Exception as e:
        logger.warning(f"[extract_page] 章节抽取失败: {e}")

    return {
        "url": page.url,
        "title": (title or "").strip(),
        "meta_description": (meta or "").strip(),
        "sections": sections,
    }


def page_resources(result: Dict[str, Any], platform: str) -> List[Resource]:
    """抽取结果转 Resource 记录（page_meta + page_section*）."""
    rid_base = hashlib.md5(result["url"].encode("utf-8")).hexdigest()[:12]
    resources = [
        Resource(
            id=f"pg_{rid_base}",
            resource_type="page_meta",
            resource_url=result["url"],
            resource_content=result.get("meta_description", ""),
            description=result.get("title", ""),
            resource_platform=platform,
            resource_platform_url=result["url"],
            analytics=Analytics(),
        )
    ]
    for rank, sec in enumerate(result.get("sections", []), start=1):
        resources.append(
            Resource(
                id=f"pg_{rid_base}_{rank}",
                resource_type="page_section",
                resource_url=result["url"],
                resource_content=sec.get("body", "")[:_SECTION_BODY_LIMIT],
                description=sec.get("heading", ""),
                resource_platform=platform,
                resource_platform_url=result["url"],
                analytics=Analytics(),
                urls=[{"type": "page_section", "rank": rank, "heading": sec.get("heading", "")}],
            )
        )
    return resources


async def extract_and_save(task, actor_name: str, max_sections: int = 20) -> Dict[str, Any]:
    """抽取当前页面并保存（create → extract_page → 读 saved_to 模式的中段）."""
    result = await extract_page_content(task, max_sections)
    resources = page_resources(result, actor_name)

    saved_to = None
    stats = None
    if resources:
        from core.task_storage import TaskStorage

        storage = TaskStorage()
        raw_file = storage.save_raw_result(task.task_config.name, resources)
        stats = storage.merge_to_database(task.task_config.name, resources)
        saved_to = str(raw_file)

    logger.info(
        f"[extract_page] url={result['url']} 章节={len(result.get('sections', []))} "
        f"saved={saved_to is not None}"
    )
    return {
        "status": "success",
        "url": result["url"],
        "title": result["title"],
        "meta_description": result["meta_description"],
        "section_count": len(result.get("sections", [])),
        "saved_to": saved_to,
        "storage_stats": stats,
    }
