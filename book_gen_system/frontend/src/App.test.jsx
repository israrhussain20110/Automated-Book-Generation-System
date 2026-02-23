import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import axios from 'axios';
import App from './App';

// Mock axios so we don't make real network requests during testing
vi.mock('axios');

describe('Book Generation Dashboard - Title & Outline Flow', () => {
    it('should accept a title, submit it, and transition to the Outline review stage', async () => {
        // 1. Setup our mock API responses
        // Mock the POST /books response
        axios.post.mockResolvedValueOnce({
            data: { book_id: '123', outline_id: '456' }
        });

        // Mock the GET /books/123/outline response
        axios.get.mockResolvedValueOnce({
            data: {
                id: '456',
                status: 'pending',
                content: JSON.stringify({
                    chapters: ["Chapter 1", "Chapter 2"]
                })
            }
        });

        // 2. Render the App
        render(<App />);

        // 3. Verify we are on the Setup stage initially
        expect(screen.getByText('Start New Project')).toBeInTheDocument();

        // 4. Find input fields
        const titleInput = screen.getByPlaceholderText('e.g. The Future of AI');
        const notesInput = screen.getByPlaceholderText('Describe the scope, tone, and key themes...');
        const startButton = screen.getByRole('button', { name: /Kickstart Outline/i });

        // 5. Simulate User Input
        fireEvent.change(titleInput, { target: { value: 'My Awesome Test Book' } });
        fireEvent.change(notesInput, { target: { value: 'This is a test note about AI.' } });

        // 6. Simulate clicking the generate button
        fireEvent.click(startButton);

        // 7. Verify the API was called with the correct data
        await waitFor(() => {
            expect(axios.post).toHaveBeenCalledWith('http://localhost:8002/books', {
                title: 'My Awesome Test Book',
                notes: 'This is a test note about AI.'
            });
        });

        // 8. Verify the UI transitions to the Outline stage
        await waitFor(() => {
            expect(screen.getByText('Review Outline')).toBeInTheDocument();
            expect(screen.getByRole('button', { name: /Approve & Generate Chapters/i })).toBeInTheDocument();
        });
    });
});
