"""Run NOVA locally for development/preview.

Loads the root .env (so ANTHROPIC_API_KEY / TAVILY_API_KEY are present — pydantic
otherwise looks for backend/.env, which doesn't exist) and serves the full app
(API + frontend) on http://127.0.0.1:8098.

    python run_local.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(HERE, ".env"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8098, reload=False, log_level="info")
