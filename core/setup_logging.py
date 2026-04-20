import logging
import sys
import os  # <-- 导入 os
from logging.config import dictConfig
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler  # <-- 导入轮转处理器
from typing import Dict, Any
# 定义日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging(log_dir: str = "logs", level=logging.INFO):
    """
配置全局（根）日志记录器。
    只需在程序启动时调用一次。
    """
    # 1. 确保日志目录存在
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 获取根 Logger (名称为空字符串)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 如果已经有处理器（防止重复初始化导致日志打印两次），先清空
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 3. 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # ------------------------------------------------
    # A. 控制台处理器 (使用 UTF-8 编码)
    # ------------------------------------------------
    import io
    # 创建一个使用 UTF-8 编码的文本包装器
    utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ------------------------------------------------
    # B. 文件处理器 (按大小轮转，Windows 兼容性更好)
    # ------------------------------------------------
    log_file_path = os.path.join(log_dir, "app.log")
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 这里的 root_logger 不需要返回，因为它是全局单例的
    # 使用 logger 而不是 print 避免编码问题
    logger = logging.getLogger(__name__)
    logger.info("日志系统已初始化，输出目录: {}".format(log_dir))