#!/usr/bin/env python3
"""
测试脚本 - 验证 NovelWriter 安装和基本功能
"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试所有模块能否正常导入"""
    print("测试模块导入...")
    
    try:
        from src.llm.base import BaseLLM, create_llm
        print("  ✓ src.llm.base")
    except Exception as e:
        print(f"  ✗ src.llm.base: {e}")
        return False
    
    try:
        from src.llm.qwen import QwenLLM
        print("  ✓ src.llm.qwen")
    except Exception as e:
        print(f"  ✗ src.llm.qwen: {e}")
        return False
    
    try:
        from src.llm.ollama import OllamaLLM
        print("  ✓ src.llm.ollama")
    except Exception as e:
        print(f"  ✗ src.llm.ollama: {e}")
        return False
    
    try:
        from src.data.schemas import ProjectState, WorkflowState
        print("  ✓ src.data.schemas")
    except Exception as e:
        print(f"  ✗ src.data.schemas: {e}")
        return False
    
    try:
        from src.data.state_manager import StateManager
        print("  ✓ src.data.state_manager")
    except Exception as e:
        print(f"  ✗ src.data.state_manager: {e}")
        return False
    
    try:
        from src.agents.base import BaseAgent
        print("  ✓ src.agents.base")
    except Exception as e:
        print(f"  ✗ src.agents.base: {e}")
        return False
    
    try:
        from src.agents.context_agent import ContextAgent
        print("  ✓ src.agents.context_agent")
    except Exception as e:
        print(f"  ✗ src.agents.context_agent: {e}")
        return False
    
    try:
        from src.agents.data_agent import DataAgent
        print("  ✓ src.agents.data_agent")
    except Exception as e:
        print(f"  ✗ src.agents.data_agent: {e}")
        return False
    
    try:
        from src.workflow.manager import WorkflowManager
        print("  ✓ src.workflow.manager")
    except Exception as e:
        print(f"  ✗ src.workflow.manager: {e}")
        return False
    
    try:
        from src.init.project import InitProject
        print("  ✓ src.init.project")
    except Exception as e:
        print(f"  ✗ src.init.project: {e}")
        return False
    
    try:
        from src.utils.config import load_config
        print("  ✓ src.utils.config")
    except Exception as e:
        print(f"  ✗ src.utils.config: {e}")
        return False
    
    return True


def test_config():
    """测试配置加载"""
    print("\n测试配置加载...")
    
    try:
        from src.utils.config import load_config
        config = load_config()
        print(f"  ✓ 配置加载成功，LLM 提供商: {config.get('llm', {}).get('provider', 'qwen')}")
        return True
    except Exception as e:
        print(f"  ✗ 配置加载失败: {e}")
        return False


def test_llm_creation():
    """测试 LLM 创建"""
    print("\n测试 LLM 创建...")
    
    try:
        from src.llm.base import create_llm
        
        # 测试创建 QwenLLM（需要有 API Key）
        config = {
            "provider": "qwen",
            "api_key": "test_key",  # 假 key，只测试创建逻辑
            "model": "qwen-max",
        }
        
        llm = create_llm(config)
        print(f"  ✓ QwenLLM 创建成功: {llm.model_name}")
        
        # 测试创建 OllamaLLM
        config = {
            "provider": "ollama",
            "model": "qwen2.5:72b",
        }
        
        llm = create_llm(config)
        print(f"  ✓ OllamaLLM 创建成功: {llm.model_name}")
        
        return True
    except Exception as e:
        print(f"  ✗ LLM 创建失败: {e}")
        return False


def main():
    print("=" * 60)
    print("NovelWriter 安装测试")
    print("=" * 60)
    
    all_passed = True
    
    # 测试导入
    if not test_imports():
        all_passed = False
    
    # 测试配置
    if not test_config():
        all_passed = False
    
    # 测试 LLM 创建
    if not test_llm_creation():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ 所有测试通过！NovelWriter 已正确安装。")
    else:
        print("✗ 部分测试失败，请检查错误信息。")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
