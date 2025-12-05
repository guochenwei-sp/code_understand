from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
# backend/app/db/database.py -> backend/app/db -> backend/app -> backend
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "code_analysis.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_fts5():
    """初始化 FTS5 全文搜索虚拟表"""
    with engine.connect() as conn:
        # 为了修复之前的 schema 问题，我们先尝试删除旧表和触发器
        conn.execute(text("DROP TRIGGER IF EXISTS symbols_ai"))
        conn.execute(text("DROP TRIGGER IF EXISTS symbols_ad"))
        conn.execute(text("DROP TRIGGER IF EXISTS symbols_au"))
        conn.execute(text("DROP TABLE IF EXISTS symbols_fts"))
        
        # 创建 FTS5 虚拟表 (标准模式，不使用 external content)
        # 这样我们可以自由定义字段，包括 file_path
        conn.execute(text("""
            CREATE VIRTUAL TABLE symbols_fts USING fts5(
                symbol_id UNINDEXED,
                name,
                kind,
                signature,
                file_path
            )
        """))

        # 创建触发器以保持 FTS5 表同步
        conn.execute(text("""
            CREATE TRIGGER symbols_ai AFTER INSERT ON symbols BEGIN
                INSERT INTO symbols_fts(rowid, symbol_id, name, kind, signature, file_path)
                SELECT new.id, new.id, new.name, new.kind, new.signature,
                        (SELECT path FROM files WHERE id = new.file_id)
                FROM symbols WHERE id = new.id;
            END
        """))

        conn.execute(text("""
            CREATE TRIGGER symbols_ad AFTER DELETE ON symbols BEGIN
                DELETE FROM symbols_fts WHERE rowid = old.id;
            END
        """))

        conn.execute(text("""
            CREATE TRIGGER symbols_au AFTER UPDATE ON symbols BEGIN
                UPDATE symbols_fts SET name = new.name, kind = new.kind,
                                        signature = new.signature
                WHERE rowid = old.id;
            END
        """))

        # 重建索引：将现有数据导入 FTS
        # 注意：每次启动都重建可能会慢，但对于修复 bug 和确保一致性是必要的
        # 在生产环境中应该只在表不存在时执行
        conn.execute(text("DELETE FROM symbols_fts")) # 清空以防万一
        conn.execute(text("""
            INSERT INTO symbols_fts(rowid, symbol_id, name, kind, signature, file_path)
            SELECT s.id, s.id, s.name, s.kind, s.signature, f.path
            FROM symbols s
            JOIN files f ON s.file_id = f.id
        """))
        
        conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
