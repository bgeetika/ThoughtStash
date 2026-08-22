/**
 * ThoughtStash — Frontend logic
 * Voice recording, Geo-location, Timestamping, Agent status, UI rendering
 */

// ── State ──────────────────────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let timerInterval = null;
let seconds = 0;
let chatHistory = [];
let currentGeo = { latitude: null, longitude: null, locationName: null };

// ── DOM refs ───────────────────────────────────────────────────────

const recordBtn = document.getElementById('recordBtn');
const recordStatus = document.getElementById('recordStatus');
const timerEl = document.getElementById('timer');
const locationBadge = document.getElementById('locationBadge');
const processing = document.getElementById('processing');
const latestThought = document.getElementById('latestThought');
const thoughtsList = document.getElementById('thoughtsList');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const patternsResult = document.getElementById('patternsResult');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');

const scribeChip = document.getElementById('scribeStatus');
const connectorChip = document.getElementById('connectorStatus');
const oracleChip = document.getElementById('oracleStatus');
const connectorInsights = document.getElementById('connectorInsights');
const connectorContent = document.getElementById('connectorContent');

// ── Tab Navigation ─────────────────────────────────────────────────

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(tab.dataset.tab).classList.add('active');

        // Load data when switching tabs
        if (tab.dataset.tab === 'thoughts') loadThoughts();
    });
});

// ── Geolocation Detection ──────────────────────────────────────────

function initGeolocation() {
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                currentGeo.latitude = pos.coords.latitude;
                currentGeo.longitude = pos.coords.longitude;
                if (locationBadge) {
                    locationBadge.innerHTML = `📍 GPS Active (${pos.coords.latitude.toFixed(3)}, ${pos.coords.longitude.toFixed(3)})`;
                    locationBadge.classList.add('active');
                }
            },
            (err) => {
                console.log("Geolocation info:", err.message);
                if (locationBadge) {
                    locationBadge.innerHTML = `📍 Local Time Captured`;
                }
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    } else {
        if (locationBadge) locationBadge.innerHTML = `📍 Location on`;
    }
}

// ── Cross-Browser MIME & Audio Support ─────────────────────────────

function getSupportedMimeType() {
    const candidates = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
        'audio/aac',
        'audio/ogg;codecs=opus',
        'audio/wav'
    ];
    for (const type of candidates) {
        if (window.MediaRecorder && typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }
    return '';
}

// ── Voice Recording ────────────────────────────────────────────────

recordBtn.addEventListener('click', async () => {
    if (!isRecording) {
        initGeolocation(); // refresh GPS right when user initiates recording
        await startRecording();
    } else {
        stopRecording();
    }
});

async function startRecording() {
    // Check for Secure Context (Chrome requirement for microphone on non-localhost)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        const isChrome = navigator.userAgent.includes('Chrome');
        let helpText = '⚠️ Microphone requires HTTPS or localhost.';
        if (isChrome && window.location.hostname !== 'localhost') {
            helpText += ' In Chrome, enable chrome://flags/#unsafely-treat-insecure-origin-as-secure for this URL, or use localhost via SSH tunnel.';
        }
        recordStatus.innerHTML = `<span style="color:var(--warning);font-size:12px">${helpText}</span>`;
        alert(helpText);
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const selectedMime = getSupportedMimeType();
        const options = selectedMime ? { mimeType: selectedMime } : {};
        
        mediaRecorder = new MediaRecorder(stream, options);
        audioChunks = [];
        const actualMime = mediaRecorder.mimeType || selectedMime || 'audio/webm';

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            const blob = new Blob(audioChunks, { type: actualMime });
            await uploadThought(blob, actualMime);
        };

        mediaRecorder.start(250); // collect in 250ms chunks
        isRecording = true;
        recordBtn.classList.add('recording');
        recordStatus.textContent = 'Recording walk thought... tap to stop';
        timerEl.style.display = 'block';
        seconds = 0;
        updateTimer();
        timerInterval = setInterval(() => { seconds++; updateTimer(); }, 1000);
    } catch (err) {
        recordStatus.textContent = `⚠️ Microphone access failed: ${err.message}`;
        console.error('Mic error:', err);
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    recordBtn.classList.remove('recording');
    recordStatus.textContent = 'Scribe processing...';
    clearInterval(timerInterval);
}

