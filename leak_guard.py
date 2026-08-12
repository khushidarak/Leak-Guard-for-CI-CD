"""
Leak-Guard: Static Resource-Leak Detector
-------------------------------------------
A lightweight, local static-analysis check that scans Python source code
for resources (files, DB connections, sockets) that are opened but never
safely closed.

Given a chunk of Python source code, this script:
 1. Parses it into an AST (no external parser dependency).
 2. Tracks every `x = open(...)` / `x = sqlite3.connect(...)` /
    `x = socket.socket(...)`-style resource-opening call.
 3. Checks whether each one is closed via a `with` block, or a
    `x.close()` call inside `try/finally`.
 4. Reports leaks and prints a ready-to-apply fix suggestion.

Usage:
    python leak_guard.py

No external API calls or dependencies are used -- scanning runs 100% locally.
"""

import ast


# callable name (the trailing attribute, or bare name) -> resource type
RESOURCE_PATTERNS = {
    "open": "file handle",
    "connect": "connection (db/socket)",
    "socket": "raw socket",
    "urlopen": "network stream",
}


def _callable_name(call_node: ast.Call):
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _LeakVisitor(ast.NodeVisitor):
    """Walks the AST tracking open() / close() calls per function scope."""

    def __init__(self, source):
        self.source = source
        self.leaks = []
        self.scope_stack = []   # list of dicts: {resources, closed_all, closed_finally}
        self.in_finally = 0

    def _enter_scope(self, node):
        self.scope_stack.append({"resources": [], "closed_all": set(), "closed_finally": set()})
        self.generic_visit(node)
        self._exit_scope()

    def visit_Module(self, node):
        self._enter_scope(node)

    def visit_FunctionDef(self, node):
        self._enter_scope(node)

    def visit_AsyncFunctionDef(self, node):
        self._enter_scope(node)

    def _exit_scope(self):
        scope = self.scope_stack.pop()
        for res in scope["resources"]:
            name = res["name"]
            if name in scope["closed_finally"]:
                continue  # safely closed -> not a leak
            elif name in scope["closed_all"]:
                severity = "MEDIUM"
                note = "closed, but not inside try/finally -- leaks on exception"
            else:
                severity = "HIGH"
                note = "never closed on any path"
            call_src = ast.get_source_segment(self.source, res["node"].value)
            self.leaks.append({
                "line": res["node"].lineno,
                "var": name,
                "type": res["rtype"],
                "severity": severity,
                "note": note,
                "fix": f"with {call_src} as {name}:\n    ...  # move code using '{name}' here",
            })

    def visit_Try(self, node):
        for stmt in node.body:
            self.visit(stmt)
        for h in node.handlers:
            self.visit(h)
        for stmt in node.orelse:
            self.visit(stmt)
        self.in_finally += 1
        for stmt in node.finalbody:
            self.visit(stmt)
        self.in_finally -= 1

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Call) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = _callable_name(node.value)
            rtype = RESOURCE_PATTERNS.get(name)
            if rtype and self.scope_stack:
                self.scope_stack[-1]["resources"].append(
                    {"name": node.targets[0].id, "rtype": rtype, "node": node}
                )
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "close" and isinstance(func.value, ast.Name) and self.scope_stack:
            scope = self.scope_stack[-1]
            scope["closed_all"].add(func.value.id)
            if self.in_finally:
                scope["closed_finally"].add(func.value.id)
        self.generic_visit(node)


def scan_code(source: str) -> list[dict]:
    """Scan a string of Python source code and return a list of leak findings."""
    tree = ast.parse(source)
    visitor = _LeakVisitor(source)
    visitor.visit(tree)
    return visitor.leaks


if __name__ == "__main__":
    sample_code = '''
import sqlite3

def export_users(db_path, out_path):
    f = open(out_path, "w")
    conn = sqlite3.connect(db_path)
    for row in conn.execute("SELECT * FROM users"):
        f.write(str(row))
    return out_path

def safe_read(path):
    with open(path) as f:
        return f.read()
'''

    findings = scan_code(sample_code)

    print("=" * 60)
    print("LEAK-GUARD: STATIC RESOURCE-LEAK DETECTOR")
    print("=" * 60)
    print(f"\nScanned {len(sample_code.splitlines())} lines -> "
          f"{len(findings)} finding(s)\n")

    for leak in findings:
        print(f"[{leak['severity']}] line {leak['line']}: '{leak['var']}' "
              f"({leak['type']}) -- {leak['note']}")
        print("  Suggested fix:")
        for line in leak["fix"].splitlines():
            print(f"    {line}")
        print()

    if not findings:
        print("No leaks found.")
