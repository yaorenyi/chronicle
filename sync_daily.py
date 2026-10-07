#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI HOT 日报 → Hexo 博客文章

用法:
    python sync_daily.py                      # 拉今天日报,生成文章
    python sync_daily.py --date 2026-10-07    # 指定日期
    python sync_daily.py --backfill 5         # 回补最近 5 期(按已有文章去重)

产出: source/_posts/ai-daily-YYYY-MM-DD.md
不依赖第三方库,可直接在 GitHub Actions 里跑。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

API_BASE = "https://aihot.virxact.com/api/v1"
CANONICAL = "https://aihot.news/daily"
UA = "aihot-skill/1.2.1 (+https://aihot.virxact.com/aihot-skill/)"

ROOT = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(ROOT, "source", "_posts")

WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

SECTIONS = [
    ("sec-model", "模型发布 / 更新", "🧠"),
    ("sec-product", "产品发布 / 更新", "🧩"),
    ("sec-industry", "行业动态", "📈"),
    ("sec-paper", "论文研究", "📚"),
    ("sec-tips", "技巧与观点", "💡"),
]

SECTION_KEYWORDS = {
    "sec-model": [
        ("模型", 2), ("权重", 2), ("开源模型", 2), ("参数", 2), ("架构", 2),
        ("微调", 2), ("蒸馏", 2), ("量化", 2), ("moe", 2), ("多模态", 2),
        ("预训练", 2), ("激活参数", 2), ("评测", 1), ("基准", 1), ("推理", 1),
        ("benchmark", 1), ("嵌入", 2), ("embedding", 2), ("开源", 2),
        ("gpt", 2), ("claude", 2), ("gemini", 2), ("deepseek", 2), ("llama", 2),
        ("qwen", 2), ("mistral", 2), ("grok", 2), ("kimi", 2), ("llm", 2),
        ("arc-agi", 2), ("openrouter", 1), ("huggingface", 2),
    ],
    "sec-product": [
        ("插件", 2), ("app", 2), ("应用", 2), ("客户端", 2), ("工作流", 2),
        ("集成", 2), ("扩展", 2), ("sdk", 2), ("api", 2), ("命令行", 2),
        ("cli", 2), ("浏览器", 2), ("ide", 2), ("编码", 2), ("coding", 2),
        ("ios", 2), ("android", 2), ("桌面端", 2), ("workspace", 2),
        ("助手", 2), ("服务", 1), ("平台", 1), ("工具", 1), ("上线", 2),
        ("公测", 2), ("内测", 2), ("开放", 1), ("发布", 1), ("更新", 1),
        ("版本", 1), ("支持", 1), ("功能", 1), ("git", 2), ("开发", 1),
        ("会议", 1), ("文档", 1), ("表格", 1), ("搜索", 1), ("订阅", 1),
        ("虚拟机", 2), ("vm", 1), ("部署", 2), ("容器", 2),
        ("cowork", 2), ("远程控制", 2), ("云端", 1), ("会话", 1), ("协议", 1),
    ],
    "sec-industry": [
        ("融资", 2), ("投资", 2), ("估值", 2), ("上市", 2), ("ipo", 2),
        ("收购", 2), ("并购", 2), ("裁员", 2), ("财报", 2), ("营收", 2),
        ("利润", 2), ("支出", 2), ("基金", 2), ("股东", 2), ("法院", 2),
        ("诉讼", 2), ("裁定", 2), ("监管", 2), ("政策", 2), ("法案", 2),
        ("禁令", 2), ("合规", 2), ("版权", 2), ("市场", 1), ("公司", 1),
        ("合作", 1), ("签约", 1), ("用户", 1), ("增长", 1), ("份额", 1),
        ("算力", 2), ("芯片", 2), ("数据中心", 2), ("供应链", 2),
        ("安全", 1), ("泄露", 2), ("事故", 2), ("组织", 1), ("条款", 1),
        ("亿元", 2), ("亿美元", 2), ("gdp", 2),
    ],
    "sec-paper": [
        ("论文", 2), ("paper", 2), ("arxiv", 2), ("预印本", 2), ("期刊", 2),
        ("证明", 2), ("定理", 2), ("推导", 2), ("形式化", 2), ("数据集", 2),
        ("研究", 1), ("实验", 1), ("评估", 1), ("评测", 1), ("基准", 1),
        ("综述", 2), ("方法", 1), ("框架", 1), ("对齐", 1), ("可解释", 1),
        ("鲁棒", 1), ("数学", 2), ("引用协议", 2), ("学者", 2), ("团队提出", 2),
    ],
    "sec-tips": [
        ("技巧", 2), ("指南", 2), ("教程", 2), ("实践", 2), ("心得", 2),
        ("解读", 2), ("观点", 2), ("复盘", 2), ("推荐", 1), ("用法", 2),
        ("提示词", 2), ("prompt", 2), ("避坑", 2), ("上手", 2), ("玩法", 2),
        ("盘点", 2), ("观察", 1), ("建议", 1), ("最佳实践", 2), ("案例", 1),
        ("实战", 2), ("总结", 1), ("如何", 1),
    ],
}

