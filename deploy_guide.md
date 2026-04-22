# Deploy Guide — Multi-Agent Research System Backend

## Option A — Render.com [সবচেয়ে সহজ, কোনো CLI দরকার নেই]

### Step 1 — GitHub এ code push করো

```powershell
# MultiAgentPart folder এ যাও
cd d:\Anthic\MultiagenSytemAllPart\MultiAgentPart

# Git init (যদি না থাকে)
git init
git add .
git commit -m "production ready backend"

# GitHub এ নতুন repo তৈরি করো → তারপর:
git remote add origin https://github.com/YOUR_USERNAME/multi-agent-research.git
git push -u origin main
```

### Step 2 — Render.com এ deploy

1. **render.com** → Sign up (GitHub দিয়ে)
2. Dashboard → **"New +"** → **Web Service**
3. GitHub repo connect করো
4. Settings:
   ```
   Name:         multi-agent-research
   Root Dir:     (খালি রাখো)
   Runtime:      Python 3
   Build Cmd:    pip install -r requirements.txt
   Start Cmd:    uvicorn api.server:app --host 0.0.0.0 --port $PORT
   ```
5. **Environment Variables** যোগ করো:
   ```
   MISTRALAI_API_KEY      = PLRPRiuwy5f7eEB49ZenNd5jDuncblPL
   TAVILY_API_KEY         = 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
   QDRANT_URL             = https://6b7acebb-f152-4760-b99d-73610ecaa471.sa-east-1-0.aws.cloud.qdrant.io:6333
   QDRANT_API_KEY         = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   DATABASE_URL_POOLER    = (Supabase dashboard থেকে নাও)
   UPSTASH_REDIS_URL      = https://light-vulture-80588.upstash.io
   UPSTASH_REDIS_TOKEN    = (Upstash dashboard থেকে নাও)
   ```
6. **"Create Web Service"** click → Deploy!

> Render free tier: app idle হলে spin down হয় (cold start ~30s). Paid ($7/mo) হলে always on।

---

## Option B — Google Cloud Run [Production Grade]

### Step 1 — gcloud CLI install

1. https://cloud.google.com/sdk/docs/install → Windows installer
2. Install করে:
   ```powershell
   gcloud auth login
   gcloud auth application-default login
   ```

### Step 2 — Deploy

```powershell
cd d:\Anthic\MultiagenSytemAllPart\MultiAgentPart

gcloud run deploy multi-agent-research `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --timeout 300 `
  --memory 1Gi `
  --set-env-vars "MISTRALAI_API_KEY=PLRPRiuwy5f7eEB49ZenNd5jDuncblPL,TAVILY_API_KEY=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,QDRANT_URL=https://6b7acebb-f152-4760-b99d-73610ecaa471.sa-east-1-0.aws.cloud.qdrant.io:6333,QDRANT_API_KEY=YOUR_KEY,UPSTASH_REDIS_URL=https://light-vulture-80588.upstash.io,UPSTASH_REDIS_TOKEN=YOUR_TOKEN"
```

---

## Option C — Azure Container Apps [GitHub Student Credit ব্যবহার করে]

যেহেতু আপনার কাছে $100 ক্রেডিট আছে, এটিই আপনার জন্য সেরা অপশন।

### Step 1 — Azure CLI install
1. [Azure CLI for Windows](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows) ইন্সটল করুন।
2. টার্মিনালে লগইন করুন:
   ```powershell
   az login
   ```

### Step 2 — Deploy Command
নিচের কমান্ডটি কপি করে আপনার PowerShell-এ রান করুন (এটি অটোমেটিক Resource Group এবং Environment তৈরি করে নিবে):

```powershell
cd d:\Anthic\MultiagenSytemAllPart\MultiAgentPart

az containerapp up `
  --name multi-agent-research `
  --resource-group MultiAgentRG `
  --location eastus `
  --environment multi-agent-env `
  --source . `
  --ingress external `
  --target-port 8000 `
  --env-vars `
    "MISTRALAI_API_KEY=PLRPRiuwy5f7eEB49ZenNd5jDuncblPL" `
    "TAVILY_API_KEY=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" `
    "QDRANT_URL=https://6b7acebb-f152-4760-b99d-73610ecaa471.sa-east-1-0.aws.cloud.qdrant.io:6333" `
    "QDRANT_API_KEY=YOUR_KEY" `
    "UPSTASH_REDIS_URL=https://light-vulture-80588.upstash.io" `
    "UPSTASH_REDIS_TOKEN=YOUR_TOKEN"
```

---

## Deploy এর পর Test

```bash
curl https://YOUR_URL/health
curl -X POST https://YOUR_URL/research -H "Content-Type: application/json" -d '{"topic":"AI 2024"}'
curl https://YOUR_URL/job/JOB_ID
```

---

## Summary

| | Render.com | Cloud Run | Azure Container Apps |
|--|--|--|--|
| সহজতা | ★★★★★ | ★★★ | ★★★★ |
| খরচ | ফ্রি (সীমিত) | ফ্রি (সীমিত) | **ফ্রি ($100 ক্রেডিট দিয়ে)** |
| Setup | ১০ মিনিট | ৩০ মিনিট | ২০ মিনিট |
| স্ট্যাটাস | Spin down হয় | Serverless | **Always On সম্ভব** |

**আপনার জন্য রিকমেন্ডেশন:** Azure Container Apps ব্যবহার করুন।
