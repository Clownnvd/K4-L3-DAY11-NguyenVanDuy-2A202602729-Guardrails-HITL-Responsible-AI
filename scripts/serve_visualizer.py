#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from web.guardrail_service import GuardrailRequest, GuardrailService  # noqa: E402


class EvaluateBody(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    user_id: str = Field(default="visualizer-user", min_length=1, max_length=128)
    destination: str = Field(default="https://api.vinbank.example/v1/chat")
    burst_count: int = Field(default=1, ge=1, le=20)
    fixture_output: bool = False


app = FastAPI(title="VinBank Guardrail Visualizer", docs_url="/api/docs")
service = GuardrailService()


@app.post("/api/evaluate/stream")
async def evaluate_stream(body: EvaluateBody):
    request = GuardrailRequest(
        text=body.text,
        user_id=body.user_id,
        destination=body.destination,
        burst_count=body.burst_count,
        fixture_output=body.fixture_output,
    )

    async def stream():
        async for event in service.evaluate(request):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/")
async def root():
    return RedirectResponse("/visualizer/")


app.mount("/outputs", StaticFiles(directory=ROOT / "outputs"), name="outputs")
app.mount("/visualizer", StaticFiles(directory=ROOT / "visualizer", html=True), name="visualizer")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8765")),
        log_level="info",
    )
