import os.path
import base64
import logging
from typing import List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import email
from bs4 import BeautifulSoup

from sources.base import BaseSource, JobLead
from config.loader import get_config
from utils.retries import retry_with_backoff

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

class GmailIngestSource(BaseSource):
    def __init__(self):
        super().__init__()
        self.config = get_config()
        self.service = None
        if self.config["sources"]["gmail_ingest"]["enabled"]:
            self.service = self._authenticate()

    def _authenticate(self):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        # Check env var first for CI/CD
        token_json = os.environ.get("GMAIL_TOKEN_JSON")
        if token_json:
            import json
            info = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(info, SCOPES)
        elif os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        # If there are no (valid) credentials available, let the user log in.
        # NOTE: In a headless server environment (GitHub Actions), you MUST generate token.json locally
        # and save it as a secret (base64 or json string) to env.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Could not refresh token: {e}")
                    return None
            else:
                # We cannot open browser in headless mode. 
                # If we are here in production, we fail gracefully.
                logger.warning("No valid Gmail token found and cannot start auth flow in headless mode.")
                return None

        return build('gmail', 'v1', credentials=creds)

    @retry_with_backoff(retries=2)
    def fetch_leads(self) -> List[JobLead]:
        if not self.service:
            logger.info("Gmail service not initialized. Skipping.")
            return []

        leads = []
        try:
            query = self.config["sources"]["gmail_ingest"]["search_query"]
            # Get messages from last 24h to avoid deep crawling
            # Using 'q' parameter with 'newer_than:1d'
            full_query = f"{query} newer_than:1d"
            
            results = self.service.users().messages().list(userId='me', q=full_query, maxResults=20).execute()
            messages = results.get('messages', [])

            for msg in messages:
                full_msg = self.service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                lead = self._parse_message(full_msg)
                if lead:
                    leads.append(lead)
                    
        except Exception as e:
            logger.error(f"Error fetching Gmail leads: {e}")
            
        return leads

    def _parse_message(self, msg_payload) -> JobLead:
        try:
            payload = msg_payload['payload']
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), "No Subject")
            from_header = next((h['value'] for h in headers if h['name'] == 'From'), "")
            
            # Simple heuristic parsing
            # This is high variance. We rely on finding links and basic text.
            
            snippet = msg_payload.get('snippet', '')
            
            # Get body
            body_data = ""
            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/html':
                        body_data = part['body'].get('data', '')
                        break
            elif 'body' in payload:
                body_data = payload['body'].get('data', '')
                
            if not body_data: 
                return None
                
            decoded_html = base64.urlsafe_b64decode(body_data).decode('utf-8')
            soup = BeautifulSoup(decoded_html, "html.parser")
            
            # Heuristic: Find the first major link that looks like a job post
            # Or assume the email IS the alert
            
            # If LinkedIn Job Alert
            if "linkedin.com" in from_header:
                # LinkedIn alerts usually have lists of jobs. 
                # Complexity: parsing a digest. 
                # For MVP, we might just grab the top recommended job or treating the whole email as a "Lead" to investigate?
                # A "Lead" should be a specific job.
                # Let's try to extract ONE job for now to prove the point, or multiple if we refactor return type (fetch_leads returns List)
                pass
                
            # Generic fallback: Treat as single lead if subject looks promising
            # Extract links
            links = [a['href'] for a in soup.find_all('a', href=True)]
            valid_link = next((l for l in links if "linkedin.com/jobs/view" in l or "indeed.com/rc/clk" in l), "")
            
            if valid_link:
                return JobLead(
                    source="gmail_alert",
                    company="See Link", # Hard to parse without specific templates
                    role_title=subject,
                    link=valid_link,
                    description_snippet=snippet[:200]
                )
                
        except Exception as e:
            logger.warning(f"Failed to parse email: {e}")
            return None
        return None
