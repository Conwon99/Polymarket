"""
Polymarket Weather Niche Copytrade Finder
Finds the best wallets to copytrade in Polymarket's weather prediction markets.

Usage:
    python weather_copytrade.py

Outputs a ranked table of weather traders by net P&L, win rate, and market breadth.
"""

import requests
import time
from collections import defaultdict

BASE = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

WEATHER_KEYWORDS = (
    "temperature", "celsius", "fahrenheit", "rain", "snow",
    "hurricane", "storm", "wind", "humidity", "weather",
    "highest temp", "lowest temp", "°c", "°f",
    "highest temperature", "degrees",
)

WEATHER_EVENT_SLUGS = [
    "highest-temperature-in-london-on-june-23-2026",
    "highest-temperature-in-paris-on-june-23-2026",
    "highest-temperature-in-nyc-on-june-23-2026",
    "highest-temperature-in-hong-kong-on-june-23-2026",
    "highest-temperature-in-munich-on-june-23-2026",
    "highest-temperature-in-madrid-on-june-23-2026",
    "highest-temperature-in-amsterdam-on-june-23-2026",
    "highest-temperature-in-istanbul-on-june-23-2026",
    "highest-temperature-in-miami-on-june-23-2026",
    "highest-temperature-in-los-angeles-on-june-23-2026",
    "highest-temperature-in-atlanta-on-june-23-2026",
    "highest-temperature-in-sao-paulo-on-june-23-2026",
    "highest-temperature-in-helsinki-on-june-23-2026",
    "highest-temperature-in-warsaw-on-june-23-2026",
    "highest-temperature-in-ankara-on-june-23-2026",
    "highest-temperature-in-moscow-on-june-23-2026",
    "highest-temperature-in-jeddah-on-june-23-2026",
    "highest-temperature-in-london-on-june-24-2026",
    "highest-temperature-in-hong-kong-on-june-24-2026",
    "highest-temperature-in-seoul-on-june-24-2026",
]

# Score only top N wallets by breadth — keeps runtime under 3 min
TOP_N = 150


def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1.5 ** attempt)


def is_weather_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in WEATHER_KEYWORDS)


def get_condition_ids_for_events(slugs: list) -> list:
    condition_ids = []
    print(f"[+] Fetching condition IDs for {len(slugs)} weather events...")
    for slug in slugs:
        data = get(f"{GAMMA}/events", params={"slug": slug})
        if not data:
            continue
        events = data if isinstance(data, list) else [data]
        for event in events:
            for m in event.get("markets", []):
                cid = m.get("conditionId")
                if cid:
                    condition_ids.append(cid)
        time.sleep(0.1)
    print(f"    Found {len(condition_ids)} condition IDs")
    return condition_ids


def get_holders_flat(condition_id: str, limit: int = 50) -> list:
    """Returns flat list of holder dicts for a conditionId.
    API returns [{token, holders:[{proxyWallet,...}]}, ...] per YES/NO token.
    """
    data = get(f"{BASE}/holders", params={"market": condition_id, "limit": limit})
    if not data or not isinstance(data, list):
        return []
    flat = []
    for token_group in data:
        for h in token_group.get("holders", []):
            flat.append(h)
    return flat


def collect_weather_wallets(condition_ids: list) -> dict:
    """Returns {wallet: market_count} sorted descending."""
    wallet_count = defaultdict(int)
    print(f"[+] Scanning {len(condition_ids)} markets for weather traders...")
    for i, cid in enumerate(condition_ids):
        seen = set()
        for h in get_holders_flat(cid, limit=50):
            w = (h.get("proxyWallet") or "").lower()
            if w and w not in seen:
                wallet_count[w] += 1
                seen.add(w)
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(condition_ids)} markets scanned")
        time.sleep(0.1)
    return dict(sorted(wallet_count.items(), key=lambda x: -x[1]))


def score_wallet(wallet: str) -> dict | None:
    positions = get(
        f"{BASE}/positions",
        params={"user": wallet, "sizeThreshold": "0", "limit": "500"},
    )
    if not positions or not isinstance(positions, list):
        return None

    wp = [p for p in positions if is_weather_title(p.get("title", ""))]
    if not wp:
        return None

    # Skip liquidity providers (many positions with identically huge values & 0% P&L)
    vals = [float(p.get("currentValue", 0)) for p in wp]
    if vals and max(vals) > 500_000:
        return None

    net_pnl = sum(float(p.get("cashPnl", 0)) for p in wp)
    wins  = sum(1 for p in wp if float(p.get("cashPnl", 0)) > 0)
    total = len(wp)
    win_rate = wins / total if total else 0
    initial = sum(abs(float(p.get("initialValue", 0))) for p in wp)
    roi = (net_pnl / initial * 100) if initial > 0 else 0

    # Largest single win gives signal of real knowledge
    best_pnl = max((float(p.get("cashPnl", 0)) for p in wp), default=0)

    name = ""
    for p in wp:
        n = p.get("name") or p.get("pseudonym") or ""
        if n:
            name = n
            break

    return {
        "wallet": wallet,
        "username": name,
        "weather_markets": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round(win_rate * 100, 1),
        "net_pnl": round(net_pnl, 2),
        "total_wagered": round(initial, 2),
        "roi_pct": round(roi, 2),
        "best_single_pnl": round(best_pnl, 2),
        "url": f"https://polymarket.com/profile/{wallet}",
    }


def composite(r: dict, breadth: int) -> float:
    """Rank: reward profitable, wide, high-win-rate traders."""
    wagered = r["total_wagered"] or 1
    roi_norm = r["net_pnl"] / wagered
    wr = r["win_rate"] / 100
    return roi_norm * wr * breadth


def main():
    print("=" * 62)
    print("  Polymarket Weather Niche — Copytrade Leaderboard")
    print("=" * 62)

    condition_ids = get_condition_ids_for_events(WEATHER_EVENT_SLUGS)
    wallet_counts = collect_weather_wallets(condition_ids)

    # Limit to top N by market breadth to keep runtime fast
    top_wallets = list(wallet_counts.keys())[:TOP_N]
    print(f"\n[+] Scoring top {len(top_wallets)} wallets by weather P&L...")

    results = []
    for i, wallet in enumerate(top_wallets):
        score = score_wallet(wallet)
        if score:
            score["breadth"] = wallet_counts[wallet]
            results.append(score)
        if (i + 1) % 25 == 0:
            print(f"    {i+1}/{len(top_wallets)} scored so far...")
        time.sleep(0.12)

    results.sort(key=lambda r: composite(r, r["breadth"]), reverse=True)

    top = results[:15]
    hdr = f"{'#':<4} {'Username':<22} {'Wallet':<44} {'Mkt':>4} {'W/L':>7} {'WR%':>5} {'Net P&L':>10} {'ROI':>7}"
    print("\n" + "=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(top, 1):
        name = (r["username"] or r["wallet"][:10] + "…")[:21]
        wl = f"{r['wins']}/{r['losses']}"
        print(
            f"{i:<4} {name:<22} {r['wallet']:<44} {r['weather_markets']:>4} "
            f"{wl:>7} {r['win_rate']:>4.0f}% {r['net_pnl']:>+10.2f} {r['roi_pct']:>+6.1f}%"
        )
    print("=" * len(hdr))

    print("\nProfile links:")
    for r in top[:8]:
        name = r["username"] or r["wallet"][:14] + "…"
        print(f"  {name:<28}  {r['url']}")

    return top


if __name__ == "__main__":
    main()
