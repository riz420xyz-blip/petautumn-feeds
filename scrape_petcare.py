#!/usr/bin/env python3
"""
PetAutumn - Pet Care Feed Scraper
Sources: Bark & Whiskers (barkandwhiskers.com) + Diamond Pet Foods (diamondpet.com)
Output: feeds/petautumn_petcare.xml
"""

import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timezone
import hashlib
import os
import re
import json

SOURCES = [
    "https://www.barkandwhiskers.com/rss",
    "https://diamondpet.com/blog/feed/?x=1",
]

OUTPUT_FILE = "feeds/petautumn_petcare.xml"
HASH_FILE = "feeds/.petcare_seen.json"
FEED_TITLE = "PetAutumn - Pet Care"
FEED_LINK = "https://petautumn.com"
FEED_DESC = "Pet care tips, health guides, and nutrition advice from PetAutumn"
GENERATOR = "GitHub Scraper (petautumn_petcare)"
MAX_ITEMS = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def load_seen_hashes():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_hashes(hashes):
    os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
    with open(HASH_FILE, "w") as f:
        json.dump(list(hashes), f)


def make_hash(url):
    return hashlib.md5(url.encode()).hexdigest()


def fetch_source(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[ERROR] Fetch failed for {url}: {e}")
        return None


def parse_items(xml_content, source_url):
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"[ERROR] XML parse error from {source_url}: {e}")
        return []

    ns = {
        "content": "http://purl.org/rss/1.0/modules/content/",
        "media": "http://search.yahoo.com/mrss/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    items = []
    channel = root.find("channel")
    if channel is None:
        return []

    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        description = item.findtext("description", "").strip()

        content_encoded = item.find("content:encoded", ns)
        full_content = (
            content_encoded.text.strip()
            if content_encoded is not None and content_encoded.text
            else description
        )

        image_url = ""
        enclosure = item.find("enclosure")
        if enclosure is not None:
            image_url = enclosure.get("url", "")

        if not image_url:
            media = item.find("media:content", ns)
            if media is not None:
                image_url = media.get("url", "")

        if not image_url:
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', full_content)
            if img_match:
                image_url = img_match.group(1)

        categories = [c.text.strip() for c in item.findall("category") if c.text]

        if image_url:
            desc_html = f'<p><img src="{image_url}" style="max-width:100%;" /></p>{full_content}'
        else:
            desc_html = full_content

        if not title or not link:
            continue

        items.append({
            "title": title,
            "link": link,
            "pubDate": pub_date,
            "description": desc_html,
            "content_encoded": desc_html,
            "image_url": image_url,
            "categories": categories,
            "guid": link,
        })

    return items


def build_xml(items):
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        "xmlns:media": "http://search.yahoo.com/mrss/",
        "xmlns:atom": "http://www.w3.org/2005/Atom",
    })

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = FEED_LINK
    ET.SubElement(channel, "description").text = FEED_DESC
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )
    ET.SubElement(channel, "generator").text = GENERATOR

    for art in items:
        it = ET.SubElement(channel, "item")
        ET.SubElement(it, "title").text = art["title"]
        ET.SubElement(it, "link").text = art["link"]
        ET.SubElement(it, "guid", {"isPermaLink": "true"}).text = art["guid"]
        ET.SubElement(it, "pubDate").text = art["pubDate"]

        desc = ET.SubElement(it, "description")
        desc.text = art["description"]

        ce = ET.SubElement(it, "content:encoded")
        ce.text = art["content_encoded"]

        for cat in art["categories"]:
            ET.SubElement(it, "category").text = cat

        if art["image_url"]:
            ET.SubElement(it, "media:content", {
                "url": art["image_url"],
                "medium": "image",
            })

    raw = ET.tostring(rss, encoding="unicode")
    parsed = minidom.parseString(raw)
    return parsed.toprettyxml(indent="  ", encoding=None)


def main():
    seen = load_seen_hashes()
    all_new_items = []

    for source_url in SOURCES:
        print(f"[INFO] Fetching: {source_url}")
        xml_content = fetch_source(source_url)
        if not xml_content:
            continue

        items = parse_items(xml_content, source_url)
        print(f"[INFO] Parsed {len(items)} items from {source_url}")

        new_items = []
        for item in items:
            h = make_hash(item["link"])
            if h not in seen:
                new_items.append(item)
                seen.add(h)

        print(f"[INFO] {len(new_items)} new items from {source_url}")
        all_new_items.extend(new_items)

    print(f"[INFO] Total new items: {len(all_new_items)}")

    if not all_new_items and not os.path.exists(OUTPUT_FILE):
        print("[WARN] No new items and no existing feed. Fetching all items.")
        for source_url in SOURCES:
            xml_content = fetch_source(source_url)
            if xml_content:
                all_new_items.extend(parse_items(xml_content, source_url))

    existing_items = []
    if os.path.exists(OUTPUT_FILE):
        try:
            tree = ET.parse(OUTPUT_FILE)
            root = tree.getroot()
            channel = root.find("channel")
            if channel:
                for item in channel.findall("item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    pub_date = item.findtext("pubDate", "")
                    guid = item.findtext("guid", link)
                    desc_el = item.find("description")
                    desc = desc_el.text or "" if desc_el is not None else ""
                    ce_el = item.find("{http://purl.org/rss/1.0/modules/content/}encoded")
                    ce = ce_el.text or "" if ce_el is not None else desc
                    cats = [c.text for c in item.findall("category") if c.text]
                    media = item.find("{http://search.yahoo.com/mrss/}content")
                    img = media.get("url", "") if media is not None else ""
                    existing_items.append({
                        "title": title, "link": link, "pubDate": pub_date,
                        "description": desc, "content_encoded": ce,
                        "image_url": img, "categories": cats, "guid": guid,
                    })
        except Exception as e:
            print(f"[WARN] Could not parse existing feed: {e}")

    all_items = all_new_items + existing_items
    all_items = all_items[:MAX_ITEMS]

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    xml_output = build_xml(all_items)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml_output)

    save_seen_hashes(seen)
    print(f"[DONE] Saved {len(all_items)} items → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
