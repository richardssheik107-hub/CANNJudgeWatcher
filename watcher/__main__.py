from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .collector import backfill, poll
from .core import dumps
from .demo import seed
from .source import Client, matches
from .store import Store


def main():
    parser = argparse.ArgumentParser(description='CANNJudgeWatcher: read-only observed peak monitor')
    parser.add_argument('--db', help='SQLite path (demo and live use different defaults)')
    parser.add_argument('--config', default='config/monitor.json')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve'); serve.add_argument('--host', default='127.0.0.1'); serve.add_argument('--port', type=int, default=8088)
    serve.add_argument('--poll', action='store_true')
    sub.add_parser('demo'); sub.add_parser('discover'); sub.add_parser('poll')
    sub.add_parser('scopes')
    exp = sub.add_parser('export'); exp.add_argument('output')
    imp = sub.add_parser('import'); imp.add_argument('input')
    bak = sub.add_parser('backup'); bak.add_argument('output')
    history = sub.add_parser('backfill'); history.add_argument('scope_id'); history.add_argument('--max-pages', type=int, default=10)
    history.add_argument('--start-skip', type=int, default=0)
    args = parser.parse_args()
    db = args.db or ('data/demo.sqlite3' if args.command == 'demo' else 'data/live.sqlite3')
    store = Store(db)
    if args.command == 'serve':
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(db, args.config, args.poll), host=args.host, port=args.port, workers=1)
    elif args.command == 'demo':
        seed(store)
        print('Synthetic demo ready. Start: python -m watcher --db data/demo.sqlite3 serve')
    elif args.command == 'scopes':
        print(dumps(store.scopes()))
    elif args.command == 'export':
        with Path(args.output).open('w', encoding='utf-8') as f:
            f.writelines(store.export())
        print('Exported normalized, redacted snapshots (not source code).')
    elif args.command == 'import':
        count = 0
        with Path(args.input).open(encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    store.ingest(json.loads(line), imported=True); count += 1
        print(dumps({'imported_lines': count, 'provenance': 'operator-provided; not authenticated by the organizer'}))
    elif args.command == 'backup':
        store.backup(args.output); print('Consistent SQLite backup complete.')
    else:
        config = json.loads(Path(args.config).read_text(encoding='utf-8'))
        client = Client(config)
        try:
            if args.command == 'discover':
                results = [{'id': c['_id'], 'slug': c.get('name'), 'title': c.get('title'),
                            'start_time': c.get('start_time'), 'end_time': c.get('end_time'),
                            'problem_ids': [p.get('problem_id') for p in c.get('problems', [])],
                            'selected': matches(c, config)} for c in client.discover()]
                print(dumps(results))
            elif args.command == 'poll':
                result = poll(store, client, config); print(dumps(result))
                if result['status'] not in ('SUCCESS', 'SKIPPED'):
                    raise SystemExit(1)
            else:
                print(dumps(backfill(store, client, args.scope_id, args.max_pages, args.start_skip)))
        finally:
            client.close()

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as e:
        print(f'{type(e).__name__}: {e}', file=sys.stderr)
        raise SystemExit(1)
