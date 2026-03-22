from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from agent_os.backend.routes import portfolios, runs, websocket
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_os")

app = FastAPI(title="AgentOS API")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# --- Include Routes ---
app.include_router(portfolios.router)
app.include_router(runs.router)
app.include_router(websocket.router)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AgentOS API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8088)
