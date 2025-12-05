# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CodeUnderstand is a cross-platform C language code analysis tool designed to help developers understand large C codebases (like Linux kernel modules and embedded systems). It provides deep code comprehension capabilities beyond typical IDEs, focusing on reading and understanding code rather than just editing it.

**Core Value Proposition**: Unlike VS Code which optimizes for writing code, this tool specializes in architecture analysis, relationship visualization, and understanding legacy codebases with complex macro definitions.

## Architecture

This is an **Electron-based desktop application** with a client-server architecture:

- **Frontend**: React + Ant Design UI running in Electron, using Monaco Editor for code display and Cytoscape.js for interactive relationship graphs
- **Backend**: FastAPI Python server that performs C code parsing using LibClang and stores analysis results in SQLite
- **Parser**: LibClang-based indexer that extracts symbols, references, and relationships from C source code

### Key Components

**Backend (`backend/`)**:
- `app/main.py` - FastAPI server with REST endpoints for project management, code analysis, and graph generation
- `app/core/indexer.py` - Core LibClang-based parser that builds the symbol database
- `app/db/models.py` - SQLAlchemy models: `Project`, `FileRecord`, `Symbol`, `Reference`
- `app/db/database.py` - Database session management (SQLite)
- `code_analysis.db` - SQLite database storing parsed code metadata

**Frontend (`frontend/`)**:
- `src/App.jsx` - Main React component with project list, file tree, code editor, and graph visualization
- `electron/main.js` - Electron main process
- Monaco Editor integration for code viewing
- Cytoscape.js for rendering call graphs and dependency diagrams

### Data Model

The tool uses a relational database to store comprehensive code metadata:

- **Symbol**: Functions, variables, structs, typedefs, macros with USR (Unified Symbol Resolution) identifiers
- **Reference**: Tracks relationships (CALL, READ, WRITE, TYPE_USAGE) between symbols
- **FileRecord**: Source files with modification timestamps for incremental parsing
- **Project**: Root container for C codebases being analyzed

## Development Commands

### Backend

Start the FastAPI backend server:
```bash
cd backend
.\venv\Scripts\activate  # Windows
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or use the convenience script:
```bash
run_backend.bat  # Windows
```

Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### Frontend

Start the Electron app with hot-reload:
```bash
cd frontend
npm run electron:dev
```

Or use the convenience script:
```bash
run_frontend.bat  # Windows
```

This command runs both Vite dev server and Electron concurrently.

Build the frontend for production:
```bash
cd frontend
npm run build
```

Run ESLint:
```bash
cd frontend
npm run lint
```

### Full Stack Development

1. Start backend in one terminal: `run_backend.bat`
2. Start frontend in another terminal: `run_frontend.bat`
3. The frontend will connect to `http://127.0.0.1:8000` for API calls

## Key Technical Details

### LibClang Integration

The parser uses LibClang's Python bindings to traverse C source files:

1. Parses files into Abstract Syntax Trees (AST)
2. Extracts symbol definitions (functions, variables, structs) with location info
3. Identifies references (function calls, variable reads/writes) with context
4. Uses USR (Unified Symbol Resolution) for globally unique symbol identification
5. Stores all data in SQLite for fast querying

**Important**: The tool requires either `compile_commands.json` or proper include path configuration for accurate parsing of projects with complex macro definitions.

### Incremental Parsing

The `FileRecord.last_modified` timestamp enables incremental updates - only changed files are re-parsed, avoiding full project scans on every update.

### Graph Visualization

The frontend can generate several graph types:
- **Call Graph**: Function call relationships filtered by file or globally
- **Dependency Structure Matrix (DSM)**: Module-level dependency analysis for detecting circular dependencies
- **Symbol Relations**: Variable read/write patterns and type usage

### Background Processing

Project scanning happens asynchronously via FastAPI's `BackgroundTasks` to prevent blocking the API during large codebase analysis.

## Project Workflow

1. **Create Project**: User specifies a name and root directory containing C source
2. **Scan Project**: Background task walks directory tree, parses all `.c`/`.h` files with LibClang
3. **Browse Code**: File tree navigation with Monaco Editor display
4. **Analyze Relations**: Click symbols to see call graphs, references, and dependency diagrams
5. **Search Symbols**: Fast full-text search across all indexed symbols

## Testing

Backend tests are located in `backend/tests/` but test infrastructure needs expansion.

## Notes for Development

### When modifying the parser (`indexer.py`):
- Symbol extraction happens in `get_or_create_symbol()` which maps Clang cursor kinds to internal `SymbolType` enum
- Reference tracking happens in `visit_node()` which recursively walks the AST
- The `parent_symbol_id` parameter tracks lexical scope (e.g., which function a variable reference occurs in)
- Use `is_written_context` flag to distinguish variable writes from reads

### When modifying the API (`main.py`):
- All endpoints use SQLAlchemy sessions via `SessionLocal()`
- Remember to close sessions in finally blocks
- Background tasks run in separate DB sessions

### When modifying the UI (`App.jsx`):
- State management uses React hooks (no Redux/Context)
- The app has two main views: 'project-list' and 'project-detail'
- File tree is built dynamically from flat file paths in `treeData` useMemo
- Graph filtering by `filterKind` ('function', 'variable', etc.) affects what the backend returns

### Electron Integration
- IPC is available via `window.require('electron').ipcRenderer`
- Frontend checks for Electron context before using IPC features
- Main process is in `frontend/electron/main.js`
