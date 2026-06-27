"""
Polymarket FIFA World Cup 2026 — Correct-Streak Finder
Identifies wallets that correctly predicted the most recent group-stage matches.

Usage:
    python worldcup_streaks.py

For each recently resolved match, queries the YES-token holders on the winning
outcome, then ranks wallets by how many consecutive / recent matches they got right.
"""

import requests
import time
import json
from collections import defaultdict

BASE  = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

# LP-bot threshold: if a wallet holds YES in this many winning markets it's an AMM
LP_THRESHOLD = 15

# Minimum correct predictions to appear in the leaderboard
MIN_CORRECT = 3

# How many wallets to show in the final table
TOP_N = 20


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


def get_winning_condition_ids(event_ids: list) -> list:
    """Returns list of (date, label, conditionId) for each resolved winning outcome."""
    results = []
    print(f"[+] Resolving winning outcomes for {len(event_ids)} events...")
    for eid in event_ids:
        data = get(f"{GAMMA}/events/{eid}")
        if not data:
            continue
        title  = data.get("title", "?")
        end_dt = (data.get("endDate", "") or "")[:10]
        for m in data.get("markets", []):
            op       = parse_prices(m.get("outcomePrices"))
            outcomes = m.get("outcomes", [])
            cid      = m.get("conditionId", "")
            question = m.get("question", "")
            # YES (index 0) resolved to 1 means YES won
            if op and str(op[0]) == "1" and cid:
                winning_outcome = outcomes[0] if outcomes else "Yes"
                results.append({
                    "event_id": eid,
                    "date":     end_dt,
                    "title":    title,
                    "question": question,
                    "outcome":  winning_outcome,
                    "cid":      cid,
                })
        time.sleep(0.1)
    print(f"    Found {len(results)} winning markets across {len(event_ids)} events")
    return results


def get_yes_holders(cid: str, limit: int = 200) -> list:
    """Returns flat list of {proxyWallet, name} dicts for the YES token holders."""
    data = get(f"{BASE}/holders", params={"market": cid, "limit": limit})
    if not data or not isinstance(data, list):
        return []
    flat = []
    for token_group in data:
        for h in token_group.get("holders", []):
            w = (h.get("proxyWallet") or "").lower()
            if w:
                flat.append({
                    "wallet": w,
                    "name":   h.get("name") or h.get("pseudonym") or "",
                })
    return flat


def build_streak_table(winning_markets: list) -> list:
    """Returns list of {wallet, name, correct, matches} sorted by correct desc."""
    wallet_correct = defaultdict(list)
    wallet_names   = {}

    print(f"[+] Fetching YES holders for {len(winning_markets)} winning markets...")
    for i, m in enumerate(winning_markets):
        label = f"{m['date'][:7][5:]} {m['title'][:30]}"
        for h in get_yes_holders(m["cid"]):
            w = h["wallet"]
            wallet_correct[w].append({"date": m["date"], "label": m["title"][:40]})
            if h["name"] and w not in wallet_names:
                wallet_names[w] = h["name"]
        if (i + 1) % 6 == 0:
            print(f"    {i+1}/{len(winning_markets)} markets processed...")
        time.sleep(0.12)

    # Filter LP bots and require minimum correct count
    rows = []
    for wallet, matches in wallet_correct.items():
        if len(matches) >= LP_THRESHOLD:
            continue
        if len(matches) < MIN_CORRECT:
            continue
        rows.append({
            "wallet":  wallet,
            "name":    wallet_names.get(wallet, ""),
            "correct": len(matches),
            "matches": matches,
        })
    rows.sort(key=lambda r: -r["correct"])
    return rows


def main():
    print("=" * 66)
    print("  Polymarket WC 2026 — Recent Match Prediction Streak Finder")
    print("=" * 66)

    # Group-stage event IDs covering Jun 21–26, 2026
    # Each event corresponds to one match
    event_ids = [
        351771, 351772, 351773, 351774, 351775, 351776,  # Jun 25–26
        351761, 351762, 351763, 351764, 351765, 351766,  # Jun 23–24
        351750, 351751, 351752, 351753, 351754, 351755,  # Jun 21–22
    ]

    winning_markets = get_winning_condition_ids(event_ids)
    if not winning_markets:
        print("No resolved markets found. Try again later.")
        return []

    print("\nResolved matches:")
    for m in winning_markets:
        print(f"  [{m['date']}] {m['title']:<45}  → {m['question'][:55]}")

    rows = build_streak_table(winning_markets)
    total_matches = len(winning_markets)

    print(f"\n[+] {len(rows)} human traders with {MIN_CORRECT}+ correct predictions (out of {total_matches} matches)\n")

    hdr = f"{'#':<4} {'Username':<22} {'Wallet':<44} {'✓/Total':>8}  Recent correct calls"
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(rows[:TOP_N], 1):
        name       = (r["name"] or r["wallet"][:10] + "…")[:21]
        score_str  = f"{r['correct']}/{total_matches}"
        call_str   = " | ".join(m["label"][:22] for m in r["matches"][:5])
        print(f"{i:<4} {name:<22} {r['wallet']:<44} {score_str:>8}  {call_str}")
    print("=" * len(hdr))

    print("\nPolymarket profiles (top 10):")
    for r in rows[:10]:
        name = r["name"] or r["wallet"][:14] + "…"
        print(f"  {name:<30}  https://polymarket.com/profile/{r['wallet']}  ({r['correct']}/{total_matches} correct)")

    return rows


if __name__ == "__main__":
    main()
