import os
import time
import json
import uuid
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

from core.db_manager import DBManager
from core.llm_manager import LLMManager
from stages.outline_stage import OutlineStage
from stages.chapter_stage import ChapterStage
from stages.compilation_stage import CompilationStage

def sync_input_file(db: DBManager, filepath: str = "input.xlsx"):
    """Reads input data and pushes new books into the DB."""
    if not os.path.exists(filepath):
        # Create a dummy file if it doesn't exist for the sake of the demo
        print(f"[{time.strftime('%H:%M:%S')}] Input file '{filepath}' not found. Creating a starter file...")
        df_dummy = pd.DataFrame({
            "title": ["The AI Revolution", "Space Colonization"],
            "notes_on_outline_before": ["Focus on ethics and modern usage.", "Focus on Mars and future tech."]
        })
        df_dummy.to_excel(filepath, index=False)
        
    df = pd.read_excel(filepath) if filepath.endswith('.xlsx') else pd.read_csv(filepath)
    for _, row in df.iterrows():
        title = str(row.get('title', '')).strip()
        notes = str(row.get('notes_on_outline_before', '')).strip()
        
        if not title or title.lower() == 'nan':
            continue
            
        if db.db_type == "sqlite":
            db.cursor.execute("SELECT id FROM books WHERE title = ?", (title,))
            existing = db.cursor.fetchone()
            if not existing:
                book_id = str(uuid.uuid4())
                print(f"[{time.strftime('%H:%M:%S')}] Syncing new book from spreadsheet: '{title}'")
                db.cursor.execute(
                    "INSERT INTO books (id, title, book_output_status, final_review_notes_status, final_review_notes) VALUES (?, ?, ?, ?, ?)",
                    (book_id, title, 'drafting', 'pending_review', '') # Initialize safely
                )
                db.cursor.execute(
                    "INSERT INTO outlines (id, book_id, content, notes_before, status) VALUES (?, ?, ?, ?, ?)",
                    (book_id, book_id, "", notes, 'not_started')
                )
                db.conn.commit()
        else:
            # Supabase version of checking and syncing
            res = db.supabase.table("books").select("id").eq("title", title).execute()
            if not res.data:
                book_id = str(uuid.uuid4())
                print(f"[{time.strftime('%H:%M:%S')}] Syncing new book from spreadsheet: '{title}'")
                db.supabase.table("books").insert({
                    "id": book_id, "title": title, "status": "drafting", "final_review_notes_status": "pending_review", "final_review_notes": ""
                }).execute()
                
                db.supabase.table("outlines").insert({
                    "id": book_id, "book_id": book_id, "content": "", "notes_before": notes, "status": "not_started"
                }).execute()


def get_all_books(db: DBManager):
    """Fetch all active books from DB for processing."""
    if db.db_type == "sqlite":
        # We also want the initial notes shown in the UI. Let's join with outlines to get notes_before
        db.cursor.execute('''
            SELECT b.id, b.title, b.status_outline_notes, b.book_output_status, b.final_review_notes_status, o.notes_before 
            FROM books b 
            LEFT JOIN outlines o ON b.id = o.book_id
        ''')
        rows = db.cursor.fetchall()
        books = []
        for r in rows:
            books.append({
                "id": r[0], "title": r[1],
                "status_outline_notes": r[2], "book_output_status": r[3],
                "final_review_notes_status": r[4], "description": r[5] or ""
            })
        return books
    else:
        res = db.supabase.table("books").select("*, outlines(notes_before)").execute()
        return res.data

def get_outline(db: DBManager, book_id: str):
    if db.db_type == "sqlite":
        db.cursor.execute("SELECT id, content, notes_before, notes_after, status FROM outlines WHERE book_id = ?", (book_id,))
        row = db.cursor.fetchone()
        if row: return {"id": row[0], "content": row[1], "notes_before": row[2], "notes_after": row[3], "status": row[4]}
    else:
        res = db.supabase.table("outlines").select("*").eq("book_id", book_id).execute()
        if res.data: return res.data[0]
    return None


