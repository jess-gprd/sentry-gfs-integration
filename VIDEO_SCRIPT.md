# We Hooked Sentry Alerts to Auto-Commit Database State Using GFS

## Metadata

| Field | Value |
|-------|-------|
| **Title** | When This Bug Fires, Your Database Snapshots Itself: Sentry + GFS |
| **Series** | GFS Use Cases |
| **Status** | `draft` |
| **Target Length** | 3–4 min |

**Summary**
> When an error fires in production, the database state that caused it is usually gone by the time you go looking. This video hooks Sentry's error reporting to GFS so that every captured error automatically commits the exact database state behind it, and tags the Sentry issue with the commit hash. A teammate reproduces the bug from one command instead of a dump file over Slack. Built on FastAPI, aimed at anyone doing observability or on-call work.


## Production Setup

### Demo Stack

| Tool | Version / Notes |
|------|-----------------|
| `gfs` CLI | installed, authenticated |
| Python | 3.7+, virtualenv ready |
| FastAPI | in `requirements.txt` |
| `sentry-sdk` | 2.x, real DSN configured |
| PostgreSQL | 17, tracked by GFS |
| Terminal + editor | clean prompt, font ≥ 18, dark theme |

- [ ] Empty project folder ready, virtualenv created
- [ ] Real Sentry project + DSN on hand (the demo needs live dashboard hits)
- [ ] `requirements.txt` prepared: `fastapi`, `uvicorn`, `sentry-sdk`, `psycopg2-binary`
- [ ] Two browser tabs pre-opened: Sentry Issues, Sentry Performance
- [ ] Database seeded with the schema below (run once before recording)
- [ ] `gfs status` clean before recording

### Database Seed (run once before recording)

Two small tables: `customers` and `orders`. Enough to drive both a clean
read endpoint and a database-mutating bug.

```sql
-- schema.sql
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    credits     NUMERIC NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    total        NUMERIC NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customers (name, email, credits) VALUES
    ('Ada Lovelace',    'ada@example.com',    120.00),
    ('Alan Turing',     'alan@example.com',     0.00),
    ('Grace Hopper',    'grace@example.com',   45.50),
    ('Linus Torvalds',  'linus@example.com',  300.00);

INSERT INTO orders (customer_id, total, status) VALUES
    (1,  59.99, 'completed'),
    (1,  19.99, 'completed'),
    (2, 250.00, 'pending'),
    (3,  12.00, 'refunded'),
    (4, 500.00, 'completed');
```

Load it:
```bash
gfs query "$(cat schema.sql)"
# or: psql <connection-string> -f schema.sql
```

### Pre-Roll Checklist

- [ ] Terminal: one pane, history cleared
- [ ] DSN scrubbed or acceptable to show on camera
- [ ] Sentry dashboard logged in, project selected
- [ ] Notifications off
- [ ] OBS: all scenes tested


## Scene Types

| Tag | Layout | When to use |
|-----|--------|-------------|
| `[INTRO]` | Brand animation | Auto, no action needed |
| `[CAM]` | Full-frame webcam, no screen | Greeting, concept explanations, CTA |
| `[SCREEN]` | Full screen, no cam | Dense code the viewer needs to read without distraction |
| `[SCREEN+CAM]` | Screen with small PiP webcam | Actively writing code or running commands |
| `[SPLIT]` | Cam beside screen, side by side | Talking about something on screen (Sentry dashboard) without coding |
| `[OUTRO]` | Brand animation | Auto, no action needed |


## Script


### [CAM] Introduction

**line:**
- greet: "Hi, my name is Jess from the Guepard community building team"
- today: hooking Sentry error alerts to GFS so the database snapshots itself when a bug fires
- what the viewer will build: an error in production auto-commits the exact DB state, and tags the Sentry issue with the commit hash


### [INTRO]


### [CAM] The Problem

