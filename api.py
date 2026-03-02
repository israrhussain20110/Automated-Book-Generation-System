
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
import io
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

from core.db_manager import DBManager
from core.llm_manager import LLMManager
from stages.outline_stage import OutlineStage
from stages.chapter_stage import ChapterStage
from stages.compilation_stage import CompilationStage
from core.notifier import Notifier

app = FastAPI(title="Book Generation API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    print("API-driven architecture: no background global loop started.")


# Initialize managers
db = DBManager(db_type="sqlite")
llm = LLMManager()

teams_webhook = os.getenv('TEAMS_WEBHOOK_URL')
smtp_config = None
if os.getenv('SMTP_SERVER') and os.getenv('SMTP_PASS'):
    smtp_config = {
        'server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'port': int(os.environ.get('SMTP_PORT', 587)),
        'username': os.environ.get('SMTP_USER'),
        'password': os.environ.get('SMTP_PASS'),
        'sender_email': os.environ.get('SMTP_USER'),
        'receiver_email': os.environ.get('SMTP_USER')
    }

notifier = Notifier(teams_webhook_url=teams_webhook, smtp_config=smtp_config)

outline_stage = OutlineStage(db, llm, notifier)
chapter_stage = ChapterStage(db, llm, notifier)
compilation_stage = CompilationStage(db)

class BookCreate(BaseModel):
    title: str
    notes: Optional[str] = ""

class OutlineFeedback(BaseModel):
    status: str
    notes_after: Optional[str] = ""

class ChapterGenerate(BaseModel):
    chapter_num: int
    title: str
    chapter_title: str
    status: str = "no_notes_needed"
    notes: str = ""

class BookCompile(BaseModel):
    title: str

@app.post("/books")
async def create_book(book: BookCreate, background_tasks: BackgroundTasks):
    book_id = str(uuid.uuid4())
    db.create_book(book_id, book.title)
    
    if db.db_type == "sqlite":
        db.cursor.execute("INSERT OR REPLACE INTO outlines (id, book_id, content, notes_before, status) VALUES (?, ?, ?, ?, ?)", (book_id, book_id, "", book.notes, "not_started"))
        db.conn.commit()
    else:
        db.supabase.table("outlines").insert({"id": book_id, "book_id": book_id, "content": "", "notes_before": book.notes, "status": "not_started"}).execute()
        
    background_tasks.add_task(notifier.outline_ready, book.title)
    
    return {"book_id": book_id, "outline_id": book_id}

@app.post("/books/upload")
async def upload_books(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.endswith(('.csv', '.xlsx')):
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported.")
    
    try:
        content = await file.read()
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
            
        required_cols = {'title', 'notes_on_outline_before'}
        if not required_cols.issubset(df.columns):
            raise ValueError(f"File must contain columns: {required_cols}")
            
        results = []
        for _, row in df.iterrows():
            title = str(row['title']).strip()
            notes = str(row['notes_on_outline_before']).strip()
            
            if not title or title.lower() == 'nan':
                continue
                
            try:
                res = outline_stage.process(title, notes if notes and notes.lower() != 'nan' else "")
                if res:
                    book_id, outline_id = res
                    results.append({"title": title, "status": "started", "book_id": book_id})
                    background_tasks.add_task(notifier.outline_ready, title)
                else:
                    results.append({"title": title, "status": "skipped_or_failed"})
            except Exception as e:
                results.append({"title": title, "status": f"error: {str(e)}"})
                
        return {"processed": len(results), "results": results}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing file: {str(e)}")

@app.get("/books/{book_id}/outline")
async def get_outline(book_id: str):
    outline = db.get_outline(book_id)
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found.")
    return outline

@app.get("/books/syncing")
async def get_syncing_books():
    if db.db_type == "sqlite":
        db.cursor.execute("SELECT id, title, status_outline_notes, book_output_status, final_review_notes_status FROM books")
        rows = db.cursor.fetchall()
        books = []
        for r in rows:
            books.append({
                "id": r[0],
                "title": r[1],
                "status_outline_notes": r[2],
                "book_output_status": r[3],
                "final_review_notes_status": r[4]
            })
        return books
    else:
        res = db.supabase.table("books").select("id, title, status_outline_notes, book_output_status, final_review_notes_status").execute()
        return res.data

@app.post("/outlines/{outline_id}/feedback")
async def outline_feedback(outline_id: str, feedback: OutlineFeedback, background_tasks: BackgroundTasks):
    db.update_outline_status(outline_id, feedback.status, feedback.notes_after)
    
    # Check if we belong to a book
    db.cursor.execute("SELECT book_id FROM outlines WHERE id = ?", (outline_id,))
    row = db.cursor.fetchone()
    if not row: return {"message": "Feedback received."}
    book_id = row[0]
    book = db.get_book_details(book_id)
    title = book.get('title', 'Unknown')
    
    if feedback.status == "no_notes_needed":
        # Immediately start compiling chapters
        background_tasks.add_task(run_chapter_generation, book_id, title)
    elif feedback.status == "yes":
        # Regenerate outline immediately
        background_tasks.add_task(regenerate_outline, book_id, outline_id, title, feedback.notes_after)
        
    return {"message": "Feedback received, proceeding or regenerating."}

def regenerate_outline(book_id: str, out_id: str, title: str, notes_after: str):
    outline = db.get_outline(book_id)
    prompt = f"Rewrite this book outline for '{title}' based on the editor's notes.\nOld Outline: {outline['content']}\nEditor's Notes: {notes_after}\nOutput JSON."
    new_content = llm.generate_content(prompt)
    if db.db_type == "sqlite":
        db.cursor.execute("UPDATE outlines SET content = ?, status = 'pending_review', notes_after = '' WHERE id = ?", (new_content, out_id))
        db.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book_id,))
        db.conn.commit()

