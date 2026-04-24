# Deploy setup guide (AWS + GitHub Actions)

This guide walks you through **one-time setup** so you can run Terraform and deploy the **static frontend** (S3 + CloudFront). The FastAPI backend is **not** deployed by this script—you run it separately (Docker, ECS, etc.).

**Time:** about 30–60 minutes the first time, mostly clicking in AWS and GitHub.

---

## What you are setting up

| Piece | Why |
|-------|-----|
| **S3 bucket** `docbase-terraform-state-<account-id>` | Stores Terraform state so your computer and GitHub don’t overwrite each other blindly. |
| **DynamoDB table** `docbase-terraform-locks` | Prevents two Terraform runs from corrupting state at the same time. |
| **IAM role + GitHub OIDC** | Lets GitHub Actions call AWS **without** storing AWS access keys in GitHub. |
| **GitHub secrets** | Tells the workflow which role and region to use. |
| **Optional variable `DOCBASE_VITE_API_URL`** | Tells the Vite build where your **public API** lives (browser calls this URL). |

Pick **one AWS region** (example: `us-east-1`) and use it everywhere below.

---

## Before you start (checklist)

- [ ] An AWS account you can log into (root or IAM admin).
- [ ] [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed (`aws --version`).
- [ ] CLI configured (`aws configure` or SSO)—you can run `aws sts get-caller-identity` and see an **Account** number.
- [ ] GitHub repo for docbase (organization or user repo is fine).

---

## Step 1 — Write down your account ID and region

In a terminal:

```bash
aws sts get-caller-identity
```

Copy:

- **Account** → 12 digits, e.g. `123456789012`
- Decide **Region** → e.g. `us-east-1`

Your **state bucket name** will be:

```text
docbase-terraform-state-123456789012
```

(replace with your real account ID)

---

## Step 2 — Create the Terraform state S3 bucket

**Goal:** A **private** bucket only for Terraform state—not your website files.

### Using the AWS console (recommended)

1. Open **AWS Console** → **S3** → **Create bucket**.
2. **Bucket name:** `docbase-terraform-state-<YOUR_ACCOUNT_ID>` (from Step 1).
3. **Region:** same as your chosen region (e.g. `US East (N. Virginia)`).
4. Leave **Block all public access** **ON** (default).
5. **Create bucket**.
6. Open the bucket → **Properties**:
   - Turn **Bucket Versioning** → **Enable** (helps recover from bad state).
7. **Properties** → **Default encryption** → enable (AWS managed key is fine).

**Checkpoint:** Bucket exists, versioning on, not public.

---

## Step 3 — Create the DynamoDB lock table

**Goal:** Terraform uses this so only one `apply` touches a given state at a time.

### Using the AWS console

1. **DynamoDB** → **Tables** → **Create table**.
2. **Table name:** `docbase-terraform-locks` (exact spelling—scripts expect this name).
3. **Partition key:** `LockID` → type **String**.
4. **Table settings** → default is fine (on-demand billing is OK).
5. **Region:** same as Step 2.
6. **Create table**.

**Checkpoint:** Table `docbase-terraform-locks` exists in the same region as the state bucket.

---

## Step 4 — Create an IAM role GitHub Actions can assume (OIDC)

**Goal:** GitHub proves “I am workflow run X from repo Y” and AWS returns temporary credentials—no long-lived keys in GitHub.

### 4a. Add GitHub as an identity provider (once per AWS account)

1. **IAM** → **Identity providers** → **Add provider**.
2. **Provider type:** OpenID Connect.
3. **Provider URL:** `https://token.actions.githubusercontent.com`
4. **Audience:** `sts.amazonaws.com`
5. **Add provider** (if it already exists, skip).

### 4b. Create the role

1. **IAM** → **Roles** → **Create role**.
2. **Trusted entity type:** Web identity.
3. **Identity provider:** `token.actions.githubusercontent.com`.
4. **Audience:** `sts.amazonaws.com`.
5. **GitHub organization AND repository:** choose your org/user and repo (e.g. `your-org/docbase`).
6. **Next**.

### 4c. Attach permissions (start simple, tighten later)

For a first successful deploy, many teams attach **PowerUserAccess** *or* a custom policy that allows at least:

- S3: full access to buckets Terraform creates **and** read/write on the **state** bucket prefix.
- DynamoDB: read/write on table `docbase-terraform-locks`.
- CloudFront, ACM (us-east-1 if using custom domains), Route53 if using custom domain in Terraform, IAM for CloudFront-related resources Terraform creates.

**Practical tip:** Use **PowerUserAccess** for a private dev account only; for production accounts, replace with a least-privilege policy later.

1. **Next** → name the role e.g. `github-actions-docbase-deploy`.
2. **Create role**.

### 4d. Lock the trust policy to your repo (important)

1. Open the new role → **Trust relationships** → **Edit trust policy**.
2. Ensure the `StringEquals` / condition limits **which repo** can assume the role. The GitHub wizard often adds `repo:ORG/REPO:*` or similar—keep it as narrow as you are comfortable with (e.g. only `ref:refs/heads/main` for stricter setups).

**Checkpoint:** You have a **Role ARN** like:

```text
arn:aws:iam::123456789012:role/github-actions-docbase-deploy
```

Copy it—you will paste it into GitHub as `AWS_ROLE_ARN`.

---

## Step 5 — Configure GitHub

Open your repo on GitHub → **Settings** → **Secrets and variables** → **Actions**.

### 5a. Repository secrets (required for the deploy workflow)

| Name | Value |
|------|--------|
| `AWS_ROLE_ARN` | The role ARN from Step 4d. |
| `DEFAULT_AWS_REGION` | e.g. `us-east-1` (must match bucket/table region). |

**How to add:** **New repository secret** → name → value → **Add secret**.

### 5b. Repository variable (optional)

| Name | When to set |
|------|-------------|
| `DOCBASE_VITE_API_URL` | Set if the static site must call a **separate** API URL (typical for S3+CloudFront + API on another host). Example: `https://api-dev.yourdomain.com` (no trailing slash unless you know you need it). |

**How to add:** **Variables** tab → **New repository variable**.

If you leave it empty, the workflow still builds the frontend, but the build may rely on same-origin `/api` (which usually **does not** apply to a static site on CloudFront unless you also put the API behind the same hostname).

### 5c. GitHub Environments (optional but good practice)

**Settings** → **Environments** → create **`dev`**, **`test`**, **`prod`**.

- For **`prod`**, add **required reviewers** so production deploys need a click-through approval.

The workflow uses the selected environment name when you run it.

---

## Step 6 — First deploy (pick one path)

### Path A — From GitHub (no local AWS credentials needed)

1. Push this repo to GitHub (if it isn’t already).
2. **Actions** → **Deploy docbase** → **Run workflow**.
3. Choose **`dev`** → **Run workflow**.
4. Watch the job log. If it fails with `AccessDenied`, extend the IAM policy from Step 4c.

### Path B — From your laptop (uses your own AWS login)

```bash
export DEFAULT_AWS_REGION=us-east-1   # your region
./scripts/deploy.sh dev
```

Your IAM user/role needs permissions similar to the GitHub role.

---

## Step 7 — After a successful deploy

From the workflow log or after a local apply, Terraform prints outputs. You care about:

- **CloudFront URL** — where the static site is served.
- **S3 frontend bucket** — where files were synced.

Point your **API** CORS and any auth settings at the CloudFront URL if the browser will call the API cross-origin.

**Fastest way to attach an API** (tunnel to local Docker, then set `DOCBASE_VITE_API_URL` + CORS): see [`BACKEND_QUICK_CONNECT.md`](./BACKEND_QUICK_CONNECT.md).

---

## Quick troubleshooting

| Symptom | Likely fix |
|---------|------------|
| `NoSuchBucket` for state bucket | Bucket name must be `docbase-terraform-state-<account-id>` in the **same** region you use in `DEFAULT_AWS_REGION`. |
| DynamoDB errors about locking | Table must be named **`docbase-terraform-locks`** with partition key **`LockID`** (String). |
| GitHub: `Could not assume role` | Wrong `AWS_ROLE_ARN`, or trust policy doesn’t allow this repo/environment, or OIDC provider missing. |
| Terraform applies but UI can’t reach API | Set **`DOCBASE_VITE_API_URL`** to the real public API base URL; ensure API **CORS** allows your CloudFront origin. |

---

## Order to use from now on

1. **Local:** `make test` (and `make up` smoke if you want).
2. **AWS dev:** Run workflow or `./scripts/deploy.sh dev`.
3. **Verify** CloudFront URL + API + CORS.
4. **AWS prod:** Only then `./scripts/deploy.sh prod` or workflow with **`prod`**.

---

## Related files in this repo

- `scripts/deploy.sh` — Terraform apply + `npm ci` / `npm run build` + `aws s3 sync` + CloudFront invalidation.
- `scripts/public-api-tunnel.sh` — optional HTTPS tunnel to local `:8000` for quick API + CloudFront wiring.
- `docs/BACKEND_QUICK_CONNECT.md` — tunnel + minimal AWS server notes for the API.
- `terraform/` — S3 website + CloudFront (static frontend only).
- `.github/workflows/deploy.yml` — Manual deploy workflow.

If anything in this guide doesn’t match what you see in the AWS console, AWS often renames labels—search the console for the same concepts (S3 bucket, DynamoDB partition key `LockID`, IAM OIDC, etc.).
