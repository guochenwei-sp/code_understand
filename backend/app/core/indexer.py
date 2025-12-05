import sys
import os
import re
import clang.cindex
from clang.cindex import CursorKind, TokenKind
from sqlalchemy.orm import Session
from ..db.database import SessionLocal, engine, Base
from ..db.models import FileRecord, Symbol, Reference, SymbolType, RefType, Project, Include, ScanStatus

# 确保表已创建
Base.metadata.create_all(bind=engine)

# --- LibClang 配置 (复用之前的逻辑) ---
try:
    clang.cindex.Index.create()
except Exception:
    pass # 假设环境已配置或依赖 PATH

def calculate_cyclomatic_complexity(cursor):
    """
    计算函数的圈复杂度
    基本算法：统计判定节点数量 + 1
    """
    if cursor.kind != CursorKind.FUNCTION_DECL:
        return 0

    complexity = 1  # 基础复杂度

    def count_decision_points(node):
        nonlocal complexity

        # 判定节点类型
        decision_kinds = {
            CursorKind.IF_STMT,
            CursorKind.WHILE_STMT,
            CursorKind.FOR_STMT,
            CursorKind.CASE_STMT,
            CursorKind.DEFAULT_STMT,
            CursorKind.CONDITIONAL_OPERATOR,  # ? :
            CursorKind.DO_STMT
        }

        if node.kind in decision_kinds:
            complexity += 1

        # 检查逻辑运算符 && 和 ||
        if node.kind == CursorKind.BINARY_OPERATOR:
            try:
                tokens = list(node.get_tokens())
                for token in tokens:
                    if token.spelling in ['&&', '||']:
                        complexity += 1
            except:
                pass

        for child in node.get_children():
            count_decision_points(child)

    count_decision_points(cursor)
    return complexity

