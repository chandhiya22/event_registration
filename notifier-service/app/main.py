"""
notifier-service
Subscribes to the 'registration-events' topic via Dapr pub/sub.
"Sends" a confirmation/rejection email (logged here; wire SendGrid/SMTP for real).
This is the service you point KEDA at to scale on Service Bus queue depth.
"""
import os
from fastapi import FastAPI, Request

app = FastAPI(title="Confer - Notifier Service")

PUBSUB_NAME = os.environ.get("DAPR_PUBSUB", "pubsub")
TOPIC = os.environ.get("DAPR_PUBSUB_TOPIC", "registration-events")


@app.get("/health")
def health():
    return {"status": "ok", "service": "notifier-service"}


# Dapr requires a subscription declaration endpoint
@app.get("/dapr/subscribe")
def subscribe():
    return [
        {
            "pubsubname": PUBSUB_NAME,
            "topic": TOPIC,
            "route": "/events/registration",
        }
    ]


@app.post("/events/registration")
async def handle_event(request: Request):
    event = await request.json()
    data = event.get("data", event)  # Dapr wraps the payload in a CloudEvent envelope

    name = data.get("name")
    email = data.get("email")
    status = data.get("status")

    if status == "validated":
        print(f"[EMAIL] To: {email} | Subject: Registration confirmed | Hi {name}, you're in!")
    else:
        print(f"[EMAIL] To: {email} | Subject: Registration issue | Hi {name}, we couldn't validate your submission.")

    return {"status": "SUCCESS"}  # tells Dapr the message was handled (ack)
