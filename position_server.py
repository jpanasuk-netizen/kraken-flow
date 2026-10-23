#!/usr/bin/env python3
"""Kraken Flow position helper — READ-ONLY, stdlib only.
Reads KRAKEN_API_KEY / KRAKEN_PRIVATE_KEY from the environment or a .env file next to this script
(use a query-only key: Query Funds + Query Open Orders & Trades, NO trading permissions).
Serves sanitized JSON at http://127.0.0.1:8787/position (no account IDs, txids or order IDs).
Keys can also be saved from the app (File > Keys...): they are POSTed to this helper on 127.0.0.1 only,
written to the gitignored .env with owner-only permissions, and never sent back (only the last 4 chars of the key).
It only calls OpenPositions, TradeBalance and OpenOrders. It never places, edits or cancels orders."""
import os, time, base64, hashlib, hmac, json, urllib.parse, urllib.request, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, '.env')
KEY = SEC = ''
def read_env():
    d = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); d[k.strip()] = v.strip().strip('"\'')
    return d
def load_keys():
    global KEY, SEC
    d = read_env()
    KEY = d.get('KRAKEN_API_KEY') or os.environ.get('KRAKEN_API_KEY', '')
    SEC = d.get('KRAKEN_PRIVATE_KEY') or os.environ.get('KRAKEN_PRIVATE_KEY', '')
    if 'your_read_only' in KEY: KEY = SEC = ''
def save_keys(key, sec):
    """Write .env (owner-only permissions where the OS supports it)."""
    body = f'KRAKEN_API_KEY={key}\nKRAKEN_PRIVATE_KEY={sec}\n' if key else ''
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write(body)
    try: os.chmod(ENV, 0o600)
    except OSError: pass
    if os.name == 'nt':   # restrict to current user on Windows
        try:
            import subprocess; u = os.environ.get('USERNAME', '')
            if u: subprocess.run(['icacls', ENV, '/inheritance:r', '/grant:r', f'{u}:F'], capture_output=True)
        except Exception: pass
    if not key: os.environ.pop('KRAKEN_API_KEY', None); os.environ.pop('KRAKEN_PRIVATE_KEY', None)
    load_keys(); CACHE.update(t=0, v=None)
def masked(): return {'configured': bool(KEY and SEC), 'key_last4': KEY[-4:] if KEY else None}
load_keys()
ALLOWED = {'OpenPositions', 'TradeBalance', 'OpenOrders'}   # read-only allowlist
LIQ_ML = 40.0   # Kraken liquidates near 40% margin level (used only for the labelled estimate)
LOCK = threading.Lock(); CACHE = {'t': 0, 'v': None}
def priv(method, data=None):
    if method not in ALLOWED: raise ValueError('blocked: not a read-only endpoint')
    data = dict(data or {}); data['nonce'] = str(int(time.time() * 1000))
    path = '/0/private/' + method; body = urllib.parse.urlencode(data)
    sha = hashlib.sha256((data['nonce'] + body).encode()).digest()
    sig = base64.b64encode(hmac.new(base64.b64decode(SEC), path.encode() + sha, hashlib.sha512).digest())
    req = urllib.request.Request('https://api.kraken.com' + path, body.encode(), {'API-Key': KEY, 'API-Sign': sig})
    r = json.load(urllib.request.urlopen(req, timeout=10))
    if r.get('error'): raise RuntimeError(', '.join(r['error']))
    return r['result']

