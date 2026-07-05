'''
# Python 数据结构速览笔记
# 一、List（列表）
lst = []
# 常用操作
lst.append(x)        # O(1) 尾部追加
lst.insert(i, x)     # O(n) 插入
lst.pop()            # O(1) 删尾部
lst.pop(i)           # O(n) 删指定索引
lst.remove(x)        # O(n) 删指定值
len(lst)             # O(1)
lst[a:b]             # O(k) 切片
# 特点：可变、有序、可重复

# 二、Dict（字典）
d = {}
# 常用操作
d[key] = val         # O(1) avg 插入/更新
d.get(key, default)  # O(1) avg 查询
key in d             # O(1) avg 判存
del d[key]           # O(1) avg 删除
d.keys()             # O(1) 视图
d.values()           # O(1) 视图
# 特点：键唯一、查找快、3.7+ 保序

# 三、Set（集合）
s = set()
# 常用操作
s.add(x)             # O(1) avg
s.remove(x)          # O(1) avg
s1 & s2              # 交集
s1 | s2              # 并集
s1 - s2              # 差集
# 特点：去重、集合运算

# 四、Tuple（元组）
t = (1, 2, 3)
# 特点：不可变、可哈希
# 用途：dict key / set element

# 五、Deque（双端队列）
from collections import deque
dq = deque()
dq.appendleft(x)     # O(1)
dq.append(x)         # O(1)
dq.popleft()         # O(1)
dq.pop()             # O(1)
# 特点：BFS、滑动窗口

# 六、Heap（堆）
import heapq
heap = []
heapq.heappush(heap, x)      # O(log n)
heapq.heappop(heap)          # O(log n)  # 删除根节点
heap[0]                      # O(1) 最小元素
# 特点：默认小顶堆

# 七、Counter（计数器）
from collections import Counter
c = Counter("aabbc")
c["a"]                     # 计数
c.most_common(1)           # 返回频率最大的：[(字符, 次数)]
# 特点：频率统计

# 八、OrderedDict（有序字典）
from collections import OrderedDict
   方法	                              作用	                   对应 LRU 逻辑
move_to_end(key, last=False)   把指定键移到字典开头	             标记为 “最近使用”
popitem()	                   弹出字典末尾的键值对	             淘汰 “最久未使用” 的元素
内部有序性	                   字典会按 “使用顺序” 维护元素排列	 天然维护 LRU 顺序

# 九、Defaultdict
from collections import defaultdict
d = defaultdict(int)
d[key] += 1                # 无需初始化
# 特点：避免 KeyError

# 十、时间复杂度速记
"""
list:  查 O(n)  增 O(1)/O(n)  删 O(n)
dict:  查 O(1)  增 O(1)       删 O(1)
set:   查 O(1)  增 O(1)       删 O(1)
deque: 头尾 O(1)
heap:  入堆/出堆 O(log n)
"""

# 十一、选型建议
"""
快速查重        -> set
键值映射        -> dict
BFS/滑动窗口    -> deque
TopK           -> heapq
计数统计        -> Counter
回溯/DFS       -> list / dict
"""

常用位运算公式大全
1. 基础判定与奇偶
功能	公式 (C/Java/Python)	说明
判断奇偶	(n & 1) == 1	比 n % 2 == 1 更快，二进制末位为 1 是奇数
判断正负	(n >> 31) & 1（32 位 int）	 算术右移把符号位移至末尾，1 为负数，0 为正数
判断 2 的整数次幂	(n & (n - 1)) == 0 && n > 0	  2的幂二进制仅有单个 1，减 1 后所有低位反转，相与为 0
判断 4 的整数次幂	(n & (n - 1)) == 0 && (n & 0x55555555) != 0 && n > 0	在 2 的幂基础上，1 必须出现在偶数位
判断两数异号	(x ^ y) < 0	  符号位不同则异或结果符号位为 1，整体为负数
判断整数是否为 0	!n/not n(Python)	  位运算最简判零写法

2. 乘除法与符号变换 (O (1) 复杂度)
功能	公式	说明
乘 2k	n << k	二进制整体左移 k 位，等价快速乘幂
除 2k（向下取整）	n >> k	二进制整体右移 k 位，仅适用于正数
取相反数	~n + 1	计算机补码规则，按位取反再加 1
取整数绝对值	(n ^ (n >> 31)) - (n >> 31)	正数不变，负数自动转为正数
整数除以 2 向上取整	(n + 1) >> 1	替代 (n+1)//2，位运算提速
两数无溢出求平均值	(x & y) + ((x ^ y) >> 1)	避免 (x+y)/2 大数相加溢出

3. 交换与异或 (Swap & XOR)
功能	公式	说明
无临时变量交换   a ^= b; b ^= a; a ^= b;	原理 a^b^b=a，不可交换同地址变量（如数组同一元素）。
消除最低位1	n & (n - 1)	把最右侧第一个 1 置 0，经典高频操作。
提取最低位1	n & (-n)	仅保留最右侧 1，其余所有位清零（树状数组核心）。
取最大值(无分支)	b ^ ((a ^ b) & -(a < b))	若 a<b则结果为 b，否则为 a。
取最小值(无分支)	a ^ ((a ^ b) & -(a < b))	若 a<b则结果为 a，否则为 b。

4. 状态压缩与掩码 (Masking)
功能	公式	说明
判断第 k 位是否为 1	(n >> k) & 1	将第 k 位移至最低位，与 1 相与判定
将第 k 位强制设为 1	n = (1 << k)	构造第 k 位为 1 掩码，或运算置 1
将第 k 位强制设为 0	n &= ~(1 << k)	构造第 k 位为 0 掩码，与运算清 0
翻转第 k 位状态	n ^= (1 << k)	0 变 1、1 变 0，快速反转二进制位
截取数字低 k 位	n & ((1 << k) - 1)	等价 n % (2^k)，取模极速优化
清空第 k 位及更高位	n &= (1 << k) - 1	只保留 0~k-1 低位区间

5. 实战算法技巧 (高频笔试 / 竞赛考点)
① 最快统计二进制中 1 的个数（Brian Kernighan）
count = 0
while n:
    n &= n - 1   # 每次消去一个低位1
    count += 1
return count
说明：循环次数 = 二进制 1 的数量，效率远超逐位遍历
② 数组唯一只出现一次数字（其余均两次）
res = 0
for num in nums:
    res ^= num
return res
说明：相同数字异或抵消为 0，最终剩余唯一数
③ 枚举一个集合所有子集（状态压缩 DP 核心）
sub = mask
while sub:
    sub = (sub - 1) & mask
说明：遍历 mask 代表集合的全部合法子集，组合题必备
④ 数组元素均出现三次，找唯一出现一次的数
        a=b=0
        for n in nums:
            a=(a^n)&~b
            b=(b^n)&~a
        return a
⑤ 快速寻找连续缺失整数（异或法）
def find_missing_num(arr, n):
    # arr：缺失一个数的连续数组  n：完整序列的最大值
    xor_full = 0
    xor_arr = 0
    # 完整序列 1~n
    for i in range(1, n+1):
        xor_full ^= i
    # 数组元素
    for num in arr:
        xor_arr ^= num
    return xor_full ^ xor_arr
arr = [1,2,4,5]
n = 5
print(f"缺失的数字：{find_missing_num(arr, n)}")    #输出3
⑥ 大小写字母快速转换（ASCII 位运算）
功能	公式	说明
大写转小写	ch | 32	 32对应二进制第 5 位，置 1 变小写
小写转大写	ch & ~32	清除第 5 位，转为大写
判断字母大小写	ch & 32	 结果非 0 为小写，0 为大写
例如：a = "A"
# 大写转小写：先转ASCII，位运算，再转字符
lower_a = chr(ord(a) | 32)      # ord()函数实现字符相减（ASCLL码） 例如：ord('a')-ord('b')=-1
print(lower_a)  # 输出：a

*的用法：
假设数组 a = [1, 2, 3, 4]
1. 不加 * → 打印整个列表（带括号、逗号）
print(a)   # 输出：[1, 2, 3, 4] 这是列表本身，刷题时绝对不能这样输出（格式错误）
2. 加 * → 拆成独立元素（空格分隔）
print(*a)  # 等价于 print(1, 2, 3, 4)
# 输出：1 2 3 4  这正是编程题要求的输出格式：元素用空格隔开，无括号、无逗号
一句话记忆
✅ *列表 = 把列表拆开，变成一个个单独的数
✅ print(*列表) = 按空格分隔打印所有元素
zfill：zfill(width)是 Python 字符串的一个方法，它的全称是 zero-fill（零填充）。
功能：在字符串的左侧填充指定数量的字符 '0'，直到字符串的总长度达到 width。
n = bin(n)[2:].zfill(32)
bin(n)会把整数转换成二进制字符串（例如 5变成 '0b101'）。
[2:]是为了切掉前面的 '0b'前缀（剩下 '101'）。
.zfill(32)会把这个二进制数补长到 32位。如果原长度不足32，前面就会自动填满 0（例如变成 '0000...000101'）。

import random # 引入随机数
#这是注释
from sys import flags
while True:
 v=random.randint(1,3)# 生成随机整数
for i in range(5): # 生成[0，n）的数据序列不包含n,相当于一个数组,也可以range（a，b）
#range（a，b，c）c是步频
 print('我爱你')
if v>3:
    print('你好')
elif v==2:
     print('buhao')
else:
    v=1
# len() 同时适用于 list / set / dict / tuple / str 等所有容器，统一接口，O(1) 时间复杂度。
# 创建范围为n的列表数组 a=[0]*(n+1)
# 一维列表推导式：
# matrix=[x for x in range(n)]
# 二维列表推导式：
# m, n = 3, 4
# matrix = [[0 for _ in range(n)] for _ in range(m)]
# [[0, 0, 0, 0],
# [0, 0, 0, 0],
# [0, 0, 0, 0]]
二维数组转一维数组：
1. 最简洁：列表推导式（推荐）
arr1d = [num for row in arr2d for num in row]
print(arr1d)  # [1,2,3,4,5,6,7,8,9]
2. 最直观：for 循环（新手易懂）
arr1d = []
for row in arr2d:
    arr1d.extend(row)  # 把每一行直接加进去
print(arr1d)
3. 最快：itertools.chain（适合大数据）
import itertools
arr1d = list(itertools.chain.from_iterable(arr2d))
print(arr1d)
4. 科学计算：numpy 扁平化（处理矩阵专用）
如果你用的是 numpy 二维数组，用 .flatten() 最快：
import numpy as np
np_arr2d = np.array([[1,2,3], [4,5,6], [7,8,9]])
arr1d = np_arr2d.flatten()
print(arr1d)  # [1 2 3 4 5 6 7 8 9]
5. 万能：sum 函数（极简一行）
arr1d = sum(arr2d, [])
print(arr1d)
# 创建正无穷大
positive_inf = float('inf')
positive_inf = float('infinity')
positive_inf = math.inf  # 需要 import math
# 创建负无穷大
negative_inf = float('-inf')
negative_inf = -math.inf
name='100.00'
name1=name.rfind(1,0,len(name))# 从右边查找  切片：str=str1[a:b] 冒号前从下标a开始切片，到下标(b-1)停止
name2=name[4,1,-1] # sub_str index()返回一个下标，不会是负数
# count(str，num)计数
# s=s.replace(str1,str2,n) str1替换成str2,n为替换次数,字符串不可变，修改后生成新字符串，必须重新赋值才生效
# split(str，n)以str为分隔符进行切割，n为切割次数 rsplit（）
默认情况下，split() 会：
1、（包括连续空格、制表符等）
2、去掉首尾空格
3、返回一个单词列表
示例：
s="  the   sky is   blue  "
s.split()           → ['the', 'sky', 'is', 'blue']
s[::-1]             → ['blue', 'is', 'sky', 'the']
" ".join(...)       → "blue is sky the"
# 对像.strip() 去重/n，把字符窜两边的字符去掉
# str.join(str1)将str插入到字符串str1的每两个元素之间，str1为可迭代对象，分隔
# 若a为字符串列表 则' '.join(a)操作为将a中元素拼接成字符串 注意：a为可迭代的字符串对象。如果传入整数列表，类型不匹配，Python 会拒绝执行。
my_list[start:stop:step]  切片，start：开始下标位置， stop-1：结束下标位置， step：步长，默认为1
my_list=list()
# append(str)在末尾添加数据str，附加
# insert(index,str)在index处插入数据str，插入
# extend(可迭代对象)将可迭代对象逐个插入到列表末尾，在末尾连接另一个迭代对象
# list.index(num) 在list列表中查找num，返回其在list中的下标
# str in list/str not in list 判断str是否在list中返回值为True或False
# remove(str) 删除列表的数据str
# pop(index)删除index处的元素,pop()默认删除最后一个元素(哈希集合不要这样用)
del My_list # 删除整个列表 del My_list[index]删除index处的数据
# list.sort()对列表进行排序，前提是列表元素是一样的，默认是从小到大排序， sort(reverse=True) 从大到小排序
# sorted(list) 不在原列表中进行排序，会得到一个新的列表 newlist=sorted(set(list)) 这个函数可以对哈希集合元素进行排序,返回一个列表
dic = defaultdict()  字典排序用法
dic['name'] = 'b'
dic['encoding'] = 'g'
# 使用 .items() 并解包 (k, v)
# sorted 会收到一个个元组，比如 ('name', 'b'), ('encoding', 'g')
# 然后 lambda k, v: v['name'] 就会变成 v，也就是字典的值
dic = sorted(dic.items(), key=lambda item: item[1]) # 按照值来排序
print(dic)
# 输出：[('name', 'b'), ('encoding', 'g')]

# reverse() 对原列表进行逆序排序
#哈希集合：
s = set()               # 空
s = {1, 2, 3}           # 字面值
s = set('abbccc')       # 去重 {'a','b','c'}
s.add(x)        # 单加
s.update(iter)  # 批量加
s.discard(x)    # 删（不存在不抛异常）
s.remove(x)     # 删（不存在抛 KeyError）
注意不要使用s.pop()会返回最后一个数，但是哈希集合的插入不看顺序，要使用s.remove()
x in s          # O(1) 存在性判断
s1 | s2  or s1.union(s2)        # 并
s1 & s2  or s1.intersection(s2) # 交
s1 - s2  or s1.difference(s2)   # 差
s1 ^ s2                         # 对称差
# 推导式：odd_set = {x for x in range(10) if x & 1}
# 元组（tuple）用圆括号来定义，和列表很相似，但是不能修改其中的数据
# my_tuple=()，定义空元组，my_tuple=(n,)不能单独一个数据，不然类型就是int，要加一个逗号
# my_tuple=tuple()定义元组
# 字典 dict ={key:value，} 要加冒号，用逗号隔开，关键字dict，使用大括号 也就是map()
# d = dict(zip(keys, values))        # 两个列表拼一起,互为映射
# 建空字典
# dic = defaultdict(list)  # 目前是 {} 访问不存在的键值不好会报错
# d.setdefault(k, v)  # 没有就设，有就返回旧值
# d.update(d2)      # 批量覆盖/新增
# 字典的value值可以是列表，也可以是元组，也可以是字符串
# 使用[]访问和get（key）访问  get(key,value),若key不存在，返回value值
# 删除字典： 1，del my-dict/删除键值元素 del my-dict[key]  2，pop(key) 返回key对应的value值 3， 清空字典 my_dict.clear()
# for key in my_dict：遍历的是字典的key值
# 字典.keys()返回字典的key值 /字典.values()返回字典的所有value值 / 字典.items()返回字典的所有键值对，是元组类型
# 将两组内容转换成映射字典
keys = ['a', 'b', 'c']      # 第一组键
values = [1, 2, 3]          # 第二组值
mapping = dict(zip(keys, values))   zip 把两组元素按位置配对 → 生成 (k, v) 元组迭代器。
# {'a': 1, 'b': 2, 'c': 3}
# enumerate()将可迭代序列中具体元素下标和具体元素组合在一块变成元组，可用for循环遍历
# +法支持列表，元组，字符串，*number 支持列表，元组，字符串，复制number分组合成新容器
# 字符串内容判断
text = "Python123"
#s=s.lower() 对s转小写
#s=s.upper()对s转大写
#c=s[::-1]将s反转再赋值给c
print(f"是否为数字: {text.isdigit()}")  注意：只能判断非负数字，带负号数字判断不出来
print(f"是否为字母: {text.isalpha()}")
print(f"是否为字母数字: {text.isalnum()}")
print(f"是否为小写: {text.islower()}")
print(f"是否为大写: {text.isupper()}")
# 字符串切片操作
text = "Python Programming"
print(f"前6个字符: {text[:6]}") 不包括text[6]，0-5
print(f"后11个字符: {text[7:]}")
print(f"中间部分: {text[7:18]}")
print(f"每隔一个字符: {text[::2]}")
print(f"反转字符串: {text[::-1]}")

#将整数、浮点数转换成字符串：num=123
1、s_num=str(num)  2、s_num='%s' % num
3、s_num=f'{num}' 4、 str_num = "{}".format(num)

#十进制转二进制：
bin()方法：
num = 10
binary_str = bin(num)
print(binary_str)  # 输出：'0b1010'
# 若需去掉前缀'0b'，可使用字符串切片
binary_str_without_prefix = bin(num)[2:]
print(binary_str_without_prefix)  # 输出：'1010'
将n转换为32位二进制字符串（前导0补全）可以用zfill()函数补全前导0
        binary = bin(n)[2:].zfill(32)
获取十进制数的二进制位数长度：N=int(input()) N.bit_length()
统计十进制数的二进制数中1的个数：N=int(input()) N.bit_count()
format方法：
num = 15
binary_str = format(num, 'b')
print(binary_str)  # 输出：'1111'
手动实现求余法：
def dec_to_bin(num):
    if num == 0:
        return '0'
    res = []
    while num > 0:
        res.append(str(num % 2))
        num = num // 2
    return ''.join(reversed(res))
print(dec_to_bin(8))  # 输出：'1000'

二进制转十进制：
1、a='11'
a=int(a, 2)
print(a)  a=3
2、a=0b11  print(a) 输出3
3、a=eval('0b1011')  print(a)  a=3
4、def bin2dec(b_str):
    return sum(int(ch) * (2 ** i) for i, ch in enumerate(reversed(b_str)))
bin2dec('1011')   # 11

#引入List： from typing import List
或者直接用list[]小写

异或运算的关键性质：
任何数和0异或，结果为自身（即 a ^ 0 = a）。
任何数和自身异或，结果为0（即 a ^ a = 0）。
异或运算满足交换律和结合律（即 a ^ b ^ a = b ^ (a ^ a) = b ^ 0 = b）。
可以用这种方法找出列表里的单个元素

位运算速查表：
| 运算符 | 名称 | 描述 | 示例 (`a=5`, `b=3`) | 二进制演示 | 结果 |
| `&` | 按位与   | 两位都为 1 时，结果才为 1       | `5 & 3` -> `0101 & 0011` = `0001` = 1 |
| `|` | 按位或   | 两位只要有一个为 1，结果就为 1   | `5 | 3` -> `0101 | 0011` = `0111` = 7 |
| `^` | 按位异或 | 两位不同为 1，相同为 0          | `5 ^ 3` -> `0101 ^ 0011` = `0110` = 6 |
| `~` | 按位取反 | 0 变 1，1 变 0 (注意负数陷阱)   | `~5` -> `~0...0101` = `1...1010` = -6 |
| `<<` | 左移   | 向左移动 n 位，右边补 0 (相当于*2^n)   | `5 << 1` 即 `0101` -> `1010` = 10 |
| `>>` | 右移   | 向右移动 n 位，左边补符号位 (相当于/2^n)   | `5 >> 1` 即 `0101` -> `0010` = 2 |

#Counter函数的使用（统计列表中元素的个数）
3️⃣ 找出现次数最多的元素 （考试神器！）
lst = [1,2,2,3,3,3]
c = Counter(lst)
print(c)  # Counter({3:3, 2:2, 1:1})
# 最多的 1 个
print(c.most_common(1))  # [(3, 3)]
# 最多的 2 个
print(c.most_common(2))  # [(3,3), (2,2)]
# 直接拿众数的次数
print(c.most_common(1)[0][1])  # 3
4️⃣ 转成字典 / 列表 / 元素列表
dict(c)        # {1:1, 2:2, 3:3}
list(c)        # [1,2,3]（所有键）
list(c.values()) # [1,2,3]（次数）
5️⃣ 遍历 Counter
for num, count in c.items():
    print(num, count)
6️⃣ 增加 / 减少计数
c[2] += 1   # 2 的次数 +1
c[3] -= 1   # 3 的次数 -1
7️⃣ 统计字符串（超好用）
s = "abracadabra"
c = Counter(s)
print(c['a'])  # 5
8️⃣ 清空
c.clear()

给你两个整数 left 和 right ，表示区间 [left, right] ，返回此区间内所有数字 按位与 的结果（包含 left 、right 端点）。
def rangeBitwiseAnd(self, left: int, right: int) -> int:
        shift = 0
        # 找到left和right的公共前缀
        while left < right:     最终 left 和 right 相等时，得到的就是它们的公共前缀
            left >>= 1   每次右移一位，相当于"忽略"最低位，寻找更高位的公共前缀
            right >>= 1
            shift += 1    当 left 和 right 不相等时，它们至少有一位是不同的
        return left << shift   通过左移 shift 位，将公共前缀恢复到正确的位置
初始: left=5(101), right=7(111), shift=0
↓
第1次循环后: left=2(10), right=3(11), shift=1
↓
第2次循环后: left=1(1), right=1(1), shift=2
↓
退出循环
↓
结果: 1 << 2 = 4(100)


#一个递归例子：
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def max_depth(root):
    # 基准情况
    if not root:
        return 0
    # 递归情况
    return 1 + max(max_depth(root.left), max_depth(root.right))

# 创建二叉树:    1
#              / \
#             2   3
#                / \
#               4   5
root = TreeNode(1, TreeNode(2), TreeNode(3, TreeNode(4), TreeNode(5)))
print(max_depth(root))  # 输出: 3


# 一个回溯例子：
def permute(nums):
    def backtrack(path, used):
        # 终止条件：路径长度等于原数组长度
        if len(path) == len(nums):
            result.append(path[:])  # 注意要使用副本
            return
        #循环
        for i in range(len(nums)):
            # 跳过已使用的元素
            if used[i]:
                continue

            path.append(nums[i])# 做选择
            used[i] = True

            backtrack(path, used)# 递归

            path.pop()# 撤销选择（回溯）
            used[i] = False

    result = []
    used = [False] * len(nums)
    backtrack([], used)
    return result

print(permute([1, 2, 3]))
# 输出: [[1,2,3],[1,3,2],[2,1,3],[2,3,1],[3,1,2],[3,2,1]]

一、先明确核心概念
path：当前正在构建的排列（如 [1]、[1,2]）；
used：布尔数组，标记元素是否已被选入当前 path（True= 已使用，False= 未使用）；
result：存储所有最终排列的结果集；
回溯关键：递归前 “做选择”，递归后 “撤销选择”，确保回到上一层时状态干净，能尝试其他选择。
二、完整执行流程（按递归顺序）
初始状态：result = []，used = [False, False, False]，调用 backtrack([], used)。
第一层递归：backtrack([], [F,F,F])
目标：选择第一个元素，构建 path 的第 1 位。
循环遍历 i=0,1,2（对应元素 1,2,3）：
分支 1：选第 0 个元素（1）
做选择：path.append(1) → path = [1]；used[0] = True → used = [T,F,F]；
递归调用：backtrack([1], [T,F,F])（进入第二层递归）。
第二层递归：backtrack([1], [T,F,F])
目标：选择第二个元素，构建 path 的第 2 位（只能选未使用的 2 或 3）。
循环遍历 i=0,1,2：
i=0：used[0] = True（已用），跳过；
i=1：未使用，进入分支：
分支 1.1：选第 1 个元素（2）
做选择：path.append(2) → path = [1,2]；used[1] = True → used = [T,T,F]；
递归调用：backtrack([1,2], [T,T,F])（进入第三层递归）。
第三层递归：backtrack([1,2], [T,T,F])
目标：选择第三个元素，构建 path 的第 3 位（只剩未使用的 3）。
循环遍历 i=0,1,2：
i=0、i=1：已用，跳过；
i=2：未使用，进入分支：
做选择：path.append(3) → path = [1,2,3]；used[2] = True → used = [T,T,T]；
递归调用：backtrack([1,2,3], [T,T,T])（进入终止层）。
终止层 1：backtrack([1,2,3], [T,T,T])
判断终止条件：len(path) == len(nums)（3==3）；
保存结果：result.append(path[:]) → result = [[1,2,3]]（注意 path[:] 是副本，避免后续修改影响结果）；
直接返回，回到第三层递归。
第三层递归回溯（撤销选择）
执行 path.pop() → path = [1,2]；used[2] = False → used = [T,T,F]；
循环结束（i=2 是最后一个索引），返回第二层递归。
第二层递归回溯（撤销选择）
执行 path.pop() → path = [1]；used[1] = False → used = [T,F,F]；
循环继续，i=2（元素 3，未使用），进入分支：
分支 1.2：选第 2 个元素（3）
做选择：path.append(3) → path = [1,3]；used[2] = True → used = [T,F,T]；
递归调用：backtrack([1,3], [T,F,T])（进入第三层递归）。
第三层递归：backtrack([1,3], [T,F,T])
循环遍历 i=0,1,2：
i=0、i=2：已用，跳过；
i=1（元素 2，未使用）：
做选择：path.append(2) → path = [1,3,2]；used[1] = True → used = [T,T,T]；
递归调用：backtrack([1,3,2], [T,T,T])（终止层）；
终止层：result.append([1,3,2]) → result = [[1,2,3], [1,3,2]]；
回溯：path.pop() → [1,3]，used[1] = False；循环结束，返回第二层。
第二层递归回溯（撤销选择）
执行 path.pop() → path = [1]；used[2] = False → used = [T,F,F]；
循环结束，返回第一层递归。
第一层递归回溯（撤销选择）
执行 path.pop() → path = []；used[0] = False → used = [F,F,F]；
循环继续，i=1（元素 2，未使用），重复上述逻辑，生成排列 [2,1,3]、[2,3,1]；
循环继续，i=2（元素 3，未使用），重复上述逻辑，生成排列 [3,1,2]、[3,2,1]。
def generate_permutations(nums, current, result):
    """
    使用回溯算法生成所有排列。
    """
    if len(current) == len(nums):
        result.append(current[:])
        return
    for num in nums:
        if num not in current:
            current.append(num)
            generate_permutations(nums, current, result)
            current.pop()

if __name__ == "__main__":
    n = int(input().strip())  #去除两边字符
    nums = list(map(int, input().strip().split()))  #将以空格分割的一串输入分割并转换成int型数字
    result = []
    generate_permutations(nums, [], result)
    for perm in result:
        print(' '.join(map(str, perm)))  #map做映射作用

动态规划解题步骤
定义状态：明确dp数组的含义
确定状态转移方程：找到如何从已知状态推导新状态
初始化：设置基准情况的初始值
确定计算顺序：自底向上或自顶向下
返回结果：从dp数组中获取最终答案
一个例子：
def coinChange(coins, amount):
    """
    零钱兑换：计算凑成总金额所需的最少硬币数
    """
    # dp[i]表示凑成金额i所需的最少硬币数
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0  # 金额为0时不需要硬币

    for i in range(1, amount + 1):
        for coin in coins:
            if i >= coin:
                dp[i] = min(dp[i], dp[i - coin] + 1)

    return dp[amount] if dp[amount] != float('inf') else -1

# 测试
coins = [1, 2, 5]
amount = 11
print(coinChange(coins, amount))  # 输出: 3 (5+5+1)




# 函数定义
def 函数体():
  '函数文档说明' # 必须在函数名下方
 函数代码
# 函数调用
函数体()
# 查看函数文档注释用 help(函数名)
# 在函数内部修改全局变量使用关键字： global 全局变量名=新的值
# 在函数体内 有多个返回值时可以 return 返回值1，返回值2.。。默认是元组返回类型  使用列表的形式打印出来
# 在形参前面加一个* 变为不定长元组形参，可以接受所有的位置实参，类型是元组 例 func(1,2,3,4,5)
# 加两个*，变为不定长字典形参，可以接受所有关键字实参，类型是字典 例 func(a=1,b=2,c=3,d=4)
def my_sum(*args,**kwargs)  # 不变长参数应用案例
 num=0
 for i in args:
  num+=i
 for j，k in kwargs.items():
# 形参排序 普通形参 不定长元组形参 缺省形参
# 在print函数中 'sep=str‘ 将str插入到输出的所有元素中，类似join()函数
# 组包 将多个数据值组成元组赋值给一个变量 a=1，2，3
# 拆包 将容器的数据分别给到多个变量，注意；数据个数和变量个数相等   例如：a，b，c，d=*list  list中有四项内容
# 拆包应用 交换两个变量的值 a，b=b，a
# 引用 a=b a引用b的地址值 使用函数id()可以获得地址 若a的值改变，b的值不会跟随a一起改变（列表，元组，字典除外）
# 不可变类型 int float bool str tuple 可变类型 list dict
# func(*args,**kwargs)
# func(my_list) 将列表作为一个数据进行传递  func(*my_list) 将列表中的每一个数据作为位置参数进行传递，拆包
# func(my_dict) 将字典作为一个位置实参进行传递 func(*my_dict) 将字典中的key作为位置实参进行传递
# func(**my_dict) 将字典中的键值对作为关键字实参进行传递
# 匿名函数
# 无参无返回值 lambda：函数代码  使用：(lambda:函数代码)()
# 无参有返回值  def func(): return 1+2 == lambda:1+2  先赋值： fi=lambda:1+2  再调用：fi()  /有参有返回值 lambda a，b：a+b
# 列表排序 1，直接用sort()前提是列表元素统一  2，list.sort(key=lambda x:x['name']) 列表元素是字典类型 按照name排序
# 3，list.sort(key=lambda x:(x['name'],x['age'])) 先按name排序，若相同则按age排序
# sort(key=len)或者sort(key=lambda x：len(x)) 按照长度排序
# 列表推导式(为了快速生成一个列表) list=[生成数据的规则 for 临时变量 in xxx] 例；my_list=[i for i in range(5)]-> [0,1,2,3,4]
# 1，my_list=[f'num:(i)' for i in xxx]生成字典  2，在xxx 后加if 条件代码 满足条件就生成一个数据
# 3，变量=[(i,j) for i in range(3) for j in range(3)] 共生成（3-1）*(3-1)对数值
# 哈希集合 set 定义用set{数据，数据} 集合中的数据是不可变类型， 集合是可变类型， 集合是无序的，集合中的数据不能是重复的（去重）添加 add() 删除 remove()
# 集合，列表，元组之间可以互相转换
# 文件操作 1，打开文件 open(filename,mode='打开方式‘，encoding=None) ’r‘:只读，'w'：只写，'a'：追加 encoding：文件编码格式 gbk/utf-8
# 2，读文件 文件对象.read(n)  n:一次性读取字节数 readline(n)一次性读取n行内容，默认是1行 readlines()一次读取所有行，返回值是列表，使用变量。strip()可以去掉多余的字符
# 显示文件内容：（文件对象.read()）   关闭文件 文件对象.close()  3，写文件 文件对象.write(写入文件的内容)
# 若打开文件出现乱码 解决方法1，open()打开文件的时候，指定使用utf-8打开即encoding 方法2pycharm中使用gbk方式打开
# 不管是用a方式打开文件还是用w方式打开文件，都是用write()函数写入内容，同时encoding='utf-8'
# 若使用二进制书写文件 wb 文件对象.write(内容.encode())将输入内容转换成二进制内容  读二进制文件时，文件对象.decode()将二进制内容解码
# 文件操作 先导入模块os import os os.rename(旧文件名，新文件名) os.remove(文件名) 创建文件夹 os.mkdir(str) 获取当前目录 os.getcwd()
切换当前目录(修改当前目录) os.chdir(目标目录) 获取目录列表内容 os.listdir(str) 删除当前目录(文件夹) os.rmdir(str)
 os.path.exists(文件名)判断文件存不存在
# 面向对像 类
       class 类名(object): 括号可去，object可去，同时类定义的前后需要两个空行
           def play(self): 解释器自动将调用该方法的对象传递给self，所以self代表的就是对象，在对象调用该方法时不需要手动传递实参值
# 在类中定义的函数称为方法，函数的所有知识都可以使用 修改属性值和添加一样，存在就修改，不存在就添加
# 魔法方法1 __int__在创建对象之后会立即调用。作用1，给对象添加属性，给对象属性一个初始值。作用2，每创建一个对象都要执行的代码可以写在这里
   给属性赋值: __int__(self,name) self.name=name
# 2,__str__ print(对象)会自动调用此方法,类似tostring()   2，str(对象)，将自定义对象转化为字符串时会调用
应用：1，打印对象的时候输出一些属性信息 2，将对象转化为字符串类型 注意点：方法必须返回一个字符串，只有self一个参数
 def __str__(self)print() return '' 一般不加参数 但是可以__str__(self,*args,**kwargs)
# 3,__del__() 调用时机：1，程序代码运行结束时 2，使用 del变量 将这个对象的引用对象变为0时
# 4，__repr__和__str__非常类似也是必须返回有一个字符串。用于将对象属性内容存到容器中，打印出属性内容而不是对象地址值。系统的类中都有此方法
# 继承 class A(夫类B)： 调用父类的方法 1，父类名.方法名(self,其他参数)。 2，super(类A，self).方法名(参数) 会调用类A的父类的方法
方法3，方法二的简写 super().方法名（）==方法二
# 如果子类重写了父类的init方法，在子类中需要调用父类的init方法，给对象添加从父类继承的属性，在子类init方法中先写父类的形参再写自己的形参
# 多继承 若两个父类中有相同方法，子类调用时会调用第一个父类的方法   __mro__方法可以查看当前类的继承顺序链，也叫做方法的调用顺序
# 私有属性: 在属性前加上两个下划线就成为私有属性 列如 __name，私有方法也是如此，私有方法不能在类外部访问，__func():
# 实例对象.__dict__ 可以查看对象具有的属性信息，类型是字典，key是属性名，value是属性值
# @classmethod
 def get_class_name(cls): cls是类方法的默认形参，不需要手动传递参数
  return cls.class_name
# 定义静态方法 @staticmethod  参数可以有，也可以没有，若有参数必须传递实参值
前提：不需要使用类属性，也不需要使用实例属性，则可以定义为静态方法

# 捕获异常 是指在程序运行过程中遇到错误，不让程序代码终止，让其继续运行，同时可以给错误者一个提示信息
# 捕获单个异常：                   打印异常信息：
 try：                         try：
 可能发生异常的代码                可能发生异常的代码
except 异常的类型：              except 异常的类型 as 变量名：     打印异常信息用as
发生异常执行的代码                 发生异常执行的代码
                                print(变量名)           即可以打印编译器规定的报错信息
# 捕获多个异常:
 try:                                        捕获所有的异常:
 可能发生异常的代码                                try:
 except(异常类型1，异常类型2.。。)：                 可能发生异常的代码
  发生异常执行的代码                               except Exception as 变量名：  Exceptions是常见异常类的父类
 else：                                          发生异常执行的代码
   未发生异常，代码执行                              print(变量名)
 finally：
   不管发布发生都会执行的代码
  （以上是完整结构）
 try：
 可能发生异常的代码
 except（异常类型1）：
  发生异常1，执行代码
 except（异常类型2）：
 发生异常2，执行代码
 。。。。
# 自定义异常：
1，自定义异常类，继承自异常类Exception或者BaseException 2,选择__init__，__str__方法 3，在合适的时机抛出异常对象即可
抛出异常：raise 异常对象       异常对象=异常类(输出内容)

# 模块导入  模块：有特定功能代码的python文件
方法一                 引入：import 模块名    使用：模块名.功能名
方法二                引入： from 模块名 import 功能1，功能2，。。。。   使用：功能名   注意点：如果存在同名的方法名，则会被覆盖掉
方法三             引入：from 模块名 import * 将模块中所有的功能引入
as 起别名 可以对模块和功能起别名  例如：import 原模块名 as 新模块名
注意：如果导入的是自己书写的模块，使用的模块和代码文件续需要在一个目录中
# 模块搜索顺序： 当前目录->系统目录->程序报错    注意：自己定义的模块名不要和系统模块名相同
# 若在目录嵌套中，导入模块报红线，且不提示，则将此目录设置成根目录。root sources
# 模块中的变量 __all__变量  可以在每个代码文件（模块）中定义，类型是元组，列表      例如：__all__=['num','func'] 导入变量num和方法func
作用：影响 from 模块名 import * 的导入行为，另外两种行为不受影响  如果定义__all__变量 只能导入变量中定义的内容，而不再是全部内容
# __name__变量 在每个模块和系统中都有，是系统自己定义的。 用于判断该文件是直接使用还是作为导入模块使用 例： if __name__=='__main__':
使用：1，直接运行当前代码,值为__main__  2，把文件作为模块导入时运行，结果为 my_calc(文件)

# 包：功能相近或相似的模块放在一个目录中，并且目录中定义一个__init__。py文件，这个目录就是包
包的导入：方法一： import 包名.模块名  方法二：from 包名.模块名 import 功能名 或者加*号 引入该模块全部内容
方法三：from 包名 import * 导入的是__init__.py 中的内容

a=eval(name)   将name变量还原成原来的变量类型
d= a+v if v==1 else a-v# 三目运算符
b=input('请输入b:')
bb=eval(b)
print(f'还爱{a:.2f}')控制小数点后位数    print(f'{bb:06d}')在前面留出空格用0补齐
print(type(a)) 获取变量类型
c=a**bb
print(c, end=' ')
print('a=%.1f, %s'%(a,b))
map(function,iterable) 将function应用到所有iterable上
例:map(int,input().split()) 将以空格分割的一窜输入数据转换成int型

isinstance(object, classinfo) 是 Python 内置函数，用来判断object是否是classinfo（或其子类）的实例

py中类似switch语句：
def process_data(data):
    match data:
        case int(n):
            print(f"整数：{n * 2}")
        case str(s):
            print(f"字符串：{s.upper()}")
        case list(l) if len(l) > 0:  # 带条件的匹配（guard 从句）
            print(f"非空列表：{sum(l)}")
        case _:
            print("未知类型")

process_data(10)       # 输出：整数：20
process_data("hello")  # 输出：字符串：HELLO
process_data([1,2,3])  # 输出：非空列表：6

//枚举
from enum import Enum

# 定义枚举类（继承 Enum）
class Color(Enum):
    RED = 1       # 枚举成员：名称（RED）+ 值（1）
    GREEN = 2
    BLUE = 3

# 使用枚举
print(Color.RED)          # 输出：Color.RED（不是原始值，保持语义）
print(Color.RED.value)    # 输出：1（获取枚举值）
print(Color.RED.name)     # 输出：RED（获取枚举名称）

# 根据值获取枚举成员
print(Color(2))           # 输出：Color.GREEN

# 遍历枚举
for color in Color:
    print(f"{color.name}: {color.value}")

一、通用二叉树节点类
所有遍历都用这个节点结构：
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right
二、递归遍历（最简单，必背）
1. 前序遍历：根 → 左 → 右
def preorder(root, res):
    if not root:
        return
    res.append(root.val)    # 根
    preorder(root.left, res)# 左
    preorder(root.right,res)# 右
2. 中序遍历：左 → 根 → 右
def inorder(root, res):
    if not root:
        return
    inorder(root.left, res) # 左
    res.append(root.val)    # 根
    inorder(root.right,res) # 右
3. 后序遍历：左 → 右 → 根
def postorder(root, res):
    if not root:
        return
    postorder(root.left, res)  # 左
    postorder(root.right,res)  # 右
    res.append(root.val)       # 根
三、迭代遍历（非递归，面试高频）
1. 前序遍历（栈）
def preorderIter(root):
    res=list()
    stack=list()
    node=root
    while node or stack:
        while node:
            res.append(node)
            stack.append(node)
            node=node.left
        node=stack.pop()
        node=node.right
    return res
2. 中序遍历（栈）
def inorderIter(root):
    res = []
    stack = []
    cur = root
    while cur or stack:
        while cur:
            stack.append(cur)
            cur = cur.left
        cur = stack.pop()
        res.append(cur.val)
        cur = cur.right
    return res
3. 后序遍历（栈）
def postorderIter(root):
    res=list()
    stack=list()
    node=root
    while node or stack:
        while node:
            res.append(node)
            stack.append(node)
            node=node.left
        node=stack.pop()
        node=node.right
    return res[::-1]  # 反转就是后序
四、快速记忆口诀
前序：根左右
中序：左根右
后序：左右根

层序遍历：
from collections import deque

class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

# 层次遍历（返回二维列表：[[第一层], [第二层], [第三层]...]）
def levelOrder(root):
    if not root:
        return []

    res = []
    q = deque()
    q.append(root)

    while q:
        level_size = len(q)  # 当前层有多少个节点
        current_level = []

        # 遍历当前层所有节点
        for _ in range(level_size):
            node = q.popleft()
            current_level.append(node.val)

            # 把下一层节点加入队列
            if node.left:
                q.append(node.left)
            if node.right:
                q.append(node.right)

        res.append(current_level)

    return res

链表反转算法：
反转步骤（固定四步走）
先保存 cur.next（不保存后面就丢了）
让 cur.next 指向 prev（反转！）
prev 往前挪到 cur
cur 往前挪到刚才保存的 next
def reverseList(head):
    prev = None  # 前一个节点，一开始是空
    cur = head   # 当前节点，从头开始
    while cur:
        next_temp = cur.next  # 1. 保存下一个节点
        cur.next = prev       # 2. 反转！当前节点指向前一个
        prev = cur            # 3. prev 前进
        cur = next_temp       # 4. cur 前进
    return prev  # 最后prev就是新头

局部头插法算法：
for _ in range(right - left):
    next_node = cur.next   # 保存要拎到前面的节点，防止下一步删除后找不到
    cur.next = next_node.next  # 跳过这个节点，让它脱离原位置，相当于删除这个节点
    next_node.next = pre.next  # 把它插到 pre 的后面，将它拎到当前节点的前面
    pre.next = next_node       # 更新 pre 的 next，让它指向新插入的节点，将前驱节点指向它

矩阵转置算法：
方法 1：列表推导式（最常用）
matrix = [[1,2,3],
          [4,5,6]]
# 转置
transposed = [[row[j] for row in matrix] for j in range(len(matrix[0]))]

方法 2：用 zip（一行搞定）
transposed = list(zip(*matrix))
结果会是元组，要列表可以：
transposed = [list(t) for t in zip(*matrix)]

方法 3：numpy 转置（最简单）
import numpy as np
m = np.array(matrix)
t = m.T

图标准初始化模板：
n = 节点数
edges = 边列表
# 建图
graph = [[] for _ in range(n)]
for u, v in edges:
    graph[u].append(v)
    graph[v].append(u)
# 访问标记
visited = [False] * n

图的两大遍历算法：
1、DFS 深度优先（递归）
def dfs(u):
    visited[u] = True
    for v in graph[u]:
        if not visited[v]:
            dfs(v)

2、BFS 广度优先（队列）
from collections import deque
def bfs(start):
    q = deque()
    q.append(start)
    visited[start] = True
    while q:
        u = q.popleft()
        for v in graph[u]:
            if not visited[v]:
                visited[v] = True
                q.append(v)


算法	   平均时间复杂度	最坏时间复杂度	 数组有序	   空间复杂度	 稳定性 原地排序
冒泡排序	  O(n2)	      O(n2)	      O(n)	     O(1)	  ✅	✅
插入排序	  O(n2)	      O(n2)	      O(n)	     O(1)	  ✅	✅
选择排序	  O(n2)	      O(n2)	      O(n2)	     O(1)	  ❌	✅
希尔排序	  O(nlogn)	  O(n2)	      O(n)	     O(1)	  ❌	✅
快速排序	  O(nlogn)	  O(n2)	      O(nlogn)	 O(logn)  ❌	✅
归并排序	  O(nlogn)	  O(nlogn)	  O(nlogn)	 O(n)	  ✅	❌
堆排序	  O(nlogn)	  O(nlogn)	  O(nlogn)	 O(1)	  ❌	✅
计数排序	  O(n+k)	  O(n+k)	  O(n+k)	 O(k)	  ✅	❌
桶排序	  O(n)	      O(n2)	      O(n)	     O(n+k)	  ✅	❌
基数排序	  O(d(n+k))	  O(d(n+k))	  O(d(n+k))	 O(n+k)	  ✅	❌

1、归并排序：链表排序、外部排序、需要稳定性时
思想：先拆到单个，再两两合并。
拆分：
[5,2,4,1,3]
→ [5,2] 和 [4,1,3]
→ [5] [2] / [4] [1,3]
→ 全部单个：[5][2][4][1][3]
合并：
[2,5] 和 [1,3,4]
→ 合并成 [1,2,3,4,5]
def merge_sort(arr):
    # 递归终止条件：只剩一个元素，天然有序
    if len(arr) <= 1:
        return arr
    # 1. 拆分：从中间分成左右两半
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])   # 左半边递归排序
    right = merge_sort(arr[mid:])  # 右半边递归排序
    # 2. 合并：合并两个有序数组
    return merge(left, right)
def merge(left, right):
    result = []
    i = j = 0
    # 谁小就先放谁
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    # 把剩下的直接加进去
    result += left[i:]
    result += right[j:]
    return result
# 测试
print(merge_sort([4,2,1,3]))  # 输出 [1,2,3,4]

2、快速排序：几乎所有数据、乱序数据、大数据量
思想：选基准，小左大右，递归。
选 5 当基准：
[2,4,1,3] + [5]
左边选 2 当基准：
[1] + [2] + [4,3]
右边再分：
[3] + [4]
拼起来：[1,2,3,4,5]
def quick_sort(arr):
    # 终止条件：空或1个元素就是有序
    if len(arr) <= 1:
        return arr
    pivot = arr[0]  # 选第一个当基准
    left = [x for x in arr[1:] if x < pivot]   # 小的放左边
    right = [x for x in arr[1:] if x >= pivot] # 大的放右边
    # 递归 + 拼接
    return quick_sort(left) + [pivot] + quick_sort(right)
# 测试
print(quick_sort([4,3,1,5,2]))  # 输出 [1,2,3,4,5]

3、冒泡排序
思想：相邻两个比，大的往后冒，像气泡上浮。
过程：
5 和 2 比 → 交换 → [2,5,4,1,3]
5 和 4 比 → 交换 → [2,4,5,1,3]
5 和 1 比 → 交换 → [2,4,1,5,3]
5 和 3 比 → 交换 → [2,4,1,3,5]
最大的 5 沉底了
重复上面步骤，依次把 4、3、2 沉底
最后：[1,2,3,4,5]
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        c = False
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                c=True
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
        if not c:  # 剪枝
            break
    return arr
print(bubble_sort([5,2,4,1,3]))  # [1,2,3,4,5]

4、选择排序
思想：每次找最小的，放到前面。
过程：
找最小 1 → 和第 1 位交换 → [1,2,4,5,3]
剩下找最小 2 → 已经在第 2 位
剩下找最小 3 → 和第 3 位交换 → [1,2,3,5,4]
剩下找最小 4 → 交换 → [1,2,3,4,5]
def select_sort(arr):
    n = len(arr)
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr
print(select_sort([5,2,4,1,3]))

5、插入排序
思想：像摸扑克牌，逐个插入前面有序区。
初始：[5] 有序
拿 2 → 插入前面 → [2,5]
拿 4 → 插入中间 → [2,4,5]
拿 1 → 插最前面 → [1,2,4,5]
拿 3 → 插入 4 前面 → [1,2,3,4,5]
def insert_sort(arr):
    n = len(arr)
    for i in range(1, n):
        key = arr[i]
        j = i - 1
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]  # 把大的往后移
            j -= 1
        arr[j + 1] = key
    return arr
print(insert_sort([5,2,4,1,3]))

6、堆排序
思想：建成大顶堆，每次拿堆顶，再调整。
建成堆：最大值 5 在顶
拿走 5 → 剩下调整堆 → 顶是 4
拿走 4 → 顶是 3
拿走 3 → 顶是 2
最后：[1,2,3,4,5]
def heap_sort(arr):
    arr = arr.copy()
    n = len(arr)
    def heapify(i, size):
        largest = i
        l = 2 * i + 1
        r = 2 * i + 2
        if l < size and arr[l] > arr[largest]:
            largest = l
        if r < size and arr[r] > arr[largest]:
            largest = r
        if largest != i:
            arr[i], arr[largest] = arr[largest], arr[i]
            heapify(largest, size)
    for i in range(n//2 - 1, -1, -1):
        heapify(i, n)
    for i in range(n-1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]
        heapify(0, i)
    return arr
print(heap_sort([5,2,4,1,3]))

7、希尔排序
思想：跳着分组插入排序，逐步缩小步长。
比如步长 2：
分组 [5,4,3] 和 [2,1]
组内排序
再步长 1 → 变成插入排序
很快就有序
def shell_sort(arr):
    n = len(arr)
    gap = n // 2
    while gap > 0:
        for i in range(gap, n):
            temp = arr[i]
            j = i
            while j >= gap and arr[j - gap] > temp:
                arr[j] = arr[j - gap]
                j -= gap
            arr[j] = temp
        gap //= 2
    return arr
print(shell_sort([5,2,4,1,3]))

8、计数排序:整数、分数、考试成绩、年龄、有限范围数字
思想：数每个数字出现几次，再按顺序写出来。
数字范围 1~5：
1 出现 1 次，2 出现 1 次，3 出现 1 次，4 出现 1 次，5 出现 1 次
直接输出：[1,2,3,4,5]
def count_sort(arr):
    if not arr:
        return []
    min_val = min(arr)  # 新增：获取最小值，处理负数
    max_val = max(arr)
    # 计数数组长度 = 最大值 - 最小值 + 1
    count = [0] * (max_val - min_val + 1)
    for num in arr:
        # 映射到计数数组的索引：num - min_val
        count[num - min_val] += 1
    res = []
    for i in range(len(count)):
        # 还原真实数字：min_val + i
        res.extend([min_val + i] * count[i])
    return res

9、桶排序-要开辟的空间太多
思想：分到几个桶里，桶内排序再拼接。
分桶：
桶 1：1,2
桶 2：3
桶 3：4,5
每个桶排好，拼起来：[1,2,3,4,5]
def bucket_sort(arr):
    min_val = min(arr)
    max_val = max(arr)
    bucket = [[] for _ in range(min_val, max_val + 1)] #能从负数下标开始
    for num in arr:
        bucket[num - min_val].append(num)
    res = []
    for b in bucket:
        res.extend(b)
    return res
print(bucket_sort([5,2,4,1,3]))

10、基数排序-不建议使用，复杂难记
思想：按个位、十位…… 依次排。
这里都是个位数，排一次就好：
按个位排 → [1,2,3,4,5]
def radix_sort(arr):
    if not arr:
        return arr
    # 拆分正数和负数
    positives = [x for x in arr if x >= 0]
    negatives = [-x for x in arr if x < 0]  # 负数取绝对值
    # 对正数做基数排序
    def _radix_positive(nums):
        if not nums:
            return nums
        max_digit = max(nums)
        digit = 1
        while max_digit // digit > 0:
            bucket = [[] for _ in range(10)]
            for num in nums:
                bucket[num // digit % 10].append(num)
            nums = []
            for b in bucket:
                nums.extend(b)
            digit *= 10
        return nums
    sorted_pos = _radix_positive(positives)
    sorted_neg_abs = _radix_positive(negatives)
    sorted_neg = [-x for x in reversed(sorted_neg_abs)]  # 反转后还原负数
    return sorted_neg + sorted_pos
# 测试
print(radix_sort([5, 2, 4, -1, 1, 3]))  # 输出: [-1, 1, 2, 3, 4, 5]
print(radix_sort([-3, -1, 2, -5, 0]))   # 输出: [-5, -3, -1, 0, 2]


math库常用数学函数清单：
 第一部分：数学常量
在使用函数之前，先记住这几个常用的“老朋友”：
常量	含义	值 (近似)
math.pi	圆周率 π	3.141592653589793
math.e	自然常数 e	2.718281828459045
math.tau	圆周常数 τ (2π)	6.283185307179586
math.inf	正无穷大	inf
math.nan	非数字 (NaN)	nan
🧮 第二部分：核心函数清单
1. 取整与数值处理 📏
这部分函数用于处理浮点数与整数之间的转换，以及特殊的数值判断。
math.ceil(x)：向上取整。返回不小于 x 的最小整数。
math.floor(x)：向下取整。返回不大于 x 的最大整数。
math.trunc(x)：截断取整。直接去除小数部分（向零取整）。
math.fabs(x)：返回 x 的绝对值（浮点数形式）。
math.copysign(x, y)：返回 |x| 带上 y 的符号。
math.modf(x)：返回一个元组 (小数部分, 整数部分)。
2. 幂、对数与指数函数 📈
涉及乘方、开方以及以 e 为底的运算。
math.pow(x, y)：返回 x的y次方 (比内置的 ** 运算符更精确的浮点数处理)。
math.sqrt(x)：返回 x 的平方根。
math.isqrt(x)：返回 x 的整数平方根（向下取整），结果为整数。
math.exp(x)：返回 e的x次方
math.log(x[, base])：返回 x 的对数值（默认自然对数 ln，也可指定底数）。
math.log1p(x)：返回 ln(1+x) ，对极小的 x 更精确。
math.log2(x) / math.log10(x)：分别以 2 和 10 为底的对数。
3. 三角函数与角度转换 ⭕
注意：Python 中的三角函数参数通常是弧度，不是角度。
math.radians(x)：将角度转换为弧度。
math.degrees(x)：将弧度转换为角度。
math.sin(x) / math.cos(x) / math.tan(x)：正弦、余弦、正切。
math.asin(x) / math.acos(x) / math.atan(x)：反正弦、反余弦、反正切。
math.atan2(y, x)：返回 y/x 的反正切，能正确处理象限。
math.hypot(*coordinates)：计算欧几里得范数（即点到原点的距离，常用于求直角三角形斜边）。
4. 数论与组合数学 🔢
用于处理整数、阶乘以及最大公约数等。
math.factorial(n)：返回 n 的阶乘 n! 。
math.gcd(a, b)：返回 a 和 b 的最大公约数。
math.lcm(*integers)：返回给定整数的最小公倍数。
math.perm(n, k)：返回排列数P(n,k) 。
math.comb(n, k)：返回组合数C(n,k) 。
math.prod(iterable)：计算可迭代对象中所有元素的乘积。
5. 浮点数特殊判断 🔍
用于处理计算机浮点数精度带来的特殊问题。
math.isclose(a, b)：判断两个浮点数是否“接近”（由于精度问题，直接用 == 判断浮点数往往不准确，推荐用这个）。
math.isfinite(x)：检查 x 是否为有限数。
math.isinf(x)：检查 x 是否为无穷大。
math.isnan(x)：检查 x 是否为 NaN。


heapq库常用函数：
heapq.heappush(heap, item) - 向堆中插入元素
功能：将指定元素item插入到已初始化的堆heap中，插入后会自动维护堆的最小堆特性（父节点始终小于等于子节点）。
注意：heap必须是一个符合堆结构的列表（未初始化的列表可直接传入，首次插入后会变成堆结构）。

heapq.heappop(heap) - 弹出并返回堆顶元素
功能：弹出堆中最小的元素（即堆顶，列表索引 0 的元素），弹出后会自动重新调整列表，维护最小堆特性。
注意：如果堆为空，会抛出IndexError异常。

heapq.heapify(x) - 将普通列表转换为堆
功能：直接将一个普通列表x原地转换为最小堆（无需额外创建新列表，时间复杂度为 O (n)，比逐个heappush更高效）。
注意：转换后列表会满足堆结构，但不一定是完全有序的，仅保证堆顶（索引 0）是最小元素。
lst = [5, 3, 8, 1]
heapq.heapify(lst)
print(lst)  # 输出 [1, 3, 8, 5]（已转换为最小堆）

heapq.heappushpop(heap, item) - 插入后立即弹出堆顶
功能：先将元素item插入到堆heap中，再弹出并返回堆中的最小元素（等价于先heappush再heappop，但更高效，时间复杂度更低）。
适用场景：需要插入元素后快速获取当前最小值的场景。
heap = [1, 3, 2]
min_item = heapq.heappushpop(heap, 0)
print(min_item)  # 输出 0（插入0后，堆顶最小元素仍是0）
print(heap)      # 输出 [1, 3, 2]（插入0再弹出后的堆结构）

heapq.heapreplace(heap, item) - 弹出堆顶后插入新元素
功能：先弹出堆中的最小元素，再将元素item插入到堆中（与heappushpop顺序相反，同样比单独执行heappop+heappush更高效）。
注意：即使新插入的item比弹出的元素更小，也会先弹出原堆顶，再插入新元素。
eap = [1, 3, 2]
min_item = heapq.heapreplace(heap, 0)
print(min_item)  # 输出 1（先弹出原堆顶1）
print(heap)      # 输出 [0, 3, 2]（再插入0后的堆结构）

heapq.nlargest(n, iterable, key=None) - 获取前 n 个最大元素
功能：从可迭代对象iterable中，返回前n个最大的元素组成的列表（按从大到小排序）。
参数：key可选，用于指定排序的关键字（类似sorted函数的key参数）。
lst = [5, 3, 8, 1, 9, 2]
top3 = heapq.nlargest(3, lst)
print(top3)  # 输出 [9, 8, 5]
# 带key参数（按字典value排序）
dicts = [{'name': 'a', 'score': 90}, {'name': 'b', 'score': 80}, {'name': 'c', 'score': 95}]
top2 = heapq.nlargest(2, dicts, key=lambda x: x['score'])
print(top2)  # 输出 [{'name': 'c', 'score': 95}, {'name': 'a', 'score': 90}]

heapq.nsmallest(n, iterable, key=None) - 获取前 n 个最小元素
功能：从可迭代对象iterable中，返回前n个最小的元素组成的列表（按从小到大排序）。
参数：key可选，用法同nlargest。
lst = [5, 3, 8, 1, 9, 2]
bottom3 = heapq.nsmallest(3, lst)
print(bottom3)  # 输出 [1, 2, 3]


1、requests库常用api：

Get请求：
requests.get(url, params=None, headers=None, timeout=None)向目标 URL 发送 GET 请求（参数拼接在 URL 上）
- params：字典，URL 查询参数（如 {'key': 'value'}）
- headers：字典，请求头（如 User-Agent、Cookie）
- timeout：超时时间（秒，如 5，避免无限等待）

Post请求：
requests.post(url, data=None, json=None, headers=None)向目标 URL 发送 POST 请求（参数在请求体）
- data：表单数据（字典 / 字符串，如 {'username': 'test'}）
- json：JSON 数据（自动序列化，Content-Type 设为 application/json）

其他请求（PUT/DELETE）：
requests.put(url, ...) / requests.delete(url, ...)对应 HTTP 的 PUT/DELETE 方法
参数同 GET/POST，根据接口要求传递

# 基础示例：GET 请求 + 响应解析
import requests

url = "https://httpbin.org/get"
params = {"name": "test", "age": 20}
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 发送请求
response = requests.get(url, params=params, headers=headers, timeout=5)

# 响应核心属性
print(response.status_code)  # 响应状态码（200=成功，404=未找到，500=服务器错误）
print(response.text)         # 响应文本（字符串，自动解码）
print(response.json())       # 响应 JSON 数据（返回字典，仅适用于 JSON 响应）
print(response.content)      # 响应二进制数据（用于下载图片、文件）
print(response.headers)      # 响应头（字典）
print(response.cookies)      # 响应 Cookie（可用于维持登录状态）

session = requests.Session()  # 创建会话对象
session.post("https://xxx/login", data={"username": "a", "pwd": "b"})  # 登录
session.get("https://xxx/userinfo")  # 自动携带登录 Cookie

response = requests.get(url, verify=False)  # 禁用 SSL 证书验证
常见问题：
编码乱码：response.encoding = "utf-8" 手动指定编码；
超时错误：设置 timeout 参数（如 timeout=10）；
反爬拦截：通过 headers 携带 User-Agent、Referer 模拟浏览器。

6. 携带 Cookie
# 方式1：cookies参数
cookies = {"sessionid": "abc123"}
res = requests.get("https://httpbin.org/cookies", cookies=cookies)

# 方式2：session自动保存cookie（登录后保持会话）
session = requests.Session()
# 登录
session.post("https://httpbin.org/post", data={"user":"a"})
# 后续请求自动带上登录cookie
res = session.get("https://httpbin.org/cookies")
print(res.json())

Cookie 是服务器下发、存在浏览器 / 客户端本地的一小段文本数据（键值对），随每次请求自动发给服务端，用来标记你是谁。
Session 是存在服务端的用户会话存储空间，对应唯一的会话 ID（sessionid）
维度	       Cookie	     Session
存储位置	客户端（浏览器 / 程序）	服务端
存储内容	简单键值、会话 ID	 用户完整信息、登录态
安全性	低，可篡改	     高，用户无法修改
容量限制	很小（4KB 左右）	 服务器无严格上限
依赖关系	Session 绝大多数依赖 Cookie 传递 id	不必须，但不用 Cookie 会用 URL 传 id（不安全）

7. 超时设置、异常捕获
import requests

try:
    # 5秒超时
    res = requests.get("https://httpbin.org/get", timeout=5)
    res.raise_for_status()  # 状态码4xx/5xx直接抛异常
except requests.exceptions.Timeout:
    print("请求超时")
except requests.exceptions.ConnectionError:
    print("连接失败，网址错误/无网络")
except requests.exceptions.HTTPError as e:
    print("状态码错误", e)
except Exception as e:
    print("其他错误", e)

8. 下载二进制文件（图片 / 视频）
res = requests.get("https://httpbin.org/image/png", stream=True)
with open("test.png", "wb") as f:
    # 分块写入，防止大文件占内存
    for chunk in res.iter_content(chunk_size=1024):
        f.write(chunk)

9. 上传文件 POST
files = {"file": open("test.png", "rb")}
res = requests.post("https://httpbin.org/post", files=files)
print(res.json())

10. 代理 proxies
proxies = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890",
}
res = requests.get("https://httpbin.org/get", proxies=proxies)
代理 = 中间人服务器，你的程序不直接访问目标网站，先把请求发给代理服务器，由代理替你转发请求、拿回数据再转给你。
正常访问流程：你的程序 → 目标网站
走代理流程：你的程序 → 代理服务器 → 目标网站 → 代理服务器 → 你的程序
代理的作用：
 1、突破网络访问限制：本地无法直连的网址，通过代理中转访问。
 2、隐藏本机真实 IP：网站拿到的 IP 是代理服务器 IP，看不到你的本机公网 IP，保护隐私。
 3、缓存加速：公共代理会缓存静态资源（图片、js），重复访问更快。
 4、爬虫防封禁：爬虫大量请求时使用多个代理轮换 IP，避免本机 IP 被网站拉黑。

# httpx 完整教程（同步+异步，Cookie/Session/代理全覆盖，对比requests）
## 一、httpx 是什么
下一代 Python HTTP 客户端，**兼容 requests 语法，但更强**：
1. 同时支持**同步 + 异步**（requests 只有同步）
2. 原生支持 **HTTP/2**，多路复用，并发更快
3. 全类型注解、严格超时、连接池自动管理
4. `httpx.Client` = requests.Session（会话持久化Cookie）
5. 异步专用：`httpx.AsyncClient`，爬虫/接口并发首选

### 安装
```bash
# 基础版
pip install httpx
# 需要 socks5 代理额外装
pip install httpx[socks]
# 带命令行调试工具
pip install httpx[cli]
```

## 二、基础同步用法（和requests几乎一样）
### 1. 简单 GET/POST
```python
import httpx

# GET
res = httpx.get("https://httpbin.org/get", timeout=10)
print(res.status_code)
print(res.text)
print(res.json()) # json接口直接解析
print(str(res.url)) # url是URL对象，转字符串使用

# POST 表单
data = {"user":"admin", "pwd":"123"}
res = httpx.post("https://httpbin.org/post", data=data)

# POST json（最常用）
json_body = {"name":"张三", "id":1001}
res = httpx.post("https://httpbin.org/post", json=json_body)
```

### 2. GET 传参 params
```python
params = {"page":1, "size":20, "kw":["a","b"]}
res = httpx.get("https://httpbin.org/get", params=params)
print(str(res.url))
```

### 3. 请求头 headers（模拟浏览器）
```python
headers = {
    "User-Agent": "Mozilla/5.0 Chrome/120.0",
    "token": "xxxxxxx"
}
res = httpx.get("https://httpbin.org/get", headers=headers)
```

## 三、会话 Client（对应requests.Session，自动保存Cookie）
`httpx.Client()` 持久化 Cookie、连接池、统一headers/proxy，**爬虫必用**
```python
import httpx

# 推荐with上下文，自动关闭连接，无资源泄漏
with httpx.Client() as client:
    # 全局统一请求头
    client.headers.update({"User-Agent":"test/1.0"})

    # 登录，服务器下发Set-Cookie
    login = client.post("https://httpbin.org/post", data={"user":"test"})

    # 自动携带登录Cookie，保持会话（session会话）
    info = client.get("https://httpbin.org/cookies")
    print(info.json())

# 不使用with手动关闭
client = httpx.Client()
res = client.get("https://httpbin.org/get")
client.close()
```

### 手动设置/读取 Cookie
```python
# 单个请求临时cookie
cookies = {"sessionid":"abc123456"}
res = httpx.get("https://httpbin.org/cookies", cookies=cookies)

# client全局cookie
client = httpx.Client()
client.cookies.set("token", "xxx", domain="httpbin.org")

# 获取返回的cookie
print(res.cookies.get("sessionid"))
```

## 四、代理 proxy（http/https/socks5）
### 1. 单次请求代理
```python
# HTTP/HTTPS代理
proxies = {
    "http://": "http://127.0.0.1:7890",
    "https://": "http://127.0.0.1:7890",
}
res = httpx.get("https://httpbin.org/ip", proxies=proxies)

# SOCKS5代理（需要 httpx[socks]）
socks_proxy = {
    "http://": "socks5://127.0.0.1:1080",
    "https://": "socks5://127.0.0.1:1080",
}
res = httpx.get("https://httpbin.org/ip", proxies=socks_proxy)
```

### 2. Client全局代理（所有请求共用）
```python
proxies = {"http://":"http://127.0.0.1:7890", "https://":"http://127.0.0.1:7890"}
with httpx.Client(proxies=proxies) as client:
    res1 = client.get("https://httpbin.org/ip")
    res2 = client.get("https://httpbin.org/get") # 自动走代理
```

## 五、文件上传/流式下载
### 1. 上传文件
```python
files = {"avatar": open("test.jpg", "rb")}
res = httpx.post("https://httpbin.org/post", files=files)
```

### 2. 大文件流式下载（stream=True）
```python
res = httpx.get("https://httpbin.org/image/png", stream=True, timeout=20)
with open("out.png", "wb") as f:
    for chunk in res.iter_bytes(chunk_size=4096):
        f.write(chunk)
```

## 六、异常捕获（统一错误体系）
```python
import httpx

try:
    res = httpx.get("https://httpbin.org/get", timeout=5)
    res.raise_for_status() # 4xx/5xx抛异常
except httpx.TimeoutException:
    print("请求超时")
except httpx.ConnectError:
    print("连接失败，网址/代理错误")
except httpx.HTTPStatusError as e:
    print("响应码异常", e.response.status_code)
except httpx.RequestError as e:
    print("其他网络错误", str(e))
```

## 七、异步 AsyncClient（核心优势，requests做不到）
高并发爬虫、批量请求必用，基于 asyncio
```python
import asyncio
import httpx

async def fetch(url):
    async with httpx.AsyncClient() as client:
        res = await client.get(url, timeout=10)
        return res.json()

async def main():
    # 并发3个请求，总耗时≈最慢一个，不是叠加
    task1 = fetch("https://httpbin.org/delay/1")
    task2 = fetch("https://httpbin.org/delay/1")
    task3 = fetch("https://httpbin.org/delay/1")
    results = await asyncio.gather(task1, task2, task3)
    print(results)

if __name__ == "__main__":
    asyncio.run(main())
```
异步Client同样支持：持久Cookie、全局headers、全局proxies、HTTP/2。

## 八、开启 HTTP/2 协议（性能提升）
```
# 同步开启http2
with httpx.Client(http2=True) as client:
    res = client.get("https://httpbin.org/get")
    print(res.http_version) # HTTP/2

# 异步开启http2
async with httpx.AsyncClient(http2=True) as client:
    res = await client.get("https://httpbin.org/get")
```

## 九、httpx vs requests 关键区别
| 特性 | requests | httpx |
|------|----------|-------|
| 异步支持 | ❌ 无 | ✅ AsyncClient |
| HTTP/2 | ❌ | ✅ 原生支持 |
| 会话对象 | Session | Client / AsyncClient |
| 自动重定向 | 默认开启 | 默认关闭，需加 `follow_redirects=True` |
| url类型 | 字符串 | URL对象，需`str(res.url)` |
| 类型注解 | 无 | 完整类型提示 |
| 默认超时 | 无（会卡死） | 默认5秒，强制超时保护 |
| socks代理 | 需要requests[socks] | 需要httpx[socks] |

### 重定向差异举例（坑点）
```python
# httpx默认不跟随301/302，要手动开启
res = httpx.get("https://httpbin.org/redirect/1", follow_redirects=True)
```

## 十、Cookie & Session 在 httpx 里的逻辑（对应之前概念）
1. **Cookie**：服务器返回存在 `client.cookies`，每次请求自动携带；存在客户端，可读取修改。
2. **Client（会话容器）** = 维持浏览器会话，等价网页Session机制：
   - 登录接口返回 `sessionid` 存入Cookie
   - 同一个Client实例后续请求自动带上sessionid
   - 服务端通过sessionid读取你的登录态（网页Session）
3. 代理Proxy：Client全局配置，所有请求通过中间人转发，隐藏本机IP。

## 十一、通用封装模板（可直接复制）
### 同步通用请求封装（带会话、代理、异常）
```
import httpx

def create_client(proxy=None):
    headers = {
        "User-Agent": "Mozilla/5.0 Windows Chrome",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }
    client_kwargs = {"headers": headers, "timeout": 10, "follow_redirects": True}
    if proxy:
        client_kwargs["proxies"] = proxy
    return httpx.Client(**client_kwargs)

# 使用
if __name__ == "__main__":
    proxy_cfg = {"http://":"http://127.0.0.1:7890", "https://":"http://127.0.0.1:7890"}
    with create_client(proxy=proxy_cfg) as client:
        try:
            res = client.get("https://httpbin.org/get")
            res.raise_for_status()
            print(res.json())
        except httpx.RequestError as e:
            print("请求失败：", e)
```


2、numpy库常用api：

从列表创建	np.array(list, dtype=None)	 np.array([1,2,3]) → 一维数组；np.array([[1,2],[3,4]]) → 二维数组
全 0 数组	np.zeros(shape, dtype=np.float64)	 np.zeros((2,3)) → 2 行 3 列全 0 数组
全 1 数组	np.ones(shape)	 np.ones((3,3)) → 3 行 3 列全 1 数组
随机数组	np.random.rand(shape)（0-1 均匀分布）/ np.random.randn(shape)（正态分布）	 np.random.rand(2,2) → 2 行 2 列随机数组
范围数组	np.arange(start, stop, step)	 np.arange(0, 10, 2) → [0,2,4,6,8]
等间隔数组	np.linspace(start, stop, num)	 np.linspace(0, 10, 5) → 0 到 10 等分 5 个值

import numpy as np

# 创建示例数组
arr = np.array([[1,2,3], [4,5,6], [7,8,9]])  # 3行3列二维数组

# 1. 数组属性
print(arr.shape)  # 数组形状 → (3,3)
print(arr.ndim)   # 数组维度 → 2
print(arr.dtype)  # 数据类型 → int64
print(arr.size)   # 元素总数 → 9
print(arr.reshape(1,9))  # 重塑形状 → (1,9)（1行9列）
print(arr.flatten())     # 展平为一维数组 → [1 2 3 4 5 6 7 8 9]

# 2. 索引与切片（类似列表，但支持多维）
# 一维数组切片
brr=[1,2,3,4,5]
print(brr[:3])  # 返回[1,2,3] 即第二个参数不从0开始数
print(brr[2:3])  # 返回[3]
print(brr[start:stop:step])  # 返回下标从start到下标stop-1的数组
# 二维数组索引
print(arr[0, 1])  # 第0行第1列 → 2
print(arr[1:3, 0:2])  # 行1-2，列0-1 → [[4,5],[7,8]]
print(arr[:, 2])  # 所有行的第2列 → [3,6,9]

# 3. 条件索引
print(arr[arr > 5])  # 所有大于5的元素 → [6,7,8,9]
arr[arr > 5] = 0     # 大于5的元素赋值为0 → [[1,2,3],[4,5,0],[0,0,0]]

arr1 = np.array([[1,2], [3,4]])
arr2 = np.array([[5,6], [7,8]])

# 1. 元素级运算（无需循环，向量ized 操作）
print(arr1 + arr2)  # 加法 → [[6,8],[10,12]]
print(arr1 * arr2)  # 乘法（元素级）→ [[5,12],[21,32]]
print(arr1 ** 2)    # 平方 → [[1,4],[9,16]]
print(np.sqrt(arr1))# 平方根 → [[1.,1.414],[1.732,2.]]

# 2. 矩阵运算
print(np.dot(arr1, arr2))  # 矩阵乘法 → [[1*5+2*7, 1*6+2*8], [3*5+4*7, 3*6+4*8]] → [[19,22],[43,50]]
print(arr1 @ arr2)         # 矩阵乘法简写（同 dot）

# 3. 统计计算
print(arr1.sum())        # 所有元素求和 → 10
print(arr1.sum(axis=0))  # 按列求和 → [4,6]
print(arr1.sum(axis=1))  # 按行求和 → [3,7]
print(arr1.mean())       # 均值 → 2.5
print(arr1.max())        # 最大值 →4
print(arr1.min(axis=0))  # 按列求最小值 → [1,2]
print(np.median(arr1))   # 中位数 → 2.5

arr3 = np.array([[1,2,3], [4,5,6]])  # (2,3)
arr4 = np.array([10, 20, 30])        # (3,)
print(arr3 + arr4)  # 自动广播 arr4 为 (2,3) → [[11,22,33],[14,25,36]]

numpy库的文件保存：np.save（"保存名称"，保存内容）
文件内容导入a=np.load("文件名")



3、pandas数据分析库常用api：

pip install pandas openpyxl  # openpyxl 用于读取 Excel 文件
Series：一维数组（带索引）；
DataFrame：二维表格（行索引 + 列索引，最常用）。

读取 CSV 文件	pd.read_csv("file.csv", encoding="utf-8")	df = pd.read_csv("data.csv")
读取 Excel 文件	pd.read_excel("file.xlsx", sheet_name="Sheet1")	df = pd.read_excel("data.xlsx")
保存为 CSV	df.to_csv("output.csv", index=False)	index=False 不保存行索引
保存为 Excel	df.to_excel("output.xlsx", sheet_name="结果", index=False)	需安装 openpyxl 库
创建 DataFrame	pd.DataFrame(data, columns=["列1", "列2"])	data = [["a", 1], ["b", 2]]; df
= pd.DataFrame(data, columns=["name", "age"])

import pandas as pd

# 创建示例 DataFrame
data = {
    "name": ["张三", "李四", "王五", "张三"],
    "age": [20, 25, 30, 20],
    "score": [85, 92, 78, 88]
}
df = pd.DataFrame(data)

# 1. 数据查看
print(df.head(2))  # 查看前 2 行（默认 5 行）
print(df.tail(1))  # 查看最后 1 行
print(df.info())   # 查看数据类型、非空值数量
print(df.describe())  # 数值列统计信息（均值、标准差、最值等）
print(df.columns)  # 查看所有列名
print(df.index)    # 查看行索引

# 2. 数据筛选（核心）
# 按列筛选
df["name"]  # 单个列（返回 Series）
df[["name", "score"]]  # 多个列（返回 DataFrame）

# 按行筛选（条件筛选）
df[df["age"] > 22]  # 年龄大于 22 的行
df[(df["age"] > 20) & (df["score"] >= 80)]  # 多条件（&=且，|=或，需用括号包裹）
df[df["name"].isin(["张三", "李四"])]  # 姓名在列表中

# 按索引筛选
df.loc[0]  # 按行索引（标签）筛选第 0 行
df.loc[1:3, ["name", "score"]]  # 行索引 1-3，列 name/score
df.iloc[0:2, 0:2]  # 按位置索引（行 0-1，列 0-1）

# 1. 缺失值处理
df.dropna()  # 删除含缺失值的行（默认 axis=0）
df.dropna(axis=1)  # 删除含缺失值的列
df.fillna(0)  # 缺失值填充为 0
df.fillna(df["score"].mean())  # 缺失值填充为 score 列的均值

# 2. 重复值处理
df.drop_duplicates()  # 删除完全重复的行
df.drop_duplicates(subset=["name"], keep="first")  # 按 name 列去重，保留第一次出现的行

# 3. 列操作
df["new_col"] = df["score"] + 5  # 新增列（score+5）
df.drop("new_col", axis=1)  # 删除列
df.rename(columns={"name": "姓名", "age": "年龄"})  # 列名重命名

# 4. 数据排序
df.sort_values(by="score", ascending=False)  # 按 score 降序排序（ascending=True 升序）

# 按 name 分组，计算 score 的均值、最大值
grouped = df.groupby("name")["score"].agg(["mean", "max"])
print(grouped)
# 输出：
#       mean  max
# name
# 张三    86.5   88
# 李四    92.0   92
# 王五    78.0   78

# 按 name 和 age 多列分组
df.groupby(["name", "age"])["score"].sum()


# 示例：两个 DataFrame 合并
df1 = pd.DataFrame({"name": ["张三", "李四"], "age": [20, 25]})
df2 = pd.DataFrame({"name": ["张三", "王五"], "score": [85, 78]})

# 按 name 列合并（类似 SQL join）
pd.merge(df1, df2, on="name", how="inner")  # inner join（默认，只保留共同 name）
pd.merge(df1, df2, on="name", how="left")   # left join（保留 df1 所有行）

axis：0 表示行（默认），1 表示列（如 dropna(axis=1) 删除列）；
ascending：排序时是否升序（默认 True）；
how：合并时的连接方式（inner/left/right/outer）。



4、matplotlib（基础静态绘图库）常用api：

matplotlib库解决中文显示问题1-2
1：
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']  # 设置全局中文字体
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示异常问题
2：
plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows：黑体；Mac：Arial Unicode MS
plt.rcParams['axes.unicode_minus'] = False  # 正常显示负号

import matplotlib.pyplot as plt
import numpy as np

# 1. 创建画布（可选，默认自动创建）
plt.figure(figsize=(8, 4))  # figsize=(宽, 高)，单位英寸

# 2. 绘制图表（核心步骤）
x = np.linspace(0, 10, 100)  # 0-10 生成 100 个均匀点
y = np.sin(x)
plt.plot(x, y, label="sin(x)", color="blue", linewidth=2)  # 折线图

# 3. 设置标签、标题、图例（美化+信息补充）
plt.xlabel("X 轴", fontsize=12)  # X轴标签
plt.ylabel("Y 轴", fontsize=12)  # Y轴标签
plt.title("正弦函数图像", fontsize=14, pad=20)  # 标题（pad=标题与图表间距）
plt.legend(loc="upper right")  # 图例位置（upper right/center/etc.）

# 4. 调整刻度（可选）
plt.xticks(np.arange(0, 11, 2))  # X轴刻度：0,2,...,10
plt.yticks([-1, 0, 1], labels=["-1", "0", "1"])  # Y轴刻度与显示标签

# 5. 显示/保存图片
plt.grid(alpha=0.3)  # 添加网格（alpha=透明度）
plt.savefig("sin_plot.png", dpi=300, bbox_inches="tight")  # 保存（dpi=分辨率）
plt.show()  # 显示图片（必须放在最后）

图表类型	语法示例	关键参数说明
柱状图	python x = ["A", "B", "C"] y = [3, 7, 5]
plt.bar(x, y, color=["red", "green", "blue"], width=0.6) # 横向柱状图用
 plt.barh(x, y)	  - width：柱子宽度（0-1）   - color：柱子颜色（列表 / 单个颜色）

散点图	python x = np.random.rand(50) y = np.random.rand(50) size = np.random.randint(20, 100, 50) # 点大小
color = np.random.rand(50) # 点颜色
plt.scatter(x, y, s=size, c=color, alpha=0.7, cmap="viridis")
plt.colorbar() # 显示颜色条	- s：点大小  - c：点颜色（可传数组）   - cmap：颜色映射（如 viridis/plasma）

直方图	python data = np.random.normal(0, 1, 1000) # 正态分布数据
 plt.hist(data, bins=30, color="orange", edgecolor="black", alpha=0.7)
 - bins：柱子数量（越多越精细）
- edgecolor：柱子边框颜色

子图（多图共存）	python
 # 2行1列子图，第1个图
  plt.subplot(2, 1, 1)
  plt.plot(x, np.sin(x))
  plt.title("sin(x)")

  # 2行1列子图，第2个图
  plt.subplot(2, 1, 2)
  plt.plot(x, np.cos(x), color="red")
  plt.title("cos(x)")
  plt.tight_layout() # 自动调整子图间距
  - subplot(行, 列, 索引)：索引从 1 开始



5、seaborn（美化 + 统计绘图库）常用api：

import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

# 设置 seaborn 风格（可选：darkgrid/whitegrid/dark/white/ticks）
sns.set_style("whitegrid")
# 设置图片尺寸
plt.figure(figsize=(8, 4))

美化折线图
# 创建 DataFrame
data = pd.DataFrame({ "x": np.linspace(0, 10, 100), "sin(x)": np.sin(x), "cos(x)": np.cos(x) })
# 绘制多折线图
 sns.lineplot(data=data, x="x", y="sin(x)", label="sin(x)", linewidth=2)
 sns.lineplot(data=data, x="x", y="cos(x)", label="cos(x)", color="red", linewidth=2)
 plt.xlabel("X 轴")
 plt.ylabel("Y 轴")
 plt.title("seaborn 折线图")
 plt.legend()
 plt.show()	替代 matplotlib 折线图，默认样式更美观

热力图（相关性矩阵）
# 生成相关性矩阵
data = pd.DataFrame(np.random.rand(5, 5), columns=["A", "B", "C", "D", "E"]) corr = data.corr()
# 绘制热力图
sns.heatmap( corr, annot=True, # 显示数值 fmt=".2f", # 数值格式（保留2位小数） cmap="RdBu_r", # 颜色映射（红-蓝） center=0, # 颜色中心值 square=True # 正方形格子 )
 plt.title("相关性热力图")
 plt.show()	展示变量间相关性（数据分析高频）

箱线图（统计分布）
# 创建数据
data = pd.DataFrame({ "group": ["A"]*50 + ["B"]*50, "value": np.concatenate([np.random.normal(10, 2, 50), np.random.normal(15, 2, 50)]) })
# 绘制箱线图
sns.boxplot(data=data, x="group", y="value", palette="Set2")
plt.title("两组数据分布箱线图")
plt.show()	展示数据中位数、四分位数、异常值

分类散点图
# 绘制带分类的散点图
sns.scatterplot(data=data, x="group", y="value", hue="group", palette="Set1", s=50, alpha=0.7)
 plt.title("分类散点图")
 plt.show()	区分不同类别数据的分布

小提琴图（分布密度）
sns.violinplot(data=data, x="group", y="value", palette="Set3", inner="quartile")# inner：显示四分位数
plt.title("小提琴图（分布密度）")
plt.show()	结合箱线图和核密度图，展示数据分布形状



6、plotly（交互式绘图库）常用api：

 plotly.express（简称 px）是高层 API，语法简洁；
 plotly.graph_objects 是底层 API，更灵活。

import plotly.express as px
import numpy as np
import pandas as pd

# 创建数据
x = np.linspace(0, 10, 100)
data = pd.DataFrame({
    "x": x,
    "sin(x)": np.sin(x),
    "cos(x)": np.cos(x)
})

# 绘制交互式折线图
fig = px.line(
    data,
    x="x",
    y=["sin(x)", "cos(x)"],  # 多列数据自动生成多条线
    title="交互式正弦/余弦函数图",
    labels={"value": "Y 值", "variable": "函数类型"},  # 轴标签和图例标签
    color_discrete_map={"sin(x)": "blue", "cos(x)": "red"}  # 自定义颜色
)

# 调整布局（可选）
fig.update_layout(
    xaxis_title="X 轴",
    yaxis_title="Y 轴",
    legend_title="函数",
    hovermode="x unified"  # 鼠标悬停时显示同一 x 下所有 y 值
)

# 显示图表（浏览器打开）/ 保存为 HTML
fig.show()
fig.write_html("interactive_plot.html")  # 保存后可直接用浏览器打开


高频交互式图表
图表类型	语法示例	交互特性
交互式柱状图
 data = pd.DataFrame({ "category": ["A", "B", "C", "D"], "value": [3, 7, 5, 9] })
 fig = px.bar( data, x="category", y="value", color="category", title="交互式柱状图", text="value" # 柱子上显示数值 )
 fig.show()	悬停显示数值，可缩放、下载

3D 散点图
 data = pd.DataFrame({ "x": np.random.rand(100), "y": np.random.rand(100), "z": np.random.rand(100), "category": np.random.choice(["A", "B"], 100) })
 fig = px.scatter_3d( data, x="x", y="y", z="z", color="category", title="3D 交互式散点图", size_max=10 )
fig.show()	可旋转、缩放 3D 视角

交互式直方图
data = pd.DataFrame({ "value": np.random.normal(0, 1, 1000) })
fig = px.histogram( data, x="value", nbins=30, title="交互式直方图", color_discrete_sequence=["orange"], marginal="box" # 边缘添加箱线图 )
fig.show()	悬停显示区间计数，可调整区间大小

热力图
data = pd.DataFrame(np.random.rand(5, 5), columns=["A", "B", "C", "D", "E"])
fig = px.imshow( data, title="交互式热力图", labels=dict(x="列", y="行", color="数值"), color_continuous_scale="RdBu_r" )
 fig.show()	悬停显示具体数值，可调整颜色范围


库名	核心特性	适用场景	优点	缺点
matplotlib	基础静态绘图，高度定制	科研论文、静态报告、需要精确调整图表细节	功能全面，可定制性强，生态成熟	默认样式较丑，需手动调整美化
seaborn	美化统计绘图，衔接 pandas	数据分析、统计报告、快速生成专业图表	样式美观，支持统计可视化，易用	交互式弱，仅支持静态图
plotly	交互式绘图，支持网页展示	网页演示、动态报告、需要用户交互的场景	交互性强，跨平台，支持 3D / 动态	静态图美化不如 seaborn，体积较大


连接数据库模板代码
import pymysql
# 建立数据库连接
connection = pymysql.connect(
    host='localhost',      # 数据库服务器地址
    user='root',           # 数据库用户名
    password='052834',     # 数据库密码
    database='mydb',       # 数据库名
    port=3306,             # 端口（默认3306）
    autocommit=True,       #设置自动提交
    charset='utf8mb4',     # 字符集
    cursorclass=pymysql.cursors.DictCursor # 让结果以字典形式返回，可选
)
try:
    # 创建一个游标对象，用于执行SQL语句
    with connection.cursor() as cursor:
       cursor.select_db() #选择数据库
        # 编写一个示例查询
        sql = "SELECT * FROM student LIMIT 5;" # 在这里编写SQL语句
        cursor.execute(sql)   #执行查询
        cursor.commit #进行数据更改时确认
        # 获取所有结果
        results = cursor.fetchall()
        for row in results:
            print(row) # 打印每一行数据
finally:
    # 关闭连接
    connection.close()
'''