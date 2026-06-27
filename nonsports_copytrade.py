"""
Polymarket Non-Sports Copytrade Finder
Ranks wallets by: high win rate × high ROI ÷ trades-per-day (lower = more selective).

Usage:
    python nonsports_copytrade.py

Covers politics, crypto, AI/tech, finance, science, and entertainment markets.
Excludes all sports markets.
"""

import requests
import time
import json
from collections import defaultdict
from datetime import datetime, timezone

BASE  = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

TOP_N         = 200   # wallets to score (from breadth ranking)
MIN_POSITIONS = 5     # require at least this many non-sports positions
MIN_WINS      = 2     # require at least this many wins
MAX_TPD       = 15    # exclude wallets trading more than this per day (bots)
MIN_WIN_RATE  = 30    # % — must win at least this often
TOP_RESULTS   = 20    # rows to print

# Used to exclude sports-related positions from a wallet's position history.
# Note: broad patterns like " vs " are intentionally excluded — they match
# non-sports titles ("Trump vs Biden") and would over-filter.
SPORTS_TITLE_KW = (
    "nba", "nfl", "nhl", "mlb", " ufc", " mma", " boxing",
    " soccer", " football", "basketball", " tennis ",
    " golf", " cricket", "rugby", "baseball", "ice hockey",
    "esport", "e-sport",
    "world cup", "fifa", "fifwc", "super bowl", "superbowl",
    "champions league", "premier league", "serie a", "la liga",
    "bundesliga", "eredivisie", "ligue 1",
    "formula 1", "formula one", "nascar", "motogp",
    "olympic", "wimbledon", "french open", "australian open",
    "stanley cup", "nba finals", "world series",
    "touchdowns", "yards rushing", "rushing yards",
    "home run", "strikeout", "batting average",
)

# Non-sports category slugs fetched dynamically; these seed the list
SEED_SLUGS = [
    # Politics / Elections
    "presidential-election-winner-2024",
    "democratic-presidential-nominee-2028",
    "republican-presidential-nominee-2028",
    "presidential-election-winner-2028",
    "next-president-to-serve-after-trump",
    "next-fed-chair",
    # Crypto
    "what-price-will-bitcoin-reach-in-2025",
    "what-price-will-ethereum-reach-in-2025",
    "will-bitcoin-reach-100k",
    "bitcoin-ath-in-2025",
    # AI / Tech
    "largest-company-end-of-june",
    "largest-company-end-of-april",
    "anthropic-new-claude-model",
    "openai-gpt-5",
    "which-companies-will-be-acquired-before-2027",
    # Finance / Economy
    "fed-decision-in-january",
    "fed-rate-cut-in-2025",
    "us-recession-in-2025",
    "us-gdp-growth-in-2025",
    # Geopolitics
    "russia-x-ukraine-ceasefire-in-2025",
    "russia-x-ukraine-ceasefire-by-end-of-2026",
    "strait-of-hormuz-traffic-returns-to-normal-by-end-of-may",
    # Entertainment / Culture
    "elon-musk-tweets-february-10-february-17-2026",
    "next-twitter-ceo",
    "will-elon-leave-doge",
]


def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
    return None


def is_sports(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in SPORTS_TITLE_KW)


def fetch_non_sports_cids(max_pages: int = 5, max_cids: int = 500) -> list:
    """Fetches condition IDs from the top non-sports events by volume.
    Markets are embedded in each event response — no second round-trip needed.
    Results are ordered by event volume so the most-traded markets come first.
    """
    cids = []
    seen_cids = set()

    print(f"[+] Fetching top non-sports events by volume ({max_pages} pages)...")
    for page in range(max_pages):
        if len(cids) >= max_cids:
            break
        data = get(f"{GAMMA}/events", params={
            "limit": 100,
            "offset": page * 100,
            "order": "volume",
            "ascending": "false",
        })
        if not data or not isinstance(data, list):
            break
        page_cids = 0
        for ev in data:
            if is_sports(ev.get("title", "")):
                continue
            # Limit markets per event to avoid swamping on 128-market events
            for m in ev.get("markets", [])[:20]:
                cid = m.get("conditionId")
                if cid and cid not in seen_cids:
                    cids.append(cid)
                    seen_cids.add(cid)
                    page_cids += 1
        print(f"    page {page+1}: +{page_cids} CIDs (total={len(cids)})")
        time.sleep(0.1)

    print(f"    {len(cids)} non-sports condition IDs collected")
    return cids[:max_cids]


def get_holders_flat(cid: str, limit: int = 100) -> list:
    data = get(f"{BASE}/holders", params={"market": cid, "limit": limit})
    if not data or not isinstance(data, list):
        return []
    flat = []
    for token_group in data:
        for h in token_group.get("holders", []):
            flat.append(h)
    return flat