function updateTimer() {
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
}

// ── Agent Status Helpers ───────────────────────────────────────────

function setAgentState(chip, state, label) {
    if (!chip) return;
    chip.className = 'agent-chip ' + state;
    chip.querySelector('span').textContent = label;
}

// ── Upload & Process (Agentic Pipeline) ────────────────────────────

async function uploadThought(blob, mimeType) {
    latestThought.style.display = 'none';
    connectorInsights.style.display = 'none';
    processing.style.display = 'block';

    // Scribe agent working
    setAgentState(scribeChip, 'working', 'Transcribing...');

    const ext = (mimeType && mimeType.includes('mp4')) ? 'mp4' :
                (mimeType && mimeType.includes('ogg')) ? 'ogg' :
                (mimeType && mimeType.includes('wav')) ? 'wav' : 'webm';

    const formData = new FormData();
    formData.append('audio', blob, `thought.${ext}`);
    
    // Spatio-temporal data
    const localTimestamp = new Date().toISOString();
    formData.append('client_timestamp', localTimestamp);
    if (currentGeo.latitude !== null) {
        formData.append('latitude', currentGeo.latitude);
    }
    if (currentGeo.longitude !== null) {
        formData.append('longitude', currentGeo.longitude);
    }
    if (currentGeo.locationName) {
        formData.append('location_name', currentGeo.locationName);
    }

    try {
        const res = await fetch('/api/thoughts', { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Upload failed');
        }
        const thought = await res.json();

        // Scribe done
        setAgentState(scribeChip, 'active', 'Done ✓');
        showThoughtResult(thought);

        // Connector agent is now working autonomously in the background
        setAgentState(connectorChip, 'working', 'Connecting...');

        // Poll for connector results
        pollConnectorInsights(thought.id);

    } catch (err) {
        recordStatus.textContent = `❌ Error: ${err.message}`;
        setAgentState(scribeChip, 'active', 'Error');
        console.error('Upload error:', err);
    } finally {
        processing.style.display = 'none';
        recordStatus.textContent = 'Tap to start recording';
        timerEl.style.display = 'none';
    }
}

async function pollConnectorInsights(thoughtId) {
    for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 2000));
        try {
            const res = await fetch(`/api/thoughts/${thoughtId}/connections`);
            const data = await res.json();
            if (data.status === 'pending') continue;

            // Connector found something!
            setAgentState(connectorChip, 'active', 'Done ✓');
            showConnectorInsights(data);
            return;
        } catch { /* keep polling */ }
    }
    setAgentState(connectorChip, 'active', 'Done');
}

function showConnectorInsights(data) {
    let html = '';

    if (data.proactive_insight) {
        html += `<div class="proactive-insight">💡 ${data.proactive_insight}</div>`;
    }

    if (data.spatio_temporal_insights) {
        html += `<div class="connection-item">📍 <strong>Spatio-Temporal Pattern:</strong> ${data.spatio_temporal_insights}</div>`;
    }

    if (data.connections?.length) {
        html += '<h4 style="margin-top:12px; font-size:13px; color:var(--text-muted)">Connections across time & place:</h4>';
        data.connections.forEach(c => {
            const icon = c.connection_type === 'contradicts' ? '⚡' :
                         c.connection_type === 'evolves' ? '📈' : '🔗';
            const locInfo = c.past_location ? ` @ ${c.past_location}` : '';
            html += `<div class="connection-item">${icon} <strong>${c.connection_type}</strong> (${c.past_thought_date}${locInfo}): ${c.explanation}</div>`;
        });
    }

    if (data.thinking_evolution) {
        html += `<p style="margin-top:10px; color:var(--text-muted)">📈 ${data.thinking_evolution}</p>`;
    }

    if (html) {
        connectorContent.innerHTML = html;
        connectorInsights.style.display = 'block';
    }
}

