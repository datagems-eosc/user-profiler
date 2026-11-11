'''
End-to-end check of the automatic keyword refresh, simulating the QR's notification.
'''

import base64
import json
import os
import sys
import time
from datetime import datetime
import requests


# variables 
API = os.getenv("UP_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.environ.get("TOKEN", "").strip().removeprefix("Bearer ").strip()
USER_ID = os.environ.get("USER_ID", "").strip()
H = {"Authorization": f"Bearer {TOKEN}"}
WAIT_S = 90
failures = 0


# ---------------------------------------------------------------------------
# Functions

def check(ok: bool, msg: str) -> bool:
    global failures
    print(("  OK    " if ok else "  FAIL  ") + msg)
    failures += not ok
    return ok


def dt(value) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# minutes left before the token expires
def token_minutes_left():
    try:
        payload = TOKEN.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
        return (exp - time.time()) / 60
    except Exception:
        return None


def get_user() -> dict:
    # _save deletes and recreates the subgraph: during a save the user can briefly be 404
    for _ in range(10):
        r = requests.get(f"{API}/user/{USER_ID}", headers=H, timeout=10)
        if r.status_code != 404:
            r.raise_for_status()
            return r.json()
        time.sleep(0.5)
    r.raise_for_status()


def history_times(user: dict) -> set:
    hist = next((s for s in user["sessions"] if s["sessionId"] == "dmm-history"), {"queries": []})
    return {dt(q["typedAt"]) for q in hist["queries"] if q.get("typedAt")}


def keyword_state() -> set:
    r = requests.get(f"{API}/user/{USER_ID}/keywords", headers=H, timeout=10)
    r.raise_for_status()
    return {(k["value"], k["lastSeenAt"]) for k in r.json()["keywords"]}


def notify(user_id: str, text: str) -> requests.Response:
    return requests.post(f"{API}/user/{user_id}/queries", json={"query": text}, headers=H, timeout=10)


# ---------------------------------------------------------------------------
print("0. Prerequisites")

if not TOKEN or not USER_ID:
    sys.exit("  Set TOKEN and USER_ID first")

left = token_minutes_left()

if left is None:
    sys.exit("  TOKEN doesn't look like a Keycloak token")

if left <= 0:
    sys.exit(f"  TOKEN expired {-left:.0f} min ago: get a new one")

check(True, f"token valid for {left:.1f} more min")

if left < 2:
    print("        (barely enough: get a fresh one if the test fails halfway)")


# ---------------------------------------------------------------------------
print("\n1. Latest query of the user in the DMM")

r = requests.get(f"{API}/user/{USER_ID}/queries_test", headers=H, timeout=30)

if not check(r.ok, f"GET /queries_test -> {r.status_code}"):
    sys.exit("        " + r.text[:300])

queries = r.json()["queries"]

if not check(bool(queries), "the DMM has queries for this user"):
    sys.exit(1)

latest = max(queries, key=lambda q: dt(q["typedAt"]))

latest_at = dt(latest["typedAt"])

print(f"        -> {latest['text']!r}  ({latest['typedAt']})")


before = get_user()

if not check(latest_at not in history_times(before), "it has not been processed yet"):
    sys.exit("        Make a NEW query in the DataGEMS UI (and don't keep Streamlit in "
             "'Local + DMM' mode, it refreshes on its own), then rerun")


# ---------------------------------------------------------------------------
print("\n2. Notification with the exact text, as the QR would send it")

sent = time.time()

r = notify(USER_ID, latest["text"])

check(r.status_code == 202, f"POST /queries -> {r.status_code}  (answered in {time.time() - sent:.2f}s)")

# ---------------------------------------------------------------------------
print(f"\n3. Waiting for the background refresh (up to {WAIT_S}s)")

after = before

while time.time() - sent < WAIT_S:
    time.sleep(1)
    after = get_user()
    if latest_at in history_times(after):
        break

elapsed = time.time() - sent

if not check(latest_at in history_times(after), f"query saved in dmm-history after {elapsed:.1f}s"):
    sys.exit("        Look at the uvicorn log: the 'Refresh of ...' line says what went wrong")


kws = keyword_state()

fresh = sorted(v for v, seen in kws if seen and dt(seen).timestamp() >= sent - 1)

check(bool(fresh), f"keywords added/refreshed by this refresh: {fresh}")

# ---------------------------------------------------------------------------
print("\n4. Same notification again: the query is already processed, nothing must change")

check(notify(USER_ID, latest["text"]).status_code == 202, "POST /queries -> 202")

time.sleep(8)  # 3 DMM attempts (~4s) + margin

check(keyword_state() == kws and history_times(get_user()) == history_times(after),
      "keywords and dmm-history unchanged")

# ---------------------------------------------------------------------------
print("\n5. Notification for a user that is not in the graph")

r = notify("00000000-0000-0000-0000-000000000000", "x")

check(r.status_code == 404, f"POST /queries -> {r.status_code}")

# ---------------------------------------------------------------------------
print("\n" + ("ALL CHECKS PASSED" if failures == 0 else f"{failures} CHECK(S) FAILED"))

sys.exit(1 if failures else 0)
