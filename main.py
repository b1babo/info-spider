import logging
import os
import sys
import yaml
import time
import argparse
import subprocess
import platform
import json
import copy
import httpx
from pydantic import ValidationError

# 引入我们定义的模块
from core.models import AppConfig
from core.task_storage import TaskStorage
from core.plugin_loader import discover_actors
from pathlib import Path

from core import setup_logging
setup_logging.setup_logging()

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = "config.yaml"
SERVER_URL = "http://127.0.0.1:7666"


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Info-Spider - Actor框架浏览器自动化系统"
    )

    # Actor命令
    parser.add_argument("--create-task", type=str, metavar="TASK_NAME",
                       help="创建任务实例（指定任务模板名称）")
    parser.add_argument("--close-task", type=str, metavar="TASK_ID",
                       help="关闭任务实例（指定任务实例ID）")
    parser.add_argument("--task-id", type=str,
                       help="指定任务实例ID")
    parser.add_argument("--action", type=str,
                       help="指定要执行的action名称")
    parser.add_argument("--action-params", type=str,
                       help="Action参数，JSON格式")
    parser.add_argument("--list-templates", action="store_true",
                       help="列出所有任务模板")
    parser.add_argument("--list-instances", action="store_true",
                       help="列出所有活跃的任务实例")
    parser.add_argument("--list-actors", action="store_true",
                       help="列出所有可用的Actors")

    # 服务器命令
    parser.add_argument("--server", type=str, choices=["start", "stop", "status"],
                       help="服务器操作: start/stop/status")
    parser.add_argument("--server-host", type=str, default="127.0.0.1",
                       help="服务器地址 (默认: 127.0.0.1)")
    parser.add_argument("--server-port", type=int, default=7666,
                       help="服务器端口 (默认: 7666)")

    # Storage命令（兼容现有功能）
    parser.add_argument("--stats", type=str, nargs="?", const="__all__",
                       metavar="TASK_NAME", help="显示任务统计信息")
    parser.add_argument("--query", type=str, metavar="TASK_NAME",
                       help="查询任务数据")

    # 兼容旧模式的单次执行
    parser.add_argument("--params", "-p", type=str,
                       help="任务参数（兼容旧模式）")

    return parser.parse_args()


def load_and_validate_config(path: str) -> AppConfig:
    """读取并校验配置"""
    if not os.path.exists(path):
        logger.info(f"找不到配置文件: {path}")
        sys.exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return AppConfig(**yaml.safe_load(f))
    except ValidationError as e:
        logger.info("配置文件校验失败！")
        logger.info(e)
        sys.exit(1)
    except Exception as e:
        logger.info(f"未知错误: {e}")
        sys.exit(1)


def check_server(url: str = SERVER_URL) -> bool:
    """检查服务器是否运行"""
    try:
        response = httpx.get(f"{url}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


def handle_server_commands(args, config: AppConfig):
    """处理服务器相关命令"""
    from core.actor_server import start_server

    server_url = f"http://{args.server_host}:{args.server_port}"

    if args.server == "start":
        if check_server(server_url):
            logger.info(f"服务器已在运行: {server_url}")
            logger.info(f"API文档: {server_url}/docs")
            return

        logger.info(f"正在启动Actor服务器: {server_url}")
        logger.info(f"API文档将提供在: {server_url}/docs")
        try:
            start_server(config, args.server_host, args.server_port)
        except KeyboardInterrupt:
            logger.info("\n服务器已停止")
        except Exception as e:
            logger.error(f"启动服务器失败: {e}")
            sys.exit(1)

    elif args.server == "status":
        if check_server(server_url):
            logger.info(f"✓ 服务器运行中: {server_url}")

            try:
                response = httpx.get(f"{server_url}/tasks", timeout=5)
                if response.status_code == 200:
                    result = response.json()
                    tasks = result.get("tasks", [])
                    if tasks:
                        logger.info(f"  活跃的任务 ({len(tasks)}):")
                        for t in tasks:
                            logger.info(f"    - {t['task_id']}: {t['task_name']} ({t['status']})")
                    else:
                        logger.info("  没有活跃的任务")
            except Exception as e:
                logger.warning(f"无法获取任务: {e}")
        else:
            logger.info(f"✗ 服务器未运行: {server_url}")
            logger.info("  使用 --server start 启动服务器")

    elif args.server == "stop":
        pid_file = ".actor_server.pid"
        if not os.path.exists(pid_file):
            logger.info("服务器未运行（未找到PID文件）")
            return

        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())

            logger.info(f"正在停止服务器进程 (PID: {pid})...")

            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)

            # 等待进程退出
            for _ in range(10):
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                     capture_output=True, check=True)
                    else:
                        os.kill(pid, 0)  # 检查进程是否存在
                    time.sleep(0.5)
                except:
                    break
            else:
                logger.warning("服务器可能未正常退出")

            logger.info("服务器已停止")
        except subprocess.CalledProcessError:
            logger.info("服务器进程已停止")
        except ProcessLookupError:
            logger.info("服务器进程不存在")
        except Exception as e:
            logger.error(f"停止服务器失败: {e}")
        finally:
            if os.path.exists(pid_file):
                os.remove(pid_file)


