
import os
import argparse
import json
from dotenv import load_dotenv

load_dotenv()
from core.db_manager import DBManager
from core.llm_manager import LLMManager
from stages.outline_stage import OutlineStage
from stages.chapter_stage import ChapterStage
from stages.compilation_stage import CompilationStage
from core.notifier import Notifier

def main():
    parser = argparse.ArgumentParser(description="Automated Book Generation System")
    parser.add_argument("--title", required=True, help="Title of the book")
    parser.add_argument("--notes", help="Initial notes for the outline")
    parser.add_argument("--mode", choices=["outline", "chapter", "compile", "full"], default="full")
    parser.add_argument("--db", choices=["sqlite", "supabase"], default="sqlite")
    parser.add_argument("--interactive", action="store_true", help="Pause for human editor feedback")
    parser.add_argument("--teams-webhook", help="MS Teams Webhook URL")
    parser.add_argument("--email", help="Recipient Email for alerts")
    
    args = parser.parse_args()

    # Configure Email
    email_address = args.email or os.getenv('SMTP_USER')
    smtp_config = None
    if email_address and os.getenv('SMTP_SERVER') and os.getenv('SMTP_PASS'):
        smtp_config = {
            'server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
            'port': int(os.environ.get('SMTP_PORT', 587)),
            'username': os.environ.get('SMTP_USER'),
            'password': os.environ.get('SMTP_PASS'),
            'sender_email': os.environ.get('SMTP_USER'),
            'receiver_email': email_address
        }

    teams_webhook = args.teams_webhook or os.environ.get('TEAMS_WEBHOOK_URL')

    # Initialize components
    db = DBManager(db_type=args.db)
    llm = LLMManager()
    notifier = Notifier(teams_webhook_url=teams_webhook, smtp_config=smtp_config)
    
    outline_stage = OutlineStage(db, llm)
    chapter_stage = ChapterStage(db, llm)
    compilation_stage = CompilationStage(db)


    if args.mode in ["outline", "full"]:
        res = outline_stage.process(args.title, args.notes)
        if res:
            book_id, outline_id = res
            notifier.outline_ready(args.title)
            
            # Fetch outline content to parse chapters
            if args.db == "sqlite":
                db.cursor.execute("SELECT content FROM outlines WHERE id = ?", (outline_id,))
                content = db.cursor.fetchone()[0]
            else:
                content = db.supabase.table("outlines").select("content").eq("id", outline_id).single().execute().data["content"]
            
            try:
                # Basic cleaning of LLM response if it has triple backticks
                json_str = content.strip().replace("```json", "").replace("```", "")
                outline_json = json.loads(json_str)
                chapters_list = outline_json.get("chapters", [])
            except Exception as e:
                print(f"Failed to parse outline JSON: {e}. Fallback to dummy.")
                chapters_list = ["Chapter 1", "Chapter 2", "Chapter 3"]

            if args.interactive:
                notifier.waiting_for_notes(0) # 0 to indicate outline
                status = input(f"\n[HUMAN REVIEW] Outline generated. Please review Db.\nApprove outline? [yes/no/no_notes_needed]: ").strip()
                notes_after = ""
                if status == "yes":
                    notes_after = input("[HUMAN REVIEW] Enter notes to regenerate: ").strip()
                
                outline_stage.handle_feedback(outline_id, status, notes_after)
                
                if status != "no_notes_needed":
                    print("Halting generation. Outline requires regeneration/more notes.")
                    return
            else:
                # Simulating "no_notes_needed" for full automated demo
                outline_stage.handle_feedback(outline_id, "no_notes_needed")

    if args.mode in ["chapter", "full"]:
        book_id = "demo_book" if args.mode == "chapter" else book_id
        # Use parsed chapters if available, else fallback
        if 'chapters_list' not in locals():
            chapters_list = ["Chapter 1", "Chapter 2", "Chapter 3"]
            
        for i, ch_title in enumerate(chapters_list):
            status = "no_notes_needed"
            notes = ""
            
            if args.interactive:
                print(f"\n[HUMAN REVIEW] Up Next: Chapter {i+1} - '{ch_title}'")
                status = input("Proceed with generation? [yes (I have notes)/no (Pause)/no_notes_needed (Proceed)]: ").strip()
                
                if status == "yes":
                    notifier.waiting_for_notes(i + 1)
                    notes = input("[HUMAN REVIEW] Enter notes for this chapter: ").strip()
                elif status == 'no' or not status:
                    print(f"Halting generation at Chapter {i+1}.")
                    notifier.notify(f"Generation paused at Chapter {i+1}. Waiting for human editor.")
                    return
                    
            chapter_stage.generate_next_chapter(
                book_id, i + 1, args.title, ch_title, status, notes
            )
            
    if args.mode in ["compile", "full"]:
        book_id = "demo_book" if args.mode == "compile" else book_id
        compilation_stage.compile_book(book_id, args.title)
        notifier.final_draft_compiled(args.title)

if __name__ == "__main__":
    main()
