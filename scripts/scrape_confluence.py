import os
import re
import time
import logging
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
import html2text
import datetime
import argparse

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "confluence_raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DOMAIN = "www.barclays.co.uk"
BASE_URL = "https://www.barclays.co.uk"

START_URLS = [
    "https://www.barclays.co.uk/help/",
    "https://www.barclays.co.uk/current-accounts/",
    "https://www.barclays.co.uk/mortgages/",
    "https://www.barclays.co.uk/loans/",
    "https://www.barclays.co.uk/credit-cards/",
    "https://www.barclays.co.uk/barclaycard/",
    "https://www.barclays.co.uk/savings/",
    "https://www.barclays.co.uk/ways-to-bank/"
]

MAIN_PATHS = [
    "/current-accounts/",
    "/accounts/",
    "/mortgages/",
    "/loans/",
    "/credit-cards/",
    "/barclaycard/",
    "/savings/",
    "/ways-to-bank/"
]

# Elements to remove from HTML before converting to markdown
JUNK_SELECTORS = [
    'header', 'footer', 'nav', 'script', 'style', 'noscript',
    '.global-header', '.c-header', '.c-footer', '.ef_header', '.ef-footer',
    '.skiplinks', '.search-bar', '.c-popup-nav', '.cookie-banner',
    '.c-skip-links', '#pers-header'
]

def clean_html(soup):
    for selector in JUNK_SELECTORS:
        for el in soup.select(selector):
            el.decompose()
    return soup

def extract_metadata(soup, url):
    title = ""
    if soup.title:
        title = soup.title.get_text(strip=True).split("|")[0].strip()
        
    category = "General"
    if "/help/" in url:
        category = "Help"
    else:
        for p in MAIN_PATHS:
            if p in url:
                category = p.strip('/').capitalize()
                break

    # Attempt to extract precise breadcrumbs if available
    script_texts = [s.get_text() for s in soup.find_all('script') if s.get_text()]
    for text in script_texts:
        match = re.search(r"breadcrumbs:\s*'([^']+)'", text)
        if match:
            parts = match.group(1).split(",")
            cleaned = [p.replace("Answers", "").strip() for p in parts if p.strip() and p != "Answers"]
            if cleaned:
                category = " > ".join(cleaned)
            break
            
    return {
        "title": title,
        "category": category,
        "url": url,
        "date_scraped": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

def is_valid_url(parsed_url):
    if parsed_url.netloc != DOMAIN:
        return False, -1
        
    path = parsed_url.path
    
    # 1. Infinite depth for Help
    if "/help/" in path:
        return True, float('inf')
        
    # 2. Max depth 1 for Main menus
    for p in MAIN_PATHS:
        if path.startswith(p):
            relative = path[len(p):].strip('/')
            if not relative:
                return True, 1 # Root page, allowed
            parts = relative.split('/')
            if len(parts) == 1:
                return True, 1 # Direct submenu, allowed
            return False, -1 # Too deep, rejected
            
    return False, -1

def process_page(url, session):
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code != 200:
            return None, []
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return None, []

    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return None, []

    soup = BeautifulSoup(resp.text, "html.parser")
    
    new_links = []
    for a in soup.find_all("a", href=True):
        href = a['href']
        full_url = urljoin(BASE_URL, href)
        parsed = urlparse(full_url)
        
        valid, _ = is_valid_url(parsed)
        if valid:
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            new_links.append(clean_url)

    metadata = extract_metadata(soup, url)
    soup = clean_html(soup)
    
    main_content = soup.find("main") or soup.find("article") or soup.find("div", class_="c-page") or soup.find("body")
    if not main_content:
        return None, new_links

    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0 
    
    markdown_content = h.handle(str(main_content)).strip()
    
    if len(markdown_content) < 50:
        return None, new_links
        
    return (metadata, markdown_content), new_links

def save_markdown(metadata, content):
    slug = re.sub(r'[^a-z0-9]+', '-', metadata['title'].lower()).strip('-')
    if not slug:
        slug = "untitled"
        
    url_hash = str(hash(metadata['url']))[-6:]
    filename = f"{slug}_{url_hash}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write(f"title: \"{metadata['title']}\"\n")
        f.write(f"category: \"{metadata['category']}\"\n")
        f.write(f"url: \"{metadata['url']}\"\n")
        f.write(f"date_scraped: \"{metadata['date_scraped']}\"\n")
        f.write("---\n\n")
        f.write(content)
        
    return filepath

def crawl(limit=None):
    visited = set()
    queue = list(START_URLS)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    })
    
    saved_count = 0
    
    while queue:
        if limit and saved_count >= limit:
            logging.info(f"Reached limit of {limit} pages.")
            break
            
        current_url = queue.pop(0)
        
        canon_url = current_url.rstrip('/')
        if canon_url in visited:
            continue
            
        visited.add(canon_url)
        logging.info(f"Scraping: {current_url} | Q: {len(queue)} | Saved: {saved_count}")
        
        page_data, new_links = process_page(current_url, session)
        
        for link in new_links:
            if link.rstrip('/') not in visited and link not in queue:
                queue.append(link)
                
        if page_data:
            metadata, content = page_data
            filepath = save_markdown(metadata, content)
            saved_count += 1
            logging.info(f"Saved -> {os.path.basename(filepath)}")
            
        time.sleep(0.3) # Slightly faster crawl

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Barclays Multi-Category Scraper")
    parser.add_argument("--limit", type=int, help="Limit number of pages to scrape", default=0)
    args = parser.parse_args()
    
    if args.limit > 0:
        crawl(limit=args.limit)
    else:
        crawl()
