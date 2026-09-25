import argparse
import concurrent.futures
import os
import random
import statistics
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))


def run(client: httpx.Client, base: str, path: str, method: str = "GET", json_body=None, token: str = ""):
    t0 = time.time()
    headers = {"X-API-Token": token}
    try:
        if method == "GET":
            r = client.get(base + path, headers=headers, timeout=120)
        else:
            r = client.post(base + path, headers=headers, json=json_body, timeout=120)
        return path, r.status_code, (time.time() - t0) * 1000
    except Exception:
        return path, 0, (time.time() - t0) * 1000


def main():
    ap = argparse.ArgumentParser(description="Simple load test: concurrent /documents and /query hits")
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--users", type=int, default=50, help="total requests")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--token", default="")
    ap.add_argument("--query", default="what was the coal production")
    args = ap.parse_args()

    paths = ["/documents"] * 5 + ["/query"] * 3 + ["/analytics/wordcloud"] * 2
    jobs = []
    with httpx.Client(), concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as (client, ex):
            for _i in range(args.users):
                p = random.choice(paths)
                body = {"question": args.query} if p == "/query" else None
                jobs.append(ex.submit(run, client, args.base, p, "POST" if p == "/query" else "GET", body, args.token))
            results = [f.result() for f in jobs]

    by_path: dict[str, list] = {}
    for path, status, ms in results:
        by_path.setdefault(path, []).append((status, ms))

    print(f"{args.users} requests, concurrency {args.concurrency}\n")
    print(f"{'path':<25} {'ok':>5} {'err':>5} {'p50 ms':>8} {'p95 ms':>8}")
    for path, rs in sorted(by_path.items()):
        statuses = [s for s, _ in rs]
        lats = sorted(m for _, m in rs)
        p50 = lats[len(lats) // 2]
        p95 = lats[int(len(lats) * 0.95)]
        ok = sum(1 for s in statuses if 200 <= s < 300)
        print(f"{path:<25} {ok:>5} {len(rs) - ok:>5} {p50:>8.0f} {p95:>8.0f}")

    lat_all = sorted(m for _, m in results)
    if lat_all:
        print(f"\noverall p50 {statistics.median(lat_all):.0f} ms, max {lat_all[-1]:.0f} ms")


if __name__ == "__main__":
    main()
