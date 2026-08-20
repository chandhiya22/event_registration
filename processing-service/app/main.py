"""
processing-service
Internal service, invoked by registration-api via Dapr.
Validates the registration (using a rule pulled from Key Vault),
writes status via Dapr state management, and publishes the result
to Service Bus via Dapr pub/sub.
"""
import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="Confer - Processing Service")

DAPR_HTTP_PORT = os.environ.get("DAPR_HTTP_PORT", "3500")
STATE_STORE_NAME = os.environ.get("DAPR_STATE_STORE", "statestore")
PUBSUB_NAME = os.environ.get("DAPR_PUBSUB", "pubsub")
PUBSUB_TOPIC = os.environ.get("DAPR_PUBSUB_TOPIC", "registration-events")
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")  # e.g. https://kv-confer.vault.azure.net


def get_validation_key() -> str:
    """Pull the mock payment-validation key from Key Vault via managed identity."""
    if not KEY_VAULT_URL:
        return "local-dev-key"
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
    client = SecretClient(vault_url=KEY_VAULT_URL, credential=DefaultAzureCredential())
    return client.get_secret("PaymentValidationKey").value


@app.get("/health")
def health():
    return {"status": "ok", "service": "processing-service"}


@app.post("/process")
async def process(request: Request):
    payload = await request.json()
    registration_id = payload["registration_id"]

    # 1. "Validate" — in a real system this might check a payment reference
    #    against a payment gateway using the key from Key Vault.
    validation_key = get_validation_key()
    is_valid = bool(payload.get("name")) and bool(payload.get("email")) and validation_key is not None
    status = "validated" if is_valid else "rejected"

    # 2. Write status via Dapr state management (backed by Blob Storage)
    state_url = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/state/{STATE_STORE_NAME}"
    state_body = [{"key": registration_id, "value": {**payload, "status": status}}]
    async with httpx.AsyncClient() as client:
        await client.post(state_url, json=state_body, timeout=5.0)

        # 3. Publish result to Service Bus topic via Dapr pub/sub
        publish_url = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/publish/{PUBSUB_NAME}/{PUBSUB_TOPIC}"
        event = {
            "registration_id": registration_id,
            "name": payload.get("name"),
            "email": payload.get("email"),
            "status": status,
        }
        await client.post(publish_url, json=event, timeout=5.0)

    return {"registration_id": registration_id, "status": status}
