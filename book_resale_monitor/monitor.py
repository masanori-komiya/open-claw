import json
import math
import statistics
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


@dataclass
class Listing:
    source: str
    title: str
    price: int
    url: str


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_config() -> Dict[str, Any]:
    with open(ROOT / "config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def headers(cfg: Dict[str, Any]) -> Dict[str, str]:
    return {"User-Agent": cfg["user_agent"], "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}


def normalize_price(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def fetch_html(url: str, cfg: Dict[str, Any]) -> str:
    use_playwright = cfg.get("use_playwright", True)
    if use_playwright and sync_playwright is not None:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=cfg["user_agent"],
                    locale="ja-JP",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1500)
                html = page.content()
                context.close()
                browser.close()
                return html
        except Exception:
            pass

    r = requests.get(url, headers=headers(cfg), timeout=25)
    r.raise_for_status()
    return r.text


def scrape_mercari(keyword: str, cfg: Dict[str, Any]) -> List[Listing]:
    url = f"https://jp.mercari.com/search?keyword={urllib.parse.quote(keyword)}"
    html = fetch_html(url, cfg)

    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return []

    payload = json.loads(script.string)
    found: List[Listing] = []

    def walk(node: Any):
        if isinstance(node, dict):
            keys = node.keys()
            if ("name" in keys or "title" in keys) and ("price" in keys or "priceDisplay" in keys):
                title = str(node.get("name") or node.get("title") or "").strip()
                price = normalize_price(node.get("price") or node.get("priceDisplay"))
                item_id = node.get("id") or node.get("itemId")
                item_url = node.get("url")
                if not item_url and item_id:
                    item_url = f"https://jp.mercari.com/item/{item_id}"
                if title and price > 0 and item_url:
                    found.append(Listing("mercari", title, price, item_url))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(payload)

    unique = {}
    for item in found:
        unique[item.url] = item

    return list(unique.values())[: cfg["max_items_per_source"]]


def scrape_yahoo_auctions(keyword: str, cfg: Dict[str, Any]) -> List[Listing]:
    url = f"https://auctions.yahoo.co.jp/search/search?p={urllib.parse.quote(keyword)}"
    try:
        html = fetch_html(url, cfg)
    except requests.HTTPError as e:
        if "404" in str(e):
            return []
        raise

    soup = BeautifulSoup(html, "html.parser")
    listings: List[Listing] = []

    for a in soup.select("a.Product__titleLink, a.Product__title"):
        title = a.get_text(strip=True)
        href = a.get("href")
        root = a.find_parent()
        if not root:
            continue

        price_text = ""
        price_el = root.select_one(".Product__priceValue, .Product__price")
        if price_el:
            price_text = price_el.get_text(" ", strip=True)
        price = normalize_price(price_text)

        if title and href and price > 0:
            listings.append(Listing("yahoo_auctions", title, price, href))

    if not listings:
        for li in soup.select("li.Product"):
            a = li.select_one("a")
            price_el = li.select_one(".Product__price")
            if not a or not price_el:
                continue
            title = a.get_text(strip=True)
            href = a.get("href")
            price = normalize_price(price_el.get_text(" ", strip=True))
            if title and href and price > 0:
                listings.append(Listing("yahoo_auctions", title, price, href))

    return listings[: cfg["max_items_per_source"]]


def fetch_source(source: str, keyword: str, cfg: Dict[str, Any]) -> List[Listing]:
    if source == "mercari":
        return scrape_mercari(keyword, cfg)
    if source == "yahoo_auctions":
        return scrape_yahoo_auctions(keyword, cfg)
    return []


def estimate_sell_price(listings: List[Listing], buy_source: str) -> int:
    other_prices = [x.price for x in listings if x.source != buy_source]
    if len(other_prices) >= 3:
        return int(statistics.median(other_prices))
    if other_prices:
        return int(sum(other_prices) / len(other_prices))
    return 0


def analyze_keyword(keyword: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    all_items: List[Listing] = []
    errors: List[str] = []

    for source in cfg["sources"]:
        try:
            items = fetch_source(source, keyword, cfg)
            all_items.extend(items)
        except Exception as e:
            errors.append(f"{source}: {e}")

    if not all_items:
        return {"keyword": keyword, "candidates": [], "errors": errors}

    cheapest = min(all_items, key=lambda x: x.price)
    expected_sell = estimate_sell_price(all_items, cheapest.source)

    if expected_sell <= 0:
        return {"keyword": keyword, "candidates": [], "errors": errors}

    fee = math.floor(expected_sell * cfg["marketplace_fee_rate"])
    profit = expected_sell - fee - cfg["shipping_yen"] - cheapest.price
    rate = profit / cheapest.price if cheapest.price else -1

    candidate = {
        "keyword": keyword,
        "buy": asdict(cheapest),
        "expected_sell_yen": expected_sell,
        "estimated_fee_yen": fee,
        "shipping_yen": cfg["shipping_yen"],
        "profit_yen": profit,
        "profit_rate": round(rate, 4),
    }

    ok = profit >= cfg["min_profit_yen"] and rate >= cfg["min_profit_rate"]
    return {"keyword": keyword, "candidates": [candidate] if ok else [], "errors": errors}


def main() -> None:
    cfg = load_config()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = [analyze_keyword(k, cfg) for k in cfg["keywords"]]
    candidates = [c for r in results for c in r["candidates"]]
    errors = [e for r in results for e in r["errors"]]

    payload = {
        "generated_at": ts,
        "thresholds": {
            "min_profit_yen": cfg["min_profit_yen"],
            "min_profit_rate": cfg["min_profit_rate"],
        },
        "candidates_count": len(candidates),
        "candidates": sorted(candidates, key=lambda x: x["profit_yen"], reverse=True),
        "errors": errors,
    }

    json_path = OUTPUT_DIR / "latest.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = [
        f"# 学術書転売候補レポート ({ts})",
        "",
        f"- 最低利益額: {cfg['min_profit_yen']}円",
        f"- 最低利益率: {int(cfg['min_profit_rate'] * 100)}%",
        f"- 候補件数: {len(candidates)}",
        "",
    ]

    for c in payload["candidates"][:20]:
        lines += [
            f"## {c['keyword']}",
            f"- 仕入れ: {c['buy']['source']} / {c['buy']['price']}円",
            f"- 予想売値: {c['expected_sell_yen']}円",
            f"- 見込み利益: {c['profit_yen']}円 ({round(c['profit_rate']*100,1)}%)",
            f"- タイトル: {c['buy']['title']}",
            f"- URL: {c['buy']['url']}",
            "",
        ]

    if errors:
        lines += ["## 取得エラー", ""] + [f"- {e}" for e in errors]

    md_path = OUTPUT_DIR / "latest.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated: {json_path}")
    print(f"Generated: {md_path}")


if __name__ == "__main__":
    main()
