"""临时诊断：模拟前端 media list 的 dir 过滤请求。"""
import os

os.environ["VITOICE_ENV"] = "dev"

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as c:
    # 1. 库根（不传 dir）
    r = c.get("/api/media", params={"library_id": 8, "page_size": 5})
    print("lib8 root:", r.status_code, "total =", r.json().get("total"))

    # 2. 传相对子目录（反斜杠，tree API 的 rel_path 格式）
    r = c.get("/api/media", params={"library_id": 8, "dir": "庆余年", "page_size": 5})
    print("lib8 dir='庆余年':", r.status_code, "total =", r.json().get("total"))

    # 3. 嵌套子目录（tree 返回 rel_path 用 os.sep 连接）
    r = c.get("/api/media", params={"library_id": 8, "dir": "庆余年\\第一季", "page_size": 5})
    print("lib8 dir='庆余年\\\\第一季':", r.status_code, "total =", r.json().get("total"))

    # 4. library_id 传字符串（前端 filterLib 是 string）
    r = c.get("/api/media", params={"library_id": "8", "dir": "庆余年", "page_size": 5})
    print("lib8 str-id + dir:", r.status_code, "total =", r.json().get("total"))

    # 5. lib5 的 # 开头目录（URL fragment 截断风险）
    r = c.get("/api/media", params={"library_id": 5, "dir": "# 多人", "page_size": 5})
    print("lib5 dir='# 多人':", r.status_code, "total =", r.json().get("total"))

    # 6. 带常见附加筛选组合（管理页 buildParams 会带 sort/order/page）
    r = c.get("/api/media", params={
        "library_id": 8, "dir": "庆余年", "sort": "added_at",
        "order": "desc", "page": 1, "page_size": 60,
    })
    print("lib8 full params:", r.status_code, "total =", r.json().get("total"))
