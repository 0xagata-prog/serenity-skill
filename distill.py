"""
scripts/distill.py
从最新推文重新蒸馏，同时更新：
  1. SKILL.md
  2. index.html 里的推文数据和股票 Wiki
"""
import os
import re
import json
import pandas as pd
from anthropic import Anthropic
from collections import Counter
from pathlib import Path

client = Anthropic()
DATA_FILE  = Path("data/latest_tweets.csv")
SKILL_FILE = Path("SKILL.md")
HTML_FILE  = Path("index.html")


# ── 1. 数据提取 ────────────────────────────────────────────────

def extract_stats(df):
    her = df[df["url"].str.contains("aleabitoreddit", na=False)].copy()
    her["date"] = pd.to_datetime(her["date"])

    all_tickers = []
    for content in her["content"].dropna():
        all_tickers.extend(re.findall(r'\$([A-Z]{1,5})\b', content))
    top_tickers = Counter(all_tickers).most_common(20)
    top_tweets  = her.nlargest(10, "likeCount")[["date","content","likeCount","url"]]
    date_range  = f"{her['date'].min().strftime('%Y-%m')} → {her['date'].max().strftime('%Y-%m')}"

    return {
        "her": her,
        "total": len(her),
        "date_range": date_range,
        "top_tickers": top_tickers,
        "top_tweets": top_tweets.to_dict("records"),
    }


def get_theme_tweets(her, keywords, n=4):
    """按关键词抓主题推文"""
    pattern = '|'.join(keywords)
    sub = her[her["content"].str.contains(pattern, case=False, na=False)]
    rows = sub.nlargest(n, "likeCount")
    result = []
    for _, r in rows.iterrows():
        result.append({
            "body": r["content"][:350].replace("\\", "\\\\").replace("`", "'"),
            "likes": int(r["likeCount"]),
            "date": str(r["date"])[:10],
            "url": r["url"]
        })
    return result


def get_wiki_data(her, top_n=12):
    """生成股票 Wiki 数据"""
    all_tickers = []
    for content in her["content"].dropna():
        all_tickers.extend(re.findall(r'\$([A-Z]{1,5})\b', content))
    counter = Counter(all_tickers)

    # 已知情绪标注（bear 的保留，其余默认 bull）
    bear_list = {"IREN", "HOOD"}

    result = []
    for ticker, count in counter.most_common(top_n):
        mask = her["content"].str.contains(f'\\${ticker}\\b', na=False)
        sub  = her[mask].nlargest(2, "likeCount")
        tweets = []
        for _, r in sub.iterrows():
            tweets.append({
                "c": r["content"][:180].replace("\\", "\\\\").replace("`", "'").replace("\n", " "),
                "l": int(r["likeCount"]),
                "d": str(r["date"])[:10]
            })
        sentiment = "bear" if ticker in bear_list else "bull"
        result.append({
            "t": ticker,
            "m": count,
            "s": sentiment,
            "tweets": tweets
        })
    return result


# ── 2. 更新 SKILL.md ──────────────────────────────────────────

def build_skill_prompt(stats):
    tickers_str = "\n".join([f"  ${t}: {c}次" for t, c in stats["top_tickers"]])
    tweets_str  = "\n\n".join([
        f"[{r['likeCount']}❤ {str(r['date'])[:10]}]\n{r['content'][:300]}"
        for r in stats["top_tweets"]
    ])
    return f"""You are distilling the thinking of Serenity (@aleabitoreddit), a supply chain bottleneck analyst on X with 500k+ followers.

DATA SUMMARY:
- Total her own tweets analyzed: {stats['total']}
- Date range: {stats['date_range']}

TOP MENTIONED TICKERS:
{tickers_str}

TOP 10 MOST LIKED TWEETS:
{tweets_str}

YOUR TASK:
Generate an updated SKILL.md. Include:
1. ## Who is Serenity
2. ## Mental Models (5-6, with tweet quotes as evidence)
3. ## Decision Heuristics
4. ## Expression DNA
5. ## Core Investment Thesis (bull/bear based on latest data)
6. ## Honest Limits
7. ## How to Use This Skill

Write in English. Start with:
# Serenity.skill
> *Distilled from {stats['total']} tweets by @aleabitoreddit — updated {stats['date_range']}*

End with:
*Distilled with care from {stats['total']} tweets. Not financial advice. Not Serenity.*
*Made by @0xAgata. All research credit to @aleabitoreddit.*
*Auto-updated monthly. Views may have changed — check latest release.*
"""

def update_skill(stats):
    print("Distilling SKILL.md...")
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": build_skill_prompt(stats)}]
    )
    new_skill = response.content[0].text
    SKILL_FILE.write_text(new_skill, encoding="utf-8")
    print(f"SKILL.md updated ({len(new_skill)} chars)")


# ── 3. 更新 index.html ────────────────────────────────────────

def js_str(s):
    """把 Python 字符串安全转成 JS 字符串内容"""
    return s.replace("\\", "\\\\").replace("`", "'").replace("</", "<\\/")

def build_themes_js(her):
    themes = {
        "cpo":    ["CPO","photonics","chokepoint","laser","optical","SIVE","supercycle"],
        "retail": ["free","paywall","retail","institution","for free","hedge fund"],
        "bear":   ["bearish","dumpster","IREN","avoid","scam","terrible"],
        "record": ["YTD","return","10x","cooked","called out","thesis"],
    }
    js_parts = []
    for key, kws in themes.items():
        tweets = get_theme_tweets(her, kws, n=4)
        items = []
        for tw in tweets:
            body = js_str(tw["body"])
            items.append(
                f'{{body:`{body}`,likes:{tw["likes"]},date:"{tw["date"]}",url:"{tw["url"]}"}}'
            )
        js_parts.append(f'{key}:[{",".join(items)}]')
    return "const THEMES={" + ",".join(js_parts) + "};"


