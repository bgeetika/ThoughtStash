/**
 * Thought Stash — Frontend Application Logic
 * Implements the Branding Kit Specifications, Constellation Interactions & Microcopy
 */

document.addEventListener('DOMContentLoaded', () => {
    initNavScroll();
    initThemeToggle();
    initConstellationInteractions();
    initStashModals();
    initLiveMock();
    initAudioRecording();
    loadRecentThoughts();
});

// ── 1. Nav Scroll Border (Fades in after 40px scroll) ─────────────────
function initNavScroll() {
    const header = document.getElementById('navHeader');
    if (!header) return;

    window.addEventListener('scroll', () => {
        if (window.scrollY > 40) {
            header.classList.add('scrolled');
        } else {
            header.classList.remove('scrolled');
        }
    }, { passive: true });
}

// ── 2. Theme Toggle (Stone Paper Light / Dark System) ──────────────────
function initThemeToggle() {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;

    const savedTheme = localStorage.getItem('thoughtstash_theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }

    btn.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        if (next === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('thoughtstash_theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('thoughtstash_theme', 'light');
        }
    });
}

// ── 3. Constellation Hover & Interactions ─────────────────────────────
function initConstellationInteractions() {
    const svg = document.getElementById('heroConstellation');
    if (!svg) return;

    const rings = svg.querySelectorAll('.rings circle');
    rings.forEach(ring => {
        const nodeId = ring.dataset.node;
        if (!nodeId) return;

        ring.addEventListener('mouseenter', () => {
            svg.classList.add(`highlight-${nodeId}`);
        });

        ring.addEventListener('mouseleave', () => {
            svg.classList.remove(`highlight-${nodeId}`);
        });
    });
}

// ── 4. Toast Microcopy Notification ───────────────────────────────────
function showToast(message) {
    const toast = document.getElementById('stashToast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('visible');
    setTimeout(() => {
        toast.classList.remove('visible');
    }, 2400);
}

// ── 5. Stash Modal & Drawer Workflows ─────────────────────────────────
function initStashModals() {
    const modal = document.getElementById('stashModal');
    const closeBtn = document.getElementById('closeModalBtn');
    const openBtns = document.querySelectorAll('.open-stash-btn');

    openBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (modal) {
                modal.classList.add('active');
                modal.setAttribute('aria-hidden', 'false');
                const input = document.getElementById('modalTextInput');
                if (input) setTimeout(() => input.focus(), 50);
            }
        });
    });

    if (closeBtn && modal) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
            modal.setAttribute('aria-hidden', 'true');
        });
    }

    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
                modal.setAttribute('aria-hidden', 'true');
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
            modal.classList.remove('active');
            modal.setAttribute('aria-hidden', 'true');
        }
    });
}

