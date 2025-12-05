"""
架构分析模块
提供分层分析、架构违规检测等功能
"""
import os
import fnmatch
from typing import List, Dict, Set, Tuple
from sqlalchemy.orm import Session
import networkx as nx
from ..db.models import Project, FileRecord, Symbol, Reference, ModuleDefinition, ArchitectureRule, Include

class ArchitectureAnalyzer:
    """架构分析器"""

    def __init__(self, db: Session, project_id: int):
        self.db = db
        self.project_id = project_id
        self.project = db.query(Project).filter(Project.id == project_id).first()
        self.root_path = self.project.root_path if self.project else ""

    def _get_project_files(self):
        """Helper to get files belonging to this project (including nested)"""
        if not self.root_path:
            return []
        
        return self.db.query(FileRecord).filter(
            (FileRecord.path == self.root_path) | 
            (FileRecord.path.like(f"{self.root_path}{os.sep}%"))
        ).all()

    def auto_detect_modules(self) -> List[ModuleDefinition]:
        """
        自动检测模块结构（基于目录结构）
        """
        files = self._get_project_files()
        if not files or not self.project:
            return []

        root_path = self.project.root_path

        # 收集所有一级和二级目录
        dir_structure = {}
        for file in files:
            rel_path = os.path.relpath(file.path, root_path)
            parts = rel_path.split(os.sep)

            if len(parts) > 1:
                top_dir = parts[0]
                if top_dir not in dir_structure:
                    dir_structure[top_dir] = set()
                if len(parts) > 2:
                    dir_structure[top_dir].add(parts[1])

        # 创建模块定义
        modules = []
        for idx, (top_dir, sub_dirs) in enumerate(dir_structure.items()):
            # 为顶级目录创建模块
            module = ModuleDefinition(
                project_id=self.project_id,
                name=top_dir,
                path_pattern=f"{top_dir}/*",
                layer=idx,  # 简单的按字母顺序分层
                description=f"Auto-detected module: {top_dir}"
            )
            modules.append(module)

        return modules

    def compute_file_layer(self, file_id: int, include_graph: nx.DiGraph) -> int:
        """
        计算文件在架构中的层次
        基于 include 关系进行拓扑排序
        """
        try:
            # 获取从根节点到当前文件的最长路径
            if file_id not in include_graph:
                return 0

            # 使用 longest_path 算法
            # 首先需要反转图（因为我们要的是"被依赖"的层次）
            reverse_graph = include_graph.reverse()

            # 使用 dag_longest_path_length
            try:
                layers = nx.single_source_shortest_path_length(reverse_graph, file_id)
                return max(layers.values()) if layers else 0
            except:
                return 0
        except:
            return 0

    def build_include_graph(self) -> nx.DiGraph:
        """
        构建基于 include 关系的依赖图
        """
        G = nx.DiGraph()

        files = self._get_project_files()
        for f in files:
            G.add_node(f.id, path=f.path)

        includes = self.db.query(Include).join(FileRecord, Include.source_file_id == FileRecord.id)\
            .filter((FileRecord.path == self.root_path) | (FileRecord.path.like(f"{self.root_path}{os.sep}%")))\
            .all()

        for inc in includes:
            if inc.target_file_id:
                # source include target => source 依赖 target
                G.add_edge(inc.source_file_id, inc.target_file_id)

        return G

    def detect_circular_dependencies(self) -> List[List[int]]:
        """
        检测循环依赖
        返回强连通分量列表
        """
        G = self.build_include_graph()

        # 找到所有强连通分量
        sccs = list(nx.strongly_connected_components(G))

        # 过滤掉单节点的分量（不是循环）
        circular_deps = [list(scc) for scc in sccs if len(scc) > 1]

        return circular_deps

    def compute_levelization(self) -> Dict[int, int]:
        """
        计算分层（Levelization）
        返回 {file_id: layer} 映射
        """
        G = self.build_include_graph()

        # 尝试拓扑排序
        try:
            # 检测并移除循环
            if not nx.is_directed_acyclic_graph(G):
                # 有环，使用 SCC condensation
                scc_graph = nx.condensation(G)
                topo_order = list(nx.topological_sort(scc_graph))

                # 构建层级映射
                layers = {}
                for layer, scc_id in enumerate(topo_order):
                    members = scc_graph.nodes[scc_id]['members']
                    for file_id in members:
                        layers[file_id] = layer
                return layers
            else:
                # 无环，直接计算
                layers = {}
                for node in nx.topological_sort(G):
                    # 节点的层级 = 所有前驱节点的最大层级 + 1
                    predecessors = list(G.predecessors(node))
                    if not predecessors:
                        layers[node] = 0
                    else:
                        layers[node] = max(layers.get(p, 0) for p in predecessors) + 1
                return layers
        except:
            return {}

    def check_architecture_violations(self) -> List[Dict]:
        """
        检查架构违规
        基于定义的架构规则
        """
        violations = []

        rules = self.db.query(ArchitectureRule).filter(
            ArchitectureRule.project_id == self.project_id,
            ArchitectureRule.is_active == True
        ).all()

        for rule in rules:
            if rule.rule_type == "layer_violation":
                # 检查分层违规
                violations.extend(self._check_layer_violations(rule))
            elif rule.rule_type == "locked_module":
                # 检查锁定模块违规
                violations.extend(self._check_locked_module_violations(rule))

        return violations

    def _check_layer_violations(self, rule: ArchitectureRule) -> List[Dict]:
        """
        检查分层违规
        下层不应调用上层
        """
        violations = []

        if not rule.source_module_id or not rule.target_module_id:
            return violations

        source_module = self.db.query(ModuleDefinition).filter(ModuleDefinition.id == rule.source_module_id).first()
        target_module = self.db.query(ModuleDefinition).filter(ModuleDefinition.id == rule.target_module_id).first()

        if not source_module or not target_module:
            return violations

        # 如果 source 的层级 < target 的层级，则是违规
        if source_module.layer < target_module.layer:
            # 查找实际的调用
            source_files = self.db.query(FileRecord).filter(FileRecord.module_id == source_module.id).all()
            target_files = self.db.query(FileRecord).filter(FileRecord.module_id == target_module.id).all()

            source_file_ids = [f.id for f in source_files]
            target_file_ids = [f.id for f in target_files]

            # 查找跨模块的引用
            refs = self.db.query(Reference, Symbol).join(Symbol, Reference.target_id == Symbol.id)\
                .filter(Reference.file_id.in_(source_file_ids))\
                .filter(Symbol.file_id.in_(target_file_ids))\
                .all()

            for ref, target_sym in refs:
                violations.append({
                    'rule_id': rule.id,
                    'rule_name': rule.name,
                    'type': 'layer_violation',
                    'message': f"Lower layer '{source_module.name}' (layer {source_module.layer}) calls upper layer '{target_module.name}' (layer {target_module.layer})",
                    'reference_line': ref.line,
                    'file_id': ref.file_id,
                    'target_symbol': target_sym.name
                })

        return violations

    def _check_locked_module_violations(self, rule: ArchitectureRule) -> List[Dict]:
        """
        检查锁定模块违规
        这需要结合 Git diff 来实现，这里提供检测框架
        """
        # TODO: 需要 Git 集成
        return []

    def get_module_dependency_matrix(self) -> Dict:
        """
        获取模块级别的依赖矩阵
        """
        modules = self.db.query(ModuleDefinition).filter(ModuleDefinition.project_id == self.project_id).all()

        if not modules:
            return {'modules': [], 'matrix': []}

        # 构建模块间的 include 依赖
        n = len(modules)
        matrix = [[0] * n for _ in range(n)]
        module_index = {m.id: i for i, m in enumerate(modules)}

        # 统计模块间的 include 关系
        for i, src_module in enumerate(modules):
            src_files = self.db.query(FileRecord).filter(FileRecord.module_id == src_module.id).all()
            src_file_ids = [f.id for f in src_files]

            for j, tgt_module in enumerate(modules):
                if i == j:
                    continue

                tgt_files = self.db.query(FileRecord).filter(FileRecord.module_id == tgt_module.id).all()
                tgt_file_ids = [f.id for f in tgt_files]

                # 统计 include 关系
                include_count = self.db.query(Include)\
                    .filter(Include.source_file_id.in_(src_file_ids))\
                    .filter(Include.target_file_id.in_(tgt_file_ids))\
                    .count()

                matrix[i][j] = include_count

        module_list = [{'id': m.id, 'name': m.name, 'layer': m.layer} for m in modules]

        return {
            'modules': module_list,
            'matrix': matrix
        }

    def get_hotspot_files(self, top_n: int = 10) -> List[Dict]:
        """
        获取热点文件（被频繁修改或高复杂度的文件）
        需要结合 Git 历史
        """
        # 基于复杂度和符号数量计算
        files = self._get_project_files()

        file_metrics = []
        for file in files:
            symbols = self.db.query(Symbol).filter(Symbol.file_id == file.id).all()
            total_complexity = sum(s.cyclomatic_complexity or 0 for s in symbols)
            function_count = len([s for s in symbols if s.kind == 'function'])

            file_metrics.append({
                'file_id': file.id,
                'path': file.path,
                'total_complexity': total_complexity,
                'function_count': function_count,
                'symbol_count': len(symbols),
                'avg_complexity': total_complexity / function_count if function_count > 0 else 0
            })

        # 按总复杂度排序
        file_metrics.sort(key=lambda x: x['total_complexity'], reverse=True)

        return file_metrics[:top_n]

    def get_structure_graph(self) -> Dict:
        """
        生成项目文件结构和依赖图
        Nodes: 文件夹 (Compound), 文件
        Edges: Include 关系
        """
        files = self._get_project_files()
        root_path = self.project.root_path
        
        nodes = []
        edges = []
        
        # 1. 构建目录树节点
        # 使用 set 避免重复
        dirs = set()
        
        for f in files:
            try:
                rel_path = os.path.relpath(f.path, root_path)
            except ValueError:
                # 处理不同驱动器的情况 (Windows)
                rel_path = os.path.basename(f.path)

            # 添加文件节点
            dir_name = os.path.dirname(rel_path)
            # 如果文件在根目录，dir_name 为 ''
            
            # 记录所有上级目录
            if dir_name:
                parts = dir_name.split(os.sep)
                current = ""
                for part in parts:
                    parent = current
                    current = os.path.join(current, part) if current else part
                    dirs.add((current, part, parent)) # (full_rel_path, label, parent_rel_path)

            nodes.append({
                "data": {
                    "id": str(f.id),
                    "label": os.path.basename(f.path),
                    "parent": dir_name if dir_name else None,
                    "type": "file",
                    "color": "#1890ff"
                }
            })

        # 添加目录节点
        for d_path, d_label, d_parent in dirs:
            nodes.append({
                "data": {
                    "id": d_path,
                    "label": d_label,
                    "parent": d_parent if d_parent else None,
                    "type": "directory",
                    "color": "#e6f7ff"
                }
            })

        # 2. 构建依赖边 (Include)
        includes = self.db.query(Include).join(FileRecord, Include.source_file_id == FileRecord.id)\
            .filter((FileRecord.path == self.root_path) | (FileRecord.path.like(f"{self.root_path}{os.sep}%")))\
            .all()

        for inc in includes:
            if inc.target_file_id:
                edges.append({
                    "data": {
                        "source": str(inc.source_file_id),
                        "target": str(inc.target_file_id),
                        "type": "include"
                    }
                })

        return {"nodes": nodes, "edges": edges}