**line:**
- when an error fires, the database state that caused it is usually already gone by the time you investigate
- the usual fix: someone exports a dump, drops it in Slack, a teammate rebuilds the env by hand
- the idea here: the moment Sentry catches an error, GFS commits that exact state automatically, and the commit hash rides along on the Sentry issue
- a teammate reproduces from one command, no dump files, no manual setup


### [SCREEN+CAM] Scaffold the FastAPI App

**line:**
- start from nothing: requirements file with fastapi, uvicorn, sentry-sdk

**action:**
```bash
# requirements.txt
fastapi
uvicorn
sentry-sdk

pip install -r requirements.txt
```

**line:**
- a minimal main.py, plain FastAPI server, plus a tiny DB connection helper we'll reuse

**action:**
```python
# server/main.py
import psycopg2
from fastapi import FastAPI

app = FastAPI()

DB_DSN = "postgresql://user:pass@localhost:5432/vibey"

def get_conn():
    return psycopg2.connect(DB_DSN)

@app.get("/")
async def root():
    return {"status": "ok"}
```


### [SCREEN+CAM] Add Sentry (Straight from the Docs)

**line:**
- wire in Sentry exactly as their docs say — base init, the integration auto-enables because fastapi is present
- no GFS yet, just see what Sentry does on its own first

**action:**
```python
import sentry_sdk

sentry_sdk.init(
    dsn="https://...ingest.de.sentry.io/...",
    send_default_pii=True,
)
```

**line:**
- add the debug route from the docs to fire a clean error on demand

**action:**
```python
@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
```


### [SCREEN+CAM] Fire the First Bug

**line:**
- run the server, hit the endpoint, trigger the error

**action:**
```bash
python server/main.py
curl http://localhost:8000/sentry-debug
```


### [SPLIT] What Sentry Caught

**line:**
- switch to the Sentry dashboard, Issues tab — the divide-by-zero is already there
- walk through what Sentry captured on its own: stack trace, request data, the endpoint
- this is the baseline — now make it capture database state too


### [SCREEN+CAM] Initialize GFS

**line:**
- set up GFS on the database side

**action:**
```bash
gfs init . --provider postgres --version 17
gfs config user.name "Your Name"
gfs config user.email "you@example.com"
```


### [SCREEN+CAM] The Hook: before_send

**line:**
- the whole integration is one Sentry callback — before_send runs on every event before it ships
- if the event carries an exception, fire a gfs commit, then attach the commit hash back onto the event as a tag

**action:**
```python
import subprocess
import logging

logger = logging.getLogger(__name__)

def commit_to_gfs(event, hint):
    if hint.get("exc_info"):
        error_msg = str(hint["exc_info"][1])
        logger.info(f"Sentry caught an error: {error_msg}. Taking GFS snapshot.")
        try:
            result = subprocess.run(
                ["gfs", "commit", "-m", f"Backend Auto-save: {error_msg}"],
                check=True, capture_output=True, text=True,
            )
            parts = result.stdout.strip().split()
            if len(parts) >= 3:
                commit_hash = parts[2]
                event.setdefault("tags", {})["gfs_commit"] = commit_hash
        except Exception as e:
            logger.error(f"GFS commit failed: {e}")
    return event
```

**line:**
- pass it into init alongside the tracing options

**action:**
```python
sentry_sdk.init(
    dsn="https://...ingest.de.sentry.io/...",
    send_default_pii=True,
    enable_logs=True,
    traces_sample_rate=1.0,
    before_send=commit_to_gfs,
)
```


### [SCREEN+CAM] Fire a Database Bug

**line:**
- this time use a bug that actually touches the database — the endpoint mutates a row, then raises
- so the snapshot captures real, meaningful state mid-operation, not an empty DB

