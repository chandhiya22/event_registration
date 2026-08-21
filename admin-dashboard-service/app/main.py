from fastapi import FastAPI

app = FastAPI()

# Add a simple health check at the root
@app.get("/")
def health_check():
    return {"status": "ok"}