"""
FastAPI web server — serves the browser UI and REST/WebSocket API.
All real-time progress (batch + email) is pushed via WebSocket.
"""

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from fastapi import FastAPI, File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import app.config as cfg
import app.checkpoint as checkpoint_mod
from app.classifier import (
    classify_message, check_ollama, warmup_model, strip_html,
    feedback_store, result_cache,
    set_extra_criteria, set_custom_criteria,
    get_extra_criteria, get_custom_criteria,
    determine_status, should_notify_email,
)
from app.email_reader import EmailMonitor
from app.excel_loader import load_messages

# JSON sanitizer

def _san(obj):
    """Recursively replace float NaN/Inf with None so JSONResponse never crashes."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _san(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_san(v) for v in obj]
    return obj


# App instance

app_inst = FastAPI(title="MC Auto-Analysis", version="1.0")

_STATIC = Path(__file__).parent / "static"
app_inst.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

# Event loop (stored at startup for use in sync threads)

_event_loop: Optional[asyncio.AbstractEventLoop] = None


@app_inst.on_event("startup")
async def _on_startup():
    global _event_loop
    _event_loop = asyncio.get_running_loop()


# WebSocket connection manager

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()

# Application state

_email_monitor: Optional[EmailMonitor] = None
_excel_batch_running = False
_email_batch_running = False
_all_results: list[dict] = []
_executor = ThreadPoolExecutor(max_workers=cfg.WORKERS)

# Stop events
_excel_stop_event = threading.Event()
_email_stop_event = threading.Event()

# Pending queued jobs (at most 1 per type)
_excel_pending: Optional[dict] = None
_email_pending: Optional[dict] = None


# Routes

@app_inst.get("/")
async def root():
    return FileResponse(str(_STATIC / "index.html"))


@app_inst.get("/message")
async def message_detail(id: str = Query(...)):
    """Render a full-page message detail view (opens in new tab)."""
    result = next((r for r in _all_results if str(r.get("ID", "")) == str(id)), None)
    if not result:
        return HTMLResponse("""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Not Found — MailAI</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="/static/style.css" rel="stylesheet">
</head><body>
<nav class="navbar"><span class="navbar-brandM"><span class="dot-red">M</span>ail<span class="dot-yellow">@</span>AI</span></nav>
<div class="brand-bar"><span></span><span></span><span></span><span></span></div>
<div class="container-fluid px-3 mt-4"><div class="card p-4 text-center">
  <h4 class="text-danger">Message not found</h4>
  <p class="text-muted small">ID not present in current session results.</p>
  <button class="btn btn-outline-secondary btn-sm" onclick="window.close()">Close</button>
