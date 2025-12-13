import re

class LocationParser:
    def __init__(self):
        self.us_state_codes = [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC"
        ]
        
    def parse(self, raw_location: str) -> dict:
        """
        Returns {
            'city': str,
            'state': str,
            'country': str,
            'remote_type': str (remote, hybrid, onsite, unknown),
            'is_us': bool
        }
        """
        raw = raw_location.lower() if raw_location else ""
        
        # Remote detection
        remote_type = "unsure"
        if "remote" in raw:
            remote_type = "remote"
        elif "hybrid" in raw:
            remote_type = "hybrid"
        elif "onsite" in raw or "on-site" in raw:
            remote_type = "onsite"
        else:
            # Default to onsite if a specific city is present and no remote keyword, 
            # but let's stick to unknown/unsure to be safe
            remote_type = "onsite" 

        # Country detection
        is_us = True # Default assumption for this project scope
        if "canada" in raw or "uk" in raw or "london" in raw or "berlin" in raw:
            # Very basic exclusion
            is_us = False
        
        # State detection
        state = ""
        # Look for ", CA" or "CA" bounded
        upper_raw = raw_location.upper()
        for code in self.us_state_codes:
            # Check for " San Francisco, CA " or " CA" at end
            if re.search(rf"\b{code}\b", upper_raw):
                state = code
                break
        
        # City - minimal effort extraction (take first part before comma)
        city = ""
        if "," in raw_location:
            city_candidate = raw_location.split(",")[0].strip()
            if len(city_candidate) < 30: # Avoid capturing long sentences
                city = city_candidate
        
        return {
            "city": city,
            "state": state,
            "country": "USA" if is_us else "Other",
            "remote_type": remote_type,
            "is_us": is_us
        }
