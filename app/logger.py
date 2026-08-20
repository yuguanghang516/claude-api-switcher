"""
日志模块
记录程序运行日志，但绝不记录 API Key
"""
import os
import logging
from datetime import datetime


class AppLogger:
    """应用程序日志管理器"""

    def __init__(self, logs_dir: str):
        self.logs_dir = logs_dir
        os.makedirs(logs_dir, exist_ok=True)

        # 创建日志文件名（按日期）
        log_file = os.path.join(
            logs_dir,
            f"switcher_{datetime.now().strftime('%Y%m%d')}.log"
        )

        # 配置日志
        self.logger = logging.getLogger("ClaudeAPISwitcher")
        self.logger.setLevel(logging.DEBUG)

        # 避免重复添加处理器
        if not self.logger.handlers:
            # 文件处理器
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)

            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            # 格式化
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def info(self, message: str):
        """记录信息日志"""
        self.logger.info(message)

    def error(self, message: str):
        """记录错误日志"""
        self.logger.error(message)

    def warning(self, message: str):
        """记录警告日志"""
        self.logger.warning(message)

    def debug(self, message: str):
        """记录调试日志"""
        self.logger.debug(message)

    def sanitize(self, text: str) -> str:
        """
        清理敏感信息，防止 API Key 被写入日志
        将可能的 Key 替换为掩码
        """
        if not text:
            return text
        # 替换常见的 API Key 格式
        import re
        # 匹配 sk- 开头的 key
        text = re.sub(r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]*(?=[a-zA-Z0-9]{4})',
                       r'\1****', text)
        # 匹配 ak_ 开头的 key
        text = re.sub(r'(ak_[a-zA-Z0-9]{4})[a-zA-Z0-9]*(?=[a-zA-Z0-9]{4})',
                       r'\1****', text)
        return text
