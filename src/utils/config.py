"""
配置加载和管理
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv, find_dotenv

logger = logging.getLogger(__name__)


def _load_env_file():
    """
    自动查找并加载 .env 文件
    支持项目根目录和当前目录下的 .env
    """
    # 先尝试从当前工作目录加载
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=True)
        logger.debug(f"已加载 .env 文件: {dotenv_path}")
        return
    
    # 再尝试从脚本所在目录加载
    script_dir = Path(__file__).resolve().parent.parent.parent
    dotenv_path = script_dir / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=True)
        logger.debug(f"已加载 .env 文件: {dotenv_path}")
        return
    
    # 最后尝试从当前工作目录加载
    dotenv_path = Path.cwd() / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=True)
        logger.debug(f"已加载 .env 文件: {dotenv_path}")
        return
    
    logger.warning("未找到 .env 文件，将使用环境变量或默认配置")


# 初始加载一次 .env 文件
_load_env_file()


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """加载配置文件"""
    if config_path is None:
        config_path = Path("config.yaml")
    
    config = {}
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    
    # 从环境变量覆盖配置
    config = _load_env_overrides(config)
    
    return config


def _load_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """从环境变量覆盖配置"""
    # LLM 配置
    llm_provider = os.getenv("NOVEL_LLM_PROVIDER")
    if llm_provider:
        config.setdefault("llm", {})
        config["llm"]["provider"] = llm_provider
    
    # 直接从 .env 读取 API Key（即使没有 config.yaml 也能工作）
    qwenv_api_key = os.getenv("QWEN_API_KEY")
    if qwenv_api_key and qwenv_api_key != "your_api_key_here":
        config.setdefault("llm", {})
        config["llm"]["api_key"] = qwenv_api_key
    
    qwenv_model = os.getenv("QWEN_MODEL")
    if qwenv_model and qwenv_model != "qwen-max":
        config.setdefault("llm", {})
        config["llm"]["model"] = qwenv_model
    
    # 如果是 openai 兼容模式，自动使用百炼平台端点
    if llm_provider == "openai":
        config.setdefault("llm", {})
        config["llm"].setdefault("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        if not config["llm"].get("model"):
            config["llm"]["model"] = "glm-5"

    llm_temp = os.getenv("NOVEL_LLM_TEMPERATURE")
    if llm_temp:
        config.setdefault("llm", {})
        config["llm"]["temperature"] = float(llm_temp)

    llm_max_tokens = os.getenv("NOVEL_LLM_MAX_TOKENS")
    if llm_max_tokens:
        config.setdefault("llm", {})
        config["llm"]["max_tokens"] = int(llm_max_tokens)

    # 工作流配置
    workflow_mode = os.getenv("NOVEL_WORKFLOW_MODE")
    if workflow_mode:
        config.setdefault("workflow", {})
        config["workflow"]["default_mode"] = workflow_mode

    review_depth = os.getenv("NOVEL_REVIEW_DEPTH")
    if review_depth:
        config.setdefault("workflow", {})
        config["workflow"]["review_depth"] = review_depth

    # 替换配置中的环境变量引用
    config = _resolve_env_variables(config)

    return config


def _resolve_env_variables(config: Any) -> Any:
    """解析配置中的环境变量引用 ${VAR_NAME}"""
    if isinstance(config, dict):
        return {k: _resolve_env_variables(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [_resolve_env_variables(item) for item in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        var_name = config[2:-1]
        return os.getenv(var_name, config)
    else:
        return config


def resolve_project_root(override: Optional[Path] = None) -> Path:
    """解析项目根目录（包含 .webnovel/state.json 的目录）"""
    if override is not None:
        return _find_project_root_from(override)
    return _find_project_root_from(Path.cwd())


def _find_project_root_from(start_path: Path) -> Path:
    """从指定路径开始向上查找包含 .webnovel/state.json 的目录"""
    current = start_path.resolve()
    
    for _ in range(20):  # 最多向上查找 20 层
        webnovel_dir = current / ".webnovel"
        if webnovel_dir.exists() and (webnovel_dir / "state.json").exists():
            return current
        
        if current.parent == current:
            break
        current = current.parent
    
    raise FileNotFoundError(
        "未找到项目根目录。请确保当前目录或父目录包含 .webnovel/state.json"
    )
