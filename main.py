import os
import pandas as pd
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import JSONResponse
import uvicorn

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = os.getenv("API_KEY", "change-me-in-production")
CSV_PATH = os.getenv("CSV_PATH", "loads_sample.csv")

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# ── Load data at startup ────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH, sep=";")
df["load_id"] = df["load_id"].astype(str).str.zfill(5)   # normalise to "00001"
df = df.where(pd.notnull(df), None)                        # NaN → None (JSON null)

# ── Auth dependency ─────────────────────────────────────────────────────────
async def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key")
    return key

# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Loads API",
    description="Webhook GET endpoint to retrieve load details by load_id",
    version="1.0.0",
)


@app.get("/health")
def health():
    """Health check – no auth required."""
    return {"status": "ok", "total_loads": len(df)}


@app.get("/load/{load_id}", dependencies=[Depends(verify_api_key)])
def get_load(load_id: str):
    """
    Return all fields for a single load.

    - **load_id**: 1-5 digit numeric ID (e.g. `1`, `00001`)
    - Header **x-api-key** is required.
    """
    # Normalise incoming ID (accept "1" or "00001")
    normalised = load_id.strip().zfill(5)
    match = df[df["load_id"] == normalised]

    if match.empty:
        raise HTTPException(status_code=404, detail=f"Load '{load_id}' not found")

    record = match.iloc[0].to_dict()
    return JSONResponse(content=record)


@app.get("/loads", dependencies=[Depends(verify_api_key)])
def list_loads(skip: int = 0, limit: int = 50):
    """
    Paginated list of all loads.

    - **skip**: offset (default 0)
    - **limit**: page size, max 200 (default 50)
    """
    limit = min(limit, 200)
    page = df.iloc[skip : skip + limit].to_dict(orient="records")
    return {
        "total": len(df),
        "skip": skip,
        "limit": limit,
        "data": page,
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
