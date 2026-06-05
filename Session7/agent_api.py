"""Simple HTTP API wrapper for the agent."""
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent import run
from services.decision_service import Decision
from services.memory_service import Memory
from services.perception_service import Perception
from services.artifact_service import ArtifactStore
from services.action_service import Action
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
  

@app.post("/query")
async def query_agent(request: QueryRequest) -> QueryResponse:
    """Query the agent and get a response."""
    answer = await run(request.query)
    return QueryResponse(answer=answer)

if __name__ == "__main__":
    # Initialize global variables needed by agent.py
    import agent
    agent.MAX_ITERATIONS = 10
    agent.memory = Memory()
    agent.perception = Perception()
    agent.artifacts = ArtifactStore()
    agent.decision = Decision()
    agent.action = Action()

    uvicorn.run(app, host="127.0.0.1", port=8002)
