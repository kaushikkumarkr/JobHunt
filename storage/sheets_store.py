import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
import logging
import json
import os
import base64
from datetime import datetime
from typing import List, Dict, Set, Any, Optional
from config.loader import get_config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class SheetsStore:
    def __init__(self):
        self.config = get_config()
        self.client = self._authenticate()
        self.sheet_name = self.config["storage"]["google_sheets"]["sheet_name"]
        self.sheet = self._get_or_create_sheet()
        
        self.tabs = self.config["storage"]["google_sheets"]["tabs"]
        self._ensure_tabs_exist()

    def _authenticate(self):
        """Authenticate with Google Sheets API using Service Account."""
        creds = None
        
        # Try finding the file locally
        creds_path = self.config["storage"]["google_sheets"]["credentials_path"]
        
        # Check if we have the JSON content in an env var (Base64 encoded) - helpful for GitHub Actions
        env_creds_b64 = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64")
        
        if env_creds_b64:
            try:
                creds_json = json.loads(base64.b64decode(env_creds_b64).decode('utf-8'))
                creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
            except Exception as e:
                logger.error(f"Failed to load credentials from env var: {e}")
        
        if not creds and os.path.exists(creds_path):
             creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)

        if not creds:
            # Fallback for local development if GOOGLE_APPLICATION_CREDENTIALS is set by SDK
            if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                 creds = Credentials.from_service_account_file(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"), scopes=SCOPES)
            else:
                 raise RuntimeError("No valid Google Cloud credentials found. Please set GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64 env var or path in config.")

        return gspread.authorize(creds)

    def _get_or_create_sheet(self):
        # 1. Try opening by ID (Best practice)
        sheet_id = os.environ.get("SHEET_ID")
        if sheet_id:
            try:
                return self.client.open_by_key(sheet_id)
            except Exception as e:
                logger.error(f"Failed to open sheet by ID: {e}")
                # Fallthrough

        # 2. Try opening by name
        try:
            return self.client.open(self.sheet_name)
        except gspread.SpreadsheetNotFound:
            logger.info(f"Sheet '{self.sheet_name}' not found. Attempting create.")
            return self.client.create(self.sheet_name)

    def _ensure_tabs_exist(self):
        existing_titles = [ws.title for ws in self.sheet.worksheets()]
        
        # We ONLY care about the 'leads' tab now.
        leads_tab = self.tabs["leads"]
        
        # Define headers
        headers = [
            "lead_id", "source", "captured_at_utc", "posted_at_utc", "company", "role_title", 
            "role_category", "seniority", "employment_type", "location_raw", "city", "state", 
            "country", "remote_type", "salary_min", "salary_max", "salary_currency", "salary_raw", 
            "tech_stack_keywords", "description_snippet", "hiring_language_flags", "link", 
            "apply_link", "match_score", "matched_keywords", "status", "notes"
        ]

        if leads_tab not in existing_titles:
            logger.info(f"Creating tab '{leads_tab}'")
            ws = self.sheet.add_worksheet(title=leads_tab, rows=1000, cols=30)
            ws.append_row(headers)

    def load_seen_ids(self) -> Set[str]:
        """Load seen IDs directly from the 'leads' tab to avoid managing a second tab."""
        ws = self.sheet.worksheet(self.tabs["leads"])
        try:
            # Assume lead_id is column 1 (index 0)
            # Fetch all values in column 1
            ids = ws.col_values(1)
            if ids:
                # Remove header if present
                if ids[0] == "lead_id":
                    ids = ids[1:]
            return set(ids)
        except Exception as e:
            logger.warning(f"Error loading seen_ids from leads tab: {e}")
            return set()

    def add_seen_ids(self, new_ids: List[str]):
        """No-op: We now persist IDs naturally when appending the lead itself."""
        pass

    def append_leads(self, leads: List[Dict[str, Any]]):
        """Append new leads to the leads tab."""
        if not leads:
            return
            
        ws = self.sheet.worksheet(self.tabs["leads"])
        # We need headers to know order, but we can assume the configured order or read it
        # Safest is to read current headers
        headers = ws.row_values(1)
        if not headers:
             # Fallback if empty
            headers = [
                "lead_id", "source", "captured_at_utc", "posted_at_utc", "company", "role_title", 
                "role_category", "seniority", "employment_type", "location_raw", "city", "state", 
                "country", "remote_type", "salary_min", "salary_max", "salary_currency", "salary_raw", 
                "tech_stack_keywords", "description_snippet", "full_description", "crawled_at", 
                "hiring_language_flags", "link", "apply_link", "match_score", "matched_keywords", 
                "status", "notes"
            ]
        
        rows_to_add = []
        for lead in leads:
            row = []
            for h in headers:
                row.append(str(lead.get(h, "")))
            rows_to_add.append(row)
            
        ws.append_rows(rows_to_add)
        logger.info(f"Appended {len(rows_to_add)} new leads to Sheet.")

    def get_llm_cache_entry(self, text_hash: str) -> Optional[str]:
        # Optimization: storing cache in sheet might be slow if huge.
        # Ideally, we read the whole cache into memory at start if small, 
        # or just skip this if too slow. 
        # For < 5000 rows it's okay.
        ws = self.sheet.worksheet(self.tabs["llm_cache"])
        try:
            # Get all hashes (col 1) and outputs (col 2)
            # This is O(N) but persistent.
            records = ws.get_all_records()
            for r in records:
                if str(r.get("text_hash")) == text_hash:
                    return r.get("llm_output")
        except Exception:
            return None
        return None

    def save_llm_cache_entry(self, text_hash: str, output: str, model: str):
        ws = self.sheet.worksheet(self.tabs["llm_cache"])
        now = datetime.utcnow().isoformat()
        ws.append_row([text_hash, output, now, model])

