"""
Actor服务器 - 常驻进程保持浏览器连接
CLI通过HTTP API与服务器通信
"""
import logging
import os
import sys
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from core.models import AppConfig
from core.actor_registry import ActorRegistry
from core.task_instance import TaskInstanceManager
from core.plugin_loader import discover_actors

logger = logging.getLogger(__name__)

# PID文件路径
PID_FILE = ".actor_server.pid"


# ===== 请求/响应模型 =====

class TaskCreateResponse(BaseModel):
    status: str
    task_id: str
    task_name: str
    actor: str


class ActionRequest(BaseModel):
    params: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    server: str = "actor_server"


# ===== 服务器类 =====

class ActorServer:
    """Actor HTTP服务器 - 保持所有TaskInstance常驻"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.manager = TaskInstanceManager.get_manager()

        # 发现并注册所有 Actors
        discover_actors()
        logger.info(f"Registered {len(ActorRegistry.list_actors())} actors")

        self.app = FastAPI(
            title="Actor Server",
            description="常驻进程保持浏览器连接，支持交互式Action执行",
            version="1.0.0"
        )
        self._setup_routes()

    def _setup_routes(self):
        """设置API路由"""

        @self.app.get("/health", response_model=HealthResponse)
        async def health():
            """健康检查"""
            return HealthResponse(status="ok")

        @self.app.get("/")
        async def root():
            """根路径 - API信息"""
            return {
                "server": "Actor Server",
                "version": "1.0.0",
                "docs": "/docs",
                "endpoints": {
                    "health": "GET /health",
                    "task_templates": "GET /task-templates",
                    "actors": "GET /actors",
                    "tasks": "GET /tasks",
                    "create-task": "POST /task/{task_name}/create-task",
                    "action": "POST /task/{task_id}/action/{action_name}",
                    "status": "GET /task/{task_id}/status",
                    "close-task": "POST /task/{task_id}/close-task"
                }
            }

        @self.app.get("/task-templates")
        async def list_task_templates():
            """列出所有任务模板"""
            templates = []
            for task in self.config.tasks:
                templates.append({
                    "name": task.name,
                    "actor": task.actor,
                    "profile": task.use_profile,
                    "enabled": task.enable,
                    "actions": len(task.actions),
                    "params": task.params
                })
            return {"templates": templates}

        @self.app.get("/actors")
        async def list_actors():
            """列出所有Actors"""
            return {"actors": ActorRegistry.list_actors()}

        @self.app.get("/tasks")
        async def list_tasks():
            """列出所有活跃的任务实例"""
            instances = self.manager.list_instances()
            return {"tasks": instances}

        @self.app.post("/task/{task_name}/create-task", response_model=TaskCreateResponse)
        async def create_task(task_name: str):
            """创建Task实例（仅创建，不执行任何action）

            后续需要通过 POST /task/{task_id}/action/create 来执行 actor 的 create action
            """
            try:
                task_config = self.config.get_task(task_name)
                if not task_config:
                    raise HTTPException(status_code=404, detail=f"Task not found: {task_name}")

                profile = self.config.get_profile(task_config.use_profile)
                if not profile:
                    raise HTTPException(status_code=404, detail=f"Profile not found: {task_config.use_profile}")

                actor_class = ActorRegistry.get(task_config.actor)
                if not actor_class:
                    raise HTTPException(status_code=404, detail=f"Actor not found: {task_config.actor}")

                actor = actor_class()

                # 创建实例（异步）
                task_id = await self.manager.create_instance(task_config, profile, actor)

                logger.info(f"Created task instance: {task_id}")
                return TaskCreateResponse(
                    status="success",
                    task_id=task_id,
                    task_name=task_config.name,
                    actor=task_config.actor
                )
            except HTTPException:
                raise
            except Exception as e:
                import traceback
                import sys
                error_type = type(e).__name__
                error_msg = str(e)
                tb = traceback.format_exc()
                logger.error(f"Error creating task [{error_type}]: {error_msg}\n{tb}")
                raise HTTPException(status_code=500, detail=f"{error_type}: {error_msg}\n{tb}")

        @self.app.post("/task/{task_id}/action/{action_name}")
        async def execute_action(task_id: str, action_name: str, request: ActionRequest):
            """执行Action"""
            try:
                params = request.params or {}

                instance = self.manager.get_instance(task_id)
                if not instance:
                    raise HTTPException(status_code=404, detail=f"Task instance not found: {task_id}")

                # 执行 action
                result = await instance.execute_action(action_name, params)
                result["task_id"] = task_id

                return result
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error executing action: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/task/{task_id}/close-task")
        async def close_task(task_id: str):
            """关闭Task实例"""
            try:
                instance = self.manager.get_instance(task_id)
                if not instance:
                    raise HTTPException(status_code=404, detail=f"Task instance not found: {task_id}")

                result = await instance.execute_action("close", {})
                await self.manager.close_instance(task_id)

                result["task_id"] = task_id
                return result
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error closing task: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/task/{task_id}/status")
        async def get_status(task_id: str):
            """获取Task状态"""
            instance = self.manager.get_instance(task_id)
            if not instance:
                raise HTTPException(status_code=404, detail=f"Task instance not found: {task_id}")
            return instance.get_status()

    def run(self, host: str = '127.0.0.1', port: int = 7666):
        """启动服务器"""
        logger.info(f"Starting Actor server on http://{host}:{port}")
        logger.info(f"API docs available at http://{host}:{port}/docs")
        logger.info("Task instances will be kept alive in server process")


        uvicorn.run(
            self.app,
            host=host,
            port=port,
            log_level="info"
        )


def start_server(config: AppConfig, host: str = '127.0.0.1', port: int = 7666):
    """启动Actor服务器"""
    # 记录PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    try:
        server = ActorServer(config)
        server.run(host, port)
    finally:
        # 退出时删除PID文件
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
