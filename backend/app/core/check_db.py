from sqlalchemy.orm import Session
from ..db.database import SessionLocal, engine, Base
from ..db.models import FileRecord, Symbol, Reference

# 确保表已创建 (如果尚未运行 indexer)
Base.metadata.create_all(bind=engine)

def check_db_content():
    db: Session = SessionLocal()
    
    print("--- Files ---")
    files = db.query(FileRecord).all()
    for f in files:
        print(f"ID: {f.id}, Path: {f.path}, Modified: {f.last_modified}")

    print("\n--- Symbols ---")
    symbols = db.query(Symbol).all()
    for s in symbols:
        file_path = db.query(FileRecord).filter(FileRecord.id == s.file_id).first().path if s.file_id else "N/A"
        print(f"ID: {s.id}, Name: {s.name}, Kind: {s.kind}, USR: {s.usr}, File: {file_path}, Line: {s.line}")

    print("\n--- References ---")
    references = db.query(Reference).all()
    for r in references:
        source_symbol = db.query(Symbol).filter(Symbol.id == r.source_id).first()
        target_symbol = db.query(Symbol).filter(Symbol.id == r.target_id).first()
        source_name = source_symbol.name if source_symbol else "N/A"
        target_name = target_symbol.name if target_symbol else "N/A"
        
        file_path = db.query(FileRecord).filter(FileRecord.id == r.file_id).first().path if r.file_id else "N/A"
        
        print(f"ID: {r.id}, Source: {source_name}, Target: {target_name}, Kind: {r.kind}, File: {file_path}, Line: {r.line}")

    db.close()

if __name__ == "__main__":
    check_db_content()
