"""从同目录 region-data.ts 生成 app/domain/city_longitude.py（城市→经度映射）。

用法：python shared/utils/gen_city_longitude.py
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))  # <root>/shared/utils
ROOT = os.path.dirname(os.path.dirname(HERE))  # <root>
SRC = os.path.join(HERE, "region-data.ts")
DST = os.path.join(ROOT, "app", "domain", "city_longitude.py")


def main():
    src = io.open(SRC, encoding="utf-8").read()
    pairs = re.findall(r"\{ name: '([^']+)', longitude: ([0-9.]+), districts:", src)
    seen = {}
    for name, lon in pairs:
        key = name.replace("市", "").replace("地区", "").replace("自治州", "").replace("盟", "")
        if key not in seen:
            seen[key] = float(lon)
    lines = [
        '"""中国城市经度映射（由 shared/utils/region-data.ts 自动生成，勿手工编辑）。',
        "",
        "用于真太阳时校正：出生地城市名 -> 东经度数。",
        "区县继承所属城市经度（同市经度差对真太阳时无实质影响），故仅保留城市级。",
        "数据源变更后请重新运行 shared/utils/gen_city_longitude.py。",
        '"""',
        "",
        "CITY_LONGITUDE: dict[str, float] = {",
    ]
    for k in sorted(seen):
        lines.append(f'    "{k}": {seen[k]},')
    lines.append("}")
    lines.append("")
    io.open(DST, "w", encoding="utf-8").write("\n".join(lines))
    print("cities:", len(seen))


if __name__ == "__main__":
    main()
