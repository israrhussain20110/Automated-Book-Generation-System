
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Book, Edit3, CheckCircle, Download, Loader2, Plus, ChevronRight, MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = "http://localhost:8002";

const App = () => {
  const [stage, setStage] = useState('setup'); // setup, outline, chapters, compile
  const [loading, setLoading] = useState(false);
  const [bookData, setBookData] = useState({ title: '', notes: '' });
  const [ids, setIds] = useState({ bookId: '', outlineId: '' });
  const [outline, setOutline] = useState({ content: '', chapters: [] });
  const [progress, setProgress] = useState(0);
  const [chapters, setChapters] = useState([]);

  const handleStart = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/books`, bookData);
      setIds({ bookId: res.data.book_id, outlineId: res.data.outline_id });
      fetchOutline(res.data.book_id);
      setStage('outline');
    } catch (err) {
      alert("Error starting book generation");
    } finally {
      setLoading(false);
    }
  };

  const fetchOutline = async (bookId) => {
    const res = await axios.get(`${API_BASE}/books/${bookId}/outline`);
    let chaptersList = [];
    try {
      const cleanContent = res.data.content.trim().replace(/```json/g, "").replace(/```/g, "");
      const outlineJson = JSON.parse(cleanContent);
      chaptersList = outlineJson.chapters || [];
      // Normalize chaptersList to be strings in case LLM returns objects
      chaptersList = chaptersList.map(ch => {
        if (typeof ch === 'string') return ch;
        return ch.title || ch.chapter_title || ch.name || JSON.stringify(ch);
      });
    } catch (e) {
      console.error("Failed to parse outline:", e);
      chaptersList = ["Chapter 1", "Chapter 2", "Chapter 3"];
    }
    setOutline({
      content: res.data.content,
      chapters: chaptersList
    });
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
      // Optional: automatically save before approving just in case
      await axios.put(`${API_BASE}/books/${ids.bookId}/outline`, { content: outline.content });
      await axios.post(`${API_BASE}/outlines/${ids.outlineId}/feedback`, { status: 'no_notes_needed' });
      setStage('chapters');
      generateChapters();
    } catch (err) {
      alert("Error approving outline");
    } finally {
      setLoading(false);
    }
  };

  const generateChapters = async () => {
    const total = outline.chapters.length || 3;
    const chaptersList = outline.chapters.length ? outline.chapters : ["Chapter 1", "Chapter 2", "Chapter 3"];

    for (let i = 0; i < chaptersList.length; i++) {
      setProgress(((i + 1) / total) * 100);
      try {
        await axios.post(`${API_BASE}/books/${ids.bookId}/chapters`, {
          chapter_num: i + 1,
          title: bookData.title,
          chapter_title: chaptersList[i],
          status: 'no_notes_needed'
        });
        const list = await axios.get(`${API_BASE}/books/${ids.bookId}/chapters`);
        setChapters(list.data);
      } catch (err) {
        console.error("Error generating chapter", i + 1);
      }
    }
    setStage('compile');
  };

  const compileBook = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API_BASE}/books/${ids.bookId}/compile`, { title: bookData.title }, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${bookData.title.replace(/ /g, '_')}.docx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      alert(`Book compiled and downloaded!`);
    } catch (err) {
      alert("Error compiling book");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <header style={{ marginBottom: '3rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div className="glass" style={{ padding: '12px', borderRadius: '12px' }}>
          <Book size={32} color="#818cf8" />
        </div>
        <div>
          <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 700 }}>Kickstart AI</h1>
          <p style={{ color: 'var(--text-dim)' }}>Automated Book Generation Engine</p>
        </div>
      </header>

      <main>
        <AnimatePresence mode="wait">
          {stage === 'setup' && (
            <motion.div
              key="setup"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="card"
            >
              <h2 style={{ marginBottom: '1.5rem' }}>Start New Project</h2>
              <label>Book Title</label>
              <input
                placeholder="e.g. The Future of AI"
                value={bookData.title}
                onChange={e => setBookData({ ...bookData, title: e.target.value })}
              />
              <label>Initial Outline Notes</label>
              <textarea
                rows={4}
                placeholder="Describe the scope, tone, and key themes..."
                value={bookData.notes}
                onChange={e => setBookData({ ...bookData, notes: e.target.value })}
              />
              <button className="primary" onClick={handleStart} disabled={loading || !bookData.title}>
                {loading ? <Loader2 className="animate-spin" /> : 'Kickstart Outline'}
              </button>
            </motion.div>
          )}

          {stage === 'outline' && (
            <motion.div
              key="outline"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="card"
            >
              <h2 style={{ marginBottom: '1rem' }}>Review Outline</h2>
              <div className="glass" style={{ padding: '1.5rem', borderRadius: '12px', marginBottom: '1.5rem', maxHeight: '400px', overflowY: 'auto' }}>
                <textarea
                  style={{ width: '100%', minHeight: '300px', background: 'transparent', border: 'none', color: 'var(--text-dim)', resize: 'vertical' }}
                  value={outline.content}
                  onChange={(e) => setOutline({ ...outline, content: e.target.value })}
                />
              </div>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <button className="secondary" onClick={saveOutline} disabled={loading}>
                  {loading ? <Loader2 className="animate-spin" /> : 'Save Changes'}
                </button>
                <button className="primary" onClick={approveOutline} disabled={loading}>
                  {loading ? <Loader2 className="animate-spin" /> : 'Approve & Generate Chapters'}
                </button>
              </div>
            </motion.div>
          )}

          {stage === 'chapters' && (
            <motion.div
              key="chapters"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="card"
            >
              <h2 style={{ marginBottom: '1rem' }}>Generating Chapters</h2>
              <div style={{ background: 'var(--border)', height: '8px', borderRadius: '4px', marginBottom: '2rem' }}>
                <motion.div
                  style={{ background: 'var(--primary)', height: '100%', borderRadius: '4px' }}
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                />
              </div>
              <div style={{ display: 'grid', gap: '1rem' }}>
                {chapters.map((ch, i) => (
                  <div key={i} className="glass" style={{ padding: '1rem', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <CheckCircle size={20} color="var(--success)" />
                      <span>{ch.title}</span>
                    </div>
                    <span style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Completed</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {stage === 'compile' && (
            <motion.div
              key="compile"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="card"
              style={{ textAlign: 'center' }}
            >
              <div className="glass" style={{ width: '80px', height: '80px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
                <Download size={40} color="var(--success)" />
              </div>
              <h2 style={{ marginBottom: '1rem' }}>Draft Ready!</h2>
              <p style={{ color: 'var(--text-dim)', marginBottom: '2rem' }}>All chapters have been generated and reviewed.</p>
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
