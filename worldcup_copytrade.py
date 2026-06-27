"""
Polymarket FIFA World Cup 2026 Copytrade Finder
Identifies the best wallets to copytrade for World Cup prediction markets.

Usage:
    python worldcup_copytrade.py

Scans winner markets + group-stage match markets, finds consistent traders,
and ranks them by composite score: ROI × win_rate × market_breadth.
"""

import requests
import time
from collections import defaultdict

BASE  = "https://data-api.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

# World Cup event slugs: tournament-level + match-level
# Match slug pattern: fifwc-{team1}-{team2}-{date}[-{variant}]
WC_EVENT_SLUGS = [
    # Tournament outright markets
    "world-cup-winner",
    "world-cup-nation-to-reach-final",
    "world-cup-nation-to-reach-quarterfinals",
    "world-cup-team-to-advance-to-knockout-stages",
    "world-cup-golden-boot-winner",

    # Group-stage matches (June 12-27)
    "fifwc-esp-cpv-2026-06-15",          # Spain vs Cabo Verde
    "fifwc-tur-par-2026-06-19",          # Türkiye vs Paraguay
    "fifwc-cze-rsa-2026-06-18",          # Czechia vs South Africa
    "fifwc-irn-cze-2026-06-15",          # Iran vs Czechia
    "fifwc-col-prt-2026-06-27",          # Colombia vs Portugal
    "fifwc-pan-eng-2026-06-27",          # Panama vs England
    "fifwc-jor-arg-2026-06-27",          # Jordan vs Argentina
    "fifwc-hrv-gha-2026-06-27",          # Croatia vs Ghana
    "fifwc-alg-aut-2026-06-27",          # Algeria vs Austria
    "fifwc-cdr-uzb-2026-06-27",          # DR Congo vs Uzbekistan
    "fifwc-bra-jpn-2026-06-29",          # Brazil vs Japan
    "fifwc-rsa-can-2026-06-28",          # South Africa vs Canada
    "fifwc-nld-mar-2026-06-29",          # Netherlands vs Morocco
    "fifwc-fra-bel-2026-06-22",          # France vs Belgium
    "fifwc-arg-mex-2026-06-22",          # Argentina vs Mexico
    "fifwc-eng-tun-2026-06-18",          # England vs Tunisia
    "fifwc-ger-jpn-2026-06-16",          # Germany vs Japan
    "fifwc-bra-cri-2026-06-14",          # Brazil vs Costa Rica
    "fifwc-prt-usa-2026-06-17",          # Portugal vs USA
    "fifwc-esp-mar-2026-06-21",          # Spain vs Morocco
    "fifwc-ned-ecu-2026-06-16",          # Netherlands vs Ecuador

    # Spread / handicap variants (high volume)
    "fifwc-esp-cpv-2026-06-15-spread",
    "fifwc-col-prt-2026-06-27-spread",
    "fifwc-pan-eng-2026-06-27-spread",
    "fifwc-jor-arg-2026-06-27-spread",
]

FOOTBALL_KEYWORDS = (
    "will ", " win", " draw", "world cup", "fifa", "fifwc",
    "advance", "knockout", "qualify", "group", "final", "quarter",
    "golden boot", "score", "spread", "goal",
)

TOP_N = 200  # wallets to score


def get(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 ** attempt)
    return None


def is_football_title(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in FOOTBALL_KEYWORDS)