class OutlineUpdate(BaseModel):
    content: str
    
@app.put("/books/{book_id}/outline")
async def update_outline(book_id: str, update: OutlineUpdate):
    outline = db.get_outline(book_id)
    if not outline:
        raise HTTPException(status_code=404, detail="Outline not found.")
    
    outline_id = outline['id']
    # Use save_outline to update the content but we only want to update the outline content
    if db.db_type == "sqlite":
        db.cursor.execute("UPDATE outlines SET content = ? WHERE id = ?", (update.content, outline_id))
        db.conn.commit()
    else:
        # For supabase we'd do roughly the same, simplified here for outline
        import json
        try:
            clean_content = update.content.replace('```json', '').replace('```', '').strip()
            outline_json = json.loads(clean_content)
        except:
            outline_json = {"content": update.content}
        db.supabase.table("books").update({"outline": outline_json}).eq("id", book_id).execute()
        
    return {"message": "Outline updated successfully."}

def _parse_outline_chapters(book_id: str) -> list:
    import re, json
    outline = db.get_outline(book_id)
    if not outline or not outline.get('content'): return []
    
    content = outline['content']
    # Try to extract JSON object from possible markdown wrapping
    json_match = re.search(r'\{[\s\S]*\}', content)
    json_str = json_match.group(0) if json_match else content
    
    try:
        data = json.loads(json_str)
        chapters = data.get("chapters", [])
        # Normalize: each entry could be a string or dict
        result = []
        for ch in chapters:
            if isinstance(ch, str):
                result.append(ch)
            elif isinstance(ch, dict):
                result.append(ch.get('title', ch.get('chapter_title', ch.get('name', str(ch)))))
            else:
                result.append(str(ch))
        return result if result else []
    except:
        return []

def run_chapter_generation(book_id: str, title: str):
    """Generate ONLY the next pending chapter, then stop so human can review."""
    chapters_list = _parse_outline_chapters(book_id)
    if not chapters_list:
        print(f"No chapters found in outline for book {book_id}")
        return
    
    for i, ch_title in enumerate(chapters_list):
        ch_num = i + 1
        
        db.cursor.execute("SELECT id, chapter_notes_status FROM chapters WHERE book_id = ? AND chapter_number = ?", (book_id, ch_num))
        row = db.cursor.fetchone()
        
        if not row:
            # This chapter hasn't been generated yet — generate it and STOP
            try:
                chapter_stage.generate_next_chapter(book_id, ch_num, title, ch_title, "no_notes_needed", "")
                print(f"Generated chapter {ch_num} for '{title}'. Waiting for human review.")
            except Exception as e:
                print(f"Error generating chapter {ch_num}: {e}")
            return  # STOP — wait for human to approve before generating next
        else:
            status = row[1]
            if status in ('pending_review', 'generating'):
                # Already waiting for human — don't generate anything
                return
            # status == 'no_notes_needed' means approved, continue to next chapter
    
    # All chapters generated and approved — update book status
    db.cursor.execute("UPDATE books SET book_output_status = 'completed' WHERE id = ?", (book_id,))
    db.conn.commit()
    print(f"All chapters done for '{title}'. Book ready for compilation.")

@app.post("/books/{book_id}/outline/generate")
async def generate_outline_api(book_id: str, background_tasks: BackgroundTasks):
    book = db.get_book_details(book_id)
    if not book: raise HTTPException(404, "Book not found")
    
    outline = db.get_outline(book_id)
    if not outline or outline['status'] == 'not_started':
        if db.db_type == "sqlite":
            db.cursor.execute("UPDATE outlines SET status = 'generating' WHERE book_id = ?", (book_id,))
            db.conn.commit()
        else:
            db.supabase.table("outlines").update({"status": "generating"}).eq("book_id", book_id).execute()
            
        background_tasks.add_task(do_outline_generation, book_id, book['title'])
        return {"message": "Outline generation started."}
    return {"message": "Outline already exists or generating."}

