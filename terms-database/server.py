#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["flask"]
# ///
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from flask import Flask, request, jsonify, render_template
import search as s

app = Flask(__name__)

def _connect():
    con = sqlite3.connect(s.DB)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def do_search(q, loc, src, limit):
    rows = s.search(q, loc=loc, src=src, limit=limit)
    return [{'zh': r['zh'], 'en': r['en'], 'loc': r['loc'] or None, 'source': r['source']} for r in rows]


def do_sources():
    with _connect() as con:
        rows = con.execute(
            'SELECT source, COUNT(*) AS cnt FROM terms GROUP BY source ORDER BY cnt DESC'
        ).fetchall()
    return [{'source': r[0], 'count': r[1]} for r in rows]

@app.route('/search')
def search():
    try:
        q = request.args.get('q', '')
        loc = request.args.get('loc')
        src = request.args.get('src')
        limit = request.args.get('limit', type=int)
        results = do_search(q, loc, src, limit)
        return jsonify({'count': len(results), 'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sources')
def sources():
    try:
        sources = do_sources()
        return jsonify(sources)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sources.html')
def sources_html():
    try:
        sources = do_sources()
        total = sum(s['count'] for s in sources)
        return render_template('sources.html', sources=sources, total=total)
    except Exception as e:
        return render_template('sources.html', sources=[], total=0, error=str(e))

@app.route('/')
def ui():
    q = request.args.get('q', '')
    loc = request.args.get('loc', '')
    src = request.args.get('src', '')
    limit = request.args.get('limit', '')
    searched = bool(request.args)
    results = []
    count = 0
    error = None
    if searched and (q or loc or src):
        try:
            lim = int(limit) if limit else None
            results = do_search(q, loc or None, src or None, lim)
            count = len(results)
        except Exception as e:
            error = str(e)
    return render_template('index.html', q=q, loc=loc, src=src, limit=limit,
                           searched=searched, results=results, count=count, error=error)

if __name__ == '__main__':
    app.run(port=8910)
