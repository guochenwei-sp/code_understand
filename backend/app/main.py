from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from typing import Optional, List
import sys
import os
import networkx as nx

# Add current directory to sys.path to ensure modules can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.indexer import Indexer
from app.core.git_helper import GitHelper
from app.core.arch_analyzer import ArchitectureAnalyzer
from app.db.database import SessionLocal, engine, Base, init_fts5
from app.db.models import Symbol, Reference, FileRecord, RefType, Project, Include, ScanStatus, ModuleDefinition, ArchitectureRule

app = FastAPI(title="C Code Analysis Tool Backend", version="0.3.0")

# Ensure tables are created on startup
@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    init_fts5()  # 初始化 FTS5 全文搜索

# Configure CORS to allow requests from the Electron frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specific origins should be used
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectCreate(BaseModel):
    name: str
    root_path: str

def scan_project_task(project_id: int, root_path: str):
    """Background task for scanning a project."""
    db = SessionLocal()
    try:
        indexer = Indexer(db)
        indexer.scan_project(project_id, root_path)
    except Exception as e:
        print(f"Error scanning project {project_id}: {e}")
    finally:
        db.close()

@app.post("/projects/")
def create_project(project: ProjectCreate):
    db = SessionLocal()
    try:
        if not os.path.exists(project.root_path):
            raise HTTPException(status_code=400, detail="Path does not exist")
            
        db_project = Project(name=project.name, root_path=os.path.abspath(project.root_path))
        db.add(db_project)
        db.commit()
        db.refresh(db_project)
        return db_project
    finally:
        db.close()

@app.get("/projects/")
def list_projects():
    db = SessionLocal()
    try:
        projects = db.query(Project).all()
        return projects
    finally:
        db.close()

@app.post("/projects/{project_id}/scan")
def scan_project_endpoint(project_id: int, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Add scan task to background
        background_tasks.add_task(scan_project_task, project.id, project.root_path)
        
        return {"status": "accepted", "message": f"Scanning started for project {project.name}"}
    finally:
        db.close()

@app.get("/projects/{project_id}/files")
def list_project_files(project_id: int):
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # 使用路径前缀匹配而不是 project_id
        # 这样支持子项目视图，而不需要重复存储文件
        root_path = project.root_path
        
        files = db.query(FileRecord).filter(
            (FileRecord.path == root_path) | 
            (FileRecord.path.like(f"{root_path}{os.sep}%"))
        ).all()
        
        return [{"id": f.id, "path": f.path, "last_modified": f.last_modified} for f in files]
    finally:
        db.close()

@app.get("/files/{file_id}/content")
def get_file_content(file_id: int):
    db = SessionLocal()
    try:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        if not os.path.exists(file_record.path):
             raise HTTPException(status_code=404, detail="File on disk not found")

        try:
            with open(file_record.path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return {"content": content}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")
    finally:
        db.close()

@app.get("/files/{file_id}/symbols")
def get_file_symbols(file_id: int):
    """获取文件中的所有符号列表"""
    db = SessionLocal()
    try:
        symbols = db.query(Symbol).filter(Symbol.file_id == file_id).all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "line": s.line,
                "signature": s.signature,
                "complexity": s.cyclomatic_complexity
            }
            for s in symbols
        ]
    finally:
        db.close()