def get_chapter(db: DBManager, book_id: str, ch_num: int):
    if db.db_type == "sqlite":
        db.cursor.execute("SELECT id, content, notes, chapter_notes_status FROM chapters WHERE book_id = ? AND chapter_number = ?", (book_id, ch_num))
        row = db.cursor.fetchone()
        if row: return {"id": row[0], "content": row[1], "notes": row[2], "chapter_notes_status": row[3]}
    else:
        res = db.supabase.table("chapters").select("*").eq("book_id", book_id).eq("chapter_number", ch_num).execute()
        if res.data: return {"id": res.data[0]["id"], "content": res.data[0]["content"], "notes": res.data[0]["notes"], "chapter_notes_status": res.data[0]["status"]}
    return None

def update_chapter_status(db: DBManager, ch_id: str, status: str, notes: str):
    if db.db_type == "sqlite":
        db.cursor.execute("UPDATE chapters SET chapter_notes_status = ?, notes = ? WHERE id = ?", (status, notes, ch_id))
        db.conn.commit()
    else:
        db.supabase.table("chapters").update({"status": status, "notes": notes}).eq("id", ch_id).execute()


def process_outline_stage(db: DBManager, llm: LLMManager, book: dict):
    outline = get_outline(db, book['id'])
    if not outline: return False
    
    out_id = outline['id']
    title = book['title']
    out_status = outline['status']
    
    if out_status == 'not_started':
        print(f"\n[{title}] [Automated] Generating Outline...")
        prompt = llm.get_outline_prompt(title, outline.get('notes_before', ''))
        content = llm.generate_content(prompt)
        
        if db.db_type == "sqlite":
            db.cursor.execute("UPDATE outlines SET content = ?, status = 'pending_review' WHERE id = ?", (content, out_id))
            db.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book['id'],))
            db.conn.commit()
        else:
            db.supabase.table("outlines").update({"content": content, "status": "pending_review"}).eq("id", out_id).execute()
            db.supabase.table("books").update({"status_outline_notes": "pending_review"}).eq("id", book['id']).execute()
            
        return True # Handled something this cycle

    elif out_status == 'pending_review':
        # Waiting for frontend approval.
        return True
        
    elif out_status == 'yes':
        print(f"\n[{title}] [Automated] Regenerating Outline based on notes: {outline['notes_after']}")
        prompt = f"Rewrite this book outline for '{title}' based on the editor's notes.\nOld Outline: {outline['content']}\nEditor's Notes: {outline.get('notes_after', '')}\nOutput JSON."
        new_content = llm.generate_content(prompt)
        
        if db.db_type == "sqlite":
            db.cursor.execute("UPDATE outlines SET content = ?, status = 'pending_review', notes_after = '' WHERE id = ?", (new_content, out_id))
            db.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book['id'],))
            db.conn.commit()
        else:
            db.supabase.table("outlines").update({"content": new_content, "status": "pending_review", "notes_after": ""}).eq("id", out_id).execute()
            db.supabase.table("books").update({"status_outline_notes": "pending_review"}).eq("id", book['id']).execute()
        return True
        
    elif out_status == 'no':
        # Paused
        return False

    return False # If no_notes_needed, move to chapter stage


