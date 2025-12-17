import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from openai import OpenAI
from supabase import create_client, Client

from database import DatabaseManager
from session_processor import SessionProcessor

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# --------------------------------------------------
# Global instances
# --------------------------------------------------
supabase: Optional[Client] = None
db_manager: Optional[DatabaseManager] = None
session_processor: Optional[SessionProcessor] = None
openai_client: Optional[OpenAI] = None


# --------------------------------------------------
# Lifespan (startup / shutdown)
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global supabase, db_manager, session_processor, openai_client

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    db_manager = DatabaseManager(supabase)
    session_processor = SessionProcessor(supabase)
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    print("✓ Services initialized")
    yield
    print("✓ Shutting down services")


# --------------------------------------------------
# FastAPI app
# --------------------------------------------------
app = FastAPI(
    title="Realtime AI Backend",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Simple tool execution (FREE-safe)
# --------------------------------------------------
async def execute_tool(tool_name: str, tool_input: Dict) -> Dict:
    if tool_name == "get_weather":
        return {
            "location": tool_input.get("location", "Unknown"),
            "temperature": 28,
            "unit": "celsius",
            "conditions": "Partly Cloudy"
        }

    if tool_name == "search_database":
        query = tool_input.get("query", "")
        return {
            "results": [
                {"title": f"Result for {query}", "score": 0.95}
            ]
        }

    return {"error": "Unknown tool"}


# --------------------------------------------------
# Health endpoints
# --------------------------------------------------
@app.get("/")
async def root():
    return {"status": "online", "service": "Realtime AI Backend"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


# --------------------------------------------------
# WebSocket endpoint
# --------------------------------------------------
@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    user_id = f"user_{session_id[-6:]}"
    conversation_history = []

    await db_manager.create_session(session_id, user_id)
    await db_manager.log_event(session_id, "session_start", {"user_id": user_id})

    await websocket.send_json({
        "type": "session_start",
        "session_id": session_id,
        "start_time": datetime.utcnow().isoformat()
    })

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg["type"] != "user_message":
                continue

            user_text = msg["content"]

            await db_manager.log_event(
                session_id, "user_message", {"content": user_text}
            )

            conversation_history.append({
                "role": "user",
                "content": user_text
            })

            # --------------------------------------
            # SIMPLE TOOL DETECTION (FREE)
            # --------------------------------------
            if "weather" in user_text.lower():
                tool_result = await execute_tool(
                    "get_weather", {"location": "Bangalore"}
                )

                await websocket.send_json({
                    "type": "function_result",
                    "function_name": "get_weather",
                    "result": tool_result
                })

                conversation_history.append({
                    "role": "system",
                    "content": f"Weather data: {tool_result}"
                })

            # --------------------------------------
            # OpenAI streaming response
            # --------------------------------------
            stream = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=conversation_history,
                stream=True
            )

            full_response = ""

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_response += token

                    await websocket.send_json({
                        "type": "token",
                        "content": token
                    })

            await websocket.send_json({"type": "response_complete"})

            conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            await db_manager.log_event(
                session_id,
                "assistant_response",
                {"content": full_response}
            )

    except WebSocketDisconnect:
        print("Client disconnected")

    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })

    finally:
        await db_manager.end_session(session_id)
        await db_manager.log_event(session_id, "session_end", {})
        asyncio.create_task(session_processor.process_session(session_id))


# --------------------------------------------------
# Run locally
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
