
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    res = outline_stage.process(book.title, book.notes)
    if not res:
        raise HTTPException(status_code=400, detail="Failed to initiate book generation.")
    
    book_id, outline_id = res
    background_tasks.add_task(notifier.outline_ready, book.title)
    
    return {"book_id": book_id, "outline_id": outline_id}

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

@app.post("/outlines/{outline_id}/feedback")
async def outline_feedback(outline_id: str, feedback: OutlineFeedback):
    # First update the DB status and notes
    status = outline_stage.handle_feedback(outline_id, feedback.status, feedback.notes_after)
    
    # If the user said "yes" and provided notes, we explicitly regenerate
    if feedback.status == "yes" and feedback.notes_after:
        db.cursor.execute("SELECT book_id, content FROM outlines WHERE id = ?", (outline_id,))
        row = db.cursor.fetchone()
        if row:
            book_id, old_content = row
            # Fetch book title
            db.cursor.execute("SELECT title FROM books WHERE id = ?", (book_id,))
            title_row = db.cursor.fetchone()
            title = title_row[0] if title_row else "Unknown Title"
            
            prompt = f"Rewrite this book outline for '{title}' based on the editor's notes.\nOld Outline: {old_content}\nEditor's Notes: {feedback.notes_after}\nOutput clearly structured JSON with a 'chapters' array."
            new_content = llm.generate_content(prompt)
            
            # Save the new version
            db.cursor.execute("UPDATE outlines SET content = ?, status = 'pending_review' WHERE id = ?", (new_content, outline_id))
            db.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book_id,))
            db.conn.commit()
            
            # Notify that regeneration is complete
            notifier.outline_ready(title)
            return {"message": "Outline regenerated based on notes and is pending review again."}

    if status == "paused":
        return {"message": "Generation paused due to feedback."}
    elif status == "waiting":
        return {"message": "Waiting for additional notes to regenerate."}
    return {"message": "Feedback received, proceeding."}

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

@app.post("/books/{book_id}/chapters")
async def generate_chapter(book_id: str, chapter_data: ChapterGenerate, background_tasks: BackgroundTasks):
    res = chapter_stage.generate_next_chapter(book_id, chapter_data.chapter_num, chapter_data.title, chapter_data.chapter_title, chapter_data.status, chapter_data.notes)
    if res is None:
        if chapter_data.status == "no" or not chapter_data.status:
            return {"message": f"Chapter {chapter_data.chapter_num} generation paused.", "chapter_id": None}
        if chapter_data.status == "yes" and not chapter_data.notes:
             return {"message": f"Waiting for notes for Chapter {chapter_data.chapter_num}.", "chapter_id": None}
        raise HTTPException(status_code=400, detail="Failed to generate chapter.")
    return {"chapter_id": res}

@app.get("/books/{book_id}/chapters")
async def list_chapters(book_id: str):
    chapters = db.get_all_chapters(book_id)
    return chapters

class ChapterFeedback(BaseModel):
    status: str
    notes: str = ""

@app.post("/books/{book_id}/chapters/{chapter_num}/feedback")
async def chapter_feedback(book_id: str, chapter_num: int, feedback: ChapterFeedback):
    # Retrieve existing chapter to rewrite
    if db.db_type == "sqlite":
        db.cursor.execute("SELECT id, title, content FROM chapters WHERE book_id = ? AND chapter_number = ?", (book_id, chapter_num))
        row = db.cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Chapter not found.")
            
        chapter_id, chapter_title, old_content = row
        
        # Update chapter status first
        db.cursor.execute("UPDATE chapters SET chapter_notes_status = ?, notes = ? WHERE id = ?", (feedback.status, feedback.notes, chapter_id))
        db.conn.commit()
        
        if feedback.status == "yes" and feedback.notes:
            prompt = f"Rewrite this book chapter '{chapter_title}' based on the editor's notes.\nOld Chapter Content: {old_content}\nEditor's Notes: {feedback.notes}\nOutput just the rewritten chapter content."
            new_content = llm.generate_content(prompt)
            new_summary = llm.generate_content(llm.get_summary_prompt(new_content))
            
            db.save_chapter(chapter_id, book_id, chapter_num, chapter_title, new_content, new_summary)
            # Reset status so it can be reviewed again
            db.cursor.execute("UPDATE chapters SET chapter_notes_status = 'pending_review' WHERE id = ?", (chapter_id,))
            db.conn.commit()
            return {"message": f"Chapter {chapter_num} regenerated based on notes."}
            
        elif feedback.status == "no" or not feedback.status:
            notifier.notify_pause_or_error(f"Book ID {book_id}", f"User requested pause on chapter {chapter_num} generation")
            return {"message": f"Chapter {chapter_num} paused."}
            
        return {"message": "Chapter feedback received."}
    else:
        # Supabase fallback would go here
        return {"message": "Chapter feedback logic not fully implemented for Supabase yet."}

@app.post("/books/{book_id}/compile")
async def compile_book(book_id: str, compile_data: BookCompile, background_tasks: BackgroundTasks):
    file_path = compilation_stage.compile_book(book_id, compile_data.title)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="Compilation failed. No chapters found to compile.")
    background_tasks.add_task(notifier.final_draft_compiled, compile_data.title)
    filename = os.path.basename(file_path)
    return FileResponse(path=file_path, filename=filename, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
