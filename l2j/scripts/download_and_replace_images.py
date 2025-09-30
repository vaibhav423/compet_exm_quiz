#!/usr/bin/env python3
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

DEFAULT_ROOT = Path("examgroups")
DEFAULT_DOWNLOAD_CONCURRENCY = 32
DEFAULT_FILE_CONCURRENCY = 4
DEFAULT_RETRIES = 2
DEFAULT_MANIFEST_DIR = "manifest"
USER_AGENT = "ImageDownloader/2.0 (+https://example.com)"
TIMEOUT = aiohttp.ClientTimeout(total=60)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("imgdl")

try:
    import lxml
    BS_PARSER = "lxml"
except Exception:
    BS_PARSER = "html.parser"

def find_jsons(root: Path) -> List[Path]:
    return sorted(root.glob("*/*/*/*/*.json"))

def walk_and_collect_html(obj: Any, path: List[Any], hits: List[Tuple[List[Any], str]]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk_and_collect_html(v, path + [k], hits)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_and_collect_html(v, path + [i], hits)
    elif isinstance(obj, str):
        if "<img" in obj.lower():
            hits.append((path, obj))

def set_by_path(root: Any, path: List[Any], value: Any) -> None:
    cur = root
    for p in path[:-1]:
        cur = cur[p]
    cur[path[-1]] = value

def short_hash(s: str, n: int = 8) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]

def safe_filename_from_url(url: str, hash_len: int = 8) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if name:
        stem = Path(name).stem
        ext = Path(name).suffix
        if ext:
            return f"{stem}-{short_hash(url, hash_len)}{ext}"
        else:
            return f"{stem}-{short_hash(url, hash_len)}"
    return short_hash(url, hash_len)

def ensure_ext(path: Path, content_type: Optional[str]) -> Path:
    if path.suffix:
        return path
    if not content_type:
        return path
    try:
        ctype = content_type.split(";")[0].strip()
        ext = mimetypes.guess_extension(ctype)
        if ext:
            return path.with_suffix(ext)
    except Exception:
        pass
    return path

def make_relative(dest: Path, base: Path) -> str:
    try:
        return os.path.relpath(dest, start=base)
    except Exception:
        return str(dest)

def extract_image_urls_from_tag(tag) -> List[Tuple[str, str]]:
    urls: List[Tuple[str, str]] = []
    for attr in ("src", "data-src", "data-original"):
        val = tag.get(attr)
        if val:
            urls.append((attr, val))
    srcset = tag.get("srcset")
    if srcset:
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            pieces = part.split()
            url = pieces[0]
            urls.append(("srcset", url))
    return urls

def replace_urls_in_tag(tag, url_map: Dict[str, str]) -> None:
    for attr in ("src", "data-src", "data-original"):
        val = tag.get(attr)
        if val:
            mapped = url_map.get(val)
            if mapped:
                tag[attr] = mapped
            if attr in ("data-src", "data-original") and tag.get("src") is None:
                mapped2 = url_map.get(tag.get(attr))
                if mapped2:
                    tag["src"] = mapped2

    srcset = tag.get("srcset")
    if srcset:
        new_entries = []
        for part in srcset.split(","):
            part = part.strip()
            if not part:
                continue
            pieces = part.split()
            url = pieces[0]
            descriptor = " ".join(pieces[1:]) if len(pieces) > 1 else ""
            mapped = url_map.get(url)
            if mapped:
                entry = f"{mapped} {descriptor}".strip()
            else:
                entry = part
            new_entries.append(entry)
        tag["srcset"] = ", ".join(new_entries)

    lazy_attrs = [
        "data-src",
        "data-original",
        "data-lazy",
        "data-lazy-src",
        "data-lazy-srcset",
        "loading",
        "data-srcset",
    ]
    for a in lazy_attrs:
        if a in tag.attrs:
            del tag.attrs[a]

async def fetch_with_retries(session: aiohttp.ClientSession, url: str, retries: int) -> Optional[Tuple[bytes, str]]:
    last_exc = None
    for attempt in range(retries + 1):
        try:
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                content = await resp.read()
                ctype = resp.headers.get("content-type", "")
                return content, ctype
        except Exception as e:
            last_exc = e
            logger.debug("Attempt %d failed for %s: %s", attempt + 1, url, e)
            await asyncio.sleep(0.2 * (attempt + 1))
    logger.warning("Failed to download %s after %d retries: %s", url, retries, last_exc)
    return None

async def download_all(urls: Set[str], dest_map: Dict[str, Path], concurrency: int, retries: int, session: aiohttp.ClientSession) -> Dict[str, Optional[Path]]:
    sem = asyncio.Semaphore(concurrency)
    out: Dict[str, Optional[Path]] = {}

    async def worker(u: str):
        async with sem:
            dest = dest_map[u]
            if dest.exists() and dest.stat().st_size > 0:
                logger.debug("Skipping existing %s", dest)
                out[u] = dest
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            res = await fetch_with_retries(session, u, retries)
            if not res:
                out[u] = None
                return
            content, ctype = res
            dest_with_ext = ensure_ext(dest, ctype)
            try:
                dest_with_ext.write_bytes(content)
                out[u] = dest_with_ext
                logger.debug("Saved %s -> %s", u, dest_with_ext)
            except Exception as e:
                logger.error("Failed to write %s: %s", dest_with_ext, e)
                out[u] = None

    tasks = [asyncio.create_task(worker(u)) for u in sorted(urls)]
    if tasks:
        await asyncio.gather(*tasks)
    return out

