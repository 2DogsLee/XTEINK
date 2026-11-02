#!/usr/bin/env python3
"""
静态 OPDS 目录生成器
扫描 books/*.epub，提取元数据与封面，生成:
  - opds.xml     OPDS 1.x Acquisition Feed（KOReader/Moon+ Reader 等通用）
  - index.html   网页版书架（浏览器直接看）
  - covers/      封面缩略图
用法: python3 scripts/generate_opds.py [BASE_URL]
BASE_URL 形如 https://2dogsee.github.io/XTEINK（留空则用环境变量或占位符，
本地生成后由 CI 用正确 URL 重新生成）。
"""
import os, sys, re, html, zipfile, hashlib, datetime
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS = os.path.join(ROOT, "books")
COVERS = os.path.join(ROOT, "covers")
BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OPDS_BASE_URL", "{{BASE_URL}}")).rstrip("/")
ATOM_NS = "http://www.w3.org/2005/Atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
OPDS_NS = "http://opds-spec.org/2010/catalog"

def epub_meta(path):
    """从 epub 提取 (title, author, date, uuid, cover_bytes, cover_mime)"""
    z = zipfile.ZipFile(path)
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile").get("full-path")
    opf = ET.fromstring(z.read(opf_path))
    title = author = date = uid = ""
    cover_href = cover_id = None
    ns = "{http://www.idpf.org/2007/opf}"
    metadata = opf.find(ns + "metadata")
    if metadata is not None:
        for el in metadata:
            tag = el.tag.split("}")[-1]
            if tag == "title":
                title = (el.text or "").strip()
            elif tag == "creator":
                author = (el.text or "").strip()
            elif tag == "date":
                date = (el.text or "").strip()
            elif tag == "identifier":
                uid = (el.text or "").strip()
    manifest = opf.find(ns + "manifest")
    if manifest is not None:
        for item in manifest:
            if item.get("properties") == "cover-image":
                cover_id = item.get("id")
                cover_href = item.get("href")
            if (item.get("id") or "").lower() in ("cover", "img-cover") and (item.get("href") or "").startswith(("images/", "cover")):
                cover_href = cover_href or item.get("href")
    if cover_href:
        cover_path = os.path.normpath(os.path.join(os.path.dirname(opf_path), cover_href))
        try:
            data = z.read(cover_path)
            mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            return title, author, date, uid, data, mime
        except KeyError:
            pass
    return title, author, date, uid, None, None

