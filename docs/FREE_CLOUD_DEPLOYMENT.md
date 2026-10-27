# Free Cloud Deployment Guide

This guide explains how to deploy the **Smart AI Hiring Assistant (SAIHA)** to production for **$0.00 (completely free, no credit card required)** using:
* **Database:** [Neon PostgreSQL](https://neon.tech) (Serverless Postgres free tier, 0.5 GB storage)
* **Backend:** [Render](https://render.com) (Python 3 Web Service free tier)
* **Frontend:** [Render](https://render.com) (Static Site free tier)
* **Version Control:** [GitHub](https://github.com)

```mermaid
flowchart LR
    subgraph Client
        Browser[User Web Browser]
    end

    subgraph Render_Cloud [Render.com Free Tier]
        Frontend[Render Static Site\nReact + Vite SPA\nhttps://saiha-frontend.onrender.com]
        Backend[Render Web Service\nFastAPI Python Service\nhttps://saiha-backend.onrender.com]
    end

    subgraph Neon_Cloud [Neon.tech Free Tier]
        DB[(Serverless PostgreSQL 16\nSSL encrypted)]
    end

    Browser -->|1. Loads UI| Frontend
    Browser -->|2. Direct API calls with JWT| Backend
    Backend -->|3. SQL queries via psycopg 3| DB
```

---

## 1. System Requirements & Architecture Summary

| Component | Target Platform | Root Directory | Build Command | Start Command | Free Tier Constraints |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Database** | Neon.tech | N/A | Automated by Alembic | Managed Serverless | 0.5 GB storage, auto-suspend |
| **Backend** | Render Web Service | `backend` | `pip install -r requirements.txt` | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` | 512 MB RAM, spins down on idle |
| **Frontend** | Render Static Site | `frontend` | `npm install && npm run build` | Static files from `dist` | 100 GB bandwidth/month |

> [!IMPORTANT]
> **Free Tier Memory Limit (512 MB RAM):**
> PyTorch and heavy embedding weights (`requirements-ml.txt`) consume over 1.5 GB of RAM and will exceed Render's free tier memory limit.
> For free cloud deployment, set `INSTALL_ML=false`, `ENABLE_DENSE=false`, and `ENABLE_RERANK=false`.
> The system operates in its multi-agent BM25 screening mode (Experiments B, D, G, H, I, J, rubric drafting, and evidence verification all remain fully functional).

---

## 2. Step-by-Step Deployment Instructions

### Step 1: Create Free PostgreSQL on Neon.tech
1. Sign up for free at [https://neon.tech](https://neon.tech) (using GitHub or Google account).
2. Click **Create Project**:
   - Name: `saiha-db`
   - Postgres version: `16` (default)
   - Region: Choose the region closest to you or Render (e.g., `US East (Ohio)` or `Frankfurt`).
3. Once created, copy the **Connection string**:
   ```
   postgresql://user:password@ep-xyz.region.aws.neon.tech/neondb?sslmode=require
   ```
4. **Driver Prefix Note:** SQLAlchemy with `psycopg 3` uses the `postgresql+psycopg://` driver prefix.
   Format your connection string as:
   ```
   postgresql+psycopg://user:password@ep-xyz.region.aws.neon.tech/neondb?sslmode=require
   ```
   *(Note: The codebase includes automatic normalization, so both prefixes work seamlessly).*

---

### Step 2: Push Repository to GitHub
1. Open PowerShell and navigate to the project directory:
   ```powershell
   cd d:\smart-ai-hiring-assistant\smart-ai-hiring-assistant
   git init
   git add .
   git commit -m "feat: prepare project for free cloud deployment"
   ```
2. Create a new repository on your GitHub account (e.g., `smart-ai-hiring-assistant`).
3. Push your code:
   ```powershell
   git remote add origin https://github.com/<your-username>/smart-ai-hiring-assistant.git
   git branch -M main
   git push -u origin main
   ```

---

### Step 3: Deploy Backend (Render Web Service)
1. Log in to [https://render.com](https://render.com).
2. Click **New +** > **Web Service**.
3. Connect your GitHub repository.
4. Configure the service settings:
   * **Name:** `saiha-backend` (or your chosen name)
   * **Region:** Same region as your Neon database (e.g., `Oregon` or `Frankfurt`)
   * **Root Directory:** `backend`
   * **Environment:** `Python 3`
   * **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   * **Start Command:**
     ```bash
     alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   * **Instance Type:** `Free` (512 MB RAM, 0.1 CPU)
5. Under **Environment Variables**, add the following:

   | Key | Value | Description |
   | :--- | :--- | :--- |
   | `DATABASE_URL` | `postgresql+psycopg://user:password@ep-...neon.tech/neondb?sslmode=require` | Your Neon database connection string |
   | `JWT_SECRET` | *(Generate a random 32+ char token)* | Cryptographic key for JWT tokens |
   | `CORS_ORIGINS` | `http://localhost:5173` *(update in Step 5)* | Allowed origin for frontend requests |
   | `INSTALL_ML` | `false` | Keeps memory usage under 250 MB |
   | `ENABLE_DENSE` | `false` | Disables in-memory vector weights |
   | `ENABLE_RERANK` | `false` | Disables in-memory cross-encoder |
   | `STORAGE_DIR` | `/tmp/saiha_files` | Ephemeral storage for uploads |
   | `DATASET_DIR` | `/tmp/saiha_datasets` | Ephemeral storage for datasets |
   | `LLM_PROVIDER` | `none` | Deterministic evaluator mode (or set `openai`/`anthropic` if you have keys) |

6. Click **Create Web Service**.
7. Wait 2–3 minutes for Render to build packages and run Alembic migrations.
   Once deployed, note your backend URL: e.g., `https://saiha-backend.onrender.com`.

---

### Step 4: Deploy Frontend (Render Static Site)
1. In the Render Dashboard, click **New +** > **Static Site**.
2. Select the same GitHub repository.
3. Configure the settings:
   * **Name:** `saiha-frontend`
   * **Root Directory:** `frontend`
   * **Build Command:**
     ```bash
     npm install && npm run build
     ```
   * **Publish Directory:** `dist`
4. Under **Environment Variables**, add:
   * **Key:** `VITE_API_URL`
   * **Value:** `https://saiha-backend.onrender.com` *(your backend URL from Step 3 without trailing slash)*
5. **Critical for Single Page Apps (SPA Routing):**
   * Go to the **Redirects / Rewrites** tab on the left menu.
   * Click **Add Rule**:
     * **Source:** `/*`
     * **Destination:** `/index.html`
     * **Action:** `Rewrite`
   * *(This prevents 404 errors when refreshing pages like `/jobs` or `/ranking`).*
6. Click **Create Static Site**.
   Once built, note your frontend URL: e.g., `https://saiha-frontend.onrender.com`.

---

### Step 5: Connect Frontend and Backend (Update CORS)
1. Return to your **`saiha-backend`** Web Service on Render.
2. Go to **Environment Variables**.
3. Update `CORS_ORIGINS`:
   * **Key:** `CORS_ORIGINS`
   * **Value:** `https://saiha-frontend.onrender.com` *(your actual frontend URL from Step 4)*
4. Click **Save Changes**. Render will automatically redeploy the backend with the updated CORS policy.

---

### Step 6: Initial Application Setup & Verification
1. Open your frontend URL in your browser: `https://saiha-frontend.onrender.com`.
2. Because the database is brand new, the system will direct you to the **Bootstrap Setup Screen**.
3. Create your first administrator account:
   * Email: `admin@youruniversity.edu`
   * Password: `your-secure-password`
   * Workspace Name: `SAIHA Production`
4. Log in to access the dashboard.
5. Verify the following:
   * **3D Agent Visualization:** Renders smoothly on the Overview page.
   * **Job Creation & Rubric:** Navigate to **Job Descriptions**, create a job, click **Analyze**, and approve the draft rubric.
   * **Evidence Explorer:** Upload a resume and verify that citations and quotes are verified accurately against the document text.
   * **System Status:** In **Settings**, inspect system status and verify that database is reported as connected.

---

## 3. Troubleshooting & Free Tier FAQs

### Why does the initial page load take 30–50 seconds?
Render free web services "spin down" after 15 minutes of inactivity. When a request arrives, Render automatically spins up the container (cold start). Once awake, requests respond normally within milliseconds.

### Are files and datasets persisted?
* **Database Records:** All resumes (full text, parsed pages, metadata, extraction), jobs, rubrics, evaluation runs, and audit logs are stored permanently in Neon PostgreSQL.
* **Uploaded PDF/DOCX binaries:** Temporary upload files are stored in `/tmp/saiha_files`. Extracted text is permanently kept in the database.

### What if I want to run LLM rubric drafting?
Add your `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to the Render backend environment variables, and set `LLM_PROVIDER=openai` or `LLM_PROVIDER=anthropic`.
