import json, urllib.request, urllib.error
BASE = "http://127.0.0.1:8765/api"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

items = get("/media?page=1&page_size=5")["items"]
print("media_count=%d" % len(items))
if not items:
    print("NO MEDIA") 
else:
    for it in items[:3]:
        print("id=%s metadata_ignored=%s title=%s" % (it["id"], it.get("metadata_ignored"), (it.get("title") or "")[:20]))
    mid = items[0]["id"]
    # ignore
    r1 = post("/media/batch", {"action": "metadata_ignore", "media_ids": [int(mid)], "params": {"ignored": True}})
    d1 = get("/media/%s" % mid)
    print("IGNORE action=%s msg=%s -> metadata_ignored=%s" % (r1["action"], r1["message"], d1.get("metadata_ignored")))
    # restore
    r2 = post("/media/batch", {"action": "metadata_ignore", "media_ids": [int(mid)], "params": {"ignored": False}})
    d2 = get("/media/%s" % mid)
    print("RESTORE action=%s msg=%s -> metadata_ignored=%s" % (r2["action"], r2["message"], d2.get("metadata_ignored")))