**action:**
```python
# the /db-bug endpoint: deduct credits, THEN hit an error
@app.get("/db-bug")
async def db_bug():
    conn = get_conn()
    cur = conn.cursor()
    # mutate first — this write is what the GFS snapshot will capture
    cur.execute(
        "UPDATE customers SET credits = credits - 50 WHERE id = 2;"
    )
    conn.commit()
    # now the bug: Alan Turing started at 0 credits, so he's now negative
    cur.execute("SELECT credits FROM customers WHERE id = 2;")
    balance = cur.fetchone()[0]
    if balance < 0:
        raise ValueError(f"Negative balance for customer 2: {balance}")
    return {"balance": balance}
```

**line:**
- hit it, then check the GFS log

**action:**
```bash
curl http://localhost:8000/db-bug
gfs log
```

**line:**
- the new commit "Backend Auto-save: Negative balance for customer 2: -50.00" is right there in the log


### [SPLIT] The Hash on the Issue

**line:**
- back to Sentry — open the new issue, point to the gfs_commit tag
- this is the link: the Sentry issue and the exact database snapshot are now tied together
- a teammate copies that hash and checks out the state directly


### [SCREEN+CAM] Navigating Commits: Errors vs Normal Traffic

**line:**
- add two normal database endpoints that read and succeed — no errors, no commits

**action:**
```python
@app.get("/orders")
async def list_orders():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, customer_id, total, status FROM orders;")
    rows = cur.fetchall()
    return {"orders": rows}

@app.get("/customers")
async def list_customers():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, credits FROM customers;")
    rows = cur.fetchall()
    return {"customers": rows}
```

**line:**
- show it in a realistic flow: hit the error endpoint, then the two clean ones
- only the error produced a commit — normal traffic stays quiet

**action:**
```bash
curl http://localhost:8000/db-bug       # error -> commits
curl http://localhost:8000/orders       # normal -> no commit
curl http://localhost:8000/customers    # normal -> no commit
gfs log
```

**line:**
- the log reads as a clean timeline of only the moments things broke


### [SCREEN+CAM] Time-Travel to a Failure

**line:**
- grab a commit hash from a failure and check out that exact state
- inspect the data as it was at the moment the bug fired, then hop back

**action:**
```bash
gfs checkout <commit_hash>
gfs query "SELECT id, name, credits FROM customers WHERE id = 2;"
gfs checkout main
```

**line:**
- at that commit, customer 2's credits are negative — the exact broken state, frozen
- this is the payoff: every error in Sentry is now a one-command trip back to the database that caused it


### [CAM] Wrap-Up and What's Next

**line:**
- recap: Sentry catches the error, GFS commits the state, the hash links them, anyone reproduces from one command
- no dumps over Slack, no manual env rebuilds

**line:**
- the honest limitation: right now the commit message is just the raw error string, "Backend Auto-save: Negative balance for customer 2: -50.00"
- useful, but it tells you the symptom, not the story

**line:**
- the next step, and a whole separate video if people want it: drop a small AI agent into the hook
- instead of pasting the raw error, the agent looks at the error plus what just changed in the database and writes a real message — what the endpoint was doing, which rows moved, why it probably broke
- the GFS log stops reading like stack-trace fragments and starts reading like review notes a teammate actually wrote
- tease: "let me know in the comments if you want that build — it's a fun one"


### [OUTRO]


## Notes & Cuts

- Scrub or rotate the DSN if you don't want the real one on camera
- The two-tab setup (Issues + Performance) matters — the cut to Sentry needs to be instant, not a fumble
- Mention briefly that default failed_request_status_codes is 5xx only, so non-5xx won't trigger a commit unless widened — one sentence, don't dwell
- If showing explicit StarletteIntegration + FastApiIntegration options, note both are required because FastAPI is built on Starlette
- The database bug is the real demo — the divide-by-zero is just the warm-up. Don't over-invest screen time in the warm-up
- The `/db-bug` logic leans on the seed data: customer 2 (Alan Turing) starts at 0 credits, so deducting 50 drops him negative and triggers the raise. If you reseed, keep one customer at a low balance
- The AI-commit-message tease is the hook for a potential follow-up video — keep it short and aspirational, end with a direct ask so it's easy to gauge interest