</div></div></body></html>""", status_code=404)

    def esc(s):
        return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    batch_src = result.get("_batch_source", "")
    src_badge_cls = {"excel": "bg-success", "email": "bg-primary", "uploaded": "bg-secondary"}.get(batch_src, "bg-secondary")
    ai_src = result.get("_source", "ai")
    ai_src_cls = {"rules": "bg-info", "cache": "bg-secondary", "fallback": "bg-danger"}.get(ai_src, "bg-primary")

    fields = [
        ("ID",         esc(result.get("ID", ""))),
        ("Date",       esc(result.get("Created", ""))),
        ("Type",       esc(result.get("Typ", "") or "—")),
        ("Priority",   esc(result.get("Priorytet", "") or "—")),
        ("Service",    esc(result.get("Serwis", "") or "—")),
        ("Action",     esc(result.get("Akcja", "") or "—")),
        ("Status",     esc(result.get("Status", "") or "—")),
        ("Confidence", esc(f"{result.get('Confidence', '?')}/10")),
        ("Deadline",   esc(result.get("Data_wazna", "") or "—")),
        ("Email Alert", "YES" if result.get("Email_alert") else "no"),
    ]
    if result.get("Subject"):
        fields.append(("Subject", esc(result.get("Subject", ""))))
    if result.get("Sender"):
        fields.append(("Sender",  esc(result.get("Sender",  ""))))

    typ = esc(result.get("Typ", "") or "unclear")
    pri = esc(result.get("Priorytet", "") or "")

    fields_html = "".join(
        f'<div class="col-6 col-sm-4 col-md-3 col-lg-2 mb-2">'
        f'<div class="dm-field h-100"><div class="dm-field-label">{lbl}</div>'
        f'<div class="dm-field-val">{val}</div></div></div>'
        for lbl, val in fields
    )

    summary = esc(result.get("Streszczenie", "") or "—")
    full_msg = esc(result.get("FullMessage", "") or "(message body not stored)")
    msg_id   = esc(str(result.get("ID", "")))
    msg_date = esc(result.get("Created", ""))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Message {msg_id} — MailAI</title>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Merriweather:wght@400;700&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <link href="/static/style.css" rel="stylesheet">
  <style>
    @media print {{
      .no-print {{ display: none !important; }}
      .navbar, .brand-bar, footer {{ display: none !important; }}
      .dm-message-block {{ max-height: none !important; overflow: visible !important; }}
      body {{ background: #fff; }}
    }}
  </style>
</head>
<body>

<nav class="navbar no-print">
  <span class="navbar-brandM"><span class="dot-red">M</span>ail<span class="dot-yellow">@</span>AI</span>
  <div class="d-flex align-items-center gap-2">
    <span class="badge {src_badge_cls}">{esc(batch_src) or "—"}</span>
    <span class="badge {ai_src_cls}">{esc(ai_src)}</span>
  </div>
</nav>
<div class="brand-bar no-print"><span></span><span></span><span></span><span></span></div>

<div class="container-fluid px-3 mt-3">

  <!-- Header card -->
  <div class="card mb-3">
    <div class="card-header d-flex justify-content-between align-items-center">
      <div>
        <span class="dm-section mb-0" style="border:none;padding:0">Message</span>
        <strong class="ms-2" style="font-family:'Merriweather',serif;font-size:15px">{msg_id}</strong>
        <span class="badge badge-{esc(result.get('Typ',''))} ms-2">{typ}</span>
        <span class="badge badge-{pri} ms-1">{pri}</span>
        <span class="text-muted ms-2" style="font-size:12px">{msg_date}</span>
      </div>
      <div class="d-flex gap-2 no-print">
        <button class="btn btn-outline-secondary btn-sm" onclick="window.print()" title="Print">
          <i class="bi bi-printer me-1"></i>Print
        </button>
        <button class="btn btn-outline-danger btn-sm" onclick="window.close()" title="Close tab">
          <i class="bi bi-x-lg me-1"></i>Close
        </button>
      </div>
    </div>
  </div>

  <!-- Classification fields -->
  <div class="card mb-3">
    <div class="card-header"><i class="bi bi-tags me-1"></i>Classification</div>
    <div class="card-body">
      <div class="row g-2">{fields_html}</div>
    </div>
  </div>

  <!-- Summary -->
  <div class="card mb-3">
    <div class="card-header"><i class="bi bi-card-text me-1"></i>Summary</div>
    <div class="card-body p-0">
      <div class="dm-text-block" style="border:none;margin:0">{summary}</div>
    </div>
  </div>

  <!-- Original message -->
  <div class="card mb-3">
    <div class="card-header"><i class="bi bi-envelope-open me-1"></i>Original Message</div>
    <div class="card-body p-0">
      <div class="dm-message-block" style="border:none;max-height:55vh">{full_msg}</div>
    </div>
  </div>

</div>

<footer class="footer mt-auto py-3 bg-light border-top no-print">
  <div class="container-fluid text-center">
    <small class="text-muted">
      Designed &amp; Developed by
      <a href="https://dimon.work" target="_blank" class="text-decoration-none fw-medium">dimon.work</a>
    </small>
  </div>
</footer>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>"""
    return HTMLResponse(html)


# Setup helpers

def _get_ollama_exe() -> str:
    """Find ollama.exe from install_config.json or well-known paths."""
    config_path = Path(__file__).parent.parent / "installer" / "install_config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text("utf-8"))
            ol = data.get("ollama", "")
            if ol and Path(ol).exists():
                return ol
        except Exception:
            pass
    localappdata = os.environ.get("LOCALAPPDATA", "")
    programfiles = os.environ.get("ProgramFiles", "")
    for p in [
        Path(localappdata) / "Programs" / "Ollama" / "ollama.exe",
        Path(programfiles) / "Ollama" / "ollama.exe",
    ]:
        if p.exists():
            return str(p)
    return shutil.which("ollama") or ""