def sha1_of(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def xml_escape(s):
    return html.escape(s or "", quote=True)

def main():
    os.makedirs(COVERS, exist_ok=True)
    entries = []
    for fn in sorted(os.listdir(BOOKS)):
        if not fn.endswith(".epub"):
            continue
        path = os.path.join(BOOKS, fn)
        try:
            title, author, date, uid, cover, cover_mime = epub_meta(path)
        except Exception as e:
            print(f"[warn] 元数据提取失败 {fn}: {e}")
            title, author, date, uid, cover, cover_mime = os.path.splitext(fn)[0], "", "", "", None, None
        if not title:
            title = os.path.splitext(fn)[0]
        author = author or "未知作者"
        etag = sha1_of(path)[:12]
        cover_name = None
        if cover:
            ext = "png" if cover_mime == "image/png" else "jpg"
            cover_name = f"{etag}.{ext}"
            with open(os.path.join(COVERS, cover_name), "wb") as f:
                f.write(cover)
        entries.append({
            "title": title, "author": author, "date": date or "2026-01-01",
            "fn": fn, "etag": etag, "size": os.path.getsize(path),
            "cover": cover_name, "cover_mime": cover_mime, "uid": uid,
        })
        print(f"[book] {title} — {author} ({fn}, {os.path.getsize(path)//1024}KB)")

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = max([e["date"] for e in entries] + [now], key=lambda d: d[:10])

    # ---------- opds.xml ----------
    L = []
    L.append('<?xml version="1.0" encoding="UTF-8"?>')
    L.append(f'<feed xmlns="{ATOM_NS}" xmlns:opds="{OPDS_NS}" xmlns:dc="{DC_NS}" xml:lang="zh-CN">')
    L.append(f"  <id>urn:xteink:catalog</id>")
    L.append(f"  <title>XTEINK 书库</title>")
    L.append(f"  <subtitle>微信公众号文章电子书</subtitle>")
    L.append(f"  <updated>{updated}</updated>")
    L.append(f'  <author><name>XTEINK</name><uri>{BASE}</uri></author>')
    L.append(f'  <link rel="self" href="{BASE}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>')
    L.append(f'  <link rel="start" href="{BASE}/opds.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>')
    for e in entries:
        href_book = f"{BASE}/books/" + urllib.parse.quote(e["fn"])
        L.append("  <entry>")
        L.append(f"    <id>{xml_escape(e['uid'] or 'urn:xteink:' + e['etag'])}</id>")
        L.append(f"    <title>{xml_escape(e['title'])}</title>")
        L.append(f"    <author><name>{xml_escape(e['author'])}</name></author>")
        L.append(f"    <updated>{e['date']}T00:00:00Z</updated>")
        L.append(f'    <dc:language>zh-CN</dc:language>')
        L.append(f'    <dc:publisher>XTEINK</dc:publisher>')
        if e["cover"]:
            L.append(f'    <link rel="http://opds-spec.org/image" href="{BASE}/covers/{e["cover"]}" type="{e["cover_mime"]}"/>')
            L.append(f'    <link rel="http://opds-spec.org/image/thumbnail" href="{BASE}/covers/{e["cover"]}" type="{e["cover_mime"]}"/>')
        L.append(f'    <link rel="http://opds-spec.org/acquisition" href="{href_book}" type="application/epub+zip"/>')
        L.append(f'    <link rel="alternate" href="{BASE}/index.html" type="text/html"/>')
        L.append("  </entry>")
    L.append("</feed>")
    with open(os.path.join(ROOT, "opds.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    # ---------- index.html ----------
    cards = []
    for e in entries:
        href_book = "books/" + urllib.parse.quote(e["fn"])
        cover = f"covers/{e['cover']}" if e["cover"] else ""
        cards.append(f'''    <div class="card">
      <a href="{href_book}">{f'<img src="{cover}"/>' if cover else '<div class="nocover">无封面</div>'}</a>
      <div class="info">
        <div class="title"><a href="{href_book}">{xml_escape(e['title'])}</a></div>
        <div class="author">{xml_escape(e['author'])} · {e['date']}</div>
        <div class="size">{e['size']//1024} KB · EPUB</div>
      </div>
    </div>''')
    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>XTEINK 书库</title>
<style>
body{{font-family:-apple-system,sans-serif;background:#f5f5f4;margin:0;padding:2em 1em;}}
h1{{text-align:center;font-size:1.4em;}}
p.hint{{text-align:center;color:#78716c;font-size:.9em;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:1.2em;max-width:1100px;margin:0 auto;}}
.card{{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);}}
.card img{{width:100%;aspect-ratio:2/3;object-fit:cover;display:block;}}
.nocover{{width:100%;aspect-ratio:2/3;display:flex;align-items:center;justify-content:center;background:#e7e5e4;color:#78716c;}}
.info{{padding:.6em .8em;}}
.title{{font-size:.92em;font-weight:600;line-height:1.4;max-height:2.8em;overflow:hidden;}}
.title a{{color:#1c1917;text-decoration:none;}}
.author{{font-size:.8em;color:#78716c;margin-top:.25em;}}
.size{{font-size:.75em;color:#a8a29e;margin-top:.15em;}}
</style></head><body>
<h1>📚 XTEINK 书库</h1>
<p class="hint">共 {len(entries)} 本 · OPDS 订阅地址：<code>{BASE}/opds.xml</code></p>
<div class="grid">
{chr(10).join(cards)}
</div></body></html>"""
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)

    print(f"[done] {len(entries)} 本书 → opds.xml + index.html + covers/")

if __name__ == "__main__":
    main()
