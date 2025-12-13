import asyncio
import logging
import random
from typing import List
from crawl4ai import AsyncWebCrawler
from datetime import datetime

# Local imports
from sources.base import JobLead

logger = logging.getLogger(__name__)

async def crawl_lead(crawler: AsyncWebCrawler, lead: JobLead):
    """
    Crawls a single lead's link and updates its full_description.
    """
    if not lead.link or "http" not in lead.link:
        return

    try:
        # random sleep to be polite
        await asyncio.sleep(random.uniform(1.0, 3.0))
        
        logger.info(f"🕸️ Crawling: {lead.role_title} ({lead.company})")
        
        # arun returns a CrawlResult
        result = await crawler.arun(url=lead.link)
        
        if result.success:
            # Basic Auth Wall Check
            # content length < 500 often means a login wall on LinkedIn
            if len(result.markdown) < 500 and ("Sign In" in result.markdown or "Join LinkedIn" in result.markdown):
                logger.warning(f"⚠️ Auth Wall hit for {lead.link} (keeping snippet)")
                return
            
            lead.full_description = result.markdown
            lead.crawled_at = datetime.utcnow().isoformat()
            lead.notes += " [Crawled]"
        else:
            logger.warning(f"❌ Crawl failed for {lead.link}: {result.error_message}")
            
    except Exception as e:
        logger.error(f"❌ Crawl error for {lead.link}: {e}")

async def enrich_leads(leads: List[JobLead]):
    """
    Takes a list of JobLeads, visits each URL, and populates 'full_description'.
    Process in polite batches.
    """
    if not leads:
        return

    logger.info(f"🕷️ Starting Deep Crawl for {len(leads)} leads...")
    
    # Context manager handles browser lifecycle
    async with AsyncWebCrawler(verbose=False) as crawler:
        # Batch size 3 to be safe
        batch_size = 3
        for i in range(0, len(leads), batch_size):
            batch = leads[i : i + batch_size]
            
            tasks = [crawl_lead(crawler, lead) for lead in batch]
            await asyncio.gather(*tasks)
            
            # Delay between batches
            await asyncio.sleep(2)
            
    logger.info("🕷️ Deep Crawl Complete.")
