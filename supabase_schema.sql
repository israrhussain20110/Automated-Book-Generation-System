CREATE TABLE IF NOT EXISTS books (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'drafting',
    final_review_notes_status TEXT DEFAULT 'pending_review',
    final_review_notes TEXT
);
CREATE TABLE IF NOT EXISTS outlines (
    id UUID PRIMARY KEY,
    book_id UUID REFERENCES books (id) ON DELETE CASCADE,
    content TEXT,
    notes_before TEXT,
    notes_after TEXT,
    status TEXT DEFAULT 'pending_review'
);
CREATE TABLE IF NOT EXISTS chapters (
    id UUID PRIMARY KEY,
    book_id UUID REFERENCES books (id) ON DELETE CASCADE,
    chapter_number INTEGER,
    title TEXT,
    content TEXT,
    summary TEXT,
    notes TEXT,
    status TEXT DEFAULT 'pending_review'
);