def process_chapter_stage(db: DBManager, llm: LLMManager, chapter_stage: ChapterStage, book: dict) -> bool:
    outline = get_outline(db, book['id'])
    
    import json
    try:
        clean_content = outline['content'].replace('```json', '').replace('```', '').strip()
        outline_json = json.loads(clean_content)
        chapter_titles = outline_json.get("chapters", ["Chapter 1", "Chapter 2"])
    except:
        chapter_titles = ["Chapter 1", "Chapter 2"]
        
    title = book['title']
    all_chapters_done = True
    
    for i, ch_title in enumerate(chapter_titles):
        # Extract title string if it's an object from LLM JSON
        if isinstance(ch_title, dict):
            ch_title = ch_title.get('title', ch_title.get('chapter_title', f"Chapter {i+1}"))
            
        ch_num = i + 1
        chapter = get_chapter(db, book['id'], ch_num)
        
        if not chapter:
            # Generate new chapter
            print(f"\n[{title}] [Automated] Generating Chapter {ch_num}...")
            chapter_stage.generate_next_chapter(book['id'], ch_num, title, ch_title, "no_notes_needed", "")
            all_chapters_done = False
            return True # Processed one chapter action
            
        ch_id = chapter['id']
        ch_status = chapter['chapter_notes_status']
        ch_notes = chapter.get('notes', '')
        ch_content = chapter['content']
        
        if ch_status == 'pending_review':
            # Waiting for frontend review
            all_chapters_done = False
            return True
            
        elif ch_status == 'yes':
            print(f"\n[{title}] [Automated] Regenerating Chapter {ch_num} based on notes: {ch_notes}")
            prompt = f"Rewrite this book chapter '{ch_title}' based on the editor's notes.\nOld Chapter Content: {ch_content}\nEditor's Notes: {ch_notes}\nOutput just the rewritten chapter content."
            new_content = llm.generate_content(prompt)
            new_summary = llm.generate_content(llm.get_summary_prompt(new_content))
            
            db.save_chapter(ch_id, book['id'], ch_num, ch_title, new_content, new_summary)
            update_chapter_status(db, ch_id, 'pending_review', "")
            all_chapters_done = False
            return True
            
        elif ch_status == 'no':
            # print(f"\n[{title}] Chapter {ch_num} is paused by user.")
            all_chapters_done = False
            break # Halted
            
        elif ch_status == 'no_notes_needed':
            continue # Already approved, check next
            
    return all_chapters_done # True only if all loops pass as 'no_notes_needed'


def process_compilation_stage(db: DBManager, compilation_stage: CompilationStage, book: dict):
    title = book['title']
    final_status = book.get('final_review_notes_status', 'pending_review')
    
    if final_status == 'pending_review':
        # Waiting for frontend review
        return True
        
    elif final_status == 'no_notes_needed':
        if book.get('book_output_status') != 'compiled':
            print(f"\n[{title}] [Automated] Compiling book to Output Format...")
            compilation_stage.compile_book(book['id'], title)
            
            if db.db_type == "sqlite":
                db.cursor.execute("UPDATE books SET book_output_status = 'compiled' WHERE id = ?", (book['id'],))
                db.conn.commit()
            else:
                db.supabase.table("books").update({"book_output_status": "compiled"}).eq("id", book['id']).execute()
            return True
            
    return False

def main():
    print("="*60)
    print("      AUTOMATED BOOK GENERATION - POLLING ENGINE v1.0")
    print("="*60)
    db = DBManager(db_type="sqlite")
    llm = LLMManager()
    
    # Wait for DB init
    time.sleep(1)
    
    chapter_stage = ChapterStage(db, llm)
    compilation_stage = CompilationStage(db)
    
    print(f"[{time.strftime('%H:%M:%S')}] Started polling loop. Will check for source data every 5 seconds...")
    
    while True:
        try:
            # 1. Sync from Input File (simulating webhooks/Google Sheets)
            sync_input_file(db, "input.xlsx")
            
            # 2. Get active books
            books = get_all_books(db)
            
            for book in books:
                # We only want to process one stage at a time per tick so we don't block the loop forever
                outline = get_outline(db, book['id'])
                
                # Check Outline Stage
                if not outline or outline['status'] != 'no_notes_needed':
                    handled = process_outline_stage(db, llm, book)
                    if handled: break # Stop processing other books, keep human in the loop per book
                else: 
                    # Outline done, move to chapters
                    all_chapters_done = process_chapter_stage(db, llm, chapter_stage, book)
                    
                    if all_chapters_done:
                        # Move to compilation
                        handled = process_compilation_stage(db, compilation_stage, book)
                        if handled: break # Stop for human review of compilation
                    else:
                        break # Stop processing other books if a chapter of this book is generating or pending review
                        
            # Sleep before next polling iteration
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\nAutomation Engine manually stopped. Goodbye.")
            break
        except Exception as e:
            print(f"\nError in event loop: {e}")
            time.sleep(5) # Delay on error
            
if __name__ == "__main__":
    main()
