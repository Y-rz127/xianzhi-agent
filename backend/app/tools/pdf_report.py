"""八字命理 PDF 报告生成（reportlab）。

注册中文字体以支持中文显示：优先项目内置字体，其次 Windows/Linux 系统字体，glob 扫描兜底。
"""
from __future__ import annotations

import datetime
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
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.logger import log

_FONT_REGISTERED = False
_FONT_NAME = "Helvetica"
_FONT_LOCK = threading.Lock()

# 项目内置字体目录（随应用分发，不依赖容器系统字体；放在代码目录避免被运行时数据忽略规则屏蔽）
_PROJECT_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def _register_chinese_font():
    """注册中文字体，返回实际生效的字体名（未找到时回退 Helvetica）。"""
    global _FONT_REGISTERED, _FONT_NAME
    if _FONT_REGISTERED:
        return _FONT_NAME
    with _FONT_LOCK:
        if _FONT_REGISTERED:
            return _FONT_NAME
        # 优先级：项目内置字体（随仓库分发，最可靠，不依赖容器系统字体轮廓类型）
        #         > Windows 本地字体 > Linux 系统字体（Debian/Alpine）> glob 兜底扫描
        candidates = [
            # 项目内置（已随仓库分发，TrueType 轮廓，reportlab 100% 支持）
            ("ProjectSimHei", os.path.join(_PROJECT_FONT_DIR, "simhei.ttf")),
            # Windows 本地开发
            ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
            ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
            ("MSYH", r"C:\Windows\Fonts\msyh.ttc"),
            # Linux Debian/Ubuntu：fonts-noto-cjk 实际安装路径（opentype 目录，.ttc）
            ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            ("NotoSerifCJK", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
            ("WenQuanYiZenHei", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
            ("WenQuanYiMicroHei", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
            # Alpine
            ("NotoSansCJK", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
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
        # glob 兜底：扫描系统字体目录里含 CJK 关键字的字体（路径随发行版变动时仍能命中）
        if _FONT_NAME == "Helvetica":
            import glob as _glob
            for pat in (
                "/usr/share/fonts/**/NotoSansCJK*.ttc",
                "/usr/share/fonts/**/NotoSerifCJK*.ttc",
                "/usr/share/fonts/**/*wqy*.ttc",
                "/usr/share/fonts/**/*SourceHanSans*",
                "/usr/share/fonts/**/*simhei*",
            ):
                for fpath in _glob.glob(pat, recursive=True):
                    try:
                        pdfmetrics.registerFont(TTFont("AutoCJK", fpath))
                        _FONT_NAME = "AutoCJK"
                        log.info("PDF 中文字体已通过 glob 注册: {}", fpath)
                        break
                    except Exception as e:
                        log.warning("注册字体 {} 失败: {}", fpath, e)
                if _FONT_NAME != "Helvetica":
                    break
        if _FONT_NAME == "Helvetica":
            log.warning("未找到中文字体，PDF 中文会显示为黑块。已将 simhei.ttf 内置到 data/fonts/，若仍失败请确认该文件已被打包进镜像。")
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


def _data_table(headers: list, rows: list, font_name: str, widths: list) -> Table:
    """细盘数据表格：金色表头、单元格用小号 Paragraph 承载长文本（神煞列表可换行）。

    repeatRows=1 使表头在跨页时重复，13 步大运 / 12 个月的长表不丢表头。
    """
    hdr_style = ParagraphStyle("tblhdr", fontName=font_name, fontSize=9,
                               leading=12, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle("tblcell", fontName=font_name, fontSize=8.5,
                                leading=11.5, textColor=colors.HexColor("#3a2a1a"))
    center_style = ParagraphStyle("tblctr", parent=cell_style, alignment=1)
    data = [[Paragraph(_escape(h), hdr_style) for h in headers]]
    for row in rows:
        data.append([
            Paragraph(_escape(str(cell)), center_style if i == 0 else cell_style)
            for i, cell in enumerate(row)
        ])
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c8a97e")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#faf7f1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4b88e")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return tbl


# ---- 报告章节构造（单一职责；story 为可写列表，counter 为章节号计数器）----

_CN_NUM = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def _chapter_title(title: str, counter: list) -> str:
    """章节自动编号：有细盘数据时章节更多，避免手写序号错位。"""
    counter[0] += 1
    return f"{_CN_NUM[counter[0] - 1]}、{title}"


def _basic_info_section(story, styles, counter, birth_time, gender):
    story.append(Paragraph(_chapter_title("基本信息", counter), styles["h2"]))
    for line in [
        "出生时间：{}".format(birth_time),
        "性别：{}".format(gender),
        "报告生成时间：{}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]:
        story.append(Paragraph(line, styles["body"]))


def _pillar_section(story, styles, font_name, counter, chart_text):
    story.append(Paragraph(_chapter_title("四柱排盘", counter), styles["h2"]))
    pillars = _extract_pillars(chart_text)
    if pillars:
        story.append(_pillar_table(pillars, font_name))
        story.append(Spacer(1, 8))
    story.append(Paragraph(_escape(chart_text), styles["body"]))


def _analysis_section(story, styles, counter, analysis_text):
    story.append(Paragraph(_chapter_title("五行与十神分析", counter), styles["h2"]))
    story.append(Paragraph(_escape(analysis_text), styles["body"]))


def _dayun_section(story, styles, font_name, counter, dayun_text, dayun_rows):
    story.append(Paragraph(_chapter_title("大运推算", counter), styles["h2"]))
    if dayun_rows:
        story.append(_data_table(
            ["大运", "十神", "年份", "年龄", "藏干", "副星(地支十神)", "星运", "神煞"],
            [[r["ganzhi"], r["shishen"], r["years"], r["ages"], r["hidden"], r["fuxing"],
              r["changsheng"], r["shensha"]] for r in dayun_rows],
            font_name,
            widths=[1.7*cm, 1.5*cm, 2.2*cm, 1.9*cm, 2.0*cm, 2.6*cm, 1.3*cm, 3.8*cm],
        ))
    else:
        story.append(Paragraph(_escape(dayun_text), styles["body"]))


def _liunian_section(story, styles, font_name, counter, liunian_text, liunian_rows):
    story.append(Paragraph(_chapter_title("流年运势", counter), styles["h2"]))
    if liunian_rows:
        story.append(_data_table(
            ["年份", "干支", "十神", "虚岁", "星运", "神煞"],
            [[r["year"], r["ganzhi"], r["shishen"], r["age"], r["changsheng"], r["shensha"]]
             for r in liunian_rows],
            font_name,
            widths=[1.6*cm, 1.8*cm, 1.8*cm, 1.4*cm, 1.6*cm, 8.8*cm],
        ))
    elif liunian_text:
        story.append(Paragraph(_escape(liunian_text), styles["body"]))


def _relations_section(story, styles, counter, relations):
    if not relations:
        return
    story.append(Paragraph(_chapter_title("岁运与原局关系", counter), styles["h2"]))
    for block_title, block in (
        ("岁运分析（{}）", relations.get("suiyun") or {}),
        ("原局分析（{}）", relations.get("yuanju") or {}),
    ):
        label = block.get("label") or ""
        story.append(Paragraph(f"<b>{block_title.format(label)}</b>", styles["body"]))
        for row_label, key in (("天干", "gan"), ("地支", "zhi"), ("整柱", "zhu")):
            items = block.get(key) or []
            story.append(Paragraph(
                f"{row_label}：{'｜'.join(items) if items else '—'}",
                styles["body"],
            ))


def _liuyue_section(story, styles, font_name, counter, liuyue_rows):
    if not liuyue_rows:
        return
    story.append(Paragraph(_chapter_title("流月排盘（当年）", counter), styles["h2"]))
    story.append(_data_table(
        ["节气", "交节", "干支", "十神", "星运", "神煞"],
        [[r["jieqi"], r["date"], r["ganzhi"], r["shishen"], r["changsheng"], r["shensha"]]
         for r in liuyue_rows],
        font_name,
        widths=[2.0*cm, 1.8*cm, 1.8*cm, 1.8*cm, 1.6*cm, 8.0*cm],
    ))


def _shensha_section(story, styles, font_name, counter, shensha_by_pillar):
    if not shensha_by_pillar:
        return
    story.append(Paragraph(_chapter_title("神煞按柱", counter), styles["h2"]))
    story.append(_data_table(
        ["柱位", "神煞"],
        [[name, "、".join(names) or "—"] for name, names in shensha_by_pillar],
        font_name,
        widths=[2.2*cm, 14.8*cm],
    ))


def _ai_commentary_section(story, styles, counter, ai_commentary):
    if ai_commentary:
        story.append(Paragraph(_chapter_title("先知综合解读", counter), styles["h2"]))
        story.append(Paragraph(_escape(ai_commentary), styles["body"]))


def _footer_section(story, styles):
    story.append(Spacer(1, 20))
    story.append(Paragraph("【免责声明】", styles["h2"]))
    story.append(Paragraph(
        "本报告由 AI 智能体基于传统命理算法生成，仅供参考与文化交流，不构成任何决策依据。"
        "命理之说，信则有不信则无，望理性看待，积极面对人生。",
        styles["small"],
    ))
    story.append(Spacer(1, 30))
    story.append(Paragraph("—— 先知智能体 · Powered by Xianzhi Agent ——", styles["footer"]))


def generate_bazi_report(
    birth_time: str,
    gender: str,
    chart_text: str,
    analysis_text: str,
    dayun_text: str,
    ai_commentary: Optional[str] = None,
    liunian_text: Optional[str] = None,
    dayun_rows: Optional[list] = None,
    liunian_rows: Optional[list] = None,
    liuyue_rows: Optional[list] = None,
    relations: Optional[dict] = None,
    shensha_by_pillar: Optional[list] = None,
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
        dayun_rows: 细盘大运行（12 步，含神煞/星运/纳音），传入则替代 dayun_text 表格化
        liunian_rows: 细盘流年行（含神煞/星运），传入则替代 liunian_text
        liuyue_rows: 细盘流月行（当年 12 节气月，含神煞）
        relations: 岁运/原局干支关系（xipan.relations，六栏）
        shensha_by_pillar: 按柱神煞 [(柱名, [神煞名...])...]

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

    counter = [0]
    story = []
    story.append(Paragraph("先知 · 八字命理分析报告", styles["title"]))
    story.append(Paragraph("命由天定 · 运由己造", styles["subtitle"]))
    story.append(Spacer(1, 6))

    _basic_info_section(story, styles, counter, birth_time, gender)
    _pillar_section(story, styles, font_name, counter, chart_text)
    _analysis_section(story, styles, counter, analysis_text)
    _dayun_section(story, styles, font_name, counter, dayun_text, dayun_rows)
    _liunian_section(story, styles, font_name, counter, liunian_text, liunian_rows)
    _relations_section(story, styles, counter, relations)
    _liuyue_section(story, styles, font_name, counter, liuyue_rows)
    _shensha_section(story, styles, font_name, counter, shensha_by_pillar)
    _ai_commentary_section(story, styles, counter, ai_commentary)
    _footer_section(story, styles)

    doc.build(story)
    return buf.getvalue()
