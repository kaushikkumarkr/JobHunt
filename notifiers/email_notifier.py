import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from sources.base import JobLead
from config.loader import get_config
import os

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self):
        self.config = get_config()
        self.enabled = self.config["notifications"]["email"]["enabled"]
        self.sender = self.config["notifications"]["email"]["sender_user"]
        self.recipient = self.config["notifications"]["email"]["recipient_email"]
        
        # We expect an App Password for Gmail in env var
        self.password = os.environ.get("EMAIL_APP_PASSWORD")

    def send_digest(self, leads: List[JobLead]):
        if not self.enabled or not leads or not self.password:
            return

        subject = f"Job Digest: {len(leads)} New Tech Roles"
        body_parts = ["<h2>New Tech Jobs Found</h2><ul>"]
        
        for lead in leads:
            score = round(lead.match_score * 100)
            item = f"""
            <li>
                <strong><a href="{lead.link}">{lead.role_title}</a></strong> at {lead.company} 
                <br/>
                Match: {score}% | {lead.location_raw} | {lead.role_category}
            </li>
            """
            body_parts.append(item)
        
        body_parts.append("</ul>")
        html_content = "".join(body_parts)
        
        self._send(subject, html_content)

    def _send(self, subject, html_body):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = self.recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html_body, 'html'))

            # Standard Gmail SMTP
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.sender, self.password)
            text = msg.as_string()
            server.sendmail(self.sender, self.recipient, text)
            server.quit()
            logger.info(f"Email sent to {self.recipient}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
