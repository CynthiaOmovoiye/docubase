# docbase — Demo Prep: Complete Pipeline Guide

> **Audience:** Technical and non-technical stakeholders.
> Every section explains what something is, why we chose it over alternatives, and exactly how it works — with no assumed knowledge.
> Written from the actual code, not from memory.

---

## The Big Picture — One Sentence Per Layer

| Layer | What it does in plain English |
|---|---|
| **CI/CD** | Every time code is pushed to GitHub, a pipeline automatically tests and deploys the whole product — no manual steps |
| **Infrastructure** | The actual AWS cloud resources that run the product (servers, CDN, database, storage) |
| **Ingestion pipeline** | When a user connects a Google Drive or PDF, this pipeline reads, processes, and stores it safely |
| **Retrieval** | When a user asks a question, this finds the most relevant pieces of their documents |
| **Answering** | Passes the relevant pieces to an AI model and generates a grounded, honest response |
| **Observability** | Two systems that watch everything happening in real time — CloudWatch monitors infrastructure health, Langfuse monitors AI quality |

---

## Part 1 — Infrastructure: What's Running in AWS

### The Three Core Resources

#### 1. EC2 — The Backend Server

**What it is:** A virtual machine (think: a computer rented from Amazon) that runs our Python API and background workers.

**Why EC2 over alternatives:**
- **vs. AWS Lambda (serverless):** Lambda has a 15-minute maximum runtime and cold-start latency. Our background ingestion jobs can run for several minutes (reading a large Google Drive folder + generating embeddings). EC2 has no time limit and no cold starts.
- **vs. AWS ECS/EKS (containers as a service):** These add orchestration complexity that's unnecessary for a single-server early-stage product. We run Docker Compose directly on EC2, which is simpler to reason about and debug.
- **vs. Fargate:** Same problem — per-container billing and cold starts hurt background jobs.

**How it works:**
- Instance type is configurable via Terraform variable (defaults to a general-purpose type)
- Runs **Amazon Linux 2023** — the current AWS-supported Linux distribution
- Has a **30 GB encrypted disk** (gp3 type — fast SSD, good value)
- Has an **Elastic IP** (a stable public IP address that never changes even if the server restarts) — this is critical because CloudFront needs a fixed hostname to route API traffic to
- SSH is **disabled by default** — all access goes through SSM (explained below)
- On first boot, a bootstrap script runs automatically via EC2 `user_data`. It installs Docker, clones the repo from GitHub, pulls the `.env` from SSM, and starts the application. Every subsequent deploy uses CI/CD instead.

**What runs on EC2:**
- **FastAPI backend** — the Python API (port 8000)
- **ARQ worker** — the background job processor that handles ingestion and memory extraction
- **PostgreSQL** — the database (runs in Docker)
- **Redis** — the job queue and cache (runs in Docker)
- **CloudWatch Agent** — ships CPU, memory, and disk metrics to CloudWatch

#### 2. S3 — Frontend File Storage

**What it is:** Amazon's object storage service. We use it to store the compiled frontend application — the HTML, JavaScript, and CSS files that users' browsers download when they visit docbase.

**Why S3:**
- The frontend is a static Single Page Application (SPA) built with Vite/React. There's no server-side rendering needed. Static files are perfectly suited for S3.
- Near-zero cost — we only pay for storage space (a few megabytes) and download traffic.
- Infinitely scalable — S3 can serve millions of simultaneous downloads with no configuration.

