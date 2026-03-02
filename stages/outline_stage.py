
import json
import uuid
from core.db_manager import DBManager
from core.llm_manager import LLMManager

class OutlineStage:
    def __init__(self, db: DBManager, llm: LLMManager, notifier: 'Notifier' = None):
        self.db = db
        self.llm = llm
        self.notifier = notifier

    def process(self, title: str, notes_on_outline_before: str):
        """Logic: Only generate outlines if notes_on_outline_before exists."""
        if not notes_on_outline_before:
            print(f"Skipping '{title}': Missing required notes_on_outline_before.")
            if self.notifier:
                self.notifier.notify_pause_or_error(title, "Missing required notes_on_outline_before")
            return None

        book_id = str(uuid.uuid4())
        self.db.create_book(book_id, title)
        
        prompt = self.llm.get_outline_prompt(title, notes_on_outline_before)
        outline_content = self.llm.generate_content(prompt)
        
        outline_id = book_id
        self.db.save_outline(outline_id, book_id, outline_content, notes_on_outline_before)
        
        print(f"Outline generated for '{title}' (Book ID: {book_id})")
        return book_id, outline_id

    def handle_feedback(self, outline_id: str, status: str, notes_after: str = None):
        """
        Logic:
        yes: wait for notes.
        no_notes_needed: proceed.
        no/empty: pause.
        """
        self.db.update_outline_status(outline_id, status, notes_after)
        
        # We need the book title if possible for notifications, simpler if just ID for now
        book_id = outline_id
        
        if status == "yes":
            print("Status is 'yes'. Waiting for notes to regenerate.")
            if self.notifier:
                self.notifier.waiting_for_notes("Outline")
            return "waiting"
        elif status == "no_notes_needed":
            print("Outline approved. Ready for chapter generation.")
            return "proceeding"
        else:
            print("Status is empty or 'no'. Paused.")
            if self.notifier:
                self.notifier.notify_pause_or_error(f"Book ID {book_id}", "User requested pause or provided empty status")
            return "paused"
