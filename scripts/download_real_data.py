"""Download the real public reference documents the platform needs (eval grounding +
real ingestion corpus). Sources: Ministry of Coal (coal.nic.in), Coal Controller
(coalcontroller.gov.in), PIB, Coal India Limited, DGMS.

All files carry a public source URL recorded in data/real_data/manifest_download.json.
Skips files already downloaded (re-runnable). --list shows the plan without downloading.

Usage: python scripts/download_real_data.py [--list] [--only substring]
"""
import argparse
import json
import os
import re
import ssl
import urllib.request

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "real_data")
STATS_PAGE = "https://www.coal.nic.in/major-statistics/coal-statistics"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# static, hand-verified targets (title, url)
STATIC_TARGETS = [
    ("CIL_Integrated_Annual_Report_2024-25.pdf",
     "https://d3u7ubx0okog7j.cloudfront.net/documents/Annual_Report_2024-2025_50MB.pdf"),
    ("CMPDI_Annual_Report_2024-25.pdf",
     "https://www.cmpdi.co.in/sites/default/files/2025-08/50th%20Annual%20Report%20of%20CMPDIL%20for%20the%20FY%202024-25.pdf"),
    ("CMPDI_National_Inventory_Coal_Lignite_2025.pdf",
     "https://www.cmpdi.co.in/sites/default/files/2025-10/National%20Inventory%20for%20Coal%20and%20lignite_2025.pdf"),
    ("MoC_Annual_Report_2024-25_chap12_exploration.pdf",
     "https://coal.gov.in/sites/default/files/2025-02/chap12AnnualReport2025en2.pdf"),
    ("MoC_Annual_Report_2023-24_chap12_exploration.pdf",
     "https://coal.gov.in/sites/default/files/2024-07/chap12AnnualReport2024en2.pdf"),
    ("msg-march24_monthly_summary.pdf",
     "https://www.coal.gov.in/sites/default/files/2024-04/msg-march24.pdf"),
]

# PIB publishes releases as HTML pages; saved as stripped text
PIB_TEXT_TARGETS = [
    ("PIB_Year_End_Review_2025_MoC.txt",
     "https://pib.gov.in/PressReleaseIframePage.aspx?PRID=2095712"),
]



def fetch(url: str, timeout: int = 60) -> bytes:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read()


def fetch_stream(url: str, dest: str, timeout: int = 300) -> None:
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp, open(dest, "wb") as fh:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            fh.write(block)


def scrape_stats_links() -> list[tuple[str, str]]:
    """Scrape the Coal Statistics page by href pattern (table markup is unreliable).
    Returns (filename, url) for the files this project needs."""
    html = fetch(STATS_PAGE).decode("utf-8", errors="replace")
    hrefs = re.findall(r'href="([^"]+)"', html)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href in hrefs:
        if href.startswith("/"):
            href = "https://www.coal.nic.in" + href
        low = href.lower()
        m = re.search(r"cdchap(\d+)\.xlsx", low)
        if m:
            fname = f"Coal_Directory_2024-25_Chapter_{int(m.group(1)):02d}.xlsx"
        elif "adir" in low and low.endswith(".pdf"):
            fname = "Coal_Directory_of_India_2024-25.pdf"
        elif "coal_171023" in low:
            fname = "Provisional_Coal_Statistics_2022-23.pdf"
        else:
            continue
        if fname not in seen:
            seen.add(fname)
            out.append((fname, href))
    return out


def save_pib_text(url: str, dest: str) -> int:
    """Fetch a PIB release page and save the reader-friendly text."""
    import html as htmllib
    html = fetch(url).decode("utf-8", errors="replace")
    body = re.search(r'<div[^>]+class="[^"]*pdf-asset-content[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I)
    txt = body.group(1) if body else html
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", txt, flags=re.S | re.I)
    txt = htmllib.unescape(re.sub(r"<[^>]+>", " ", txt))
    txt = re.sub(r"[ \t\r\f\v]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt).strip()
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    return len(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show plan only")
    ap.add_argument("--only", default="", help="substring filter on target title")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    manifest_path = os.path.join(OUT_DIR, "manifest_download.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)

    targets: dict[str, str] = {}  # filename -> url

    # 1) static, known-good targets
    for fname, url in STATIC_TARGETS:
        targets[fname] = url

    # 2) scraped Coal Statistics attachments (filenames already normalized)
    print("scraping", STATS_PAGE)
    try:
        links = scrape_stats_links()
        print(f"  found {len(links)} needed attachments")
    except Exception as e:
        print(f"  scrape failed ({e.__class__.__name__}: {str(e)[:80]}) - continuing with static targets")
        links = []
    for fname, href in links:
        targets[fname] = href

    for fname, url in PIB_TEXT_TARGETS:
        targets[fname] = url

    if args.only:
        targets = {k: v for k, v in targets.items() if args.only.lower() in k.lower()}

    print(f"\nplan: {len(targets)} file(s)")
    for fname in sorted(targets):
        have = "HAVE " if os.path.exists(os.path.join(OUT_DIR, fname)) else "fetch"
        print(f"  [{have}] {fname}")

    if args.list:
        return

    ok = skip = fail = 0
    for fname in sorted(targets):
        dest = os.path.join(OUT_DIR, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            skip += 1
            continue
        url = targets[fname]
        try:
            print(f"downloading {fname} ...", flush=True)
            if fname in dict(PIB_TEXT_TARGETS):
                n = save_pib_text(url, dest)
                print(f"  ok ({n:,} chars of text)")
                manifest[fname] = {"url": url, "bytes": n}
                ok += 1
                continue
            fetch_stream(url, dest)
            size = os.path.getsize(dest)
            print(f"  ok ({size / 1e6:.1f} MB)")
            manifest[fname] = {"url": url, "bytes": size,
                               "source_page": STATS_PAGE if "msg-" not in url else "https://coal.gov.in"}
            ok += 1
        except Exception as e:
            print(f"  FAIL: {e.__class__.__name__}: {str(e)[:100]}")
            if os.path.exists(dest):
                os.remove(dest)
            fail += 1

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"\ndone: {ok} downloaded, {skip} skipped (already present), {fail} failed")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
