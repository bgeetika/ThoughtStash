/**
 * ThoughtStash — Cosmic Editorial Application
 * Features:
 * - 3D Audio Orb (Three.js WebGL with Live Audio Frequency Reactivity)
 * - 3D Neural Knowledge Space (ForceGraph3D WebGL)
 * - Spatio-Temporal Radar Map (Leaflet + Neon Radar Pulse)
 * - Offline IndexedDB Queue
 * - Glassmorphic Inspector Drawer & Navigation
 */

// ── Global State ───────────────────────────────────────────────────

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let timerInterval = null;
let seconds = 0;
let chatHistory = [];
let currentGeo = { latitude: null, longitude: null, locationName: null };

// 3D Audio Orb state
let orbScene, orbCamera, orbRenderer, orbMesh, orbWireframe, orbLight1, orbLight2;
let audioContext, audioAnalyser, audioDataArray;
let orbAnimationId = null;

// 3D Force Graph state
let forceGraph3DInstance = null;
let graphRawData = { nodes: [], edges: [] };

// Map state
let leafletMap = null;
let mapMarkers = [];
let mapPolylines = [];

// ── DOM References ─────────────────────────────────────────────────

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

const scribePill = document.getElementById('scribeStatus');
const connectorPill = document.getElementById('connectorStatus');
const oraclePill = document.getElementById('oracleStatus');
const connectorInsights = document.getElementById('connectorInsights');
const connectorContent = document.getElementById('connectorContent');

const thoughtInspectorDrawer = document.getElementById('thoughtInspectorDrawer');
const closeInspectorBtn = document.getElementById('closeInspectorBtn');

// ── 1. Cosmic Background Particle Canvas ───────────────────────────

