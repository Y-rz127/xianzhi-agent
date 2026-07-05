import os
# 导入必要的第三方库和MCP服务器核心模块
import httpx  # 用于发送异步HTTP请求的库，替代requests的异步实现
from mcp.server.fastmcp import FastMCP  # 导入FastMCP框架，用于快速构建MCP工具服务
from typing import Any, Dict, Optional  # 导入类型注解相关工具，提升代码可维护性和类型安全性

# ========================================
# 全局配置与MCP服务器初始化
# ========================================
# 初始化FastMCP服务器实例，指定服务名称为"amap-weather"
# 该服务主要提供基于高德地图API的天气查询相关功能
mcp = FastMCP("amap-weather")

# 高德地图API相关全局配置（需用户根据实际情况替换/配置）
AMAP_API_BASE = "https://restapi.amap.com/v3"  # 高德地图API的基础请求地址
AMAP_API_KEY = os.getenv("AMAP_MAPS_API_KEY", "")  # 高德地图API密钥（必填）
# 注意：请前往高德开放平台申请有效的API Key，该测试密钥可能已失效
# 申请地址：https://lbs.amap.com/
USER_AGENT = "amap-weather-app/1.0"  # 请求头中的用户代理标识，用于标识请求来源


# ========================================
# 核心工具函数：高德API请求发送
# ========================================
async def make_amap_request(endpoint: str, params: dict) -> Optional[Dict[str, Any]]:
    """
    封装高德地图API的异步请求发送逻辑，包含完整的错误处理机制

    Args:
        endpoint: API接口路径（如"/weather/weatherInfo"，需以/开头）
        params: 接口所需的业务请求参数（无需包含key和output）

    Returns:
        Optional[Dict[str, Any]]: 成功返回API响应的JSON数据字典，失败返回None
    """
    print('正在发送高德API请求...make_amap_request')

    # 构造基础请求参数，所有接口都需要携带key和output格式指定
    base_params = {
        'key': AMAP_API_KEY,  # 接口调用凭证，必填
        'output': 'JSON'  # 指定响应数据格式为JSON，方便后续解析
    }

    # 合并基础参数和业务参数（业务参数可覆盖基础参数，提升灵活性）
    full_params = {**base_params, **params}

    # 异步创建HTTP客户端，使用上下文管理器自动管理客户端生命周期
    async with httpx.AsyncClient() as client:
        try:
            # 发送GET异步请求，获取高德API响应
            response = await client.get(
                url=f'{AMAP_API_BASE}{endpoint}',  # 拼接完整的请求URL
                params=full_params,  # 传递拼接后的完整请求参数
                headers={'User-Agent': USER_AGENT},  # 设置请求头，标识客户端身份
                timeout=30.0  # 设置30秒请求超时时间，防止长时间阻塞
            )

            # 检查HTTP响应状态码，非2xx状态码会抛出HTTPStatusError异常
            response.raise_for_status()

            # 解析响应数据为JSON格式（字典类型）
            data = response.json()

            # 处理高德API自身的业务错误（HTTP状态码200不代表业务请求成功）
            # 高德API约定：status为'1'表示业务请求成功，其他值为失败
            if data.get("status") != '1':
                err_msg = data.get("info", "未知错误")  # 获取API返回的错误描述信息
                print(f"高德API请求失败: {err_msg}")
                return None

            # 业务请求成功，返回解析后的JSON数据
            return data

        # 捕获所有可能的异常（网络异常、超时、JSON解析失败等）
        except Exception as e:
            print(f"请求异常: {str(e)}")
            return None


# ========================================
# 数据格式化函数：天气数据转可读文本
# ========================================
def format_weather_forecast(data: Dict[str, Any]) -> str:
    """
    格式化实时天气数据（简化版），转换为人类可读的简洁文本

    Args:
        data: 高德API返回的天气数据字典

    Returns:
        str: 格式化后的简洁天气信息字符串
    """
    try:
        # 校验数据是否包含有效实时天气字段（lives为高德API实时天气数据关键字段）
        if 'lives' in data and data['lives']:
            weather_info = data['lives'][0]  # 取第一个元素（对应查询城市的天气数据）
            city = weather_info.get('city', '未知城市')  # 城市名称
            weather = weather_info.get('weather', '未知天气')  # 天气状况
            temperature = weather_info.get('temperature', '未知')  # 温度
            humidity = weather_info.get('humidity', '未知')  # 湿度

            # 拼接简洁的天气信息字符串并返回
            return f"{city}天气：{weather}，温度：{temperature}℃，湿度：{humidity}%"
        else:
            # 数据中无有效实时天气字段
            return "未找到天气信息"
    except Exception as e:
        # 捕获数据格式化过程中的异常（如字段缺失、类型错误等）
        print(f"格式化天气数据时出错: {str(e)}")
        return "天气数据格式错误"


def format_realtime_weather(data: Dict[str, Any]) -> str:
    """
    格式化实时天气数据（详细版），包含更多气象信息

    Args:
        data: 高德API返回的天气数据字典

    Returns:
        str: 格式化后的详细实时天气信息字符串
    """
    try:
        # 校验数据是否包含有效实时天气字段
        if 'lives' in data and data['lives']:
            live = data['lives'][0]  # 取第一个元素（对应查询城市的实时天气数据）
            # 从数据中提取各类气象信息，指定默认值防止字段缺失导致报错
            city = live.get('city', '未知城市')
            weather = live.get('weather', '未知')
            temperature = live.get('temperature', '未知')
            wind_direction = live.get('winddirection', '未知')
            wind_power = live.get('windpower', '未知')
            humidity = live.get('humidity', '未知')
            report_time = live.get('reporttime', '未知')

            # 拼接详细的实时天气信息，采用分行格式提升可读性
            return (f"【{city}实时天气】\n"
                    f"天气状况：{weather}\n"
                    f"温度：{temperature}℃\n"
                    f"风向：{wind_direction}\n"
                    f"风力：{wind_power}级\n"
                    f"湿度：{humidity}%\n"
                    f"发布时间：{report_time}")
        else:
            # 数据中无有效实时天气字段
            return "未找到实时天气数据"
    except Exception as e:
        # 捕获数据格式化过程中的异常
        print(f"格式化实时天气数据时出错: {str(e)}")
        return "实时天气数据格式错误"


