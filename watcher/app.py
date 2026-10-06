"""Read-only FastAPI dashboard. Mutations are local CLI operations, not public routes."""
from __future__ import annotations
import asyncio
import hmac
import json
import os
import random
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .collector import archive_rows, poll
from .source import Client
from .store import Store

ROOT = Path(__file__).resolve().parent.parent

def create_app(db_path: str = 'data/live.sqlite3', config_path: str = 'config/monitor.json', polling: bool = False) -> FastAPI:
    store = Store(db_path)
    config = json.loads(Path(config_path).read_text(encoding='utf-8')) if Path(config_path).exists() else {}
    if polling and not config:
        raise ValueError('polling requires an explicit readable configuration')
    stop = asyncio.Event()

    async def worker():
        client = Client(config)
        failures = 0
        try:
            while not stop.is_set():
                result = await asyncio.to_thread(poll, store, client, config)
                failures = 0 if result['status'] == 'SUCCESS' else min(failures + 1, 5)
                interval = max(60, float(config.get('poll_seconds', 120)))
                delay = max(min(3600, interval * 2 ** failures), result['retry_after'])
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay + random.uniform(0, interval * .1))
                except asyncio.TimeoutError:
                    pass
        finally:
            client.close()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker()) if polling else None
        yield
        stop.set()
        if task:
            await task

    app = FastAPI(title='CANNJudgeWatcher · Observed Peak', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    token = os.environ.get('WATCHER_TOKEN', '')

    @app.middleware('http')
    async def security(request: Request, call_next):
        if request.url.path.startswith('/api/') and token:
            provided = request.headers.get('Authorization', '')
            if not hmac.compare_digest(provided, 'Bearer ' + token):
                return JSONResponse({'detail': '访问令牌缺失或无效'}, status_code=401)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': '未找到对应记录'}, status_code=404)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'collector_enabled': polling}

    @app.get('/api/scopes')
    def scopes():
        return {'scopes': store.scopes(), 'collector_enabled': polling, 'poll_seconds': config.get('poll_seconds', 120)}

    @app.get('/api/board/{sid}')
    def board(sid: str):
        return store.board(sid)

    @app.get('/api/history/{sid}')
    def history(sid: str, team: str, limit: int = 200, before: str | None = None):
        try:
            return store.history(sid, team, limit, before)
        except ValueError:
            raise HTTPException(400, 'invalid history cursor')

    @app.get('/api/evidence/{eid}')
    def evidence(eid: str):
        return store.evidence(eid)

    @app.get('/api/archive/{sid}')
    def archive(sid: str, team: str | None = None, limit: int = 100, offset: int = 0):
        return archive_rows(store, sid, team, limit, offset)

    @app.get('/api/runs')
    def runs():
        return {'runs': store.runs()}

    @app.get('/api/export')
    def export():
        return StreamingResponse(store.export(), media_type='application/x-ndjson',
                                 headers={'Content-Disposition': 'attachment; filename="observed-snapshots.jsonl"'})

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web/index.html')

    app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')
    return app
