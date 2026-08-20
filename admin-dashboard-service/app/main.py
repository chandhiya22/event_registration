"""
admin-dashboard-service
Subscribes to the same 'registration-events' topic independently from
notifier-service — this is the fan-out proof. Keeps an in-memory list
for the demo (swap for real persistence / Elerve Connect DB later)
and serves it back to the organizer dashboard.
"""
import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Confer - Admin Dashboard Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PUBSUB_NAME = os.environ.get("DAPR_PUBSUB", "pubsub")
TOPIC = os.environ.get("DAPR_PUBSUB_TOPIC", "registration-events")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "dev-key")  # pull from Key Vault in real deploy

registrations = []  # demo-only in-memory store; not persisted across restarts


@app.get("/health")
def health():
    return {"status": "ok", "service": "admin-dashboard-service"}


@app.get("/dapr/subscribe")
def subscribe():
    return [{"pubsubname": PUBSUB_NAME, "topic": TOPIC, "route": "/events/registration"}]


@app.post("/events/registration")
async def handle_event(request: Request):
    event = await request.json()
    data = event.get("data", event)
    registrations.append({**data, "received_at": datetime.now(timezone.utc).isoformat()})
    return {"status": "SUCCESS"}


@app.get("/recent")
def recent(x_api_key: str = Header(default=None)):
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return {"count": len(registrations), "registrations": list(reversed(registrations))[:50]}
