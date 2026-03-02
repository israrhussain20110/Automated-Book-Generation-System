
import uuid
from core.db_manager import DBManager
from core.llm_manager import LLMManager
from core.research_manager import ResearchManager

class ChapterStage:
    def __init__(self, db: DBManager, llm: LLMManager, notifier: 'Notifier' = None):
        self.db = db
        self.llm = llm
        self.notifier = notifier
        self.research = ResearchManager()

    def generate_next_chapter(self, book_id: str, chapter_num: int, title: str, chapter_title: str, status: str, notes: str = "", pre_generated_id: str = None):
        """
        Logic:
        Use summary of all previous chapters as context.
        If chapter_notes_status = yes, wait for notes.
        If no_notes_needed, proceed.
        If no/empty, pause.
        """
        if status == "yes" and not notes:
            print(f"Waiting for notes for Chapter {chapter_num}.")
            if self.notifier:
                self.notifier.waiting_for_notes(chapter_num)
            return None
        elif status == "no" or not status:
            print(f"Chapter {chapter_num} generation paused.")
            if self.notifier:
                self.notifier.notify_pause_or_error(title, f"User requested pause on chapter {chapter_num} generation")
            return None

        # Pre-insert stub to DB so frontend sees it as generating immediately
        chapter_id = pre_generated_id or self.db.insert_stub_chapter(book_id, chapter_num, chapter_title)

        # Aggregated research context
        research_context = self.research.get_research_context(title)
        combined_notes = f"{notes}\n\nResearch Context:\n{research_context}"
        
        # Aggregate context
        prev_summaries = self.db.get_chapter_summaries(book_id)
        
        # Single LLM call: generate chapter content (skip slow web research)
        prompt = self.llm.get_chapter_prompt(title, chapter_title, prev_summaries, notes)
        content = self.llm.generate_content(prompt)

        # Quick inline summary (single sentence, no separate LLM call)
        summary = content[:200] if len(content) > 200 else content
        
        # Save replaces or updates the stub
        self.db.save_chapter(chapter_id, book_id, chapter_num, chapter_title, content, summary)
        if self.db.db_type == "sqlite":
            self.db.cursor.execute("UPDATE chapters SET chapter_notes_status = 'pending_review' WHERE id = ?", (chapter_id,))
            self.db.conn.commit()
        else:
            self.db.supabase.table("chapters").update({"status": "pending_review"}).eq("id", chapter_id).execute()
        
        print(f"Chapter {chapter_num} ('{chapter_title}') generated and summarized.")
        return chapter_id
