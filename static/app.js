/**
 * ThoughtStash — Frontend Application Logic
 * Clean, minimal, light product design
 */

let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recordTimer = null;
let seconds = 0;
let currentGeo = { latitude: null, longitude: null, locationName: "Palo Alto, CA" };
let chatHistory = [];
let leafletMap = null;
let mapMarkers = [];
let mapPolylines = [];

// DOM Elements
const recordBtn = document.getElementById('recordBtn');
const recordStatus = document.getElementById('recordStatus');
const timerEl = document.getElementById('timer');
const locationBadge = document.getElementById('locationBadge');
const processing = document.getElementById('processing');
const latestThought = document.getElementById('latestThought');
const resultSummary = document.getElementById('resultSummary');
const resultMoodBadge = document.getElementById('resultMoodBadge');
const resultTimeLocation = document.getElementById('resultTimeLocation');
const resultTranscript = document.getElementById('resultTranscript');
const resultTopics = document.getElementById('resultTopics');
const resultInsights = document.getElementById('resultInsights');
const connectorInsights = document.getElementById('connectorInsights');
const connectorContent = document.getElementById('connectorContent');
const thoughtsList = document.getElementById('thoughtsList');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const analyzeBtn = document.getElementById('analyzeBtn');
const patternsResult = document.getElementById('patternsResult');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSendBtn = document.getElementById('chatSendBtn');

// ── 1. Tab Navigation ──────────────────────────────────────────────

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
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

// ── 2. Geolocation ─────────────────────────────────────────────────

function initGeolocation() {
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                currentGeo.latitude = pos.coords.latitude;
                currentGeo.longitude = pos.coords.longitude;
                if (locationBadge) {
                    locationBadge.querySelector('span').textContent = `${pos.coords.latitude.toFixed(3)}° N, ${pos.coords.longitude.toFixed(3)}° W`;
                }
            },
            () => {
                // Fallback coordinates
                currentGeo.latitude = 37.4419;
                currentGeo.longitude = -122.1430;
                currentGeo.locationName = "Palo Alto, CA";
            }
        );
    }
}

// ── 3. 3D Audio Visualizer (Clean Pearlescent Orb) ──────────────────

let orbScene, orbCamera, orbRenderer, orbGroup, orbParticles;
let audioContext, audioAnalyser, audioDataArray;
let orbAnimationId;

function init3DAudioOrb() {
    const container = document.getElementById('threeOrbCanvas');
    if (!container || typeof THREE === 'undefined') return;

    container.innerHTML = '';
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 320;

    orbScene = new THREE.Scene();
    orbCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    orbCamera.position.set(0, 0, 110);

    orbRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    orbRenderer.setSize(width, height);
    orbRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(orbRenderer.domElement);

    // Studio Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    orbScene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x3b82f6, 1.5);
    dirLight1.position.set(50, 50, 80);
    orbScene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x10b981, 1.2);
    dirLight2.position.set(-50, -50, 80);
    orbScene.add(dirLight2);

    orbGroup = new THREE.Group();
    orbScene.add(orbGroup);

    // Central Sphere (Soft Pearlescent)
    const coreGeo = new THREE.IcosahedronGeometry(22, 3);
    const coreMat = new THREE.MeshStandardMaterial({
        color: 0xf8fafc,
        roughness: 0.4,
        metalness: 0.1,
        transparent: true,
        opacity: 0.85
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    orbGroup.add(coreMesh);

    // Subtle Node Rings (Blue, Green, Amber, Coral)
    const nodeColors = [0x3b82f6, 0x10b981, 0xf59e0b, 0xef4444];
    const nodeCount = 8;
    const ringRadius = 36;
    const nodeMeshes = [];

    for (let i = 0; i < nodeCount; i++) {
        const angle = (i / nodeCount) * Math.PI * 2;
        const nGeo = new THREE.SphereGeometry(2.5, 16, 16);
        const col = nodeColors[i % nodeColors.length];
        const nMat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.2 });
        const nMesh = new THREE.Mesh(nGeo, nMat);
        nMesh.position.set(
            Math.cos(angle) * ringRadius,
            Math.sin(angle) * (ringRadius * 0.7),
            Math.sin(angle * 2) * 12
        );
        orbGroup.add(nMesh);
        nodeMeshes.push(nMesh);
    }

    // Connect nodes with light lines
    const lineCoords = [];
    for (let i = 0; i < nodeCount; i++) {
        const p1 = nodeMeshes[i].position;
        const p2 = nodeMeshes[(i + 1) % nodeCount].position;
        lineCoords.push(p1.x, p1.y, p1.z, p2.x, p2.y, p2.z);
        // Connect to center
        lineCoords.push(0, 0, 0, p1.x, p1.y, p1.z);
    }
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(lineCoords, 3));
    const lineMat = new THREE.LineBasicMaterial({ color: 0xcbd5e1, transparent: true, opacity: 0.6 });
    const lines = new THREE.LineSegments(lineGeo, lineMat);
    orbGroup.add(lines);

    function animateOrb() {
        orbAnimationId = requestAnimationFrame(animateOrb);

        let audioScale = 1.0;
        if (audioAnalyser && isRecording && audioDataArray) {
            audioAnalyser.getByteFrequencyData(audioDataArray);
            let sum = 0;
            for (let i = 0; i < audioDataArray.length; i++) sum += audioDataArray[i];
            const avg = sum / audioDataArray.length;
            audioScale = 1.0 + (avg / 255.0) * 0.4;
        }

        orbGroup.rotation.y += 0.005;
        orbGroup.rotation.x += 0.002;
        coreMesh.scale.set(audioScale, audioScale, audioScale);

        orbRenderer.render(orbScene, orbCamera);
    }
    animateOrb();
}