async def process_json_file(json_path: Path, session: aiohttp.ClientSession, download_concurrency: int, retries: int, manifest_dirname: str, dry_run: bool) -> None:
    logger.info("Processing %s", json_path)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    hits: List[Tuple[List[Any], str]] = []
    walk_and_collect_html(data, [], hits)
    if not hits:
        logger.info("No HTML with <img> found in %s", json_path)
        return

    filename = json_path.stem
    assets_dir = json_path.parent / "assets" / filename
    assets_dir.mkdir(parents=True, exist_ok=True)

    url_to_dest: Dict[str, Path] = {}
    html_parsed_cache: List[Tuple[List[Any], BeautifulSoup]] = []
    for path, html in hits:
        soup = BeautifulSoup(html, BS_PARSER)
        html_parsed_cache.append((path, soup))
        for img in soup.find_all("img"):
            for attr, url in extract_image_urls_from_tag(img):
                if not url:
                    continue
                if url.startswith("//"):
                    url = "https:" + url
                if not (url.startswith("http://") or url.startswith("https://")):
                    logger.debug("Skipping non-absolute URL: %s", url)
                    continue
                if url not in url_to_dest:
                    fname = safe_filename_from_url(url)
                    dest = assets_dir / fname
                    if "-" not in dest.stem or dest.stem.endswith(short_hash(url)):
                        pass
                    else:
                        dest = assets_dir / f"{dest.stem}-{short_hash(url)}{dest.suffix}"
                    url_to_dest[url] = dest

    if not url_to_dest:
        logger.info("No downloadable image URLs found in %s", json_path)
        return

    result = await download_all(set(url_to_dest.keys()), url_to_dest, download_concurrency, retries, session)

    url_map: Dict[str, str] = {}
    failed: Dict[str, str] = {}
    for url, saved in result.items():
        if saved is None:
            failed[url] = "download_failed"
            continue
        rel = make_relative(saved, json_path.parent)
        url_map[url] = rel.replace(os.path.sep, "/")

    for (path, soup) in html_parsed_cache:
        for img in soup.find_all("img"):
            local_map: Dict[str, str] = {}
            for attr, url in extract_image_urls_from_tag(img):
                if not url:
                    continue
                u = url
                if u.startswith("//"):
                    u = "https:" + u
                mapped = url_map.get(u) or url_map.get(url)
                if mapped:
                    local_map[url] = mapped
                    local_map[u] = mapped
            if local_map:
                replace_urls_in_tag(img, local_map)
        new_html = str(soup)
        set_by_path(data, path, new_html)

    manifest_folder = json_path.parent / manifest_dirname
    manifest_folder.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_folder / f"{filename}_manifest.json"
    manifest = {"mappings": url_map, "failed": failed}
    if dry_run:
        logger.info("[dry-run] Manifest for %s would be written to %s", json_path, manifest_path)
    else:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote manifest %s", manifest_path)

    if dry_run:
        logger.info("[dry-run] JSON %s would be updated (in-place)", json_path)
    else:
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Updated JSON %s", json_path)

async def main_async(root: Path, download_concurrency: int, file_concurrency: int, retries: int, manifest_dirname: str, dry_run: bool) -> None:
    jsons = find_jsons(root)
    if not jsons:
        logger.warning("No matching JSON files under %s", root)
        return
    logger.info("Found %d JSON files", len(jsons))

    connector = aiohttp.TCPConnector(limit=max(download_concurrency * 2, 100))
    headers = {"User-Agent": USER_AGENT}
    sem = asyncio.Semaphore(file_concurrency)
    async with aiohttp.ClientSession(connector=connector, headers=headers, timeout=TIMEOUT) as session:
        async def file_worker(j: Path):
            async with sem:
                try:
                    await process_json_file(j, session, download_concurrency, retries, manifest_dirname, dry_run)
                except Exception as e:
                    logger.exception("Failed processing %s: %s", j, e)

        tasks = [asyncio.create_task(file_worker(j)) for j in jsons]
        if tasks:
            await asyncio.gather(*tasks)

def parse_args():
    p = argparse.ArgumentParser(description="Download images referenced in JSON-stored HTML and replace urls with local assets.")
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Root folder to scan (default: examgroups)")
    p.add_argument("--concurrency", type=int, default=DEFAULT_DOWNLOAD_CONCURRENCY, help="Concurrent downloads per JSON processing")
    p.add_argument("--file-concurrency", type=int, default=DEFAULT_FILE_CONCURRENCY, help="Number of JSON files to process concurrently")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Download retries per file")
    p.add_argument("--manifest-dir", type=str, default=DEFAULT_MANIFEST_DIR, help="Folder name next to JSON to write manifests")
    p.add_argument("--dry-run", action="store_true", help="Do not write files; only print planned actions")
    return p.parse_args()

def main():
    args = parse_args()
    try:
        asyncio.run(main_async(args.root, args.concurrency, args.file_concurrency, args.retries, args.manifest_dir, args.dry_run))
    except KeyboardInterrupt:
        logger.info("Interrupted")

if __name__ == "__main__":
    main()
