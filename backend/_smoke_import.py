"""Smoke test: POST /libraries/{id}/files/import — conflict suffix, ext filter, soft-deleted occupation.

Run with backend/.venv, VITOICE_ENV=dev (uses backend/data/vitoice_dev.db, not prod).
"""
import os
import sys
import tempfile

os.environ["VITOICE_ENV"] = "dev"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
tmp = tempfile.mkdtemp(prefix="vitoice_import_smoke_")
src = os.path.join(tmp, "src")
os.mkdir(src)

with open(os.path.join(src, "movie.mp4"), "wb") as f:
    f.write(b"\x00" * 100)

libroot = os.path.join(tmp, "lib")
os.mkdir(libroot)

r = c.post("/api/libraries", json={"name": "import-smoke", "root_path": libroot})
assert r.status_code == 201, r.text
lib_id = r.json()["id"]

def imp(name):
    return c.post(
        f"/api/libraries/{lib_id}/files/import",
        json={"source_paths": [os.path.join(src, name)], "target_dir": ""},
    ).json()

def imp_raw(paths, action=None, target_dir=""):
    body = {"source_paths": paths, "target_dir": target_dir}
    if action:
        body["action"] = action
    return c.post(f"/api/libraries/{lib_id}/files/import", json=body).json()

fails = []

# 0. invalid action rejected
res = imp_raw([os.path.join(src, "movie.mp4")], action="rename")
if not ("detail" in res and "copy" in res["detail"]):
    fails.append(("bad-action", res))

# 1. normal import
res = imp("movie.mp4")
if not (res["imported"] == 1 and res["results"][0]["renamed"] is False):
    fails.append(("normal", res))
if not os.path.isfile(os.path.join(libroot, "movie.mp4")):
    fails.append(("normal-disk", "file not copied"))

# 2. same name again -> auto suffix " (1)"
res = imp("movie.mp4")
if not (res["imported"] == 1 and res["results"][0]["imported_as"] == "movie (1).mp4"):
    fails.append(("suffix", res))
if not os.path.isfile(os.path.join(libroot, "movie (1).mp4")):
    fails.append(("suffix-disk", "file not copied"))

# 3. non-video rejected
with open(os.path.join(src, "note.txt"), "w") as f:
    f.write("x")
res = imp("note.txt")
if not (res["skipped"] == 1 and "格式" in res["results"][0]["reason"]):
    fails.append(("ext-filter", res))
if os.path.exists(os.path.join(libroot, "note.txt")):
    fails.append(("ext-filter-disk", "txt copied to library"))

# 4. soft-deleted record occupies path -> suffix even though disk free
from app.database import async_session
from app.models.media import Media
import asyncio
async def soft_delete():
    async with async_session() as s:
        # import only copies + enqueues scan; the Media row is created
        # asynchronously, so seed a soft-deleted row occupying the path.
        m = Media(
            library_id=int(lib_id),
            title="movie",
            file_path=os.path.join(libroot, "movie.mp4"),
            file_name="movie.mp4",
            is_deleted=True,
        )
        s.add(m)
        await s.commit()

asyncio.run(soft_delete())
res = imp("movie.mp4")
if not (res["imported"] == 1 and res["results"][0]["imported_as"] == "movie (2).mp4"):
    fails.append(("soft-deleted", res))

# 5. action=move: source file removed after transfer
src2 = os.path.join(tmp, "src2")
os.mkdir(src2)
with open(os.path.join(src2, "other.mp4"), "wb") as f:
    f.write(b"\x00" * 100)
res = imp_raw([os.path.join(src2, "other.mp4")], action="move")
if not (res["imported"] == 1 and res["results"][0]["imported_as"] == "other.mp4"):
    fails.append(("move", res))
if not os.path.isfile(os.path.join(libroot, "other.mp4")):
    fails.append(("move-disk", "file not moved in"))
if os.path.exists(os.path.join(src2, "other.mp4")):
    fails.append(("move-src", "source still exists after move"))

# 6. file already at exact target location -> skipped, no side effects
res = imp_raw([os.path.join(libroot, "other.mp4")], action="move")
if not (res["skipped"] == 1 and "已在目标目录" in res["results"][0]["reason"]):
    fails.append(("same-location", res))
if not os.path.isfile(os.path.join(libroot, "other.mp4")):
    fails.append(("same-location-disk", "file was harmed"))

# cleanup: delete the smoke library (DB rows only; tmp dir removed below)
c.delete(f"/api/libraries/{lib_id}")
import shutil
shutil.rmtree(tmp, ignore_errors=True)

if fails:
    for name, detail in fails:
        print(f"FAIL {name}: {detail}")
    sys.exit(1)
print("SMOKE_OK: normal / suffix (1) / ext-filter / soft-deleted occupation / move / same-location all pass")