def handle_actor_commands(args):
    """处理Actor命令（通过服务器API）"""
    server_url = f"http://{args.server_host}:{args.server_port}"

    # 检查服务器
    if not check_server(server_url):
        logger.error(f"服务器未运行: {server_url}")
        logger.info("请先启动服务器: python main.py --server start")
        sys.exit(1)

    # 列出任务模板
    if args.list_templates:
        try:
            response = httpx.get(f"{server_url}/task-templates", timeout=10)
            if response.status_code == 200:
                result = response.json()
                templates = result.get("templates", [])
                print(f"\n=== 任务模板 ({len(templates)}) ===")
                for tmpl in templates:
                    print(f"  • {tmpl['name']}")
                    print(f"    Actor: {tmpl['actor']}")
                    print(f"    Profile: {tmpl.get('profile', 'N/A')}")
                    print(f"    Actions: {tmpl.get('actions', 0)} 个")
                    if tmpl.get('params'):
                        print(f"    Params: {tmpl['params']}")
                return
        except Exception as e:
            logger.error(f"获取任务模板失败: {e}")
            sys.exit(1)

    # 列出任务实例
    if args.list_instances:
        try:
            response = httpx.get(f"{server_url}/tasks", timeout=10)
            if response.status_code == 200:
                result = response.json()
                instances = result.get("tasks", [])
                print(f"\n=== 活跃的任务实例 ({len(instances)}) ===")
                for inst in instances:
                    print(f"  • {inst['task_id']}")
                    print(f"    任务名: {inst['task_name']}")
                    print(f"    Actor: {inst['actor']}")
                    print(f"    状态: {inst['status']}")
                return
        except Exception as e:
            logger.error(f"获取任务实例失败: {e}")
            sys.exit(1)

    # 列出actors
    if args.list_actors:
        try:
            response = httpx.get(f"{server_url}/actors", timeout=10)
            if response.status_code == 200:
                result = response.json()
                actors = result.get("actors", [])
                print(f"\n=== 可用的Actors ({len(actors)}) ===")
                for actor in actors:
                    print(f"  • {actor['name']}: {actor.get('description', '')}")
                return
        except Exception as e:
            logger.error(f"获取Actor列表失败: {e}")
            sys.exit(1)

    # 创建task实例（仅创建，不执行action）
    if args.create_task:
        try:
            response = httpx.post(
                f"{server_url}/task/{args.create_task}/create-task",
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                print(f"\nTask实例创建成功!")
                print(f"  task_id: {result['task_id']}")
                print(f"  task_name: {result['task_name']}")
                print(f"  actor: {result['actor']}")
                print(f"\n下一步执行 create action:")
                print(f"  python main.py --task-id {result['task_id']} --action create --action-params '{{\"query\": \"your search term\"}}'")
                return
            else:
                error = response.json()
                logger.error(f"创建失败: {error.get('detail', 'Unknown error')}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"创建失败: {e}")
            sys.exit(1)

    # 关闭task实例（直接调用 close-task 端点）
    if args.close_task:
        try:
            response = httpx.post(
                f"{server_url}/task/{args.close_task}/close-task",
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                print(f"\nTask实例已关闭!")
                print(f"  task_id: {result['task_id']}")

                # 显示保存统计
                if result.get('storage_stats'):
                    stats = result['storage_stats']
                    print(f"\n保存统计:")
                    print(f"  total: {stats.get('total', 0)}")
                    print(f"  added: {stats.get('added', 0)}")
                    print(f"  skipped: {stats.get('skipped', 0)}")
                    print(f"  errors: {stats.get('errors', 0)}")

                if result.get('saved_to'):
                    print(f"  保存到: {result['saved_to']}")

                return
            else:
                error = response.json()
                logger.error(f"关闭失败: {error.get('detail', 'Unknown error')}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"关闭失败: {e}")
            sys.exit(1)

    # 执行action
    if args.task_id and args.action:
        action_params = {}
        if args.action_params:
            try:
                action_params = json.loads(args.action_params)
            except json.JSONDecodeError as e:
                logger.error(f"无效的JSON参数: {e}")
                sys.exit(1)

        try:
            print(f"\n执行action: {args.action}")
            response = httpx.post(
                f"{server_url}/task/{args.task_id}/action/{args.action}",
                json={"params": action_params},
                timeout=60
            )
            if response.status_code == 200:
                result = response.json()
                print(f"执行成功")
                # 打印关键结果
                if 'url' in result:
                    print(f"  URL: {result['url']}")
                if 'title' in result:
                    print(f"  Title: {result['title']}")
                if 'status' in result:
                    print(f"  Status: {result['status']}")
                print(f"\n完整结果:")
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return
            else:
                error = response.json()
                logger.error(f"执行失败: {error.get('detail', 'Unknown error')}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"执行失败: {e}")
            sys.exit(1)

    # 参数不完整提示
    if args.task_id and not args.action:
        logger.error("参数不完整: 需要指定 --action")
        logger.info("用法: python main.py --task-id <id> --action <name> [--action-params <json>]")
        sys.exit(1)

    if args.action and not args.task_id:
        logger.error("参数不完整: 需要指定 --task-id")
        logger.info("用法: python main.py --task-id <id> --action <name> [--action-params <json>]")
        sys.exit(1)


def handle_storage_commands(args):
    """处理存储相关命令"""
    storage = TaskStorage()

    if args.stats is not None:
        if args.stats == "__all__":
            tasks = storage.list_all_tasks()
            if not tasks:
                print("No tasks found.")
            else:
                print(f"\nFound {len(tasks)} task(s):")
                for task_name in tasks:
                    stats = storage.get_task_stats(task_name)
                    print(f"\n[{task_name}]")
                    print(f"  Total: {stats['total']:,}")
        else:
            stats = storage.get_task_stats(args.stats)
            print(f"\nTask: {args.stats}")
            print(f"  Total: {stats['total']:,}")

        return True

    if args.query:
        results = storage.query_resources(args.query, limit=20)
        print(f"\nQuery results ({args.query}):")
        for r in results[:5]:
            print(f"  - {r.get('resource_url', 'N/A')}")
        return True


    return False


def main():
    args = parse_arguments()

    logger.info("="*50)
    logger.info("Info-Spider Actor Framework")
    logger.info("="*50)

    # Storage commands (不需要config)
    if handle_storage_commands(args):
        return

    # 加载配置
    config = load_and_validate_config(CONFIG_PATH)

    # 服务器命令（需要在加载插件前处理）
    if args.server:
        # 在创建服务器前加载 Actor（手动注册，避免同步 API 导入）
        actors = discover_actors()
        logger.info(f"已加载 {len(actors)} 个 Actors")
        handle_server_commands(args, config)
        return

    # Actor命令（需要服务器运行）
    if args.create_task or args.close_task or args.task_id or args.action or args.list_templates or args.list_instances or args.list_actors:
        handle_actor_commands(args)
        return

    # 默认提示
    logger.info("\n使用说明:")
    logger.info("  启动服务器:    python main.py --server start")
    logger.info("  查看任务模板:  python main.py --list-templates")
    logger.info("  查看任务实例:  python main.py --list-instances")
    logger.info("  API文档:       http://127.0.0.1:7666/docs")


if __name__ == "__main__":
    main()
