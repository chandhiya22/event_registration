"""
registration-api
Public-facing service. Accepts a registration (name, email, file upload),
stores the file in Blob Storage, calls processing-service via Dapr
service invocation, and returns immediately (async pattern).
"""
import os
import uuid
import httpx
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from azure.storage.blob import BlobServiceClient, ContentSettings

app = FastAPI(title="Confer - Registration API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten before real client use
    allow_methods=["*"],
    allow_headers=["*"],
)

DAPR_HTTP_PORT = os.environ.get("DAPR_HTTP_PORT", "3500")
STORAGE_ACCOUNT_URL = os.environ.get("STORAGE_ACCOUNT_URL")  # e.g. https://stconfer01.blob.core.windows.net
CONTAINER_NAME = os.environ.get("BLOB_CONTAINER", "documents")

# When deployed on Azure with managed identity, use DefaultAzureCredential instead of a key.
def get_blob_service_client():
    from azure.identity import DefaultAzureCredential
    return BlobServiceClient(account_url=STORAGE_ACCOUNT_URL, credential=DefaultAzureCredential())


@app.get("/health")
def health():
    return {"status": "ok", "service": "registration-api"}


@app.post("/register")
async def register(name: str = Form(...), email: str = Form(...), document: UploadFile = None):
    registration_id = str(uuid.uuid4())

    # 1. Upload document to Blob Storage
    blob_name = f"{registration_id}-{document.filename}"
    if STORAGE_ACCOUNT_URL:
        blob_client = get_blob_service_client().get_blob_client(container=CONTAINER_NAME, blob=blob_name)
        content = await document.read()
        blob_client.upload_blob(
            content, overwrite=True,
            content_settings=ContentSettings(content_type=document.content_type),
        )

    # 2. Invoke processing-service via Dapr service invocation (fire-and-forget style)
    invoke_url = f"http://localhost:{DAPR_HTTP_PORT}/v1.0/invoke/processing-service/method/process"
    payload = {
        "registration_id": registration_id,
        "name": name,
        "email": email,
        "document_blob": blob_name,
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(invoke_url, json=payload, timeout=5.0)
        except httpx.HTTPError as e:
            # Don't fail the registration if processing is briefly unavailable;
            # in production you'd fall back to Dapr pub/sub for guaranteed delivery.
            print(f"processing-service invoke failed: {e}")

    return {
        "registration_id": registration_id,
        "status": "received",
        "message": "Your registration is under review. You'll get an email shortly.",
    }
