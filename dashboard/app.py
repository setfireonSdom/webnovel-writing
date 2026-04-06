"""
Dashboard FastAPI 应用
提供只读的 REST API 用于可视化项目状态
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NovelWriter Dashboard",
    description="网文写作系统可视化面板",
    version="1.0.0",
)

# CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局变量存储项目根目录
PROJECT_ROOT: Optional[Path] = None


def set_project_root(project_root: Path):
    """设置项目根目录"""
    global PROJECT_ROOT
    PROJECT_ROOT = project_root


def get_state() -> Dict[str, Any]:
    """获取项目状态"""
    state_file = PROJECT_ROOT / ".webnovel" / "state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="state.json 不存在")
    
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_workflow_state() -> Dict[str, Any]:
    """获取工作流状态"""
    state_file = PROJECT_ROOT / ".webnovel" / "workflow_state.json"
    if not state_file.exists():
        return {}
    
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_reading_power() -> Dict[str, Any]:
    """获取追读力数据"""
    rp_file = PROJECT_ROOT / ".webnovel" / "reading_power.json"
    if not rp_file.exists():
        return {"hooks": [], "cool_points": [], "debts": [], "micro_payoffs": []}
    
    with open(rp_file, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ API 端点 ============

@app.get("/api/project/info")
def get_project_info():
    """获取项目基本信息"""
    state = get_state()
    return {
        "title": state.get("project", {}).get("title", "未命名"),
        "genre": state.get("project", {}).get("genre", "未知"),
        "one_liner": state.get("project", {}).get("one_liner", ""),
        "target_scale": state.get("project", {}).get("target_scale", ""),
    }


@app.get("/api/project/state")
def get_project_state():
    """获取完整项目状态"""
    return get_state()


@app.get("/api/chapters")
def get_chapters():
    """获取章节列表"""
    content_dir = PROJECT_ROOT / "正文"
    if not content_dir.exists():
        return []
    
    chapters = []
    for file in sorted(content_dir.glob("ch*.md")):
        chapter_num = int(file.stem[2:])
        stat = file.stat()
        chapters.append({
            "chapter_num": chapter_num,
            "file_name": file.name,
            "file_size": stat.st_size,
            "modified_at": stat.st_mtime,
        })
    
    return chapters


@app.get("/api/chapter/{chapter_num}")
def get_chapter(chapter_num: int):
    """获取章节内容"""
    file = PROJECT_ROOT / "正文" / f"ch{chapter_num:04d}.md"
    if not file.exists():
        raise HTTPException(status_code=404, detail=f"章节 {chapter_num} 不存在")
    
    with open(file, "r", encoding="utf-8") as f:
        content = f.read()
    
    return {
        "chapter_num": chapter_num,
        "content": content,
        "word_count": len(content),
    }


@app.get("/api/entities")
def get_entities(entity_type: Optional[str] = None):
    """获取实体列表"""
    state = get_state()
    entities = state.get("entities", {}).get("all", [])
    
    if entity_type:
        entities = [e for e in entities if e.get("entity_type") == entity_type]
    
    return entities


@app.get("/api/characters")
def get_characters():
    """获取角色状态列表"""
    state = get_state()
    characters = state.get("character_states", [])
    return characters


@app.get("/api/reading_power")
def get_reading_power_stats():
    """获取追读力统计"""
    return get_reading_power()


@app.get("/api/workflow")
def get_workflow_status():
    """获取工作流状态"""
    return get_workflow_state()


@app.get("/api/summaries")
def get_chapter_summaries():
    """获取章节摘要列表"""
    summaries_dir = PROJECT_ROOT / ".webnovel" / "summaries"
    if not summaries_dir.exists():
        return []
    
    summaries = []
    for file in sorted(summaries_dir.glob("ch*.md")):
        chapter_num = int(file.stem[2:])
        with open(file, "r", encoding="utf-8") as f:
            content = f.read()
            # 提取摘要（跳过标题行）
            lines = content.split("\n")
            summary = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
        
        summaries.append({
            "chapter_num": chapter_num,
            "summary": summary,
        })
    
    return summaries


@app.get("/api/observability/performance")
def get_performance_data():
    """获取性能数据"""
    perf_file = PROJECT_ROOT / ".webnovel" / "observability" / "performance.jsonl"
    if not perf_file.exists():
        return []
    
    records = []
    with open(perf_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    return records


@app.get("/api/observability/llm-calls")
def get_llm_calls():
    """获取 LLM 调用记录"""
    llm_file = PROJECT_ROOT / ".webnovel" / "observability" / "llm_calls.jsonl"
    if not llm_file.exists():
        return []
    
    records = []
    with open(llm_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    
    return records


# ============ 前端 ============

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """提供 Dashboard 前端"""
    return HTMLResponse(content=DASHBOARD_HTML)


# 简化的 Dashboard HTML（内联）
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NovelWriter Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f5f7fa; color: #333; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px 0; margin-bottom: 30px; }
        header h1 { text-align: center; font-size: 2.5em; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .stat-card h3 { color: #667eea; margin-bottom: 10px; font-size: 1.2em; }
        .stat-card .value { font-size: 2.5em; font-weight: bold; color: #333; }
        .stat-card .label { color: #666; margin-top: 5px; }
        .section { background: white; border-radius: 12px; padding: 25px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .section h2 { color: #667eea; margin-bottom: 15px; border-bottom: 2px solid #667eea; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e0e0e0; }
        th { background: #f5f7fa; font-weight: 600; color: #667eea; }
        tr:hover { background: #f9f9f9; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; font-weight: 600; }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-info { background: #d1ecf1; color: #0c5460; }
        .loading { text-align: center; padding: 40px; color: #999; }
        .refresh-btn { position: fixed; bottom: 30px; right: 30px; background: #667eea; color: white; border: none; padding: 15px 30px; border-radius: 25px; cursor: pointer; font-size: 1em; box-shadow: 0 4px 12px rgba(102,126,234,0.4); }
        .refresh-btn:hover { background: #764ba2; }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>📖 NovelWriter Dashboard</h1>
        </div>
    </header>

    <div class="container">
        <!-- 统计卡片 -->
        <div class="stats-grid" id="stats-grid">
            <div class="loading">加载中...</div>
        </div>

        <!-- 章节列表 -->
        <div class="section">
            <h2>📚 章节列表</h2>
            <table id="chapters-table">
                <thead>
                    <tr>
                        <th>章节号</th>
                        <th>文件名</th>
                        <th>字数</th>
                        <th>修改时间</th>
                    </tr>
                </thead>
                <tbody id="chapters-body">
                    <tr><td colspan="4" class="loading">加载中...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- 角色状态 -->
        <div class="section">
            <h2>👥 角色状态</h2>
            <table id="characters-table">
                <thead>
                    <tr>
                        <th>角色名</th>
                        <th>境界</th>
                        <th>状态</th>
                        <th>备注</th>
                    </tr>
                </thead>
                <tbody id="characters-body">
                    <tr><td colspan="4" class="loading">加载中...</td></tr>
                </tbody>
            </table>
        </div>

        <!-- 追读力 -->
        <div class="section">
            <h2>📈 追读力</h2>
            <div id="reading-power" class="loading">加载中...</div>
        </div>
    </div>

    <button class="refresh-btn" onclick="loadAll()">🔄 刷新</button>

    <script>
        const API_BASE = window.location.origin;

        async function loadAll() {
            await Promise.all([
                loadStats(),
                loadChapters(),
                loadCharacters(),
                loadReadingPower(),
            ]);
        }

        async function loadStats() {
            try {
                const [info, chapters] = await Promise.all([
                    fetch(`${API_BASE}/api/project/info`).then(r => r.json()),
                    fetch(`${API_BASE}/api/chapters`).then(r => r.json()),
                ]);

                const stats = [
                    { label: '书名', value: info.title || '未命名' },
                    { label: '题材', value: info.genre || '未知' },
                    { label: '章节数', value: chapters.length },
                    { label: '总字数', value: chapters.reduce((sum, ch) => sum + (ch.file_size || 0), 0).toLocaleString() },
                ];

                document.getElementById('stats-grid').innerHTML = stats.map(stat => `
                    <div class="stat-card">
                        <h3>${stat.label}</h3>
                        <div class="value">${stat.value}</div>
                    </div>
                `).join('');
            } catch (error) {
                console.error('加载统计失败:', error);
            }
        }

        async function loadChapters() {
            try {
                const chapters = await fetch(`${API_BASE}/api/chapters`).then(r => r.json());

                if (chapters.length === 0) {
                    document.getElementById('chapters-body').innerHTML = '<tr><td colspan="4" class="loading">暂无章节</td></tr>';
                    return;
                }

                document.getElementById('chapters-body').innerHTML = chapters.map(ch => `
                    <tr>
                        <td><span class="badge badge-info">第 ${ch.chapter_num} 章</span></td>
                        <td>${ch.file_name}</td>
                        <td>${ch.file_size} 字节</td>
                        <td>${new Date(ch.modified_at * 1000).toLocaleString('zh-CN')}</td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('加载章节失败:', error);
            }
        }

        async function loadCharacters() {
            try {
                const characters = await fetch(`${API_BASE}/api/characters`).then(r => r.json());

                if (characters.length === 0) {
                    document.getElementById('characters-body').innerHTML = '<tr><td colspan="4" class="loading">暂无角色</td></tr>';
                    return;
                }

                document.getElementById('characters-body').innerHTML = characters.map(ch => `
                    <tr>
                        <td><strong>${ch.name}</strong></td>
                        <td>${ch.cultivation || '未知'}</td>
                        <td><span class="badge badge-success">${ch.status || 'unknown'}</span></td>
                        <td>${ch.notes || '-'}</td>
                    </tr>
                `).join('');
            } catch (error) {
                console.error('加载角色失败:', error);
            }
        }

        async function loadReadingPower() {
            try {
                const rp = await fetch(`${API_BASE}/api/reading_power`).then(r => r.json());

                const html = `
                    <div class="stats-grid">
                        <div class="stat-card">
                            <h3>钩子数</h3>
                            <div class="value">${rp.hooks?.length || 0}</div>
                        </div>
                        <div class="stat-card">
                            <h3>爽点数</h3>
                            <div class="value">${rp.cool_points?.length || 0}</div>
                        </div>
                        <div class="stat-card">
                            <h3>活跃债务</h3>
                            <div class="value">${rp.debts?.filter(d => !d.is_paid).length || 0}</div>
                        </div>
                        <div class="stat-card">
                            <h3>微兑现</h3>
                            <div class="value">${rp.micro_payoffs?.length || 0}</div>
                        </div>
                    </div>
                `;

                document.getElementById('reading-power').innerHTML = html;
            } catch (error) {
                console.error('加载追读力失败:', error);
                document.getElementById('reading-power').innerHTML = '<div class="loading">加载失败</div>';
            }
        }

        // 初始加载
        loadAll();

        // 每 30 秒自动刷新
        setInterval(loadAll, 30000);
    </script>
</body>
</html>
"""
