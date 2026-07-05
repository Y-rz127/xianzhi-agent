# 从typing模块导入各类类型注解相关工具，用于实现更丰富的类型约束
from typing import List, Union, Dict, Tuple, Set, Any, Literal, Optional, NewType, TypeVar, Sequence

# ---------------------- 一、基本数据类型注解（Python内置基础类型） ----------------------
# python 类型注解 type hints：用于标注变量、函数参数/返回值的类型，提升代码可读性和可维护性
# 注意：Python 是动态类型语言，类型注解仅为「提示」，不做强制类型检查（运行时可传入其他类型）

# 整型注解：标注变量age为整数类型
age: int = 18
# 字符串类型注解：标注变量name为字符串类型（注：原注释"证书类型"为笔误，应为"字符串类型"）
name: str = "Jane"
# 浮点型注解：标注变量price为浮点小数类型
price: float = 10.5
# 布尔类型注解：标注变量is_valid为布尔类型（True/False），此处显式添加注解更规范
is_valid: bool = True
# 字节类型注解：标注变量data为字节类型（以b开头的字节串，常用于二进制数据处理）
data: bytes = b"Hello World"

# 打印基本类型变量，验证赋值结果
print(age, name, price, is_valid, data)

# 函数的类型注解：参数注解 + 返回值注解
# 注解说明：参数a、b为int类型，-> 后面标注函数返回值为int类型
# 注意：Python 不强制类型校验，传入非int类型（如字符串）调用时，语法不报错，但运行时运算会抛出异常
def add(a: int, b: int) -> int:
    return a + b


# ---------------------- 二、引用数据类型注解（容器/集合类型） ----------------------
# 列表（List）注解：标注scores为「存储int类型元素的列表」，List[]内指定列表元素的类型
scores: List[int] = [80, 90, 100]
# 二维列表注解：标注matrix为「存储int类型二维列表的列表」，即嵌套列表（二维数组）
matrix: List[List[int]] = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

# 字典（Dict）注解：Dict[KeyType, ValueType]，分别指定键和值的类型
# 标注person为「键是str类型、值也是str类型」的字典
person: Dict[str, str] = {"name": "Jane", "age": "18"}  # 注意：age值此处改为字符串，匹配注解类型
# 混合类型字典注解：使用Union[]指定值可以是str、int中的一种（布尔类型True/False本质是int子类）
config: Dict[str, Union[str, int]] = {"port": 8080, "timeout": 5, "debug": True, "host": "localhost"}

# 打印列表和字典变量，验证赋值结果
print(scores, matrix, person, config)

# 元组（Tuple）注解：有两种常见形式，固定长度和可变长度
# 固定长度元组：明确指定每个元素的类型（此处二元元组，两个元素均为int类型），对应坐标场景
point: Tuple[int, int] = (10, 20)
# 固定长度元组：三元元组，三个元素均为int类型，对应RGB颜色值场景
rgb: Tuple[int, int, int] = (255, 0, 0)
# 可变长度元组：使用...表示元组长度不限，所有元素均为int类型
flexible: Tuple[int, ...] = (1, 2, 3, 4, 5)

# 集合（Set）注解：Set[]内指定集合元素的类型，集合自动去重，元素无序
# 标注unique_ids为「存储str类型元素的集合」
unique_ids: Set[str] = {"red", "green", "blue"}
# 混合类型集合注解：使用Union[]指定集合元素可以是str或int类型
tags: Set[Union[str, int]] = {"python", 1, 2, 3}

# 打印元组和集合变量，验证赋值结果
print(point, rgb, flexible, unique_ids, tags)


# ---------------------- 三、特殊类型注解（Any、Literal、Union、Optional） ----------------------
# Any 类型：表示「任意类型」，解除类型约束，适用于无法确定类型的场景
any_value: Any = "Any"
any_value = 123  # 可随意修改为其他类型，无类型提示警告

# 函数注解：参数a为任意类型，返回值为None（表示函数无返回结果）
def func(a: Any) -> None:
    print(a)

# 函数类型注解（补充）：参数为str类型，返回值为str类型
def function(nick_name: str) -> str:
    return f"hello，{nick_name}"

# Literal 字面量类型：限定变量/参数只能取指定的几个字面量值（类似简易枚举，非强类型检查）
# 定义http_method类型，只能取"GET"、"POST"、"PUT"三个字符串中的一个
HttpMethod = Literal["GET", "POST", "PUT"]  # 规范命名：首字母大写，区分变量