def _check_model_ready() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = r.json().get("models", [])
        return any(cfg.MODEL in m.get("name", "") for m in models)
    except Exception:
        return False


@app_inst.get("/api/setup/status")
async def setup_status():
    ollama_running = check_ollama()
    return {
        "ollama_running": ollama_running,
        "model_ready": _check_model_ready() if ollama_running else False,
        "model": cfg.MODEL,
    }


@app_inst.get("/api/setup/run")
async def setup_run():
    """SSE stream: start Ollama if needed, then pull the model."""

    async def generate():
        def evt(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        ollama_exe = _get_ollama_exe()

        # Step 1: ensure Ollama server is running
        if not check_ollama():
            if not ollama_exe:
                yield evt({"type": "error", "msg": "Ollama not found. Please reinstall."})
                return
            yield evt({"type": "status", "step": 1, "msg": "Starting Ollama server..."})
            no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                [ollama_exe, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=no_win,
            )
            for _ in range(30):
                await asyncio.sleep(1)
                if check_ollama():
                    break
            if not check_ollama():
                yield evt({"type": "error", "msg": "Ollama server failed to start. Try restarting the app."})
                return

        yield evt({"type": "status", "step": 1, "msg": "Ollama server is running."})

        # Step 2: pull model if not present
        if _check_model_ready():
            yield evt({"type": "done", "msg": "Model already available. Loading app..."})
            return

        if not ollama_exe:
            yield evt({"type": "error", "msg": "Ollama executable not found. Please reinstall."})
            return

        yield evt({"type": "status", "step": 2,
                   "msg": f"Downloading model {cfg.MODEL} (~3 GB). Please wait..."})

        proc = await asyncio.create_subprocess_exec(
            ollama_exe, "pull", cfg.MODEL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        buf = b""
        while True:
            chunk = await proc.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            parts = buf.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
            buf = parts[-1]
            for raw in parts[:-1]:
                text = raw.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                m = re.search(r"(\d+)%", text)
                pct = int(m.group(1)) if m else None
                yield evt({"type": "pull", "msg": text, "pct": pct})

        if buf.strip():
            text = buf.decode("utf-8", errors="replace").strip()
            yield evt({"type": "pull", "msg": text, "pct": None})

        await proc.wait()
        if proc.returncode == 0:
            yield evt({"type": "done", "msg": "Setup complete! Loading app..."})
        else:
            yield evt({"type": "error",
                       "msg": f"Model pull failed (exit {proc.returncode}). Check connection and try again."})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app_inst.get("/api/status")
async def api_status():
    return {
        "ollama":              check_ollama(),
        "model":               cfg.MODEL,
        "workers":             cfg.WORKERS,
        "cache_size":          result_cache.size,
        "cache_hits":          result_cache.hits,
        "results_count":       len(_all_results),
        "excel_batch_running": _excel_batch_running,
        "email_batch_running": _email_batch_running,
        "excel_queued":        _excel_pending is not None,
        "email_queued":        _email_pending is not None,
        "email":               _email_monitor.status if _email_monitor else None,
    }


@app_inst.get("/api/results")
async def api_results():
    return JSONResponse(_san(_all_results))


@app_inst.delete("/api/results")
async def api_clear_results():
    global _all_results
    _all_results = []
    checkpoint_mod.clear()
    result_cache.clear()
    return {"ok": True}


# Config

@app_inst.get("/api/config")
async def api_get_config():
    return {
        "model":             cfg.MODEL,
        "workers":           cfg.WORKERS,
        "max_retries":       cfg.MAX_RETRIES,
        "request_timeout":   cfg.REQUEST_TIMEOUT,
        "max_message_chars": cfg.MAX_MESSAGE_CHARS,
        "typ_values":        cfg.TYP_VALUES,
        "priorytet_values":  cfg.PRIORYTET_VALUES,
        "serwis_values":     cfg.SERWIS_VALUES,
        "akcja_values":      cfg.AKCJA_VALUES,
        "extra_criteria":    get_extra_criteria(),
        "custom_criteria":   get_custom_criteria(),
    }


@app_inst.post("/api/config")
async def api_set_config(body: dict):
    if "model" in body:           cfg.MODEL = body["model"]
    if "workers" in body:         cfg.WORKERS = int(body["workers"])
    if "request_timeout" in body: cfg.REQUEST_TIMEOUT = int(body["request_timeout"])
    if "typ_values" in body:      cfg.TYP_VALUES = body["typ_values"]
    if "priorytet_values" in body: cfg.PRIORYTET_VALUES = body["priorytet_values"]
    if "serwis_values" in body:   cfg.SERWIS_VALUES = body["serwis_values"]
    if "akcja_values" in body:    cfg.AKCJA_VALUES = body["akcja_values"]
    if "extra_criteria" in body:  set_extra_criteria(body["extra_criteria"])
    if "custom_criteria" in body: set_custom_criteria(body["custom_criteria"])
    return {"ok": True}


# Upload pre-classified results

@app_inst.post("/api/results/upload")
async def upload_results(file: UploadFile = File(...)):
    """Upload a pre-classified Excel (.xlsx) file and merge into current results."""
    global _all_results
    tmp_path = Path(f"_upload_results_{uuid.uuid4().hex}.xlsx")
    try:
        contents = await file.read()
        tmp_path.write_bytes(contents)
        df = pd.read_excel(tmp_path)
        if "ID" not in df.columns:
            return JSONResponse({"error": "Missing required column: ID"}, status_code=400)
        # Normalise column names (strip whitespace)
        df.columns = [str(c).strip() for c in df.columns]
        records = [_san(r) for r in df.where(pd.notnull(df), None).to_dict(orient="records")]
        # Tag as uploaded and avoid duplicates by ID
        existing_ids = {str(r.get("ID", "")) for r in _all_results}
        added = 0
        for rec in records:
            rec["_batch_source"] = "uploaded"
            if "_source" not in rec or not rec["_source"]:
                rec["_source"] = "uploaded"
            if str(rec.get("ID", "")) not in existing_ids:
                _all_results.append(rec)
                existing_ids.add(str(rec.get("ID", "")))
                added += 1
        return {"ok": True, "added": added, "total": len(records)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        tmp_path.unlink(missing_ok=True)


# Excel batch classification

@app_inst.post("/api/classify/excel")
async def classify_excel(
    file: UploadFile = File(...),
    date_from: Optional[str] = Form(None),
    date_to: Optional[str]   = Form(None),
    limit: Optional[str]     = Form(None),
):
    global _excel_batch_running, _excel_pending
    lm = None if not limit or limit in ("0", "") else int(limit)
    df_from = date_from or None
    df_to   = date_to   or None

    tmp_path = Path(f"_upload_{uuid.uuid4().hex}.xlsx")
    try:
        contents = await file.read()
        tmp_path.write_bytes(contents)
        df = load_messages(str(tmp_path), date_from=df_from, date_to=df_to, limit=lm)
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        return JSONResponse({"error": str(e)}, status_code=400)

    if _excel_batch_running:
        # Queue this job (replace any previous pending)
        _excel_pending = {"df": df, "tmp_path": tmp_path}
        await ws_manager.broadcast({"type": "excel_queued", "count": len(df)})
        return {"ok": True, "queued": True, "count": len(df)}

    _excel_stop_event.clear()
    asyncio.create_task(_run_batch(df, tmp_path))
    return {"ok": True, "queued": False, "count": len(df)}


@app_inst.post("/api/classify/excel/stop")
async def stop_excel_batch():
    global _excel_pending
    _excel_stop_event.set()
    _excel_pending = None
    return {"ok": True}


def _classify_single(args: tuple) -> tuple:
    """Called in thread pool for each row."""
    position, msg_id, created, full_msg = args
    classification = classify_message(full_msg)
    result = {
        "ID":           msg_id,
        "Created":      str(created)[:10],
        "Typ":          classification["typ"],
        "Priorytet":    classification["priorytet"],
        "Serwis":       classification["serwis"],
        "Akcja":        classification["akcja"],
        "Data_wazna":   classification["data_wazna"],
        "Streszczenie": classification["streszczenie"],
        "Status":       classification["status"],
        "Email_alert":  classification["email_alert"],
        "Confidence":   classification.get("confidence", 5),
        "_source":      classification.get("_source", "ai"),
        "_batch_source": "excel",
        "FullMessage":  strip_html(str(full_msg))[:1000],
    }
    for name, val in classification.get("_custom", {}).items():
        result[name.capitalize()] = val
    return position, result


async def _run_batch(df: pd.DataFrame, tmp_path: Path):
    global _excel_batch_running, _all_results, _excel_pending
    _excel_batch_running = True
    loop = asyncio.get_running_loop()

    try:
        ckpt = checkpoint_mod.load()
        before = len(df)
        df = df[~df["ID"].isin(ckpt.keys())].reset_index(drop=True)
        skipped = before - len(df)

        await ws_manager.broadcast({
            "type": "batch_start",
            "total": len(df) + skipped,
            "new": len(df),
            "skipped": skipped,
        })

        if df.empty:
            _all_results = list(ckpt.values())
            await ws_manager.broadcast({
                "type": "batch_done",
                "results": _san(_all_results),
                "output_file": None,
            })
            return

        await loop.run_in_executor(None, warmup_model)

        tasks = [
            (i, row["ID"], row["Created"], str(row.get("FullMessage", "")))
            for i, row in df.iterrows()
        ]
        total = len(tasks)

        queue: asyncio.Queue = asyncio.Queue()

        def _worker():
            pool = ThreadPoolExecutor(max_workers=cfg.WORKERS)
            futures = {pool.submit(_classify_single, t): t for t in tasks}
            for fut in as_completed(futures):
                if _excel_stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    loop.call_soon_threadsafe(queue.put_nowait, ("stopped", 0, None))
                    return
                try:
                    pos, result = fut.result()
                    loop.call_soon_threadsafe(queue.put_nowait, ("ok", pos, result))
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, ("err", 0, str(e)))
            pool.shutdown(wait=False)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", 0, None))

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        done = 0
        results_map: dict[int, dict] = {}
        t_start = time.time()

        while True:
            msg_type, pos, payload = await queue.get()
            if msg_type in ("done", "stopped"):
                stopped = msg_type == "stopped"
                ordered_new = [results_map[p] for p in sorted(results_map)]
                _all_results = list(ckpt.values()) + ordered_new

                out_file = "_classified_results.xlsx"
                pd.DataFrame(_all_results).to_excel(out_file, index=False, engine="openpyxl")

                await ws_manager.broadcast({
                    "type":        "batch_done",
                    "results":     _all_results,
                    "output_file": out_file,
                    "stopped":     stopped,
                })
                break
            elif msg_type == "ok":
                results_map[pos] = payload
                checkpoint_mod.save(payload["ID"], payload)
                done += 1
                elapsed = time.time() - t_start
                avg = elapsed / done
                eta = int(avg * (total - done))
                await ws_manager.broadcast({
                    "type":   "progress",
                    "done":   done,
                    "total":  total,
                    "eta":    eta,
                    "result": payload,
                })
            elif msg_type == "err":
                await ws_manager.broadcast({"type": "batch_error", "error": payload})

    except Exception as e:
        await ws_manager.broadcast({"type": "batch_error", "error": str(e)})
    finally:
        _excel_batch_running = False
        tmp_path.unlink(missing_ok=True)
        # Start queued job if any
        pending = _excel_pending
        _excel_pending = None
        if pending and not _excel_stop_event.is_set():
            _excel_stop_event.clear()
            asyncio.create_task(_run_batch(pending["df"], pending["tmp_path"]))


@app_inst.get("/api/classify/excel/download")
async def download_results():
    out_file = "_classified_results.xlsx"
    if not Path(out_file).exists():
        return JSONResponse({"error": "No results file yet"}, status_code=404)
    return FileResponse(out_file, filename="classified_results.xlsx")


# Email batch classification

def _classify_email_single(args: tuple) -> tuple:
    """Called in thread pool for each fetched email."""
    position, msg_dict = args
    classification = classify_message(msg_dict["body"])
    result = {
        "ID":           f"email_{msg_dict['uid']}",
        "Created":      (msg_dict.get("date", "") or "")[:10],
        "Subject":      msg_dict.get("subject", ""),
        "Sender":       msg_dict.get("sender", ""),
        "Typ":          classification["typ"],
        "Priorytet":    classification["priorytet"],
        "Serwis":       classification["serwis"],
        "Akcja":        classification["akcja"],
        "Data_wazna":   classification["data_wazna"],
        "Streszczenie": classification["streszczenie"],
        "Status":       classification["status"],
        "Email_alert":  classification["email_alert"],
        "Confidence":   classification.get("confidence", 5),
        "_source":      classification.get("_source", "ai"),
        "_batch_source": "email",
        "FullMessage":  msg_dict["body"][:1000],
    }
    for name, val in classification.get("_custom", {}).items():
        result[name.capitalize()] = val
    return position, result


async def _run_email_batch(messages: list[dict]):
    global _email_batch_running, _all_results, _email_pending
    _email_batch_running = True
    loop = asyncio.get_running_loop()
    total = len(messages)

    try:
        await ws_manager.broadcast({"type": "email_batch_start", "total": total})

        if not messages:
            await ws_manager.broadcast({
                "type": "email_batch_done",
                "results": _san(_all_results),
                "output_file": None,
            })
            return

        await loop.run_in_executor(None, warmup_model)

        queue: asyncio.Queue = asyncio.Queue()

        def _worker():
            pool = ThreadPoolExecutor(max_workers=cfg.WORKERS)
            futures = {
                pool.submit(_classify_email_single, (i, msg)): i
                for i, msg in enumerate(messages)
            }
            for fut in as_completed(futures):
                if _email_stop_event.is_set():
                    pool.shutdown(wait=False, cancel_futures=True)
                    loop.call_soon_threadsafe(queue.put_nowait, ("stopped", 0, None))
                    return
                try:
                    pos, result = fut.result()
                    loop.call_soon_threadsafe(queue.put_nowait, ("ok", pos, result))
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, ("err", 0, str(e)))
            pool.shutdown(wait=False)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", 0, None))

        threading.Thread(target=_worker, daemon=True).start()

        done = 0
        results_map: dict[int, dict] = {}
        t_start = time.time()

        while True:
            msg_type, pos, payload = await queue.get()
            if msg_type in ("done", "stopped"):
                ordered = [results_map[p] for p in sorted(results_map)]
                _all_results.extend(ordered)

                out_file = "_classified_results.xlsx"
                pd.DataFrame(_all_results).to_excel(out_file, index=False, engine="openpyxl")

                await ws_manager.broadcast({
                    "type":        "email_batch_done",
                    "results":     _all_results,
                    "output_file": out_file,
                    "stopped":     msg_type == "stopped",
                })
                break
            elif msg_type == "ok":
                results_map[pos] = payload
                done += 1
                elapsed = time.time() - t_start
                avg = elapsed / done
                eta = int(avg * (total - done))
                await ws_manager.broadcast({
                    "type":   "email_batch_progress",
                    "done":   done,
                    "total":  total,
                    "eta":    eta,
                    "result": payload,
                })
            elif msg_type == "err":
                await ws_manager.broadcast({"type": "email_batch_error", "error": payload})

    except Exception as e:
        await ws_manager.broadcast({"type": "email_batch_error", "error": str(e)})
    finally:
        _email_batch_running = False
        pending = _email_pending
        _email_pending = None
        if pending and not _email_stop_event.is_set():
            _email_stop_event.clear()
            asyncio.create_task(_run_email_batch(pending["messages"]))


@app_inst.post("/api/email/classify")
async def classify_email_mailbox(body: dict):
    global _email_batch_running, _email_pending
    limit      = int(body.get("limit", 200))
    date_from  = body.get("date_from") or None
    date_to    = body.get("date_to")   or None

    monitor = EmailMonitor(
        host=body["host"],
        port=int(body.get("port", 993)),
        username=body["username"],
        password=body["password"],
        folder=body.get("folder", "INBOX"),
        use_ssl=body.get("ssl", True),
        protocol=body.get("protocol", "imap"),
    )
    try:
        messages = await asyncio.get_running_loop().run_in_executor(
            None, lambda: monitor.fetch_messages(
                limit=limit, date_from=date_from, date_to=date_to
            )
        )
    except Exception as e:
        detail = traceback.format_exc()
        err_msg = str(e) or type(e).__name__
        print(f"[email/classify] fetch error:\n{detail}")
        return JSONResponse({"error": f"{type(e).__name__}: {err_msg}"}, status_code=400)

    if _email_batch_running:
        _email_pending = {"messages": messages}
        await ws_manager.broadcast({"type": "email_queued", "count": len(messages)})
        return {"ok": True, "queued": True, "count": len(messages)}

    _email_stop_event.clear()
    asyncio.create_task(_run_email_batch(messages))
    return {"ok": True, "queued": False, "count": len(messages)}


@app_inst.post("/api/email/classify/stop")
async def stop_email_batch():
    global _email_pending
    _email_stop_event.set()
    _email_pending = None
    return {"ok": True}


# Email monitor

@app_inst.post("/api/email/test")
async def test_email(body: dict):
    monitor = EmailMonitor(
        host=body["host"],
        port=int(body.get("port", 993)),
        username=body["username"],
        password=body["password"],
        folder=body.get("folder", "INBOX"),
        use_ssl=body.get("ssl", True),
        protocol=body.get("protocol", "imap"),
    )
    ok, msg = monitor.test_connection()
    return {"ok": ok, "message": msg}


@app_inst.post("/api/email/start")
async def start_email(body: dict):
    global _email_monitor
    if _email_monitor and _email_monitor.status["running"]:
        return JSONResponse({"error": "Monitor already running"}, status_code=409)

    loop = _event_loop

    def on_new_email(msg_dict: dict):
        classification = classify_message(msg_dict["body"])
        result = {
            "ID":           f"email_{msg_dict['uid']}",
            "Created":      msg_dict.get("date", "")[:10],
            "Subject":      msg_dict.get("subject", ""),
            "Sender":       msg_dict.get("sender", ""),
            "Typ":          classification["typ"],
            "Priorytet":    classification["priorytet"],
            "Serwis":       classification["serwis"],
            "Akcja":        classification["akcja"],
            "Data_wazna":   classification["data_wazna"],
            "Streszczenie": classification["streszczenie"],
            "Status":       classification["status"],
            "Email_alert":  classification["email_alert"],
            "Confidence":   classification.get("confidence", 5),
            "_source":      classification.get("_source", "ai"),
            "_batch_source": "email",
            "FullMessage":  msg_dict["body"][:500],
        }
        for name, val in classification.get("_custom", {}).items():
            result[name.capitalize()] = val
        _all_results.append(result)
        if loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": "email_classified", "result": result}),
                loop,
            )

    def on_error(err: str):
        if loop:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": "email_error", "error": err}),
                loop,
            )

    _email_monitor = EmailMonitor(
        host=body["host"],
        port=int(body.get("port", 993)),
        username=body["username"],
        password=body["password"],
        folder=body.get("folder", "INBOX"),
        poll_interval=int(body.get("poll_interval", 60)),
        use_ssl=body.get("ssl", True),
        protocol=body.get("protocol", "imap"),
        on_message=on_new_email,
        on_error=on_error,
    )
    _email_monitor.start()
    return {"ok": True, "status": _email_monitor.status}


@app_inst.post("/api/email/stop")
async def stop_email():
    global _email_monitor
    if _email_monitor:
        _email_monitor.stop()
    return {"ok": True}


@app_inst.get("/api/email/status")
async def email_status():
    if not _email_monitor:
        return {"running": False, "connected": False}
    return _email_monitor.status


# Feedback

@app_inst.get("/api/feedback")
async def list_feedback():
    return feedback_store.list_all()


@app_inst.post("/api/feedback")
async def add_feedback(body: dict):
    feedback_store.add(
        msg_id=body["id"],
        text=body.get("text", ""),
        original=body.get("original", {}),
        corrected=body.get("corrected", {}),
    )
    return {"ok": True}


@app_inst.delete("/api/feedback/{msg_id}")
async def delete_feedback(msg_id: int):
    ok = feedback_store.delete(msg_id)
    return {"ok": ok}


# WebSocket

@app_inst.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