function showThoughtResult(thought) {
    document.getElementById('resultTranscript').textContent = thought.transcript || '—';
    document.getElementById('resultSummary').textContent = thought.summary || '—';
    document.getElementById('resultMood').textContent = thought.mood || '—';

    // Time & Location display
    const dateObj = new Date(thought.created_at);
    const dateFormatted = dateObj.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
    const timeFormatted = dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    
    let locationStr = thought.location_name || '';
    if (!locationStr && thought.latitude != null) {
        locationStr = `GPS: ${Number(thought.latitude).toFixed(4)}, ${Number(thought.longitude).toFixed(4)}`;
    }
    const fullLocTime = `🕒 ${dateFormatted} at ${timeFormatted}` + (locationStr ? `<br>📍 ${locationStr}` : '');
    document.getElementById('resultLocationTime').innerHTML = fullLocTime;

    // Topics
    const topicsEl = document.getElementById('resultTopics');
    topicsEl.innerHTML = '';
    (thought.topics || []).forEach(t => {
        const span = document.createElement('span');
        span.className = 'tag';
        span.textContent = t;
        topicsEl.appendChild(span);
    });

    // Insights
    const insightsEl = document.getElementById('resultInsights');
    insightsEl.innerHTML = '';
    (thought.key_insights || []).forEach(insight => {
        const li = document.createElement('li');
        li.textContent = insight;
        insightsEl.appendChild(li);
    });

    latestThought.style.display = 'block';
}

// ── Thoughts Timeline ──────────────────────────────────────────────

async function loadThoughts(searchQuery) {
    let url = '/api/thoughts';
    if (searchQuery) url = `/api/search?q=${encodeURIComponent(searchQuery)}`;

    try {
        const res = await fetch(url);
        const thoughts = await res.json();
        renderThoughts(thoughts, !!searchQuery);
    } catch (err) {
        thoughtsList.innerHTML = '<p class="empty-state">Failed to load thoughts</p>';
    }
}

function renderThoughts(thoughts, isSearch) {
    if (!thoughts.length) {
        thoughtsList.innerHTML = `<p class="empty-state">${
            isSearch ? 'No matching thoughts found' : 'No thoughts yet. Go for a walk and capture some! 🎙️'
        }</p>`;
        return;
    }

    thoughtsList.innerHTML = '';
    thoughts.forEach(t => {
        const card = document.createElement('div');
        card.className = 'thought-card';

        const dateObj = new Date(t.created_at);
        const dateStr = dateObj.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const relevance = t.relevance !== undefined ? ` · relevance: ${(t.relevance * 100).toFixed(0)}%` : '';

        let locBadge = '';
        if (t.location_name) {
            locBadge = `<span class="tag" style="background:#3b82f6;font-size:11px">📍 ${t.location_name}</span>`;
        } else if (t.latitude != null) {
            locBadge = `<span class="tag" style="background:#3b82f6;font-size:11px">📍 ${Number(t.latitude).toFixed(3)}, ${Number(t.longitude).toFixed(3)}</span>`;
        }

        card.innerHTML = `
            <div class="meta">
                <span class="date">📅 ${dateStr}${relevance}</span>
                <span class="mood-badge">${t.mood || '—'}</span>
            </div>
            <div class="summary">${t.summary || '—'}</div>
            <div class="transcript">${t.transcript || ''}</div>
            <div class="card-footer">
                ${locBadge}
                ${(t.topics || []).map(tp => `<span class="tag">${tp}</span>`).join('')}
            </div>
        `;
        thoughtsList.appendChild(card);
    });
}