# 函数参数使用Literal限定类型，确保传入的请求方法只能是指定值
def send_request(method: HttpMethod) -> None:
    print(f"Sending {method} request...")

# 调用函数：传入合法的Literal值"POST"，符合类型注解要求
send_request("POST")

# Union 类型：用于标注「多种可选类型中的一种」，常用于参数/返回值支持多种类型的场景
# 函数注解：参数input可以是str类型或int类型，无返回值
def process_input(input: Union[str, int]) -> None:
    if isinstance(input, str):
        print(f"Processing string input: {input}")
    elif isinstance(input, int):
        print(f"Processing integer input: {input}")
    else:
        # 抛出异常：处理非Union指定的类型（理论上可通过类型注解避免，此处做容错处理）
        raise TypeError("Unsupported input type, only str and int are allowed.")

# 调用函数：传入合法的str和int类型
print(process_input("Hello"))
print(process_input(123))
# 调用函数：传入bool类型（本质是int子类，部分场景会被识别为int，此处会触发异常）
# print(process_input(True))

# Optional 类型：表示「可选类型」，等价于 Union[指定类型, None]，即允许值为指定类型或None
# 函数注解：参数name为可选的str类型，默认值为None（可传参、可不传参）
def greet(name: Optional[str] = None) -> None:
    if name:
        print(f"Hello, {name}!")
    else:
        print("Hello!")

# 函数注解：参数name为可选的str类型（允许为None），但无默认值，调用时必须传参（可传None）
def greet2(name: Optional[str]) -> None:
    if name:
        print(f"Hello, {name}!")
    else:
        print("Hello!")

# 调用greet：可不传参（使用默认值None）、可传字符串
print(greet())
print(greet("Jane"))
# 调用greet2：必须传参，可传None或字符串（不传参会报错）
print(greet2(None))
# print(greet2())  # 报错：缺少必要参数name


# ---------------------- 四、类型别名与自定义类型（Type Alias、NewType） ----------------------
# 基本类型别名：为已有类型创建别名，提升代码可读性（仅别名，无类型隔离，本质还是原类型）
UserId = int  # 为int类型创建别名UserId，用于标注用户ID
Point = Tuple[int, int]  # 为二元int元组创建别名Point，用于标注坐标点

# 使用类型别名注解函数参数
def get_user_name(id: UserId) -> str:
    return f"User {id}"

# 使用类型别名注解函数参数（列表元素为Point类型）
def plot(points: List[Point]) -> float:
    for x, y in points:
        print(f"Plotting point ({x}, {y})")
    return 0.0  # 补充返回值，匹配函数注解（此处为示例，返回0.0）

# NewType：创建自定义类型对象，与原类型有「逻辑上的隔离」（本质是包装，运行时仍为原类型）
# 定义自定义类型UserId，基于int类型创建，用于区分普通int和用户ID
UserId = NewType('UserId', int)
# 创建自定义类型实例：必须通过NewType定义的构造函数创建
admin_id = UserId(1)

# 函数参数使用NewType自定义类型注解
def get_user_name_new(id: UserId) -> str:
    return f"User {id}"

# 调用函数：传入NewType实例，符合类型注解要求
print(get_user_name_new(admin_id))
# 注意：直接传入int类型（如1001），部分编辑器会给出类型提示警告，但运行时不报错（无强制隔离）
print(get_user_name_new(UserId(1001)))  # 规范写法：显式包装为UserId类型


# ---------------------- 五、泛型注解（TypeVar、Sequence） ----------------------
# TypeVar：定义泛型变量，实现「类型复用」，支持约束或无约束类型
T = TypeVar('T')  # 无约束泛型：可以是任意类型
Num = TypeVar('Num', int, float)  # 有约束泛型：只能是int或float类型（数值类型）

# 有约束泛型函数：参数a、b必须是Num类型（int/float），返回值也为Num类型
def add_generic(a: Num, b: Num) -> Num:
    return a + b

# 调用泛型函数：传入int类型，符合约束要求
print(add_generic(1, 2))

# 无约束泛型函数：参数a、b为同一泛型类型T，返回值也为T类型（保证输入输出类型一致）
def add2_generic(a: T, b: T) -> T:
    return a + b