SUMMARY_MAX = 110


# ---------------------------------------------------------------- HTTP

def fetch(path, timeout=20):
    req = urllib.request.Request(
        API_BASE + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_daily(date_str):
    """拉指定日期日报;不存在则回退到最近一期。返回 (report, 是否回退)。"""
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    target = date_str or today
    try:
        return fetch("/dailies/%s" % target)["report"], False
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        print("[!] %s 日报尚未生成,回退到最近一期" % target)
    except Exception as e:
        print("[!] 请求 %s 失败(%s),回退" % (target, e))

    idx = fetch("/dailies?limit=7")
    entries = idx.get("dailies") or idx.get("items") or idx.get("entries") or []
    dates = sorted({(d.get("date") or (d.get("report") or {}).get("date") or "")
                    for d in entries if (d.get("date") or (d.get("report") or {}).get("date"))})
    if not dates:
        raise SystemExit("[x] 日报索引为空")
    latest = dates[-1]
    print("[i] 使用最近一期:%s" % latest)
    return fetch("/dailies/%s" % latest)["report"], True


# ---------------------------------------------------------------- 工具

def to_beijing(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=8)))


def human_time(iso):
    dt = to_beijing(iso)
    if not dt:
        return ""
    return "%d 月 %d 日 %02d:%02d" % (dt.month, dt.day, dt.hour, dt.minute)


def clip(text, limit=SUMMARY_MAX):
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return ""
    if len(t) <= limit:
        return t
    cut = t[:limit]
    # 首选句号/分号,断句更自然
    for sep in ("。", "；"):
        p = cut.rfind(sep)
        if p >= limit * 0.5:
            return cut[:p + 1]
    # 次选逗号/顿号,留足内容再断
    for sep in ("，", "、", " "):
        p = cut.rfind(sep)
        if p >= limit * 0.8:
            return cut[:p] if sep == " " else cut[:p]
    return cut.rstrip("，、；") + "…"


def md_escape(s):
    """转义 Markdown 表格与行内语法可能踩到的字符"""
    s = (s or "").replace("|", "\\|")
    return re.sub(r"\s+", " ", s).strip()


def norm_title(t):
    return re.sub(r"[\s\W_]+", "", (t or "").lower())


def is_duplicate(title, seen):
    n = norm_title(title)
    if not n:
        return False
    for prev in seen:
        if not prev:
            continue
        if n == prev:
            return True
        m = min(len(n), len(prev))
        cp = 0
        while cp < m and n[cp] == prev[cp]:
            cp += 1
        if cp >= 12 and m >= 20 and abs(len(n) - len(prev)) >= 4:
            return True
    return False


def guess_section(text):
    title = (text or "").lower()
    best_sid, best_score = "sec-industry", 0
    for sid, kws in SECTION_KEYWORDS.items():
        score = sum(w for kw, w in kws if kw in title)
        if score > best_score:
            best_sid, best_score = sid, score
    return best_sid


