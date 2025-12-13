import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from sources.base import BaseSource, JobLead
from utils.retries import retry_with_backoff
from config.loader import get_config

logger = logging.getLogger(__name__)

class ATSScraper(BaseSource):
    def __init__(self):
        super().__init__()
        self.config = get_config()
        # Load targets directly from config
        self.targets = self.config["sources"]["ats_scrapers"].get("targets", [])
        
        logger.info(f"Initialized ATS Scraper with {len(self.targets)} target companies.")
        
    @retry_with_backoff(retries=3)
    def _get_page(self, url: str):
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobFinderBot/1.0)"}
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    def fetch_leads(self) -> List[JobLead]:
        leads = []
        
        # 1. Scraping Configured Targets
        for target in self.targets:
            try:
                leads.extend(self._scrape_target(target))
            except Exception as e:
                logger.error(f"Failed to scrape {target['name']}: {e}")
                
        # 2. Dynamic Discovery (Disabled to focus on High-Quality Targets)
        # discovered_leads = self._discover_leads()
        # leads.extend(discovered_leads)
        
        return leads

    def _scrape_target(self, target: Dict[str, str]) -> List[JobLead]:
        if target["type"] == "greenhouse":
            return self._parse_greenhouse(target)
        elif target["type"] == "lever":
            return self._parse_lever(target)
        return []

        return leads

    def _discover_leads(self) -> List[JobLead]:
        """Combine DDG Search and RSS Feeds for discovery."""
        leads = []
        
        # 1. RSS Feeds (Most Reliable)
        try:
            leads.extend(self._discover_rss())
        except Exception as e:
            logger.error(f"RSS Discovery failed: {e}")

        # 2. DDG Search (Supplementary)
        try:
            from duckduckgo_search import DDGS
            logger.info("Running Smart Discovery via DuckDuckGo...")
            queries = [
                'software engineer jobs "greenhouse.io" "united states"',
                'software engineer jobs "lever.co" "united states"',
                'site:linkedin.com/jobs "software engineer" "united states"',
            ]
            
            with DDGS() as ddgs:
                for q in queries:
                    try:
                        results = list(ddgs.text(q, max_results=5, region='us-en'))
                        logger.info(f"Query '{q}' returned {len(results)} results.")
                        for res in results:
                            link = res['href']
                            title = res['title']
                            snippet = res['body']
                            
                            s_type = "unknown"
                            if "greenhouse.io" in link: s_type = "greenhouse"
                            elif "lever.co" in link: s_type = "lever"
                            elif "linkedin.com" in link: s_type = "linkedin"

                            # Clean LinkedIn titles (often "Hiring Software Engineer | LinkedIn")
                            if s_type == "linkedin":
                                title = title.split("|")[0].strip()
                                title = title.replace("Hiring", "").strip()
                            
                            lead = JobLead(
                                source=f"{s_type}_search",
                                company=self._extract_company_from_title(title),
                                role_title=title,
                                link=link,
                                description_snippet=snippet,
                                location_raw="United States"
                            )
                            leads.append(lead)
                            
                    except Exception as e:
                        logger.warning(f"DDG Search failed for {q}: {e}")
        except Exception as e:
            logger.warning(f"DDG module failed: {e}")
                    
        return leads

    def _discover_rss(self) -> List[JobLead]:
        import feedparser
        logger.info("Running Smart Discovery via RSS Feeds...")
        leads = []
        feeds = [
            # "https://remoteok.com/rss", # Often has cloudflare
            "https://weworkremotely.com/categories/remote-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
        ]
        
        for url in feeds:
            try:
                feed = feedparser.parse(url)
                logger.info(f"Fetched RSS {url}: Found {len(feed.entries)} entries.")
                for entry in feed.entries:
                    lead = JobLead(
                        source="rss_feed",
                        company=entry.get("author", "Unknown"),
                        role_title=entry.title,
                        link=entry.link,
                        description_snippet=entry.summary[:500] if hasattr(entry, "summary") else "",
                        location_raw="Remote",
                        posted_at_utc=entry.published if hasattr(entry, "published") else ""
                    )
                    leads.append(lead)
            except Exception as e:
                logger.warning(f"Failed to parse RSS {url}: {e}")
        return leads

    def _extract_company_from_title(self, title: str) -> str:
        # Titles are often "Software Engineer at Acme" or "Acme - Software Engineer"
        if " at " in title:
            return title.split(" at ")[-1].strip()
        if " - " in title:
            return title.split(" - ")[0].strip()
        return "Unknown Company"

    def _parse_greenhouse(self, target) -> List[JobLead]:
        html = self._get_page(target["url"])
        soup = BeautifulSoup(html, "html.parser")
        leads = []
        
        # Greenhouse often has <div class="opening"> or similar
        for job in soup.select("div.opening"):
            try:
                a_tag = job.select_one("a")
                if not a_tag: continue
                
                title = a_tag.get_text(strip=True)
                # Correct relative URL handling
                href = a_tag["href"]
                if href.startswith("http"):
                    link = href
                else:
                    # Ensure no double slashes if base has one and href has one
                    base = "https://boards.greenhouse.io"
                    link = base + href if href.startswith("/") else base + "/" + href
                
                location = job.select_one("span.location").get_text(strip=True) if job.select_one("span.location") else ""
                
                lead = JobLead(
                    source="greenhouse_direct",
                    company=target["name"],
                    role_title=title,
                    link=link,
                    location_raw=location,
                )
                leads.append(lead)
            except Exception:
                continue
        return leads

    def _parse_lever(self, target) -> List[JobLead]:
        html = self._get_page(target["url"])
        soup = BeautifulSoup(html, "html.parser")
        leads = []
        
        # Lever often has <a class="posting-title">
        for job in soup.select("a.posting-title"):
            try:
                title = job.select_one("h5").get_text(strip=True)
                link = job["href"]
                
                # Location often in spans
                loc_span = job.select_one("span.sort-by-location")
                location = loc_span.get_text(strip=True) if loc_span else ""
                
                lead = JobLead(
                    source="lever_direct",
                    company=target["name"],
                    role_title=title,
                    link=link,
                    location_raw=location,
                )
                leads.append(lead)
            except Exception:
                continue
        return leads
