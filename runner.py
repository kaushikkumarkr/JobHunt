import logging
import hashlib
import os
from dotenv import load_dotenv
from typing import List

# Load env immediately
load_dotenv()

from config.loader import get_config
from utils.logging import setup_logging
from storage.sheets_store import SheetsStore
from sources.ats_scrapers import ATSScraper
from sources.gmail_ingest import GmailIngestSource
from sources.google_search import GoogleSearchSource
from normalizers.location_parser import LocationParser
from filters.tech_filter import TechFilter
from llm.manager import LLMManager
from notifiers.email_notifier import EmailNotifier
from notifiers.telegram_discord import InstantNotifier
from sources.base import JobLead

def generate_lead_id(lead: JobLead) -> str:
    # Dedupe ID: sha256(company + title + link)
    raw = f"{lead.company.lower()}{lead.role_title.lower()}{lead.link}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

import asyncio
from utils.crawler import enrich_leads

async def main_async():
    logger = setup_logging()
    logger.info("Starting Job Finder Run...")
    
    config = get_config()
    
    # 1. Init Storage & Load State
    store = SheetsStore()
    seen_ids = store.load_seen_ids()
    logger.info(f"Loaded {len(seen_ids)} existing lead IDs from Sheet.")
    
    # 2. Init Components
    ats_source = ATSScraper()
    gmail_source = GmailIngestSource()
    loc_parser = LocationParser()
    tech_filter = TechFilter()
    llm_manager = LLMManager()  # instantiated even if not used heavily
    email_notifier = EmailNotifier()
    instant_notifier = InstantNotifier()
    
    # 3. Fetch Leads
    all_raw_leads = []
    
    # ATS
    if config["sources"]["ats_scrapers"]["enabled"]:
        logger.info("Fetching ATS leads...")
        all_raw_leads.extend(ats_source.fetch_leads())
        
    # Google Search
    if config["sources"]["google_search"]["enabled"]:
        logger.info("Fetching Google Search leads...")
        try:
            google_source = GoogleSearchSource()
            all_raw_leads.extend(google_source.fetch_leads())
        except Exception as e:
            logger.error(f"Google Search failed: {e}")

    # Gmail
    if config["sources"]["gmail_ingest"]["enabled"]:
        logger.info("Fetching Gmail leads...")
        all_raw_leads.extend(gmail_source.fetch_leads())
        
    # 3.5 Pre-Filter Candidates
    # We only want to crawl leads that look promising (English, relevant title).
    candidates_to_crawl = []
    skipped_ids = 0
    
    for lead in all_raw_leads:
        # ID Generation
        lid = generate_lead_id(lead)
        if lid in seen_ids:
            skipped_ids += 1
            continue
        
        lead.lead_id = lid
        
        # Base Text Normalization
        lead.company = lead.company.strip()
        lead.role_title = lead.role_title.strip()
        
        # Location Parse
        loc_data = loc_parser.parse(lead.location_raw)
        lead.city = loc_data["city"]
        lead.state = loc_data["state"]
        lead.country = loc_data["country"]
        lead.remote_type = loc_data["remote_type"]
        
        # 1. Geo Filter
        if config["filters"]["geo"]["allowed_countries"] and "USA" not in lead.country:
             if not loc_data["is_us"]:
                 continue

        # 2. Tech Filter (Initial Pass on Title/Snippet)
        lead = tech_filter.process_lead(lead)
        
        if lead.match_score < config["filters"]["roles"]["match_score_threshold"]:
            # Drop spam/irrelevant BEFORE crawling
            continue
            
        candidates_to_crawl.append(lead)
        
    logger.info(f"Identified {len(candidates_to_crawl)} leads to crawl (Skipped {skipped_ids} duplicates/low-quality).")
    
    # 4. Deep Crawl / Enrichment
    if candidates_to_crawl:
        await enrich_leads(candidates_to_crawl)
    
    # 5. Finalize & Persist: LLM Scoring on Full Content
    new_leads_to_save = []
    high_value_leads = []
    new_seen_ids = []

    for lead in candidates_to_crawl:
        # 4.1 LLM Scoring (if enabled and crawled text exists)
        # Now that we have the full description from crawl4ai, let's ask the LLM: "Is this ACTUALLY a match?"
        if lead.full_description and config["llm"]["enabled"]:
            logger.info(f"🤖 LLM Scoring: {lead.role_title}")
            try:
                # This updates lead.match_score and lead.notes based on deep analysis
                lead = llm_manager.score_lead(lead)
            except Exception as e:
                logger.error(f"LLM Scoring failed for {lead.lead_id}: {e}")

        # 4.2 Final Threshold Check
        # If LLM says score is 0.0 or very low, we drop it.
        if lead.match_score < config["filters"]["roles"]["match_score_threshold"]:
            logger.info(f"Dropping lead {lead.role_title} (Score: {lead.match_score})")
            continue

        new_leads_to_save.append(lead)
        new_seen_ids.append(lead.lead_id)
        seen_ids.add(lead.lead_id) 
        
        # Note high value
        threshold = 0.85
        if "discord" in config["notifications"] and "alert_threshold" in config["notifications"]["discord"]:
             threshold = config["notifications"]["discord"]["alert_threshold"]
        
        if lead.match_score >= threshold:
            high_value_leads.append(lead)

    if new_leads_to_save:
        # Convert Pydantic to dict
        leads_dicts = [l.dict() for l in new_leads_to_save]
        store.append_leads(leads_dicts)
        store.add_seen_ids(new_seen_ids)
        
    logger.info(f"Saved {len(new_leads_to_save)} new leads.")
    
    # 6. Notifications
    for lead in high_value_leads:
        instant_notifier.notify(lead)
        
    if new_leads_to_save:
        sorted_leads = sorted(new_leads_to_save, key=lambda x: x.match_score, reverse=True)
        email_notifier.send_digest(sorted_leads[:20])
    
    logger.info("Run Complete.")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
