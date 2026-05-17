# Loads API

REST API to query freight load data by `load_id`. Protected by `x-api-key` header. Dockerized and ready to deploy on Railway.

---

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | ❌ | Health check |
| GET | `/load/{load_id}` | ✅ | Get single load by ID |
| GET | `/loads?skip=0&limit=50` | ✅ | Paginated list of loads |

### Example request
```bash
curl https://your-app.railway.app/load/00001 \
  -H "x-api-key: YOUR_SECRET_KEY"
```

### Example response
```json
{
  "load_id": "00001",
  "origin": "Las Vegas, NV",
  "destination": "Portland, OR",
  "pickup_datetime": "04/06/2025 22:49",
  "delivery_datetime": "06/06/2025 22:49",
  "equipment_type": "flatbed",
  "loadboard_rate": 985,
  "notes": null,
  "weight": 32989,
  "commodity_type": "frozen produce",
  "num_of_pieces": 23,
  "miles": 344,
  "dimensions": "48ft"
}
```

---

## Local development

### Run with Docker
```bash
docker build -t loads-api .
docker run -p 8000:8000 -e API_KEY=mysecretkey loads-api
```

### Run without Docker
```bash
pip install -r requirements.txt
API_KEY=mysecretkey python main.py
```

Interactive docs available at: http://localhost:8000/docs

---

## Deploy to Railway

### Option A – GitHub (recommended)

1. Push this repo to GitHub.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repo. Railway auto-detects the `Dockerfile`.
4. Go to **Variables** and add:
   ```
   API_KEY=<your-strong-secret-key>
   ```
5. Click **Deploy**. Railway builds the Docker image and exposes a public URL.

### Option B – Railway CLI

```bash
# Install CLI
npm install -g @railway/cli

# Login
railway login

# Init project (first time)
railway init

# Set the API key secret
railway variables set API_KEY=<your-strong-secret-key>

# Deploy
railway up
```

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `change-me-in-production` | Secret key sent in `x-api-key` header |
| `PORT` | `8000` | Port the server listens on (Railway sets this automatically) |
| `CSV_PATH` | `loads_sample.csv` | Path to the data CSV (relative to `/app`) |

> ⚠️ Always set `API_KEY` to a strong random value in production.  
> Generate one with: `openssl rand -hex 32`
