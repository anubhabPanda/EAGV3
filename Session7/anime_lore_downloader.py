#!/usr/bin/env python3
"""
Anime wiki downloader - fetches anime wikis and converts to markdown.
Usage: python anime_lore_downloader.py "One Piece"
"""

import sys
import os
import subprocess
import re
from pathlib import Path
from markitdown import MarkItDown
import time

os.environ['PYTHONIOENCODING'] = 'utf-8'


def get_wiki_url(anime_name: str) -> str:
    """Get the main wiki page URL for an anime."""
    wikis = {
        "fandom": f"https://{anime_name.lower().replace(' ', '')}.fandom.com/wiki/{anime_name.replace(' ', '_')}",
        "wikipedia": f"https://en.wikipedia.org/wiki/{anime_name.replace(' ', '_')}",
    }
    return wikis["fandom"]


def fetch_html(url: str) -> str:
    """Fetch HTML content from URL using crawl4ai subprocess."""
    print(f"Fetching: {url}")
    script = f"""
import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    async with AsyncWebCrawler(verbose=False, headless=True) as crawler:
        result = await crawler.arun(url="{url}")
        print("<<<HTML_START>>>")
        print(result.html)
        print("<<<HTML_END>>>")

asyncio.run(main())
"""
    result = subprocess.run([sys.executable, "-c", script],
                          capture_output=True, text=True,
                          encoding='utf-8', errors='replace')

    output = result.stdout
    if "<<<HTML_START>>>" in output and "<<<HTML_END>>>" in output:
        start = output.index("<<<HTML_START>>>") + len("<<<HTML_START>>>")
        end = output.index("<<<HTML_END>>>")
        return output[start:end].strip()
    raise Exception(f"Failed to fetch: {result.stderr}")


def save_markdown(content: str, anime_name: str, output_dir: Path) -> Path:
    """Save markdown content to file."""
    output_dir.mkdir(exist_ok=True)
    filename = f"{anime_name.replace(' ', '_').lower()}_wiki.md"
    filepath = output_dir / filename
    filepath.write_text(content, encoding='utf-8')
    print(f"[OK] Saved: {filepath}")
    return filepath


def extract_links_from_markdown(md_content: str, section_marker: str) -> list[str]:
    """Extract wiki links from a specific section in markdown."""
    links = []
    in_section = False

    for line in md_content.split('\n'):
        if section_marker.lower() in line.lower():
            in_section = True
            continue
        if in_section and line.startswith('* ') and '[' not in line:
            break
        if in_section:
            matches = re.findall(r'\[([^\]]+)\]\((https://[^\)]+)\)', line)
            for text, url in matches:
                if 'onepiece.fandom.com/wiki/' in url and ':' not in url.split('/wiki/')[-1]:
                    links.append((text, url))
    return links


def download_page(url: str, name: str, output_dir: Path, category: str) -> bool:
    """Download a single page."""
    try:
        html = fetch_html(url)
        md = MarkItDown()
        import io
        result = md.convert_stream(io.BytesIO(html.encode('utf-8')), file_extension=".html")

        category_dir = output_dir / category
        category_dir.mkdir(exist_ok=True)

        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        filepath = category_dir / f"{safe_name}.md"
        filepath.write_text(result.text_content, encoding='utf-8')

        print(f"  [OK] {category}/{safe_name}.md")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def download_anime_wiki(anime_name: str, output_dir: Path = None) -> Path:
    """Download anime wiki and all related content."""
    if output_dir is None:
        output_dir = Path(__file__).parent / "anime_wikis" / anime_name.lower().replace(' ', '_')

    output_dir.mkdir(parents=True, exist_ok=True)

    # Download main page
    wiki_url = get_wiki_url(anime_name)
    html_content = fetch_html(wiki_url)

    md = MarkItDown()
    import io
    result = md.convert_stream(io.BytesIO(html_content.encode('utf-8')), file_extension=".html")
    main_content = result.text_content

    main_file = save_markdown(main_content, "main", output_dir)
    print(f"[SUCCESS] Downloaded main wiki: {len(main_content):,} characters\n")

    # Extract and download story arcs
    print("[DOWNLOADING] Story Arcs...")
    arc_links = extract_links_from_markdown(main_content, "Story Arcs")
    for name, url in arc_links[:20]:
        download_page(url, name, output_dir, "story_arcs")
        time.sleep(1)

    # Download character pages
    print("\n[DOWNLOADING] Characters...")
    char_url = f"https://{anime_name.lower().replace(' ', '')}.fandom.com/wiki/List_of_Canon_Characters"
    try:
        char_html = fetch_html(char_url)
        char_md = md.convert_stream(io.BytesIO(char_html.encode('utf-8')), file_extension=".html").text_content
        char_links = re.findall(r'\[([^\]]+)\]\((https://[^\)]+)\)', char_md)
        char_links = [(n, u) for n, u in char_links if 'onepiece.fandom.com/wiki/' in u and ':' not in u.split('/wiki/')[-1]]

        for name, url in char_links[:30]:
            download_page(url, name, output_dir, "characters")
            time.sleep(1)
    except:
        pass

    # Download organizations (single file)
    print("\n[DOWNLOADING] Organizations...")
    org_url = f"https://{anime_name.lower().replace(' ', '')}.fandom.com/wiki/Category:Organizations"
    try:
        org_html = fetch_html(org_url)
        org_md = md.convert_stream(io.BytesIO(org_html.encode('utf-8')), file_extension=".html").text_content
        (output_dir / "organizations.md").write_text(org_md, encoding='utf-8')
        print(f"  [OK] organizations.md")
    except:
        pass

    # Download locations (single file)
    print("\n[DOWNLOADING] Locations...")
    loc_url = f"https://{anime_name.lower().replace(' ', '')}.fandom.com/wiki/Category:Locations"
    try:
        loc_html = fetch_html(loc_url)
        loc_md = md.convert_stream(io.BytesIO(loc_html.encode('utf-8')), file_extension=".html").text_content
        (output_dir / "locations.md").write_text(loc_md, encoding='utf-8')
        print(f"  [OK] locations.md")
    except:
        pass

    # Download animal species pages
    print("\n[DOWNLOADING] Animal Species...")
    species_url = f"https://{anime_name.lower().replace(' ', '')}.fandom.com/wiki/Animal_Species"
    try:
        species_html = fetch_html(species_url)
        species_md = md.convert_stream(io.BytesIO(species_html.encode('utf-8')), file_extension=".html").text_content
        species_links = re.findall(r'\[([^\]]+)\]\((https://[^\)]+)\)', species_md)
        species_links = [(n, u) for n, u in species_links if 'onepiece.fandom.com/wiki/' in u and 'Animal' not in u and ':' not in u.split('/wiki/')[-1]]

        for name, url in species_links[:20]:
            download_page(url, name, output_dir, "animal_species")
            time.sleep(1)
    except:
        pass

    print(f"\n[COMPLETE] All files saved to: {output_dir}")
    return output_dir


if __name__ == "__main__":
    if len(sys.argv) > 1:
        anime_name = " ".join(sys.argv[1:])
    else:
        anime_name = "One Piece"

    print(f"Downloading wiki for: {anime_name}\n")
    download_anime_wiki(anime_name)
