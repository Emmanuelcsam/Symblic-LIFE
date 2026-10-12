#!/usr/bin/env python3
"""LIFE research run: one question, one light model, one worker node, printed as ONE JSON object. Calls a model only when
bin/life-tick.py runs it (a node slot); importing it does nothing.

    life-research.py --model MODEL --node NODE --question TEXT

Wraps local_research.research (search through SearXNG on the host, page reads through the safe-fetch path, every
generation through fleet_runner.launch on NODE) with LIFE's bounds: RESEARCH_TOOLS tool uses, RESEARCH_STEP_TIMEOUT
seconds per generation (local_research.STEP_TIMEOUT is read at call time), and at most RESEARCH_GENERATIONS model
launches: a further launch raises model_call_limit and the run reports that error. It writes no report into the live
checkout (bin/local-research would write local_research_data/). Every launch is recorded with SIGTERM and SIGINT
blocked, so a signal arriving during a launch is handled only once the new run id is recorded; on SIGTERM or SIGINT it
cancels every fleet-runner run it started (fleet_runner.cancel) before exiting, so a killed research run never keeps a
worker node's only Ollama slot; every OTHER exit (an exception, a normal return) also cancels, in a bounded final phase, every
the fleet runner run it started (cancelling an ended run is harmless). Prints exactly {"model", "node", "answer", "sources":
[{"url", "title"}], "steps", "error"}: steps = the number of model launches it made (LAUNCHES). The platform's result
is validated before anything is converted: a result that is not an object, an answer that is not a string, a source
list that is not a list of objects with a string url, or a steps value that is not a list is the error
"contract: ..." (the tick records a contract outcome), never coerced. A URL longer than URL_MAX is dropped, never
shortened; titles are cut to 200 characters (display only). The question is passed as the operative text the operator
wrote (life_common.plain_line: control characters and runs of white space only; braces and backticks kept).
"""
import sys
sys.dont_write_bytecode = True                  # no .pyc is ever written under bin/ (kit_sha256 hashes __pycache__)
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import life_common as L  # noqa: E402

STARTED = []
LAUNCHES = [0]


def main(argv):
    p = argparse.ArgumentParser(prog='life-research.py')
    p.add_argument('--model', required=True)
    p.add_argument('--node', required=True, choices=L.NODES)
    p.add_argument('--question', required=True)
    a = p.parse_args(argv)
    sys.path.insert(0, L.REPO)
    import fleet_runner as ba
    import local_research as lr
    launch = ba.launch
    masked = {signal.SIGTERM, signal.SIGINT}

    def tracked_launch(req, *args, **kwargs):
        if LAUNCHES[0] >= L.RESEARCH_GENERATIONS:
            raise RuntimeError(f'model_call_limit: more than {L.RESEARCH_GENERATIONS} generations')
        LAUNCHES[0] += 1
        signal.pthread_sigmask(signal.SIG_BLOCK, masked)
        try:
            row = launch(req, *args, **kwargs)
            if isinstance(row, dict) and row.get('id'):
                STARTED.append(row['id'])
        finally:
            signal.pthread_sigmask(signal.SIG_UNBLOCK, masked)
        return row

    def cancel_started():
        for rid in list(STARTED):
            try:
                ba.cancel({'id': rid})
            except Exception:  # noqa: BLE001 - best effort; the fleet runner's unit RuntimeMaxSec bounds it anyway
                pass

    def on_term(signum, _frame):
        cancel_started()
        os._exit(128 + signum)

    ba.launch = tracked_launch
    lr.STEP_TIMEOUT = L.RESEARCH_STEP_TIMEOUT
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    out = {'model': a.model, 'node': a.node, 'answer': '', 'sources': [], 'steps': 0, 'error': ''}
    try:
        res = lr.research(L.plain_line(a.question, L.QUESTION_CHARS), a.model, a.node, L.RESEARCH_TOOLS)
        sources = res.get('sources') if isinstance(res, dict) else None
        if not isinstance(res, dict):
            out['error'] = 'contract: research returned no result object'
        elif not isinstance(res.get('answer', ''), str) or not isinstance(res.get('error', ''), (str, type(None))):
            out['error'] = 'contract: the answer or error is not a string'
        elif not isinstance(sources, list) or not all(isinstance(s, dict) and isinstance(s.get('url'), str) for s in sources):
            out['error'] = 'contract: the sources are not a list of objects with a string url'
        elif not isinstance(res.get('steps', []), list):
            out['error'] = 'contract: steps is not a list'
        else:
            out['answer'] = (res.get('answer') or '')[:L.ANSWER_CHARS]
            out['sources'] = [{'url': s['url'], 'title': str(s.get('title') or '')[:200]}
                              for s in sources if len(s['url']) <= L.URL_MAX][:20]
            out['error'] = (res.get('error') or '')[:300]
    except Exception as exc:  # noqa: BLE001 - reported as the research error (LIFE classifies it)
        out['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, masked)
        cancel_started()                     # every exit path settles every run it started
    out['steps'] = LAUNCHES[0]
    print(json.dumps(out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
