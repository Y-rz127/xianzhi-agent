"""压测脚本（locust）。

用法（项目根目录，本机直跑后端）：
  # 混合基线：health + chart 按权重 10:1（chat 权重为 0，不会参与）
  .venv\\Scripts\\python.exe -m locust -f scripts/locustfile.py \\
      --host http://127.0.0.1:8123 --headless -u 200 -r 20 -t 5m --only-summary

  # 只压排盘（位置参数指定用户类）
  .venv\\Scripts\\python.exe -m locust -f scripts/locustfile.py ChartUser \\
      --host http://127.0.0.1:8123 --headless -u 500 -r 50 -t 2m --only-summary

  # 压聊天链路（真实 LLM 计费）：先把 ChatUser.weight 改为 1，然后
  .venv\\Scripts\\python.exe -m locust -f scripts/locustfile.py ChatUser \\
      --host http://127.0.0.1:8123 --headless -u 20 -r 2 -t 10m --only-summary

压测前提：
- --host 必须用 127.0.0.1：本机 localhost 优先解析到 IPv6 ::1 而应用只听
  IPv4，客户端会空等约 2 秒才回退，所有延迟数据失真
- 被测进程必须关闭 RELOAD 热重载（否则 --csv 落盘会触发文件监听反复重启应用），
  并建议设置 RATE_LIMIT_PER_MINUTE=0：本机单 IP 直连会把限流瞬间打满，
  得到的只会是 429 曲线
- 单独验证限流时设回正常值（如 300），观察 429 比例即可
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

_BIRTH_TIMES = [
    "1988-06-15 09:30",
    "1990-01-01 12:00",
    "1995-11-23 03:15",
    "2000-07-07 18:45",
    "1985-03-08 21:00",
    "1992-09-30 07:20",
    "1978-12-01 11:00",
    "2003-02-14 14:00",
]
_GENDERS = ["男", "女"]


class HealthUser(HttpUser):
    """探针用户：低频轮询健康检查。"""

    weight = 1
    wait_time = between(5, 10)

    @task
    def health(self):
        self.client.get("/api/health", name="/api/health")


class ChartUser(HttpUser):
    """排盘用户：压计算路径与缓存命中。"""

    weight = 10
    wait_time = between(3, 6)

    @task
    def chart(self):
        self.client.get(
            "/api/ai/xianzhi/chart",
            params={
                "birth_time": random.choice(_BIRTH_TIMES),
                "gender": random.choice(_GENDERS),
            },
            name="/api/ai/xianzhi/chart",
        )


class ChatUser(HttpUser):
    """聊天用户：SSE 全链路（真实 LLM 计费）。

    weight=0 表示默认不参与压测；跑聊天链路前把 weight 改为 1，
    并用位置参数 ChatUser 单跑该类。
    """

    weight = 0
    wait_time = between(30, 60)

    @task
    def chat(self):
        with self.client.get(
            "/api/ai/xianzhi/chat",
            params={
                "message": "帮我看看整体命盘",
                "birth_time": "1990-01-01 12:00",
                "gender": "男",
            },
            stream=True,
            timeout=180,
            catch_response=True,
            name="/api/ai/xianzhi/chat",
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return
            got_data = False
            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8", errors="ignore")
                # SSE 事件：data: {"event": "error", ...} / data: {"event": "message", ...}
                if '"event": "error"' in text or "event: error" in text:
                    resp.failure(f"stream error: {text[:128]}")
                    return
                if text.startswith("data:"):
                    got_data = True
            if not got_data:
                resp.failure("empty stream")