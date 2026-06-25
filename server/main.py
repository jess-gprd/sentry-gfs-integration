from fastapi import FastAPI
import sentry_sdk
import uvicorn
import logging
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def commit_to_gfs(event, hint):
    if hint.get("exc_info"):
        error_msg = str(hint["exc_info"][1])
        logger.info(f"Sentry caught an error: {error_msg}. Taking GFS snapshot.")
        
        try:
            result = subprocess.run(
                ["gfs", "commit", "-m", f"Backend Auto-save: {error_msg}"], 
                check=True,
                capture_output=True,
                text=True
            )
            output_line = result.stdout.strip()
            parts = output_line.split()
            
            if len(parts) >= 3:
                commit_hash = parts[2]
                logger.info(f"GFS database state locked in at commit hash: {commit_hash}")
                event.setdefault("tags", {})["gfs_commit"] = commit_hash
            else:
                logger.info(f"GFS database state locked in. Raw output: {output_line}")
                
        except Exception as e:
            logger.error(f"GFS commit failed: {e}")
            
    return event

sentry_sdk.init(
    dsn="https://b3f79aef9239dbff5a5223ba71fd9490@o4511612248719360.ingest.de.sentry.io/4511612269953104",
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
    # Enable sending logs to Sentry
    enable_logs=True,
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    before_send=commit_to_gfs,
)

app = FastAPI()


class CustomSentryException(Exception):
    pass

@app.get("/health")
async def health():
    logger.info("application is very healthy!")
    return {"status": "ok"}

@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0

@app.get("/sentry-debug-casing")
async def trigger_casing_error():
    x = float("x")

@app.get("/sentry-debug-custom")
async def trigger_custom_error():
    raise CustomSentryException("Custom Sentry exception triggered")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)