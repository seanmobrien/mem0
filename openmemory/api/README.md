# OpenMemory API

This directory contains the backend API for OpenMemory, built with FastAPI and SQLAlchemy. This also runs the Mem0 MCP Server that you can use with MCP clients to remember things.

## Quick Start with Docker (Recommended)

The easiest way to get started is using Docker. Make sure you have Docker and Docker Compose installed.

1. Build the containers:
```bash
make build
```

2. Create `.env` file:
```bash
make env
```

Once you run this command, edit the file `api/.env` and enter the `OPENAI_API_KEY`.

3. Start the services:
```bash
make up
```

The API will be available at `http://localhost:8765`

### Common Docker Commands

- View logs: `make logs`
- Open shell in container: `make shell`
- Run database migrations: `make migrate`
- Run tests: `make test`
- Run tests and clean up: `make test-clean`
- Stop containers: `make down`

## Local Development Setup

### Prerequisites

- Python 3.12+
- `hatch` (Python project manager)
- `pip` (Python package manager)

### Installation Steps

1. **Install hatch** (if not already installed):
```bash
pip install hatch
# or globally via pipx for system-wide availability
pipx install hatch
```

2. **Set up virtual environment** from the root directory:

   Create a new virtual environment (if one doesn't exist):
```bash
cd /path/to/mem0
python3.12 -m venv .venv
```

   Activate the virtual environment:
```bash
# On Linux/macOS
source .venv/bin/activate

# On Windows
.venv\Scripts\activate
```

3. **Install mem0 in editable mode** from the root directory:

   For rapid development with instant code reloading:
```bash
pip install -e .
```

   This installs mem0 in editable/development mode, so changes to the mem0 source code are immediately reflected without rebuilding.

   Alternatively, for distribution builds:
```bash
hatch build
```

   This creates the `mem0ai` wheel package (use this for production deployments).

4. **Install dependencies** in the openmemory/api directory:
```bash
cd openmemory/api
pip install -r requirements.txt
```

5. **Create `.env` file** (optional, for local development):
```bash
cp .env.example .env  # if .env.example exists
# Edit .env and add OPENAI_API_KEY and other required environment variables
```

6. **Run the server**:

   With auto-reload (recommended for development):
```bash
uvicorn main:app --host 0.0.0.0 --port 8765 --no-server-header --forwarded-allow-ips '*' --log-level debug --reload
```

   Without auto-reload (production-like testing):
```bash
uvicorn main:app --host 0.0.0.0 --port 8765 --no-server-header --forwarded-allow-ips '*' --log-level debug
```

The API will be available at `http://localhost:8765`

### Local Debugging in VS Code

Use the provided VS Code launch configurations for debugging:

1. Open the Debug view (Ctrl+Shift+D or Cmd+Shift+D)
2. Select one of the launch configurations:
   - **"OpenMemory API Debug"** — Includes `--reload` flag for automatic code reloading during development
   - **"OpenMemory API (No Reload)"** — Without reload for production-like testing
3. Click the play button or press F5 to start debugging

**Features:**
- Breakpoints and step debugging fully functional
- Automatic code reloading when you save files (Debug configuration)
- Output in the integrated terminal
- Framework code debugging enabled

### Common Local Development Tasks

- **Run tests**: `pytest`
- **Run with code reload**: Use the "OpenMemory API Debug" launch configuration
- **Access API docs**: Visit `http://localhost:8765/docs` while server is running
- **View database**: The default SQLite database is `openmemory.db` in the api directory

## API Documentation

Once the server is running, you can access the API documentation at:
- Swagger UI: `http://localhost:8765/docs`
- ReDoc: `http://localhost:8765/redoc`

## Project Structure

- `app/`: Main application code
  - `models.py`: Database models
  - `database.py`: Database configuration
  - `routers/`: API route handlers
- `migrations/`: Database migration files
- `tests/`: Test files
- `alembic/`: Alembic migration configuration
- `main.py`: Application entry point

## Development Guidelines

- Follow PEP 8 style guide
- Use type hints
- Write tests for new features
- Update documentation when making changes
- Run migrations for database changes