def format_forecast(data: Dict[str, Any]) -> str:
    """
    格式化未来多天天气预报数据，转换为人类可读的文本

    Args:
        data: 高德API返回的天气预报数据字典

    Returns:
        str: 格式化后的未来3天天气预报信息字符串
    """
    try:
        # 校验数据是否包含有效天气预报字段（forecasts为高德API预报数据关键字段）
        if 'forecasts' in data and data['forecasts']:
            forecast = data['forecasts'][0]  # 取第一个元素（对应查询城市的预报数据）
            city = forecast.get('city', '未知城市')  # 城市名称
            casts = forecast.get('casts', [])  # 每日预报数据列表

            # 初始化结果列表，用于拼接多行预报信息
            result = [f"【{city}天气预报】"]

            # 遍历前3天的预报数据（避免数据过多，提升可读性）
            for cast in casts[:3]:
                # 提取每日预报的详细信息，指定默认值防止字段缺失
                date = cast.get('date', '未知日期')
                day_weather = cast.get('dayweather', '未知')
                night_weather = cast.get('nightweather', '未知')
                day_temp = cast.get('daytemp', '未知')
                night_temp = cast.get('nighttemp', '未知')
                day_wind = cast.get('daywind', '未知')
                night_wind = cast.get('nightwind', '未知')
                day_power = cast.get('daypower', '未知')
                night_power = cast.get('nightpower', '未知')

                # 拼接单日预报信息，添加到结果列表中
                result.append(
                    f"\n{date}：\n"
                    f"  白天：{day_weather}，{day_temp}℃，{day_wind}风{day_power}级\n"
                    f"  夜间：{night_weather}，{night_temp}℃，{night_wind}风{night_power}级"
                )

            # 将结果列表拼接为完整字符串并返回
            return "\n".join(result)
        else:
            # 数据中无有效天气预报字段
            return "未找到天气预报数据"
    except Exception as e:
        # 捕获数据格式化过程中的异常
        print(f"格式化天气预报数据时出错: {str(e)}")
        return "天气预报数据格式错误"


# ========================================
# MCP工具注册：对外暴露的天气查询接口
# ========================================
@mcp.tool()
async def get_weather(city: str) -> str:
    """
    获取指定城市的天气信息（简化版，通过城市名称查询）

    Args:
        city: 城市名称（如"北京"、"上海"，支持中文全称）

    Returns:
        str: 格式化后的简洁天气信息字符串
    """
    # 构造天气查询请求参数
    params = {
        'city': city,  # 目标城市名称
        'extensions': 'base'  # 查询类型：base=实时天气，all=未来天气预报
    }

    # 调用封装的高德API请求函数，获取天气数据
    data = await make_amap_request("/weather/weatherInfo", params)

    # 校验数据是否获取成功，返回对应结果
    if data is None:
        return "获取天气信息失败，请检查网络连接或API配置"

    # 格式化天气数据并返回
    return format_weather_forecast(data)


@mcp.tool()
async def get_realtime_weather(city_adcode: str) -> str:
    """
    获取中国城市实时天气（详细版，通过城市编码查询，精度更高）

    Args:
        city_adcode: 城市编码（如北京110000，上海310000，可通过高德城市编码表查询）

    Returns:
        str: 格式化后的详细实时天气信息字符串
    """
    print('正在获取实时天气...get_realtime_weather')

    # 调用封装的高德API请求函数，获取详细实时天气数据
    data = await make_amap_request(
        endpoint='/weather/weatherInfo',  # 天气查询接口路径
        params={'city': city_adcode, 'extensions': 'base'}  # 查询参数：城市编码+实时天气
    )

    # 校验数据是否有效，返回对应结果
    if not data or not data.get('lives'):
        return '无法获取实时天气数据（请检查城市编码或API Key）'

    # 格式化详细实时天气数据并返回
    return format_realtime_weather(data)


@mcp.tool()
async def get_forecast(city_adcode: str) -> str:
    """
    获取中国城市未来多天天气预报（通过城市编码查询，精度更高）

    Args:
        city_adcode: 城市编码（如北京110000，上海310000，可通过高德城市编码表查询）

    Returns:
        str: 格式化后的未来3天天气预报信息字符串
    """
    # 调用封装的高德API请求函数，获取天气预报数据
    data = await make_amap_request(
        endpoint='/weather/weatherInfo',  # 天气查询接口路径
        params={'city': city_adcode, 'extensions': 'all'}  # 查询参数：城市编码+未来预报
    )

    # 校验数据是否有效，返回对应结果
    if not data or not data.get('forecasts'):
        return '无法获取天气预报数据（请检查城市编码或API Key）'

    # 格式化天气预报数据并返回
    return format_forecast(data)


# ========================================
# 程序入口：启动MCP服务器
# ========================================
if __name__ == "__main__":
    # 启动FastMCP服务器，采用stdio（标准输入输出）进行通信
    # 该模式适用于MCP框架的进程间通信，兼容大多数MCP客户端
    mcp.run(transport='stdio')