def snapshot():
    with LOCK:
        if CACHE['v'] and time.time() - CACHE['t'] < 5: return CACHE['v']
        if not KEY or not SEC:
            return {'ok': False, 'nokeys': True, 'updated': int(time.time())}
        try:
            pos = priv('OpenPositions', {'docalcs': 'true'}); tb = priv('TradeBalance'); oo = priv('OpenOrders')
            groups = {}
            for p in pos.values():
                vol = float(p['vol']) - float(p['vol_closed']); k = (p['pair'], p['type'])
                g = groups.setdefault(k, {'pair': p['pair'].split(':')[0], 'side': 'long' if p['type'] == 'buy' else 'short',
                                          'size': 0.0, 'cost': 0.0, 'value': 0.0, 'net': 0.0, 'margin': 0.0, 'fees': 0.0, 'lots': 0})
                g['size'] += vol; g['cost'] += float(p['cost']); g['value'] += float(p.get('value') or 0)
                g['net'] += float(p.get('net') or 0); g['margin'] += float(p['margin']); g['fees'] += float(p['fee']); g['lots'] += 1
            e, m = float(tb.get('e', 0)), float(tb.get('m', 0)); out = []
            for g in groups.values():
                s = g['size'] or 1
                g['avg_entry'] = g['cost'] / s; g['price'] = g['value'] / s if g['value'] else None
                g['pnl_pct'] = g['net'] / g['cost'] * 100 if g['cost'] else 0
                g['leverage'] = g['cost'] / g['margin'] if g['margin'] else None
                g['liq_est'] = None
                if len(groups) == 1 and g['price'] and m:   # estimate only when one pair/side is open
                    room = e - LIQ_ML / 100 * m
                    g['liq_est'] = g['price'] - room / s if g['side'] == 'long' else g['price'] + room / s
                out.append({k: (round(v, 6) if isinstance(v, float) else v) for k, v in g.items()})
            v = {'ok': True, 'updated': int(time.time()), 'positions': out,
                 'account': {'equity': float(tb.get('e', 0)), 'free_margin': float(tb.get('mf', 0)),
                             'margin_used': m, 'margin_level': float(tb['ml']) if tb.get('ml') else None,
                             'unrealized': float(tb.get('n', 0)), 'trade_balance': float(tb.get('tb', 0))},
                 'open_orders': len(oo.get('open', {})), 'liq_note': f'estimate: margin level {LIQ_ML:.0f}%, other balances unchanged'}
        except Exception as ex:
            v = {'ok': False, 'updated': int(time.time()), 'error': type(ex).__name__ + ': ' + str(ex)[:120]}
        CACHE.update(t=time.time(), v=v); return v

class H(BaseHTTPRequestHandler):
    def _origin_ok(self):
        # Only the local Kraken Flow page (file:// => Origin "null") or local tools (no Origin) may talk to us.
        o = self.headers.get('Origin')
        return o in (None, 'null') or o.startswith('http://127.0.0.1') or o.startswith('http://localhost')
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json'); self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin') or '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'); self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true'); self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self):
        if not self._origin_ok(): return self._send(403, {'ok': False, 'error': 'origin not allowed'})
        self._send(204 if False else 200, {})
    def do_GET(self):
        if not self._origin_ok(): return self._send(403, {'ok': False, 'error': 'origin not allowed'})
        p = self.path.split('?')[0]
        if p == '/position': self._send(200, snapshot())
        elif p == '/keys': self._send(200, masked())
        else: self._send(404, {'ok': False, 'error': 'not found'})
    def do_POST(self):
        if not self._origin_ok(): return self._send(403, {'ok': False, 'error': 'origin not allowed'})
        p = self.path.split('?')[0]
        try: body = json.loads(self.rfile.read(min(int(self.headers.get('Content-Length') or 0), 4096)) or b'{}')
        except Exception: body = {}
        if p == '/keys':
            k, s_ = str(body.get('key', '')).strip(), str(body.get('secret', '')).strip()
            try: ok = bool(k) and len(base64.b64decode(s_, validate=True)) > 0
            except Exception: ok = False
            if not ok: return self._send(400, {'ok': False, 'error': 'key and a valid base64 secret are required'})
            save_keys(k, s_); return self._send(200, {'ok': True, **masked()})
        if p == '/keys/clear': save_keys('', ''); return self._send(200, {'ok': True, **masked()})
        if p == '/keys/test':
            if not (KEY and SEC): return self._send(200, {'ok': False, 'error': 'no keys saved'})
            try: priv('TradeBalance'); return self._send(200, {'ok': True, 'message': 'Kraken accepted the key (read access works)'})
            except Exception as ex: return self._send(200, {'ok': False, 'error': type(ex).__name__ + ': ' + str(ex)[:120]})
        self._send(404, {'ok': False, 'error': 'not found'})
    def log_message(self, *a): pass

if __name__ == '__main__':
    if not KEY or not SEC: print('No keys yet - add a READ-ONLY key in Kraken Flow (File > Keys...) or copy .env.example to .env.')
    print('Kraken Flow position helper (read-only) on http://127.0.0.1:8787/position')
    ThreadingHTTPServer(('127.0.0.1', 8787), H).serve_forever()
