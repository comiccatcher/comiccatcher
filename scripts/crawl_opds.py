#!/usr/bin/env python3
import os
import json
import httpx
import asyncio
import hashlib
import argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse

class OPDSCrawler:
    def __init__(self, base_url, name, max_depth=3, auth=None, user=None, password=None, concurrency=10):
        self.base_url = base_url
        self.name = name
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.output_dir = Path(f"crawls/{name}")
        self.index_file = self.output_dir / "index.json"
        
        self.visited = {}    # URL -> filename
        self.to_visit = set() # To avoid duplicate queueing
        self.queue = asyncio.Queue()
        
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        
        # Authentication logic
        if user and password:
            self.client.auth = (user, password)
        elif auth:
            if ":" in auth:
                u, p = auth.split(":", 1)
                self.client.auth = (u, p)
            else:
                self.client.headers["Authorization"] = f"Bearer {auth}"

    def _get_filename(self, url):
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        parsed = urlparse(url)
        path_part = parsed.path.strip("/").replace("/", "_")[-32:]
        if not path_part:
            path_part = "root"
        return f"{path_part}_{h}.json"

    async def crawl(self):
        print(f"[*] Starting crawl of {self.name} (Concurrency: {self.concurrency})")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initial seed
        self.to_visit.add(self.base_url)
        await self.queue.put((self.base_url, 0))
        
        workers = [asyncio.create_task(self._worker()) for _ in range(self.concurrency)]
        
        await self.queue.join()
        
        for w in workers:
            w.cancel()
            
        await self.client.aclose()
        self._save_index()
        print(f"\n[+] Crawl complete. Results in {self.output_dir}")

    async def _worker(self):
        while True:
            url, depth = await self.queue.get()
            try:
                await self._fetch_node(url, depth)
            finally:
                self.queue.task_done()

    async def _fetch_node(self, url, depth):
        if depth > self.max_depth:
            return
        
        print(f"  [{depth}] Fetching: {url}")
        
        try:
            resp = await self.client.get(url)
            if resp.status_code != 200:
                return
            
            if "json" not in resp.headers.get("content-type", "").lower():
                return
            
            data = resp.json()
            
            filename = self._get_filename(url)
            (self.output_dir / filename).write_text(json.dumps(data, indent=2))
            self.visited[url] = filename
            
            # 1. Pagination (same depth)
            meta = data.get("metadata", {})
            num_items = meta.get("numberOfItems")
            per_page = meta.get("itemsPerPage")
            
            should_page = True
            if num_items is not None and per_page:
                # Calculate current offset if possible, or count publications
                pubs_count = len(data.get("publications", []))
                groups_count = len(data.get("groups", []))
                
                # If this page is empty, definitely stop
                if pubs_count == 0 and groups_count == 0:
                    should_page = False
                
                # Note: Exact offset math is hard because different servers use 
                # different query params (page=N, offset=N, etc).
                # The "empty page" check above is the most reliable cross-server stop.

            if should_page:
                next_url = self._find_rel(data, "next", url)
                if next_url and next_url not in self.to_visit:
                    self.to_visit.add(next_url)
                    await self.queue.put((next_url, depth))
            
            # 2. Child Links (next depth)
            if depth < self.max_depth:
                child_links = self._extract_links(data, url)
                for child in child_links:
                    if child not in self.to_visit:
                        self.to_visit.add(child)
                        await self.queue.put((child, depth + 1))
                
        except Exception as e:
            print(f"    [!] Error {url}: {e}")

    def _find_rel(self, data, rel_name, base_url):
        links = data.get("links", [])
        for l in links:
            rel = l.get("rel", "")
            if isinstance(rel, list):
                if rel_name in rel:
                    return urljoin(base_url, l.get("href"))
            elif rel == rel_name:
                return urljoin(base_url, l.get("href"))
        return None

    def _extract_links(self, data, base_url):
        found = []
        
        # Look in navigation
        for l in data.get("navigation", []):
            if l.get("href"):
                found.append(urljoin(base_url, l["href"]))
                
        # Look in groups
        for g in data.get("groups", []):
            # Recurse into group navigation
            for l in g.get("navigation", []):
                if l.get("href"):
                    found.append(urljoin(base_url, l["href"]))
            # Recurse into group links (less common but possible)
            for l in g.get("links", []):
                if l.get("rel") == "subsection" or "opds" in l.get("type", ""):
                    found.append(urljoin(base_url, l["href"]))
                    
        # Look in facets
        for f in data.get("facets", []):
            for l in f.get("links", []):
                if l.get("href"):
                    found.append(urljoin(base_url, l["href"]))

        return list(set(found))

    def _save_index(self):
        with open(self.index_file, "w") as f:
            json.dump({
                "name": self.name,
                "base_url": self.base_url,
                "max_depth": self.max_depth,
                "files": self.visited
            }, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OPDS 2.0 Feed Crawler for Analysis")
    parser.add_argument("url", help="Base OPDS 2.0 URL")
    parser.add_argument("name", help="Name for the output folder")
    parser.add_argument("--depth", type=int, default=2, help="Max crawl depth (default: 2)")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent requests (default: 10)")
    parser.add_argument("--user", help="Basic auth username")
    parser.add_argument("--password", help="Basic auth password")
    parser.add_argument("--auth", help="Auth info (combined user:pass or bearer_token)")
    
    args = parser.parse_args()
    
    crawler = OPDSCrawler(args.url, args.name, 
                         max_depth=args.depth, 
                         auth=args.auth, 
                         user=args.user, 
                         password=args.password,
                         concurrency=args.concurrency)
    asyncio.run(crawler.crawl())