def front_matter_quote(s):
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------- 组装

def collect(report):
    """把日报摊平成 {section_id: [item]}"""
    buckets = {sid: [] for sid, _, _ in SECTIONS}
    seen = []
    dropped = 0

    for sec in report.get("sections", []):
        sid = None
        for cand, label, _ in SECTIONS:
            if label.replace(" ", "") == sec.get("label", "").replace(" ", ""):
                sid = cand
                break
        if sid is None:
            sid = guess_section(sec.get("label", ""))
        for it in sec.get("items", []):
            t = it.get("title", "")
            if is_duplicate(t, seen):
                dropped += 1
                continue
            seen.append(norm_title(t))
            buckets[sid].append({
                "title": t,
                "summary": clip(it.get("summary", "")),
                "source": (it.get("source") or {}).get("name", "AI HOT"),
                "url": (it.get("links") or {}).get("aihot") or (it.get("links") or {}).get("original") or "",
                "time": "",
            })

    for f in report.get("flashes", []):
        t = f.get("title", "")
        if is_duplicate(t, seen):
            dropped += 1
            continue
        seen.append(norm_title(t))
        sid = guess_section(t)
        buckets[sid].append({
            "title": t,
            "summary": "",
            "source": (f.get("source") or {}).get("name", "AI HOT"),
            "url": (f.get("links") or {}).get("aihot") or (f.get("links") or {}).get("original") or "",
            "time": human_time(f.get("publishedAt")),
        })

    if dropped:
        print("[i] 已合并重复报道 %d 条" % dropped)
    return buckets


def render_post(report, buckets, fell_back):
    date_str = report["date"]
    dt = to_beijing(report.get("generatedAt")) or datetime.now(timezone(timedelta(hours=8)))
    total = sum(len(v) for v in buckets.values())
    sources = set()
    for v in buckets.values():
        for it in v:
            sources.add(it["source"])

    y, m, d = (int(x) for x in date_str.split("-"))
    title = "AI 日报 %s · %d 条" % (date_str, total)

    L = []
    L.append("---")
    L.append("title: %s" % front_matter_quote(title))
    L.append("date: %s" % dt.strftime("%Y-%m-%d %H:%M:%S"))
    L.append("tags: [AI 日报, AI, 资讯]")
    L.append("categories: [AI 日报]")
    L.append("toc: true")
    L.append("comments: false")
    L.append("description: %s" % front_matter_quote(
        clip("%s 今日 %d 条 AI 资讯，覆盖五个版块。" % (date_str, total), 100)))
    L.append("---")
    L.append("")

    # 概要卡片
    lead = report.get("lead") or {}
    L.append("> **共 %d 条 · %d 个信源 · %d 个版块** · %s" % (
        total, len(sources), len(SECTIONS), _window_text(report)))
    L.append(">")
    if lead.get("title"):
        L.append("> **今日头条**：%s" % md_escape(lead.get("title")))
        if lead.get("leadParagraph") or lead.get("summary"):
            L.append(">")
            L.append("> %s" % md_escape(clip(lead.get("leadParagraph") or lead.get("summary"), 150)))
    L.append("")

    if fell_back:
        L.append(":::warning 当日日报尚未生成")
        L.append("本文展示的是最近一期已生成的日报。")
        L.append(":::")
        L.append("")

    n = 0
    for sid, label, emoji in SECTIONS:
        items = buckets.get(sid) or []
        if not items:
            continue
        L.append("## %s %s（%d）" % (emoji, label, len(items)))
        L.append("")
        for it in items:
            n += 1
            L.append("### %02d · %s" % (n, md_escape(it["title"])))
            L.append("")
            meta = [it["source"]]
            if it["time"]:
                meta.append(it["time"])
            L.append("`%s`" % " · ".join(meta))
            L.append("")
            if it["summary"]:
                L.append(md_escape(it["summary"]))
                L.append("")
            if it["url"]:
                L.append("[阅读原文 →](%s)" % it["url"])
                L.append("")

    L.append("---")
    L.append("")
    L.append("*本文由 [AI HOT 日报](%s/%s) 自动生成于 %s。第三方原文版权归原作者所有。*" % (
        CANONICAL, date_str, dt.strftime("%Y-%m-%d %H:%M")))
    L.append("")

    return "\n".join(L), total


