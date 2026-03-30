#!/usr/bin/env python3
import os
import json
import requests
- cron: '0 0 * * *'  # 毎日 00:00 UTC = 09:00 JST
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import anthropic

LARK_WEBHOOK_URL = os.environ["LARK_WEBHOOK_URL"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

SOURCES = [
    {"name": "ロジスティクス業界紙", "rss": "https://online.logi-biz.com/feed/", "site": "https://online.logi-biz.com/"},
    {"name": "物流Today", "rss": "https://www.logi-today.com/feed/", "site": "https://www.logi-today.com/"},
    {"name": "日本ロジスティクスシステム協会", "rss": None, "site": "https://www1.logistics.or.jp/news/"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LogiNewsBot/1.0)"}
MAX_ARTICLES = 45


def fetch_rss(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        articles = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            if title and link:
                articles.append({"title": title, "url": link})
        return articles
    except Exception as e:
        print(f"RSS取得失敗 ({url}): {e}")
        return []


def fetch_html(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html.parser")
        articles = []
        seen = set()
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            href = a["href"]
            if len(text) < 10:
                continue
            if not href.startswith("http"):
                href = urljoin(url, href)
            if href in seen or url not in href:
                continue
            seen.add(href)
            articles.append({"title": text, "url": href})
            if len(articles) >= 15:
                break
        return articles
    except Exception as e:
        print(f"HTML取得失敗 ({url}): {e}")
        return []


def fetch_all():
    results = {}
    for src in SOURCES:
        articles = []
        if src["rss"]:
            articles = fetch_rss(src["rss"])
        if not articles:
            articles = fetch_html(src["site"])
        results[src["name"]] = articles[:15]
        print(f"  {src['name']}: {len(results[src['name']])} 件")
    return results


def filter_by_ai(grouped):
    all_articles = []
    for source, articles in grouped.items():
        for a in articles:
            all_articles.append({"source": source, **a})

    if not all_articles:
        return grouped

    titles_text = "\n".join(f"{i}. {a['title']}" for i, a in enumerate(all_articles))

    prompt = f"""以下は物流ニュースサイトから取得した記事タイトルの一覧です。

【選定基準】次のトピックに関連する記事を選んでください：
- スタートアップ・新技術・新サービス・イノベーション
- Amazon・大手EC・eコマース関連
- ヤマト運輸・佐川急便・日本郵便・DHL・フェデックスなど知名度の高い企業の動向
- 物流法令・規制・2024年問題・2026年問題
- 倉庫管理・庫内効率化・自動化・ロボット・AI・DX
- 物流業界の重要な動向・M&A・業界再編・市場トレンド

【記事一覧】
{titles_text}

関連性が高い記事の番号を、JSON配列で返してください。例: [0, 2, 5, 8]
番号のみ返し、説明は不要です。"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        indices = set(json.loads(text[start:end]))
        print(f"  AI選定: {len(indices)} 件 / {len(all_articles)} 件")
    except Exception as e:
        print(f"  AI判定失敗（全件使用）: {e}")
        indices = set(range(len(all_articles)))

    filtered = {src["name"]: [] for src in SOURCES}
    for i, a in enumerate(all_articles):
        if i in indices:
            filtered[a["source"]].append({"title": a["title"], "url": a["url"]})

    return filtered


def build_message(grouped):
    today = datetime.now().strftime("%Y年%m月%d日")
    lines = [f"📦 物流週報｜{today}（月）", ""]
    count = 1
    for source, articles in grouped.items():
        if not articles:
            continue
        lines.append(f"【{source}】")
        for a in articles:
            lines.append(f"{count}. {a['title']}")
            lines.append(f"   {a['url']}")
            count += 1
            if count > MAX_ARTICLES:
                break
        lines.append("")
        if count > MAX_ARTICLES:
            break
    lines.append(f"計 {count - 1} 件")
    return "\n".join(lines)


def send_to_lark(message):
    payload = {"msg_type": "text", "content": {"text": message}}
    r = requests.post(LARK_WEBHOOK_URL, json=payload, timeout=10)
    r.raise_for_status()
    result = r.json()
    print(f"Lark応答: {result}")
    if result.get("code") != 0:
        raise Exception(f"Larkエラー: {result}")


def main():
    print("物流ニュース取得中...")
    grouped = fetch_all()
    print("AI関連度判定中...")
    grouped = filter_by_ai(grouped)
    message = build_message(grouped)
    print("\n--- プレビュー ---")
    print(message[:400])
    print("---")
    send_to_lark(message)
    print("配信完了!")


if __name__ == "__main__":
    main()
