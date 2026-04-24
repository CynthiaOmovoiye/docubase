# Backend quick connect (CloudFront UI → API)

Fastest way to **plug a real API** into the static CloudFront site: expose whatever already runs on **port 8000** (usually `docker compose up backend`) as **HTTPS**, point the Vite build at it, and allow **CORS** for your CloudFront origin.

**Time:** about 5–15 minutes.

---

## Path A — Tunnel (fastest, no new AWS servers)

### 1. Install a tunnel CLI (pick one)

- **Cloudflare (recommended):** `brew install cloudflared`
- **ngrok:** [ngrok download](https://ngrok.com/download)

### 2. Run the API locally

From repo root (same as always):

```bash
docker compose up -d db redis
docker compose up backend
```

Wait until `http://127.0.0.1:8000/api/docs` loads in a browser.

### 3. Start the tunnel

```bash
chmod +x scripts/public-api-tunnel.sh
./scripts/public-api-tunnel.sh
```

Copy the **`https://…`** origin (no path). Quick tunnels get a **new hostname each time**; when it changes, update GitHub and redeploy the frontend.

### 4. CORS on the backend

The browser **Origin** is your **CloudFront** URL (not the tunnel). In `.env` for the running backend:

```bash
CORS_ALLOWED_ORIGINS=https://YOUR_ID.cloudfront.net
```

Restart the backend container after editing `.env` (or `docker compose up -d --force-recreate backend`).

### 5. Point the built frontend at the API

**GitHub Actions:** Settings → Secrets and variables → **Actions** → **Variables** → `DOCBASE_VITE_API_URL` = tunnel **origin** only (example: `https://random-words.trycloudflare.com`, no `/api/v1`).

Re-run **Deploy docbase** for `dev`.

**Local deploy script:**

```bash
export DOCBASE_VITE_API_URL='https://your-tunnel-origin'
./scripts/deploy.sh dev
```

### 6. Smoke test

Open the CloudFront site, try register/login. If the browser shows CORS errors, double-check `CORS_ALLOWED_ORIGINS` matches the CloudFront URL **exactly** (scheme + host, no trailing slash unless you know you need it).

### Limits

- Your laptop (or wherever the tunnel runs) must stay up.
- Quick tunnel URLs rotate; production should use a **stable host** (Path B or ECS).

---

## Path B — Small AWS server (stable URL, still simple)

1. **Lightsail** or **EC2** (Ubuntu): open inbound **8000** (or 443 behind Caddy).
2. Install Docker, clone docubase, copy `.env`, run `docker compose up -d`.
3. Attach a **static IP** (Lightsail) or Elastic IP (EC2).
4. Use **`http://STATIC_IP:8000`** only for testing; for HTTPS put **Caddy** or **nginx + certbot** in front, or terminate TLS on a load balancer.
5. Set **`DOCBASE_VITE_API_URL`** to `https://api.yourdomain.com` (or `https://IP` if you accept browser warnings for dev only — not ideal).
6. **`CORS_ALLOWED_ORIGINS`** = CloudFront URL as in Path A.

---

## Related

- [DEPLOY_SETUP_GUIDE.md](./DEPLOY_SETUP_GUIDE.md) — frontend + `DOCBASE_VITE_API_URL`
- `frontend/src/lib/api.ts` — how `VITE_API_URL` becomes `/api/v1` calls
- `backend/app/core/config.py` — `cors_allowed_origins` / `frontend_url`