def collect_wallets(cids: list) -> dict:
    """Returns {wallet: market_breadth} sorted descending."""
    counts = defaultdict(int)
    print(f"[+] Scanning {len(cids)} markets for non-sports traders...")
    for i, cid in enumerate(cids):
        seen = set()
        for h in get_holders_flat(cid, limit=100):
            w = (h.get("proxyWallet") or "").lower()
            if w and w not in seen:
                counts[w] += 1
                seen.add(w)
        if (i + 1) % 25 == 0:
            print(f"    {i+1}/{len(cids)} markets scanned...")
        time.sleep(0.08)
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def get_trades_per_day(wallet: str) -> float:
    """Estimates non-sports trades per day from recent activity."""
    data = get(f"{BASE}/activity", params={"user": wallet, "limit": 500})
    if not data or not isinstance(data, list):
        return 0.0
    trades = [a for a in data if a.get("type") == "TRADE" and not is_sports(a.get("title", ""))]
    if len(trades) < 2:
        return len(trades) or 0.0
    timestamps = [a["timestamp"] for a in trades if "timestamp" in a]
    if not timestamps:
        return 0.0
    earliest = min(timestamps)
    latest   = max(timestamps)
    days = max(1, (latest - earliest) / 86400)
    return round(len(trades) / days, 2)


def score_wallet(wallet: str) -> dict | None:
    positions = get(
        f"{BASE}/positions",
        params={"user": wallet, "sizeThreshold": "0", "limit": "500"},
    )
    if not positions or not isinstance(positions, list):
        return None

    # Keep only non-sports positions
    fp = [p for p in positions if not is_sports(p.get("title", ""))]
    if len(fp) < MIN_POSITIONS:
        return None

    # Skip LP bots
    if any(float(p.get("currentValue", 0)) > 2_000_000 for p in fp):
        return None

    net   = sum(float(p.get("cashPnl", 0)) for p in fp)
    wins  = sum(1 for p in fp if float(p.get("cashPnl", 0)) > 0)
    total = len(fp)
    wr    = wins / total if total else 0
    init  = sum(abs(float(p.get("initialValue", 0))) for p in fp)
    roi   = (net / init * 100) if init > 0 else 0
    best  = max((float(p.get("cashPnl", 0)) for p in fp), default=0)

    if wins < MIN_WINS or wr * 100 < MIN_WIN_RATE or net <= 0:
        return None

    name = ""
    for p in fp:
        n = p.get("name") or p.get("pseudonym") or ""
        if n:
            name = n
            break

    return {
        "wallet":    wallet,
        "username":  name,
        "positions": total,
        "wins":      wins,
        "losses":    total - wins,
        "win_rate":  round(wr * 100, 1),
        "net_pnl":   round(net, 2),
        "wagered":   round(init, 2),
        "roi_pct":   round(roi, 2),
        "best_win":  round(best, 2),
        "url":       f"https://polymarket.com/profile/{wallet}",
    }


def composite(r: dict, tpd: float) -> float:
    """Reward high win rate × high ROI, penalise frequent trading."""
    tpd = tpd or 0.01
    if tpd > MAX_TPD:
        return -1  # exclude bots
    wr  = r["win_rate"] / 100
    roi = r["roi_pct"]  # percentage points
    return (wr * roi) / (tpd + 0.5)


def main():
    print("=" * 66)
    print("  Polymarket Non-Sports — High Win-Rate / Low-Frequency Finder")
    print("=" * 66)

    cids    = fetch_non_sports_cids(max_pages=4, max_cids=500)
    wallets = collect_wallets(cids)
    top_w   = list(wallets.keys())[:TOP_N]

    print(f"\n[+] Scoring top {len(top_w)} wallets...")

    results = []
    for i, w in enumerate(top_w):
        sc = score_wallet(w)
        if sc:
            tpd = get_trades_per_day(w)
            sc["tpd"] = tpd
            if composite(sc, tpd) > 0:
                results.append(sc)
        if (i + 1) % 25 == 0:
            print(f"    {i+1}/{len(top_w)} scored...")
        time.sleep(0.15)

    results.sort(key=lambda r: composite(r, r["tpd"]), reverse=True)
    top = results[:TOP_RESULTS]

    hdr = (f"{'#':<4} {'Username':<22} {'Wallet':<44} {'Pos':>5} {'W/L':>7} "
           f"{'WR%':>5} {'Net P&L':>12} {'ROI':>7} {'Trd/Day':>8} {'Best Win':>11}")
    print("\n" + "=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(top, 1):
        name    = (r["username"] or r["wallet"][:10] + "…")[:21]
        wl      = f"{r['wins']}/{r['losses']}"
        pnl_str = f"${r['net_pnl']:>+,.2f}"
        best_s  = f"${r['best_win']:>+,.2f}"
        print(
            f"{i:<4} {name:<22} {r['wallet']:<44} {r['positions']:>5} "
            f"{wl:>7} {r['win_rate']:>4.0f}% {pnl_str:>12} {r['roi_pct']:>+6.1f}% "
            f"{r['tpd']:>8.2f} {best_s:>11}"
        )
    print("=" * len(hdr))

    print("\nPolymarket profiles (top 10):")
    for r in top[:10]:
        name = r["username"] or r["wallet"][:14] + "…"
        print(f"  {name:<30}  {r['url']}  (WR={r['win_rate']}%, ROI={r['roi_pct']:+.1f}%, {r['tpd']:.2f} trades/day)")

    return top


if __name__ == "__main__":
    main()
