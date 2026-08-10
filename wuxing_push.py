#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日五行穿衣指南 - 自动推送到微信(PushPlus)
纯标准库实现，零依赖

适用于 GitHub Actions 云端运行，无需电脑开机。
Token 从环境变量 PUSHPLUS_TOKEN 读取（GitHub Secrets）。
"""

import urllib.request
import urllib.error
import re
import json
import sys
import os
from datetime import date, datetime, timezone, timedelta

# ==================== 配置 ====================
# 优先从环境变量读取（GitHub Secrets），本地测试可回退到硬编码
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "5afc18b7501e416eabeac3404462ac84")

# 北京时区（UTC+8），确保云端运行时日期正确
BEIJING_TZ = timezone(timedelta(hours=8))

# ==================== 天干地支算法 ====================
STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 参考日期: 2026-08-08 = 甲寅日（经多源验证）
REF_DATE = date(2026, 8, 8)
REF_STEM_IDX = 0   # 甲
REF_BRANCH_IDX = 2  # 寅

# 地支 → 五行
BRANCH_WUXING = {
    "申": "金", "酉": "金",
    "寅": "木", "卯": "木",
    "子": "水", "亥": "水",
    "午": "火", "巳": "火",
    "辰": "土", "未": "土", "戌": "土", "丑": "土",
}

# 五行 → 代表颜色
WUXING_COLORS = {
    "金": ["白色", "银色", "金色", "杏色", "米白", "灰色", "乳白"],
    "木": ["绿色", "青色", "翠绿", "青绿", "浅绿"],
    "水": ["黑色", "蓝色", "深蓝"],
    "火": ["红色", "紫色", "粉色", "橙色", "橙红"],
    "土": ["黄色", "棕色", "咖色", "褐色", "橙黄", "咖啡"],
}

# 五行相生: A生B
GENERATES = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
# 五行相克: A克B
CONTROLS = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}


def get_ganzhi(target_date):
    """计算给定日期的天干地支（基于60甲子循环）"""
    delta = (target_date - REF_DATE).days
    stem_idx = (REF_STEM_IDX + delta) % 10
    branch_idx = (REF_BRANCH_IDX + delta) % 12
    stem = STEMS[stem_idx]
    branch = BRANCHES[branch_idx]
    return stem + branch, branch


def get_wuxing_colors(branch):
    """根据地支计算五行穿衣颜色"""
    day_element = BRANCH_WUXING[branch]

    daji = GENERATES[day_element]
    ciji = day_element
    shenyong = [k for k, v in GENERATES.items() if v == day_element][0]
    pingping = [k for k, v in CONTROLS.items() if v == day_element][0]
    jiyong = CONTROLS[day_element]

    return {
        "day_element": day_element,
        "daji": WUXING_COLORS[daji],
        "ciji": WUXING_COLORS[ciji],
        "pingping": WUXING_COLORS[pingping],
        "shenyong": WUXING_COLORS[shenyong],
        "jiyong": WUXING_COLORS[jiyong],
    }


# ==================== 网页抓取（可选增强） ====================
def strip_html(html_text):
    html_text = re.sub(r'<script[^>]*>.*?</script>', '', html_text, flags=re.S)
    html_text = re.sub(r'<style[^>]*>.*?</style>', '', html_text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', html_text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def fetch_extra_info(target_date):
    """从网页抓取农历、方位、宜忌等额外信息（失败不影响核心功能）"""
    date_ymd = f"{target_date.year}-{target_date.month}-{target_date.day}"
    date_ymd_compact = target_date.strftime("%Y%m%d")

    urls = [
        f"https://www.baibaidu.com/toolbox/wuxingchuanyis/{date_ymd_compact}.html",
        f"https://www.d5168.com/wuhang/{date_ymd}",
        f"https://services.shen88.cn/lhl/chuanyi/{date_ymd}.html",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            resp = urllib.request.urlopen(req, timeout=15)
            raw = resp.read()
            for enc in ['utf-8', 'gbk', 'gb2312']:
                try:
                    html = raw.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                html = raw.decode('utf-8', errors='ignore')

            text = strip_html(html)
            result = {}

            m = re.search(r'农历([二〇〇一二三四五六七八九十百千正月腊冬冬]+年[^\s,，.。]+)', text)
            if m:
                result['lunar'] = m.group(1)[:20]

            m = re.search(r'喜神[方位]*([东南西北中]+)', text)
            if m:
                result['xi_shen'] = m.group(1)
            m = re.search(r'福神[方位]*([东南西北中]+)', text)
            if m:
                result['fu_shen'] = m.group(1)
            m = re.search(r'财神[方位]*([东南西北中]+)', text)
            if m:
                result['cai_shen'] = m.group(1)

            m = re.search(r'宜([^\s]{2,60})', text)
            if m:
                yi = m.group(1).strip().rstrip('忌禁')
                if len(yi) > 1:
                    result['yi'] = yi[:50]
            m = re.search(r'忌([^\s]{2,40})', text)
            if m:
                ji = m.group(1).strip().rstrip('宜禁')
                if len(ji) > 1:
                    result['ji'] = ji[:50]

            if result:
                return result
        except Exception:
            continue

    return {}


# ==================== 格式化推送内容 ====================
def format_push_content(today, ganzhi, branch, colors, extra):
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_names[today.weekday()]
    date_str = f"{today.year}年{today.month}月{today.day}日 {weekday}"

    lunar = extra.get('lunar', '')
    element = colors['day_element']

    parts = []
    parts.append(
        f"<div style='font-family:sans-serif;max-width:600px;margin:0 auto;padding:15px;'>"
        f"<h2 style='color:#333;border-bottom:2px solid #e74c3c;padding-bottom:10px;'>"
        f"👕 今日五行穿衣指南</h2>"
    )

    if lunar:
        parts.append(f"<p style='color:#666;font-size:14px;'>{date_str} | 农历{lunar}</p>")
    else:
        parts.append(f"<p style='color:#666;font-size:14px;'>{date_str}</p>")
    parts.append(f"<p style='color:#999;font-size:13px;'>{ganzhi}日 | 今日五行属{element}</p>")

    sections = [
        ("✅ 大吉色（贵人色）", colors['daji'], "#e74c3c", "易招贵人，易获扶助，异性缘佳"),
        ("🤝 次吉色（合作色）", colors['ciji'], "#e67e22", "幸运眷顾，合作顺利，事半功倍"),
        ("💰 平平色（招财色）", colors['pingping'], "#27ae60", "努力有回报，利于求财"),
        ("⚠️ 慎用色（消耗色）", colors['shenyong'], "#8e44ad", "精力消耗大，需防疲惫"),
        ("🚫 忌用色（不利色）", colors['jiyong'], "#7f8c8d", "事倍功半，进展缓慢"),
    ]

    for title, color_list, color, desc in sections:
        parts.append(f"<h3 style='color:{color};'>{title}</h3>")
        parts.append(
            f"<p style='font-size:16px;color:{color};font-weight:bold;'>"
            f"{'、'.join(color_list)}</p>"
        )
        parts.append(f"<p style='font-size:13px;color:#888;'>{desc}</p>")

    parts.append("<hr style='border:none;border-top:1px solid #eee;margin:15px 0;'>")

    fangwei = []
    if 'cai_shen' in extra:
        fangwei.append(f"💰 财神：{extra['cai_shen']}")
    if 'xi_shen' in extra:
        fangwei.append(f"😊 喜神：{extra['xi_shen']}")
    if 'fu_shen' in extra:
        fangwei.append(f"🍀 福神：{extra['fu_shen']}")
    if fangwei:
        parts.append(f"<p style='font-size:13px;color:#999;'>{' | '.join(fangwei)}</p>")

    if 'yi' in extra:
        parts.append(f"<p style='font-size:13px;color:#27ae60;'>📌 宜：{extra['yi']}</p>")
    if 'ji' in extra:
        parts.append(f"<p style='font-size:13px;color:#e74c3c;'>📌 忌：{extra['ji']}</p>")

    parts.append("</div>")
    return ''.join(parts)


# ==================== PushPlus 推送 ====================
def push_to_wechat(title, content):
    """通过PushPlus API推送到微信"""
    data = json.dumps({
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html"
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://www.pushplus.plus/send",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read().decode('utf-8'))
    return result


# ==================== 日志 ====================
def log(msg):
    print(f"[{datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


# ==================== 主程序 ====================
def main():
    log("=== 五行穿衣推送开始 ===")
    # 使用北京时区获取日期，确保云端运行日期正确
    today = datetime.now(BEIJING_TZ).date()
    log(f"今天(北京时间): {today}")

    ganzhi, branch = get_ganzhi(today)
    colors = get_wuxing_colors(branch)
    log(f"干支: {ganzhi} | 地支: {branch} | 五行: {colors['day_element']}")
    log(f"大吉色: {colors['daji']}")

    log("抓取网页额外信息...")
    extra = fetch_extra_info(today)
    if extra:
        log(f"抓取成功: {list(extra.keys())}")
    else:
        log("抓取失败或无数据，使用纯本地计算结果")

    title = f"今日五行穿衣指南 | {today.year}年{today.month}月{today.day}日"
    content = format_push_content(today, ganzhi, branch, colors, extra)

    log("推送到PushPlus...")
    result = push_to_wechat(title, content)

    if result.get('code') == 200:
        log(f"推送成功! data={result.get('data','')}")
        log("=== 五行穿衣推送完成 ===")
    else:
        log(f"推送失败: {result}")
        import time
        time.sleep(5)
        result2 = push_to_wechat(title, content)
        if result2.get('code') == 200:
            log(f"重试成功!")
        else:
            log(f"重试失败: {result2}")
            sys.exit(1)


if __name__ == '__main__':
    main()
