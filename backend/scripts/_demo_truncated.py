"""演示：被截断的审核输出长什么样、旧代码和新代码分别怎么处理。"""

import json
import sys

sys.path.insert(0, ".")

from app.agent.workflow.workflow_support import _parse_json
from app.agent.workflow.workflow_workers import _salvage_verdict

# 复刻你日志里那段（模型写到一半就没了）
TRUNCATED = """{
"pass": false,
"issues": [
"十神事实错误：回答称'地支酉金是印星'，但根据排盘事实，日主为壬水，酉金（辛）对壬水应为正印，而非统称印星",
"五行生克逻辑/十神定义错误：回答称'天干癸水是劫财...这步运不是靠水去疏金，而是金印之力转到比劫上'。在八字中，金生水，印生比劫。若原局金"""

print("=== 1) 这段文本的结尾 60 字（注意：没有收尾的 \"]}」） ===")
print(repr(TRUNCATED[-60:]))
print()
print("=== 2) json.loads 直接解析报什么错 ===")
try:
    json.loads(TRUNCATED)
except json.JSONDecodeError as e:
    print(f"JSONDecodeError: {e.msg}  (line {e.lineno}, col {e.colno}, pos {e.pos}/{len(TRUNCATED)})")
print()
print("=== 3) 旧路径：_parse_json（含平衡扫描）→ 结果 ===")
print("_parse_json ->", _parse_json(TRUNCATED))
print()
print("=== 4) 新路径：_salvage_verdict 抢救出来的结论 ===")
passed, issues = _salvage_verdict(TRUNCATED)
print("pass =", passed)
for i, s in enumerate(issues, 1):
    print(f"  issue[{i}] ({len(s)}字): {s[:70]}…")