def get_symbol_signature(cursor):
    """
    获取符号的签名（函数签名、类型定义等）
    """
    try:
        # 尝试获取完整的声明文本
        extent = cursor.extent
        if extent.start.file and extent.start.file == extent.end.file:
            # 读取源码片段
            with open(str(extent.start.file), 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                start_line = extent.start.line - 1
                end_line = extent.end.line - 1

                if start_line == end_line:
                    line = lines[start_line]
                    sig = line[extent.start.column-1:extent.end.column-1]
                else:
                    # 多行签名
                    sig_parts = []
                    for i in range(start_line, min(end_line + 1, len(lines))):
                        if i == start_line:
                            sig_parts.append(lines[i][extent.start.column-1:])
                        elif i == end_line:
                            sig_parts.append(lines[i][:extent.end.column-1])
                        else:
                            sig_parts.append(lines[i])
                    sig = ''.join(sig_parts)

                # 清理空白符
                sig = ' '.join(sig.split())
                # 限制长度
                if len(sig) > 500:
                    sig = sig[:500] + "..."
                return sig
    except:
        pass

    # 降级方案：使用 cursor 的 displayname
    return cursor.displayname or cursor.spelling

def get_symbol_end_line(cursor):
    """获取符号的结束行"""
    try:
        return cursor.extent.end.line
    except:
        return cursor.location.line

class Indexer:
    def __init__(self, db: Session):
        self.db = db
        self.index = clang.cindex.Index.create()
        self.current_file_id = None
        self.file_path = None

    def get_or_create_file(self, path: str, project_id: int = None) -> FileRecord:
        # 统一路径格式
        abs_path = os.path.abspath(path)
        file_record = self.db.query(FileRecord).filter(FileRecord.path == abs_path).first()
        if not file_record:
            file_record = FileRecord(
                path=abs_path, 
                last_modified=int(os.path.getmtime(abs_path)),
                project_id=project_id
            )
            self.db.add(file_record)
            self.db.commit()
            self.db.refresh(file_record)
        return file_record

    def get_or_create_symbol(self, cursor) -> Symbol:
        """
        根据 Cursor 获取或创建符号。
        使用 USR (Unified Symbol Resolution) 作为唯一标识。
        """
        if not cursor:
            return None

        usr = cursor.get_usr()
        if not usr:
            return None

        # 尝试查找现有的
        symbol = self.db.query(Symbol).filter(Symbol.usr == usr).first()
        if symbol:
            return symbol

        # 确定符号类型
        kind_map = {
            CursorKind.FUNCTION_DECL: SymbolType.FUNCTION,
            CursorKind.VAR_DECL: SymbolType.VARIABLE,
            CursorKind.STRUCT_DECL: SymbolType.STRUCT,
            CursorKind.TYPEDEF_DECL: SymbolType.TYPEDEF,
            CursorKind.FIELD_DECL: SymbolType.FIELD,
            CursorKind.PARM_DECL: SymbolType.VARIABLE,
            CursorKind.ENUM_DECL: SymbolType.ENUM,
            CursorKind.UNION_DECL: SymbolType.UNION,
            CursorKind.MACRO_DEFINITION: SymbolType.MACRO
        }

        # 默认归类为 Variable 如果映射不到
        sym_type = kind_map.get(cursor.kind, SymbolType.VARIABLE)

        # 获取签名
        signature = get_symbol_signature(cursor)

        # 计算圈复杂度（仅函数）
        complexity = 0
        if cursor.kind == CursorKind.FUNCTION_DECL:
            complexity = calculate_cyclomatic_complexity(cursor)

        # 检查是否是定义还是声明
        is_definition = cursor.is_definition()

        # 检查存储类
        is_static = cursor.storage_class == clang.cindex.StorageClass.STATIC
        is_extern = cursor.storage_class == clang.cindex.StorageClass.EXTERN

        # 获取结束行
        end_line = get_symbol_end_line(cursor)

        symbol = Symbol(
            name=cursor.spelling,
            usr=usr,
            kind=sym_type,
            signature=signature,
            line=cursor.location.line,
            column=cursor.location.column,
            end_line=end_line,
            cyclomatic_complexity=complexity,
            is_static=is_static,
            is_extern=is_extern,
            is_definition=is_definition,
            file_id=self.current_file_id
        )
        self.db.add(symbol)
        self.db.commit()
        self.db.refresh(symbol)
        return symbol

    def visit_node(self, node, parent_symbol_id=None, is_written_context=False):
        """
        递归遍历 AST
        :param node: 当前 AST 节点
        :param parent_symbol_id: 当前节点所处的“作用域”符号ID (例如在 main 函数内部)
        :param is_written_context: 是否处于被写入的上下文 (例如赋值号左边)
        """
        
        # 1. 检查当前节点是不是一个“定义” (Definition)
        # 如果是定义，它将成为子节点的 parent_symbol_id
        current_symbol_id = parent_symbol_id
        
        is_definition = node.kind in [
            CursorKind.FUNCTION_DECL, 
            CursorKind.STRUCT_DECL, 
            CursorKind.TYPEDEF_DECL,
            CursorKind.VAR_DECL
        ]

        # 只有在当前文件定义的符号我们才作为“Source”
        # 避免去遍历 include 进来的头文件里的所有定义
        in_current_file = (node.location.file and os.path.abspath(str(node.location.file)) == self.file_path)

        if is_definition and in_current_file:
            symbol = self.get_or_create_symbol(node)
            if symbol:
                current_symbol_id = symbol.id
                # print(f"Defined: {symbol.name} ({symbol.kind})")

        # 2. 检查当前节点是不是一个“引用” (Reference)
        # 只有当我们处于某个作用域内 (parent_symbol_id is valid) 时，引用才有意义
        # 例如：全局变量初始化时的引用，或者函数体内的调用
        if parent_symbol_id:
            ref_kind = None
            target_cursor = None

            if node.kind == CursorKind.CALL_EXPR:
                ref_kind = RefType.CALL
                target_cursor = node.get_definition() or node.referenced
            
            elif node.kind in [CursorKind.DECL_REF_EXPR, CursorKind.MEMBER_REF_EXPR]:
                # 区分读写
                ref_kind = RefType.WRITE if is_written_context else RefType.READ
                target_cursor = node.get_definition() or node.referenced

            if ref_kind and target_cursor:
                # 获取被引用的符号 (Target)
                target_symbol = self.get_or_create_symbol(target_cursor)
                
                if target_symbol:
                    # 创建引用记录
                    # 避免重复添加完全相同的引用？(可选)
                    ref = Reference(
                        source_id=parent_symbol_id,
                        target_id=target_symbol.id,
                        kind=ref_kind,
                        file_id=self.current_file_id,
                        line=node.location.line,
                        column=node.location.column
                    )
                    self.db.add(ref)
                    # print(f"  -> Ref: {ref_kind} to {target_symbol.name}")

        # 3. 递归遍历子节点
        
        # 特殊处理：检测赋值操作，区分读写
        # 如果当前节点是二元操作符或复合赋值符
        if node.kind == CursorKind.BINARY_OPERATOR or node.kind == CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
            # 简单的启发式：检查 token 中是否包含赋值号
            # 注意：这可能会误判宏展开等复杂情况，但对大多数 C 代码有效
            is_assign = False
            try:
                # 检查直接属于该节点的 tokens (不含子节点? LibClang 的 get_tokens 包含所有覆盖范围的 token)
                # 我们简单检查是否有赋值类操作符
                assign_ops = {'=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='}
                # 为了性能，这里只取前几个 token 或者完全遍历? 
                # 对于 a = b，token 是 'a', '=', 'b'。
                # 只要存在 assignment operator，我们就假设这是一个赋值表达式
                # 并且左侧子节点是被写入的。
                # 这种判断对于 a == b 是安全的，因为 == 不在集合中。
                tokens = [t.spelling for t in node.get_tokens()]
                if any(t in assign_ops for t in tokens):
                    is_assign = True
            except Exception:
                pass
            
            if is_assign:
                children = list(node.get_children())
                # 赋值表达式 LHS 是写入
                if len(children) >= 1:
                    self.visit_node(children[0], parent_symbol_id, is_written_context=True)
                # RHS 是读取
                if len(children) >= 2:
                    for child in children[1:]:
                        self.visit_node(child, parent_symbol_id, is_written_context=False)
                return # 跳过默认递归

        # 默认递归逻辑
        # 注意：如果当前节点是定义，传递 current_symbol_id (即它自己) 作为 scope
        # 如果当前节点只是语句(IfStmt)，传递 parent_symbol_id (保持原 scope)
        next_scope = current_symbol_id if is_definition else parent_symbol_id
        
        for child in node.get_children():
            self.visit_node(child, next_scope, is_written_context=False)

    def extract_includes(self, tu):
        """提取 #include 指令"""
        try:
            for inclusion in tu.get_includes():
                # inclusion.source 是 File 对象
                # inclusion.include 也是 File 对象（被包含的文件）
                source_path = os.path.abspath(str(inclusion.source))
                target_path = str(inclusion.include)

                # 检查是否是当前文件
                if source_path != self.file_path:
                    continue

                # 尝试查找目标文件是否在项目中
                target_file_record = self.db.query(FileRecord).filter(
                    FileRecord.path == os.path.abspath(target_path)
                ).first()

                # 创建 Include 记录
                include_record = Include(
                    source_file_id=self.current_file_id,
                    target_path=target_path,
                    target_file_id=target_file_record.id if target_file_record else None,
                    line=inclusion.location.line
                )
                self.db.add(include_record)
        except Exception as e:
            print(f"Warning: Failed to extract includes: {e}")

    def index_file(self, file_path, project_id: int = None, comp_db=None):
        print(f"Indexing: {file_path}")
        self.file_path = os.path.abspath(file_path)

        # 1. 注册文件
        file_record = self.get_or_create_file(file_path, project_id)
        self.current_file_id = file_record.id

        # 清理旧的 symbols 和 includes（增量更新）
        self.db.query(Symbol).filter(Symbol.file_id == file_record.id).delete()
        self.db.query(Include).filter(Include.source_file_id == file_record.id).delete()
        self.db.commit()

        # 2. 准备编译参数
        args = []
        if comp_db:
            try:
                cmds = comp_db.getCompileCommands(file_path)
                if cmds:
                    # 获取第一条编译命令
                    cmd = cmds[0]
                    cmd_args = list(cmd.arguments)

                    # 简单的过滤策略：去掉编译器路径
                    if len(cmd_args) > 0:
                        if not cmd_args[0].startswith('-'):
                            args = cmd_args[1:]
                        else:
                            args = cmd_args
            except Exception as e:
                print(f"Error getting compile commands: {e}")

        # 3. 解析
        try:
            tu = self.index.parse(file_path, args=args)

            # 4. 提取 include 关系
            self.extract_includes(tu)

            # 5. 开始遍历 AST
            self.visit_node(tu.cursor)
            self.db.commit()
        except Exception as e:
            print(f"Failed to parse {file_path}: {e}")
            self.db.rollback()

    def scan_project(self, project_id: int, root_path: str):
        """
        递归扫描整个项目目录
        """
        print(f"Scanning project {project_id} at {root_path}")

        # 更新项目状态为 SCANNING
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.scan_status = ScanStatus.SCANNING
            project.scan_progress = 0.0
            project.scan_message = "Initializing scan..."
            self.db.commit()

        try:
            # 尝试加载 compile_commands.json
            comp_db = None
            db_path = os.path.join(root_path, "compile_commands.json")
            if not os.path.exists(db_path):
                db_path = os.path.join(root_path, "build", "compile_commands.json")

            if os.path.exists(db_path):
                print(f"Found compilation database at {db_path}")
                try:
                    comp_db = clang.cindex.CompilationDatabase.fromDirectory(os.path.dirname(db_path))
                    if project:
                        project.compile_commands_path = db_path
                        self.db.commit()
                except Exception as e:
                    print(f"Failed to load compilation database: {e}")

            # 首先收集所有文件
            files_to_scan = []
            for root, dirs, files in os.walk(root_path):
                # 忽略一些常见目录
                if '.git' in dirs: dirs.remove('.git')
                if 'build' in dirs: dirs.remove('build')
                if 'venv' in dirs: dirs.remove('venv')
                if 'node_modules' in dirs: dirs.remove('node_modules')

                for file in files:
                    if file.endswith(('.c', '.h', '.cpp', '.hpp', '.cc', '.cxx')):
                        full_path = os.path.join(root, file)
                        files_to_scan.append(full_path)

            total_files = len(files_to_scan)
            print(f"Found {total_files} files to index")

            # 扫描文件并更新进度
            for idx, full_path in enumerate(files_to_scan):
                try:
                    self.index_file(full_path, project_id, comp_db)

                    # 每10个文件更新一次进度
                    if (idx + 1) % 10 == 0 and project:
                        progress = (idx + 1) / total_files
                        project.scan_progress = progress
                        project.scan_message = f"Indexed {idx + 1}/{total_files} files"
                        self.db.commit()
                except Exception as e:
                    print(f"Error indexing {full_path}: {e}")
                    continue

            # 扫描完成
            if project:
                project.scan_status = ScanStatus.COMPLETED
                project.scan_progress = 1.0
                project.scan_message = f"Scan complete. Indexed {total_files} files."
                self.db.commit()

            print(f"Project scan complete. Indexed {total_files} files.")

        except Exception as e:
            print(f"Scan failed: {e}")
            if project:
                project.scan_status = ScanStatus.FAILED
                project.scan_message = f"Scan failed: {str(e)}"
                self.db.commit()