// ── 4. Voice Recording ─────────────────────────────────────────────

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
        
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioContext.createMediaStreamSource(stream);
            audioAnalyser = audioContext.createAnalyser();
            audioAnalyser.fftSize = 64;
            source.connect(audioAnalyser);
            audioDataArray = new Uint8Array(audioAnalyser.frequencyBinCount);
        } catch (e) {
            console.warn("AudioContext visualizer skipped:", e);
        }

        const selectedMime = getSupportedMimeType();
        const options = selectedMime ? { mimeType: selectedMime } : {};
        mediaRecorder = new MediaRecorder(stream, options);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());
            if (audioContext && audioContext.state !== 'closed') {
                audioContext.close();
            }
            if (audioChunks.length > 0) {
                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                await uploadThoughtAudio(audioBlob, mediaRecorder.mimeType);
            }
        };

        mediaRecorder.start(250);
        isRecording = true;
        seconds = 0;
        recordBtn.classList.add('recording');
        recordStatus.textContent = 'Listening...';
        timerEl.style.display = 'block';
        updateTimer();
        recordTimer = setInterval(() => { seconds++; updateTimer(); }, 1000);

    } catch (err) {
        alert(`Could not access microphone: ${err.message}`);
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    isRecording = false;
    clearInterval(recordTimer);
    recordBtn.classList.remove('recording');
    recordStatus.textContent = 'Processing voice note...';
    timerEl.style.display = 'none';
}

function updateTimer() {
    const m = String(Math.floor(seconds / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    timerEl.textContent = `${m}:${s}`;
}

// ── 5. Upload & Process Thought ────────────────────────────────────

async function uploadThoughtAudio(blob, mimeType) {
    latestThought.style.display = 'none';
    connectorInsights.style.display = 'none';
    processing.style.display = 'flex';

    const ext = (mimeType && mimeType.includes('mp4')) ? 'mp4' :
                (mimeType && mimeType.includes('wav')) ? 'wav' : 'webm';

    const formData = new FormData();
    formData.append('audio', blob, `note.${ext}`);
    formData.append('client_timestamp', new Date().toISOString());
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
        recordStatus.textContent = 'Tap to record a voice note';
        showThoughtResult(thought);
        pollConnectorInsights(thought.id);

        if (leafletMap) loadMapPoints();
        if (graph3DRenderer) init3DGraph();

    } catch (err) {
        recordStatus.textContent = `Error: ${err.message}`;
    } finally {
        processing.style.display = 'none';
    }
}

// Quick Text Input
const textInput = document.getElementById('textThoughtInput');
const textSubmit = document.getElementById('textThoughtSubmit');

async function handleTextThoughtSubmit() {
    if (!textInput) return;
    const text = textInput.value.trim();
    if (!text) return;

    textInput.value = '';
    textSubmit.disabled = true;
    textSubmit.textContent = 'Saving...';

    latestThought.style.display = 'none';
    connectorInsights.style.display = 'none';
    processing.style.display = 'flex';

    try {
        const payload = {
            text: text,
            latitude: currentGeo.latitude,
            longitude: currentGeo.longitude,
            location_name: currentGeo.locationName,
            client_timestamp: new Date().toISOString()
        };

        const res = await fetch('/api/thoughts/text', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Capture failed');
        }

        const thought = await res.json();
        showThoughtResult(thought);
        pollConnectorInsights(thought.id);

        if (leafletMap) loadMapPoints();
        if (graph3DRenderer) init3DGraph();

    } catch (err) {
        recordStatus.textContent = `Error: ${err.message}`;
    } finally {
        processing.style.display = 'none';
        textSubmit.disabled = false;
        textSubmit.textContent = 'Save';
    }
}

if (textSubmit) textSubmit.addEventListener('click', handleTextThoughtSubmit);
if (textInput) textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleTextThoughtSubmit();
});

