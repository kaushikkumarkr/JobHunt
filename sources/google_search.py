import logging
import os
import time
from typing import List, Dict
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sources.base import BaseSource, JobLead
from config.loader import get_config

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

        self.config = get_config() # Ensure config is loaded
        
        roles = self.config["sources"]["google_search"].get("roles", ["Software Engineer"])
        location = self.config["sources"]["google_search"].get("location", "United States")
        
        leads = []
        
        # Maximize Quota: User has 100 queries/day. 
        # Hourly runs = 24 runs/day.
        # Queries per run allowed = 100 / 24 ~= 4.
        # We perform 2 query types (posts + jobs).
        # So we can run 2 separate batches of roles per hour (2 batches * 2 types = 4 queries).
        
        # Split roles into 2 chunks if possible to get better/more specific results
        # instead of one giant OR query that might dilute detailed matches.
        
        chunk_size = (len(roles) + 1) // 2
        role_batches = [roles[i:i + chunk_size] for i in range(0, len(roles), chunk_size)]
        
        # Ensure we don't exceed 2 batches (4 queries) even if list is huge, 
        # to respect the 100/day limit strictly.
        if len(role_batches) > 2:
            # Fallback: flatten back to 2 chunks if math goes weird or list is tiny
            mid = len(roles) // 2
            role_batches = [roles[:mid], roles[mid:]]

        queries = []
        for batch in role_batches:
            if not batch: continue
            
            roles_str = " OR ".join([f'"{r}"' for r in batch])
            roles_query_part = f"({roles_str})"
            
            # Add queries for this batch
            # Intent: Comprehensive list of hiring signals
            intent_phrase = '("hiring" OR "we\'re hiring" OR "we are hiring" OR "join my team" OR "job opening" OR "#hiring" OR "#jobopening")'
            
            # Location: US Variants + Remote
            location_phrase = '(US OR USA OR "United States" OR "U.S." OR remote)'
            
            # Posts Query
            queries.append(f'site:linkedin.com/posts {intent_phrase} {roles_query_part} {location_phrase}')
            
            # Jobs Query (Standard)
            queries.append(f'site:linkedin.com/jobs {roles_query_part} {location_phrase}')

        logger.info(f"Running Google Search: {len(role_batches)} batches, {len(queries)} total queries (Target: ~4/hour).")
        
        for q in queries:
            while True:  # Retry loop for rate limits
                try:
                    # We fetch top 10 results for EACH query.
                    res = self.service.cse().list(
                        q=q, 
                        cx=self.cse_id,
                        # Recency: Last 24 hours (1 day) to increase volume
                        dateRestrict='d1', 
                        sort='date',
                        lr='lang_en', # Force English results to filter out SEO spam
                        num=10
                    ).execute()

                    items = res.get("items", [])
                    logger.info(f"Google Search found {len(items)} results for segment.")

                    for item in items:
                        lead = self._parse_item(item)
                        if lead:
                            leads.append(lead)
                            
                    # Success, break loop and go to next query
                    break

                except HttpError as e:
                    if e.resp.status in [403, 429]:
                        logger.warning(f"⚠️ Quota Exceeded (Status {e.resp.status}). Waiting 1 hour before retrying...")
                        time.sleep(3600)  # Wait 1 hour
                        logger.info("♻️ Resuming after wait...")
                        continue # Retry same query
                    else:
                        logger.error(f"Google Search error for '{q}': {e}")
                        break # Fatal error, skip query
                        
                except Exception as e:
                    logger.error(f"Unexpected Google Search error for '{q}': {e}")
                    break
                
        return leads

    def _parse_item(self, item: Dict) -> JobLead:
        try:
            target_link = item.get("link", "")
            snippet = item.get("snippet", "")
            title = item.get("title", "")
            
            # Strict Filter: Only LinkedIn for now as requested
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
