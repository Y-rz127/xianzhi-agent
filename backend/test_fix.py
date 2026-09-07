from datetime import date
from lunar_python import Solar
from app.domain.xipan import _current, _ZHI_OF_JIE

print("验证修复后的流月判断逻辑:")
print("=" * 60)

test_cases = [
    (date(2026, 9, 7), "今天中午 - 应该是丁酉"),
    (date(2026, 9, 8), "明天 - 应该是丁酉"),
    (date(2026, 10, 8), "寒露后 - 应该是戊戌"),
]

for today, desc in test_cases:
    lunar = Solar.fromYmdHms(today.year, today.month, today.day, 12, 0, 0).getLunar()

    # 新逻辑
    current_jie = lunar.getCurrentJie()
    if current_jie:
        month_zhi = _ZHI_OF_JIE[current_jie.getName()]
        jie_name = current_jie.getName()
    else:
        prev_jie = lunar.getPrevJie()
        month_zhi = _ZHI_OF_JIE[prev_jie.getName()]
        jie_name = prev_jie.getName()

    # 年干
    lichun = lunar.getJieQiTable()["立春"]
    from datetime import datetime as dt

    lichun_date = date(lichun.getYear(), lichun.getMonth(), lichun.getDay())
    liunian_year = today if today >= lichun_date else today.year - 1

    year_gan = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"][(liunian_year - 4) % 10]
    month_index = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"].index(month_zhi)

    # 五虎遁
    wuhu = {
        "甲": "丙",
        "己": "丙",
        "乙": "戊",
        "庚": "戊",
        "丙": "庚",
        "辛": "庚",
        "丁": "壬",
        "壬": "壬",
        "戊": "甲",
        "癸": "甲",
    }
    gan_start = wuhu[year_gan]
    gan_seq = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
    month_gan = gan_seq[(gan_seq.index(gan_start) + month_index) % 10]

    print(f"\n{desc}")
    print(f"  日期: {today}")
    print(f"  当前节气: {jie_name}")
    print(f"  流月干支: {month_gan}{month_zhi}")
