"""ดึงข้อมูลจาก API แล้วเขียน data.json (รันโดย GitHub Actions)
แต่ละแหล่งแยกกัน ถ้าแหล่งใดล้มเหลวจะเก็บข้อมูลเดิมไว้และบันทึกสถานะ
เพิ่ม: ประวัติการเปลี่ยน, เทรนปี, คำแนะนำน่าใช้/น่าจับตา
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data.json"
HISTORY_DIR = ROOT / "history"
WATCHLIST_PATH = ROOT / "watchlist.yml"
STOP = ("max", "xhigh", "high", "medium", "low", "thinking", "preview", "reasoning", "fallback", "adaptive")
UA = {"User-Agent": "tech-radar/2.0 (+https://github.com/tech-radar)"}
TODAY = dt.date.today().isoformat()
YEAR = dt.date.today().year

AA_ROWS: list[dict] = []
ARENA: dict[str, float] = {}
OR_NEW: list = []
OR_MODELS: list[dict] = []
ARENA_DIMS: dict[str, dict] = {}

# มิติจาก LMArena (config บน HuggingFace dataset)
DIM_SPECS = [
    {
        "id": "text",
        "config": "text",
        "label": "สนทนา / เขียนทั่วไป",
        "short": "Text",
        "use": "chat, อธิบาย, ร่างข้อความ",
        "tip": "คะแนนจากโหวตผู้ใช้จริงในงานคุย/เขียนทั่วไป — เหมาะเป็น default สำหรับงานภาษา",
    },
    {
        "id": "webdev",
        "config": "webdev",
        "label": "WebDev / Coding UI",
        "short": "WebDev",
        "use": "เขียนเว็บ, UI, frontend",
        "tip": "เน้นงานสร้างเว็บและโค้ดหน้าบ้าน — สำคัญถ้าคุณใช้ AI ช่วยเขียนแอป",
    },
    {
        "id": "agent",
        "config": "agent",
        "label": "Agent / Tool use",
        "short": "Agent",
        "use": "agent, tool-calling, automation",
        "tip": "วัดผลงาน agent จริง (ไม่ใช่แค่ chat) — ดูถ้าทำระบบ agent / IDE agent",
        "score_kind": "ratio",
    },
    {
        "id": "vision",
        "config": "vision",
        "label": "Vision / รูปภาพ",
        "short": "Vision",
        "use": "อ่านรูป, screenshot, UI review",
        "tip": "โมเดลที่เก่งมองรูป — เหมาะงานวิเคราะห์ภาพ/เอกสารสแกน",
    },
    {
        "id": "search",
        "config": "search",
        "label": "Search / หาข้อมูล",
        "short": "Search",
        "use": "search-augmented, research",
        "tip": "งานค้นและตอบจากเว็บ — ใกล้เคียง workflow วิจัย/ข่าว",
    },
    {
        "id": "factual",
        "config": "text_factuality",
        "label": "ข้อเท็จจริง (Factuality)",
        "short": "Factual",
        "use": "คำตอบที่ต้องถูกต้อง",
        "tip": "เน้นความถูกต้องของข้อเท็จจริงมากกว่าความลื่นของภาษา",
    },
    {
        "id": "document",
        "config": "document",
        "label": "เอกสารยาว",
        "short": "Docs",
        "use": "สรุปเอกสาร, contract, PDF",
        "tip": "งานเอกสารยาว — ดูถ้าใช้ AI กับรายงาน/สัญญา/คู่มือ",
    },
    {
        "id": "image",
        "config": "text_to_image",
        "label": "สร้างรูป (Text→Image)",
        "short": "Image",
        "use": "generate รูปจากข้อความ",
        "tip": "บอร์ดสร้างภาพ — คนละกลุ่มกับ LLM แชท",
    },
]


def norm(n: str) -> str:
    s = re.sub(r"\(.*?\)", "", n.lower())
    return "".join(w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w not in STOP)


def load_watchlist() -> dict:
    if WATCHLIST_PATH.exists():
        with open(WATCHLIST_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get(url: str, headers: dict | None = None, retries: int = 2, **kw):
    last = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers={**UA, **(headers or {})}, timeout=30, **kw)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            if i < retries:
                time.sleep(1.2 * (i + 1))
    raise last  # type: ignore[misc]


def table(id, tab, title, date, why, items, note, src):
    return dict(id=id, tab=tab, title=title, date=date, why=why, items=items, note=note, src=src)


def aa():
    global AA_ROWS
    key = os.environ.get("AA_API_KEY")
    if not key:
        raise RuntimeError("ไม่มี secret AA_API_KEY")
    hd = {"x-api-key": key}
    try:
        d = get("https://artificialanalysis.ai/api/v2/data/llms/models", hd)
    except Exception:
        d = get("https://artificialanalysis.ai/api/v2/language/models/free", hd)
    rows = []
    for m in d["data"]:
        s = (m.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
        if s is not None:
            rows.append((m.get("name") or m.get("slug"), float(s), (m.get("model_creator") or {}).get("name", ""), m))
    rows.sort(key=lambda x: -x[1])
    AA_ROWS = [
        dict(
            name=n,
            org=o,
            aa=s,
            coding=(m.get("evaluations") or {}).get("artificial_analysis_coding_index"),
            agentic=(m.get("evaluations") or {}).get("artificial_analysis_agentic_index"),
            price=(m.get("pricing") or {}).get("price_1m_blended_3_to_1"),
            speed=m.get("median_output_tokens_per_second"),
        )
        for n, s, o, m in rows[:15]
    ]
    rows = rows[:7]
    top = rows[0][1]
    items = []
    for n, s, o, m in rows:
        bits = []
        sp = m.get("median_output_tokens_per_second")
        pr = (m.get("pricing") or {}).get("price_1m_blended_3_to_1")
        if sp:
            bits.append(f"ความเร็ว {sp:.0f} tokens/วินาที")
        if pr is not None:
            bits.append(f"ราคาผสม ${pr:.2f}/ล้าน tokens")
        items.append([n, f"{s:.1f}", o, " · ".join(bits) or "ดูรายละเอียดที่เว็บต้นทาง", round(s / top * 100)])
    return table(
        "aa",
        "Artificial Analysis",
        "Artificial Analysis: ความสามารถที่วัดแบบมาตรฐาน",
        f"ดึงเมื่อ {TODAY}",
        "ทีมเดียวกันรันชุดทดสอบมาตรฐานกับทุกโมเดล จึงเทียบข้ามค่ายได้ยุติธรรม และมีข้อมูลราคาและความเร็ว",
        items,
        "เวอร์ชันของ Index เปลี่ยนเป็นระยะ เทียบคะแนนข้ามช่วงเวลาตรง ๆ ไม่ได้",
        [["Data from Artificial Analysis", "https://artificialanalysis.ai/"]],
    )


def lm():
    global ARENA
    u = (
        "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset"
        "&config=text&split=latest&offset=0&length=100"
    )
    rows = [r["row"] for r in get(u)["rows"]]
    if rows and "category" in rows[0]:
        rows = [r for r in rows if r["category"] == "overall"] or rows
    rows.sort(key=lambda r: -r["rating"])
    ARENA = {r["model_name"]: r["rating"] for r in rows}
    rows = rows[:6]
    top = rows[0]["rating"]
    items = [
        [
            r["model_name"],
            str(round(r["rating"])),
            r.get("organization", ""),
            f"จำนวนโหวต {int(r.get('vote_count', 0)):,}",
            round(r["rating"] / top * 100),
        ]
        for r in rows
    ]
    date = str(rows[0].get("leaderboard_publish_date") or TODAY)
    return table(
        "lm",
        "LMArena",
        "LMArena Text: ความชอบของผู้ใช้จริง",
        f"ข้อมูลวันที่ {date}",
        "ผู้ใช้เปรียบเทียบคำตอบของสองโมเดลแบบไม่รู้ชื่อแล้วโหวต สะท้อนว่าคนชอบคำตอบแบบไหนจริง",
        items,
        "คะแนนที่ต่างกันไม่กี่แต้มอยู่ในช่วงความคลาดเคลื่อน ถือว่าเสมอกันทางสถิติได้",
        [["LMArena leaderboard dataset (CC BY 4.0)", "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"]],
    )


def hn():
    ids = get("https://hacker-news.firebaseio.com/v0/topstories.json")[:12]
    out = []
    for i in ids:
        x = get(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        out.append([x["title"], x.get("url") or f"https://news.ycombinator.com/item?id={i}", f"{x.get('score', 0)} คะแนน"])
    return out


def gh(languages: list[str] | None = None):
    d = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    hd = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"} if os.environ.get("GITHUB_TOKEN") else {}
    r = get(f"https://api.github.com/search/repositories?q=created:>{d}&sort=stars&order=desc&per_page=10", hd)
    items = [[x["full_name"], x["html_url"], f"★{x['stargazers_count']:,} {x.get('language') or ''}"] for x in r["items"]]
    by_lang = {}
    for lang in (languages or [])[:5]:
        try:
            q = requests.utils.quote(f"created:>{d} language:{lang}")
            lr = get(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5", hd)
            by_lang[lang] = [
                [x["full_name"], x["html_url"], f"★{x['stargazers_count']:,}"] for x in lr.get("items", [])
            ]
        except Exception:
            by_lang[lang] = []
    return {"top": items, "by_lang": by_lang}


def hf():
    a = get("https://huggingface.co/api/models?sort=trendingScore&limit=10")
    return [[x["id"], f"https://huggingface.co/{x['id']}", f"♥{x.get('likes', '')}"] for x in a]


def npm(packages: list[str]):
    out = []
    for p in packages:
        try:
            d = get(f"https://api.npmjs.org/downloads/point/last-week/{p}")
            out.append([p, f"https://www.npmjs.com/package/{p}", f"{d['downloads']:,} /สัปดาห์"])
        except Exception as e:
            out.append([p, f"https://www.npmjs.com/package/{p}", f"ดึงไม่ได้: {str(e)[:60]}"])
    return out


def kev():
    v = get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json")["vulnerabilities"]
    v.sort(key=lambda x: x["dateAdded"], reverse=True)
    return [
        [f"{x['cveID']} {x['vendorProject']} {x['product']}", f"https://nvd.nist.gov/vuln/detail/{x['cveID']}", f"เพิ่มเมื่อ {x['dateAdded']}"]
        for x in v[:10]
    ]


def epss():
    r = get("https://api.first.org/data/v1/epss?order=!epss&limit=10")["data"]
    return [[x["cve"], f"https://nvd.nist.gov/vuln/detail/{x['cve']}", f"EPSS {float(x['epss']):.3f}"] for x in r]


def openrouter():
    global OR_NEW, OR_MODELS
    raw = [m for m in get("https://openrouter.ai/api/v1/models")["data"] if m.get("created")]
    models = []
    for m in raw:
        p = m.get("pricing") or {}
        try:
            prompt = float(p.get("prompt") or 0) * 1e6
            completion = float(p.get("completion") or 0) * 1e6
            blended = prompt * 0.75 + completion * 0.25
        except Exception:
            prompt = completion = blended = None
        arch = m.get("architecture") or {}
        mods_in = arch.get("input_modalities") or []
        mods_out = arch.get("output_modalities") or []
        models.append(
            dict(
                id=m.get("id"),
                name=m.get("name") or m.get("id"),
                url=f"https://openrouter.ai/{m.get('id')}",
                created=m.get("created"),
                context=m.get("context_length") or 0,
                prompt=prompt,
                completion=completion,
                blended=blended,
                modality=arch.get("modality") or "",
                input_modalities=mods_in,
                output_modalities=mods_out,
                reasoning=bool(m.get("reasoning")),
            )
        )
    OR_MODELS = models
    newest = sorted(models, key=lambda x: -x["created"])[:10]
    OR_NEW = []
    out = []
    for m in newest:
        price = (
            f"${m['prompt']:.2f} / ${m['completion']:.2f} ต่อล้าน tokens"
            if m["prompt"] is not None
            else "ราคาไม่ระบุ"
        )
        c = f"{m['context']:,}" if m["context"] else "?"
        row = [m["name"], m["url"], f"{dt.date.fromtimestamp(m['created'])} · context {c} · {price}"]
        out.append(row)
        OR_NEW.append(row)
    return out


def _arena_score(row: dict) -> float:
    if row.get("rating") is not None:
        return float(row["rating"])
    if row.get("score") is not None:
        return float(row["score"])
    return 0.0


def fetch_arena_config(config: str, limit: int = 8) -> list[dict]:
    u = (
        "https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset"
        f"&config={config}&split=latest&offset=0&length=100"
    )
    rows = [r["row"] for r in get(u)["rows"]]
    if not rows:
        return []
    if any(r.get("category") == "overall" for r in rows):
        rows = [r for r in rows if r.get("category") == "overall"]
    rows.sort(key=lambda r: -_arena_score(r))
    out = []
    for i, r in enumerate(rows[:limit]):
        score = _arena_score(r)
        out.append(
            dict(
                rank=int(r.get("rank") or i + 1),
                name=r.get("model_name") or "",
                org=r.get("organization") or "",
                score=score,
                votes=int(r.get("vote_count") or r.get("observation_count") or 0),
                date=str(r.get("leaderboard_publish_date") or TODAY),
                license=r.get("license") or "",
            )
        )
    return out


def arena_dimensions():
    """ดึงบอร์ดแยกมิติจาก LMArena หลาย config"""
    global ARENA_DIMS, ARENA
    boards = []
    for spec in DIM_SPECS:
        items = fetch_arena_config(spec["config"], limit=8)
        if not items:
            continue
        kind = spec.get("score_kind") or "elo"
        top = items[0]["score"] or 1
        formatted = []
        for it in items:
            if kind == "ratio":
                label = f"{it['score'] * 100:.1f}%"
                bar = round(it["score"] / top * 100) if top else 0
            else:
                label = str(round(it["score"]))
                bar = round(it["score"] / top * 100) if top else 0
            formatted.append(
                {
                    **it,
                    "score_label": label,
                    "bar": bar,
                    "meta": f"โหวต/สังเกต ~{it['votes']:,}" if it["votes"] else it.get("license") or "",
                }
            )
        board = {
            "id": spec["id"],
            "config": spec["config"],
            "label": spec["label"],
            "short": spec["short"],
            "use": spec["use"],
            "tip": spec["tip"],
            "score_kind": kind,
            "date": formatted[0]["date"],
            "leader": formatted[0]["name"],
            "items": formatted,
        }
        boards.append(board)
        ARENA_DIMS[spec["id"]] = board
        if spec["id"] == "text":
            ARENA = {it["name"]: it["score"] for it in formatted}
    return boards


def build_or_specialties() -> dict:
    """มิติจาก OpenRouter: ราคา, context, multimodal, reasoning"""
    def usable(m: dict) -> bool:
        mid = (m.get("id") or "").lower()
        name = (m.get("name") or "").lower()
        # ตัด router / ราคาพิเศษที่ทำให้ตัวเลขเพี้ยน
        if mid.startswith("openrouter/") or "auto router" in name or "auto code" in name:
            return False
        b = m.get("blended")
        if b is not None and (b < 0 or b > 500):
            return False
        return bool(m.get("name"))

    models = [m for m in OR_MODELS if usable(m)]
    if not models:
        return {}

    def row(m, note):
        return {
            "name": m["name"],
            "org": (m.get("id") or "").split("/")[0],
            "url": m["url"],
            "note": note,
            "context": m.get("context") or 0,
            "blended": m.get("blended"),
            "modality": m.get("modality") or "",
        }

    paid = [m for m in models if isinstance(m.get("blended"), (int, float)) and 0 < m["blended"] <= 500]
    long_ctx = sorted(
        [m for m in models if (m.get("context") or 0) >= 200_000],
        key=lambda m: (-m["context"], m["blended"] if m.get("blended") is not None and m["blended"] > 0 else 9e9),
    )
    value = sorted(
        [m for m in paid if (m.get("context") or 0) >= 64_000],
        key=lambda m: (m["blended"] / max((m.get("context") or 1) / 1000, 1)),
    )
    multi = [
        m
        for m in models
        if any(x in (m.get("input_modalities") or []) for x in ("image", "audio", "video", "file"))
        or ("image" in (m.get("modality") or "") or "audio" in (m.get("modality") or "") or "video" in (m.get("modality") or ""))
    ]
    multi = sorted(
        multi,
        key=lambda m: (
            -len(m.get("input_modalities") or []),
            m["blended"] if m.get("blended") is not None and m["blended"] > 0 else 9e9,
        ),
    )
    reason = [m for m in models if m.get("reasoning")]
    reason = sorted(
        reason,
        key=lambda m: (
            m["blended"] if m.get("blended") is not None and m["blended"] >= 0 else 9e9,
            -m.get("context", 0),
        ),
    )
    cheap = sorted(paid, key=lambda m: m["blended"])

    def pack(title, tip, items, n=6):
        out = []
        for m in items[:n]:
            bits = []
            if m.get("context"):
                bits.append(f"context {m['context']:,}")
            if m.get("blended") is not None:
                bits.append(f"~${m['blended']:.2f}/ล้านผสม")
            if m.get("modality"):
                bits.append(m["modality"])
            out.append(row(m, " · ".join(bits) or tip))
        return {"title": title, "tip": tip, "items": out}

    return {
        "long_context": pack("Context ยาวพิเศษ (≥200K)", "เหมาะงานเอกสารยาว / codebase ใหญ่", long_ctx),
        "value": pack("คุ้ม context ต่อราคา", "ได้ context เยอะในราคาไม่แพง (ประมาณการจาก OpenRouter)", value),
        "multimodal": pack("Multimodal (รับรูป/ไฟล์/เสียง/วิดีโอ)", "ใช้เมื่องานไม่ใช่แค่ข้อความ", multi),
        "reasoning": pack("มีโหมด Reasoning", "โมเดลที่ OpenRouter ติดธง reasoning", reason),
        "cheap": pack("ราคาถูกสุด (ประมาณ)", "งานปริมาณมากที่คุณภาพไม่ต้องท็อปสุด", cheap),
    }


def build_dimensions(boards: list[dict]) -> dict:
    """สรุปมิติ + ตารางไขว้ + คำแนะนำตามงาน"""
    picks = []
    for b in boards:
        if not b.get("items"):
            continue
        top = b["items"][0]
        picks.append(
            {
                "dim": b["id"],
                "label": b["label"],
                "short": b["short"],
                "model": top["name"],
                "org": top["org"],
                "score_label": top["score_label"],
                "use": b["use"],
                "why": f"อันดับ 1 บน LMArena · {b['short']} — เหมาะงาน: {b['use']}",
            }
        )

    # ตารางไขว้: โมเดลที่โผล่หลายมิติ
    rank_map: dict[str, dict] = {}
    for b in boards:
        for it in b.get("items") or []:
            name = it["name"]
            slot = rank_map.setdefault(name, {"name": name, "org": it.get("org") or "", "ranks": {}, "appear": 0})
            slot["ranks"][b["id"]] = it["rank"]
            slot["appear"] += 1
    # เลือกโมเดลที่ปรากฏ ≥2 มิติ หรือท็อปของมิติหลัก
    leaders = {b["leader"] for b in boards}
    matrix = [v for v in rank_map.values() if v["appear"] >= 2 or v["name"] in leaders]
    matrix.sort(key=lambda x: (-x["appear"], sum(x["ranks"].values()) / max(len(x["ranks"]), 1)))
    matrix = matrix[:12]

    # specialty จาก AA ถ้ามี
    aa_dims = []
    if AA_ROWS:
        coding = [r for r in AA_ROWS if r.get("coding") is not None]
        agentic = [r for r in AA_ROWS if r.get("agentic") is not None]
        speed = [r for r in AA_ROWS if r.get("speed")]
        value = [r for r in AA_ROWS if isinstance(r.get("price"), (int, float)) and r["price"] > 0]
        if coding:
            bc = max(coding, key=lambda r: r["coding"])
            aa_dims.append({"id": "aa_coding", "label": "AA Coding Index", "model": bc["name"], "score_label": f"{bc['coding']:.1f}", "why": "ทดสอบ coding มาตรฐานจาก Artificial Analysis"})
        if agentic:
            ba = max(agentic, key=lambda r: r["agentic"])
            aa_dims.append({"id": "aa_agentic", "label": "AA Agentic Index", "model": ba["name"], "score_label": f"{ba['agentic']:.1f}", "why": "ทดสอบ agentic / tool use มาตรฐาน"})
        if speed:
            bs = max(speed, key=lambda r: r["speed"])
            aa_dims.append({"id": "aa_speed", "label": "ความเร็ว (tok/s)", "model": bs["name"], "score_label": f"{bs['speed']:.0f}", "why": "median output tokens/วินาที จาก AA"})
        if value:
            bv = max(value, key=lambda r: (r.get("aa") or 0) / r["price"])
            aa_dims.append({"id": "aa_value", "label": "คุ้มค่า AA/ราคา", "model": bv["name"], "score_label": f"{(bv['aa']/bv['price']):.1f}", "why": "คะแนน AA ต่อราคาผสม — งานปริมาณมาก"})

    specialties = build_or_specialties()
    blurb = "แยกมิติตามงานจริงจาก LMArena (ไม่ใช่คะแนนรวมอย่างเดียว) — โมเดลที่เก่ง chat อาจไม่ชนะ WebDev/Agent/Vision"
    if picks:
        blurb = (
            f"ตอนนี้ผู้นำคนละมิติ: "
            + ", ".join(f"{p['short']}→{p['model']}" for p in picks[:4])
            + " — เลือกตามงาน ไม่ใช่ตามชื่อดังอย่างเดียว"
        )

    return {
        "blurb": blurb,
        "boards": boards,
        "picks": picks,
        "matrix": matrix,
        "aa_dims": aa_dims,
        "specialties": specialties,
        "source": [
            ["LMArena leaderboard dataset (CC BY 4.0)", "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"],
            ["OpenRouter models", "https://openrouter.ai/models"],
        ],
        "method": "แต่ละการ์ดดึง config แยกจาก LMArena + มิติราคา/context จาก OpenRouter อัปเดตอัตโนมัติ",
    }


def build_ai(data):
    if not AA_ROWS:
        return data.get("ai")
    prev = set((data.get("ai") or {}).get("seen", []))
    an = {norm(k): v for k, v in ARENA.items()}
    # รวมคะแนนจากมิติด้าน coding/agent ถ้ามี
    web = {norm(it["name"]): it["rank"] for it in (ARENA_DIMS.get("webdev") or {}).get("items") or []}
    ag = {norm(it["name"]): it["rank"] for it in (ARENA_DIMS.get("agent") or {}).get("items") or []}
    rows = []
    for r in AA_ROWS:
        key = norm(r["name"])
        a = an.get(key)
        rows.append(
            {
                **r,
                "arena": round(a) if a else None,
                "webdev_rank": web.get(key),
                "agent_rank": ag.get(key),
                "new": bool(prev) and r["name"] not in prev,
            }
        )
    return {"compare": rows, "seen": [r["name"] for r in AA_ROWS], "arena_count": len(ARENA)}


def corpus_text(data: dict) -> str:
    bits = []
    for t in data.get("tables") or []:
        for it in t.get("items") or []:
            bits.append(" ".join(str(x) for x in it[:3]))
    live = data.get("live") or {}
    for key in ("hn", "hf", "or"):
        for it in live.get(key) or []:
            bits.append(str(it[0]))
    gh = live.get("gh")
    if isinstance(gh, dict):
        for it in gh.get("top") or []:
            bits.append(str(it[0]))
        for items in (gh.get("by_lang") or {}).values():
            for it in items:
                bits.append(str(it[0]))
    elif isinstance(gh, list):
        for it in gh:
            bits.append(str(it[0]))
    for r in (data.get("ai") or {}).get("compare") or []:
        bits.append(f"{r.get('name','')} {r.get('org','')}")
        if r.get("coding"):
            bits.append("coding")
        if r.get("agentic"):
            bits.append("agent tool")
    for b in (data.get("dimensions") or {}).get("boards") or []:
        bits.append(b.get("label") or "")
        bits.append(b.get("use") or "")
        for it in (b.get("items") or [])[:5]:
            bits.append(it.get("name") or "")
        if b.get("id") == "webdev":
            bits.append("coding ide copilot")
        if b.get("id") == "agent":
            bits.append("agent agents tool mcp")
        if b.get("id") in ("vision", "image"):
            bits.append("multimodal vision image")
    return " ".join(bits).lower()


def build_trends(data: dict, watch: dict) -> dict:
    text = corpus_text(data)
    themes_cfg = watch.get("theme_keywords") or {}
    scored = []
    for name, kws in themes_cfg.items():
        hits = []
        score = 0
        for kw in kws:
            c = text.count(str(kw).lower())
            if c:
                hits.append(kw)
                score += c
        if score:
            scored.append({"name": name, "score": score, "hits": hits[:6], "heat": min(100, score * 12)})
    scored.sort(key=lambda x: -x["score"])
    themes = scored[:8]

    recs = []
    # คำแนะนำจากมิติเฉพาะทางก่อน (ละเอียดกว่าภาพรวม)
    for p in ((data.get("dimensions") or {}).get("picks") or [])[:6]:
        tier = "use" if p.get("dim") in ("text", "webdev", "factual", "document") else "watch"
        recs.append(
            {
                "tier": tier,
                "title": f"{p['model']} · {p['short']}",
                "why": p.get("why") or f"นำมิติ {p['label']}",
                "tags": [p.get("short") or "มิติ", p.get("org") or "AI", p.get("use") or ""],
            }
        )

    compare = (data.get("ai") or {}).get("compare") or []
    if compare:
        best = compare[0]
        recs.append(
            {
                "tier": "use",
                "title": best["name"],
                "why": f"นำด้านความสามารถ (AA {best.get('aa')}) จาก Artificial Analysis — เหมาะเป็น default สำหรับงานทั่วไป/ยาก",
                "tags": ["ความสามารถสูง", best.get("org") or "AI"],
            }
        )
        value = [r for r in compare if isinstance(r.get("price"), (int, float)) and r["price"] > 0]
        if value:
            bv = max(value, key=lambda r: (r.get("aa") or 0) / r["price"])
            if bv["name"] != best["name"]:
                recs.append(
                    {
                        "tier": "use",
                        "title": bv["name"],
                        "why": f"คุ้มค่าสุดใน Top ที่จับคู่ได้ (AA {bv.get('aa')} ต่อราคา ${bv['price']:.2f}/ล้าน) — เหมาะงานปริมาณมาก",
                        "tags": ["คุ้มราคา", bv.get("org") or "AI"],
                    }
                )
        coding = [r for r in compare if r.get("coding") is not None]
        if coding:
            bc = max(coding, key=lambda r: r["coding"])
            recs.append(
                {
                    "tier": "watch" if bc["name"] == best["name"] else "use",
                    "title": f"{bc['name']} (coding)",
                    "why": f"นำด้าน Coding Index ({bc['coding']}) — น่าลองกับงานเขียนโค้ด / review",
                    "tags": ["coding", bc.get("org") or "AI"],
                }
            )
        agentic = [r for r in compare if r.get("agentic") is not None]
        if agentic:
            ba = max(agentic, key=lambda r: r["agentic"])
            recs.append(
                {
                    "tier": "watch",
                    "title": f"{ba['name']} (agentic)",
                    "why": f"นำด้าน Agentic Index ({ba['agentic']}) — จับตาถ้าทำ agent / tool-calling",
                    "tags": ["agents", ba.get("org") or "AI"],
                }
            )
        arena = [r for r in compare if r.get("arena") is not None]
        if arena:
            br = max(arena, key=lambda r: r["arena"])
            if br["name"] != best["name"]:
                recs.append(
                    {
                        "tier": "watch",
                        "title": br["name"],
                        "why": f"คนชอบสูงบน LMArena ({br['arena']}) แม้คะแนนทดสอบอาจไม่สูงสุด — เหมาะงานสนทนา/เขียน",
                        "tags": ["user preference", br.get("org") or "AI"],
                    }
                )
        for r in compare:
            if r.get("new"):
                recs.append(
                    {
                        "tier": "watch",
                        "title": r["name"],
                        "why": "เพิ่งเข้า Top 15 ของ AA ในรอบนี้ — น่าจับตาและทดสอบกับโจทย์จริงของคุณ",
                        "tags": ["ใหม่ในบอร์ด", r.get("org") or "AI"],
                    }
                )
    else:
        # fallback เมื่อไม่มี AA: ใช้ LMArena + OpenRouter + HF
        lm_table = next((t for t in (data.get("tables") or []) if t.get("id") == "lm"), None)
        if lm_table and lm_table.get("items"):
            top = lm_table["items"][0]
            recs.append(
                {
                    "tier": "use",
                    "title": top[0],
                    "why": f"นำ LMArena Text (คะแนน {top[1]}) จากโหวตผู้ใช้จริง — เริ่มจากตัวนี้สำหรับงานสนทนา/เขียน แล้วเทียบกับโจทย์ของคุณ",
                    "tags": ["LMArena", top[2] or "AI"],
                }
            )
            if len(lm_table["items"]) > 1:
                second = lm_table["items"][1]
                recs.append(
                    {
                        "tier": "watch",
                        "title": second[0],
                        "why": f"รองอันดับบน LMArena ({second[1]}) — น่าเทียบเคียงก่อนล็อก vendor",
                        "tags": ["LMArena", second[2] or "AI"],
                    }
                )
            # open-weight hint from LM names
            for it in lm_table["items"][:6]:
                name = str(it[0]).lower()
                if any(k in name for k in ("deepseek", "qwen", "llama", "gemma", "mistral", "glm", "kimi")):
                    recs.append(
                        {
                            "tier": "watch",
                            "title": it[0],
                            "why": "สัญญาณ open-weight / ต้นทุนต่ำบนบอร์ดความชอบผู้ใช้ — น่าลองถ้าต้องการรันเองหรือคุมงบ",
                            "tags": ["open-weight", it[2] or "AI"],
                        }
                    )
                    break
        or_items = (data.get("live") or {}).get("or") or []
        if or_items:
            recs.append(
                {
                    "tier": "watch",
                    "title": or_items[0][0],
                    "why": f"โมเดลใหม่ล่าสุดบน OpenRouter — {or_items[0][2]} — เหมาะทดลองฟีเจอร์ใหม่ก่อนตัดสินใจ",
                    "tags": ["OpenRouter", "ใหม่"],
                }
            )
        hf_items = (data.get("live") or {}).get("hf") or []
        if hf_items:
            recs.append(
                {
                    "tier": "watch",
                    "title": hf_items[0][0],
                    "why": "ติด Trending บน Hugging Face ตอนนี้ — ดูถ้าสนใจโมเดล/น้ำหนักที่ชุมชนกำลังลอง",
                    "tags": ["Hugging Face", "trending"],
                }
            )

    # open-weight signal from HF / themes
    if any(t["name"].startswith("Open-weight") for t in themes[:3]):
        recs.append(
            {
                "tier": "watch",
                "title": "Open-weight / local models",
                "why": "สัญญาณจาก HN/HF/GitHub ชี้ว่า open-weight กำลังร้อน — ลองถ้าต้องการคุมข้อมูลหรือต้นทุน",
                "tags": ["open-weight", "local"],
            }
        )

    # coding theme tip for developers
    if any(t["name"].startswith("Coding") for t in themes[:4]):
        recs.append(
            {
                "tier": "use",
                "title": "Coding assistants / IDE agents",
                "why": "ธีม coding กำลังร้อนในแหล่งสด — คุ้มลงทุนเวลาเทียบเครื่องมือช่วยเขียนโค้ดกับ workflow ปัจจุบันของคุณ",
                "tags": ["coding", "devtools"],
            }
        )

    kev_items = (data.get("live") or {}).get("kev") or []
    if kev_items:
        recs.append(
            {
                "tier": "caution",
                "title": kev_items[0][0],
                "why": "อยู่ใน CISA KEV (ถูกโจมตีจริง) — ตรวจระบบที่เกี่ยวกับ vendor/product นี้ก่อน ไม่ใช่เทรนน่าลอง",
                "tags": ["security", "KEV"],
            }
        )

    # de-dupe by title keep first
    seen = set()
    uniq = []
    for r in recs:
        if r["title"] in seen:
            continue
        seen.add(r["title"])
        uniq.append(r)

    blurb = (
        f"สรุปเทรน {YEAR}: สัญญาณรวมจาก leaderboard โมเดล, OpenRouter, Hacker News, GitHub, Hugging Face และช่องโหว่ที่ถูกโจมตีจริง"
    )
    if themes:
        top_names = ", ".join(t["name"] for t in themes[:3])
        blurb = f"ปี {YEAR} ตอนนี้ความสนใจกระจุกที่: {top_names}. ใช้คำแนะนำด้านล่างเป็นจุดเริ่ม แล้วทดสอบกับงานจริงก่อนล็อกสแตก"

    return {
        "year": YEAR,
        "blurb": blurb,
        "themes": themes,
        "recommendations": uniq[:10],
        "method": "นับคำจากแหล่งสด + อันดับโมเดล ไม่ใช่ความเห็นบรรณาธิการ — รีเฟรชอัตโนมัติทุกครั้งที่สคริปต์รัน",
    }


def snapshot_for_diff(data: dict) -> dict:
    ai_names = [r["name"] for r in (data.get("ai") or {}).get("compare") or []]
    themes = [t["name"] for t in (data.get("trends") or {}).get("themes") or []]
    dim_leaders = [f"{p.get('dim')}:{p.get('model')}" for p in ((data.get("dimensions") or {}).get("picks") or [])[:8]]
    return {
        "ai_top": ai_names[:5],
        "themes": themes[:5],
        "dim_leaders": dim_leaders,
        "or_top": [x[0] for x in ((data.get("live") or {}).get("or") or [])[:5]],
        "hn_top": [x[0] for x in ((data.get("live") or {}).get("hn") or [])[:5]],
    }


def build_changes(prev: dict | None, cur: dict) -> dict:
    if not prev:
        return {"has_prev": False, "items": [], "summary": "รอบแรกหรือยังไม่มีประวัติเปรียบเทียบ"}
    items = []
    pa, ca = prev.get("ai_top") or [], cur.get("ai_top") or []
    if pa and ca and pa[0] != ca[0]:
        items.append({"kind": "ai_lead", "text": f"ผู้นำ AA เปลี่ยนจาก {pa[0]} → {ca[0]}"})
    for name in ca:
        if name not in pa:
            items.append({"kind": "ai_new", "text": f"โมเดลใหม่ใน Top: {name}"})
    pt, ct = prev.get("themes") or [], cur.get("themes") or []
    for name in ct:
        if name not in pt:
            items.append({"kind": "theme_up", "text": f"ธีมขึ้นแรง: {name}"})
    for name in pt[:3]:
        if name not in ct[:5]:
            items.append({"kind": "theme_down", "text": f"ธีมแผ่วลงจากท็อป: {name}"})
    pd, cd = prev.get("dim_leaders") or [], cur.get("dim_leaders") or []
    prev_map = dict(x.split(":", 1) for x in pd if ":" in x)
    for entry in cd:
        if ":" not in entry:
            continue
        dim, model = entry.split(":", 1)
        if dim in prev_map and prev_map[dim] != model:
            items.append({"kind": "dim", "text": f"ผู้นำมิติ {dim} เปลี่ยน: {prev_map[dim]} → {model}"})
        elif dim not in prev_map:
            items.append({"kind": "dim", "text": f"มีมิติใหม่/ผู้นำ: {dim} → {model}"})
    ph, ch = set(prev.get("hn_top") or []), cur.get("hn_top") or []
    for t in ch[:3]:
        if t not in ph:
            items.append({"kind": "hn", "text": f"HN ใหม่ในท็อป: {t}"})
    summary = f"พบการเปลี่ยนแปลง {len(items)} รายการจากรอบก่อน" if items else "คะแนนหลักนิ่งจากรอบก่อน (ยังอัปเดตแหล่งสดตามปกติ)"
    return {"has_prev": True, "items": items[:12], "summary": summary}


def save_history(data: dict):
    HISTORY_DIR.mkdir(exist_ok=True)
    day = dt.date.today().isoformat()
    snap = {
        "updated": data.get("updated"),
        "snapshot": snapshot_for_diff(data),
        "trends": data.get("trends"),
        "status": data.get("status"),
    }
    path = HISTORY_DIR / f"{day}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    # keep last 60 day files
    files = sorted(HISTORY_DIR.glob("*.json"))
    for old in files[:-60]:
        try:
            old.unlink()
        except OSError:
            pass


def load_prev_snapshot(data: dict) -> dict | None:
    # prefer last history file before today, else embedded previous_snapshot
    if HISTORY_DIR.exists():
        files = sorted(HISTORY_DIR.glob("*.json"))
        for path in reversed(files):
            if path.stem != TODAY:
                try:
                    return json.load(open(path, encoding="utf-8")).get("snapshot")
                except Exception:
                    pass
    return (data.get("meta") or {}).get("previous_snapshot")


def main():
    watch = load_watchlist()
    try:
        data = json.load(open(DATA_PATH, encoding="utf-8"))
    except Exception:
        data = {"tables": [], "live": {}, "status": {}}

    data.setdefault("status", {})
    data.setdefault("live", {})
    data.setdefault("tables", [])
    data.setdefault("schema", 3)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    prev_snap = load_prev_snapshot(data)

    for name, fn in [("aa", aa), ("lm", lm)]:
        try:
            t = fn()
            data["tables"] = [x for x in data["tables"] if x["id"] != name] + [t]
            data["status"][name] = {"ok": True, "time": now}
        except Exception as e:
            data["status"][name] = {"ok": False, "time": now, "msg": str(e)[:150]}

    # บอร์ดแยกมิติ (สำคัญกว่าภาพรวม)
    boards = []
    try:
        boards = arena_dimensions()
        # sync ตาราง LMArena text จากมิติ text ถ้ามี
        text_board = next((b for b in boards if b["id"] == "text"), None)
        if text_board and text_board.get("items"):
            items = [
                [it["name"], it["score_label"], it["org"], it.get("meta") or "", it.get("bar") or 0]
                for it in text_board["items"][:6]
            ]
            data["tables"] = [x for x in data["tables"] if x["id"] != "lm"] + [
                table(
                    "lm",
                    "LMArena",
                    "LMArena Text: ความชอบของผู้ใช้จริง",
                    f"ข้อมูลวันที่ {text_board.get('date') or TODAY}",
                    "ผู้ใช้เปรียบเทียบคำตอบของสองโมเดลแบบไม่รู้ชื่อแล้วโหวต สะท้อนว่าคนชอบคำตอบแบบไหนจริง",
                    items,
                    "ดูแท็บมิติโมเดล สำหรับ WebDev / Agent / Vision / Search แยกตามงาน",
                    [["LMArena leaderboard dataset (CC BY 4.0)", "https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset"]],
                )
            ]
        data["status"]["dims"] = {"ok": True, "time": now, "msg": f"{len(boards)} boards"}
    except Exception as e:
        data["status"]["dims"] = {"ok": False, "time": now, "msg": str(e)[:150]}
        boards = (data.get("dimensions") or {}).get("boards") or []

    npm_pkgs = watch.get("npm") or ["react", "vue", "svelte", "solid-js", "@angular/core"]
    langs = watch.get("github_languages") or ["Python", "TypeScript", "Rust"]

    def run_gh():
        return gh(langs)

    def run_npm():
        return npm(npm_pkgs)

    for name, fn in [
        ("or", openrouter),
        ("hn", hn),
        ("gh", run_gh),
        ("hf", hf),
        ("npm", run_npm),
        ("kev", kev),
        ("epss", epss),
    ]:
        try:
            data["live"][name] = fn()
            data["status"][name] = {"ok": True, "time": now}
        except Exception as e:
            data["status"][name] = {"ok": False, "time": now, "msg": str(e)[:150]}

    try:
        data["dimensions"] = build_dimensions(boards)
        data["status"]["dimensions"] = {"ok": True, "time": now}
    except Exception as e:
        data["status"]["dimensions"] = {"ok": False, "time": now, "msg": str(e)[:150]}

    try:
        ai = build_ai(data)
        if ai:
            data["ai"] = ai
            data["status"]["ai"] = {"ok": True, "time": now}
    except Exception as e:
        data["status"]["ai"] = {"ok": False, "time": now, "msg": str(e)[:150]}

    try:
        data["trends"] = build_trends(data, watch)
        data["status"]["trends"] = {"ok": True, "time": now}
    except Exception as e:
        data["status"]["trends"] = {"ok": False, "time": now, "msg": str(e)[:150]}

    cur_snap = snapshot_for_diff(data)
    data["changes"] = build_changes(prev_snap, cur_snap)
    data["meta"] = {"previous_snapshot": cur_snap, "year": YEAR, "schema": 3}
    data["updated"] = now

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    save_history(data)

    for k, v in data["status"].items():
        print(k, "OK" if v.get("ok") else "FAIL " + v.get("msg", ""))


if __name__ == "__main__":
    main()