def _md(dt):
    if not dt:
        return "—"
    return "%d 月 %d 日 %02d:00" % (dt.month, dt.day, dt.hour)


def _window_text(report):
    """收录区间人话格式;跨天时体现跨日,同日时省略重复的结束时间"""
    ws = to_beijing(report.get("windowStart"))
    we = to_beijing(report.get("windowEnd"))
    if not ws and not we:
        return ""
    if not ws:
        return "收录至 %s（北京时间）" % _md(we)
    if not we:
        return "收录自 %s（北京时间）" % _md(ws)
    if (ws.month, ws.day) == (we.month, we.day):
        return "收录于 %d 月 %d 日 %02d:00（北京时间）" % (we.month, we.day, we.hour)
    return "收录区间 %d 月 %d 日 %02d:00 — %d 月 %d 日 %02d:00（北京时间）" % (
        ws.month, ws.day, ws.hour, we.month, we.day, we.hour)


def post_path(date_str):
    return os.path.join(POSTS_DIR, "ai-daily-%s.md" % date_str)


def write_post(date_str, content):
    os.makedirs(POSTS_DIR, exist_ok=True)
    p = post_path(date_str)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return p


def existing_dates():
    if not os.path.isdir(POSTS_DIR):
        return set()
    return {m.group(1) for m in
            (re.match(r"^ai-daily-(\d{4}-\d{2}-\d{2})\.md$", n) for n in os.listdir(POSTS_DIR))
            if m}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="AI HOT 日报 → Hexo 文章")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD")
    ap.add_argument("--backfill", type=int, default=0,
                    help="回补最近 N 期(已存在文章会跳过)")
    ap.add_argument("--force", action="store_true", help="即使文章已存在也重写")
    args = ap.parse_args()

    have = existing_dates()
    written = []

    if args.backfill:
        idx = fetch("/dailies?limit=%d" % min(args.backfill + 3, 10))
        entries = idx.get("dailies") or idx.get("items") or []
        dates = sorted({(d.get("date") or (d.get("report") or {}).get("date") or "")
                        for d in entries if (d.get("date") or (d.get("report") or {}).get("date"))},
                       reverse=True)
        targets = []
        for d in dates:
            if d in have:
                continue
            targets.append(d)
            if len(targets) >= args.backfill:
                break
        if not targets:
            print("[i] 没有需要回补的期次,已存在: %s" % ", ".join(sorted(have)) or "无")
            return
        print("[i] 准备回补: %s" % ", ".join(targets))
        for d in targets:
            try:
                rep, fb = fetch_daily(d)
            except Exception as e:
                print("[!] 跳过 %s (%s)" % (d, e))
                continue
            if rep.get("date") in have and not args.force:
                continue
            buckets = collect(rep)
            if not any(buckets.values()):
                print("[i] %s 源数据为空,跳过" % rep.get("date"))
                continue
            content, n = render_post(rep, buckets, fb)
            write_post(rep["date"], content)
            print("[✓] %s  %d 条" % (post_path(rep["date"]), n))
            written.append(rep["date"])
    else:
        rep, fb = fetch_daily(args.date)
        d = rep["date"]
        if d in have and not args.force:
            print("[i] %s 文章已存在,跳过(加 --force 可重写)" % d)
            return
        buckets = collect(rep)
        if not any(buckets.values()):
            print("[!] %s 源数据为空,不生成文章" % d)
            return
        content, n = render_post(rep, buckets, fb)
        write_post(d, content)
        print("[✓] %s  %d 条" % (post_path(d), n))
        written.append(d)

    print("[done] 共写入 %d 篇" % len(written))


if __name__ == "__main__":
    main()