// ── 6. Live Mock & Quick Text Capture ─────────────────────────────────
function initLiveMock() {
    // In-Page Mock Drop Input
    const liveInput = document.getElementById('liveMockInput');
    const liveSaveBtn = document.getElementById('liveMockSaveBtn');

    async function handleLiveSave() {
        if (!liveInput) return;
        const text = liveInput.value.trim();
        if (!text) return;

        liveSaveBtn.disabled = true;
        liveSaveBtn.textContent = '...';

        try {
            const res = await fetch('/api/thoughts/text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, location_name: 'In the app' })
            });

            if (!res.ok) throw new Error('Save failed');

            const data = await res.json();
            liveInput.value = '';
            showToast('Stashed.');
            prependThoughtToFeed(data);
        } catch (err) {
            showToast('That did not save. Your text is still in the box, try again.');
        } finally {
            liveSaveBtn.disabled = false;
            liveSaveBtn.textContent = 'Stash';
        }
    }

    if (liveSaveBtn) liveSaveBtn.addEventListener('click', handleLiveSave);
    if (liveInput) {
        liveInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handleLiveSave();
        });
    }

    // Modal Drop Input
    const modalInput = document.getElementById('modalTextInput');
    const modalSaveBtn = document.getElementById('modalTextSaveBtn');

    async function handleModalSave() {
        if (!modalInput) return;
        const text = modalInput.value.trim();
        if (!text) return;

        modalSaveBtn.disabled = true;
        modalSaveBtn.textContent = '...';

        try {
            const res = await fetch('/api/thoughts/text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, location_name: 'Direct capture' })
            });

            if (!res.ok) throw new Error('Save failed');

            const data = await res.json();
            modalInput.value = '';
            showToast('Stashed.');
            prependThoughtToFeed(data);
        } catch (err) {
            showToast('That did not save. Your text is still in the box, try again.');
        } finally {
            modalSaveBtn.disabled = false;
            modalSaveBtn.textContent = 'Save';
        }
    }

    if (modalSaveBtn) modalSaveBtn.addEventListener('click', handleModalSave);
    if (modalInput) {
        modalInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handleModalSave();
        });
    }

    // Modal Search / Pull the thread
    const searchInput = document.getElementById('modalSearchInput');
    const searchBtn = document.getElementById('modalSearchBtn');
    const searchResult = document.getElementById('modalSearchResult');

    async function handleSearch() {
        if (!searchInput || !searchResult) return;
        const q = searchInput.value.trim();
        if (!q) return;

        searchBtn.disabled = true;
        searchResult.innerHTML = '<span class="loading-microcopy">Looking through your stash...</span>';

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: q, history: [] })
            });

            const data = await res.json();
            if (!data.summary || data.summary.includes("haven't recorded")) {
                searchResult.innerHTML = '<p class="body-s" style="color: var(--ink-70);">No thread matches that. Try the words you would have used at the time.</p>';
            } else {
                let html = `<div style="background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius-card); padding: 14px;">`;
                html += `<p style="font-weight: 500; font-size: 14px; margin-bottom: 6px;">${escapeHtml(data.summary)}</p>`;
                if (data.key_points && data.key_points.length) {
                    html += `<ul style="list-style: none; display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--ink-70);">`;
                    data.key_points.forEach(pt => {
                        html += `<li>&middot; ${escapeHtml(pt)}</li>`;
                    });
                    html += `</ul>`;
                }
                html += `</div>`;
                searchResult.innerHTML = html;
            }
        } catch (err) {
            searchResult.innerHTML = '<p class="body-s" style="color: var(--node-oxblood);">Could not complete search. Please try again.</p>';
        } finally {
            searchBtn.disabled = false;
        }
    }

    if (searchBtn) searchBtn.addEventListener('click', handleSearch);
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') handleSearch();
        });
    }
}

// ── 7. Voice Recording ────────────────────────────────────────────────
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recordInterval = null;
let recordSeconds = 0;

function initAudioRecording() {
    const liveMicBtn = document.getElementById('liveMockMicBtn');
    const modalMicBtn = document.getElementById('modalMicBtn');

    if (liveMicBtn) {
        liveMicBtn.addEventListener('click', () => toggleAudioRecording('live'));
    }
    if (modalMicBtn) {
        modalMicBtn.addEventListener('click', () => toggleAudioRecording('modal'));
    }
}

async function toggleAudioRecording(context) {
    if (isRecording) {
        stopAudioRecording(context);
    } else {
        await startAudioRecording(context);
    }
}

async function startAudioRecording(context) {
    const statusEl = document.getElementById(context === 'live' ? 'liveMockStatus' : 'modalRecordStatus');
    const timerEl = document.getElementById(context === 'live' ? 'liveMockTimer' : 'modalTimer');
    const btn = document.getElementById(context === 'live' ? 'liveMockMicBtn' : 'modalMicBtn');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (statusEl) statusEl.textContent = 'Microphone access is unavailable.';
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
            const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
            await uploadRecordedAudio(audioBlob, context);
        };

        mediaRecorder.start(250);
        isRecording = true;
        recordSeconds = 0;

        if (btn) btn.classList.add('recording');
        if (statusEl) statusEl.textContent = 'Listening...';
        if (timerEl) timerEl.textContent = '00:00';

        recordInterval = setInterval(() => {
            recordSeconds++;
            const m = String(Math.floor(recordSeconds / 60)).padStart(2, '0');
            const s = String(recordSeconds % 60).padStart(2, '0');
            if (timerEl) timerEl.textContent = `${m}:${s}`;
        }, 1000);

    } catch (err) {
        if (statusEl) statusEl.textContent = 'Microphone permission denied.';
    }
}