function showThoughtResult(t) {
    resultSummary.textContent = t.summary || 'Voice Note';
    resultMoodBadge.textContent = t.mood || 'Reflective';
    
    const dateStr = t.created_at ? new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
    const locStr = t.location_name || 'Bay Area';
    resultTimeLocation.textContent = `${dateStr} · ${locStr}`;

    resultTranscript.textContent = `"${t.transcript || t.summary}"`;

    resultTopics.innerHTML = (t.topics || []).map(topic => 
        `<span class="topic-pill">${escapeHtml(topic)}</span>`
    ).join('') || '<span class="topic-pill">General</span>';

    resultInsights.innerHTML = (t.key_insights || []).map(ins => 
        `<li>${escapeHtml(ins)}</li>`
    ).join('') || `<li>Captured into your personal notebook.</li>`;

    latestThought.style.display = 'flex';
}

async function pollConnectorInsights(thoughtId) {
    let attempts = 0;
    const maxAttempts = 15;
    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await fetch(`/api/thoughts/${thoughtId}/connections`);
            const data = await res.json();
            if (data.status === 'completed' && data.connections) {
                clearInterval(interval);
                renderConnectorInsights(data);
            }
        } catch (err) {
            console.error("Connection poll error:", err);
        }
        if (attempts >= maxAttempts) clearInterval(interval);
    }, 2000);
}

function renderConnectorInsights(data) {
    if (!data.connections || data.connections.length === 0) return;
    let html = '';
    if (data.proactive_insight) {
        html += `<p style="margin-bottom:8px">💡 <strong>Observation:</strong> ${escapeHtml(data.proactive_insight)}</p>`;
    }
    html += '<ul class="bullet-list">';
    data.connections.forEach(c => {
        html += `<li><strong>${escapeHtml(c.connection_type || 'Relates to')}</strong> (${c.past_thought_date || ''}): ${escapeHtml(c.explanation || c.past_summary || '')}</li>`;
    });
    html += '</ul>';
    connectorContent.innerHTML = html;
    connectorInsights.style.display = 'block';
}

// ── 6. Walk Map (Light CartoDB Positron) ────────────────────────────

function initMap() {
    const mapEl = document.getElementById('thoughtMap');
    if (!mapEl || typeof L === 'undefined') return;

    leafletMap = L.map('thoughtMap').setView([37.4419, -122.1430], 11);

    // Light CartoDB Positron Basemap
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19
    }).addTo(leafletMap);

    loadMapPoints();
}

async function loadMapPoints() {
    if (!leafletMap) return;
    try {
        const res = await fetch('/api/map/points');
        const points = await res.json();
        if (!points || points.length === 0) return;

        mapMarkers.forEach(m => leafletMap.removeLayer(m));
        mapPolylines.forEach(p => leafletMap.removeLayer(p));
        mapMarkers = [];
        mapPolylines = [];

        const latLngs = [];
        points.forEach(pt => {
            const lat = pt.latitude;
            const lng = pt.longitude;
            latLngs.push([lat, lng]);

            const color = pt.color || '#3b82f6';
            const customIcon = L.divIcon({
                className: 'clean-marker',
                html: `<div class="marker-inner-dot" style="background-color:${color}"></div>`,
                iconSize: [16, 16],
                iconAnchor: [8, 8]
            });

            const marker = L.marker([lat, lng], { icon: customIcon }).addTo(leafletMap);
            marker.on('click', () => {
                openThoughtInspector(pt);
            });
            mapMarkers.push(marker);
        });

        if (latLngs.length > 1) {
            const polyline = L.polyline(latLngs, {
                color: '#3b82f6',
                weight: 2.5,
                opacity: 0.6,
                dashArray: '4, 6'
            }).addTo(leafletMap);
            mapPolylines.push(polyline);
            leafletMap.fitBounds(polyline.getBounds(), { padding: [40, 40] });
        } else if (latLngs.length === 1) {
            leafletMap.setView(latLngs[0], 13);
        }
    } catch (err) {
        console.error("Map load error:", err);
    }
}

