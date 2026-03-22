from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from agent_os.backend.routes import portfolios, runs, websocket

app = FastAPI(title="AgentOS API")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to your React app's URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routes ---
app.include_router(portfolios.router)
app.include_router(runs.router)
app.include_router(websocket.router)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "AgentOS API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
