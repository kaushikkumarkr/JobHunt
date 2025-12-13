import logging
import os
from typing import List, Dict
from googleapiclient.discovery import build
from sources.base import BaseSource, JobLead

logger = logging.getLogger(__name__)

class GoogleSearchSource(BaseSource):
    def __init__(self):
        super().__init__()
        self.api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
        self.cse_id = os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
        
        self.service = None
        if self.api_key and self.cse_id:
            try:
                self.service = build("customsearch", "v1", developerKey=self.api_key)
            except Exception as e:
                logger.error(f"Failed to init Google Search: {e}")

    def fetch_leads(self) -> List[JobLead]:
        if not self.service:
            logger.info("Google Search credentials missing. Skipping.")
            return []

        leads = []
        # We want recent posts (past 24h) about hiring
        # dateRestrict='d1' forces last 24 hours
        queries = [
            'site:linkedin.com/posts "hiring" "software engineer" "united states"',
            'site:linkedin.com/jobs "software engineer" "united states"',
            # We can also add other sites if needed
            # 'site:twitter.com "hiring" "software engineer" "remote"'
        ]

        logger.info("Running Smart Discovery via Google Custom Search...")
        
        for q in queries:
            try:
                res = self.service.cse().list(
                    q=q, 
                    cx=self.cse_id,
                    dateRestrict='h2', # Last 2 hours only (matches hourly run schedule)
                    sort='date',       # Explicitly sort by date
                    num=10
                ).execute()

                items = res.get("items", [])
                logger.info(f"Google Search '{q}' found {len(items)} results.")

                for item in items:
                    lead = self._parse_item(item)
                    if lead:
                        leads.append(lead)

            except Exception as e:
                logger.error(f"Google Search failed for '{q}': {e}")
                
        return leads

    def _parse_item(self, item: Dict) -> JobLead:
        try:
            target_link = item.get("link", "")
            snippet = item.get("snippet", "")
            title = item.get("title", "")
            
            # Basic dedupe/filter
            if "linkedin.com" not in target_link:
                return None

            # Detect Type
            source_type = "linkedin_post" if "/posts/" in target_link else "linkedin_job"
            
            # Extract Company (heuristic)
            # LinkedIn Titles: "Software Engineer at Google..." or "Google hiring..."
            company = "Unknown"
            if " at " in title:
                company = title.split(" at ")[-1].split("|")[0].strip()
            elif " - " in title:
                company = title.split(" - ")[0].strip()

            return JobLead(
                source=f"google_{source_type}",
                company=company,
                role_title=title,
                link=target_link,
                description_snippet=snippet,
                location_raw="United States", # Google query was restricted, but we could parse snippet
                posted_at_utc="" # Optionally parse structured data if available
            )
        except Exception:
            return None
