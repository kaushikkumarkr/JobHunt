import logging
import hashlib
from typing import List

from config.loader import get_config
from utils.logging import setup_logging
from storage.sheets_store import SheetsStore
from sources.ats_scrapers import ATSScraper
from sources.gmail_ingest import GmailIngestSource
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

def main():
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
        
    # Gmail
    if config["sources"]["gmail_ingest"]["enabled"]:
        logger.info("Fetching Gmail leads...")
        all_raw_leads.extend(gmail_source.fetch_leads())
        
    logger.info(f"Fetched {len(all_raw_leads)} raw leads.")
    
    # 4. Process & Filter
    new_leads_to_save = []
    high_value_leads = []
    
    new_seen_ids = []

    for lead in all_raw_leads:
        # ID Generation
        lid = generate_lead_id(lead)
        if lid in seen_ids:
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
        
        # Filter: US Only Check
        if config["filters"]["geo"]["allowed_countries"] and "USA" not in lead.country:
             # Skip non-US if strict
             # But if location parser says "Other", we skip.
             # If remote, we might be lenient? Let's check "is_us" flag.
             if not loc_data["is_us"]:
                 continue

        # Tech Filter & Scoring
        lead = tech_filter.process_lead(lead)
        
        if lead.match_score < config["filters"]["roles"]["match_score_threshold"]:
            continue
            
        # Optional: LLM Refinement for ambiguous high-potential leads
        # If score is good but some fields missing? 
        # For now, just keep it simple as per "Minimize User" rule.
        
        # Finalize
        new_leads_to_save.append(lead)
        new_seen_ids.append(lid)
        seen_ids.add(lid) # Update local set to avoid double counting in same run
        
        # Note high value
        if lead.match_score >= config["notifications"]["telegram"]["alert_threshold"]:
            high_value_leads.append(lead)

    # 5. Persist
    if new_leads_to_save:
        # Convert Pydantic to dict
        leads_dicts = [l.dict() for l in new_leads_to_save]
        store.append_leads(leads_dicts)
        store.add_seen_ids(new_seen_ids)
        
    logger.info(f"Saved {len(new_leads_to_save)} new leads.")

    # 6. Notifications
    # Instant
    for lead in high_value_leads:
        instant_notifier.notify(lead)
        
    # Hourly Digest
    if new_leads_to_save:
        # Sort by score
        sorted_leads = sorted(new_leads_to_save, key=lambda x: x.match_score, reverse=True)
        # Send top 20 in digest
        email_notifier.send_digest(sorted_leads[:20])

    logger.info("Run Complete.")

if __name__ == "__main__":
    main()
