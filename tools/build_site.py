#!/usr/bin/env python3
"""Assemble the deployable site into _site/.

The repo keeps the page templates in site/ and the generated JSON in data/,
which is tidy to work on but wrong to serve: it would put the homepage at
/site/index.html. This lays the pieces out the way they are actually served,
so the domain root *is* the site.

    _site/index.html        <- site/index.html
    _site/assets/...        <- site/assets/...
    _site/share/...         <- generated graphic + digest
    _site/data/...          <- the JSON the pages fetch
    _site/CNAME             <- the custom domain
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from superpower.config import DOMAIN  # noqa: E402

OUT = ROOT / "_site"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # site/* becomes the root
    shutil.copytree(ROOT / "site", OUT, dirs_exist_ok=True)

    # data/ sits alongside, which is where assets/app.js looks for it
    # (it fetches "../data" from /assets/, i.e. /data).
    shutil.copytree(ROOT / "data", OUT / "data", dirs_exist_ok=True)

    (OUT / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")

    # Stop Pages running the output through Jekyll, which would drop any
    # file or directory beginning with an underscore.
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    files = sum(1 for _ in OUT.rglob("*") if _.is_file())
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"_site/  {files} files, {size / 1024:.0f} KB")
    for p in sorted(OUT.iterdir()):
        print(f"  {p.name}{'/' if p.is_dir() else ''}")


if __name__ == "__main__":
    main()
