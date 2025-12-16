import re

class LocationParser:
    def __init__(self):
        # 1. MAJOR TECH HUBS ALLOWLIST (STRICT)
        # User requested: "NY, NJ, major cities"
        self.allowed_hubs = [
            # Generic US (Re-enabled to fix "0 leads" issue, relying on -India query blocker)
            r"united states", r"usa", r"us", r"remote",

            # New York Area
            r"new york", r"ny", r"nyc", r"manhattan", r"brooklyn", r"new jersey", r"nj", r"jersey city", r"hoboken",
            
            # Bay Area / California
            r"san francisco", r"sf", r"bay area", r"palo alto", r"mountain view", r"sunnyvale", r"menlo park", 
            r"santa clara", r"san jose", r"cupertino", r"redwood city", r"los angeles", r"la", r"san diego", r"california", r"ca",
            
            # Seattle Area
            r"seattle", r"redmond", r"bellevue", r"washington", r"wa",
            
            # Texas
            r"austin", r"dallas", r"houston", r"texas", r"tx",
            
            # East Coast / Other
            r"boston", r"cambridge", r"massachusetts", r"ma",
            r"chicago", r"illinois", r"il",
            r"denver", r"boulder", r"colorado", r"co",
            r"washington dc", r"d\.c\.", r"virginia", r"va", r"maryland", r"md"
        ]

        # Blocklist: Explicit Foreign indicators (Strict Global Filter)
        self.foreign_indicators = [
            "india", "uk", "united kingdom", "london", "canada", "toronto", "vancouver", "ontario", 
            "germany", "berlin", "munich", "france", "paris", "spain", "madrid", "barcelona", 
            "australia", "sydney", "melbourne", "china", "japan", "tokyo", "singapore", 
            "brazil", "mexico", "dubai", "uae", "netherlands", "amsterdam", "sweden", "stockholm",
            
            # India Specific Leakage Blockers
            "bangalore", "mumbai", "delhi", "hyderabad", "pune", "chennai", "gurgaon", "noida", "kolkata", "ahmedabad",
            "emea", "apac", "latam"
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
        # STRICT HUB FILTERING (Major US Cities Only)
        # ---------------------------------------------------------
        is_allowed = False 
        
        # 1. IMMEDIATE FAIL: If explicit foreign country/city present
        for foreign in self.foreign_indicators:
            if re.search(rf"\b{foreign}\b", raw):
                return {
                    'city': "Unknown", 'state': "Unknown", 'country': "Non-US",
                    'remote_type': remote_type, 'is_us': False
                }

        # 2. CHECK PASS: Must match a Major Tech Hub
        for hub in self.allowed_hubs:
            # Word boundary check is risky for abbreviations like "NY", but necessary for "CA" vs "Africa"
            # We use loose matching for long names ("new york") and strict for short codes
            
            if len(hub.replace("\\", "")) <= 2: 
                # Strict boundary for short codes (NY, CA, WA)
                if re.search(rf"\b{hub}\b", raw):
                    is_allowed = True
                    break
            else:
                # Loose matching for city names ("san francisco")
                if hub in raw:
                    is_allowed = True
                    break

        return {
            'city': "Unknown", 
            'state': "Hub",
            'country': "USA" if is_allowed else "Unknown",
            'remote_type': remote_type,
            'is_us': is_allowed
        }