function initCosmicBackground() {
    const canvas = document.getElementById('cosmicBgCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    window.addEventListener('resize', () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    });

    const stars = Array.from({ length: 90 }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        radius: Math.random() * 1.2 + 0.3,
        alpha: Math.random() * 0.7 + 0.2,
        speed: Math.random() * 0.008 + 0.002
    }));

    function draw() {
        ctx.clearRect(0, 0, width, height);
        stars.forEach(s => {
            s.alpha += s.speed;
            const currentAlpha = Math.abs(Math.sin(s.alpha));
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(180, 210, 255, ${currentAlpha * 0.6})`;
            ctx.shadowBlur = 4;
            ctx.shadowColor = '#00f2fe';
            ctx.fill();
        });
        requestAnimationFrame(draw);
    }
    draw();
}

// ── 2. Three.js 3D Audio Visualizer Orb ────────────────────────────

function init3DAudioOrb() {
    const container = document.getElementById('threeOrbCanvas');
    if (!container || typeof THREE === 'undefined') return;

    const width = container.clientWidth || 580;
    const height = container.clientHeight || 360;

    orbScene = new THREE.Scene();
    orbCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    orbCamera.position.z = 4.8;

    orbRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    orbRenderer.setSize(width, height);
    orbRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = '';
    container.appendChild(orbRenderer.domElement);

    // Inner Luminous Core
    const geometry = new THREE.IcosahedronGeometry(1.35, 4);
    const material = new THREE.MeshStandardMaterial({
        color: 0x0a1224,
        emissive: 0x112244,
        roughness: 0.2,
        metalness: 0.8,
        wireframe: false
    });
    orbMesh = new THREE.Mesh(geometry, material);
    orbScene.add(orbMesh);

    // Outer Neon Wireframe Hologram
    const wireGeo = new THREE.IcosahedronGeometry(1.42, 2);
    const wireMat = new THREE.MeshBasicMaterial({
        color: 0x00f2fe,
        wireframe: true,
        transparent: true,
        opacity: 0.35
    });
    orbWireframe = new THREE.Mesh(wireGeo, wireMat);
    orbScene.add(orbWireframe);

    // Dynamic Lights
    orbLight1 = new THREE.PointLight(0x00f2fe, 3, 50);
    orbLight1.position.set(3, 3, 4);
    orbScene.add(orbLight1);

    orbLight2 = new THREE.PointLight(0x8a2be2, 3, 50);
    orbLight2.position.set(-3, -3, 3);
    orbScene.add(orbLight2);

    const ambientLight = new THREE.AmbientLight(0x223355, 1.2);
    orbScene.add(ambientLight);

    let clock = new THREE.Clock();

    function animate() {
        orbAnimationId = requestAnimationFrame(animate);
        const elapsed = clock.getElapsedTime();

        // Idle floating rotation
        orbMesh.rotation.y = elapsed * 0.25;
        orbMesh.rotation.x = elapsed * 0.15;
        orbWireframe.rotation.y = -elapsed * 0.3;
        orbWireframe.rotation.x = -elapsed * 0.18;

        // Audio reactivity if recording
        let audioFactor = 0;
        if (isRecording && audioAnalyser && audioDataArray) {
            audioAnalyser.getByteFrequencyData(audioDataArray);
            let sum = 0;
            for (let i = 0; i < audioDataArray.length; i++) {
                sum += audioDataArray[i];
            }
            audioFactor = (sum / audioDataArray.length) / 128.0; // 0 to ~1.5
        }

        const scale = 1.0 + (isRecording ? Math.min(audioFactor * 0.35, 0.45) : Math.sin(elapsed * 1.5) * 0.03);
        orbMesh.scale.set(scale, scale, scale);
        orbWireframe.scale.set(scale * 1.05, scale * 1.05, scale * 1.05);

        if (isRecording) {
            wireMat.color.setHex(0xff007f);
            orbLight1.color.setHex(0xff007f);
            wireMat.opacity = 0.6 + (audioFactor * 0.3);
        } else {
            wireMat.color.setHex(0x00f2fe);
            orbLight1.color.setHex(0x00f2fe);
            wireMat.opacity = 0.35;
        }

        orbRenderer.render(orbScene, orbCamera);
    }
    animate();

    window.addEventListener('resize', () => {
        if (!container || !orbRenderer || !orbCamera) return;
        const newW = container.clientWidth;
        const newH = container.clientHeight;
        orbCamera.aspect = newW / newH;
        orbCamera.updateProjectionMatrix();
        orbRenderer.setSize(newW, newH);
    });
}

// ── 3. Offline IndexedDB Queue ─────────────────────────────────────

let idb = null;
const DB_NAME = 'ThoughtStashOfflineDB';
const STORE_NAME = 'offline_recordings';

function initIndexedDB() {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
            db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
        }
    };
    request.onsuccess = (e) => {
        idb = e.target.result;
        syncOfflineQueue();
    };
}

async function saveOfflineRecording(blob, mimeType, geo, timestamp) {
    if (!idb) return;
    const tx = idb.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.add({ blob, mimeType, geo, timestamp, addedAt: Date.now() });
    recordStatus.innerHTML = '<span style="color:var(--neon-amber)">📶 Offline: Recording stored on device.</span>';
}

async function syncOfflineQueue() {
    if (!idb || !navigator.onLine) return;
    const tx = idb.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const getAllReq = store.getAll();

    getAllReq.onsuccess = async () => {
        const items = getAllReq.result;
        if (!items || items.length === 0) return;
        for (const item of items) {
            try {
                currentGeo = item.geo || currentGeo;
                await uploadThought(item.blob, item.mimeType, item.timestamp);
                const delTx = idb.transaction(STORE_NAME, 'readwrite');
                delTx.objectStore(STORE_NAME).delete(item.id);
            } catch (err) {
                console.error("Offline sync error:", err);
            }
        }
    };
}

window.addEventListener('online', () => syncOfflineQueue());

// ── 4. Navigation & Tab Switching ──────────────────────────────────

document.querySelectorAll('.nav-dock-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-dock-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-view').forEach(v => v.classList.remove('active'));
        
        btn.classList.add('active');
        const targetId = btn.dataset.tab;
        const targetView = document.getElementById(targetId);
        if (targetView) targetView.classList.add('active');

        if (targetId === 'thoughts') loadThoughts();
        if (targetId === 'mapTab') {
            if (!leafletMap) initMap();
            else setTimeout(() => leafletMap.invalidateSize(), 150);
        }
        if (targetId === 'graphTab') {
            setTimeout(() => init3DGraph(), 60);
        }
    });
});

// ── 5. Geolocation ─────────────────────────────────────────────────

function initGeolocation() {
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                currentGeo.latitude = pos.coords.latitude;
                currentGeo.longitude = pos.coords.longitude;
                if (locationBadge) {
                    locationBadge.querySelector('span').textContent = `${pos.coords.latitude.toFixed(3)}° N, ${pos.coords.longitude.toFixed(3)}° W`;
                    locationBadge.style.borderColor = 'rgba(0, 242, 254, 0.3)';
                    locationBadge.style.color = 'var(--neon-cyan)';
                }
            },
            () => {
                if (locationBadge) locationBadge.querySelector('span').textContent = 'Walk Mode (Bay Area)';
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    }
}

// ── 6. Audio Recording & Web Audio API Visualizer ──────────────────

function getSupportedMimeType() {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/wav'];
    for (const type of candidates) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }
    return '';
}

recordBtn.addEventListener('click', async () => {
    if (!isRecording) {
        initGeolocation();
        await startRecording();
    } else {
        stopRecording();
    }
});

async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Microphone access requires HTTPS or localhost.');
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        // Connect Web Audio API to 3D Orb visualizer
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioContext.createMediaStreamSource(stream);
            audioAnalyser = audioContext.createAnalyser();
            audioAnalyser.fftSize = 64;
            source.connect(audioAnalyser);
            audioDataArray = new Uint8Array(audioAnalyser.frequencyBinCount);
        } catch (e) {
            console.warn("AudioContext visualizer init skipped:", e);
        }

        const selectedMime = getSupportedMimeType();
        mediaRecorder = new MediaRecorder(stream, selectedMime ? { mimeType: selectedMime } : {});
        audioChunks = [];
        const actualMime = mediaRecorder.mimeType || selectedMime || 'audio/webm';

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            if (audioContext && audioContext.state !== 'closed') {
                audioContext.close();
            }
            const blob = new Blob(audioChunks, { type: actualMime });
            if (!navigator.onLine) {
                await saveOfflineRecording(blob, actualMime, currentGeo, new Date().toISOString());
            } else {
                await uploadThought(blob, actualMime);
            }
        };

        mediaRecorder.start(250);
        isRecording = true;
        recordBtn.classList.add('recording');
        recordStatus.textContent = 'Listening to walk thought... tap to finish';
        timerEl.style.display = 'block';
        seconds = 0;
        updateTimer();
        timerInterval = setInterval(() => { seconds++; updateTimer(); }, 1000);
    } catch (err) {
        recordStatus.textContent = `Microphone error: ${err.message}`;
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    recordBtn.classList.remove('recording');
    recordStatus.textContent = 'Scribing & linking thought...';
    clearInterval(timerInterval);
}

function updateTimer() {
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
}

// ── 7. Agent Status Telemetry ──────────────────────────────────────

function setAgentState(pillEl, stateClass, labelText) {
    if (!pillEl) return;
    const led = pillEl.querySelector('.agent-led');
    const state = pillEl.querySelector('.agent-state');
    if (led) led.className = `agent-led status-${stateClass}`;
    if (state) state.textContent = labelText;
    if (stateClass === 'working') pillEl.classList.add('active-pulse');
    else pillEl.classList.remove('active-pulse');
}

// ── 8. Upload & Scribe Pipeline ────────────────────────────────────

async function uploadThought(blob, mimeType, customTimestamp) {
    latestThought.style.display = 'none';
    connectorInsights.style.display = 'none';
    processing.style.display = 'flex';

    setAgentState(scribePill, 'working', 'Transcribing...');

    const ext = (mimeType && mimeType.includes('mp4')) ? 'mp4' :
                (mimeType && mimeType.includes('ogg')) ? 'ogg' :
                (mimeType && mimeType.includes('wav')) ? 'wav' : 'webm';

    const formData = new FormData();
    formData.append('audio', blob, `thought.${ext}`);
    const localTimestamp = customTimestamp || new Date().toISOString();
    formData.append('client_timestamp', localTimestamp);
    if (currentGeo.latitude !== null) formData.append('latitude', currentGeo.latitude);
    if (currentGeo.longitude !== null) formData.append('longitude', currentGeo.longitude);
    if (currentGeo.locationName) formData.append('location_name', currentGeo.locationName);

    try {
        const res = await fetch('/api/thoughts', { method: 'POST', body: formData });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Processing failed');
        }
        const thought = await res.json();

        setAgentState(scribePill, 'ready', 'Captured ✓');
        showThoughtResult(thought);

        setAgentState(connectorPill, 'working', 'Synthesizing...');
        pollConnectorInsights(thought.id);

        if (leafletMap) loadMapPoints();
        if (forceGraph3DInstance) load3DGraphData();

    } catch (err) {
        if (!navigator.onLine) {
            await saveOfflineRecording(blob, mimeType, currentGeo, localTimestamp);
        } else {
            recordStatus.textContent = `Error: ${err.message}`;
            setAgentState(scribePill, 'idle', 'Error');
        }
    } finally {
        processing.style.display = 'none';
        recordStatus.textContent = 'Tap Orb to begin walk session';
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

            setAgentState(connectorPill, 'ready', 'Linked ✓');
            showConnectorInsights(data);
            return;
        } catch { /* poll */ }
    }
    setAgentState(connectorPill, 'idle', 'Monitoring');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showThoughtResult(thought) {
    document.getElementById('resultTranscript').textContent = thought.transcript || '—';
    document.getElementById('resultSummary').textContent = thought.summary || '—';
    document.getElementById('resultMoodBadge').textContent = thought.mood ? `Mood: ${thought.mood}` : 'Reflective';

    const dateObj = new Date(thought.created_at);
    const dateFormatted = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const timeFormatted = dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    const loc = thought.location_name || (thought.latitude ? `${Number(thought.latitude).toFixed(3)}°, ${Number(thought.longitude).toFixed(3)}°` : 'Bay Area');
    document.getElementById('resultTimeLocation').textContent = `${dateFormatted} · ${timeFormatted} · ${loc}`;

    const topicsEl = document.getElementById('resultTopics');
    topicsEl.innerHTML = '';
    (thought.topics || []).forEach(t => {
        const span = document.createElement('span');
        span.className = 'tech-tag';
        span.textContent = t;
        topicsEl.appendChild(span);
    });

    const insightsEl = document.getElementById('resultInsights');
    insightsEl.innerHTML = '';
    (thought.key_insights || []).forEach(insight => {
        const li = document.createElement('li');
        li.textContent = insight;
        insightsEl.appendChild(li);
    });

    latestThought.style.display = 'block';
}

function showConnectorInsights(data) {
    let html = '';
    if (data.proactive_insight) {
        html += `<div class="proactive-banner">✦ <strong>Proactive Deduction:</strong> ${escapeHtml(data.proactive_insight)}</div>`;
    }
    if (data.connections?.length) {
        data.connections.forEach(c => {
            html += `<div class="connection-card">
                <strong>${escapeHtml(c.connection_type.toUpperCase())}</strong> (${escapeHtml(c.past_thought_date)} @ ${escapeHtml(c.past_location || 'Bay Area')}): 
                ${escapeHtml(c.explanation)}
            </div>`;
        });
    }
    if (html) {
        connectorContent.innerHTML = html;
        connectorInsights.style.display = 'block';
    }
}

// ── 9. Spatio-Temporal Radar Map (Leaflet) ─────────────────────────

function initMap() {
    if (leafletMap || typeof L === 'undefined') return;

    leafletMap = L.map('thoughtMap', {
        zoomControl: true,
        attributionControl: false
    }).setView([37.52, -122.22], 10);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        subdomains: 'abcd'
    }).addTo(leafletMap);

    loadMapPoints();
}

async function loadMapPoints() {
    if (!leafletMap) return;

    try {
        const res = await fetch('/api/map/points');
        const points = await res.json();

        mapMarkers.forEach(m => leafletMap.removeLayer(m));
        mapPolylines.forEach(p => leafletMap.removeLayer(p));
        mapMarkers = [];
        mapPolylines = [];

        if (!points || points.length === 0) return;

        const latLngs = [];
        points.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

        points.forEach(pt => {
            const lat = pt.latitude;
            const lng = pt.longitude;
            latLngs.push([lat, lng]);

            const color = pt.color || '#00f2fe';
            const customIcon = L.divIcon({
                className: 'radar-div-icon',
                html: `
                    <div class="radar-marker-pin" style="color:${color}">
                        <div class="radar-marker-pulse"></div>
                        <div class="radar-marker-core" style="background:${color}"></div>
                    </div>
                `,
                iconSize: [22, 22],
                iconAnchor: [11, 11]
            });

            const marker = L.marker([lat, lng], { icon: customIcon }).addTo(leafletMap);
            marker.on('click', () => {
                openThoughtInspector(pt);
            });
            mapMarkers.push(marker);
        });

        if (latLngs.length > 1) {
            const polyline = L.polyline(latLngs, {
                color: '#00f2fe',
                weight: 2,
                opacity: 0.7,
                dashArray: '5, 8'
            }).addTo(leafletMap);
            mapPolylines.push(polyline);
            leafletMap.fitBounds(polyline.getBounds(), { padding: [40, 40] });
        }
    } catch (err) {
        console.error("Map load error:", err);
    }
}

// ── 10. 3D Neural Knowledge Space (Native Three.js WebGL Galaxy) ───

let graph3DScene = null, graph3DCamera = null, graph3DRenderer = null, graph3DAnimationId = null;
let graph3DGroup = null, graph3DNodeMeshes = [];
let isGraphDragging = false, prevMousePos = { x: 0, y: 0 };

async function init3DGraph() {
    const container = document.getElementById('neural3DGraph');
    if (!container || typeof THREE === 'undefined') return;

    if (graph3DAnimationId) {
        cancelAnimationFrame(graph3DAnimationId);
    }
    container.innerHTML = '';

    const width = container.clientWidth || 980;
    const height = 540;

    graph3DScene = new THREE.Scene();
    graph3DCamera = new THREE.PerspectiveCamera(50, width / height, 1, 3000);
    graph3DCamera.position.set(0, 0, 310);

    graph3DRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    graph3DRenderer.setSize(width, height);
    graph3DRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(graph3DRenderer.domElement);

    // Ambient & Neon Point Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    graph3DScene.add(ambientLight);

    const pLight1 = new THREE.PointLight(0x00f2fe, 3.5, 700);
    pLight1.position.set(160, 160, 220);
    graph3DScene.add(pLight1);

    const pLight2 = new THREE.PointLight(0x8a2be2, 3.5, 700);
    pLight2.position.set(-160, -160, 220);
    graph3DScene.add(pLight2);

    graph3DGroup = new THREE.Group();
    graph3DScene.add(graph3DGroup);
    graph3DNodeMeshes = [];

    // Load graph data from API
    try {
        const res = await fetch('/api/graph');
        const data = await res.json();
        if (!data || !data.nodes || data.nodes.length === 0) return;

        const nodeMap = new Map();

        // 4 Key Pillar coordinates in 3D
        const themePillars = {
            'theme_tech': new THREE.Vector3(-85, 45, 25),
            'theme_work': new THREE.Vector3(85, 50, -25),
            'theme_family': new THREE.Vector3(-75, -55, -35),
            'theme_health': new THREE.Vector3(75, -50, 35)
        };

        data.nodes.forEach(n => {
            let pos;
            const isTheme = n.group === 'theme';
            if (isTheme && themePillars[n.id]) {
                pos = themePillars[n.id].clone();
            } else {
                let basePos = new THREE.Vector3(0, 0, 0);
                const col = (n.color || '').toLowerCase();
                if (col.includes('8b5cf6') || col.includes('00f2fe')) basePos = themePillars['theme_tech'];
                else if (col.includes('3b82f6') || col.includes('6366f1')) basePos = themePillars['theme_work'];
                else if (col.includes('ec4899') || col.includes('ff007f')) basePos = themePillars['theme_family'];
                else basePos = themePillars['theme_health'];

                const u = Math.random();
                const v = Math.random();
                const theta = u * 2.0 * Math.PI;
                const phi = Math.acos(2.0 * v - 1.0);
                const r = isTheme ? 70 : (30 + Math.random() * 50);

                const sinPhi = Math.sin(phi);
                pos = new THREE.Vector3(
                    basePos.x + r * sinPhi * Math.cos(theta),
                    basePos.y + r * sinPhi * Math.sin(theta),
                    basePos.z + r * Math.cos(phi)
                );
            }

            const size = isTheme ? 10 : 4.5;
            let colHex = 0x00f2fe;
            if (n.color) {
                colHex = parseInt(n.color.replace('#', '0x'), 16);
            }

            const sphereGeo = new THREE.SphereGeometry(size, 20, 20);
            const sphereMat = new THREE.MeshStandardMaterial({
                color: colHex,
                emissive: colHex,
                emissiveIntensity: isTheme ? 0.7 : 0.45,
                roughness: 0.25,
                metalness: 0.75
            });
            const mesh = new THREE.Mesh(sphereGeo, sphereMat);
            mesh.position.copy(pos);
            mesh.userData = n;

            // Halo ring for themes
            if (isTheme) {
                const ringGeo = new THREE.RingGeometry(size * 1.3, size * 1.6, 32);
                const ringMat = new THREE.MeshBasicMaterial({
                    color: colHex,
                    transparent: true,
                    opacity: 0.55,
                    side: THREE.DoubleSide
                });
                const ring = new THREE.Mesh(ringGeo, ringMat);
                ring.rotation.x = Math.PI / 2;
                mesh.add(ring);
            }

            // Crisp 2D Sprite Text Label
            const labelCanvas = document.createElement('canvas');
            const lCtx = labelCanvas.getContext('2d');
            labelCanvas.width = 256;
            labelCanvas.height = 64;
            lCtx.fillStyle = isTheme ? '#ffffff' : '#cbd5e1';
            lCtx.font = isTheme ? 'bold 20px Plus Jakarta Sans, sans-serif' : '16px Plus Jakarta Sans, sans-serif';
            lCtx.fillText(n.label.slice(0, 22), 8, 38);

            const spriteTex = new THREE.CanvasTexture(labelCanvas);
            const spriteMat = new THREE.SpriteMaterial({ map: spriteTex, transparent: true });
            const sprite = new THREE.Sprite(spriteMat);
            sprite.position.set(0, size + 8, 0);
            sprite.scale.set(36, 9, 1);
            mesh.add(sprite);

            graph3DGroup.add(mesh);
            nodeMap.set(n.id, mesh);
            graph3DNodeMeshes.push(mesh);
        });

        // Lines connecting related nodes
        const lineCoords = [];
        const rawLinks = data.links || data.edges || [];
        rawLinks.forEach(l => {
            const srcId = l.source || l.from;
            const tgtId = l.target || l.to;
            const m1 = nodeMap.get(srcId);
            const m2 = nodeMap.get(tgtId);
            if (m1 && m2) {
                lineCoords.push(m1.position.x, m1.position.y, m1.position.z);
                lineCoords.push(m2.position.x, m2.position.y, m2.position.z);
            }
        });

        if (lineCoords.length > 0) {
            const lineGeo = new THREE.BufferGeometry();
            lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(lineCoords, 3));
            const lineMat = new THREE.LineBasicMaterial({
                color: 0x00f2fe,
                transparent: true,
                opacity: 0.3
            });
            const lines = new THREE.LineSegments(lineGeo, lineMat);
            graph3DGroup.add(lines);
        }

    } catch (err) {
        console.error("3D Graph load error:", err);
    }

    // Mouse Interaction
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    container.onmousedown = (e) => {
        isGraphDragging = true;
        prevMousePos = { x: e.clientX, y: e.clientY };
    };

    window.onmouseup = () => {
        isGraphDragging = false;
    };

    container.onmousemove = (e) => {
        const rect = container.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / container.clientWidth) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / container.clientHeight) * 2 + 1;

        if (isGraphDragging && graph3DGroup) {
            const dx = e.clientX - prevMousePos.x;
            const dy = e.clientY - prevMousePos.y;
            graph3DGroup.rotation.y += dx * 0.005;
            graph3DGroup.rotation.x += dy * 0.005;
            prevMousePos = { x: e.clientX, y: e.clientY };
        }
    };

    container.onwheel = (e) => {
        e.preventDefault();
        graph3DCamera.position.z = Math.max(90, Math.min(550, graph3DCamera.position.z + e.deltaY * 0.35));
    };

    container.onclick = (e) => {
        const rect = container.getBoundingClientRect();
        mouse.x = ((e.clientX - rect.left) / container.clientWidth) * 2 - 1;
        mouse.y = -((e.clientY - rect.top) / container.clientHeight) * 2 + 1;

        raycaster.setFromCamera(mouse, graph3DCamera);
        const hits = raycaster.intersectObjects(graph3DNodeMeshes);
        if (hits.length > 0) {
            const hit = hits[0].object;
            if (hit.userData && hit.userData.full_data) {
                openThoughtInspector(hit.userData.full_data);
            }
        }
    };

    document.getElementById('resetGraphBtn')?.addEventListener('click', () => {
        if (graph3DGroup && graph3DCamera) {
            graph3DGroup.rotation.set(0, 0, 0);
            graph3DCamera.position.set(0, 0, 310);
        }
    });

    function animateGraph() {
        graph3DAnimationId = requestAnimationFrame(animateGraph);
        if (!isGraphDragging && graph3DGroup) {
            graph3DGroup.rotation.y += 0.0012; // Slow galactic rotation
        }
        graph3DRenderer.render(graph3DScene, graph3DCamera);
    }
    animateGraph();
}

function load3DGraphData() {
    init3DGraph();
}

// ── 11. Timeline View ──────────────────────────────────────────────

async function loadThoughts(searchQuery) {
    let url = '/api/thoughts';
    if (searchQuery) url = `/api/search?q=${encodeURIComponent(searchQuery)}`;

    try {
        const res = await fetch(url);
        const thoughts = await res.json();
        renderThoughts(thoughts, !!searchQuery);
    } catch (err) {
        thoughtsList.innerHTML = '<div class="empty-state-glass">Failed to load thoughts.</div>';
    }
}

function renderThoughts(thoughts, isSearch) {
    if (!thoughts.length) {
        thoughtsList.innerHTML = `<div class="empty-state-glass">${
            isSearch ? 'No matching thoughts found.' : 'No thoughts archived yet. Tap the orb and start speaking!'
        }</div>`;
        return;
    }

    thoughtsList.innerHTML = '';
    thoughts.forEach(t => {
        const card = document.createElement('div');
        card.className = 'timeline-thought-card';

        const dateObj = new Date(t.created_at);
        const dateStr = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const loc = t.location_name || (t.latitude ? `${Number(t.latitude).toFixed(3)}°, ${Number(t.longitude).toFixed(3)}°` : 'Bay Area');

        card.innerHTML = `
            <div class="card-top-meta">
                <span>${escapeHtml(dateStr)}</span>
                <span style="color:var(--neon-cyan)">📍 ${escapeHtml(loc)}</span>
            </div>
            <h4 class="card-summary-heading">${escapeHtml(t.summary || 'Episodic Memory')}</h4>
            <p class="card-transcript-snippet">"${escapeHtml(t.transcript || '')}"</p>
            <div class="pill-group" style="margin-top:auto">
                ${(t.topics || []).slice(0, 3).map(tp => `<span class="tech-tag">${escapeHtml(tp)}</span>`).join('')}
            </div>
        `;

        card.addEventListener('click', () => openThoughtInspector(t));
        thoughtsList.appendChild(card);
    });
}

searchBtn.addEventListener('click', () => {
    const q = searchInput.value.trim();
    loadThoughts(q);
});
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') searchBtn.click();
});

// ── 12. Universal Slide-In Thought Inspector ───────────────────────

function openThoughtInspector(t) {
    if (!thoughtInspectorDrawer) return;

    const dateObj = new Date(t.created_at);
    const dateStr = dateObj.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const loc = t.location_name || (t.latitude ? `${Number(t.latitude).toFixed(4)}°, ${Number(t.longitude).toFixed(4)}°` : 'Bay Area');

    document.getElementById('inspectorCategoryText').textContent = (t.category || (t.topics && t.topics[0]) || 'Thought');
    document.getElementById('inspectorDate').textContent = dateStr;
    document.getElementById('inspectorLocation').textContent = `📍 ${loc}`;
    document.getElementById('inspectorTitle').textContent = t.summary || 'Thought Reflection';
    document.getElementById('inspectorTranscript').textContent = `"${t.transcript || ''}"`;

    const topicsContainer = document.getElementById('inspectorTopics');
    topicsContainer.innerHTML = '';
    (t.topics || []).forEach(top => {
        const span = document.createElement('span');
        span.className = 'tech-tag';
        span.textContent = top;
        topicsContainer.appendChild(span);
    });

    const insightsList = document.getElementById('inspectorInsightsList');
    const insightsSec = document.getElementById('inspectorInsightsSection');
    insightsList.innerHTML = '';
    if (t.key_insights && t.key_insights.length) {
        insightsSec.style.display = 'block';
        t.key_insights.forEach(ins => {
            const li = document.createElement('li');
            li.textContent = ins;
            insightsList.appendChild(li);
        });
    } else {
        insightsSec.style.display = 'none';
    }

    thoughtInspectorDrawer.style.display = 'flex';
}

closeInspectorBtn?.addEventListener('click', () => {
    thoughtInspectorDrawer.style.display = 'none';
});

thoughtInspectorDrawer?.addEventListener('click', (e) => {
    if (e.target === thoughtInspectorDrawer) {
        thoughtInspectorDrawer.style.display = 'none';
    }
});

// ── 13. Pattern Synthesis ──────────────────────────────────────────

analyzeBtn.addEventListener('click', async () => {
    analyzeBtn.disabled = true;
    analyzeBtn.innerHTML = `<span>Synthesizing...</span>`;
    patternsResult.innerHTML = '<div class="empty-state-glass">Synthesizing long-horizon patterns with Gemini 3.7 Agent Swarm...</div>';

    try {
        const res = await fetch('/api/patterns');
        const data = await res.json();
        if (data.error) {
            patternsResult.innerHTML = `<div class="empty-state-glass">${escapeHtml(data.error)}.</div>`;
            return;
        }
        renderPatterns(data);
    } catch (err) {
        patternsResult.innerHTML = `<div class="empty-state-glass">Synthesis error: ${escapeHtml(err.message)}</div>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>
            <span>Run Full Synthesis</span>
        `;
    }
});

function renderPatterns(data) {
    let html = '';
    if (data.one_line_summary) {
        html += `<div class="one-line-synthesis">"${escapeHtml(data.one_line_summary)}"</div>`;
    }

    html += '<div class="pattern-grid">';

    if (data.mood_trajectory) {
        html += `
        <div class="pattern-box">
            <h4>Emotional Trajectory (${escapeHtml(data.mood_trajectory.trend)})</h4>
            <p style="font-size:13px; color:var(--text-secondary); line-height:1.5">${escapeHtml(data.mood_trajectory.summary)}</p>
        </div>`;
    }

    if (data.recurring_themes?.length) {
        html += `
        <div class="pattern-box">
            <h4>Durable Recurring Themes</h4>
            <ul class="insights-list">
                ${data.recurring_themes.map(t => `<li><strong>${escapeHtml(t.theme)}</strong> (${t.frequency}x): ${escapeHtml(t.description)}</li>`).join('')}
            </ul>
        </div>`;
    }

    if (data.emerging_patterns?.length) {
        html += `
        <div class="pattern-box">
            <h4>Emerging Behavioral Patterns</h4>
            <ul class="insights-list">
                ${data.emerging_patterns.map(p => `<li><strong>${escapeHtml(p.pattern)}</strong>: ${escapeHtml(p.evidence)}</li>`).join('')}
            </ul>
        </div>`;
    }

    if (data.recommendations?.length) {
        html += `
        <div class="pattern-box">
            <h4>AI Recommendations</h4>
            <ul class="insights-list">
                ${data.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
            </ul>
        </div>`;
    }

    html += '</div>';
    patternsResult.innerHTML = html;
}

// ── 14. Oracle Chat ────────────────────────────────────────────────

chatSendBtn.addEventListener('click', sendChatMessage);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) sendChatMessage();
});

async function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    appendChatBubble('user', message);
    chatInput.value = '';
    chatSendBtn.disabled = true;

    const typingEl = appendChatBubble('assistant', 'Synthesizing thought memory...');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: chatHistory })
        });
        const data = await res.json();

        typingEl.querySelector('.bubble-content p').textContent = data.response;

        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'model', content: data.response });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    } catch (err) {
        typingEl.querySelector('.bubble-content p').textContent = `Error: ${err.message}`;
    } finally {
        chatSendBtn.disabled = false;
        chatInput.focus();
    }
}

function appendChatBubble(role, text) {
    const div = document.createElement('div');
    div.className = `chat-bubble ${role}`;
    const iconSvg = role === 'user' ? 
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>` :
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00f2fe" stroke-width="2"><path d="M12 2L14.5 8.5L21 11L14.5 13.5L12 20L9.5 13.5L3 11L9.5 8.5L12 2Z"/></svg>`;

    div.innerHTML = `
        <div class="bubble-avatar">${iconSvg}</div>
        <div class="bubble-content"><p>${escapeHtml(text)}</p></div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

// ── 15. App Initialization ─────────────────────────────────────────

initCosmicBackground();
init3DAudioOrb();
initIndexedDB();
initGeolocation();
loadThoughts();