// ── 7. Connections (Clean Light 3D Knowledge Graph) ────────────────

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
    graph3DCamera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
    graph3DCamera.position.set(0, 0, 320);

    graph3DRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    graph3DRenderer.setSize(width, height);
    graph3DRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(graph3DRenderer.domElement);

    // Studio Lights for clean light-mode rendering
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4);
    graph3DScene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.0);
    dirLight1.position.set(100, 100, 200);
    graph3DScene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xe2e8f0, 0.8);
    dirLight2.position.set(-100, -100, 150);
    graph3DScene.add(dirLight2);

    graph3DGroup = new THREE.Group();
    graph3DScene.add(graph3DGroup);
    graph3DNodeMeshes = [];

    try {
        const res = await fetch('/api/graph');
        const data = await res.json();
        if (!data || !data.nodes || data.nodes.length === 0) return;

        const nodeMap = new Map();

        // 4 Theme Hub Positions in 3D
        const themePillars = {
            'theme_tech': new THREE.Vector3(-85, 45, 20),
            'theme_work': new THREE.Vector3(85, 50, -20),
            'theme_family': new THREE.Vector3(-75, -55, -30),
            'theme_health': new THREE.Vector3(75, -50, 30)
        };

        data.nodes.forEach(n => {
            let pos;
            const isTheme = n.group === 'theme';
            if (isTheme && themePillars[n.id]) {
                pos = themePillars[n.id].clone();
            } else {
                let basePos = new THREE.Vector3(0, 0, 0);
                const col = (n.color || '').toLowerCase();
                if (col.includes('8b5cf6') || col.includes('3b82f6')) basePos = themePillars['theme_tech'];
                else if (col.includes('10b981') || col.includes('6366f1')) basePos = themePillars['theme_work'];
                else if (col.includes('f59e0b') || col.includes('ec4899')) basePos = themePillars['theme_family'];
                else basePos = themePillars['theme_health'];

                const u = Math.random();
                const v = Math.random();
                const theta = u * 2.0 * Math.PI;
                const phi = Math.acos(2.0 * v - 1.0);
                const r = isTheme ? 75 : (30 + Math.random() * 50);

                const sinPhi = Math.sin(phi);
                pos = new THREE.Vector3(
                    basePos.x + r * sinPhi * Math.cos(theta),
                    basePos.y + r * sinPhi * Math.sin(theta),
                    basePos.z + r * Math.cos(phi)
                );
            }

            const size = isTheme ? 9 : 4.2;
            let colHex = 0x3b82f6;
            if (n.color) {
                colHex = parseInt(n.color.replace('#', '0x'), 16);
            }

            // Clean smooth sphere
            const sphereGeo = new THREE.SphereGeometry(size, 24, 24);
            const sphereMat = new THREE.MeshStandardMaterial({
                color: colHex,
                roughness: 0.3,
                metalness: 0.1
            });
            const mesh = new THREE.Mesh(sphereGeo, sphereMat);
            mesh.position.copy(pos);
            mesh.userData = n;

            // Halo ring for theme hubs (as in inspiration node graphic)
            if (isTheme) {
                const ringGeo = new THREE.RingGeometry(size * 1.3, size * 1.65, 32);
                const ringMat = new THREE.MeshBasicMaterial({
                    color: 0xcbd5e1,
                    side: THREE.DoubleSide
                });
                const ring = new THREE.Mesh(ringGeo, ringMat);
                ring.rotation.x = Math.PI / 2;
                mesh.add(ring);
            }

            // Clean 2D Label
            const labelCanvas = document.createElement('canvas');
            const lCtx = labelCanvas.getContext('2d');
            labelCanvas.width = 256;
            labelCanvas.height = 64;
            
            // White badge with subtle shadow
            lCtx.fillStyle = '#ffffff';
            lCtx.fillRect(4, 8, 248, 48);
            lCtx.lineWidth = 2;
            lCtx.strokeStyle = '#e2e8f0';
            lCtx.strokeRect(4, 8, 248, 48);

            lCtx.fillStyle = '#0f172a';
            lCtx.font = isTheme ? 'bold 20px Plus Jakarta Sans, sans-serif' : '16px Plus Jakarta Sans, sans-serif';
            lCtx.fillText(n.label.slice(0, 20), 16, 38);

            const spriteTex = new THREE.CanvasTexture(labelCanvas);
            const spriteMat = new THREE.SpriteMaterial({ map: spriteTex, transparent: true });
            const sprite = new THREE.Sprite(spriteMat);
            sprite.position.set(0, size + 9, 0);
            sprite.scale.set(34, 8.5, 1);
            mesh.add(sprite);

            graph3DGroup.add(mesh);
            nodeMap.set(n.id, mesh);
            graph3DNodeMeshes.push(mesh);
        });

        // Clean grey connecting lines (matching inspiration graph)
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
                color: 0xcbd5e1,
                transparent: true,
                opacity: 0.75
            });
            const lines = new THREE.LineSegments(lineGeo, lineMat);
            graph3DGroup.add(lines);
        }

    } catch (err) {
        console.error("3D Graph load error:", err);
    }

    // Mouse Controls
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
        graph3DCamera.position.z = Math.max(100, Math.min(600, graph3DCamera.position.z + e.deltaY * 0.35));
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
            graph3DCamera.position.set(0, 0, 320);
        }
    });

    function animateGraph() {
        graph3DAnimationId = requestAnimationFrame(animateGraph);
        if (!isGraphDragging && graph3DGroup) {
            graph3DGroup.rotation.y += 0.001;
        }
        graph3DRenderer.render(graph3DScene, graph3DCamera);
    }
    animateGraph();
}

