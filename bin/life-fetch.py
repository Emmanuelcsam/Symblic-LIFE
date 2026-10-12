#!/usr/bin/env python3
"""LIFE source fetch: one URL through the platform's safe path, printed as ONE JSON object. No model.

    life-fetch.py URL

local_research._denied(URL) (the research deny rule) -> deep_research.safe_fetch (http(s) only, every resolved address
global, every redirect re-validated, robots honoured, a byte cap) -> the HTTP status is classified HERE, before any
text is used: 2xx -> text; 401, 403, 404, 410, 451 and every other non-2xx status not listed next -> refused; 408, 425,
429 and 5xx -> error (transient). The URL is fetched ONCE, as bytes (binary=True), and the parser is chosen from that
same response: a PDF (by its content type or path) goes through local_research.pdf_text, anything else is decoded
with the charset its content type names (else UTF-8, undecodable bytes replaced) and HTML through
local_research.page_text. The text is cut to SOURCE_TEXT_CHARS. Prints {"ok": true, "text": ...} or {"ok": false,
"kind": "refused" | "error", "detail": ...}: refused = the safe path or the status said no (RuntimeError/ResearchError:
robots, address, size, type) or an unknown fault; error = a transient network fault (OSError, URLError, timeout) or a
transient status, which LIFE retries as infra. Run by bin/life-tick.py with the dashboard's .venv Python (bs4/pypdf),
-I -B, a fixed environment, FETCH_TIMEOUT s, in its own life-fetch-*.scope with MemoryMax FETCH_MEMORY and prlimit --as.
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import codecs  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import urllib.parse  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import life_common as L  # noqa: E402

TRANSIENT = {408, 425, 429}


def classify(status):
    """'ok' | 'error' | 'refused' for an HTTP status."""
    if isinstance(status, int) and 200 <= status <= 299:
        return 'ok'
    if isinstance(status, int) and (status in TRANSIENT or 500 <= status <= 599):
        return 'error'
    return 'refused'


def main(argv):
    if len(argv) != 1 or not argv[0].startswith(('http://', 'https://')):
        print(json.dumps({'ok': False, 'kind': 'refused', 'detail': 'usage: life-fetch.py http(s)://URL'}))
        return 0
    url = argv[0]
    sys.path.insert(0, L.REPO)
    try:
        import deep_research as D
        import local_research as R
        why = R._denied(url)
        if why:
            raise RuntimeError(why)
        got = D.safe_fetch(url, binary=True)
        kind = classify(got.get('status'))
        if kind != 'ok':
            print(json.dumps({'ok': False, 'kind': kind, 'detail': f'HTTP {got.get("status")}'}))
            return 0
        ctype = str(got.get('ctype') or '').lower()
        data = got.get('data') or b''
        if 'pdf' in ctype or urllib.parse.urlsplit(url).path.lower().endswith('.pdf') or data[:5] == b'%PDF-':
            text = R.pdf_text(data)
        else:
            m = re.search(r'charset=([A-Za-z0-9._-]{1,40})', ctype)
            enc = m.group(1) if m else 'utf-8'
            try:
                codecs.lookup(enc)
            except LookupError:
                enc = 'utf-8'
            text = data.decode(enc, 'replace')
            if 'html' in ctype or text.lstrip()[:1] == '<':
                text = R.page_text(text)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        print(json.dumps({'ok': True, 'text': text[:L.SOURCE_TEXT_CHARS]}))
    except (OSError, TimeoutError) as exc:           # URLError and socket timeouts are OSError subclasses
        print(json.dumps({'ok': False, 'kind': 'error', 'detail': f'{type(exc).__name__}: {str(exc)[:200]}'}))
    except Exception as exc:  # noqa: BLE001 - RuntimeError/ResearchError refusals and anything unknown: never retried
        print(json.dumps({'ok': False, 'kind': 'refused', 'detail': f'{type(exc).__name__}: {str(exc)[:200]}'}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
