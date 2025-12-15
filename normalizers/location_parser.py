import re

class LocationParser:
    def __init__(self):
        # Allowlist: Strictly US Indicators
        # Matches "United States", "USA", "U.S.", "US" (as word)
        self.us_country_indicators = [
            r"\bunited states\b", r"\busa\b", r"\bu\.s\.\b", r"\bu\.s\b", r"\bus\b"
        ]
        
        self.us_state_codes = [
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC"
        ]
        
        self.us_state_names = [
            "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "georgia",
            "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland",
            "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
            "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
            "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
            "district of columbia"
        ]

        # Blocklist: Explicit Foreign indicators (to override vague matches)
        self.foreign_indicators = [
            "india", "uk", "united kingdom", "london", "canada", "toronto", "vancouver", "ontario", 
            "germany", "berlin", "munich", "france", "paris", "spain", "madrid", "barcelona", 
            "australia", "sydney", "melbourne", "china", "japan", "tokyo", "singapore", 
            "brazil", "mexico", "dubai", "uae", "netherlands", "amsterdam", "sweden", "stockholm",
            "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai" # Common Indian tech hubs
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
        raw = raw_location.lower().strip() if raw_location else ""
        
        # Remote detection
        remote_type = "unsure"
        if "remote" in raw:
            remote_type = "remote"
        elif "hybrid" in raw:
            remote_type = "hybrid"
        elif "onsite" in raw or "on-site" in raw:
            remote_type = "onsite"
        else:
            remote_type = "onsite" 

        # ---------------------------------------------------------
        # STRICT LOCATION FILTERING (US ONLY)
        # ---------------------------------------------------------
        is_us = False 
        
        # 1. IMMEDIATE FAIL: If explicit foreign country/city present
        for foreign in self.foreign_indicators:
            if re.search(rf"\b{foreign}\b", raw):
                return {
                    'city': "Unknown", 'state': "Unknown", 'country': "Non-US",
                    'remote_type': remote_type, 'is_us': False
                }

        # 2. CHECK PASS: Must match US Indicator OR US State
        
        # Check Country ("United States", "USA", "US")
        for indicator in self.us_country_indicators:
            if re.search(indicator, raw):
                is_us = True
                break
                
        # Check State Name ("California", "New York")
        if not is_us:
            for state_name in self.us_state_names:
                if re.search(rf"\b{state_name}\b", raw):
                    is_us = True
                    break

        # Check State Code ("San Francisco, CA", "Seattle WA")
        if not is_us:
            upper_raw = raw_location.upper() # Use original case for state codes
            for code in self.us_state_codes:
                # Regex looks for ", CA" or " CA " or "NY" at end of string
                # \b matches word boundary.
                if re.search(rf"\b{code}\b", upper_raw):
                    is_us = True
                    break

        # ---------------------------------------------------------

        # State detection for saving (Extract the code)
        state_extracted = ""
        upper_raw = raw_location.upper()
        for code in self.us_state_codes:
            if re.search(rf"\b{code}\b", upper_raw):
                state_extracted = code
                break
                
        return {
            'city': "Unknown", 
            'state': state_extracted,
            'country': "USA" if is_us else "Unknown",
            'remote_type': remote_type,
            'is_us': is_us
        }
