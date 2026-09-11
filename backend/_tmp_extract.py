import re
src = open('app/domain/shensha_calc.py', encoding='utf-8').read()
names = sorted(set(re.findall(r'add\("([^"]+)"', src)))
print(len(names))
for n in names:
    print(n)