def get_condition_ids(slugs: list) -> list:
    cids = []
    print(f"[+] Resolving condition IDs for {len(slugs)} events...")
    for slug in slugs:
        data = get(f"{GAMMA}/events", params={"slug": slug})
        if not data:
            continue
        events = data if isinstance(data, list) else [data]
        for ev in events:
            for m in ev.get("markets", []):
                cid = m.get("conditionId")
                if cid:
                    cids.append(cid)
        time.sleep(0.1)
    # Also pull from leaderboard directly (top monthly P&L traders)
    print(f"    Found {len(cids)} condition IDs from events")
    return cids


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
    """Returns {wallet: breadth_count} for all World Cup holders."""
    counts = defaultdict(int)
    print(f"[+] Scanning {len(cids)} markets for WC traders...")
    for i, cid in enumerate(cids):
        seen = set()
        for h in get_holders_flat(cid, limit=100):
            w = (h.get("proxyWallet") or "").lower()
            if w and w not in seen:
                counts[w] += 1
                seen.add(w)
        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(cids)} markets scanned...")
        time.sleep(0.08)

    # Seed with known top leaderboard traders (World Cup confirmed)
    known_wc_traders = {
        "0x96cfcb0c30942cfcd1cdf76c7d408794d66b1acb": "mintblade",
        "0xed64a7bf029040aa331abc87902434d815ef217d": "fishalive",
        "0xbc11a64ab34a03a043fbe80598fa065ee87eeec6": "frostrizz",
        "0x3f87d51f27ba6e19ec52aaeebb68559a839c742c": "GRIMDRIP",
        "0x5e4c3b5b81171e2ca4ab776ac0d6bba787f9dba2": "endlessFate",
        "0xf0318c32136c2db7fec88b84869aee6a1106c80c": "BreakTheBank",
        "0xf8831548531d56ad6a4331493243c447a827cd1f": "Inaccuratestake",
        "0x26437896ed9dfeb2f69765edcafe8fdceaab39ae": "Latina",
        "0xa4b1eac99a65ed70e3d560126febe1086e6c5143": "0xa4b..143",
        "0x0346afae2603313d2bbee96b628536c8cbe352a5": "GoalLineGhost",
        "0xd6505aab3c6bef32ae6c96dbd8023d7c4df114fb": "BAREFLUX",
        "0x5966db1fe50763c9e3c014d756369bad07e1f804": "0x5966",
        "0x97cb27132b9dd66a2ef49390893cbeb26c3fe4d0": "niuniu1234",
        "0xb91aeb5accc33a5f9a8615b8ed6b2d352e913987": "afghj2421",
        "0x81da605d7dac06478367ed1bae0593b7791ca109": "gardenshed",
        "0xde7be6d489bce070a959e0cb813128ae659b5f4b": "wan123",
    }
    for w in known_wc_traders:
        if w not in counts:
            counts[w] = counts.get(w, 0) + 5  # boost known traders

    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def score_wallet(wallet: str) -> dict | None:
    positions = get(
        f"{BASE}/positions",
        params={"user": wallet, "sizeThreshold": "0", "limit": "500"},
    )
    if not positions or not isinstance(positions, list):
        return None

    fp = [p for p in positions if is_football_title(p.get("title", ""))]
    if not fp:
        return None

    # Exclude liquidity bots
    if any(float(p.get("currentValue", 0)) > 5_000_000 for p in fp):
        return None

    net    = sum(float(p.get("cashPnl", 0)) for p in fp)
    wins   = sum(1 for p in fp if float(p.get("cashPnl", 0)) > 0)
    total  = len(fp)
    wr     = wins / total if total else 0
    init   = sum(abs(float(p.get("initialValue", 0))) for p in fp)
    roi    = (net / init * 100) if init > 0 else 0
    best   = max((float(p.get("cashPnl", 0)) for p in fp), default=0)

    name = ""
    for p in fp:
        n = p.get("name") or p.get("pseudonym") or ""
        if n:
            name = n
            break

    return {
        "wallet":    wallet,
        "username":  name,
        "wc_mkts":   total,
        "wins":      wins,
        "losses":    total - wins,
        "win_rate":  round(wr * 100, 1),
        "net_pnl":   round(net, 2),
        "wagered":   round(init, 2),
        "roi_pct":   round(roi, 2),
        "best_win":  round(best, 2),
        "url":       f"https://polymarket.com/profile/{wallet}",
    }


def composite(r: dict, breadth: int) -> float:
    wagered = r["wagered"] or 1
    return (r["net_pnl"] / wagered) * (r["win_rate"] / 100) * breadth


def main():
    print("=" * 64)
    print("  Polymarket FIFA World Cup 2026 — Copytrade Leaderboard")
    print("=" * 64)

    cids      = get_condition_ids(WC_EVENT_SLUGS)
    wallets   = collect_wallets(cids)
    top_list  = list(wallets.keys())[:TOP_N]

    print(f"\n[+] Scoring top {len(top_list)} wallets by WC football P&L...")

    results = []
    for i, w in enumerate(top_list):
        sc = score_wallet(w)
        if sc:
            sc["breadth"] = wallets[w]
            results.append(sc)
        if (i + 1) % 25 == 0:
            print(f"    {i+1}/{len(top_list)} scored...")
        time.sleep(0.1)

    results.sort(key=lambda r: composite(r, r["breadth"]), reverse=True)

    top = results[:20]
    hdr = f"{'#':<4} {'Username':<22} {'Wallet':<44} {'Mkts':>5} {'W/L':>8} {'WR%':>5} {'Net P&L':>14} {'ROI':>7} {'Best Win':>12}"
    print("\n" + "=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(top, 1):
        name = (r["username"] or r["wallet"][:10] + "…")[:21]
        wl   = f"{r['wins']}/{r['losses']}"
        pnl_str  = f"${r['net_pnl']:>+,.2f}"
        best_str = f"${r['best_win']:>+,.2f}"
        print(
            f"{i:<4} {name:<22} {r['wallet']:<44} {r['wc_mkts']:>5} "
            f"{wl:>8} {r['win_rate']:>4.0f}% {pnl_str:>14} {r['roi_pct']:>+6.1f}% {best_str:>12}"
        )
    print("=" * len(hdr))

    print("\nPolymarket profiles (top 8):")
    for r in top[:8]:
        name = r["username"] or r["wallet"][:14] + "…"
        print(f"  {name:<30}  {r['url']}")

    return top


if __name__ == "__main__":
    main()