@app.get("/search")
def search_symbols(q: str, project_id: int, limit: int = 50):
    """使用 FTS5 全文搜索符号"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
             return []
        
        root_path = project.root_path
        
        # 使用 FTS5 进行全文搜索
        # FTS5 语法：MATCH 'search terms'
        # 支持前缀匹配：'term*'
        search_term = f"{q}*"  # 前缀匹配

        query = text("""
            SELECT s.id, s.name, s.kind, s.file_id, s.line, s.signature, s.cyclomatic_complexity, f.path
            FROM symbols s
            JOIN symbols_fts fts ON s.id = fts.rowid
            JOIN files f ON s.file_id = f.id
            WHERE (f.path = :root_path OR f.path LIKE :root_path_pattern)
              AND symbols_fts MATCH :search_term
            LIMIT :limit
        """)

        result = db.execute(query, {
            'root_path': root_path,
            'root_path_pattern': f"{root_path}{os.sep}%",
            'search_term': search_term,
            'limit': limit
        })

        return [
            {
                "id": row[0],
                "name": row[1],
                "kind": row[2],
                "file_id": row[3],
                "line": row[4],
                "signature": row[5],
                "complexity": row[6],
                "file_path": row[7]
            }
            for row in result
        ]
    except Exception as e:
        # 降级到 LIKE 搜索
        print(f"FTS5 search failed, falling back to LIKE: {e}")
        results = db.query(Symbol, FileRecord.path).join(FileRecord, Symbol.file_id == FileRecord.id)\
            .filter((FileRecord.path == root_path) | (FileRecord.path.like(f"{root_path}{os.sep}%")))\
            .filter(Symbol.name.ilike(f"%{q}%"))\
            .limit(limit)\
            .all()

        return [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "file_id": s.file_id,
                "file_path": path,
                "line": s.line,
                "signature": s.signature,
                "complexity": s.cyclomatic_complexity
            }
            for s, path in results
        ]
    finally:
        db.close()

@app.get("/files/{file_id}/analyze")
def analyze_file(file_id: int):
    db = SessionLocal()
    try:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")
        
        findings = []
        if os.path.exists(file_record.path):
            import subprocess
            import xml.etree.ElementTree as ET
            
            try:
                # Run cppcheck
                # Note: This requires cppcheck to be installed and in the system PATH
                cmd = ["cppcheck", "--enable=all", "--xml", "--xml-version=2", file_record.path]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                
                if result.stderr:
                    try:
                        root = ET.fromstring(result.stderr)
                        for error in root.findall("./errors/error"):
                            # Filter out 'information' severity if desired, or keep all
                            severity = error.get("severity", "info")
                            msg = error.get("msg", "Unknown issue")
                            line_elem = error.find("location")
                            line = int(line_elem.get("line")) if line_elem is not None else 0
                            
                            findings.append({
                                "line": line,
                                "message": msg,
                                "severity": severity
                            })
                    except ET.ParseError:
                         print("Failed to parse cppcheck XML output")
                
                if result.returncode != 0 and not findings:
                     print(f"Cppcheck failed: {result.stderr}")

            except FileNotFoundError:
                 findings.append({
                     "line": 1,
                     "message": "Error: 'cppcheck' tool not found. Please install Cppcheck and ensure it is in your system PATH.",
                     "severity": "error"
                 })
            except Exception as e:
                 print(f"Analysis execution failed: {e}")
                 findings.append({
                     "line": 1,
                     "message": f"Analysis failed: {str(e)}",
                     "severity": "error"
                 })

        return findings
    except Exception as e:
        print(f"Analysis failed: {e}")
        return []
    finally:
        db.close()

@app.get("/projects/{project_id}/dsm")
def get_project_dsm(project_id: int):
    """
    获取项目的依赖结构矩阵 (DSM)
    基于 #include 关系而非函数调用
    """
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return {"files": [], "matrix": []}
            
        root_path = project.root_path

        # 1. Get all files in project
        files = db.query(FileRecord).filter(
            (FileRecord.path == root_path) | 
            (FileRecord.path.like(f"{root_path}{os.sep}%"))
        ).all()

        # Build Dependency Graph based on #include relationships
        G = nx.DiGraph()
        for f in files:
            G.add_node(f.id)

        file_ids = [f.id for f in files]

        # 获取 include 关系
        includes = db.query(Include)\
            .filter(Include.source_file_id.in_(file_ids))\
            .filter(Include.target_file_id.in_(file_ids))\
            .all()

        # Add edges to graph (source includes target)
        for inc in includes:
            if inc.source_file_id != inc.target_file_id:
                G.add_edge(inc.source_file_id, inc.target_file_id)

        # Levelization (Topological Sort with Cycle Handling)
        sorted_ids = []
        try:
            sorted_ids = list(nx.topological_sort(G))
        except nx.NetworkXUnfeasible:
            # Cycles detected, use SCC condensation
            scc_graph = nx.condensation(G)
            try:
                scc_order = list(nx.topological_sort(scc_graph))
            except nx.NetworkXUnfeasible:
                # Should not happen for condensation graph, but safety first
                scc_order = list(scc_graph.nodes())

            # Flatten: condensation node -> list of original nodes
            for scc_idx in scc_order:
                sorted_ids.extend(scc_graph.nodes[scc_idx]['members'])

        # Reorder files list
        file_map_obj = {f.id: f for f in files}
        ordered_files = [file_map_obj[fid] for fid in sorted_ids if fid in file_map_obj]

        # Append any isolated files not in sorted_ids (safety)
        seen_ids = set(sorted_ids)
        for f in files:
            if f.id not in seen_ids:
                ordered_files.append(f)

        # Rebuild Matrix based on include relationships
        n = len(ordered_files)
        file_index_map = {f.id: i for i, f in enumerate(ordered_files)}
        matrix = [[0] * n for _ in range(n)]

        for inc in includes:
            src_idx = file_index_map.get(inc.source_file_id)
            tgt_idx = file_index_map.get(inc.target_file_id)

            if src_idx is not None and tgt_idx is not None:
                matrix[src_idx][tgt_idx] += 1

        # Format response
        file_list = [{"id": f.id, "name": os.path.basename(f.path), "path": f.path} for f in ordered_files]

        return {
            "files": file_list,
            "matrix": matrix
        }
    finally:
        db.close()

@app.get("/symbols/{symbol_id}/references")
def get_symbol_references(symbol_id: int, ref_type: str = "all"):
    db = SessionLocal()
    try:
        symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
        if not symbol:
            raise HTTPException(status_code=404, detail="Symbol not found")
            
        results = []
        
        # 1. Usages / Callers (Who references/calls ME?)
        # Target = ME. Source = THE REFERENCER.
        # We need the FileRecord of the REFERENCE (Reference.file_id)
        if ref_type in ["all", "usages", "callers"]:
            # Query: Reference + Source Symbol + File where ref occurred
            q = db.query(Reference, Symbol, FileRecord)\
                  .join(Symbol, Reference.source_id == Symbol.id)\
                  .join(FileRecord, Reference.file_id == FileRecord.id)\
                  .filter(Reference.target_id == symbol_id)
            
            if ref_type == "callers":
                q = q.filter(Reference.kind == "call")
                
            refs = q.all()
            
            for r, source_sym, file_rec in refs:
                results.append({
                    "id": r.id,
                    "file_id": r.file_id,
                    "file_path": file_rec.path,
                    "line": r.line,
                    "column": r.column,
                    "kind": r.kind,
                    "symbol_name": source_sym.name,
                    "symbol_kind": source_sym.kind
                })

        # 2. Callees (Who do I call?)
        # Source = ME. Target = THE CALLEE.
        # File is still Reference.file_id (usually same as ME's file, but good to be explicit)
        if ref_type in ["all", "callees"]:
            q = db.query(Reference, Symbol, FileRecord)\
                  .join(Symbol, Reference.target_id == Symbol.id)\
                  .join(FileRecord, Reference.file_id == FileRecord.id)\
                  .filter(Reference.source_id == symbol_id)
                  
            refs = q.all()
            
            for r, target_sym, file_rec in refs:
                results.append({
                    "id": r.id,
                    "file_id": r.file_id,
                    "file_path": file_rec.path,
                    "line": r.line,
                    "column": r.column,
                    "kind": r.kind,
                    "symbol_name": target_sym.name,
                    "symbol_kind": target_sym.kind
                })
                
        return results
    finally:
        db.close()

@app.get("/graph/file")
def get_file_graph(file_id: int = Query(..., description="The ID of the file to retrieve graph for"),
                   kind: str = Query(None, description="Filter nodes by kind (e.g., 'function')")):
    db = SessionLocal()
    try:
        # 1. 查找该文件定义的所有符号 (Nodes)
        query = db.query(Symbol).filter(Symbol.file_id == file_id)
        if kind:
            query = query.filter(Symbol.kind == kind)
        symbols = query.all()
        
        nodes = []
        symbol_ids = set()
        for s in symbols:
            symbol_ids.add(s.id)
            nodes.append({
                "data": {
                    "id": str(s.id),
                    "label": s.name,
                    "kind": s.kind,
                    "line": s.line,
                    "column": s.column,
                    "color": "#40a9ff" if s.kind == "function" else "#ffc069" # 简单配色: 函数蓝，变量橙
                }
            })
            
        # 2. 查找这些符号之间的引用关系 (Edges)
        # 仅当 source 和 target 都存在于 filtered nodes 中时才显示边 (如果是严格过滤模式)
        # 或者显示边但 target 是灰色 (如果不需要严格过滤)
        # 这里为了图表清晰，我们只显示两端都在过滤范围内的边
        
        refs = db.query(Reference).filter(Reference.file_id == file_id).all()
        
        edges = []
        for r in refs:
            source_exists = str(r.source_id) in [n["data"]["id"] for n in nodes]
            target_exists = str(r.target_id) in [n["data"]["id"] for n in nodes]
            
            # 颜色映射
            edge_color = "#bbb"
            if r.kind == "write":
                 edge_color = "#ff4d4f" # Red
            elif r.kind == "read":
                 edge_color = "#52c41a" # Green
            elif r.kind == "call":
                 edge_color = "#1890ff" # Blue

            # 如果指定了 kind (比如 function)，我们只关心函数间的调用
            if kind and (not source_exists or not target_exists):
                continue

            # 如果没有指定 kind，我们显示所有，包括外部引用
            if not kind and not target_exists:
                 # 这是一个外部引用 (External Symbol) - 只有在全量模式下才补充显示
                target_sym = db.query(Symbol).filter(Symbol.id == r.target_id).first()
                if target_sym:
                    nodes.append({
                        "data": {
                            "id": str(target_sym.id),
                            "label": target_sym.name + " (Ext)",
                            "kind": target_sym.kind,
                            "line": target_sym.line,
                            "color": "#d9d9d9" # 灰色表示外部
                        }
                    })
                    edges.append({
                        "data": {
                            "source": str(r.source_id),
                            "target": str(r.target_id),
                            "label": r.kind,
                            "line": r.line,
                            "color": edge_color
                        }
                    })
            elif source_exists and target_exists:
                edges.append({
                    "data": {
                        "source": str(r.source_id),
                        "target": str(r.target_id),
                        "label": r.kind,
                        "line": r.line,
                        "color": edge_color
                    }
                })

        return {"elements": {"nodes": nodes, "edges": edges}}
        
    finally:
        db.close()

# ==================== 符号详情 API ====================
@app.get("/symbols/{symbol_id}/details")
def get_symbol_details(symbol_id: int):
    """获取符号的详细信息"""
    db = SessionLocal()
    try:
        symbol = db.query(Symbol).filter(Symbol.id == symbol_id).first()
        if not symbol:
            raise HTTPException(status_code=404, detail="Symbol not found")

        file = db.query(FileRecord).filter(FileRecord.id == symbol.file_id).first()

        # 统计引用数量
        callers_count = db.query(Reference).filter(Reference.target_id == symbol_id).count()
        callees_count = db.query(Reference).filter(Reference.source_id == symbol_id).count()

        return {
            "id": symbol.id,
            "name": symbol.name,
            "kind": symbol.kind,
            "signature": symbol.signature,
            "file_id": symbol.file_id,
            "file_path": file.path if file else None,
            "line": symbol.line,
            "column": symbol.column,
            "end_line": symbol.end_line,
            "cyclomatic_complexity": symbol.cyclomatic_complexity,
            "is_static": symbol.is_static,
            "is_extern": symbol.is_extern,
            "is_definition": symbol.is_definition,
            "callers_count": callers_count,
            "callees_count": callees_count
        }
    finally:
        db.close()

# ==================== 扫描进度 API ====================
@app.get("/projects/{project_id}/scan_status")
def get_scan_status(project_id: int):
    """获取项目扫描状态"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return {
            "status": project.scan_status,
            "progress": project.scan_progress,
            "message": project.scan_message
        }
    finally:
        db.close()

