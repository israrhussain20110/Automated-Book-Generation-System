
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


        # Aggregated research context
        research_context = self.research.get_research_context(title)
        combined_notes = f"{notes}\n\nResearch Context:\n{research_context}"
        
        # Aggregate context
        prev_summaries = self.db.get_chapter_summaries(book_id)
        
        prompt = self.llm.get_chapter_prompt(title, chapter_title, prev_summaries, combined_notes)
        content = self.llm.generate_content(prompt)
        

        # Generate summary for context chaining
        summary_prompt = self.llm.get_summary_prompt(content)
        summary = self.llm.generate_content(summary_prompt)
        
        chapter_id = pre_generated_id or str(uuid.uuid4())
        self.db.save_chapter(chapter_id, book_id, chapter_num, chapter_title, content, summary)
        
        print(f"Chapter {chapter_num} ('{chapter_title}') generated and summarized.")
        return chapter_id