searchBtn.addEventListener('click', () => {
    const q = searchInput.value.trim();
    if (q) loadThoughts(q);
    else loadThoughts();
});
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') searchBtn.click();
});

// ── Pattern Analysis ───────────────────────────────────────────────

analyzeBtn.addEventListener('click', async () => {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = '⏳ Analyzing...';
    patternsResult.innerHTML = '<div class="processing"><div class="spinner"></div><p>Analyzing your spatio-temporal thought patterns...</p></div>';

    try {
        const res = await fetch('/api/patterns');
        const data = await res.json();

        if (data.error) {
            patternsResult.innerHTML = `<p class="empty-state">${data.error}. You have ${data.thought_count} thought(s).</p>`;
            return;
        }

        renderPatterns(data);
    } catch (err) {
        patternsResult.innerHTML = `<p class="empty-state">❌ Analysis failed: ${err.message}</p>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = '🔍 Analyze My Thinking';
    }
});

function renderPatterns(data) {
    let html = '';

    // One-line summary
    if (data.one_line_summary) {
        html += `<div class="one-line-summary">🧠 ${data.one_line_summary}</div>`;
    }

    // Mood trajectory
    if (data.mood_trajectory) {
        html += `
        <div class="pattern-section">
            <h3>😊 Mood Trajectory — ${data.mood_trajectory.trend}</h3>
            <p style="font-size:14px; line-height:1.6">${data.mood_trajectory.summary}</p>
        </div>`;
    }

    // Recurring themes
    if (data.recurring_themes?.length) {
        html += `<div class="pattern-section"><h3>🔄 Recurring Themes</h3>`;
        data.recurring_themes.forEach(t => {
            html += `<div class="pattern-item"><strong>${t.theme}</strong> (×${t.frequency}) — ${t.description}</div>`;
        });
        html += '</div>';
    }

    // Emerging patterns
    if (data.emerging_patterns?.length) {
        html += `<div class="pattern-section"><h3>📈 Emerging Patterns</h3>`;
        data.emerging_patterns.forEach(p => {
            html += `<div class="pattern-item"><strong>${p.pattern}</strong> — ${p.evidence}</div>`;
        });
        html += '</div>';
    }

    // Connections
    if (data.connections?.length) {
        html += `<div class="pattern-section"><h3>🔗 Thought Connections</h3>`;
        data.connections.forEach(c => {
            html += `<div class="pattern-item">"${c.thought_a}" ↔ "${c.thought_b}" — <em>${c.connection}</em></div>`;
        });
        html += '</div>';
    }

    // Recommendations
    if (data.recommendations?.length) {
        html += `<div class="pattern-section"><h3>💡 Recommendations</h3>`;
        data.recommendations.forEach(r => {
            html += `<div class="pattern-item">→ ${r}</div>`;
        });
        html += '</div>';
    }

    patternsResult.innerHTML = html;
}

// ── Context Chat ───────────────────────────────────────────────────

chatSendBtn.addEventListener('click', sendChatMessage);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) sendChatMessage();
});

async function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    // Show user message
    appendChatMsg('user', message);
    chatInput.value = '';
    chatSendBtn.disabled = true;

    // Show typing indicator
    const typingId = appendChatMsg('assistant', '⏳ Oracle searching thoughts & locations...');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: chatHistory }),
        });
        const data = await res.json();

        // Update typing indicator with response
        typingId.querySelector('.msg-content p').textContent = data.response;

        // Track history
        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'model', content: data.response });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    } catch (err) {
        typingId.querySelector('.msg-content p').textContent = `❌ Error: ${err.message}`;
    } finally {
        chatSendBtn.disabled = false;
        chatInput.focus();
    }
}

function appendChatMsg(role, text) {
    const div = document.createElement('div');
    div.className = `chat-msg ${role}`;
    div.innerHTML = `<div class="msg-content"><p>${text}</p></div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

// ── Init ───────────────────────────────────────────────────────────

initGeolocation();
loadThoughts();
