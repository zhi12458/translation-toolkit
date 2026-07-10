#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import duckdb
from flask import Flask, request, jsonify, render_template
import search as s

app = Flask(__name__)

def do_search(q, loc, src, limit):
    with duckdb.connect(s.DB, read_only=True) as con:
        rows = s.search(con, q, loc, src, limit)
    return [{'zh': r[0], 'en': r[1], 'loc': r[2] or None, 'source': r[3]} for r in rows]

def do_sources():
    with duckdb.connect(s.DB, read_only=True) as con:
        rows = con.execute(
            'SELECT source, COUNT(*) AS cnt FROM unified_terms_flat GROUP BY source ORDER BY cnt DESC'
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