// ── 8. Timeline (All Notes) ────────────────────────────────────────

async function loadThoughts(searchQuery) {
    let url = '/api/thoughts';
    if (searchQuery) {
        url = `/api/search?q=${encodeURIComponent(searchQuery)}`;
    }

    try {
        const res = await fetch(url);
        const thoughts = await res.json();

        if (!thoughts || thoughts.length === 0) {
            thoughtsList.innerHTML = '<div class="empty-state">No notes found. Record a thought or adjust search filter.</div>';
            return;
        }

        thoughtsList.innerHTML = thoughts.map(t => {
            const dateStr = t.created_at ? new Date(t.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
            const locStr = t.location_name || 'Bay Area';
            const topicsHtml = (t.topics || []).slice(0, 3).map(tp => `<span class="topic-pill">${escapeHtml(tp)}</span>`).join('');

            return `
                <div class="note-item-card" onclick='openThoughtInspectorById(${t.id})'>
                    <div class="note-meta-row">
                        <span>${escapeHtml(dateStr)}</span>
                        <span>${escapeHtml(locStr)}</span>
                    </div>
                    <div class="note-summary">${escapeHtml(t.summary || 'Voice Note')}</div>
                    <div class="note-snippet">${escapeHtml(t.transcript || t.summary || '')}</div>
                    <div class="tags-row">${topicsHtml}</div>
                </div>
            `;
        }).join('');

    } catch (err) {
        thoughtsList.innerHTML = `<div class="empty-state">Error loading notes: ${err.message}</div>`;
    }
}

searchBtn.addEventListener('click', () => loadThoughts(searchInput.value.trim()));
searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') loadThoughts(searchInput.value.trim());
});

// ── 9. Patterns Tab ────────────────────────────────────────────────

analyzeBtn.addEventListener('click', async () => {
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Analyzing...';
    patternsResult.innerHTML = '<div class="empty-state">Reviewing multi-week recordings and identifying patterns...</div>';

    try {
        const res = await fetch('/api/patterns');
        const data = await res.json();
        renderPatternsDashboard(data);
    } catch (err) {
        patternsResult.innerHTML = `<div class="empty-state">Analysis error: ${err.message}</div>`;
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.innerHTML = `
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m3 3 7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="m13 13 6 6"/></svg>
            <span>Analyze Notes</span>
        `;
    }
});

