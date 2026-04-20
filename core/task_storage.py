"""
Task Storage Module

Provides task-level storage with hierarchical daily sharding.
Each task has its own directory with:
- index.json - Global index with metadata and cross-file references
- YYYY/MM/DD/{task_name}_YYYY-MM-DD.json - Daily data shards in hierarchical directories
- YYYY/MM/DD/raw/ - Original JSON results from each run
"""

import json
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, date
from core.models import Resource
import logging

logger = logging.getLogger(__name__)


class TaskStorage:
    """
    Task-level storage manager with hierarchical daily sharding.

    Directory structure:
    data/{task_name}/
    ├── index.json
    └── {year}/
        └── {month}/
            └── {day}/
                ├── {task_name}_{year}-{month}-{day}.json
                └── raw/
                    └── {task_name}_{year}-{month}-{day}-HH-MM.json

    Features:
    - Hierarchical daily shards for efficient querying
    - Global index for fast lookups
    - Automatic index updates on merge
    - Cross-file queries with filtering
    - Friendly for AI analysis (Claude Skills)
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the task storage manager.

        Args:
            data_dir: Root directory for all task data
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, task_name: str) -> threading.Lock:
        """Get or create a lock for the specific task"""
        with self._global_lock:
            if task_name not in self._locks:
                self._locks[task_name] = threading.Lock()
            return self._locks[task_name]

    def get_task_dir(self, task_name: str) -> Path:
        """Get the task directory"""
        task_dir = self.data_dir / task_name
        task_dir.mkdir(exist_ok=True)
        return task_dir

    def get_index_path(self, task_name: str) -> Path:
        """Get the path to the index file"""
        return self.get_task_dir(task_name) / "index.json"

    def get_day_dir(self, task_name: str, year: str, month: str, day: str) -> Path:
        """Get the directory for a specific year/month/day"""
        day_dir = self.get_task_dir(task_name) / year / month / day
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def get_shard_path(self, task_name: str, year: str, month: str, day: str) -> Path:
        """Get the path to a daily shard file"""
        return self.get_day_dir(task_name, year, month, day) / f"{task_name}_{year}-{month}-{day}.json"

    def get_raw_dir(self, task_name: str, year: str, month: str, day: str) -> Path:
        """Get the raw files directory for a specific day"""
        raw_dir = self.get_day_dir(task_name, year, month, day) / "raw"
        raw_dir.mkdir(exist_ok=True)
        return raw_dir

    def _parse_date_parts(self, date_str: str) -> tuple:
        """
        Parse date string into year, month, day parts.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            Tuple of (year, month, day)
        """
        parts = date_str.split('-')
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        return None, None, None

    def _load_index(self, task_name: str) -> Dict:
        """Load the index file, creating empty structure if not exists"""
        index_path = self.get_index_path(task_name)

        if not index_path.exists():
            return {
                "version": "3.0",
                "total": 0,
                "shards": {},
                "indexes": {
                    "by_id": {},
                    "by_platform": {},
                    "by_author": {},
                    "by_hashtag": {},
                    "by_date": {}
                },
                "last_updated": None
            }

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[{task_name}] Error loading index: {e}")
            return {
                "version": "3.0",
                "total": 0,
                "shards": {},
                "indexes": {
                    "by_id": {},
                    "by_platform": {},
                    "by_author": {},
                    "by_hashtag": {},
                    "by_date": {}
                },
                "last_updated": None
            }

    def _save_index(self, task_name: str, index: Dict) -> None:
        """Save the index file"""
        index_path = self.get_index_path(task_name)
        index["last_updated"] = datetime.now().isoformat()

        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _load_shard(self, task_name: str, year: str, month: str, day: str) -> List[Dict]:
        """Load data from a specific shard file"""
        shard_path = self.get_shard_path(task_name, year, month, day)

        if not shard_path.exists():
            return []

        try:
            with open(shard_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                return data
            return []

        except json.JSONDecodeError as e:
            logger.error(f"[{task_name}] Error loading shard {year}-{month}-{day}: {e}")
            return []

    def _save_shard(self, task_name: str, year: str, month: str, day: str, data: List[Dict]) -> None:
        """Save data to a specific shard file"""
        shard_path = self.get_shard_path(task_name, year, month, day)

        with open(shard_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _get_shard_date(self, resource_date: Optional[str]) -> str:
        """
        Extract shard date from resource date or use today.

        Returns:
            Date string in YYYY-MM-DD format
        """
        if resource_date:
            try:
                dt = datetime.fromisoformat(resource_date.replace('Z', '+00:00'))
                return dt.date().isoformat()
            except:
                pass

        return date.today().isoformat()

    def save_raw_result(self, task_name: str, resources: List[Resource]) -> Path:
        """
        Save raw JSON result to the hierarchical raw/ directory.

        Args:
            task_name: Name of the task
            resources: List of resources to save

        Returns:
            Path to the saved file
        """
        today = date.today()
        year = today.strftime("%Y")
        month = today.strftime("%m")
        day = today.strftime("%d")

        raw_dir = self.get_raw_dir(task_name, year, month, day)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        raw_file = raw_dir / f"{task_name}_{timestamp}.json"

        data = [r.model_dump() for r in resources]

        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"[{task_name}] Raw data saved: {raw_file}")
        return raw_file

    def save_raw_result_to_dir(self, directory: Path, resources: List[Resource]) -> Path:
        """
        Save raw JSON result to a specified directory (e.g., task-specific data dir).

        Args:
            directory: Directory path to save the file
            resources: List of resources to save

        Returns:
            Path to the saved file
        """
        directory.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        raw_file = directory / f"data_{timestamp}.json"

        data = [r.model_dump() for r in resources]

        with open(raw_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Raw data saved to task dir: {raw_file}")
        return raw_file

    def merge_raw_files(self, task_name: str, year: str, month: str, day: str) -> Dict[str, int]:
        """
        Merge all raw files from a specific day into the main shard file.
        Ensures the main shard contains all data from raw/ directory without duplicates.

        Args:
            task_name: Name of the task
            year: Year (YYYY)
            month: Month (MM)
            day: Day (DD)

        Returns:
            Statistics dictionary with keys: total, added, skipped, errors
        """
        lock = self._get_lock(task_name)

        stats = {
            'total': 0,
            'added': 0,
            'skipped': 0,
            'errors': 0,
            'raw_files_processed': 0
        }

        with lock:
            try:
                raw_dir = self.get_raw_dir(task_name, year, month, day)

                # Find all raw files for this day
                raw_files = list(raw_dir.glob(f"{task_name}_{year}-{month}-{day}-*.json"))
                raw_files.sort()  # Process in chronological order

                if not raw_files:
                    logger.info(f"[{task_name}] No raw files found for {year}/{month}/{day}")
                    return stats

                logger.info(f"[{task_name}] Found {len(raw_files)} raw files to merge")

                # Load index for deduplication
                index = self._load_index(task_name)
                by_id = index["indexes"]["by_id"]

                # Collect all resources from raw files
                all_raw_resources = []

                for raw_file in raw_files:
                    try:
                        with open(raw_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        if isinstance(data, list):
                            all_raw_resources.extend(data)
                            stats['raw_files_processed'] += 1
                            logger.debug(f"[{task_name}] Loaded {len(data)} resources from {raw_file.name}")

                    except Exception as e:
                        logger.error(f"[{task_name}] Error loading raw file {raw_file}: {e}")
                        stats['errors'] += 1

                stats['total'] = len(all_raw_resources)

                if not all_raw_resources:
                    logger.info(f"[{task_name}] No resources found in raw files")
                    return stats

                # Load existing shard data
                shard_key = f"{year}/{month}/{day}"
                existing_shard = self._load_shard(task_name, year, month, day)
                existing_ids = {r.get('id') for r in existing_shard if r.get('id')}

                # Check if shard file exists
                shard_path = self.get_shard_path(task_name, year, month, day)
                shard_exists = shard_path.exists()

                # Merge resources with deduplication
                new_resources = []

                for resource_dict in all_raw_resources:
                    try:
                        resource_id = resource_dict.get('id')

                        # Skip if no ID
                        if not resource_id:
                            stats['skipped'] += 1
                            continue

                        # Check if already in shard
                        if resource_id in existing_ids:
                            stats['skipped'] += 1
                            continue

                        # Check if in index (other shards) - only if shard exists
                        # If shard doesn't exist, we want to include all raw resources
                        if shard_exists and resource_id in by_id:
                            stats['skipped'] += 1
                            continue

                        # Add to new resources
                        new_resources.append(resource_dict)
                        existing_ids.add(resource_id)
                        stats['added'] += 1

                    except Exception as e:
                        logger.error(f"[{task_name}] Error processing raw resource: {e}")
                        stats['errors'] += 1

                # Merge and save shard
                # Always save if: (1) there are new resources, or (2) shard doesn't exist and we have raw resources
                if new_resources or (not shard_exists and all_raw_resources):
                    # If shard doesn't exist, use all raw resources (deduplicated)
                    if not shard_exists:
                        merged_shard = all_raw_resources
                    else:
                        merged_shard = existing_shard + new_resources

                    # Save shard
                    self._save_shard(task_name, year, month, day, merged_shard)

                    # Update index for new resources (or all resources if shard didn't exist)
                    resources_to_index = new_resources if shard_exists else all_raw_resources

                    for resource_dict in resources_to_index:
                        resource_id = resource_dict.get('id')
                        if resource_id:
                            by_id[resource_id] = shard_key

                        # Update shard metadata
                        if shard_key not in index["shards"]:
                            index["shards"][shard_key] = {
                                "count": 0,
                                "ids": [],
                                "platforms": set(),
                                "authors": set(),
                                "hashtags": set()
                            }
                        else:
                            # Convert to sets for manipulation
                            index["shards"][shard_key]["platforms"] = set(index["shards"][shard_key].get("platforms", []))
                            index["shards"][shard_key]["authors"] = set(index["shards"][shard_key].get("authors", []))
                            index["shards"][shard_key]["hashtags"] = set(index["shards"][shard_key].get("hashtags", []))

                        shard_meta = index["shards"][shard_key]
                        shard_meta["count"] += 1
                        shard_meta["ids"].append(resource_id)

                        # Update platform index
                        platform = resource_dict.get('resource_platform') or "Unknown"
                        shard_meta["platforms"].add(platform)
                        if platform not in index["indexes"]["by_platform"]:
                            index["indexes"]["by_platform"][platform] = []
                        if shard_key not in index["indexes"]["by_platform"][platform]:
                            index["indexes"]["by_platform"][platform].append(shard_key)

                        # Update author index
                        author = resource_dict.get('resource_author_name')
                        if author:
                            shard_meta["authors"].add(author)
                            if author not in index["indexes"]["by_author"]:
                                index["indexes"]["by_author"][author] = []
                            if shard_key not in index["indexes"]["by_author"][author]:
                                index["indexes"]["by_author"][author].append(shard_key)

                        # Update hashtag index
                        for tag in (resource_dict.get('hashtags') or []):
                            shard_meta["hashtags"].add(tag)
                            if tag not in index["indexes"]["by_hashtag"]:
                                index["indexes"]["by_hashtag"][tag] = []
                            if shard_key not in index["indexes"]["by_hashtag"][tag]:
                                index["indexes"]["by_hashtag"][tag].append(shard_key)

                        # Update date index
                        shard_date = f"{year}-{month}-{day}"
                        if shard_date not in index["indexes"]["by_date"]:
                            index["indexes"]["by_date"][shard_date] = []
                        if shard_key not in index["indexes"]["by_date"][shard_date]:
                            index["indexes"]["by_date"][shard_date].append(shard_key)

                    # Convert sets to lists for JSON serialization
                    for shard_meta in index["shards"].values():
                        shard_meta["platforms"] = list(shard_meta["platforms"])
                        shard_meta["authors"] = list(shard_meta["authors"])
                        shard_meta["hashtags"] = list(shard_meta["hashtags"])

                    # Update total count
                    index["total"] = sum(s["count"] for s in index["shards"].values())

                    # Save index
                    self._save_index(task_name, index)

                    logger.info(
                        f"[{task_name}] Raw files merged: "
                        f"shard={shard_key}, files={stats['raw_files_processed']}, "
                        f"total={stats['total']}, added={stats['added']}, "
                        f"skipped={stats['skipped']}, shard_size={len(merged_shard)}"
                    )
                else:
                    logger.info(f"[{task_name}] No new resources to add from raw files")

            except Exception as e:
                logger.error(f"[{task_name}] Error merging raw files: {e}")
                stats['errors'] = stats['total']

        return stats

    def merge_to_database(self, task_name: str, resources: List[Resource]) -> Dict[str, int]:
        """
        Merge new resources into daily shards with deduplication.

        Args:
            task_name: Name of the task
            resources: List of resources to merge

        Returns:
            Statistics dictionary with keys: total, added, skipped, errors
        """
        if not resources:
            return {'total': 0, 'added': 0, 'skipped': 0, 'errors': 0}

        lock = self._get_lock(task_name)

        stats = {
            'total': len(resources),
            'added': 0,
            'skipped': 0,
            'errors': 0
        }

        with lock:
            try:
                # Load index
                index = self._load_index(task_name)
                by_id = index["indexes"]["by_id"]

                # Group resources by shard date
                shards: Dict[str, List[Dict]] = {}

                for resource in resources:
                    try:
                        resource_dict = resource.model_dump()
                        resource_id = resource.id

                        # Check for duplicate by ID
                        if resource_id and resource_id in by_id:
                            stats['skipped'] += 1
                            continue

                        # Determine shard date
                        shard_date = self._get_shard_date(resource.resource_create_time)
                        year, month, day = self._parse_date_parts(shard_date)

                        if not year or not month or not day:
                            logger.warning(f"[{task_name}] Invalid date format: {shard_date}")
                            stats['skipped'] += 1
                            continue

                        # Shard key for grouping
                        shard_key = f"{year}/{month}/{day}"

                        # Load existing shard data
                        if shard_key not in shards:
                            shards[shard_key] = self._load_shard(task_name, year, month, day)

                        # Get existing IDs in this shard
                        shard_ids = {r.get('id') for r in shards[shard_key] if r.get('id')}

                        # Check duplicate within shard
                        if resource_id and resource_id in shard_ids:
                            stats['skipped'] += 1
                            continue

                        # Add to shard
                        shards[shard_key].append(resource_dict)
                        shard_ids.add(resource_id)

                        # Update index
                        if resource_id:
                            by_id[resource_id] = shard_key

                        # Update shard metadata
                        if shard_key not in index["shards"]:
                            index["shards"][shard_key] = {
                                "count": 0,
                                "ids": [],
                                "platforms": set(),
                                "authors": set(),
                                "hashtags": set()
                            }
                        else:
                            # Convert existing lists to sets for in-memory manipulation
                            index["shards"][shard_key]["platforms"] = set(index["shards"][shard_key].get("platforms", []))
                            index["shards"][shard_key]["authors"] = set(index["shards"][shard_key].get("authors", []))
                            index["shards"][shard_key]["hashtags"] = set(index["shards"][shard_key].get("hashtags", []))

                        shard_meta = index["shards"][shard_key]
                        shard_meta["count"] += 1
                        shard_meta["ids"].append(resource_id)

                        # Update platform index
                        platform = resource.resource_platform or "Unknown"
                        shard_meta["platforms"].add(platform)
                        if platform not in index["indexes"]["by_platform"]:
                            index["indexes"]["by_platform"][platform] = []
                        if shard_key not in index["indexes"]["by_platform"][platform]:
                            index["indexes"]["by_platform"][platform].append(shard_key)

                        # Update author index
                        author = resource.resource_author_name
                        if author:
                            shard_meta["authors"].add(author)
                            if author not in index["indexes"]["by_author"]:
                                index["indexes"]["by_author"][author] = []
                            if shard_key not in index["indexes"]["by_author"][author]:
                                index["indexes"]["by_author"][author].append(shard_key)

                        # Update hashtag index
                        for tag in (resource.hashtags or []):
                            shard_meta["hashtags"].add(tag)
                            if tag not in index["indexes"]["by_hashtag"]:
                                index["indexes"]["by_hashtag"][tag] = []
                            if shard_key not in index["indexes"]["by_hashtag"][tag]:
                                index["indexes"]["by_hashtag"][tag].append(shard_key)

                        # Update date index
                        if shard_date not in index["indexes"]["by_date"]:
                            index["indexes"]["by_date"][shard_date] = []
                        if shard_key not in index["indexes"]["by_date"][shard_date]:
                            index["indexes"]["by_date"][shard_date].append(shard_key)

                        stats['added'] += 1

                    except Exception as e:
                        logger.error(f"[{task_name}] Error processing resource {resource.id}: {e}")
                        stats['errors'] += 1

                # Save all modified shards
                for shard_key, shard_data in shards.items():
                    year, month, day = shard_key.split('/')
                    self._save_shard(task_name, year, month, day, shard_data)
                    logger.info(f"[{task_name}] Saved shard {shard_key}: {len(shard_data)} records")

                # Convert sets to lists for JSON serialization
                for shard_meta in index["shards"].values():
                    shard_meta["platforms"] = list(shard_meta["platforms"])
                    shard_meta["authors"] = list(shard_meta["authors"])
                    shard_meta["hashtags"] = list(shard_meta["hashtags"])

                # Update total count
                index["total"] = sum(s["count"] for s in index["shards"].values())

                # Save index
                self._save_index(task_name, index)

                logger.info(
                    f"[{task_name}] Merge complete: "
                    f"total={stats['total']}, added={stats['added']}, "
                    f"skipped={stats['skipped']}, errors={stats['errors']}"
                )

            except Exception as e:
                logger.error(f"[{task_name}] Merge error: {e}")
                stats['errors'] = stats['total']

        return stats

    def query_resources(self, task_name: str,
                       limit: int = 100,
                       offset: int = 0,
                       filters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """
        Query resources from daily shards.

        Args:
            task_name: Name of the task
            limit: Maximum number of results
            offset: Number of results to skip
            filters: Optional filters
                - resource_id: str (exact match)
                - platform: str
                - min_likes: int
                - max_likes: int
                - author: str (partial match)
                - resource_type: str
                - search: str (search in content)
                - date_from: str (YYYY-MM-DD)
                - date_to: str (YYYY-MM-DD)
                - hashtag: str

        Returns:
            List of resource dictionaries
        """
        index = self._load_index(task_name)

        if not index["shards"]:
            return []

        # Determine which shards to load based on filters
        shards_to_load = set(index["shards"].keys())

        if filters:
            # Filter by date range
            if 'date_from' in filters:
                shards_to_load = {s for s in shards_to_load if s >= filters['date_from'].replace('-', '/')}
            if 'date_to' in filters:
                shards_to_load = {s for s in shards_to_load if s <= filters['date_to'].replace('-', '/')}

            # Filter by platform
            if 'platform' in filters:
                platform_shards = index["indexes"]["by_platform"].get(filters['platform'], [])
                shards_to_load &= set(platform_shards)

            # Filter by author
            if 'author' in filters:
                matching_authors = [a for a in index["indexes"]["by_author"]
                                   if filters['author'].lower() in a.lower()]
                author_shards = []
                for a in matching_authors:
                    author_shards.extend(index["indexes"]["by_author"].get(a, []))
                shards_to_load &= set(author_shards)

            # Filter by hashtag
            if 'hashtag' in filters:
                tag_shards = index["indexes"]["by_hashtag"].get(filters['hashtag'], [])
                shards_to_load &= set(tag_shards)

        # Load and filter data from relevant shards (sorted newest first)
        all_results = []

        for shard_key in sorted(shards_to_load, reverse=True):
            year, month, day = shard_key.split('/')
            shard_data = self._load_shard(task_name, year, month, day)
            all_results.extend(shard_data)

        # Apply additional filters
        results = all_results

        if filters:
            if 'resource_id' in filters:
                results = [r for r in results if r.get('id') == filters['resource_id']]

            if 'resource_type' in filters:
                results = [r for r in results if r.get('resource_type') == filters['resource_type']]

            if 'min_likes' in filters:
                min_likes = filters['min_likes']
                results = [r for r in results if r.get('analytics', {}).get('like_count', 0) >= min_likes]

            if 'max_likes' in filters:
                max_likes = filters['max_likes']
                results = [r for r in results if r.get('analytics', {}).get('like_count', 0) <= max_likes]

            if 'search' in filters:
                search = filters['search'].lower()
                results = [r for r in results
                          if search in (r.get('resource_content') or '').lower()
                          or search in (r.get('description') or '').lower()]

        # Sort by create time (newest first) and apply pagination
        results.sort(key=lambda x: x.get('resource_create_time', ''), reverse=True)
        results = results[offset:offset + limit]

        return results

    def get_task_stats(self, task_name: str) -> Dict[str, Any]:
        """
        Get statistics about a task.

        Args:
            task_name: Name of the task

        Returns:
            Dictionary with statistics
        """
        index = self._load_index(task_name)

        # Calculate date range from shard keys
        shard_dates = []
        for shard_key in index.get("shards", {}).keys():
            parts = shard_key.split('/')
            if len(parts) == 3:
                shard_dates.append('-'.join(parts))

        stats = {
            'total': index.get('total', 0),
            'by_platform': {},
            'shard_count': len(index.get('shards', {})),
            'date_range': {
                'earliest': min(shard_dates) if shard_dates else None,
                'latest': max(shard_dates) if shard_dates else None
            },
            'top_authors': [],
            'top_hashtags': [],
        }

        # Calculate stats from index
        platform_counts = {}
        for platform, shard_keys in index['indexes']['by_platform'].items():
            platform_counts[platform] = sum(
                index['shards'].get(k, {}).get('count', 0)
                for k in shard_keys
            )
        stats['by_platform'] = platform_counts

        # Get top hashtags
        hashtag_counts = {}
        for tag, shard_keys in index['indexes']['by_hashtag'].items():
            hashtag_counts[tag] = len(shard_keys)
        stats['top_hashtags'] = sorted(
            hashtag_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Get top authors
        author_counts = {}
        for author, shard_keys in index['indexes']['by_author'].items():
            author_counts[author] = len(shard_keys)
        stats['top_authors'] = [
            {'name': name, 'shards': count}
            for name, count in sorted(author_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        ]

        return stats

    def list_all_tasks(self) -> List[str]:
        """List all task directories"""
        tasks = []
        for item in self.data_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                index_file = item / "index.json"
                if index_file.exists() or (item / "2026").is_dir():  # Check for new structure
                    tasks.append(item.name)
        return sorted(tasks)

    def get_shard_dates(self, task_name: str) -> List[str]:
        """Get list of all shard dates (YYYY-MM-DD) for a task"""
        index = self._load_index(task_name)
        shard_keys = sorted(index.get('shards', {}).keys(), reverse=True)
        # Convert "2026/01/25" to "2026-01-25"
        return [k.replace('/', '-') for k in shard_keys]

    def rebuild_index(self, task_name: str) -> Dict:
        """
        Rebuild the index from existing shard files.

        Useful if index is corrupted or missing.
        """
        task_dir = self.get_task_dir(task_name)
        lock = self._get_lock(task_name)

        with lock:
            # Initialize empty index
            index = {
                "version": "3.0",
                "total": 0,
                "shards": {},
                "indexes": {
                    "by_id": {},
                    "by_platform": {},
                    "by_author": {},
                    "by_hashtag": {},
                    "by_date": {}
                },
                "last_updated": None
            }

            # Scan year directories
            for year_dir in sorted(task_dir.iterdir()):
                if not year_dir.is_dir() or not year_dir.name.isdigit():
                    continue

                # Scan month directories
                for month_dir in sorted(year_dir.iterdir()):
                    if not month_dir.is_dir():
                        continue

                    # Scan day directories
                    for day_dir in sorted(month_dir.iterdir()):
                        if not day_dir.is_dir():
                            continue

                        day = day_dir.name
                        if not day.isdigit():
                            continue

                        year = year_dir.name
                        month = month_dir.name
                        shard_key = f"{year}/{month}/{day}"

                        # Look for shard file
                        shard_file = day_dir / f"{task_name}_{year}-{month}-{day}.json"
                        if not shard_file.exists():
                            continue

                        shard_data = self._load_shard(task_name, year, month, day)
                        if not shard_data:
                            continue

                        # Build metadata for this shard
                        shard_meta = {
                            "count": len(shard_data),
                            "ids": [],
                            "platforms": set(),
                            "authors": set(),
                            "hashtags": set()
                        }

                        for r in shard_data:
                            rid = r.get('id')
                            if rid:
                                shard_meta["ids"].append(rid)
                                index["indexes"]["by_id"][rid] = shard_key

                            platform = r.get('resource_platform') or "Unknown"
                            shard_meta["platforms"].add(platform)
                            if platform not in index["indexes"]["by_platform"]:
                                index["indexes"]["by_platform"][platform] = []
                            if shard_key not in index["indexes"]["by_platform"][platform]:
                                index["indexes"]["by_platform"][platform].append(shard_key)

                            author = r.get('resource_author_name')
                            if author:
                                shard_meta["authors"].add(author)
                                if author not in index["indexes"]["by_author"]:
                                    index["indexes"]["by_author"][author] = []
                                if shard_key not in index["indexes"]["by_author"][author]:
                                    index["indexes"]["by_author"][author].append(shard_key)

                            for tag in (r.get('hashtags') or []):
                                shard_meta["hashtags"].add(tag)
                                if tag not in index["indexes"]["by_hashtag"]:
                                    index["indexes"]["by_hashtag"][tag] = []
                                if shard_key not in index["indexes"]["by_hashtag"][tag]:
                                    index["indexes"]["by_hashtag"][tag].append(shard_key)

                            # Update date index
                            shard_date = f"{year}-{month}-{day}"
                            if shard_date not in index["indexes"]["by_date"]:
                                index["indexes"]["by_date"][shard_date] = []
                            if shard_key not in index["indexes"]["by_date"][shard_date]:
                                index["indexes"]["by_date"][shard_date].append(shard_key)

                        # Convert sets to lists
                        shard_meta["platforms"] = list(shard_meta["platforms"])
                        shard_meta["authors"] = list(shard_meta["authors"])
                        shard_meta["hashtags"] = list(shard_meta["hashtags"])

                        index["shards"][shard_key] = shard_meta

            index["total"] = sum(s["count"] for s in index["shards"].values())

            self._save_index(task_name, index)

            return {
                "shards_processed": len(index["shards"]),
                "total_records": index["total"]
            }

    def export_to_json(self, task_name: str, output_path: Optional[Path] = None,
                       filters: Optional[Dict] = None) -> Path:
        """Export task data to JSON file"""
        if output_path is None:
            task_dir = self.get_task_dir(task_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = task_dir / f"export_{timestamp}.json"

        resources = self.query_resources(task_name, limit=999999, filters=filters)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(resources, f, ensure_ascii=False, indent=2)

        logger.info(f"[{task_name}] Exported {len(resources)} resources to {output_path}")
        return output_path

    def export_to_csv(self, task_name: str, output_path: Optional[Path] = None,
                      filters: Optional[Dict] = None) -> Path:
        """Export task data to CSV file"""
        import csv

        if output_path is None:
            task_dir = self.get_task_dir(task_name)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = task_dir / f"export_{timestamp}.csv"

        resources = self.query_resources(task_name, limit=999999, filters=filters)

        if not resources:
            logger.warning(f"[{task_name}] No resources to export")
            return output_path

        fieldnames = [
            'id', 'resource_type', 'resource_url', 'resource_content',
            'description', 'author_name', 'platform', 'like_count',
            'reply_count', 'share_count', 'resource_create_time'
        ]

        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()

            for r in resources:
                row = {
                    'id': r.get('id', ''),
                    'resource_type': r.get('resource_type', ''),
                    'resource_url': r.get('resource_url', ''),
                    'resource_content': (r.get('resource_content') or '')[:500],
                    'description': r.get('description', ''),
                    'author_name': r.get('resource_author_name', ''),
                    'platform': r.get('resource_platform', ''),
                    'like_count': r.get('analytics', {}).get('like_count', 0),
                    'reply_count': r.get('analytics', {}).get('reply_count', 0),
                    'share_count': r.get('analytics', {}).get('share_count', 0),
                    'resource_create_time': r.get('resource_create_time', ''),
                }
                writer.writerow(row)

        logger.info(f"[{task_name}] Exported {len(resources)} resources to {output_path}")
        return output_path

    def clear_task_data(self, task_name: str, include_raw: bool = False) -> bool:
        """Clear all data for a task"""
        task_dir = self.get_task_dir(task_name)

        lock = self._get_lock(task_name)
        with lock:
            try:
                # Delete index
                index_path = self.get_index_path(task_name)
                if index_path.exists():
                    index_path.unlink()

                # Delete year directories
                for year_dir in task_dir.iterdir():
                    if year_dir.is_dir() and year_dir.name.isdigit():
                        import shutil
                        shutil.rmtree(year_dir)

                logger.info(f"[{task_name}] Task data cleared (raw={include_raw})")
                return True

            except Exception as e:
                logger.error(f"[{task_name}] Error clearing task data: {e}")
                return False
