import requests
import smtplib
from email.mime.text import MIMEText

class Notifier:
    """Handles notifications via MS Teams webhooks and Email."""
    def __init__(self, teams_webhook_url: str = None, smtp_config: dict = None):
        self.teams_webhook_url = teams_webhook_url
        self.smtp_config = smtp_config

    def notify(self, message: str, subject: str = "Book System Alert"):
        print(f"NOTIFICATION: {message}")
        if self.teams_webhook_url:
            try:
                requests.post(self.teams_webhook_url, json={"text": message})
            except Exception as e:
                print(f"Failed to send Teams notification: {e}")
                
        if self.smtp_config:
            try:
                msg = MIMEText(message)
                msg['Subject'] = subject
                msg['From'] = self.smtp_config['sender_email']
                msg['To'] = self.smtp_config['receiver_email']

                with smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port']) as server:
                    server.starttls()
                    server.login(self.smtp_config['username'], self.smtp_config['password'])
                    server.send_message(msg)
            except Exception as e:
                print(f"Failed to send Email notification: {e}")

    def outline_ready(self, book_title: str):
        self.notify(f"Outline for '{book_title}' is ready and needs review.")

    def waiting_for_notes(self, chapter_num: int):
        self.notify(f"Waiting for chapter notes for Chapter {chapter_num}.")

    def final_draft_compiled(self, book_title: str):
        self.notify(f"Final draft for '{book_title}' has been compiled.")
        
    def notify_pause_or_error(self, book_title: str, reason: str):
        self.notify(f"System Paused/Error for '{book_title}': {reason}")
