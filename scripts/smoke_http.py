"""Black-box smoke test against a running API over HTTP.

Usage: python scripts/smoke_http.py [base_url]
Unlike scripts/smoke_test.py (in-process TestClient), this talks to a real
server over the network -- used to verify the docker-compose stack.
"""
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
fails = []


def check(label, got, want):
    ok = got == want
    print(f"  [{'ok' if ok else 'FAIL'}] {label}: {got} (want {want})")
    if not ok:
        fails.append(label)
    return ok


with httpx.Client(base_url=BASE, timeout=20) as c:
    print("health / docs")
    r = c.get("/health")
    check("GET /health", r.status_code, 200)
    print("        ", r.json())
    check("GET /docs", c.get("/docs").status_code, 200)

    tag = uuid.uuid4().hex[:8]
    owner = f"owner-{tag}@campus.edu"
    finder = f"finder-{tag}@campus.edu"

    print("\nregister + verify + login (owner)")
    r = c.post("/auth/register", json={
        "email": owner, "password": "correct-horse-1", "first_name": "Asha",
        "last_name": "Rao", "roll_number": f"R{tag}", "batch": 2026,
        "course": "BTECH", "branch": "CSE"})
    check("POST /auth/register", r.status_code, 201)
    otp = r.json()["otp_debug"]
    check("POST /auth/verify-registration", c.post("/auth/verify-registration",
          json={"email": owner, "otp": otp}).status_code, 200)
    r = c.post("/auth/login", json={"email": owner, "password": "correct-horse-1"})
    check("POST /auth/login", r.status_code, 200)
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r2 = c.post("/auth/register", json={
        "email": finder, "password": "correct-horse-2", "first_name": "Vik",
        "last_name": "Singh", "roll_number": f"S{tag}", "batch": 2025,
        "course": "MTECH", "branch": "ECE"})
    c.post("/auth/verify-registration",
           json={"email": finder, "otp": r2.json()["otp_debug"]})
    hdr2 = {"Authorization": "Bearer " + c.post("/auth/login", json={
        "email": finder, "password": "correct-horse-2"}).json()["access_token"]}

    print("\nreference data")
    loc = c.post("/locations", headers=hdr,
                 json={"name": f"Library {tag}", "building": "Block C"})
    check("POST /locations", loc.status_code, 201)
    cat = c.post("/categories", headers=hdr, json={"name": f"Electronics {tag}"})
    check("POST /categories", cat.status_code, 201)

    print("\nitem registration + search")
    item = c.post("/items", headers=hdr, json={
        "name": f"Black iPhone {tag}", "description": "Cracked screen, blue case",
        "kind": "found", "occurred_on": "2026-08-01",
        "category_id": cat.json()["id"], "location_id": loc.json()["id"]})
    check("POST /items", item.status_code, 201)
    iid = item.json()["id"]
    check("item starts 'reported'", item.json()["status"], "reported")
    check("location is a joined object", item.json()["location"]["name"], f"Library {tag}")
    check("GET /items?q=<name>", c.get("/items", params={"q": tag}).json()["total"], 1)
    check("GET /items?q=cracked (description)",
          c.get("/items", params={"q": "cracked", "category_id": cat.json()["id"]}
                ).json()["total"], 1)
    check("GET /items?limit=0 rejected", c.get("/items", params={"limit": 0}).status_code, 422)

    print("\nclaim + lifecycle")
    claim = c.post(f"/items/{iid}/claims", headers=hdr2,
                   json={"evidence": "Serial matches my receipt"})
    check("POST /items/{id}/claims", claim.status_code, 201)
    check("item auto-advanced", c.get(f"/items/{iid}").json()["status"], "matched")
    check("POST /claims/{id}/decision", c.post(
        f"/claims/{claim.json()['id']}/decision", headers=hdr,
        json={"approve": True}).status_code, 200)
    check("item now claimed", c.get(f"/items/{iid}").json()["status"], "claimed")
    r = c.post(f"/items/{iid}/status", headers=hdr,
               json={"to_status": "closed", "note": "Handed over"})
    check("POST /items/{id}/status -> closed", r.status_code, 200)
    print("        history:", " -> ".join(e["to_status"] for e in r.json()["status_events"]))
    check("illegal closed->reported", c.post(f"/items/{iid}/status", headers=hdr,
          json={"to_status": "reported"}).status_code, 422)

    print("\nauthz")
    check("unauthenticated POST /items", c.post("/items", json={
        "name": "x", "description": "y", "kind": "lost",
        "occurred_on": "2026-08-01"}).status_code, 401)
    check("non-reporter DELETE", c.delete(f"/items/{iid}", headers=hdr2).status_code, 403)

print()
if fails:
    print(f"FAILED: {len(fails)} check(s): {fails}")
    sys.exit(1)
print("ALL HTTP SMOKE CHECKS PASSED against", BASE)