function renderPatternsDashboard(data) {
    if (!data) return;
    let html = `
        <div class="pattern-overview-card">
            <h3>Overview</h3>
            <p>${escapeHtml(data.one_line_summary || 'Multi-week note synthesis')}</p>
        </div>
        <div class="pattern-grid">
    `;

    if (data.mood_trajectory) {
        html += `
            <div class="pattern-block">
                <h4>Energy & Mood</h4>
                <p style="font-size:13px;color:var(--text-secondary);line-height:1.5">${escapeHtml(data.mood_trajectory.summary || '')}</p>
            </div>
        `;
    }

    if (data.recurring_themes?.length) {
        html += `
            <div class="pattern-block">
                <h4>Recurring Themes</h4>
                <ul class="bullet-list">
                    ${data.recurring_themes.map(t => `<li><strong>${escapeHtml(t.theme)}</strong>: ${escapeHtml(t.description)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    if (data.emerging_patterns?.length) {
        html += `
            <div class="pattern-block">
                <h4>Habits & Routines</h4>
                <ul class="bullet-list">
                    ${data.emerging_patterns.map(p => `<li><strong>${escapeHtml(p.pattern)}</strong>: ${escapeHtml(p.evidence)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    if (data.recommendations?.length) {
        html += `
            <div class="pattern-block">
                <h4>Suggestions</h4>
                <ul class="bullet-list">
                    ${data.recommendations.map(r => `<li>${escapeHtml(r)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    html += '</div>';
    patternsResult.innerHTML = html;
}

// ── 10. Ask / Chat ─────────────────────────────────────────────────

chatSendBtn.addEventListener('click', sendChatMessage);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) sendChatMessage();
});

document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
        const text = chip.dataset.prompt;
        if (text) {
            chatInput.value = text;
            sendChatMessage();
        }
    });
});

async function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    appendChatBubble('user', message);
    chatInput.value = '';
    chatSendBtn.disabled = true;

    const typingEl = appendChatBubble('assistant', 'Searching notes...');

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history: chatHistory })
        });
        const data = await res.json();

        typingEl.querySelector('.bubble-body p').textContent = data.response;

        chatHistory.push({ role: 'user', content: message });
        chatHistory.push({ role: 'model', content: data.response });
        if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    } catch (err) {
        typingEl.querySelector('.bubble-body p').textContent = `Error: ${err.message}`;
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
        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`;

    div.innerHTML = `
        <div class="bubble-avatar">${iconSvg}</div>
        <div class="bubble-body"><p>${escapeHtml(text)}</p></div>
    `;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

// ── 11. Slide-In Detail Drawer ─────────────────────────────────────

const drawer = document.getElementById('thoughtInspectorDrawer');
const closeDrawerBtn = document.getElementById('closeInspectorBtn');

function openThoughtInspector(data) {
    if (!data) return;
    document.getElementById('inspectorCategoryText').textContent = data.mood || 'Note';
    document.getElementById('inspectorDate').textContent = data.created_at ? new Date(data.created_at).toLocaleDateString() : '';
    document.getElementById('inspectorLocation').textContent = data.location_name || 'Bay Area';
    document.getElementById('inspectorTitle').textContent = data.summary || 'Voice Note';
    document.getElementById('inspectorTranscript').textContent = `"${data.transcript || data.summary || ''}"`;

    const topicsEl = document.getElementById('inspectorTopics');
    topicsEl.innerHTML = (data.topics || []).map(tp => `<span class="topic-pill">${escapeHtml(tp)}</span>`).join('') || '<span class="topic-pill">General</span>';

    const insightsEl = document.getElementById('inspectorInsightsList');
    insightsEl.innerHTML = (data.key_insights || []).map(ins => `<li>${escapeHtml(ins)}</li>`).join('') || '<li>Recorded in your notebook.</li>';

    drawer.style.display = 'flex';
}

async function openThoughtInspectorById(id) {
    try {
        const res = await fetch(`/api/thoughts`);
        const thoughts = await res.json();
        const found = thoughts.find(t => t.id === id);
        if (found) openThoughtInspector(found);
    } catch (e) {
        console.error(e);
    }
}

if (closeDrawerBtn) {
    closeDrawerBtn.addEventListener('click', () => {
        drawer.style.display = 'none';
    });
}

if (drawer) {
    drawer.addEventListener('click', (e) => {
        if (e.target === drawer) drawer.style.display = 'none';
    });
}

window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawer) {
        drawer.style.display = 'none';
    }
});

// Helper
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── 12. Init ───────────────────────────────────────────────────────

init3DAudioOrb();
initGeolocation();
loadThoughts();
