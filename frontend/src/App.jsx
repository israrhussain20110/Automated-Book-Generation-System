import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Book, Edit3, CheckCircle, Download, Loader2, RefreshCw, ChevronRight, MessageSquare, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = "http://localhost:8002";

const App = () => {
  const [stage, setStage] = useState('list');
  const [loading, setLoading] = useState(false);
  const [books, setBooks] = useState([]);
  const [selectedBook, setSelectedBook] = useState(null);
  const [ids, setIds] = useState({ bookId: '', outlineId: '' });
  const [outline, setOutline] = useState({ content: '', chapters: [], status: '' });
  const [chapters, setChapters] = useState([]);
  const [totalChapters, setTotalChapters] = useState(0);

  // ── Book List ──
  useEffect(() => {
    if (stage === 'list') fetchBooks();
  }, [stage]);

  const fetchBooks = async () => {
    try {
      const res = await axios.get(`${API_BASE}/books/syncing`);
      setBooks(res.data);
    } catch (e) {
      console.error("Error fetching books", e);
    }
  };

  // ── Select Book → determine stage ──
  const selectBook = async (book) => {
    setSelectedBook(book);
    setIds({ bookId: book.id, outlineId: null });
    setChapters([]);

    if (book.book_output_status === 'completed') {
      setStage('compile');
      return;
    }

    // Always fetch the outline first to determine the correct stage
    try {
      setLoading(true);
      const res = await axios.get(`${API_BASE}/books/${book.id}/outline`);
      const outlineData = res.data;
      setIds(prev => ({ ...prev, outlineId: outlineData.id }));

      const st = outlineData.status;
      if (st === 'not_started' || st === 'pending_review' || st === 'generating' || st === 'yes') {
        parseAndSetOutline(outlineData);
        setStage('outline');
      } else if (st === 'no_notes_needed') {
        // Outline approved → show chapters
        parseAndSetOutline(outlineData);
        setStage('chapters');
        await refreshChapters(book.id);
      }
    } catch (e) {
      console.error("Error loading book", e);
      setStage('outline');
    } finally {
      setLoading(false);
    }
  };

  const parseAndSetOutline = (data) => {
    let chaptersList = [];
    try {
      let cleanContent = data.content || "";
      const jsonMatch = cleanContent.match(/\{[\s\S]*\}/);
      if (jsonMatch) cleanContent = jsonMatch[0];
      const outlineJson = JSON.parse(cleanContent);
      chaptersList = (outlineJson.chapters || []).map(ch => {
        if (typeof ch === 'string') return ch;
        return ch.title || ch.chapter_title || ch.name || JSON.stringify(ch);
      });
    } catch (e) {
      // Can't parse yet
    }
    setOutline({
      content: data.content || '',
      chapters: chaptersList,
      id: data.id,
      status: data.status,
      notes_before: data.notes_before || ''
    });
    setTotalChapters(chaptersList.length);
  };

  // ── Outline Actions ──
  const generateOutline = async () => {
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/books/${ids.bookId}/outline/generate`);
      setOutline(prev => ({ ...prev, status: 'generating' }));
      // Poll until done
      const poll = setInterval(async () => {
        try {
          const res = await axios.get(`${API_BASE}/books/${ids.bookId}/outline`);
          if (res.data.status === 'pending_review') {
            clearInterval(poll);
            parseAndSetOutline(res.data);
            setIds(prev => ({ ...prev, outlineId: res.data.id }));
            setLoading(false);
          }
        } catch (err) { /* still generating */ }
      }, 3000);
      window._outlinePoll = poll;
    } catch (err) {
      alert("Error starting outline generation");
      setLoading(false);
    }
  };

  const saveOutline = async () => {
    setLoading(true);
    try {
      await axios.put(`${API_BASE}/books/${ids.bookId}/outline`, { content: outline.content });
      alert("Outline saved!");
    } catch (err) {
      alert("Error saving outline");
    } finally {
      setLoading(false);
    }
  };

  const approveOutline = async () => {
    setLoading(true);
    try {
      await axios.put(`${API_BASE}/books/${ids.bookId}/outline`, { content: outline.content });
      await axios.post(`${API_BASE}/outlines/${ids.outlineId}/feedback`, { status: 'no_notes_needed', notes_after: '' });
      setOutline(prev => ({ ...prev, status: 'no_notes_needed' }));
      setStage('chapters');
      // Wait a moment for first chapter to start generating, then fetch
      setTimeout(async () => {
        await refreshChapters(ids.bookId);
        setLoading(false);
      }, 2000);
    } catch (err) {
      alert("Error approving outline");
      setLoading(false);
    }
  };

  const requestOutlineRevision = async () => {
    const notes = prompt("Enter your revision notes for the outline:");
    if (!notes) return;
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/outlines/${ids.outlineId}/feedback`, { status: 'yes', notes_after: notes });
      setOutline(prev => ({ ...prev, status: 'generating' }));
      // Poll until regenerated
      const poll = setInterval(async () => {
        try {
          const res = await axios.get(`${API_BASE}/books/${ids.bookId}/outline`);
          if (res.data.status === 'pending_review') {
            clearInterval(poll);
            parseAndSetOutline(res.data);
            setLoading(false);
          }
        } catch (err) { /* still regenerating */ }
      }, 3000);
      window._outlinePoll = poll;
    } catch (err) {
      alert("Error requesting revision");
      setLoading(false);
    }
  };

  // ── Chapter Actions ──
  const refreshChapters = async (bookId = ids.bookId) => {
    try {
      const res = await axios.get(`${API_BASE}/books/${bookId}/chapters`);
      setChapters(res.data);
      // Check if all chapters approved
      if (totalChapters > 0 && res.data.length === totalChapters && res.data.every(ch => ch.chapter_notes_status === 'no_notes_needed')) {
        setStage('compile');
      }
    } catch (err) {
      console.error("Error fetching chapters", err);
    }
  };

  const approveChapter = async (chapterNum) => {
    try {
      await axios.post(`${API_BASE}/books/${ids.bookId}/chapters/${chapterNum}/feedback`, { status: 'no_notes_needed', notes: '' });
      // Immediately refresh to see the next chapter being generated
      setLoading(true);
      setTimeout(async () => {
        await refreshChapters(ids.bookId);
        setLoading(false);
      }, 3000);
    } catch (err) {
      alert("Error approving chapter");
    }
  };

  const reviseChapter = async (chapterNum) => {
    const notes = prompt("Enter revision notes for this chapter:");
    if (!notes) return;
    try {
      await axios.post(`${API_BASE}/books/${ids.bookId}/chapters/${chapterNum}/feedback`, { status: 'yes', notes });
      setLoading(true);
      setTimeout(async () => {
        await refreshChapters(ids.bookId);
        setLoading(false);
      }, 5000);
    } catch (err) {
      alert("Error submitting revision");
    }
  };

  // ── Compile ──
  const compileBook = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/books/${ids.bookId}/compile`, { title: selectedBook?.title }, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${selectedBook?.title?.replace(/ /g, '_')}.docx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      alert("Book compiled and downloaded!");
    } catch (err) {
      alert("Error compiling book");
    } finally {
      setLoading(false);
    }
  };

  // ── Cleanup on navigation ──
  const goBackToList = () => {
    if (window._outlinePoll) clearInterval(window._outlinePoll);
    setStage('list');
    setChapters([]);
    setOutline({ content: '', chapters: [], status: '' });
    fetchBooks();
  };

  const getStatusBadge = (status) => {
    const colors = {
      'pending_review': { bg: '#fbbf24', text: '#000' },
      'generating': { bg: '#818cf8', text: '#fff' },
      'no_notes_needed': { bg: '#34d399', text: '#000' },
      'not_started': { bg: '#6b7280', text: '#fff' },
    };
    const c = colors[status] || colors['not_started'];
    return (
      <span style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '12px', background: c.bg, color: c.text, fontWeight: 600, textTransform: 'uppercase' }}>
        {status?.replace(/_/g, ' ')}
      </span>
    );
  };

  const progress = totalChapters > 0 ? (chapters.filter(c => c.chapter_notes_status === 'no_notes_needed').length / totalChapters) * 100 : 0;

  return (
    <div className="container">
      <header style={{ marginBottom: '3rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="glass" style={{ padding: '12px', borderRadius: '12px', cursor: 'pointer' }} onClick={goBackToList}>
            <Book size={32} color="#818cf8" />
          </div>
          <div>
            <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 700 }}>Kickstart AI</h1>
            <p style={{ color: 'var(--text-dim)' }}>Automated Book Generation Engine</p>
          </div>
        </div>
        {stage !== 'list' && (
          <button className="secondary" onClick={goBackToList}>Back to Books</button>
        )}
      </header>

      <main>
        <AnimatePresence mode="wait">
          {/* ── BOOK LIST ── */}
          {stage === 'list' && (
            <motion.div key="list" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h2>Books</h2>
                <button className="secondary" onClick={fetchBooks} style={{ padding: '6px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              <div style={{ display: 'grid', gap: '1rem' }}>
                {books.map(b => (
                  <div key={b.id} className="glass" style={{ padding: '1rem', borderRadius: '8px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} onClick={() => selectBook(b)}>
                    <div>
                      <strong style={{ display: 'block', fontSize: '1.2rem', marginBottom: '4px' }}>{b.title}</strong>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Outline:</span> {getStatusBadge(b.status_outline_notes)}
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginLeft: '0.5rem' }}>Draft:</span> {getStatusBadge(b.book_output_status)}
                      </div>
                    </div>
                    <ChevronRight size={20} color="var(--primary)" />
                  </div>
                ))}
                {books.length === 0 && <p>No books found. Upload an Excel file or add books via API.</p>}
              </div>
            </motion.div>
          )}

          {/* ── OUTLINE REVIEW ── */}
          {stage === 'outline' && (
            <motion.div key="outline" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="card">
              <h2 style={{ marginBottom: '0.5rem' }}>Outline: {selectedBook?.title}</h2>
              <p style={{ color: 'var(--text-dim)', marginBottom: '1rem', fontSize: '0.9rem' }}>
                Status: {getStatusBadge(outline.status)}
              </p>

              {outline.status === 'not_started' ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  {outline.notes_before && (
                    <p style={{ marginBottom: '1rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
                      Initial notes: "{outline.notes_before}"
                    </p>
                  )}
                  <p style={{ marginBottom: '1rem' }}>The outline has not been generated yet.</p>
                  <button className="primary" onClick={generateOutline} disabled={loading}>
                    {loading ? <Loader2 className="animate-spin" /> : 'Generate Outline'}
                  </button>
                </div>
              ) : outline.status === 'generating' ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <Loader2 className="animate-spin" style={{ margin: '0 auto', marginBottom: '1rem' }} size={32} color="var(--primary)" />
                  <p>Generating outline via DeepSeek AI...</p>
                </div>
              ) : (
                <>
                  <div className="glass" style={{ padding: '1.5rem', borderRadius: '12px', marginBottom: '1.5rem', maxHeight: '400px', overflowY: 'auto' }}>
                    <textarea
                      style={{ width: '100%', minHeight: '300px', background: 'transparent', border: 'none', color: 'var(--text-dim)', resize: 'vertical', fontFamily: 'monospace', fontSize: '0.9rem' }}
                      value={outline.content}
                      onChange={(e) => setOutline({ ...outline, content: e.target.value })}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                    <button className="secondary" onClick={saveOutline} disabled={loading}>
                      {loading ? <Loader2 className="animate-spin" /> : 'Save Changes'}
                    </button>
                    <button className="secondary" onClick={requestOutlineRevision} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Edit3 size={14} /> Request AI Revision
                    </button>
                    <button className="primary" onClick={approveOutline} disabled={loading}>
                      {loading ? <Loader2 className="animate-spin" /> : 'Approve & Generate Chapters'}
                    </button>
                  </div>
                </>
              )}
            </motion.div>
          )}

          {/* ── CHAPTER REVIEW ── */}
          {stage === 'chapters' && (
            <motion.div key="chapters" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h2>Chapters: {selectedBook?.title}</h2>
                <button className="secondary" onClick={() => refreshChapters()} disabled={loading} style={{ padding: '6px 12px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {loading ? <Loader2 className="animate-spin" size={14} /> : <RefreshCw size={14} />} Refresh
                </button>
              </div>

              <p style={{ fontSize: '0.9rem', color: 'var(--text-dim)', marginBottom: '1rem' }}>
                Approve each chapter to trigger the next one. {totalChapters > 0 ? `(${chapters.filter(c => c.chapter_notes_status === 'no_notes_needed').length}/${totalChapters} approved)` : ''}
              </p>

              <div style={{ background: 'var(--border)', height: '8px', borderRadius: '4px', marginBottom: '2rem' }}>
                <motion.div
                  style={{ background: 'var(--primary)', height: '100%', borderRadius: '4px' }}
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                />
              </div>

              <div style={{ display: 'grid', gap: '1rem' }}>
                {chapters.length === 0 && !loading && (
                  <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <Loader2 className="animate-spin" style={{ margin: '0 auto', marginBottom: '1rem' }} size={24} color="var(--primary)" />
                    <p style={{ color: 'var(--text-dim)' }}>First chapter is being generated by AI...</p>
                    <button className="secondary" onClick={() => refreshChapters()} style={{ marginTop: '1rem' }}>Check Status</button>
                  </div>
                )}
                {chapters.map((ch, i) => (
                  <div key={i} className="glass" style={{ padding: '1rem', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        {ch.chapter_notes_status === 'no_notes_needed' ? (
                          <CheckCircle size={20} color="var(--success)" />
                        ) : ch.chapter_notes_status === 'generating' ? (
                          <Loader2 className="animate-spin" size={20} color="var(--primary)" />
                        ) : (
                          <AlertCircle size={20} color="#fbbf24" />
                        )}
                        <strong>{ch.title || `Chapter ${ch.chapter_number}`}</strong>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Ch. {ch.chapter_number}</span>
                        {getStatusBadge(ch.chapter_notes_status)}
                      </div>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--text-dim)', background: 'rgba(0,0,0,0.2)', padding: '0.75rem', borderRadius: '6px', maxHeight: '120px', overflowY: 'auto' }}>
                      {ch.chapter_notes_status === 'generating' || !ch.content ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                          <Loader2 className="animate-spin" size={14} /> Generating AI content...
                        </div>
                      ) : (
                        ch.content.substring(0, 400) + (ch.content.length > 400 ? '...' : '')
                      )}
                    </div>

                    {ch.chapter_notes_status === 'pending_review' && (
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                        <button className="secondary" style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => reviseChapter(ch.chapter_number)}>
                          <Edit3 size={12} /> Revise with Notes
                        </button>
                        <button className="primary" style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }} onClick={() => approveChapter(ch.chapter_number)}>
                          <CheckCircle size={12} /> Approve
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {totalChapters > 0 && chapters.length === totalChapters && chapters.every(ch => ch.chapter_notes_status === 'no_notes_needed') && (
                <div style={{ textAlign: 'center', marginTop: '2rem' }}>
                  <button className="primary" onClick={() => setStage('compile')} style={{ fontSize: '1.1rem', padding: '12px 24px' }}>
                    All Chapters Approved → Proceed to Compile
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {/* ── COMPILE ── */}
          {stage === 'compile' && (
            <motion.div key="compile" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card" style={{ textAlign: 'center' }}>
              <div className="glass" style={{ width: '80px', height: '80px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
                <Download size={40} color="var(--success)" />
              </div>
              <h2 style={{ marginBottom: '1rem' }}>Draft Ready!</h2>
              <p style={{ color: 'var(--text-dim)', marginBottom: '2rem' }}>
                All chapters have been generated and reviewed for "{selectedBook?.title}". Compile the final document.
              </p>
              <button className="primary" onClick={compileBook} disabled={loading}>
                {loading ? <Loader2 className="animate-spin" /> : 'Compile & Export (.docx)'}
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
};

export default App;
