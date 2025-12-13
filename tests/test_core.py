import pytest
import sys
import os

# Ensure we can import from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from filters.tech_filter import TechFilter
from normalizers.location_parser import LocationParser
from sources.base import JobLead

def test_tech_filter_scoring():
    f = TechFilter()
    
    # Test High Match
    lead1 = JobLead(
        source="test",
        company="TestCorp",
        role_title="Senior Python Backend Engineer",
        description_snippet="We need python, aws, and kubernetes skills.",
        link="http://example.com",
        tech_stack_keywords="python aws k8s",
        location_raw="New York, NY"
    )
    res1 = f.process_lead(lead1)
    assert "backend" in res1.role_category
    assert res1.match_score >= 0.6
    
    # Test Exclude
    lead2 = JobLead(
        source="test",
        company="BadCorp",
        role_title="Backend Recruiter",
        link="http://example.com",
        description_snippet="Hire people.",
        location_raw="Remote"
    )
    res2 = f.process_lead(lead2)
    assert res2.match_score == 0.0
    assert "Excluded" in res2.notes

def test_location_parser():
    p = LocationParser()
    
    # US City State
    r1 = p.parse("San Francisco, CA")
    # Our parser does not title case unless the input was.
    # It extracts as-is or lowercases? 
    # The code says: city_candidate = raw_location.split(",")[0].strip()
    # It does not lowercase current output of city.
    assert r1["city"] == "San Francisco"
    assert r1["state"] == "CA"
    assert r1["country"] == "USA"
    
    # Remote
    r2 = p.parse("Remote (US)")
    assert r2["remote_type"] == "remote"
    assert r2["is_us"] is True

    # Non-US
    r3 = p.parse("London, UK")
    assert r3["is_us"] is False

def test_dedupe_id_generation():
    from runner import generate_lead_id
    lead = JobLead(
        source="s", company="ACME", role_title="Engineer", link="http://acme.com/job/1",
        location_raw="NY"
    )
    # Ensure deterministic
    id1 = generate_lead_id(lead)
    id2 = generate_lead_id(lead)
    assert id1 == id2
    assert len(id1) == 64 # sha256 hex
