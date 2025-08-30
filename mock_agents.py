# mock_agents.py - Super simple mock agent server
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Mock Agents")

@app.post("/route")  # For Axis agent
async def axis_route(payload: dict):
    return {
        "status": "success", 
        "agent": "Axis",
        "result": "Route processed successfully",
        "trace_id": payload.get("trace_id", "unknown")
    }

@app.post("/process")  # For M agent  
async def m_process(payload: dict):
    return {
        "status": "success",
        "agent": "M", 
        "result": "Policy check completed",
        "trace_id": payload.get("trace_id", "unknown")
    }

@app.get("/health")
async def health():
    return {"status": "ok", "agents": ["Axis", "M"]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)