function stopAudioRecording(context) {
    const statusEl = document.getElementById(context === 'live' ? 'liveMockStatus' : 'modalRecordStatus');
    const btn = document.getElementById(context === 'live' ? 'liveMockMicBtn' : 'modalMicBtn');

    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    clearInterval(recordInterval);

    if (btn) btn.classList.remove('recording');
    if (statusEl) statusEl.textContent = 'Scribing note...';
}

async function uploadRecordedAudio(blob, context) {
    const statusEl = document.getElementById(context === 'live' ? 'liveMockStatus' : 'modalRecordStatus');
    const timerEl = document.getElementById(context === 'live' ? 'liveMockTimer' : 'modalTimer');

    const formData = new FormData();
    formData.append('audio', blob, 'note.webm');
    formData.append('location_name', 'Voice note');
    formData.append('client_timestamp', new Date().toISOString());

    try {
        const res = await fetch('/api/thoughts', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('Upload failed');

        const thought = await res.json();
        if (statusEl) statusEl.textContent = 'Record voice thought';
        if (timerEl) timerEl.textContent = '00:00';
        showToast('Stashed.');
        prependThoughtToFeed(thought);
    } catch (err) {
        if (statusEl) statusEl.textContent = 'That did not save. Try again.';
        showToast('That did not save. Try again.');
    }
}

// ── 8. Feed Management & Microcopy ────────────────────────────────────
async function loadRecentThoughts() {
    try {
        const res = await fetch('/api/thoughts');
        if (!res.ok) return;
        const thoughts = await res.json();
        renderThoughtsFeed(thoughts);
    } catch (err) {
        console.warn('Could not load thoughts:', err);
    }
}

function renderThoughtsFeed(thoughts) {
    const mockStream = document.getElementById('mockStream');
    const modalFeed = document.getElementById('modalThoughtsFeed');

    if (!thoughts || thoughts.length === 0) {
        const emptyHtml = '<div class="body-s" style="padding: 16px; color: var(--ink-45);">Nothing here yet. Drop in the thing you were about to forget.</div>';
        if (mockStream) mockStream.innerHTML = emptyHtml;
        if (modalFeed) modalFeed.innerHTML = emptyHtml;
        return;
    }

    const accents = ['ochre', 'petrol', 'oxblood', 'slate', 'quiet'];
    const html = thoughts.slice(0, 6).map((t, idx) => {
        // Roughly 1 saturated per 3 quiet grey
        const accent = (idx % 3 === 0) ? accents[idx % 4] : 'quiet';
        const dateStr = t.created_at ? new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        const locStr = t.location_name || 'Stash';
        return `
            <div class="mock-thought-item">
                <svg class="ring-glyph ${accent} glyph-dot" viewBox="0 0 32 32" aria-hidden="true">
                    <circle cx="16" cy="16" r="11"/>
                </svg>
                <div class="mock-thought-body">
                    <p>${escapeHtml(t.summary || t.transcript || 'Recorded thought')}</p>
                    <span class="mock-thought-meta">${escapeHtml(locStr)}${dateStr ? ' · ' + dateStr : ''}</span>
                </div>
            </div>
        `;
    }).join('');

    if (mockStream) mockStream.innerHTML = html;
    if (modalFeed) modalFeed.innerHTML = html;
}

function prependThoughtToFeed(thought) {
    const mockStream = document.getElementById('mockStream');
    const modalFeed = document.getElementById('modalThoughtsFeed');

    const itemHtml = `
        <div class="mock-thought-item" style="animation: popRing 0.3s ease;">
            <svg class="ring-glyph petrol glyph-dot" viewBox="0 0 32 32" aria-hidden="true">
                <circle cx="16" cy="16" r="11"/>
            </svg>
            <div class="mock-thought-body">
                <p>${escapeHtml(thought.summary || thought.transcript || 'Recorded thought')}</p>
                <span class="mock-thought-meta">${escapeHtml(thought.location_name || 'Just now')}</span>
            </div>
        </div>
    `;

    if (mockStream) {
        const empty = mockStream.querySelector('.body-s');
        if (empty) mockStream.innerHTML = '';
        mockStream.insertAdjacentHTML('afterbegin', itemHtml);
    }
    if (modalFeed) {
        const empty = modalFeed.querySelector('.body-s, .loading-microcopy');
        if (empty) modalFeed.innerHTML = '';
        modalFeed.insertAdjacentHTML('afterbegin', itemHtml);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
