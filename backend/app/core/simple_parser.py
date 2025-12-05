import sys
import os
import clang.cindex
from clang.cindex import CursorKind

# --- 配置 LibClang ---
# 在 Windows 上，有时需要手动指定 libclang.dll 的路径
# 如果 pip install libclang 成功，通常不需要这一步，但为了保险起见，
# 如果报错，我们需要在这里处理。
try:
    # 尝试创建一个 Index，如果报错说明找不到 DLL
    clang.cindex.Index.create()
except Exception:
    print("Warning: Standard loading failed. Trying to find libclang manually...")
    # 这里可以添加额外的搜索逻辑，或者提示用户安装 LLVM
    # Config.set_library_path("C:/Program Files/LLVM/bin") 

def print_node_info(node, depth=0):
    """递归打印 AST 节点信息"""
    indent = "  " * depth
    
    # 我们主要关注文件中的定义
    if node.location.file and str(node.location.file).endswith("sample.c"):
        kind_name = str(node.kind).split(".")[1]
        print(f"{indent}[{kind_name}] {node.spelling} (Line: {node.location.line})")

        # 如果是函数，我们可以进一步看它里面调用了谁
        if node.kind == CursorKind.FUNCTION_DECL:
            # 标记这是个函数定义
            pass

    # 递归遍历子节点
    for child in node.get_children():
        print_node_info(child, depth + 1)

def parse_code(file_path):
    print(f"--- Parsing: {file_path} ---")
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return

    index = clang.cindex.Index.create()
    
    # 解析文件
    # args=['-std=c11'] 可以指定编译标准
    tu = index.parse(file_path)
    
    print("Translation Unit created. Traversing AST...")
    print_node_info(tu.cursor)

if __name__ == "__main__":
    # 获取测试文件的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 回退两级找到 tests 目录 (假设脚本在 backend/app/core)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
    target_file = os.path.join(current_dir, "../../tests/sample.c")
    
    # 如果路径不对，尝试直接用相对路径
    if not os.path.exists(target_file):
        target_file = os.path.abspath(os.path.join("backend", "tests", "sample.c"))
    
    parse_code(target_file)
