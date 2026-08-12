# Leak-Guard: Static Resource-Leak Detector

A lightweight, local static-analysis check for CI/CD pipelines. Scans Python
source code for resources (files, DB connections, sockets) that are opened
but never safely closed — catching leaks at build time instead of in
production.

## The problem

Unclosed files, DB connections, and sockets are easy to miss in code review
and often only surface as production issues: connection pool exhaustion,
file-descriptor leaks, degraded performance under load.

## The solution

Leak-Guard parses source code with Python's built-in `ast` module (no
external parser dependency) and tracks resource open/close pairs per
function scope:

```
Source code → AST parse → Track open()/close() per scope → Flag unclosed paths
```

1. Every `x = open(...)` / `x = sqlite3.connect(...)` / `x = socket.socket(...)`
   is treated as a candidate resource.
2. A resource is **safe** if it's opened via `with ... as x:`, or closed
   inside a `try/finally` block.
3. Otherwise it's flagged:
   - **HIGH** — never closed on any path
   - **MEDIUM** — closed, but not inside `try/finally` (leaks on exception)

## Quick start

```bash
python leak_guard.py
```

## Example output

```
LEAK-GUARD: STATIC RESOURCE-LEAK DETECTOR
============================================================

Scanned 13 lines -> 2 finding(s)

[HIGH] line 5: 'f' (file handle) -- never closed on any path
  Suggested fix:
    with open(out_path, "w") as f:
        ...  # move code using 'f' here

[HIGH] line 6: 'conn' (connection (db/socket)) -- never closed on any path
  Suggested fix:
    with sqlite3.connect(db_path) as conn:
        ...  # move code using 'conn' here
```

## Usage in your own pipeline

```python
from leak_guard import scan_code

findings = scan_code(source_code_string)
# each finding: {"line", "var", "type", "severity", "note", "fix"}

if any(f["severity"] == "HIGH" for f in findings):
    raise SystemExit(1)  # fail the build
```

## Live demo

Open `leak_guard_demo.html` in a browser — paste Python code, click
"Scan for leaks", see findings and suggested fixes instantly. (This demo
reimplements a simplified version of the same detection logic in
JavaScript so it can run client-side with zero dependencies; the real
version in `leak_guard.py` uses a proper AST rather than heuristics.)

## Roadmap

- Extend to more resource types and libraries (`requests.Session`, `boto3` clients, etc.)
- Add data-flow analysis to reduce false positives on complex branching
- GitHub Actions integration to block PRs on HIGH severity findings
- Multi-language support via Tree-sitter (Java, Go, JS)

## Built for

UCET Hackathon 2026 — Pixels to Possibilities
