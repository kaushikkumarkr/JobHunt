import httpx
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from sources.base import BaseSource, JobLead
from utils.retries import retry_with_backoff

logger = logging.getLogger(__name__)

class ATSScraper(BaseSource):
    def __init__(self, target_companies: List[Dict[str, str]] = None):
        """
        target_companies: List of dicts with 'name', 'ats_url', 'type' (greenhouse, lever, etc)
        For this simplified version, we'll demonstrate searching or hitting known public boards.
        Since we don't have a giant list of companies, we'll implement the logic to scrape 
        IF we are given a URL.
        
        In a real runner, you'd feed this a list of company careers page URLs.
        """
        super().__init__()
        # Example seed list - in production this might come from a config or database
        self.targets = [
            # {"name": "Example Corp", "url": "https://boards.greenhouse.io/example", "type": "greenhouse"},
            # In a real run, you'd populate this.
        ]
        
    @retry_with_backoff(retries=3)
    def _get_page(self, url: str):
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobFinderBot/1.0)"}
        resp = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    def fetch_leads(self) -> List[JobLead]:
        leads = []
        for target in self.targets:
            try:
                if target["type"] == "greenhouse":
                    leads.extend(self._parse_greenhouse(target))
                elif target["type"] == "lever":
                    leads.extend(self._parse_lever(target))
                # Add others...
            except Exception as e:
                logger.error(f"Failed to scrape {target['name']}: {e}")
        return leads

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
                link = "https://boards.greenhouse.io" + a_tag["href"] if a_tag["href"].startswith("/") else a_tag["href"]
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
