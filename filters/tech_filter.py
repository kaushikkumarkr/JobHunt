from config.loader import get_config
from sources.base import JobLead
import re

class TechFilter:
    def __init__(self):
        self.config = get_config()
        self.filters = self.config["filters"]["roles"]
        
    def process_lead(self, lead: JobLead) -> JobLead:
        """
        Analyzes the lead, updates its match score, keywords, and role category.
        Returns the modified lead.
        """
        text_corpus = (lead.role_title + " " + lead.description_snippet + " " + lead.tech_stack_keywords).lower()
        
        # 1. Check Exclude Keywords
        for bad_word in self.filters["exclude_keywords"]:
            if re.search(rf"\b{bad_word.lower()}\b", text_corpus):
                lead.match_score = 0.0
                lead.notes = f"Excluded by keyword: {bad_word}"
                return lead

        # 1.5 Anti-Spam (Non-English characters)
        # Reject if title contains common non-English ranges (Chinese, Cyrillic, etc.)
        if re.search(r"[\u4e00-\u9fff\u0400-\u04FF]", lead.role_title):
            lead.match_score = 0.0
            lead.notes = "Excluded: Non-English characters detected"
            return lead

        # 2. Check Include Keywords & Calculate Score
        hits = []
        for word in self.filters["include_keywords"]:
            if re.search(rf"\b{word.lower()}\b", text_corpus):
                hits.append(word)
        
        lead.matched_keywords = ", ".join(hits)
        
        # Simple scoring: Base on % of matched keywords? Or just existence?
        # Let's say: 1 mandatory keyword match = 0.5. More matches = higher.
        # Max score 1.0.
        
        if hits:
            # Normalize: 1 match = 0.6, 3 matches = 0.8, 5+ = 1.0
            raw_score = 0.5 + (len(hits) * 0.1)
            lead.match_score = min(raw_score, 1.0)
        else:
            # Permissive Mode: If no keywords found, but no bad words found either,
            # give it a "Maybe" score so we can crawl it and let the LLM decide.
            # Snippets are often too short to contain specific tech stack keywords.
            lead.match_score = 0.1
            lead.notes = "Snippet vague, need deep crawl to confirm."

        # 3. Categorize Role
        lead.role_category = self._categorize(lead.role_title)
        
        return lead

    def _categorize(self, title: str) -> str:
        title = title.lower()
        if "data" in title or "analyst" in title:
            return "data"
        if "backend" in title or "back-end" in title:
            return "backend"
        if "frontend" in title or "front-end" in title or "ui" in title:
            return "frontend"
        if "full stack" in title or "fullstack" in title:
            return "fullstack"
        if "machine learning" in title or "ml" in title or "ai" in title:
            return "ml-ai"
        if "devops" in title or "sre" in title or "cloud" in title:
            return "devops-sre"
        if "security" in title:
            return "security"
        return "other-tech"
