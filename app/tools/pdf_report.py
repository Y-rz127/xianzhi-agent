"""八字命理 PDF 报告生成

使用 reportlab 生成结构化命理报告 PDF。
注册 Windows 系统中文字体（SimHei/SimSun）以支持中文显示。
"""
from __future__ import annotations

import io
import os
import threading
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.logger import log


_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"
_FONT_LOCK = threading.Lock()

# 项目内置字体目录（可把字体文件放于此处随应用分发）
_PROJECT_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "fonts")


def _register_chinese_font():
    """注册中文字体。优先 Windows 系统字体，其次 Linux 系统字体，最后项目内置字体。"""
    global _FONT_REGISTERED, _FONT_NAME
    if _FONT_REGISTERED:
        return _FONT_NAME
    with _FONT_LOCK:
        if _FONT_REGISTERED:
            return _FONT_NAME
        candidates = [
            # Windows
            ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
            ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
            ("MSYH", r"C:\Windows\Fonts\msyh.ttc"),
            # Linux Debian/Ubuntu
            ("NotoSansCJK", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
            ("NotoSansCJKsc", "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"),
            ("NotoSansMonoCJKsc", "/usr/share/fonts/opentype/noto/NotoSansMonoCJKsc-Regular.otf"),
            ("WenQuanYiZenHei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            ("WenQuanYiMicroHei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            # Alpine
            ("NotoSansCJK", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
            # 项目内置
            ("ProjectSimHei", os.path.join(_PROJECT_FONT_DIR, "simhei.ttf")),
            ("ProjectNotoSC", os.path.join(_PROJECT_FONT_DIR, "NotoSansSC-Regular.otf")),
        ]
        for name, path in candidates:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont(name, path))
                    _FONT_NAME = name
                    log.info("PDF 中文字体已注册: {} ({})", name, path)
                    break
                except Exception as e:
                    log.warning("注册字体 {} 失败: {}", name, e)
        if _FONT_NAME == "Helvetica":
            log.warning("未找到中文字体，PDF 中文可能显示为方块。请在 Dockerfile 中安装 fonts-noto-cjk 或于 data/fonts 下放置字体文件。")
        _FONT_REGISTERED = True
        return _FONT_NAME


def _build_styles(font_name: str):
    """构建段落样式。"""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=font_name,
                                fontSize=22, textColor=colors.HexColor("#8b6f47"), spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName=font_name,
                                   fontSize=10, textColor=colors.grey, alignment=1, spaceAfter=18),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=font_name,
                             fontSize=14, textColor=colors.HexColor("#c8a97e"), spaceBefore=14, spaceAfter=8),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName=font_name,
                               fontSize=10.5, leading=18, spaceAfter=6),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName=font_name,
                                fontSize=9, textColor=colors.HexColor("#666666")),
        "footer": ParagraphStyle("footer", parent=base["Normal"], fontName=font_name,
                                 fontSize=8, textColor=colors.grey, alignment=1),
    }


def _pillar_table(pillars: dict, font_name: str):
    """四柱卡片表格。pillars = {年柱:(gz, nayin), 月柱:..., 日柱:..., 时柱:...}"""
    header = ["", "年柱", "月柱", "日柱", "时柱"]
    gz_row = ["天干地支"]
    ny_row = ["纳音"]
    for k in ["年柱", "月柱", "日柱", "时柱"]:
        gz, ny = pillars.get(k, ("-", "-"))
        gz_row.append(gz)
        ny_row.append(ny)
    data = [header, gz_row, ny_row]
    tbl = Table(data, colWidths=[2.5*cm, 3*cm, 3*cm, 3*cm, 3*cm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c8a97e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f5f0e8")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d4b88e")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("FONTSIZE", (1, 1), (-1, 1), 16),
        ("TEXTCOLOR", (1, 1), (-1, 1), colors.HexColor("#3a2a1a")),
    ]))
    return tbl

def _escape(text: str) -> str:
    """转义 reportlab 段落特殊字符并保留换行。"""
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\n", "<br/>")
    return text


def _extract_pillars(chart_text: str) -> dict:
    """从 bazi_chart 文本提取四柱干支与纳音。"""
    import re
    pillars = {}
    pattern = re.compile(r"(年柱|月柱|日柱|时柱)[:\s]*([^\s(]+)\s*\(([^)]+)\)")
    for m in pattern.finditer(chart_text):
        key, gz, ny = m.group(1), m.group(2).strip(), m.group(3).strip()
        pillars[key] = (gz, ny)
    return pillars


def generate_bazi_report(
    birth_time: str,
    gender: str,
    chart_text: str,
    analysis_text: str,
    dayun_text: str,
    ai_commentary: Optional[str] = None,
    liunian_text: Optional[str] = None,
) -> bytes:
    """生成八字命理 PDF 报告。

    Args:
        birth_time: 出生时间
        gender: 性别
        chart_text: bazi_chart 工具返回的排盘文本
        analysis_text: bazi_analysis 返回的分析文本
        dayun_text: bazi_dayun 返回的大运文本
        ai_commentary: AI 综合解读（可选）
        liunian_text: bazi_liunian 返回的流年文本（可选）

    Returns:
        PDF 文件二进制内容
    """
    font_name = _register_chinese_font()
    styles = _build_styles(font_name)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title="先知八字命理报告",
    )

    story = []
    import datetime as _dt

    # 标题
    story.append(Paragraph("先知 · 八字命理分析报告", styles["title"]))
    story.append(Paragraph("命由天定 · 运由己造", styles["subtitle"]))
    story.append(Spacer(1, 6))

    # 一、基本信息
    story.append(Paragraph("一、基本信息", styles["h2"]))
    for line in [
        "出生时间：{}".format(birth_time),
        "性别：{}".format(gender),
        "报告生成时间：{}".format(_dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]:
        story.append(Paragraph(line, styles["body"]))

    # 二、四柱排盘
    story.append(Paragraph("二、四柱排盘", styles["h2"]))
    pillars = _extract_pillars(chart_text)
    if pillars:
        story.append(_pillar_table(pillars, font_name))
        story.append(Spacer(1, 8))
    story.append(Paragraph(_escape(chart_text), styles["body"]))

    # 三、五行与十神分析
    story.append(Paragraph("三、五行与十神分析", styles["h2"]))
    story.append(Paragraph(_escape(analysis_text), styles["body"]))

    # 四、大运推算
    story.append(Paragraph("四、大运推算", styles["h2"]))
    story.append(Paragraph(_escape(dayun_text), styles["body"]))

    # 五、流年运势
    if liunian_text:
        story.append(Paragraph("五、流年运势", styles["h2"]))
        story.append(Paragraph(_escape(liunian_text), styles["body"]))

    # 六、AI 综合解读
    if ai_commentary:
        story.append(Paragraph("六、先知综合解读", styles["h2"]))
        story.append(Paragraph(_escape(ai_commentary), styles["body"]))

    # 免责声明
    story.append(Spacer(1, 20))
    story.append(Paragraph("【免责声明】", styles["h2"]))
    story.append(Paragraph(
        "本报告由 AI 智能体基于传统命理算法生成，仅供参考与文化交流，不构成任何决策依据。"
        "命理之说，信则有不信则无，望理性看待，积极面对人生。",
        styles["small"],
    ))

    # 页脚
    story.append(Spacer(1, 30))
    story.append(Paragraph("—— 先知智能体 · Powered by Xianzhi Agent ——", styles["footer"]))

    doc.build(story)
    return buf.getvalue()