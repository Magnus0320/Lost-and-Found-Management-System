"""Assert every route declares typed input and a response_model.

Run: python scripts/audit_routes.py
Exits non-zero if any route returns an untyped body or accepts an unvalidated
request body.
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("SECRET_KEY", "audit-only")
os.environ.setdefault("RUN_MIGRATIONS_ON_STARTUP", "false")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

SKIP = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

spec = app.openapi()
rows, failures = [], []

for path, ops in sorted(spec["paths"].items()):
    if path in SKIP:
        continue
    for method, op in sorted(ops.items()):
        ok_resp = False
        for code in ("200", "201"):
            content = op.get("responses", {}).get(code, {}).get("content", {})
            schema = content.get("application/json", {}).get("schema", {})
            if "$ref" in schema or schema.get("items", {}).get("$ref"):
                ok_resp = True
        body = op.get("requestBody")
        has_body = body is not None
        body_typed = bool(
            has_body
            and "$ref"
            in str(body.get("content", {}).get("application/json", {}).get("schema", {}))
        )
        params = op.get("parameters", [])
        typed_params = all("schema" in p for p in params)

        if not ok_resp:
            failures.append(f"{method.upper()} {path}: no typed response_model")
        if has_body and not body_typed:
            failures.append(f"{method.upper()} {path}: request body is not a schema $ref")
        if not typed_params:
            failures.append(f"{method.upper()} {path}: untyped query/path parameter")

        rows.append(
            (
                method.upper(),
                path,
                "yes" if has_body else "-",
                "yes" if body_typed else ("-" if not has_body else "NO"),
                str(len(params)),
                "yes" if ok_resp else "NO",
            )
        )

hdr = ("METHOD", "PATH", "BODY", "BODY-TYPED", "PARAMS", "RESP-MODEL")
width = [max(len(r[i]) for r in [hdr, *rows]) for i in range(6)]
line = "  ".join(h.ljust(width[i]) for i, h in enumerate(hdr))
print(line)
print("-" * len(line))
for r in rows:
    print("  ".join(r[i].ljust(width[i]) for i in range(6)))

print(f"\n{len(rows)} routes audited")
if failures:
    print("\nFAILURES:")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("PASS: every route has a response_model; every request body is a Pydantic schema.")