# ==================== Git 相关 API ====================
@app.get("/projects/{project_id}/git/commits")
def get_git_commits(project_id: int, file_path: Optional[str] = None, max_count: int = 50):
    """获取 Git 提交历史"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        git_helper = GitHelper(project.root_path)
        if not git_helper.is_git_repo():
            raise HTTPException(status_code=400, detail="Not a Git repository")

        commits = git_helper.get_commits(max_count=max_count, file_path=file_path)
        return {"commits": commits}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()

@app.get("/projects/{project_id}/git/diff")
def get_git_diff(project_id: int, commit_hash: Optional[str] = None, file_path: Optional[str] = None):
    """获取 Git diff"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        git_helper = GitHelper(project.root_path)
        diff_content = git_helper.get_diff(commit_hash=commit_hash, file_path=file_path)
        return {"diff": diff_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/projects/{project_id}/git/changed_files")
def get_changed_files(project_id: int, commit_hash: Optional[str] = None):
    """获取变更文件列表"""
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        git_helper = GitHelper(project.root_path)
        changed_files = git_helper.get_changed_files(commit_hash=commit_hash)

        # 映射到项目文件
        for cf in changed_files:
            full_path = os.path.join(project.root_path, cf['path'])
            file_record = db.query(FileRecord).filter(FileRecord.path == os.path.abspath(full_path)).first()
            cf['file_id'] = file_record.id if file_record else None

        return {"changed_files": changed_files}
    finally:
        db.close()

@app.get("/files/{file_id}/git/blame")
def get_file_blame(file_id: int):
    """获取文件的 Git blame 信息"""
    db = SessionLocal()
    try:
        file_record = db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        project = db.query(Project).filter(Project.id == file_record.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        git_helper = GitHelper(project.root_path)
        rel_path = os.path.relpath(file_record.path, project.root_path)
        blame_info = git_helper.get_blame(rel_path)

        return {"blame": blame_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

# ==================== 架构分析 API ====================
@app.get("/projects/{project_id}/architecture/circular_dependencies")
def get_circular_dependencies(project_id: int):
    """检测循环依赖"""
    db = SessionLocal()
    try:
        analyzer = ArchitectureAnalyzer(db, project_id)
        circular_deps = analyzer.detect_circular_dependencies()

        # 获取文件信息
        result = []
        for cycle in circular_deps:
            files = db.query(FileRecord).filter(FileRecord.id.in_(cycle)).all()
            result.append({
                "file_ids": cycle,
                "files": [{"id": f.id, "path": f.path} for f in files]
            })

        return {"circular_dependencies": result}
    finally:
        db.close()

@app.get("/projects/{project_id}/architecture/levelization")
def get_levelization(project_id: int):
    """获取文件分层信息"""
    db = SessionLocal()
    try:
        analyzer = ArchitectureAnalyzer(db, project_id)
        layers = analyzer.compute_levelization()

        # 按层级组织文件
        files_by_layer = {}
        for file_id, layer in layers.items():
            if layer not in files_by_layer:
                files_by_layer[layer] = []
            file = db.query(FileRecord).filter(FileRecord.id == file_id).first()
            if file:
                files_by_layer[layer].append({
                    "id": file.id,
                    "path": file.path,
                    "name": os.path.basename(file.path)
                })

        return {"layers": files_by_layer, "max_layer": max(layers.values()) if layers else 0}
    finally:
        db.close()

@app.get("/projects/{project_id}/architecture/hotspots")
def get_hotspot_files(project_id: int, top_n: int = 10):
    """获取热点文件（高复杂度）"""
    db = SessionLocal()
    try:
        analyzer = ArchitectureAnalyzer(db, project_id)
        hotspots = analyzer.get_hotspot_files(top_n=top_n)
        return {"hotspots": hotspots}
    finally:
        db.close()

@app.get("/projects/{project_id}/architecture/module_dsm")
def get_module_dsm(project_id: int):
    """获取模块级别的依赖矩阵"""
    db = SessionLocal()
    try:
        analyzer = ArchitectureAnalyzer(db, project_id)
        result = analyzer.get_module_dependency_matrix()
        return result
    finally:
        db.close()

@app.get("/projects/{project_id}/architecture/structure_graph")
def get_structure_graph(project_id: int):
    """获取项目结构图"""
    db = SessionLocal()
    try:
        analyzer = ArchitectureAnalyzer(db, project_id)
        result = analyzer.get_structure_graph()
        return {"elements": result}
    finally:
        db.close()

# ==================== 跨文件关系图 API ====================
@app.get("/graph/cross_file")
def get_cross_file_graph(
    project_id: int,
    symbol_id: Optional[int] = None,
    depth: int = 2,
    kind: Optional[str] = None
):
    """
    获取跨文件关系图
    可以从特定符号开始展开，或显示全局视图
    """
    db = SessionLocal()
    try:
        nodes = []
        edges = []
        visited_symbols = set()

        def add_symbol_and_relations(sym_id, current_depth):
            if current_depth > depth or sym_id in visited_symbols:
                return
            visited_symbols.add(sym_id)

            symbol = db.query(Symbol).filter(Symbol.id == sym_id).first()
            if not symbol:
                return

            # 添加节点
            file = db.query(FileRecord).filter(FileRecord.id == symbol.file_id).first()
            nodes.append({
                "data": {
                    "id": str(symbol.id),
                    "label": symbol.name,
                    "kind": symbol.kind,
                    "file": os.path.basename(file.path) if file else "unknown",
                    "complexity": symbol.cyclomatic_complexity,
                    "color": "#40a9ff" if symbol.kind == "function" else "#ffc069"
                }
            })

            # 添加外出引用
            refs = db.query(Reference, Symbol).join(Symbol, Reference.target_id == Symbol.id)\
                .filter(Reference.source_id == sym_id)\
                .all()

            for ref, target_sym in refs:
                # 包含所有引用（无论是跨文件还是文件内）
                if True:
                    edges.append({
                        "data": {
                            "source": str(sym_id),
                            "target": str(target_sym.id),
                            "label": ref.kind,
                            "color": "#1890ff" if ref.kind == "call" else "#52c41a"
                        }
                    })
                    add_symbol_and_relations(target_sym.id, current_depth + 1)

        if symbol_id:
            add_symbol_and_relations(symbol_id, 0)
        else:
            # 全局视图：显示跨文件的主要调用关系
            # 限制数量避免过大
            symbols = db.query(Symbol).join(FileRecord)\
                .filter(FileRecord.project_id == project_id)\
                .limit(100)\
                .all()

            for symbol in symbols:
                add_symbol_and_relations(symbol.id, 0)

        return {"elements": {"nodes": nodes, "edges": edges}}

    finally:
        db.close()

@app.get("/")
def read_root():
    return {"status": "online", "message": "C Code Analysis Backend is running", "version": "0.3.0"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