**How it works:**
- The S3 bucket is configured as a **static website host** — it serves `index.html` for any path (so React Router's client-side navigation works correctly)
- The bucket is named `docbase-{environment}-frontend-{aws-account-id}` to be globally unique
- Every deploy overwrites the bucket contents with the new build using `aws s3 sync --delete`

#### 3. CloudFront — The CDN (Content Delivery Network)

**What it is:** Amazon's global content delivery network. It sits in front of everything and is the only thing users ever talk to directly.

**Why CloudFront:**
- **Speed:** CloudFront has 400+ edge locations worldwide. When a user in Lagos requests the app, they get files from the nearest edge location, not from a server in us-east-1. Much faster.
- **HTTPS for free:** CloudFront provides SSL/TLS certificates via ACM (Amazon Certificate Manager) at no additional cost.
- **Single entry point:** Both the frontend (S3) and the backend API (EC2) are served through one CloudFront URL. The browser never needs to know there are two different backends.
- **Security:** The EC2 server's API port is exposed to the internet, but CloudFront adds a layer of control (headers forwarding, protocol enforcement, zero caching on API responses).

**How CloudFront routing works — this is important:**

CloudFront has two routing rules:

| Request path | Where it goes | Why |
|---|---|---|
| `/api/*` | EC2 backend (port 8000) | All API calls — auth, chat, sources, etc. |
| Everything else | S3 frontend bucket | HTML, JS, CSS, images |

- API responses are **never cached** (min/default/max TTL = 0) — this ensures every API call reaches the real server
- Frontend files are **cached for 1 hour** (default) up to **24 hours** — so returning users load the app instantly
- After every deploy, the CI pipeline sends a **cache invalidation** for `/*` to CloudFront — this forces all edges to pull fresh files immediately so users aren't served a stale version of the app

**Custom domain (optional):** Terraform also provisions ACM SSL certificates and Route 53 DNS records if you configure a custom domain. This is how `docbase.io` would be wired up.

#### Supporting Resources

**SSM Parameter Store:** AWS's secret management system. We store two critical secrets here:
1. `/docbase/{env}/github-deploy-token` — a GitHub Personal Access Token that EC2 uses to `git pull` the latest code
2. `/docbase/{env}/app-env` — the entire `.env` file (API keys, database credentials, etc.) encrypted at rest

**Why SSM over `.env` files committed to git or environment variables baked into the AMI:** Secrets in git is a security disaster. SSM stores them encrypted (using AWS KMS) and access is controlled by IAM permissions — only the EC2 instance role can read its own secrets.

**IAM Roles and Policies:** Identity and Access Management. The EC2 instance runs under an IAM role (`ec2-observability`) that grants it exactly the permissions it needs — write logs to CloudWatch, read its own SSM parameters, report metrics. Nothing more. This is the **principle of least privilege** — if the server were ever compromised, the attacker can't access other AWS resources.

---

## Part 2 — CI/CD: How Code Gets from Laptop to Production

### What CI/CD Is

CI/CD stands for **Continuous Integration / Continuous Deployment**. The idea is simple: instead of manually deploying code (which is error-prone and slow), every push to the `main` branch triggers an automated pipeline that deploys everything safely.

**Why this matters for a demo:** When you show the product and say "we can ship improvements the same day," this is the technical proof of that claim.

### The Trigger

```
Developer pushes code to GitHub main branch
         ↓
GitHub Actions pipeline starts automatically
         ↓
Three jobs run in parallel (after infrastructure is confirmed ready)
```

You can also trigger a deploy manually and choose the environment (dev / test / prod) from GitHub's UI.

### Job 1 — Terraform (Infrastructure)

**What Terraform is:** Infrastructure-as-code. Instead of clicking around in the AWS console to create servers and configure services, we describe what we want in code (`.tf` files) and Terraform figures out what to create, update, or leave alone.

**Why Terraform over alternatives:**
- **vs. clicking in AWS console:** No audit trail, easy to make mistakes, impossible to reproduce exactly, cannot be reviewed in a pull request
- **vs. AWS CloudFormation:** CloudFormation is AWS-native but has a much more verbose syntax and slower feedback loops. Terraform works across cloud providers and has a larger community
- **vs. Pulumi:** Pulumi uses general-purpose programming languages (Python, TypeScript) which is more powerful but overkill for our infrastructure size

**What happens in this job:**

1. GitHub Actions assumes an AWS IAM role using **OIDC** (OpenID Connect) — this is a security mechanism where GitHub proves its identity to AWS without needing long-lived access keys stored as secrets. Much safer than `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

2. Terraform initialises and pulls its **state file from S3** — Terraform tracks what currently exists in AWS in a state file. We store this in S3 (with a DynamoDB lock table to prevent two deploys from running simultaneously and corrupting it).

3. **`terraform apply`** runs — Terraform compares the desired state (code) against the current state (what's actually in AWS) and only makes the changes necessary. If you push code and infrastructure hasn't changed, this step completes in seconds.

4. Terraform outputs key values (EC2 instance ID, EC2 DNS hostname, CloudFront URL, S3 bucket name, CloudFront distribution ID) which are passed to the next two jobs.

### Job 2 — Frontend (runs in parallel with Job 3, after Job 1)

**What happens:**

1. Node.js is set up with npm caching (so `npm install` is fast on repeat runs)

2. **Vite builds the frontend** — Vite compiles all the TypeScript, React components, and styles into optimised static files. The `VITE_API_URL` environment variable (the CloudFront URL) is baked into the build at this point so the browser knows where to send API requests.

3. **`aws s3 sync --delete`** — uploads the new build to S3, deleting any old files that no longer exist

4. **CloudFront cache invalidation** — sends a `/*` invalidation request to CloudFront. Within 30–60 seconds, all CloudFront edge locations discard their cached copies and serve the new files. Without this, users might see the old version of the app for up to 24 hours.

### Job 3 — Backend (runs in parallel with Job 2, after Job 1)

This is the most sophisticated part of the CI/CD pipeline.

**The challenge:** How do you deploy new code to a server without SSH access and without storing any credentials in GitHub?

**The solution: AWS SSM RunCommand**

SSM (Systems Manager) is an AWS service that lets you run shell commands on EC2 instances **without SSH**. The instance runs an SSM agent (installed automatically on Amazon Linux 2023). GitHub Actions sends a command to SSM, SSM delivers it to the agent on EC2, the agent runs it, and the output is returned.

**Why no SSH:**
- SSH requires storing a private key somewhere — that key becomes a secret that can be leaked
- SSM uses the same IAM role system as everything else — no additional credentials needed
- SSM logs every command sent, who sent it, and the output — full audit trail

**What happens step by step:**

1. **CI waits for the SSM agent to come online** — polls every 10 seconds for up to 5 minutes. Important for the first deploy when the EC2 instance might still be bootstrapping.

2. **CI constructs a shell script** (entirely in memory on the GitHub Actions runner) and sends it to the EC2 instance via `aws ssm send-command`

3. **On the EC2 instance, the script:**
   - Fetches the GitHub deploy token from SSM Parameter Store
   - Does `git fetch origin main` + `git reset --hard origin/main` — pulls the exact commit that triggered this workflow
   - Calls `scripts/deploy-backend.sh`

4. **`deploy-backend.sh` on EC2:**
   - Fetches the `.env` file from SSM Parameter Store (fresh on every deploy — if you update a secret, it takes effect immediately)
   - Appends `COMPOSE_FILE=docker-compose.yml:docker-compose.awslogs.yml` so Docker knows to use the CloudWatch logging driver
   - Runs `docker compose up -d --build backend worker` — rebuilds the Docker images from the new code and restarts the containers. The `-d` flag means "detached" (background). Only `backend` and `worker` are restarted — `postgres` and `redis` continue running undisturbed.

5. **CI polls SSM** every 10 seconds for up to 10 minutes waiting for the command to finish. If it fails, the full stdout and stderr from the EC2 instance are printed directly into the GitHub Actions log so you can diagnose the issue without logging into the server.

### Summary Job

After all three jobs complete, a summary job prints the deploy results:

```
╔══════════════════════════════════════════╗
║         docbase deploy complete          ║
╠══════════════════════════════════════════╣
  Environment : dev
  Commit      : abc1234
  CloudFront  : https://d1234.cloudfront.net
  EC2 DNS     : ec2-44-218.compute-1.amazonaws.com
╠══════════════════════════════════════════╣
  Terraform   : success
  Frontend    : success
  Backend     : success
╚══════════════════════════════════════════╝
```

---

## Part 3 — The Application Pipeline: From User Upload to AI Answer

### Step 1 — Source Ingestion

**What triggers it:** A user attaches a source to their twin (Google Drive folder, PDF, markdown file, manual note). The API immediately queues a background job and returns — the user sees "Syncing…" in the UI.

**Why a background job and not doing it inline in the API request:**
- Reading a large Google Drive folder, extracting text, and generating embeddings can take 30–120 seconds
- HTTP requests time out after ~30 seconds in most clients
- The worker can retry if something fails without the user having to re-upload

**The worker technology: ARQ**

ARQ is a Python background job library that uses **Redis** as its queue. When a source is attached, the API pushes a job ID into a Redis list. The ARQ worker process (running alongside the API on EC2) watches that list and picks up jobs as they arrive.

**Why ARQ over alternatives:**
- **vs. Celery:** Celery is powerful but heavyweight — requires a separate broker, result backend, and has significant configuration overhead. ARQ is async-native (asyncio), simpler, and matches our FastAPI/async stack.
- **vs. AWS SQS + Lambda:** Adds infrastructure complexity and Lambda's 15-minute limit is again a problem for large ingestion jobs.

**The ingestion job — 13 steps:**

```
Source attached → job queued in Redis
        ↓
1.  Load source from database (includes OAuth account if Google Drive)
2.  Load TwinConfig (check if code snippets are allowed)
3.  Mark source as "ingesting" in the database
4.  Resolve OAuth access token (decrypt it; refresh via Google API if expired)
5.  Instantiate the correct connector (Drive / PDF / Markdown / Manual)
6.  Validate the connection (can we actually reach the files?)
7.  Fetch raw content (full sync on first attach; delta sync on updates)
8.  For full syncs: delete all existing chunks for this source
    For delta syncs: delete only chunks for changed files
9.  Run the Knowledge Pipeline (see below)
10. Update sync cursors (bookmark our place for next delta sync)
11. Register a webhook with Google Drive (so future file changes auto-trigger re-sync)
12. Mark source as "processing"
13. Enqueue the Memory Brief generation job
```

**The Knowledge Pipeline (Step 9):**

This is where the raw content becomes searchable. For each document:

1. **Policy check** — Is this file blocked? (`.env` files, files containing API keys, passwords, private keys are always blocked regardless of any configuration)

2. **Text extraction** — Extracts structured text. PDFs are parsed page by page. Google Drive docs are read via the Drive API. Markdown files are parsed for headings and sections.

3. **Chunking** — The document is split into overlapping sections of ~2000 characters with ~200 character overlap. Why overlap? So that a sentence that straddles a chunk boundary appears in both chunks — preventing context from being lost at the seam.

4. **Embedding** — Each chunk is sent to an embedding model (OpenAI's text-embedding models, with Jina as a fallback). The model converts the text into a vector — a list of ~1500 numbers that encode the semantic meaning of the text. Texts with similar meanings produce similar vectors.

5. **Database write** — The chunk text and its embedding vector are stored in PostgreSQL, which has the **pgvector** extension installed. pgvector is a PostgreSQL plugin that adds a special column type for storing vectors and lets you run similarity searches directly in SQL.

### Step 2 — Memory Brief Generation

After ingestion, a second background job automatically runs. This is the **Memory Brief**.

**What it is:** The AI reads all the chunks from a twin's sources and writes a concise summary — who this twin is, what topics it covers, key facts, recent changes. This summary is stored in the `TwinConfig.memory_brief` column.

**Why it exists:** If you ask a twin "tell me about yourself" or "what can you help me with?" — no individual document chunk says "I am a twin." The memory brief answers those identity questions. It is injected unconditionally into every answer prompt, so every response has context about what the twin represents even if retrieval doesn't find a perfect chunk.

**What prevents duplicate jobs:** A **Redis lock** with a 10-minute TTL. If a second memory brief job tries to start while one is already running (because two sources were attached in quick succession), it waits or yields rather than running in parallel and producing conflicting writes.

### Step 3 — User Asks a Question

When a user types a question in chat, the flow is:

```
User types question
       ↓
API receives the message
       ↓
Intent Classification → what kind of question is this?
       ↓
Hybrid Retrieval (vector + lexical search)
       ↓
Merge, deduplicate, prepend memory brief
       ↓
Generate answer with the AI model
       ↓
Quality Gate (optional) — LLM-as-judge validates the answer
       ↓
Evidence Verification — confirm the answer is grounded
       ↓
Return to user + log to CloudWatch + log to Langfuse
```

**Intent Classification:**

Before searching, an LLM classifies the query. The intent adjusts how many chunks to retrieve (top-k). For example:
- A specific question ("what does the SA brief say about pricing?") → fewer, more targeted chunks
- A broad question ("explain the whole project") → more chunks

**Hybrid Retrieval:**

We run two searches simultaneously and combine the results:

| Search type | How it works | Best for |
|---|---|---|
| **Vector search** (semantic) | Finds chunks whose embedding vectors are mathematically close to the query's embedding vector | "What are the risks?" — finds risk-related content even if the word "risks" doesn't appear |
| **Lexical search** (keyword) | PostgreSQL full-text search — finds exact word matches | "What does clause 4.2 say?" — precise term lookup |

**Why both?** Vector search alone misses exact matches. Lexical search alone misses synonyms and paraphrasing. The hybrid finds what either method would find and keeps the result with the higher score.

**After retrieval:**
- Duplicate chunks are removed (same chunk appearing in both search types)
- The memory brief chunks are prepended with a small score boost so they rank near the top
- The list is pruned to the configured top-k

**Answer Generation:**

The retrieved chunks, the memory brief, and any custom context the twin owner wrote are assembled into a system prompt. The structure is:

```
[Role + twin identity]
[Custom context the owner wrote]
[Memory brief — the AI-generated summary of the twin's knowledge]
[Retrieved chunks — the actual document sections most relevant to the question]
[Today's date]
[Rules — safety constraints, attribution requirements]
```

This prompt goes to the language model (OpenAI GPT-4o-mini). The model generates a response grounded in the provided context.

**Quality Gate (when enabled):**

After the first draft is generated, a second LLM call acts as a **judge**. It reads the answer and the evidence and decides: is this answer acceptable? Does it claim things that aren't in the evidence? Is it evasive when it shouldn't be?

If the judge rejects the answer, the pipeline generates a revised answer (with the judge's feedback included) and checks again — up to a bounded number of attempts. This prevents hallucinations from reaching users.

**Evidence Verification:**

A separate verifier checks that the response is grounded — it ensures the answer doesn't contradict what was retrieved. If it detects hedging (answers that say "I couldn't find information about this" when evidence exists), it flags this and the quality gate handles it.

---

## Part 4 — Observability: How We Know the System is Healthy

We run two completely separate observability systems for two different purposes. Together they answer every question about what's happening in production.

---

### CloudWatch — Infrastructure and Application Health

**What it is:** AWS's built-in monitoring service. Think of it as a real-time dashboard that watches the server and the application 24/7.

**Why CloudWatch:**
- Native to AWS — no additional infrastructure to run
- The EC2 instance role already has permission to write to it — no additional credentials needed
- Log storage, metric aggregation, alarms, and dashboards are all one integrated service

**How logs get into CloudWatch:**

There are two separate mechanisms:

**1. Docker `awslogs` driver (application logs):**

The Docker containers running the backend and worker are configured (via `docker-compose.awslogs.yml`) to use the `awslogs` log driver. This means every `print()` or `logger.info()` call inside the application is shipped directly to CloudWatch Logs — the Docker daemon handles the delivery, no additional agent needed.

- Backend logs → `/docbase/dev/backend`
- Worker logs → `/docbase/dev/worker`

All application logs are **structured JSON** — every log line is a JSON object, not a free-text string. This is essential for CloudWatch to be able to filter and query them.

Example of what a structured log line looks like:
```json
{
  "event": "chat_latency_metrics",
  "total_ms": 2341,
  "retrieval_ms": 412,
  "generation_ms": 1890,
  "chunks_returned": 8,
  "budget_exceeded": false,
  "timestamp": "2026-04-27T10:23:41Z"
}
```

**2. CloudWatch Agent (system metrics):**

The CloudWatch Agent runs directly on EC2 (not in Docker) and ships system-level metrics every 60 seconds:
- CPU usage (user, system, idle)
- Memory used percentage
- Disk used percentage (for both `/` and `/var/lib/docker`)
- Network bytes sent/received
- TCP connection counts (established, time-wait)

These metrics go to the `Docbase/Dev` namespace in CloudWatch.

**How Terraform sets up the CloudWatch Agent config:**

The agent configuration (what metrics to collect, at what frequency) is stored in SSM Parameter Store (managed by Terraform). When the EC2 bootstrap script runs, it fetches this config from SSM and tells the agent to use it. Updating the config is a Terraform `apply` + one command on the instance — no manual editing of JSON files on the server.

**Metric Filters — turning logs into metrics:**

This is one of the most powerful patterns we use. CloudWatch Metric Filters watch a log group and, whenever a log line matches a pattern, emit a numeric data point to a metric.

We have **9 metric filters:**

| Filter name | What it watches for | Why it matters |
|---|---|---|
| `chat_latency` | Lines with `event = "chat_latency_metrics"` → extracts `total_ms` | Tracks how long single-twin chat takes end-to-end |
| `workspace_chat_latency` | Same for workspace-wide chat | Workspace queries fan out across multiple twins — naturally slower |
| `budget_exceeded` | Lines where `budget_exceeded = true` | When a chat takes longer than our internal SLA target |
| `retrieval_chunks` | Lines with `event = "retrieval_complete"` → extracts `chunks_returned` | How many relevant chunks the RAG pipeline found. Near-zero = the pipeline may be broken |
| `missing_evidence` | Lines where `event = "retrieval_complete"` AND `lexical_hits = 0` | Lexical search found nothing — possible signal that a source wasn't indexed properly |
| `app_errors` | Lines where `level = "error"` in the backend log | API-level errors |
| `worker_errors` | Lines where `level = "error"` in the worker log | Ingestion and memory extraction errors |
| `quality_gate_rejections` | Lines where the LLM judge returned `is_acceptable = false` | The AI judge found the answer was not good enough. Elevated rates signal retrieval degradation or prompt regression |
| `quality_gate_exhausted` | Lines where regeneration ran out of attempts | The judge rejected every attempt. Answer was served anyway. This is the most serious quality signal |

**Alarms — automatic alerts:**

Six CloudWatch alarms watch the metrics above and fire when thresholds are crossed:

| Alarm | Threshold | What it means |
|---|---|---|
| P95 chat latency | > 5,000ms for 3 consecutive 5-min windows | Users are experiencing slow responses consistently |
| Budget exceeded rate | > 5 breaches in 5 minutes | Many queries are slow — possible model latency or retrieval bottleneck |
| App error rate | > 10 errors in 5 minutes | Something is broken in the API |
| Zero retrieval chunks | Average < 1 chunk across 3 windows | RAG pipeline is returning nothing — possible database or embedding issue |
| Quality gate rejection rate | > 10 rejections in 5 minutes | LLM judge is consistently unhappy — retrieval or prompt degradation |
| Quality gate exhausted | > 2 exhaustions in 5 minutes | Answers being served after all retries failed — serious quality regression |

When an alarm fires, AWS SNS sends an email notification (configured via `alarm_email` Terraform variable).

**The Dashboard:**

Terraform provisions a CloudWatch dashboard called `docbase-dev-observability` with **8 metric panels and 1 alarm status panel**, arranged in 5 rows:

```
Row 1: Chat Latency (p50/p95/p99) | Latency Budget Breaches
Row 2: RAG Chunks Retrieved       | Missing Evidence Events
Row 3: Quality Gate Rejections    | Application Errors (API + Worker)
Row 4: EC2 CPU                    | EC2 Memory
Row 5: EC2 Disk
Row 6: Alarm Status panel (all 6 alarms in one view)
Row 7: Recent Errors log table (last 50 errors, last 1 hour)
```

---

### Langfuse — AI Quality and LLM Tracing

**What it is:** An open-source LLM observability platform. Where CloudWatch watches the infrastructure, Langfuse watches the AI — specifically what the model is receiving, what it's generating, how long it takes, how many tokens it uses, and what quality scores the evaluator assigns.

**Why Langfuse over alternatives:**
- **vs. just CloudWatch:** CloudWatch can't store LLM inputs and outputs (they're too large and too unstructured for log filters). Langfuse is purpose-built for LLM traces.
- **vs. LangSmith:** LangSmith is tied to the LangChain ecosystem. We use raw OpenAI SDK calls, not LangChain, so LangSmith would require wrapping our code significantly.
- **vs. Weights & Biases:** Built for model training and ML experiments. Langfuse is built for production LLM applications.
- **vs. building our own:** Storing and querying LLM traces is a solved problem. Langfuse is open-source, self-hostable, and has exactly the features we need.

**How it's integrated:**

Langfuse is **optional** — if `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` are not in the `.env`, the system runs without it. The `get_langfuse()` function in `app/core/observability.py` returns `None` gracefully, and all callers check `if lf:` before using it.

**What gets traced:**

For every chat message that goes through the system:

1. **A Trace is opened** — represents the entire chat message lifecycle (user query → final answer)
   - User ID
   - Session ID
   - Twin ID
   - The user's question

2. **A Retrieval Span** is attached — represents the retrieval step
   - What query was sent to the vector/lexical search
   - How many chunks were returned
   - How long retrieval took

3. **A Generation** is attached — represents the LLM call
   - The full system prompt (what context we sent the model)
   - The model name and version
   - Input token count
   - Output token count
   - Latency of the LLM call

4. **The Trace is closed** — the final answer is attached

5. **Quality Scores are pushed** — the evaluator runs dimensional scoring and pushes named scores to the trace:
   - `completeness` — did the answer address the question fully?
   - `groundedness` — is every claim in the answer supported by the retrieved chunks?
   - `relevance` — did retrieval actually find relevant content?
   - `conciseness` — is the answer appropriately focused?

**What this gives you in the Langfuse UI:**

- A complete history of every AI interaction — searchable by user, session, twin, or date
- Token usage per query — you can see exactly how expensive each answer was
- Latency breakdown — retrieval time vs. generation time
- Score distributions — are most answers highly grounded? Are some failing on completeness?
- Ability to filter for low-scoring answers and read the actual prompt + response to understand why

**The relationship between CloudWatch and Langfuse:**

They are complementary, not redundant:

| Question | Answer comes from |
|---|---|
| Is the server running out of memory? | CloudWatch |
| Is the API returning errors? | CloudWatch |
| How many tokens did that answer use? | Langfuse |
| What exactly did the AI receive for that query? | Langfuse |
| Is the P95 chat latency above 5 seconds? | CloudWatch alarm |
| Are answers low quality for a specific twin? | Langfuse score filter |
| Did a deploy break something? | CloudWatch error rate spike |
| Is a specific retrieval pattern failing? | Langfuse retrieval spans |

---

## Part 5 — The End-to-End Story for a Demo

Here is the complete journey, told as a narrative:

**"A user attaches a Google Drive folder."**

1. They click "Add source" in the UI. The frontend sends a POST to `/api/v1/sources/`.
2. The API validates the request, creates a Source row in PostgreSQL, and pushes an `ingest_source` job into Redis.
3. The API returns immediately — the UI shows "Syncing."
4. The ARQ worker picks up the job. It fetches a decrypted OAuth token from the database, calls the Google Drive API, walks the folder, and reads each document.
5. Each document is policy-checked, chunked into ~2000-character sections, embedded via OpenAI's embedding model, and written to PostgreSQL (with the pgvector extension storing the embedding vector).
6. After all documents are processed, a second job is queued: `generate_memory_brief`. The AI reads all the chunks and writes a summary of what this twin knows.
7. The source status changes to "ready." The UI reflects this.

Every step is logged as structured JSON. CloudWatch receives these logs in real time via the Docker `awslogs` driver.

**"A visitor asks the twin a question."**

1. They type "What was the main goal of the Eshicare engagement?" and hit Send.
2. The frontend sends a POST to `/api/v1/chat/sessions/{id}/messages`.
3. If Langfuse is configured, a trace opens in Langfuse.
4. The question is classified by an LLM (intent: specific query → top-k = 12).
5. Vector search and lexical search run simultaneously in PostgreSQL.
6. Results are merged, deduplicated, and ranked. The memory brief chunks are prepended with a score boost.
7. The top 12 chunks are assembled into a system prompt alongside the memory brief and any custom context.
8. OpenAI generates the answer.
9. If the quality gate is enabled, a judge LLM reviews the answer. If it's rejected, a revised answer is generated and checked again (up to the bounded limit).
10. The evidence verifier confirms the answer is grounded.
11. The answer is saved to the database and returned to the frontend.
12. A `chat_latency_metrics` log line is emitted — CloudWatch picks this up, the metric filter extracts `total_ms`, and this data point appears on the CloudWatch dashboard within seconds.
13. The Langfuse trace closes with the final answer, token counts, and latency attached.
14. Asynchronously, the dimensional evaluator runs and pushes quality scores to the Langfuse trace.

**"A developer pushes a bug fix."**

1. They push to `main` on GitHub.
2. GitHub Actions starts the deploy pipeline.
3. Terraform runs — infrastructure is already correct, no changes needed, completes in ~20 seconds.
4. Frontend job: Vite builds in ~30 seconds, syncs to S3, invalidates CloudFront cache.
5. Backend job: SSM sends the deploy command to EC2. Git pulls the new commit. Docker rebuilds the backend and worker images. `docker compose up` restarts only the backend and worker containers — the database and Redis are undisturbed. Running ingestion jobs are not killed because the worker process exits gracefully.
6. Total time from push to live in production: **under 4 minutes**.
7. If the new code introduced errors, the CloudWatch error rate alarm fires within the first 5-minute window and sends an email.

---

## Part 6 — Key Decisions Summary (For Technical Audiences)

| Decision | What we chose | Why not the alternative |
|---|---|---|
| Frontend hosting | S3 + CloudFront | Not EC2 — static files don't need a server |
| Backend server | EC2 + Docker Compose | Not Lambda — long-running jobs; not ECS — unnecessary complexity |
| Deploy mechanism | SSM RunCommand | Not SSH — no keys to manage; not CodeDeploy — overkill |
| Secret management | SSM Parameter Store | Not environment variables in the AMI — secrets rotate without rebuilding |
| Infrastructure-as-code | Terraform | Not CloudFormation — cleaner syntax, faster iteration |
| State management | Terraform on S3 + DynamoDB | Not local state — enables team collaboration and CI/CD |
| Background jobs | ARQ (Redis-backed) | Not Celery — async-native, simpler; not SQS — no Lambda timeout issues |
| Vector search | pgvector (PostgreSQL extension) | Not a dedicated vector DB (Pinecone, Weaviate) — one fewer service to operate; PostgreSQL already runs |
| Hybrid retrieval | pgvector + PostgreSQL FTS | Vector alone misses exact terms; FTS alone misses semantics |
| LLM observability | Langfuse | Not LangSmith (LangChain-tied); not CloudWatch (can't store LLM I/O) |
| Infrastructure observability | CloudWatch | Native AWS, no additional infrastructure, integrates with alarms + dashboards |
| Log format | Structured JSON | Not free-text — CloudWatch metric filters can extract fields from JSON |
| OIDC for AWS auth | GitHub OIDC → IAM role | Not long-lived access keys — much safer, no secret rotation needed |
| Chunk overlap | 200 chars on 2000-char chunks | Prevents context loss at chunk boundaries |
| Memory brief | Separate async ARQ job | Not inline during ingestion — keeps the ingestion job fast; not in `custom_context` — that's owner-editable |
