
import sqlite3
import os
from typing import List, Dict, Any, Optional

class DBManager:
    """Interface for DB operations. Defaults to SQLite for local development."""
    def __init__(self, db_type: str = "sqlite", supabase_url: str = None, supabase_key: str = None):
        self.db_type = db_type
        if db_type == "sqlite":
            db_path = os.path.join(os.path.dirname(__file__), "..", "data", "book_gen.db")
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self._init_sqlite_db()
        elif db_type == "supabase":
            from supabase import create_client, Client
            self.supabase: Client = create_client(supabase_url, supabase_key)
        else:
            raise ValueError("Unsupported DB type. Use 'sqlite' or 'supabase'.")

    def _init_sqlite_db(self):
        """Initialize local SQLite tables."""
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status_outline_notes TEXT DEFAULT 'pending_review',
                book_output_status TEXT DEFAULT 'drafting'
            );
            CREATE TABLE IF NOT EXISTS outlines (
                id TEXT PRIMARY KEY,
                book_id TEXT,
                content TEXT,
                notes_before TEXT,
                notes_after TEXT,
                status TEXT DEFAULT 'pending_review',
                FOREIGN KEY(book_id) REFERENCES books(id)
            );
            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                book_id TEXT,
                chapter_number INTEGER,
                title TEXT,
                content TEXT,
                summary TEXT,
                notes TEXT,
                chapter_notes_status TEXT DEFAULT 'pending_review',
                FOREIGN KEY(book_id) REFERENCES books(id)
            );
        """)
        self.conn.commit()

    def create_book(self, book_id: str, title: str):
        if self.db_type == "sqlite":
            self.cursor.execute("INSERT INTO books (id, title, book_output_status) VALUES (?, ?, ?)", (book_id, title, 'drafting'))
            self.conn.commit()
        else:
            self.supabase.table("books").insert({
                "id": book_id, 
                "title": title,
                "stage": "outline",
                "processing_status": "drafting"
            }).execute()

    def save_outline(self, outline_id: str, book_id: str, content: str, notes_before: str):
        if self.db_type == "sqlite":
            self.cursor.execute(
                "INSERT OR REPLACE INTO outlines (id, book_id, content, notes_before) VALUES (?, ?, ?, ?)",
                (outline_id, book_id, content, notes_before)
            )
            # Ensure books table has the status
            self.cursor.execute("UPDATE books SET status_outline_notes = 'pending_review' WHERE id = ?", (book_id,))
            self.conn.commit()
        else:
            import json
            try:
                # The prompt returns string that might have json
                clean_content = content.replace('```json', '').replace('```', '').strip()
                outline_json = json.loads(clean_content)
            except Exception:
                outline_json = {"content": content}

            self.supabase.table("books").update({
                "outline": outline_json, 
                "notes_on_outline_before": notes_before,
                "status_outline_notes": "pending_review"
            }).eq("id", book_id).execute()

    def update_outline_status(self, outline_id: str, status: str, notes_after: str = None):
        if self.db_type == "sqlite":
            self.cursor.execute(
                "UPDATE outlines SET status = ?, notes_after = ? WHERE id = ?",
                (status, notes_after, outline_id)
            )
            # Find book_id from outline_id and update books table
            self.cursor.execute("SELECT book_id FROM outlines WHERE id = ?", (outline_id,))
            row = self.cursor.fetchone()
            if row:
                book_id = row[0]
                self.cursor.execute("UPDATE books SET status_outline_notes = ? WHERE id = ?", (status, book_id))
            self.conn.commit()
        else:
            self.supabase.table("books").update({
                "status_outline_notes": status, 
                "notes_on_outline_after": notes_after
            }).eq("id", outline_id).execute()

    def save_chapter(self, chapter_id: str, book_id: str, chapter_num: int, title: str, content: str, summary: str):
        if self.db_type == "sqlite":
            self.cursor.execute(
                "INSERT OR REPLACE INTO chapters (id, book_id, chapter_number, title, content, summary) VALUES (?, ?, ?, ?, ?, ?)",
                (chapter_id, book_id, chapter_num, title, content, summary)
            )
            self.conn.commit()
        else:
            self.supabase.table("chapters").insert({
                "id": chapter_id, 
                "book_id": book_id, 
                "chapter_number": chapter_num, 
                "chapter_title": title, 
                "chapter_content": content, 
                "chapter_summary": summary,
                "chapter_notes_status": "pending_review"
            }).execute()

    def get_chapter_summaries(self, book_id: str) -> List[str]:
        if self.db_type == "sqlite":
            self.cursor.execute("SELECT summary FROM chapters WHERE book_id = ? ORDER BY chapter_number ASC", (book_id,))
            return [row[0] for row in self.cursor.fetchall() if row[0]]
        else:
            res = self.supabase.table("chapters").select("chapter_summary").eq("book_id", book_id).order("chapter_number").execute()
            return [row["chapter_summary"] for row in res.data if row.get("chapter_summary")]
    
    def get_all_chapters(self, book_id: str) -> List[Dict[str, Any]]:
        if self.db_type == "sqlite":
            self.cursor.execute("SELECT chapter_number, title, content FROM chapters WHERE book_id = ? ORDER BY chapter_number ASC", (book_id,))
            return [{"chapter_number": r[0], "title": r[1], "content": r[2]} for r in self.cursor.fetchall()]
        else:
            res = self.supabase.table("chapters").select("*").eq("book_id", book_id).order("chapter_number").execute()
            return [{
                "chapter_number": r.get("chapter_number"),
                "title": r.get("chapter_title"),
                "content": r.get("chapter_content")
            } for r in res.data]

    def get_outline(self, book_id: str) -> Optional[Dict[str, Any]]:
        if self.db_type == "sqlite":
            # Join with books to get status_outline_notes
            self.cursor.execute("""
                SELECT o.id, o.content, b.status_outline_notes 
                FROM outlines o 
                JOIN books b ON o.book_id = b.id 
                WHERE o.book_id = ?
            """, (book_id,))
            row = self.cursor.fetchone()
            if row:
                return {"id": row[0], "content": row[1], "status": row[2]}
            return None
        else:
            res = self.supabase.table("books").select("id, outline, status_outline_notes").eq("id", book_id).execute()
            if res.data:
                row = res.data[0]
                import json
                content = json.dumps(row.get("outline")) if isinstance(row.get("outline"), dict) else row.get("outline")
                return {"id": row["id"], "content": content, "status": row.get("status_outline_notes")}
            return None
