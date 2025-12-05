from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SqEnum, Text, Float, Boolean
from sqlalchemy.orm import relationship
import enum
from datetime import datetime
from .database import Base

class SymbolType(str, enum.Enum):
    FUNCTION = "function"
    VARIABLE = "variable"
    STRUCT = "struct"
    TYPEDEF = "typedef"
    MACRO = "macro"
    FIELD = "field" # 结构体成员
    ENUM = "enum"
    UNION = "union"

class RefType(str, enum.Enum):
    CALL = "call"       # 函数调用
    READ = "read"       # 变量读取
    WRITE = "write"     # 变量写入
    TYPE_USAGE = "type_usage" # 使用了某种类型 (如 Point_t p)
    INCLUDE = "include" # 头文件包含关系

class ScanStatus(str, enum.Enum):
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"

class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    root_path = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    scan_status = Column(String, default=ScanStatus.PENDING)
    scan_progress = Column(Float, default=0.0)  # 0.0 to 1.0
    scan_message = Column(String, nullable=True)
    compile_commands_path = Column(String, nullable=True)  # Path to compile_commands.json

    files = relationship("FileRecord", back_populates="project", cascade="all, delete-orphan")
    macros = relationship("MacroDefinition", back_populates="project", cascade="all, delete-orphan")
    modules = relationship("ModuleDefinition", back_populates="project", cascade="all, delete-orphan")
    arch_rules = relationship("ArchitectureRule", back_populates="project", cascade="all, delete-orphan")

class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, unique=True, index=True)
    last_modified = Column(Integer)  # 用于增量更新检测
    project_id = Column(Integer, ForeignKey("projects.id"))
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=True)  # 所属模块

    project = relationship("Project", back_populates="files")
    module = relationship("ModuleDefinition", back_populates="files")
    symbols = relationship("Symbol", back_populates="file", cascade="all, delete-orphan")
    includes = relationship("Include", back_populates="source_file", foreign_keys="Include.source_file_id", cascade="all, delete-orphan")

class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    usr = Column(String, unique=True, index=True)  # Unified Symbol Resolution (Clang提供的唯一标识符)
    kind = Column(String)  # 对应 SymbolType
    signature = Column(Text, nullable=True)  # 函数签名或类型定义的完整文本

    file_id = Column(Integer, ForeignKey("files.id"))
    line = Column(Integer)
    column = Column(Integer)
    end_line = Column(Integer, nullable=True)  # 符号结束行

    # 代码质量度量
    cyclomatic_complexity = Column(Integer, default=0)  # 圈复杂度（仅函数）
    lines_of_code = Column(Integer, default=0)  # 代码行数

    # 可见性和修饰符
    is_static = Column(Boolean, default=False)
    is_extern = Column(Boolean, default=False)
    is_definition = Column(Boolean, default=True)  # 是定义还是声明

    file = relationship("FileRecord", back_populates="symbols")

    # 作为一个被引用者，我有哪些引用记录
    incoming_refs = relationship("Reference", back_populates="target_symbol", foreign_keys="Reference.target_id")
    # 作为一个作用域（比如函数），我内部发起了哪些引用
    outgoing_refs = relationship("Reference", back_populates="source_symbol", foreign_keys="Reference.source_id")

class Reference(Base):
    __tablename__ = "references"

    id = Column(Integer, primary_key=True, index=True)

    source_id = Column(Integer, ForeignKey("symbols.id"))  # 谁发起的引用 (例如 main 函数)
    target_id = Column(Integer, ForeignKey("symbols.id"))  # 引用了谁 (例如 add_points 函数)

    kind = Column(String)  # 对应 RefType
    file_id = Column(Integer, ForeignKey("files.id"))  # 引用发生的文件
    line = Column(Integer)
    column = Column(Integer)

    source_symbol = relationship("Symbol", foreign_keys=[source_id], back_populates="outgoing_refs")
    target_symbol = relationship("Symbol", foreign_keys=[target_id], back_populates="incoming_refs")

class Include(Base):
    """头文件包含关系表 - 用于正确的 DSM 实现"""
    __tablename__ = "includes"

    id = Column(Integer, primary_key=True, index=True)
    source_file_id = Column(Integer, ForeignKey("files.id"))  # 哪个文件
    target_path = Column(String)  # 包含了哪个头文件 (可能是相对路径或系统路径)
    target_file_id = Column(Integer, ForeignKey("files.id"), nullable=True)  # 如果能解析到项目内文件
    line = Column(Integer)  # 包含语句所在行

    source_file = relationship("FileRecord", foreign_keys=[source_file_id], back_populates="includes")
    target_file = relationship("FileRecord", foreign_keys=[target_file_id])

class MacroDefinition(Base):
    """宏定义配置表"""
    __tablename__ = "macros"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, index=True)
    value = Column(Text, nullable=True)  # 宏的值，可以为空（#define FLAG）
    is_from_compile_commands = Column(Boolean, default=False)  # 是否来自 compile_commands.json

    project = relationship("Project", back_populates="macros")

class ModuleDefinition(Base):
    """模块定义表 - 用于架构分析"""
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String, index=True)
    path_pattern = Column(String)  # 路径模式，如 "drivers/*" 或 "core/network/"
    layer = Column(Integer, default=0)  # 架构层次，0=最底层，数字越大层次越高
    is_locked = Column(Boolean, default=False)  # 是否锁定（禁止修改）
    description = Column(Text, nullable=True)

    project = relationship("Project", back_populates="modules")
    files = relationship("FileRecord", back_populates="module")

class ArchitectureRule(Base):
    """架构规则表 - 用于架构守护"""
    __tablename__ = "architecture_rules"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String)
    rule_type = Column(String)  # "layer_violation", "forbidden_call", "locked_module"
    source_module_id = Column(Integer, ForeignKey("modules.id"), nullable=True)
    target_module_id = Column(Integer, ForeignKey("modules.id"), nullable=True)
    pattern = Column(String, nullable=True)  # 正则表达式或模式
    is_active = Column(Boolean, default=True)
    violation_message = Column(Text)

    project = relationship("Project", back_populates="arch_rules")
