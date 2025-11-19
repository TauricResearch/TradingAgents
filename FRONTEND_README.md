# TradingAgents Frontend

This document describes how to run the TradingAgents web application.

## Architecture

The application consists of two parts:
1. **Backend** (`backend/`) - FastAPI server that wraps TradingAgentsGraph
2. **Frontend** (`frontend/`) - Next.js React application

## Prerequisites

- Python 3.10+ with uv or pip
- Node.js 18+ and npm
- Environment variables configured (see `.env` file)

## Setup

### Backend Setup

1. Install backend dependencies:
```bash
cd backend
pip install -r requirements.txt
# Or if using uv:
uv pip install -r requirements.txt
```

2. Ensure the main TradingAgents package is installed (it should be in the parent directory)

3. Set environment variables in `.env`:
```
OPENAI_API_KEY=your_key_here
ALPHA_VANTAGE_API_KEY=your_key_here
```

### Frontend Setup

1. Install frontend dependencies:
```bash
cd frontend
npm install
```

2. Create `.env.local` file:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

## Running the Application

### Start the Backend

From the project root directory:

```bash
# Option 1: Using the run script
cd backend
python run.py

# Option 2: Using uvicorn from project root
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# Option 3: Using Python module from project root
python -m backend.api.main
```

The backend will be available at `http://localhost:8000`
API documentation: `http://localhost:8000/docs`

### Start the Frontend

```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:3000`

## Usage

1. Open `http://localhost:3000` in your browser
2. Click "New Analysis" to start a trading analysis
3. Fill in the form:
   - Ticker symbol (e.g., "SPY")
   - Analysis date
   - Select analysts
   - Configure LLM settings
4. Click "Start Analysis"
5. View real-time progress and results

## Features

- **Real-time Analysis**: Watch agents work in real-time via WebSocket
- **Agent Progress**: See status of all agents (Analyst Team, Research Team, etc.)
- **Report Viewer**: View generated reports with collapsible sections
- **History**: Browse and view previous analyses
- **Configuration**: Save and load analysis configurations

## API Endpoints

- `POST /api/analysis/start` - Start new analysis
- `GET /api/analysis/{id}/status` - Get analysis status
- `GET /api/analysis/{id}/results` - Get analysis results
- `WS /ws/analysis/{id}/stream` - WebSocket stream for updates
- `GET /api/history` - List historical analyses
- `GET /api/history/{ticker}/{date}` - Get specific historical analysis
- `GET /api/config/presets` - List configuration presets
- `POST /api/config/save` - Save configuration preset

## Development

### Backend Development

The backend uses FastAPI with automatic reload. Changes to Python files will trigger a reload.

### Frontend Development

The frontend uses Next.js with hot module replacement. Changes to React components will update automatically.

## Troubleshooting

1. **Backend won't start**: Check that all dependencies are installed and environment variables are set
2. **Frontend can't connect**: Verify `NEXT_PUBLIC_API_URL` matches the backend URL
3. **WebSocket connection fails**: Ensure the backend is running and CORS is configured correctly
4. **Analysis fails**: Check API keys in `.env` file and verify they're valid

## Notes

- The CLI (`cli/main.py`) continues to work independently
- All existing TradingAgents code remains unchanged
- Results are saved to the `results/` directory (same as CLI)