def do_outline_generation(book_id: str, title: str):
    try:
        outline = db.get_outline(book_id)
        notes = outline.get('notes_before', '') if outline else ''
        prompt = llm.get_outline_prompt(title, notes)
        content = llm.generate_content(prompt)
        if db.db_type == "sqlite":
            db.cursor.execute("UPDATE outlines SET content = ?, status = 'pending_review' WHERE book_id = ?", (content, book_id))
            db.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book_id,))
            db.conn.commit()
        print(f"Outline generated for '{title}'.")
    except Exception as e:
        print(f"Error generating outline for '{title}': {e}")
        # Reset status so user can retry
        if db.db_type == "sqlite":
            db.cursor.execute("UPDATE outlines SET status = 'not_started' WHERE book_id = ?", (book_id,))
            db.conn.commit()


@app.post("/books/{book_id}/chapters")
async def generate_chapter(book_id: str, chapter_data: ChapterGenerate, background_tasks: BackgroundTasks):
    book = db.get_book_details(book_id)
    background_tasks.add_task(run_chapter_generation, book_id, book['title'])
    return {"message": "Chapter generation loop triggered"}

class ChapterFeedback(BaseModel):
    status: str
    notes: str = ""

@app.post("/books/{book_id}/chapters/{chapter_num}/feedback")
async def chapter_feedback(book_id: str, chapter_num: int, feedback: ChapterFeedback, background_tasks: BackgroundTasks):
    db.cursor.execute("SELECT id FROM chapters WHERE book_id = ? AND chapter_number = ?", (book_id, chapter_num))
    row = db.cursor.fetchone()
    if not row: raise HTTPException(status_code=404, detail="Chapter not found")
        
    chapter_id = row[0]
    if db.db_type == "sqlite":
        db.cursor.execute("UPDATE chapters SET chapter_notes_status = ?, notes = ? WHERE id = ?", (feedback.status, feedback.notes, chapter_id))
        db.conn.commit()
    
    book = db.get_book_details(book_id)
    if feedback.status == "no_notes_needed":
        background_tasks.add_task(run_chapter_generation, book_id, book['title'])
    elif feedback.status == "yes":
        background_tasks.add_task(regenerate_chapter, book_id, chapter_num, chapter_id, book['title'], feedback.notes)
        
    return {"message": "Feedback submitted."}

def regenerate_chapter(book_id: str, chapter_num: int, chapter_id: str, title: str, notes: str):
    db.cursor.execute("SELECT title, content FROM chapters WHERE id = ?", (chapter_id,))
    row = db.cursor.fetchone()
    if not row: return
    ch_title, old_content = row
    
    db.cursor.execute("UPDATE chapters SET chapter_notes_status = 'generating' WHERE id = ?", (chapter_id,))
    db.conn.commit()
    
    prompt = f"Rewrite this book chapter '{ch_title}' based on the editor's notes.\nOld Chapter Content: {old_content}\nEditor's Notes: {notes}\nOutput just the rewritten chapter content."
    new_content = llm.generate_content(prompt)
    new_summary = llm.generate_content(llm.get_summary_prompt(new_content))
    db.save_chapter(chapter_id, book_id, chapter_num, ch_title, new_content, new_summary)
    
    db.cursor.execute("UPDATE chapters SET chapter_notes_status = 'pending_review' WHERE id = ?", (chapter_id,))
    db.conn.commit()

@app.get("/books/{book_id}/chapters")
async def list_chapters(book_id: str):
    chapters = db.get_all_chapters(book_id)
    return chapters



@app.post("/books/{book_id}/compile")
async def compile_book(book_id: str, compile_data: BookCompile, background_tasks: BackgroundTasks):
    book = db.get_book_details(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")

    status = book.get("final_review_notes_status")
    notes = book.get("final_review_notes")

    if status == "no" or not status:
        notifier.notify_pause_or_error(f"Book '{compile_data.title}'", "User requested pause on final compilation")
        return {"message": "Final compilation paused. Awaiting further instruction."}

    if status == "yes" and not notes:
        notifier.notify_pause_or_error(f"Book '{compile_data.title}'", "Waiting for final review notes to compile.")
        return {"message": "Waiting for notes for Final Draft."}

    # At this point, status is either 'no_notes_needed' or 'yes' AND notes exist.
    file_path = compilation_stage.compile_book(book_id, compile_data.title)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Compilation failed. No chapters found to compile.")
    background_tasks.add_task(notifier.final_draft_compiled, compile_data.title)
    filename = os.path.basename(file_path)
    return FileResponse(path=file_path, filename=filename, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

class FinalFeedback(BaseModel):
    status: str
    notes: str = ""

@app.post("/books/{book_id}/final_feedback")
async def final_feedback(book_id: str, feedback: FinalFeedback):
    book = db.get_book_details(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found.")
    
    db.update_final_review_status(book_id, feedback.status, feedback.notes)
    
    if feedback.status == "no" or not feedback.status:
        notifier.notify_pause_or_error(f"Book ID {book_id}", "User requested pause on final draft")
        return {"message": "Final draft generation paused."}
    
    if feedback.status == "yes":
        if not feedback.notes:
            notifier.notify_pause_or_error(f"Book ID {book_id}", "Waiting for notes for final draft")
            return {"message": "Waiting for notes for final draft."}
        else:
            return {"message": "Notes received for final draft, ready to compile or regenerate if implemented."}
            
    return {"message": "Final feedback received."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
