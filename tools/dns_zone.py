#!/usr/bin/env python3
"""Emit a BIND zone file for Cloudflare's bulk DNS import.

Cloudflare: DNS -> Records -> Import and Export -> Import DNS records.
One upload instead of nine hand-typed records, and no typos.

    python tools/dns_zone.py --github-user YOURNAME [--email-forwarding]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from superpower.config import DOMAIN  # noqa: E402

# Verified live against GitHub's CDN; all four reverse-resolve to
# cdn-<ip>.github.com. GitHub has held these since 2018.
PAGES_A = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
PAGES_AAAA = ["2606:50c0:8000::153", "2606:50c0:8001::153",
              "2606:50c0:8002::153", "2606:50c0:8003::153"]

# Cloudflare Email Routing. Free, forwards to any inbox you verify.
EMAIL_MX = [(1, "route1.mx.cloudflare.net"), (2, "route2.mx.cloudflare.net"),
            (3, "route3.mx.cloudflare.net")]


def build(domain: str, github_user: str, email: bool) -> str:
    out = [
        f"; {domain} — GitHub Pages",
        ";",
        "; IMPORTANT: after importing, set every record below to DNS only",
        "; (grey cloud, not orange). GitHub must see the real request to issue",
        "; the HTTPS certificate. You can enable the proxy later, once the",
        "; certificate shows as issued in the repo's Pages settings.",
        ";",
        "$TTL 1",
        "",
        "; apex -> GitHub Pages",
    ]
    out += [f"{domain}.\t1\tIN\tA\t{ip}" for ip in PAGES_A]
    out += [f"{domain}.\t1\tIN\tAAAA\t{ip}" for ip in PAGES_AAAA]
    out += ["", "; www -> the same site (GitHub redirects it to the apex)",
            f"www.{domain}.\t1\tIN\tCNAME\t{github_user}.github.io."]

    if email:
        out += ["", "; Cloudflare Email Routing — finish setup in the Email tab"]
        out += [f"{domain}.\t1\tIN\tMX\t{p} {h}." for p, h in EMAIL_MX]
        out.append(f'{domain}.\t1\tIN\tTXT\t"v=spf1 include:_spf.mx.cloudflare.net ~all"')

    out += ["", "; Tell mail servers this domain sends no mail from the apex",
            "; (protects the brand from spoofing; harmless if email is on).",
            f'_dmarc.{domain}.\t1\tIN\tTXT\t"v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s"']
    if not email:
        out.append(f'{domain}.\t1\tIN\tTXT\t"v=spf1 -all"')
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--github-user", required=True)
    ap.add_argument("--domain", default=DOMAIN)
    ap.add_argument("--email-forwarding", action="store_true",
                    help="also add Cloudflare Email Routing MX + SPF records")
    ap.add_argument("-o", "--out", default="dist/cloudflare-zone.txt")
    args = ap.parse_args()

    zone = build(args.domain, args.github_user, args.email_forwarding)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(zone, encoding="utf-8")
    print(zone)
    print(f"-> {path}")


if __name__ == "__main__":
    main()
