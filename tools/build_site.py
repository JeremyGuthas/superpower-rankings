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

import hashlib
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from superpower.config import DOMAIN  # noqa: E402

OUT = ROOT / "_site"


ASSET_REF = re.compile(r'(?P<attr>src|href)="(?P<path>(?:\.\./|\./)*assets/[^"?#]+)"')
IMPORT_REF = re.compile(r"""(?P<kw>from|import)\s+['"](?P<path>\./[^'"?#]+\.js)['"]""")


def version_assets(out: Path) -> None:
    """Append a content hash to every asset URL.

    Browsers cache JS modules and stylesheets hard. Without this, a repeat
    visitor keeps running the previous deploy's code — which is invisible in
    testing and very confusing in production.
    """
    digests: dict[str, str] = {}
    for f in (out / "assets").rglob("*"):
        if f.is_file():
            digest = hashlib.sha256(f.read_bytes()).hexdigest()[:8]
            digests[f.relative_to(out).as_posix()] = digest

    # Rewrite the imports *between* modules first, then re-hash, because
    # changing an import changes the importing file's own content.
    for f in sorted((out / "assets").rglob("*.js")):
        text = f.read_text(encoding="utf-8")

        def sub_import(m: re.Match) -> str:
            target = f"assets/{Path(m.group('path')).name}"
            d = digests.get(target)
            return m.group(0) if not d else m.group(0).replace(
                m.group("path"), f"{m.group('path')}?v={d}")

        new = IMPORT_REF.sub(sub_import, text)
        if new != text:
            f.write_text(new, encoding="utf-8")

    # Re-hash after the import rewrite so the entry points get fresh digests.
    for f in (out / "assets").rglob("*"):
        if f.is_file():
            digests[f.relative_to(out).as_posix()] = hashlib.sha256(
                f.read_bytes()).hexdigest()[:8]

    for html in out.rglob("*.html"):
        text = html.read_text(encoding="utf-8")

        def sub_ref(m: re.Match) -> str:
            path = re.sub(r"^(?:\.\./)+|^\./", "", m.group("path"))
            d = digests.get(path)
            return m.group(0) if not d else f'{m.group("attr")}="{m.group("path")}?v={d}"'

        html.write_text(ASSET_REF.sub(sub_ref, text), encoding="utf-8")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # site/* becomes the root
    shutil.copytree(ROOT / "site", OUT, dirs_exist_ok=True)

    # data/ sits alongside, which is where assets/app.js looks for it
    # (it fetches "../data" from /assets/, i.e. /data).
    shutil.copytree(ROOT / "data", OUT / "data", dirs_exist_ok=True)

    # Turn the app into real pages before hashing assets, so the pre-rendered
    # HTML picks up the versioned URLs too.
    import prerender  # noqa: E402  (same directory)
    prerender.main()

    # The flat templates were copied in as the source for pre-rendering; the
    # clean URLs supersede them, and leaving them served would be duplicate
    # content competing with the pages we actually want indexed.
    for stale in ("team.html", "compare.html", "accuracy.html"):
        (OUT / stale).unlink(missing_ok=True)

    version_assets(OUT)

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
