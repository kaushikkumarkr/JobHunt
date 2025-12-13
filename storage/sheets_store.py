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
        
        # Define headers for safety
        headers_map = {
            self.tabs["leads"]: [
                "lead_id", "source", "captured_at_utc", "posted_at_utc", "company", "role_title", 
                "role_category", "seniority", "employment_type", "location_raw", "city", "state", 
                "country", "remote_type", "salary_min", "salary_max", "salary_currency", "salary_raw", 
                "tech_stack_keywords", "description_snippet", "hiring_language_flags", "link", 
                "apply_link", "match_score", "matched_keywords", "status", "notes"
            ],
            self.tabs["seen_ids"]: ["lead_id", "first_seen_at_utc"],
            self.tabs["applied_tracker"]: ["lead_id", "applied_at_utc", "status", "notes"],
            self.tabs["llm_cache"]: ["text_hash", "llm_output", "created_at_utc", "model_used"]
        }

        for tab_key, tab_name in self.tabs.items():
            if tab_name not in existing_titles:
                logger.info(f"Creating tab '{tab_name}'")
                ws = self.sheet.add_worksheet(title=tab_name, rows=1000, cols=30)
                # Init headers
                if tab_name in headers_map:
                    ws.append_row(headers_map[tab_name])
            else:
                # Optional: Check headers if needed, but risky to overwrite
                pass

    def load_seen_ids(self) -> Set[str]:
        """Load all lead IDs from the seen_ids tab to memory for fast deduping."""
        ws = self.sheet.worksheet(self.tabs["seen_ids"])
        # Assuming lead_id is column 1 (index 0)
        # Get all values from col 1, skipping header
        try:
            ids = ws.col_values(1)[1:] 
            return set(ids)
        except Exception as e:
            logger.warning(f"Error loading seen_ids: {e}")
            return set()

    def add_seen_ids(self, new_ids: List[str]):
        """Batch append new seen IDs."""
        if not new_ids:
            return
        
        ws = self.sheet.worksheet(self.tabs["seen_ids"])
        now = datetime.utcnow().isoformat()
        rows = [[lid, now] for lid in new_ids]
        ws.append_rows(rows)

    def append_leads(self, leads: List[Dict[str, Any]]):
        """Append new leads to the leads tab."""
        if not leads:
            return

        ws = self.sheet.worksheet(self.tabs["leads"])
        headers = ws.row_values(1)
        
        rows_to_add = []
        for lead in leads:
            row = []
            for h in headers:
                row.append(str(lead.get(h, ""))) # Ensure string conversion for safety
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