def build_wiki_js(her):
    wiki = get_wiki_data(her, top_n=12)

    # 预置中英文描述（常见股票）
    DESCS = {
        "SIVE": ("CPO laser chokepoint. Critical supplier to Ayar/Celestial/Lightmatter.", "CPO 激光卡点。Ayar/Celestial/Lightmatter 的关键供应商。"),
        "AXTI": ("InP substrate supplier controlling 60-70% of world supply.", "InP 衬底供应商，控制全球 60-70% 供应。"),
        "AAOI": ("Transceiver/laser assembly, American-made.", "美国制造的收发器/激光组装。"),
        "LITE": ("Vertically integrated photonics. Prior supercycle flagship.", "垂直整合光子学。上一个超级周期的旗舰标的。"),
        "SOI":  ("Silicon photonics substrate. The $AXTI analog of this cycle.", "硅光子衬底。本周期的 $AXTI 类比标的。"),
        "NVDA": ("The demand anchor. AI capex to $3-4T annually by 2030.", "需求锚点。AI 资本支出到 2030 年将达 $3-4T/年。"),
        "IREN": ("BEARISH. Fake NVDA partnership — just a brand agreement.", "看空。假的 NVDA 合作关系——只是品牌协议。"),
        "NBIS": ("Nebius — better neocloud. Actual Nvidia 5.6% stake.", "Nebius——更好的新型云计算。英伟达真实持股 5.6%。"),
        "TSEM": ("Tower Semiconductor — SiPh foundry. Triple-digit returns.", "塔尔半导体——硅光子代工厂。实现三位数回报。"),
        "COHR": ("Coherent — vertically integrated, full optical cycle.", "Coherent——垂直整合，覆盖完整光学周期。"),
        "MRVL": ("Marvell — scales revenue from Maia ASICs and CPO.", "Marvell——从 Maia ASIC 和 CPO 扩大收入。"),
        "INTC": ("America's hope for foundry and national security.", "美国铸造业与国家安全的希望。"),
    }

    items = []
    for d in wiki:
        desc_en, desc_zh = DESCS.get(d["t"], (f"${d['t']} — researched by Serenity.", f"${d['t']} — Serenity 研究过的股票。"))
        tws = []
        for tw in d["tweets"]:
            c = js_str(tw["c"])
            tws.append(f'{{c:"{c}",l:{tw["l"]},d:"{tw["d"]}"}')
        items.append(
            f'{{t:"{d["t"]}",m:{d["m"]},s:"{d["s"]}",'
            f'desc_en:"{desc_en}",desc_zh:"{desc_zh}",'
            f'tw:[{",".join(tws)}]}}'
        )
    return "const WIKI=[" + ",".join(items) + "];"


def update_html(stats):
    if not HTML_FILE.exists():
        print("index.html not found, skipping")
        return

    her = stats["her"]
    print("Generating new JS data for index.html...")

    themes_js = build_themes_js(her)
    wiki_js   = build_wiki_js(her)
    date_str  = stats["date_range"]
    total     = stats["total"]

    html = HTML_FILE.read_text(encoding="utf-8")

    # 替换 THEMES 数据块
    themes_pattern = r'const THEMES=\{.*?\};'
    if re.search(themes_pattern, html, re.DOTALL):
        html = re.sub(themes_pattern, themes_js, html, flags=re.DOTALL)
        print("THEMES updated")
    else:
        print("WARNING: THEMES pattern not found in HTML")

    # 替换 WIKI 数据块
    wiki_pattern = r'const WIKI=\[.*?\];'
    if re.search(wiki_pattern, html, re.DOTALL):
        html = re.sub(wiki_pattern, wiki_js, html, flags=re.DOTALL)
        print("WIKI updated")
    else:
        print("WARNING: WIKI pattern not found in HTML")

    # 更新推文总数和日期
    html = re.sub(
        r'Stock Wiki — \d+ tickers researched',
        f'Stock Wiki — {total} tickers researched',
        html
    )
    html = re.sub(
        r'股票百科——\d+ 只研究过的股票',
        f'股票百科——{total} 只研究过的股票',
        html
    )
    html = re.sub(
        r'DISTILLED FROM [\d,]+ TWEETS',
        f'DISTILLED FROM {total:,} TWEETS',
        html
    )
    html = re.sub(
        r'从 [\d,]+ 条推文蒸馏',
        f'从 {total:,} 条推文蒸馏',
        html
    )

    HTML_FILE.write_text(html, encoding="utf-8")
    print(f"index.html updated ({len(html)} bytes)")


# ── 4. 主流程 ─────────────────────────────────────────────────

def main():
    if not DATA_FILE.exists():
        print(f"No data file found at {DATA_FILE}")
        return

    print("Loading tweets...")
    df    = pd.read_csv(DATA_FILE)
    stats = extract_stats(df)
    print(f"Her tweets: {stats['total']} ({stats['date_range']})")
    print(f"Top tickers: {[t for t,_ in stats['top_tickers'][:5]]}")

    update_skill(stats)
    update_html(stats)
    print("\nAll done!")


if __name__ == "__main__":
    main()
