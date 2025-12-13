from abc import ABC, abstractmethod
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class JobLead(BaseModel):
    lead_id: str = "" # To be computed by runner
    source: str
    captured_at_utc: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    posted_at_utc: Optional[str] = ""
    company: str
    role_title: str
    role_category: str = "unknown" # To be filled by filter
    seniority: str = "unknown"
    employment_type: str = "unknown"
    location_raw: str
    city: str = ""
    state: str = ""
    country: str = "USA"
    remote_type: str = "unknown"
    salary_min: Optional[str] = ""
    salary_max: Optional[str] = ""
    salary_currency: str = "USD"
    salary_raw: str = ""
    tech_stack_keywords: str = ""
    description_snippet: str = ""
    hiring_language_flags: str = ""
    link: str
    apply_link: str = ""
    match_score: float = 0.0
    matched_keywords: str = ""
    status: str = "new"
    notes: str = ""

class BaseSource(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def fetch_leads(self) -> List[JobLead]:
        """Fetch new job leads from the source."""
        pass
