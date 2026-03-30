#!/usr/bin/env python3
import os
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urljoin

LARK_WEBHOOK_URL = os.environ["LARK_WEBHOOK_URL"]

SOURCES = [
    {
        "name": "ロジスティクス業界紙",
        "rss": "https://online.logi-biz.com/feed/",
        "site": "https://online.logi-biz.com/",
    },
    {
        "name": "物流Today",
        "rss": "https://www.logi-today.com/feed/",
        "site": "https://www.logi-today.com/",
    },
    {
        "name": "日本ロジスティクスシステム協会",
        "rss": None,
        "site": "https://www1.logistics.or.jp/news/",
    },
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LogiNewsBot/1.0)"}
MAX_ARTICLES = 30


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
        results[src["name"]] = articles[:10]
        print(f"  {src['name']}: {len(results[src['name']])} 件")
    return results


def build_message(grouped):
    today = datetime.now().strftime("%Y年%m月%d日")
    lines = [f"📦 Weekly Logi News｜{today}（月）", ""]
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
    print("取得中...")
    grouped = fetch_all()
    message = build_message(grouped)
    print("\n--- プレビュー ---")
    print(message[:400])
    print("---")
    send_to_lark(message)
    print("配信完了!")


if __name__ == "__main__":
    main()
