"""
SynonymManager - 同义词词典管理器

职责：
- 加载并管理所有同义词词典（从 JSON 文件）
- 提供查询接口
- 支持热重载（用于开发环境）
"""

import json
from pathlib import Path
from typing import Dict, Set

from app.utils.logger import get_logger

logger = get_logger(__name__)

# 数据目录
MATCHER_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "matcher"


class SynonymManager:
    """同义词词典管理器"""

    def __init__(self, data_dir: Path = MATCHER_DATA_DIR):
        """
        初始化 SynonymManager

        Args:
            data_dir: 数据文件目录
        """
        self.data_dir = data_dir
        self.pet_synonyms: Dict[str, str] = {}
        self.en_variations: Dict[str, str] = {}
        self.semantic_norm: Dict[str, str] = {}
        self.stop_words_en: Set[str] = set()
        self.stop_words_zh: Set[str] = set()

        self._load_all()

    def _load_json(self, filename: str) -> dict | list:
        """
        加载 JSON 文件

        Args:
            filename: 文件名

        Returns:
            解析后的 JSON 数据
        """
        file_path = self.data_dir / filename
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"词典文件不存在：{file_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"词典 JSON 解析失败：{e}")
            return {}

    def _load_all(self):
        """加载所有词典"""
        logger.info(f"从 {self.data_dir} 加载词典...")

        # 加载同义词映射
        self.pet_synonyms = self._load_json("pet_synonyms.json")
        logger.debug(f"加载 pet_synonyms: {len(self.pet_synonyms)} 条")

        # 加载词形变化
        self.en_variations = self._load_json("en_variations.json")
        logger.debug(f"加载 en_variations: {len(self.en_variations)} 条")

        # 加载语义归一化
        self.semantic_norm = self._load_json("semantic_norm.json")
        logger.debug(f"加载 semantic_norm: {len(self.semantic_norm)} 条")

        # 加载停用词
        stop_words_en_list = self._load_json("stop_words_en.json")
        self.stop_words_en = (
            set(stop_words_en_list) if isinstance(stop_words_en_list, list) else set()
        )
        logger.debug(f"加载 stop_words_en: {len(self.stop_words_en)} 条")

        stop_words_zh_list = self._load_json("stop_words_zh.json")
        self.stop_words_zh = (
            set(stop_words_zh_list) if isinstance(stop_words_zh_list, list) else set()
        )
        logger.debug(f"加载 stop_words_zh: {len(self.stop_words_zh)} 条")

        logger.info(
            f"词典加载完成: {len(self.pet_synonyms)} 同义词, "
            f"{len(self.en_variations)} 词形变化, "
            f"{len(self.semantic_norm)} 归一化映射"
        )

    def reload(self):
        """热重载所有词典（用于开发环境）"""
        logger.info("热重载词典...")
        self._load_all()

    def get_synonyms(self, word: str) -> str:
        """
        获取单词的同义词

        Args:
            word: 英文单词

        Returns:
            同义词字符串（空格分隔），如果没有找到则返回原词
        """
        return self.pet_synonyms.get(word.lower(), word)

    def get_base_form(self, word: str) -> str:
        """
        获取单词的基本形式（词形还原）

        Args:
            word: 英文单词

        Returns:
            基本形式
        """
        return self.en_variations.get(word.lower(), word)

    def normalize(self, word: str) -> str:
        """
        语义归一化（将同义词映射到规范词）

        Args:
            word: 单词（中英文）

        Returns:
            规范词
        """
        return self.semantic_norm.get(word, word)

    def is_stop_word(self, word: str, language: str = "en") -> bool:
        """
        检查是否为停用词

        Args:
            word: 单词
            language: 语言代码（"en" 或 "zh"）

        Returns:
            是否为停用词
        """
        if language == "en":
            return word.lower() in self.stop_words_en
        elif language == "zh":
            return word in self.stop_words_zh
        return False
