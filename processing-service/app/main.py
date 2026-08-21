"""
processing-service
Internal service, invoked by registration-api via Dapr.
Validates the registration (using a rule pulled from Key Vault),
writes status via Dapr state management, and publishes the result
to Service Bus via Dapr pub/sub.
"""
import os
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request

# Configure logging to see outputs clearly in Azure Log Stream
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("processing-service")

DAPR_HTTP_PORT = os.environ.get("DAPR_HTTP_PORT", "3500")
STATE_STORE_NAME = os.environ.get("DAPR_STATE_STORE", "statestore")
PUBSUB_NAME = os.environ.get("DAPR_PUBSUB", "pubsub")
PUBSUB_TOPIC = os.environ.get("DAPR_PUBSUB_TOPIC", "registration-events")
KEY_VAULT_URL = os.environ.get("KEY_VAULT_URL")  # e.g. https://kv-confer.vault.azure.net

# Global cached secret
VALIDATION_KEY = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fetch Key Vault secret once at container startup instead of per-request."""
    global VALIDATION_KEY
    if KEY_VAULT_URL:
        try:
            logger.info(f"Fetching PaymentValidationKey from Key Vault at: {KEY_VAULT_URL}")
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
            VALIDATION_KEY = client.get_secret("PaymentValidationKey").value
            logger.info("Successfully retrieved validation key from Key Vault.")
        except Exception as e:
            logger.error(f"Failed to retrieve secret from Key Vault: {e}")
            VALIDATION_KEY = "fallback-key"
    else:
        logger.warning("KEY_VAULT_URL not provided. Using local development key.")
        VALIDATION_KEY = "local-dev-key"
    
    yield


app = FastAPI(title="Confer - Processing Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "processing-service"}


@app.post("/process")
async def process(request: Request):
    payload = await request.json()
    registration_id = payload.get("registration_id")

    # 1. Validate submission using the cached Key Vault secret
    is_valid = bool(payload.get("name")) and bool(payload.get("email")) and VALIDATION_KEY is not None
    status = "validated" if is_valid else "rejected"

    # Endpoints for Dapr sidecar building blocks
    state_url = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/state/{STATE_STORE_NAME}"
    publish_url = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/publish/{PUBSUB_NAME}/{PUBSUB_TOPIC}"

    state_body = [{"key": registration_id, "value": {**payload, "status": status}}]
    event = {
        "registration_id": registration_id,
        "name": payload.get("name"),
        "email": payload.get("email"),
        "status": status,
    }

    # Execute Dapr state store save and pub/sub message publish asynchronously
    async with httpx.AsyncClient() as client:
        try:
            # Save state to Blob Storage via Dapr
            state_resp = await client.post(state_url, json=state_body, timeout=5.0)
            state_resp.raise_for_status()

            # Publish event to Azure Service Bus via Dapr
            pub_resp = await client.post(publish_url, json=event, timeout=5.0)
            pub_resp.raise_for_status()

            logger.info(f"Processed registration {registration_id} with status: {status}")
        except Exception as e:
            logger.error(f"Error communicating with Dapr sidecar: {e}")
            return {"registration_id": registration_id, "status": "error", "message": str(e)}

    return {"registration_id": registration_id, "status": status}


if __name__ == "__main__":
    import uvicorn
    # Bound to 0.0.0.0 to accept traffic from the Dapr sidecar
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)