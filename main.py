import os
import pandas as pd
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY      = os.getenv("API_KEY", "change-me-in-production")
CSV_PATH     = os.getenv("CSV_PATH", "loads_sample.csv")
DATABASE_URL = os.getenv("DATABASE_URL")  # Optional — set after adding Postgres in Railway

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

# ── CSV data ──────────────────────────────────────────────────────────────────
df = pd.read_csv(CSV_PATH, sep=";")
df["load_id"] = df["load_id"].astype(str).str.zfill(5)
df = df.where(pd.notnull(df), None)

# ── DB helpers ────────────────────────────────────────────────────────────────
def db_available():
    return DATABASE_URL is not None

@contextmanager
def get_conn():
    if not db_available():
        raise HTTPException(status_code=503, detail="Database not configured. Add PostgreSQL in Railway and set DATABASE_URL.")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Create tables if DB is available. Safe to skip if not."""
    if not db_available():
        print("⚠️  DATABASE_URL not set — webhook/dashboard endpoints disabled until Postgres is added.")
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS webhook_calls (
                        id          SERIAL PRIMARY KEY,
                        received_at TIMESTAMPTZ DEFAULT NOW(),
                        mc_number   TEXT,
                        response    TEXT,
                        transcript  TEXT,
                        load_id     TEXT,
                        origin      TEXT,
                        destination TEXT,
                        pickup      TEXT,
                        delivery    TEXT,
                        equipment   TEXT,
                        rate        TEXT,
                        notes       TEXT,
                        weight      TEXT,
                        type        TEXT,
                        num_pieces  TEXT,
                        miles       TEXT,
                        dim         TEXT,
                        timedate    TEXT,
                        phonenumber TEXT
                    );
                """)
                # Migrate existing tables — safe to run repeatedly
                for col in ["timedate", "phonenumber"]:
                    cur.execute(f"""
                        ALTER TABLE webhook_calls
                        ADD COLUMN IF NOT EXISTS {col} TEXT;
                    """)
        print("✅ Database initialised.")
    except Exception as e:
        print(f"⚠️  DB init failed: {e}")

init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
async def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing x-api-key")
    return key

# ── Webhook schema ────────────────────────────────────────────────────────────
class WebhookPayload(BaseModel):
    mc_number:   Optional[str] = None
    response:    Optional[str] = None
    transcript:  Optional[str] = None
    load_id:     Optional[str] = None
    origin:      Optional[str] = None
    destination: Optional[str] = None
    pickup:      Optional[str] = None
    delivery:    Optional[str] = None
    equipment:   Optional[str] = None
    rate:        Optional[str] = None
    notes:       Optional[str] = None
    weight:      Optional[str] = None
    type:        Optional[str] = None
    num_pieces:  Optional[str] = None
    miles:       Optional[str] = None
    dim:         Optional[str] = None
    timedate:    Optional[str] = None
    phonenumber: Optional[str] = None

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Loads API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Existing endpoints ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "total_loads": len(df),
        "database": "connected" if db_available() else "not configured"
    }

@app.get("/load/{load_id}", dependencies=[Depends(verify_api_key)])
def get_load(load_id: str):
    try:
        normalised = str(int(load_id.strip())).zfill(5)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"load_id '{load_id}' must be numeric")
    match = df[df["load_id"] == normalised]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Load '{load_id}' not found")
    return JSONResponse(content=match.iloc[0].to_dict())

@app.get("/loads", dependencies=[Depends(verify_api_key)])
def list_loads(skip: int = 0, limit: int = 50):
    limit = min(limit, 200)
    return {"total": len(df), "skip": skip, "limit": limit,
            "data": df.iloc[skip:skip+limit].to_dict(orient="records")}

# ── Webhook receiver ──────────────────────────────────────────────────────────
@app.post("/webhook", dependencies=[Depends(verify_api_key)])
def receive_webhook(payload: WebhookPayload):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO webhook_calls
                    (mc_number,response,transcript,load_id,origin,destination,
                     pickup,delivery,equipment,rate,notes,weight,type,num_pieces,miles,dim,
                     timedate,phonenumber)
                VALUES
                    (%(mc_number)s,%(response)s,%(transcript)s,%(load_id)s,%(origin)s,
                     %(destination)s,%(pickup)s,%(delivery)s,%(equipment)s,%(rate)s,
                     %(notes)s,%(weight)s,%(type)s,%(num_pieces)s,%(miles)s,%(dim)s,
                     %(timedate)s,%(phonenumber)s)
                RETURNING id, received_at;
            """, payload.model_dump())
            row = cur.fetchone()
    return {"ok": True, "id": row[0], "received_at": row[1].isoformat()}

# ── Dashboard endpoints ───────────────────────────────────────────────────────
@app.get("/dashboard/calls", dependencies=[Depends(verify_api_key)])
def dashboard_calls():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM webhook_calls ORDER BY received_at DESC;")
            rows = cur.fetchall()
    return {"total": len(rows), "data": [dict(r) for r in rows]}

@app.get("/dashboard/stats", dependencies=[Depends(verify_api_key)])
def dashboard_stats():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS total FROM webhook_calls;")
            total = cur.fetchone()["total"]
            cur.execute("SELECT response, COUNT(*) AS count FROM webhook_calls GROUP BY response ORDER BY count DESC;")
            by_response = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT equipment, COUNT(*) AS count FROM webhook_calls GROUP BY equipment ORDER BY count DESC;")
            by_equipment = [dict(r) for r in cur.fetchall()]
            cur.execute("""
                SELECT AVG(rate::numeric) AS avg_rate, MAX(rate::numeric) AS max_rate,
                       MIN(rate::numeric) AS min_rate, AVG(miles::numeric) AS avg_miles,
                       AVG(weight::numeric) AS avg_weight
                FROM webhook_calls WHERE rate ~ '^[0-9]+$';
            """)
            numeric = dict(cur.fetchone())
    return {
        "total_calls": total,
        "by_response": by_response,
        "by_equipment": by_equipment,
        "numeric": {k: float(v) if v else 0 for k, v in numeric.items()},
    }

@app.delete("/dashboard/calls", dependencies=[Depends(verify_api_key)])
def clear_calls():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM webhook_calls;")
    return {"ok": True, "message": "All calls deleted"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
