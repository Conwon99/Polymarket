"""
Polymarket Weather Niche — Copytrade Leaderboard
Finds wallets that correctly predicted the winning temperature range
across multiple resolved weather events (Jun 23–27, 2026).

Ranks by: correct predictions across most distinct city/date events.
Excludes LP bots (present in every single market of an event).

Usage:
    python weather_copytrade.py
"""

import requests
import time
import json
from collections import defaultdict

BASE  = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

CITIES = [
    "london", "paris", "nyc", "hong-kong", "munich", "madrid",
    "amsterdam", "istanbul", "miami", "los-angeles", "atlanta",
    "sao-paulo", "helsinki", "warsaw", "ankara", "moscow", "jeddah",
    "seoul", "tokyo", "singapore", "chicago", "toronto", "buenos-aires",
    "dubai", "berlin",
]

PAST_DATES = [
    "june-23-2026", "june-24-2026", "june-25-2026",
    "june-26-2026", "june-27-2026",
]

MIN_CORRECT  = 3    # minimum correct predictions to appear in leaderboard
TOP_RESULTS  = 20
BOT_THRESHOLD = 15  # wallets present in ≥ this many markets of same event = LP bot


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


def parse_prices(raw):
    if isinstance(raw, str):
        return json.loads(raw)
    return raw or []


def find_winning_cids() -> list:
    """For each closed weather event, return (event_title, winning_conditionId, total_markets_in_event)."""
    results = []
    print(f"[+] Scanning {len(CITIES) * len(PAST_DATES)} city/date combos for resolved weather events...")
    for city in CITIES:
        for date in PAST_DATES:
            slug = f"highest-temperature-in-{city}-on-{date}"
            data = get(f"{GAMMA}/events", params={"slug": slug})
            if not data:
                continue
            ev = data[0] if isinstance(data, list) else data
            if not ev.get("closed"):
                continue
            markets = ev.get("markets", [])
            total = len(markets)
            for m in markets:
                op = parse_prices(m.get("outcomePrices"))
                cid = m.get("conditionId")
                if op and str(op[0]) == "1" and cid:
                    results.append((ev["title"], cid, total))
                    break   # only one winner per event
            time.sleep(0.05)
    print(f"    Found {len(results)} resolved winning markets")
    return results


def get_yes_holders(cid: str, limit: int = 200) -> list:
    """Returns list of proxyWallet addresses that held YES in this market."""
    data = get(f"{BASE}/holders", params={"market": cid, "limit": limit})
    if not data or not isinstance(data, list):
        return []
    # First token group = YES token
    yes_group = data[0] if data else {}
    return [
        (h.get("proxyWallet") or "").lower()
        for h in yes_group.get("holders", [])
        if h.get("proxyWallet")
    ]


def main():
    print("=" * 62)
    print("  Polymarket Weather Niche — Copytrade Leaderboard")
    print("=" * 62)

    winning_markets = find_winning_cids()
    if not winning_markets:
        print("No resolved weather markets found.")
        return []

    # wallet → set of event titles they correctly predicted
    correct_events: dict[str, set] = defaultdict(set)
    # wallet → number of total distinct markets they appear in (for bot detection)
    market_count: dict[str, int] = defaultdict(int)

    print(f"\n[+] Fetching YES holders for {len(winning_markets)} winning markets...")
    for i, (event_title, cid, total_mkts) in enumerate(winning_markets):
        holders = get_yes_holders(cid, limit=200)
        for w in holders:
            correct_events[w].add(event_title)
            market_count[w] += 1
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(winning_markets)} markets processed...")
        time.sleep(0.08)

    # Build leaderboard
    rows = []
    for wallet, events in correct_events.items():
        n_correct = len(events)
        if n_correct < MIN_CORRECT:
            continue
        # Exclude LP bots: present in suspiciously many winning markets
        if market_count[wallet] >= BOT_THRESHOLD:
            continue
        rows.append({
            "wallet":   wallet,
            "correct":  n_correct,
            "url":      f"https://polymarket.com/profile/{wallet}",
        })

    rows.sort(key=lambda r: r["correct"], reverse=True)
    top = rows[:TOP_RESULTS]

    # Enrich with usernames from activity API
    print(f"\n[+] Enriching {len(top)} wallets with usernames...")
    for r in top:
        data = get(f"{BASE}/activity", params={"user": r["wallet"], "limit": 5})
        name = ""
        if data and isinstance(data, list):
            for a in data:
                name = a.get("name") or a.get("pseudonym") or ""
                if name:
                    break
        r["username"] = name
        time.sleep(0.1)

    total_events = len(winning_markets)
    hdr = f"{'#':<4} {'Username':<24} {'Wallet':<44} {'Correct':>8} {'/ Total':>8}"
    print("\n" + "=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(top, 1):
        name = (r["username"] or r["wallet"][:12] + "…")[:23]
        print(f"{i:<4} {name:<24} {r['wallet']:<44} {r['correct']:>8} {'/ ' + str(total_events):>8}")
    print("=" * len(hdr))

    print(f"\nPolymarket profiles (top {min(10, len(top))}):")
    for r in top[:10]:
        name = r["username"] or r["wallet"][:16] + "…"
        print(f"  {name:<30}  {r['url']}  ({r['correct']}/{total_events} correct)")

    return top


if __name__ == "__main__":
    main()
