/**
 * ThoughtStash — Frontend Application Logic
 * Stone & Paper Design System
 */

let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recordTimer = null;
let seconds = 0;
let currentGeo = { latitude: 37.4419, longitude: -122.1430, locationName: "Palo Alto, CA", isManual: false };
let currentConversationId = "conv_" + Date.now();
let chatHistory = [];
let leafletMap = null;
let mapMarkers = [];
let mapPolylines = [];
let isMapMode = false;

function formatDate(isoStr) {
    if (!isoStr) return "Recent";
    try {
        const d = new Date(isoStr.replace("Z", "+00:00"));
        if (isNaN(d.getTime())) return isoStr.slice(0, 10);
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    } catch (e) {
        return (isoStr || "").slice(0, 10);
    }
}

// DOM Elements
const recordBtn = document.getElementById("recordBtn");
const recordStatus = document.getElementById("recordStatus");
const timerEl = document.getElementById("timer");
const cancelRecordingBtn = document.getElementById("cancelRecordingBtn");
const locationBadge = document.getElementById("locationBadge");
const processing = document.getElementById("processing");
const latestThought = document.getElementById("latestThought");
const deleteLatestThoughtBtn = document.getElementById("deleteLatestThoughtBtn");
const resultSummary = document.getElementById("resultSummary");
const resultMoodBadge = document.getElementById("resultMoodBadge");
const resultTimeLocation = document.getElementById("resultTimeLocation");
const resultTranscript = document.getElementById("resultTranscript");
const resultTopics = document.getElementById("resultTopics");
const resultInsights = document.getElementById("resultInsights");
const connectorInsights = document.getElementById("connectorInsights");
const connectorContent = document.getElementById("connectorContent");
const thoughtsList = document.getElementById("thoughtsList");
const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const chatMessages = document.getElementById("chatMessages");
const chatInput = document.getElementById("chatInput");
const chatSendBtn = document.getElementById("chatSendBtn");
const newChatBtn = document.getElementById("newChatBtn");
const drawer = document.getElementById("thoughtInspectorDrawer");
const closeDrawerBtn = document.getElementById("closeInspectorBtn");
const drawerDeleteBtn = document.getElementById("drawerDeleteBtn");

// ── 1. Tab Navigation (4 Consolidated Tabs) ─────────────────────────

document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-view").forEach(v => v.classList.remove("active"));

        btn.classList.add("active");
        const targetId = btn.dataset.tab;
        const targetView = document.getElementById(targetId);
        if (targetView) targetView.classList.add("active");

        if (targetId === "timelineTab") {
            loadThoughts();
        }
        if (targetId === "connectionsTab") {
            if (!isMapMode) {
                setTimeout(() => init3DGraph(), 60);
            } else {
                setTimeout(() => {
                    if (!leafletMap) initMap();
                    else leafletMap.invalidateSize();
                }, 100);
            }
        }
        if (targetId === "chatTab") {
            setTimeout(() => chatInput?.focus(), 100);
        }
    });
});

// ── 2. Geolocation & Reverse Geocoding ──────────────────────────────

function initGeolocation() {
    updateLocationBadge();

    const locationBadgeEl = document.getElementById("locationBadge");
    const locationModalEl = document.getElementById("locationModal");
    const closeLocationModalBtnEl = document.getElementById("closeLocationModalBtn");
    const detectGpsBtnEl = document.getElementById("detectGpsBtn");
    const customLocationInputEl = document.getElementById("customLocationInput");
    const applyLocationBtnEl = document.getElementById("applyLocationBtn");

    if (locationBadgeEl && locationModalEl) {
        locationBadgeEl.addEventListener("click", () => {
            locationModalEl.style.display = "flex";
        });
    }

    if (closeLocationModalBtnEl && locationModalEl) {
        closeLocationModalBtnEl.addEventListener("click", () => {
            locationModalEl.style.display = "none";
        });
    }

    if (locationModalEl) {
        locationModalEl.addEventListener("click", (e) => {
            if (e.target === locationModalEl) locationModalEl.style.display = "none";
        });
    }

    if (detectGpsBtnEl) {
        detectGpsBtnEl.addEventListener("click", () => {
            if (!("geolocation" in navigator)) {
                alert("Geolocation is not supported by your browser.");
                return;
            }
            detectGpsBtnEl.disabled = true;
            const origText = detectGpsBtnEl.querySelector("span").textContent;
            detectGpsBtnEl.querySelector("span").textContent = "Acquiring GPS...";

            navigator.geolocation.getCurrentPosition(
                async (pos) => {
                    currentGeo.latitude = pos.coords.latitude;
                    currentGeo.longitude = pos.coords.longitude;
                    currentGeo.isManual = false;
                    await resolveCoordinatesName(pos.coords.latitude, pos.coords.longitude);
                    detectGpsBtnEl.disabled = false;
                    detectGpsBtnEl.querySelector("span").textContent = origText;
                    if (locationModalEl) locationModalEl.style.display = "none";
                },
                (err) => {
                    detectGpsBtnEl.disabled = false;
                    detectGpsBtnEl.querySelector("span").textContent = origText;
                    alert("GPS unavailable (" + err.message + "). On http:// connections, please pick a preset spot or type your location!");
                },
                { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
            );
        });
    }

    document.querySelectorAll(".place-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const name = chip.dataset.name;
            const lat = parseFloat(chip.dataset.lat);
            const lon = parseFloat(chip.dataset.lon);
            if (name && !isNaN(lat) && !isNaN(lon)) {
                currentGeo.locationName = name;
                currentGeo.latitude = lat;
                currentGeo.longitude = lon;
                currentGeo.isManual = true;
                updateLocationBadge();
                if (locationModalEl) locationModalEl.style.display = "none";
            }
        });
    });

    async function applyCustomLocation() {
        if (!customLocationInputEl) return;
        const query = customLocationInputEl.value.trim();
        if (!query) return;

        if (applyLocationBtnEl) {
            applyLocationBtnEl.disabled = true;
            applyLocationBtnEl.textContent = "...";
        }

        try {
            const res = await fetch("/api/geo/search?q=" + encodeURIComponent(query));
            if (res.ok) {
                const data = await res.json();
                currentGeo.locationName = data.name || query;
                currentGeo.latitude = data.lat;
                currentGeo.longitude = data.lon;
                currentGeo.isManual = true;
                updateLocationBadge();
                if (locationModalEl) locationModalEl.style.display = "none";
            }
        } catch (e) {
            console.error("Location search error:", e);
        } finally {
            if (applyLocationBtnEl) {
                applyLocationBtnEl.disabled = false;
                applyLocationBtnEl.textContent = "Set";
            }
        }
    }

    if (applyLocationBtnEl) {
        applyLocationBtnEl.addEventListener("click", applyCustomLocation);
    }
    if (customLocationInputEl) {
        customLocationInputEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter") applyCustomLocation();
        });
    }
}

async function resolveCoordinatesName(lat, lon) {
    try {
        const res = await fetch("/api/geo/reverse?lat=" + lat + "&lon=" + lon);
        if (res.ok) {
            const data = await res.json();
            currentGeo.locationName = data.location_name || lat.toFixed(4) + ", " + lon.toFixed(4);
            updateLocationBadge();
        }
    } catch (e) {
        currentGeo.locationName = lat.toFixed(4) + ", " + lon.toFixed(4);
        updateLocationBadge();
    }
}

function updateLocationBadge() {
    const textEl = document.getElementById("locationBadgeText");
    if (textEl) {
        textEl.textContent = currentGeo.locationName || "Set Location";
    }
}

// ── 3. 3D Audio Visualizer (Fluid Organic Neural Constellation) ─────

let orbScene, orbCamera, orbRenderer, orbGroup;
let audioAnalyser, audioDataArray;
let orbAnimationId;
let orbNodes = [];
let orbEdges = [];
let orbLinesMesh = null;
let ribbonInnerMesh = null, ribbonOuterMesh = null;
let pulseParticles = [];
let smoothedAudioScale = 1.0;
let smoothedAudioEnergy = 0.0;

function init3DAudioOrb() {
    const container = document.getElementById("threeOrbCanvas");
    if (!container || typeof THREE === "undefined") return;

    if (orbAnimationId) {
        cancelAnimationFrame(orbAnimationId);
        orbAnimationId = null;
    }
    if (orbRenderer) {
        try {
            orbRenderer.dispose();
            orbRenderer.forceContextLoss();
        } catch (e) {}
        orbRenderer = null;
    }

    container.innerHTML = "";
    const width = container.clientWidth || container.parentElement?.clientWidth || 800;
    const height = container.clientHeight || 290;

    orbScene = new THREE.Scene();
    orbCamera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    orbCamera.position.set(0, 0, 168);

    orbRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    orbRenderer.setSize(width, height);
    orbRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(orbRenderer.domElement);

    // Warm Studio Lighting (Balanced to prevent blowing out matte colors)
    const ambientLight = new THREE.AmbientLight(0xFAF8F5, 0.95);
    orbScene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xEAE5D8, 0.85);
    dirLight1.position.set(80, 80, 100);
    orbScene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xD8D6CE, 0.55);
    dirLight2.position.set(-80, -60, 80);
    orbScene.add(dirLight2);

    orbGroup = new THREE.Group();
    orbScene.add(orbGroup);

    // Dual soft ambient breathing aura rings (subtle rippling halos behind mic button)
    const aura1Geo = new THREE.RingGeometry(64, 65.5, 64);
    const aura1Mat = new THREE.MeshBasicMaterial({
        color: 0x1D4E4B,
        transparent: true,
        opacity: 0.14,
        side: THREE.DoubleSide
    });
    const aura1Mesh = new THREE.Mesh(aura1Geo, aura1Mat);
    orbGroup.add(aura1Mesh);

    const aura2Geo = new THREE.RingGeometry(72, 73.2, 64);
    const aura2Mat = new THREE.MeshBasicMaterial({
        color: 0xB3732A,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide
    });
    const aura2Mesh = new THREE.Mesh(aura2Geo, aura2Mat);
    orbGroup.add(aura2Mesh);

    // Earthy Matte Palette: Slate Indigo, Ochre, Terracotta, Forest Green, Ocean Teal, Velvet Plum, Berry Rose
    const nodeColors = [0x2D5B88, 0xB3732A, 0xB8573D, 0x3F7A56, 0x1C7C75, 0x7B4B88, 0xA84A6E];
    const nodeMeshes = [];
    orbNodes = [];
    orbEdges = [];

    // Inner Tier (12 nodes, base radius ~76 - 92)
    const innerCount = 12;
    for (let i = 0; i < innerCount; i++) {
        const baseAngle = (i / innerCount) * Math.PI * 2;
        const baseRadius = 78 + (i % 3) * 6;
        const baseZ = (Math.sin(i * 2.2) * 14) - 4;
        const size = 2.4 + (i % 3) * 0.5;
        const col = nodeColors[i % nodeColors.length];

        const nGeo = new THREE.SphereGeometry(size, 20, 20);
        const nMat = new THREE.MeshStandardMaterial({
            color: col,
            roughness: 0.75,
            metalness: 0.05
        });
        const nMesh = new THREE.Mesh(nGeo, nMat);
        orbGroup.add(nMesh);
        nodeMeshes.push(nMesh);

        orbNodes.push({
            mesh: nMesh,
            tier: 0,
            baseAngle: baseAngle,
            orbitSpeed: 0.00045 + (i % 2) * 0.0002, // clockwise
            baseRadius: baseRadius,
            aspect: 0.74,
            waveFreq: 0.8 + (i % 4) * 0.2,
            waveAmp: 5 + (i % 3) * 2,
            zFreq: 0.6 + (i % 3) * 0.25,
            zAmp: 7,
            baseZ: baseZ,
            phase: i * 0.9
        });
    }

    // Outer Tier (16 nodes, base radius ~122 - 168)
    const outerCount = 16;
    for (let j = 0; j < outerCount; j++) {
        const baseAngle = (j / outerCount) * Math.PI * 2 + 0.25;
        const baseRadius = 124 + (j % 4) * 11;
        const baseZ = (Math.cos(j * 1.8) * 20) - 6;
        const size = 2.0 + (j % 3) * 0.6;
        const col = nodeColors[(j + 2) % nodeColors.length];

        const nGeo = new THREE.SphereGeometry(size, 18, 18);
        const nMat = new THREE.MeshStandardMaterial({
            color: col,
            roughness: 0.8,
            metalness: 0.0
        });
        const nMesh = new THREE.Mesh(nGeo, nMat);
        orbGroup.add(nMesh);
        nodeMeshes.push(nMesh);

        orbNodes.push({
            mesh: nMesh,
            tier: 1,
            baseAngle: baseAngle,
            orbitSpeed: -(0.00035 + (j % 3) * 0.00015), // counter-clockwise drift
            baseRadius: baseRadius,
            aspect: 0.68,
            waveFreq: 0.7 + (j % 4) * 0.18,
            waveAmp: 7 + (j % 4) * 2.5,
            zFreq: 0.5 + (j % 3) * 0.2,
            zAmp: 10,
            baseZ: baseZ,
            phase: (j + 12) * 0.85
        });
    }

    const totalNodes = orbNodes.length;

    // Define Network Graph Topology (Edges)
    // 1. Inner loop
    for (let i = 0; i < innerCount; i++) {
        orbEdges.push({ u: i, v: (i + 1) % innerCount });
    }
    // 2. Outer loop
    for (let j = 0; j < outerCount; j++) {
        const u = innerCount + j;
        const v = innerCount + ((j + 1) % outerCount);
        orbEdges.push({ u, v });
    }
    // 3. Radial spokes connecting inner to outer tier
    for (let i = 0; i < innerCount; i++) {
        const targetOuter1 = innerCount + Math.floor((i / innerCount) * outerCount);
        const targetOuter2 = innerCount + ((Math.floor((i / innerCount) * outerCount) + 1) % outerCount);
        orbEdges.push({ u: i, v: targetOuter1 });
        if (i % 2 === 0) {
            orbEdges.push({ u: i, v: targetOuter2 });
        }
    }
    // 4. Subtle inner cross-chords
    for (let i = 0; i < innerCount; i += 3) {
        orbEdges.push({ u: i, v: (i + 4) % innerCount });
    }

    // Allocate Dynamic Real-time Line Buffer
    const linePositions = new Float32Array(orbEdges.length * 2 * 3);
    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.BufferAttribute(linePositions, 3));
    const lineMat = new THREE.LineBasicMaterial({
        color: 0xCDC9BD,
        transparent: true,
        opacity: 0.55
    });
    orbLinesMesh = new THREE.LineSegments(lineGeo, lineMat);
    orbGroup.add(orbLinesMesh);

    // Smooth undulating flowing stream ribbon curves (Catmull-Rom closed splines)
    const ribbonPtsCount = 64;
    const innerRibbonGeo = new THREE.BufferGeometry().setFromPoints(new Array(ribbonPtsCount).fill(new THREE.Vector3()));
    const innerRibbonMat = new THREE.LineBasicMaterial({
        color: 0x1D4E4B,
        transparent: true,
        opacity: 0.16
    });
    ribbonInnerMesh = new THREE.LineLoop(innerRibbonGeo, innerRibbonMat);
    orbGroup.add(ribbonInnerMesh);

    const outerRibbonGeo = new THREE.BufferGeometry().setFromPoints(new Array(ribbonPtsCount).fill(new THREE.Vector3()));
    const outerRibbonMat = new THREE.LineBasicMaterial({
        color: 0xB3732A,
        transparent: true,
        opacity: 0.12
    });
    ribbonOuterMesh = new THREE.LineLoop(outerRibbonGeo, outerRibbonMat);
    orbGroup.add(ribbonOuterMesh);

    // Floating Stardust Thought Pulses (Traveling along network connections)
    pulseParticles = [];
    const pulseCount = 7;
    const pulseGeo = new THREE.SphereGeometry(1.4, 12, 12);
    for (let p = 0; p < pulseCount; p++) {
        const pMat = new THREE.MeshBasicMaterial({
            color: nodeColors[p % nodeColors.length],
            transparent: true,
            opacity: 0.75
        });
        const pMesh = new THREE.Mesh(pulseGeo, pMat);
        orbGroup.add(pMesh);
        pulseParticles.push({
            mesh: pMesh,
            edgeIdx: Math.floor(Math.random() * orbEdges.length),
            progress: Math.random(),
            speed: 0.004 + Math.random() * 0.004
        });
    }

    // Responsive window/tab resize observer
    if (window.ResizeObserver) {
        const ro = new ResizeObserver(entries => {
            for (let entry of entries) {
                const nw = entry.contentRect.width;
                const nh = entry.contentRect.height;
                if (nw > 0 && nh > 0 && orbRenderer && orbCamera) {
                    orbCamera.aspect = nw / nh;
                    orbCamera.updateProjectionMatrix();
                    orbRenderer.setSize(nw, nh);
                }
            }
        });
        ro.observe(container);
    }

    let clock = 0;
    function animateOrb() {
        orbAnimationId = requestAnimationFrame(animateOrb);
        clock += 0.014;

        // Smoothly interpolate audio energy
        let targetAudioScale = 1.0;
        let targetAudioEnergy = 0.0;
        if (audioAnalyser && isRecording && audioDataArray) {
            audioAnalyser.getByteFrequencyData(audioDataArray);
            let sum = 0;
            for (let i = 0; i < audioDataArray.length; i++) sum += audioDataArray[i];
            const avg = sum / audioDataArray.length;
            targetAudioEnergy = avg / 255.0;
            targetAudioScale = 1.0 + targetAudioEnergy * 0.28;
        }

        smoothedAudioScale += (targetAudioScale - smoothedAudioScale) * 0.1;
        smoothedAudioEnergy += (targetAudioEnergy - smoothedAudioEnergy) * 0.1;

        // 1. Update all 28 nodes with organic smooth harmonic flow
        for (let i = 0; i < totalNodes; i++) {
            const n = orbNodes[i];
            const currentAngle = n.baseAngle + (clock * n.orbitSpeed * 10) * (isRecording ? 1.5 : 1.0);
            const rHarmonic = Math.sin(clock * n.waveFreq + n.phase) * n.waveAmp;
            const currentR = (n.baseRadius + rHarmonic) * smoothedAudioScale;

            n.mesh.position.x = Math.cos(currentAngle) * currentR;
            n.mesh.position.y = Math.sin(currentAngle) * (currentR * n.aspect);
            n.mesh.position.z = n.baseZ + Math.sin(clock * n.zFreq + n.phase * 1.3) * n.zAmp;
        }

        // 2. Real-time dynamic recalculation of connecting lines
        const posArray = orbLinesMesh.geometry.attributes.position.array;
        let ptr = 0;
        for (let e = 0; e < orbEdges.length; e++) {
            const p1 = orbNodes[orbEdges[e].u].mesh.position;
            const p2 = orbNodes[orbEdges[e].v].mesh.position;
            posArray[ptr++] = p1.x;
            posArray[ptr++] = p1.y;
            posArray[ptr++] = p1.z;
            posArray[ptr++] = p2.x;
            posArray[ptr++] = p2.y;
            posArray[ptr++] = p2.z;
        }
        orbLinesMesh.geometry.attributes.position.needsUpdate = true;

        // 3. Smooth undulating neural stream ribbons
        const innerCtrlPts = [];
        const innerCPCount = 8;
        for (let k = 0; k < innerCPCount; k++) {
            const a = (k / innerCPCount) * Math.PI * 2 + clock * 0.12;
            const r = (72 + Math.sin(clock * 1.4 + k * 1.2) * 7.5) * smoothedAudioScale;
            innerCtrlPts.push(new THREE.Vector3(
                Math.cos(a) * r,
                Math.sin(a) * (r * 0.74),
                Math.cos(clock * 0.8 + k) * 6
            ));
        }
        const innerCurve = new THREE.CatmullRomCurve3(innerCtrlPts, true);
        const innerSampledPts = innerCurve.getPoints(ribbonPtsCount - 1);
        ribbonInnerMesh.geometry.setFromPoints(innerSampledPts);

        const outerCtrlPts = [];
        const outerCPCount = 10;
        for (let k = 0; k < outerCPCount; k++) {
            const a = (k / outerCPCount) * Math.PI * 2 - clock * 0.08;
            const r = (136 + Math.cos(clock * 1.1 + k * 1.4) * 12) * smoothedAudioScale;
            outerCtrlPts.push(new THREE.Vector3(
                Math.cos(a) * r,
                Math.sin(a) * (r * 0.68),
                Math.sin(clock * 0.7 + k) * 9
            ));
        }
        const outerCurve = new THREE.CatmullRomCurve3(outerCtrlPts, true);
        const outerSampledPts = outerCurve.getPoints(ribbonPtsCount - 1);
        ribbonOuterMesh.geometry.setFromPoints(outerSampledPts);

        // 4. Floating stardust signal pulses along active connections
        for (let p = 0; p < pulseParticles.length; p++) {
            const particle = pulseParticles[p];
            particle.progress += particle.speed * (isRecording ? 1.8 : 1.0);
            if (particle.progress >= 1.0) {
                particle.progress = 0;
                // Transition to an edge connected to destination
                const prevEdge = orbEdges[particle.edgeIdx];
                const destNode = prevEdge.v;
                const candidateEdges = orbEdges.filter((ed, idx) => (ed.u === destNode || ed.v === destNode) && idx !== particle.edgeIdx);
                if (candidateEdges.length > 0) {
                    const nextEdge = candidateEdges[Math.floor(Math.random() * candidateEdges.length)];
                    particle.edgeIdx = orbEdges.indexOf(nextEdge);
                } else {
                    particle.edgeIdx = Math.floor(Math.random() * orbEdges.length);
                }
            }

            const edge = orbEdges[particle.edgeIdx];
            const p1 = orbNodes[edge.u].mesh.position;
            const p2 = orbNodes[edge.v].mesh.position;
            particle.mesh.position.lerpVectors(p1, p2, particle.progress);
        }

        // 5. Ambient gentle camera/group float
        orbGroup.rotation.y = Math.sin(clock * 0.3) * 0.05;
        orbGroup.rotation.x = Math.cos(clock * 0.25) * 0.035;

        // Aura gentle ripples
        const aura1Scale = 1.0 + Math.sin(clock * 1.6) * 0.025 + (smoothedAudioEnergy * 0.12);
        aura1Mesh.scale.set(aura1Scale, aura1Scale, 1);
        aura1Mat.opacity = isRecording ? (0.22 + smoothedAudioEnergy * 0.25) : 0.12;

        const aura2Scale = 1.0 + Math.cos(clock * 1.2) * 0.035 + (smoothedAudioEnergy * 0.18);
        aura2Mesh.scale.set(aura2Scale, aura2Scale, 1);
        aura2Mat.opacity = isRecording ? (0.16 + smoothedAudioEnergy * 0.2) : 0.07;

        orbRenderer.render(orbScene, orbCamera);
    }
    animateOrb();
}

// ── 4. Voice Recording & Discard Action ─────────────────────────────

function getSupportedMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac", "audio/wav"];
    for (const type of candidates) {
        if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) {
            return type;
        }
    }
    return "";
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = getSupportedMimeType();
        const options = mimeType ? { mimeType } : {};
        mediaRecorder = new MediaRecorder(stream, options);
        audioChunks = [];

        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const audioCtx = new AudioCtx();
            const source = audioCtx.createMediaStreamSource(stream);
            audioAnalyser = audioCtx.createAnalyser();
            audioAnalyser.fftSize = 64;
            audioDataArray = new Uint8Array(audioAnalyser.frequencyBinCount);
            source.connect(audioAnalyser);
        } catch (e) {
            console.warn("Audio analyser unavailable:", e);
        }

        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = () => {
            if (audioChunks.length > 0) {
                const recordedBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
                uploadAudio(recordedBlob);
            }
            stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start(250);
        isRecording = true;
        seconds = 0;
        timerEl.textContent = "00:00";
        timerEl.style.display = "inline-block";
        if (cancelRecordingBtn) cancelRecordingBtn.style.display = "inline-block";

        recordBtn.classList.add("recording");
        recordStatus.textContent = "Listening... tap to finish";

        recordTimer = setInterval(() => {
            seconds++;
            const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
            const secs = String(seconds % 60).padStart(2, "0");
            timerEl.textContent = mins + ":" + secs;
        }, 1000);

    } catch (err) {
        console.error("Microphone access error:", err);
        alert("Could not access microphone. Please grant permission or type a note below.");
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
    }
    clearInterval(recordTimer);
    recordTimer = null;
    isRecording = false;
    recordBtn.classList.remove("recording");
    recordStatus.textContent = "Processing voice note...";
    timerEl.style.display = "none";
    if (cancelRecordingBtn) cancelRecordingBtn.style.display = "none";
}

function discardRecording() {
    isRecording = false;
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.onstop = null;
        try { mediaRecorder.stop(); } catch (e) {}
    }
    if (mediaRecorder && mediaRecorder.stream) {
        mediaRecorder.stream.getTracks().forEach(t => t.stop());
    }
    clearInterval(recordTimer);
    recordTimer = null;
    seconds = 0;
    audioChunks = [];

    recordBtn.classList.remove("recording");
    recordStatus.textContent = "Recording discarded";
    timerEl.style.display = "none";
    if (cancelRecordingBtn) cancelRecordingBtn.style.display = "none";
    setTimeout(() => {
        if (!isRecording) recordStatus.textContent = "Tap to record a voice note";
    }, 2000);
}

if (recordBtn) {
    recordBtn.addEventListener("click", () => {
        if (!isRecording) startRecording();
        else stopRecording();
    });
}

if (cancelRecordingBtn) {
    cancelRecordingBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        discardRecording();
    });
}

// ── 5. Note Upload & Creation ───────────────────────────────────────

async function uploadAudio(blob) {
    processing.style.display = "flex";
    latestThought.style.display = "none";
    connectorInsights.style.display = "none";

    const ext = blob.type.includes("mp4") ? "mp4" : (blob.type.includes("wav") ? "wav" : "webm");
    const formData = new FormData();
    formData.append("audio", blob, "recording_" + Date.now() + "." + ext);
    formData.append("latitude", currentGeo.latitude);
    formData.append("longitude", currentGeo.longitude);
    formData.append("location_name", currentGeo.locationName);

    try {
        const res = await fetch("/api/thoughts", { method: "POST", body: formData });
        if (!res.ok) throw new Error("Upload failed");
        const thought = await res.json();
        showResult(thought);
    } catch (e) {
        console.error("Audio upload error:", e);
        recordStatus.textContent = "Error processing voice note.";
    } finally {
        processing.style.display = "none";
        if (!isRecording) recordStatus.textContent = "Tap to record a voice note";
    }
}

const textThoughtInput = document.getElementById("textThoughtInput");
const textThoughtSubmit = document.getElementById("textThoughtSubmit");

async function submitTextThought() {
    if (!textThoughtInput) return;
    const text = textThoughtInput.value.trim();
    if (!text) return;

    processing.style.display = "flex";
    latestThought.style.display = "none";
    connectorInsights.style.display = "none";
    textThoughtInput.value = "";

    try {
        const res = await fetch("/api/thoughts/text", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                text: text,
                latitude: currentGeo.latitude,
                longitude: currentGeo.longitude,
                location_name: currentGeo.locationName
            })
        });

        if (!res.ok) throw new Error("Failed to save text thought");
        const thought = await res.json();
        showResult(thought);
    } catch (e) {
        console.error("Text thought error:", e);
        alert("Failed to save note. Please try again.");
    } finally {
        processing.style.display = "none";
    }
}

if (textThoughtSubmit) {
    textThoughtSubmit.addEventListener("click", submitTextThought);
}
if (textThoughtInput) {
    textThoughtInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") submitTextThought();
    });
}

// ── 6. Show Saved Result Card & Poll Connections ────────────────────

function showResult(t) {
    latestThought.dataset.currentId = t.id;
    resultSummary.textContent = t.summary || "Note saved";
    resultMoodBadge.textContent = t.mood ? t.mood.charAt(0).toUpperCase() + t.mood.slice(1) : "Reflective";
    
    const dateStr = formatDate(t.created_at);
    const locStr = t.location_name || (t.latitude ? t.latitude.toFixed(2) + ", " + t.longitude.toFixed(2) : "Bay Area");
    resultTimeLocation.textContent = dateStr + " @ " + locStr;
    
    resultTranscript.textContent = t.transcript || "";

    resultTopics.innerHTML = "";
    (t.topics || []).forEach(top => {
        const span = document.createElement("span");
        span.className = "tag-chip";
        span.textContent = top;
        resultTopics.appendChild(span);
    });

    resultInsights.innerHTML = "";
    (t.key_insights || []).forEach(ins => {
        const li = document.createElement("li");
        li.textContent = ins;
        resultInsights.appendChild(li);
    });

    latestThought.style.display = "block";
    latestThought.scrollIntoView({ behavior: "smooth", block: "nearest" });

    pollConnections(t.id);
}

async function pollConnections(thoughtId) {
    let attempts = 0;
    const maxAttempts = 15;
    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await fetch("/api/thoughts/" + thoughtId + "/connections");
            if (res.ok) {
                const data = await res.json();
                if (data && data.status !== "none" && !data.error) {
                    clearInterval(interval);
                    renderConnectorInsights(data);
                }
            }
        } catch (e) {
            console.error("Poll connections error:", e);
        }
        if (attempts >= maxAttempts) clearInterval(interval);
    }, 2000);
}

function renderConnectorInsights(data) {
    if (!data) return;
    let html = "";
    if (data.proactive_insight) {
        html += "<div class=\"insight-callout\"><strong>Proactive Insight:</strong> " + escapeHtml(data.proactive_insight) + "</div>";
    }
    const connections = data.connections || [];
    if (connections.length > 0) {
        html += "<ul class=\"connections-list\">";
        connections.forEach(c => {
            html += "<li><span class=\"conn-tag conn-" + (c.connection_type || "evolves") + "\">" + escapeHtml(c.connection_type || "connects") + "</span> <span class=\"conn-expl\">\"" + escapeHtml(c.past_summary || "") + "\" — " + escapeHtml(c.explanation || "") + "</span></li>";
        });
        html += "</ul>";
    }
    if (html) {
        connectorContent.innerHTML = html;
        connectorInsights.style.display = "block";
    }
}

// ── 7. Deletion Actions ─────────────────────────────────────────────

async function deleteThoughtById(id, event) {
    if (event) event.stopPropagation();
    if (!confirm("Are you sure you want to delete this thought note?")) {
        return;
    }
    try {
        const res = await fetch("/api/thoughts/" + id, { method: "DELETE" });
        if (res.ok) {
            if (drawer && drawer.style.display !== "none" && drawer.dataset.currentId == id) {
                drawer.style.display = "none";
            }
            if (latestThought && latestThought.dataset.currentId == id) {
                latestThought.style.display = "none";
            }
            loadThoughts();
            if (document.getElementById("connectionsTab")?.classList.contains("active")) {
                if (!isMapMode) init3DGraph();
                else if (leafletMap) loadMapPoints();
            }
        } else {
            alert("Could not delete note. Please try again.");
        }
    } catch (e) {
        console.error("Delete thought error:", e);
        alert("Network error deleting note.");
    }
}

if (deleteLatestThoughtBtn) {
    deleteLatestThoughtBtn.addEventListener("click", () => {
        const id = latestThought.dataset.currentId;
        if (id) deleteThoughtById(id);
    });
}

if (drawerDeleteBtn) {
    drawerDeleteBtn.addEventListener("click", () => {
        const id = drawer.dataset.currentId;
        if (id) deleteThoughtById(id);
    });
}

// ── 8. Consolidated Connections (3D Graph + Map View) ───────────────

let graph3DScene, graph3DCamera, graph3DRenderer, graph3DGroup;
let graph3DAnimationId;
let graph3DNodeMeshes = [];
let isGraphDragging = false;
let prevMousePos = { x: 0, y: 0 };
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

async function init3DGraph() {
    const container = document.getElementById("neural3DGraph");
    if (!container || typeof THREE === "undefined") return;

    if (graph3DAnimationId) {
        cancelAnimationFrame(graph3DAnimationId);
        graph3DAnimationId = null;
    }
    if (graph3DRenderer) {
        try {
            graph3DRenderer.dispose();
            graph3DRenderer.forceContextLoss();
        } catch (e) {}
        graph3DRenderer = null;
    }
    container.innerHTML = "";

    const width = container.clientWidth || 1080;
    const height = container.clientHeight || 620;

    graph3DScene = new THREE.Scene();
    graph3DCamera = new THREE.PerspectiveCamera(45, width / height, 1, 3000);
    graph3DCamera.position.set(0, 0, 320);

    graph3DRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    graph3DRenderer.setSize(width, height);
    graph3DRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(graph3DRenderer.domElement);

    // Warm, Rich Studio Lighting
    const ambientLight = new THREE.AmbientLight(0xFBF9F5, 0.65);
    graph3DScene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xEAE6DC, 0.7);
    dirLight1.position.set(100, 100, 200);
    graph3DScene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xD8D7D0, 0.35);
    dirLight2.position.set(-100, -100, 150);
    graph3DScene.add(dirLight2);

    graph3DGroup = new THREE.Group();
    graph3DScene.add(graph3DGroup);
    graph3DNodeMeshes = [];

    try {
        const res = await fetch("/api/graph");
        const data = await res.json();
        if (!data || !data.nodes || data.nodes.length === 0) return;

        const themePillars = {
            "theme_tech": new THREE.Vector3(-90, 45, 20),
            "theme_work": new THREE.Vector3(90, 48, -25),
            "theme_family": new THREE.Vector3(-80, -60, -35),
            "theme_health": new THREE.Vector3(80, -55, 30),
            "theme_travel": new THREE.Vector3(0, 90, -45),
            "theme_philosophy": new THREE.Vector3(-85, -10, 75),
            "theme_habits": new THREE.Vector3(85, 0, 70)
        };

        data.nodes.forEach(n => {
            let pos;
            const isTheme = n.group === "theme";
            if (isTheme && themePillars[n.id]) {
                pos = themePillars[n.id].clone();
            } else {
                let basePos = new THREE.Vector3(0, 0, 0);
                const col = (n.color || "").toLowerCase();
                if (col.includes("2d5b88") || col.includes("1d4e4b")) basePos = themePillars["theme_tech"];
                else if (col.includes("b3732a") || col.includes("c78844")) basePos = themePillars["theme_work"];
                else if (col.includes("b8573d") || col.includes("c26d4d")) basePos = themePillars["theme_family"];
                else if (col.includes("1c7c75")) basePos = themePillars["theme_travel"];
                else if (col.includes("7b4b88")) basePos = themePillars["theme_philosophy"];
                else if (col.includes("a84a6e")) basePos = themePillars["theme_habits"];
                else basePos = themePillars["theme_health"];

                const u = Math.random();
                const v = Math.random();
                const theta = u * 2.0 * Math.PI;
                const phi = Math.acos(2.0 * v - 1.0);
                const r = isTheme ? 75 : (32 + Math.random() * 52);

                const sinPhi = Math.sin(phi);
                pos = new THREE.Vector3(
                    basePos.x + r * sinPhi * Math.cos(theta),
                    basePos.y + r * sinPhi * Math.sin(theta),
                    basePos.z + r * Math.cos(phi)
                );
            }

            const size = isTheme ? 9.5 : 4.5;
            let colHex = 0x1D4E4B;
            if (n.color) {
                colHex = parseInt(n.color.replace("#", "0x"), 16);
            }

            const sphereGeo = new THREE.SphereGeometry(size, 24, 24);
            const sphereMat = new THREE.MeshStandardMaterial({
                color: colHex,
                roughness: 0.8,
                metalness: 0.0
            });
            const mesh = new THREE.Mesh(sphereGeo, sphereMat);
            mesh.position.copy(pos);
            mesh.userData = n;

            if (isTheme) {
                const ringGeo = new THREE.RingGeometry(size * 1.3, size * 1.6, 32);
                const ringMat = new THREE.MeshBasicMaterial({
                    color: 0xD4D3CB,
                    side: THREE.DoubleSide,
                    transparent: true,
                    opacity: 0.8
                });
                const ring = new THREE.Mesh(ringGeo, ringMat);
                ring.rotation.x = Math.PI / 2;
                mesh.add(ring);
            }

            graph3DGroup.add(mesh);
            graph3DNodeMeshes.push(mesh);
        });

        // Add connecting links
        if (data.edges && data.edges.length > 0) {
            const edgePositions = [];
            const nodeMap = new Map(graph3DNodeMeshes.map(m => [m.userData.id, m.position]));
            data.edges.forEach(e => {
                const p1 = nodeMap.get(e.from);
                const p2 = nodeMap.get(e.to);
                if (p1 && p2) {
                    edgePositions.push(p1.x, p1.y, p1.z, p2.x, p2.y, p2.z);
                }
            });
            const edgeGeo = new THREE.BufferGeometry();
            edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
            const edgeMat = new THREE.LineBasicMaterial({
                color: 0xD4D3CB,
                transparent: true,
                opacity: 0.5
            });
            const edgesMesh = new THREE.LineSegments(edgeGeo, edgeMat);
            graph3DGroup.add(edgesMesh);
        }

    } catch (e) {
        console.error("3D graph error:", e);
    }

    container.onmousedown = (e) => {
        isGraphDragging = true;
        prevMousePos = { x: e.clientX, y: e.clientY };
    };

    window.addEventListener("mouseup", () => isGraphDragging = false);

    container.onmousemove = (e) => {
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

    function animateGraph() {
        graph3DAnimationId = requestAnimationFrame(animateGraph);
        if (!isGraphDragging && graph3DGroup) {
            graph3DGroup.rotation.y += 0.0008;
        }
        graph3DRenderer.render(graph3DScene, graph3DCamera);
    }
    animateGraph();
}

document.getElementById("resetGraphBtn")?.addEventListener("click", () => {
    if (graph3DGroup && graph3DCamera) {
        graph3DGroup.rotation.set(0, 0, 0);
        graph3DCamera.position.set(0, 0, 320);
    }
});

// Map / Graph Toggle Controller
const mapGraphToggleBtn = document.getElementById("mapGraphToggleBtn");
const mapGraphToggleLabel = document.getElementById("mapGraphToggleLabel");
const connectionsHintText = document.getElementById("connectionsHintText");
const neural3DGraphEl = document.getElementById("neural3DGraph");
const thoughtMapEl = document.getElementById("thoughtMap");

if (mapGraphToggleBtn) {
    mapGraphToggleBtn.addEventListener("click", () => {
        isMapMode = !isMapMode;
        if (isMapMode) {
            if (neural3DGraphEl) neural3DGraphEl.style.display = "none";
            if (thoughtMapEl) {
                thoughtMapEl.style.display = "block";
                if (!leafletMap) {
                    initMap();
                } else {
                    setTimeout(() => {
                        leafletMap.invalidateSize();
                        loadMapPoints();
                    }, 100);
                }
            }
            if (mapGraphToggleLabel) mapGraphToggleLabel.textContent = "Switch to 3D Graph";
            const iconMap = mapGraphToggleBtn.querySelector(".icon-map");
            const iconGraph = mapGraphToggleBtn.querySelector(".icon-graph");
            if (iconMap) iconMap.style.display = "none";
            if (iconGraph) iconGraph.style.display = "inline";
            if (connectionsHintText) connectionsHintText.textContent = "Click pins to view thought notes & walk paths";
        } else {
            if (thoughtMapEl) thoughtMapEl.style.display = "none";
            if (neural3DGraphEl) {
                neural3DGraphEl.style.display = "block";
                init3DGraph();
            }
            if (mapGraphToggleLabel) mapGraphToggleLabel.textContent = "View on Map";
            const iconMap = mapGraphToggleBtn.querySelector(".icon-map");
            const iconGraph = mapGraphToggleBtn.querySelector(".icon-graph");
            if (iconMap) iconMap.style.display = "inline";
            if (iconGraph) iconGraph.style.display = "none";
            if (connectionsHintText) connectionsHintText.textContent = "Click & drag to rotate · Scroll to zoom · Click node to inspect";
        }
    });
}

// ── 9. Leaflet Map Initialization ───────────────────────────────────

function initMap() {
    const mapEl = document.getElementById("thoughtMap");
    if (!mapEl || typeof L === "undefined") return;

    leafletMap = L.map("thoughtMap", { zoomControl: false }).setView([37.4419, -122.1430], 11);
    L.control.zoom({ position: "topright" }).addTo(leafletMap);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
        attribution: "© OpenStreetMap © CARTO",
        maxZoom: 19
    }).addTo(leafletMap);

    loadMapPoints();
}

async function loadMapPoints() {
    if (!leafletMap) return;

    mapMarkers.forEach(m => leafletMap.removeLayer(m));
    mapMarkers = [];
    mapPolylines.forEach(p => leafletMap.removeLayer(p));
    mapPolylines = [];

    try {
        const res = await fetch("/api/map/points");
        const points = await res.json();
        if (!points || points.length === 0) return;

        const bounds = [];
        const sortedPoints = [...points].sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));

        // Walk Route Lines
        const latlngs = sortedPoints.map(p => [p.latitude, p.longitude]);
        if (latlngs.length > 1) {
            const polyline = L.polyline(latlngs, {
                color: "#1D4E4B",
                weight: 3,
                opacity: 0.65,
                dashArray: "6, 8"
            }).addTo(leafletMap);
            mapPolylines.push(polyline);
        }

        // Add Markers
        sortedPoints.forEach(p => {
            const color = p.color || "#1D4E4B";
            const customIcon = L.divIcon({
                className: "custom-map-pin",
                html: "<div style=\"background-color: " + color + "; width: 14px; height: 14px; border-radius: 50%; border: 2.5px solid #FFFFFF; box-shadow: 0 2px 6px rgba(0,0,0,0.3);\"></div>",
                iconSize: [14, 14],
                iconAnchor: [7, 7]
            });

            const marker = L.marker([p.latitude, p.longitude], { icon: customIcon }).addTo(leafletMap);
            bounds.push([p.latitude, p.longitude]);

            const dateStr = formatDate(p.created_at);
            marker.bindPopup(
                "<div style=\"font-family: 'General Sans', sans-serif; min-width: 180px; padding: 4px;\">" +
                    "<div style=\"font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #787B82;\">" + dateStr + " @ " + escapeHtml(p.location_name || "Walk") + "</div>" +
                    "<div style=\"font-family: 'Newsreader', serif; font-size: 16px; font-weight: 500; margin: 4px 0 6px; color: #14161A;\">" + escapeHtml(p.summary || "") + "</div>" +
                    "<button onclick=\"openThoughtInspectorById(" + p.id + ")\" style=\"background: #1D4E4B; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; font-size: 12px; cursor: pointer; font-family: 'General Sans', sans-serif;\">View Note Details</button>" +
                "</div>"
            );

            mapMarkers.push(marker);
        });

        if (bounds.length > 0) {
            leafletMap.fitBounds(bounds, { padding: [40, 40] });
        }

    } catch (e) {
        console.error("Map points error:", e);
    }
}

// ── 10. Timeline & Pattern Synthesis ────────────────────────────────

async function loadThoughts(searchQuery) {
    if (!thoughtsList) return;
    thoughtsList.innerHTML = "<div class=\"empty-state\">Loading notes...</div>";

    try {
        let thoughts = [];
        if (searchQuery) {
            const res = await fetch("/api/search?q=" + encodeURIComponent(searchQuery));
            thoughts = await res.json();
        } else {
            const res = await fetch("/api/thoughts");
            thoughts = await res.json();
        }

        const countBadge = document.getElementById("timelineCountBadge");
        if (countBadge) {
            countBadge.textContent = thoughts.length + " " + (thoughts.length === 1 ? "note" : "notes");
        }

        if (!thoughts || thoughts.length === 0) {
            thoughtsList.innerHTML = "<div class=\"empty-state\">No thoughts recorded yet. Record your first thought!</div>";
            return;
        }

        thoughtsList.innerHTML = "";
        thoughts.forEach(t => {
            const card = document.createElement("div");
            const typeClass = "type-" + (t.thought_type || "reflection").toLowerCase();
            card.className = "thought-card " + typeClass;
            card.dataset.id = t.id;

            const dateStr = formatDate(t.created_at);
            const locStr = t.location_name || "Bay Area";

            let topicsHtml = "";
            (t.topics || []).slice(0, 3).forEach(top => {
                topicsHtml += "<span class=\"tag-chip\">" + escapeHtml(top) + "</span>";
            });

            card.innerHTML = 
                "<div class=\"thought-card-top\">" +
                    "<div class=\"thought-date-loc\">" +
                        "<span>📅 " + escapeHtml(dateStr) + "</span>" +
                        "<span>📍 " + escapeHtml(locStr) + "</span>" +
                    "</div>" +
                    "<div class=\"thought-card-actions\">" +
                        "<span class=\"badge badge-light\">" + escapeHtml(t.thought_type || "note") + "</span>" +
                        "<button class=\"card-trash-btn\" title=\"Delete note\" type=\"button\" aria-label=\"Delete note\">" +
                            "<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><polyline points=\"3 6 5 6 21 6\"/><path d=\"M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2\"/></svg>" +
                        "</button>" +
                    "</div>" +
                "</div>" +
                "<div class=\"thought-summary-title\">" + escapeHtml(t.summary || t.transcript || "Recorded Thought") + "</div>" +
                "<div class=\"thought-card-topics\">" + topicsHtml + "</div>";

            card.addEventListener("click", () => openThoughtInspector(t));
            const trashBtn = card.querySelector(".card-trash-btn");
            if (trashBtn) {
                trashBtn.addEventListener("click", (e) => deleteThoughtById(t.id, e));
            }

            thoughtsList.appendChild(card);
        });
    } catch (e) {
        console.error("Load thoughts error:", e);
        thoughtsList.innerHTML = "<div class=\"empty-state\">Error loading notes.</div>";
    }
}

if (searchBtn && searchInput) {
    searchBtn.addEventListener("click", () => loadThoughts(searchInput.value.trim()));
    searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") loadThoughts(searchInput.value.trim());
    });
}

// Pattern Synthesis Timeframe Handlers
document.querySelectorAll(".timeframe-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        document.querySelectorAll(".timeframe-chip").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        const days = parseInt(chip.dataset.days);
        const customVal = document.getElementById("patternCustomVal");
        const customUnit = document.getElementById("patternCustomUnit");
        if (days === 7 && customVal && customUnit) { customVal.value = 7; customUnit.value = "days"; }
        else if (days === 35 && customVal && customUnit) { customVal.value = 5; customUnit.value = "weeks"; }
        else if (days === 90 && customVal && customUnit) { customVal.value = 3; customUnit.value = "months"; }
        else if (days === 365 && customVal && customUnit) { customVal.value = 1; customUnit.value = "years"; }
    });
});

const generatePatternsBtn = document.getElementById("generatePatternsBtn");
if (generatePatternsBtn) {
    generatePatternsBtn.addEventListener("click", async () => {
        const resultContainer = document.getElementById("patternsResult");
        const loadingEl = resultContainer?.querySelector(".patterns-loading-indicator");
        const contentArea = document.getElementById("patternsContentArea");
        if (!resultContainer || !contentArea) return;

        resultContainer.style.display = "block";
        if (loadingEl) loadingEl.style.display = "flex";
        contentArea.innerHTML = "";

        let days = 35;
        let timeframeLabel = "Last 5 Weeks";
        const activeChip = document.querySelector(".timeframe-chip.active");
        const customVal = parseInt(document.getElementById("patternCustomVal")?.value || "5");
        const customUnit = document.getElementById("patternCustomUnit")?.value || "weeks";

        if (activeChip && activeChip.dataset.days !== undefined) {
            const rawDays = parseInt(activeChip.dataset.days);
            if (rawDays === 0) {
                days = null;
                timeframeLabel = "All Time";
            } else {
                days = rawDays;
                timeframeLabel = activeChip.textContent.trim();
            }
        } else {
            if (customUnit === "days") days = customVal;
            else if (customUnit === "weeks") days = customVal * 7;
            else if (customUnit === "months") days = customVal * 30;
            else if (customUnit === "years") days = customVal * 365;
            timeframeLabel = "Last " + customVal + " " + customUnit;
        }

        try {
            const url = days 
                ? "/api/patterns?days=" + days + "&timeframe_label=" + encodeURIComponent(timeframeLabel) + "&force=true"
                : "/api/patterns?timeframe_label=" + encodeURIComponent(timeframeLabel) + "&force=true";
            const res = await fetch(url);
            const data = await res.json();
            if (loadingEl) loadingEl.style.display = "none";

            if (data.error) {
                contentArea.innerHTML = "<div class=\"empty-state\">" + escapeHtml(data.error) + "</div>";
                return;
            }

            renderPatternReport(data, contentArea, timeframeLabel);
        } catch (e) {
            console.error("Pattern analysis error:", e);
            if (loadingEl) loadingEl.style.display = "none";
            contentArea.innerHTML = "<div class=\"empty-state\">Error analyzing patterns. Please try again.</div>";
        }
    });
}

function renderPatternReport(data, container, label) {
    const summary = data.one_line_summary || "Multi-week thinking patterns and growth trajectory.";
    const count = data.analyzed_thought_count || 0;
    const mood = data.mood_trajectory || {};
    const themes = data.recurring_themes || [];
    const recommendations = data.recommendations || [];

    let themesHtml = "";
    themes.forEach(th => {
        themesHtml += 
            "<div class=\"theme-summary-card\">" +
                "<div class=\"theme-card-top\">" +
                    "<span class=\"theme-name\">" + escapeHtml(th.theme || th.name || "") + "</span>" +
                    "<span class=\"theme-trend-badge\">" + escapeHtml(th.trend || (th.frequency ? th.frequency + "x" : "active")) + "</span>" +
                "</div>" +
                "<div class=\"theme-desc\">" + escapeHtml(th.description || "") + "</div>" +
            "</div>";
    });

    let recsHtml = "";
    recommendations.forEach(r => {
        recsHtml += "<li>" + escapeHtml(r) + "</li>";
    });

    let html = 
        "<div class=\"pattern-report-view\">" +
            "<div class=\"pattern-hero-quote\">\"" + escapeHtml(summary) + "\"</div>" +
            "<div class=\"pattern-meta-banner\">" +
                "<span><strong>Window:</strong> " + escapeHtml(label || "Selected Timeframe") + "</span>" +
                "<span><strong>Analyzed Notes:</strong> " + count + "</span>" +
                "<span><strong>Trajectory:</strong> " + escapeHtml(mood.trend || "evolving") + "</span>" +
            "</div>";

    if (themesHtml) {
        html += 
            "<div>" +
                "<label class=\"section-label\" style=\"display:block; margin-bottom:10px;\">Recurring Themes & Growth</label>" +
                "<div class=\"themes-grid-cards\">" + themesHtml + "</div>" +
            "</div>";
    }

    if (recommendations.length) {
        html += 
            "<div class=\"card\" style=\"padding:20px 24px; background:#FFFFFF;\">" +
                "<label class=\"section-label\" style=\"display:block; margin-bottom:10px;\">Proactive Recommendations</label>" +
                "<ul class=\"bullet-list\">" + recsHtml + "</ul>" +
            "</div>";
    }

    html += "</div>";
    container.innerHTML = html;
}

// ── 11. Elevated Ask Chat Pipeline ──────────────────────────────────

function bindPromptChips() {
    document.querySelectorAll(".prompt-card, .prompt-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            const prompt = chip.dataset.prompt;
            if (prompt && chatInput) {
                chatInput.value = prompt;
                handleChatSubmit();
            }
        });
    });
}

bindPromptChips();

if (newChatBtn) {
    newChatBtn.addEventListener("click", () => {
        currentConversationId = "conv_" + Date.now();
        chatHistory = [];
        chatMessages.innerHTML = 
            "<div class=\"chat-bubble assistant\">" +
                "<div class=\"bubble-avatar\">" +
                    "<svg width=\"18\" height=\"18\" viewBox=\"0 0 96 96\" fill=\"none\">" +
                        "<g stroke=\"var(--petrol)\" stroke-width=\"6\">" +
                            "<ellipse cx=\"48\" cy=\"80\" rx=\"30\" ry=\"8\"/>" +
                            "<ellipse cx=\"48\" cy=\"60\" rx=\"23\" ry=\"7.5\"/>" +
                            "<ellipse cx=\"48\" cy=\"42\" rx=\"16\" ry=\"7\"/>" +
                        "</g>" +
                        "<circle cx=\"48\" cy=\"22\" r=\"7\" fill=\"var(--color-amber)\"/>" +
                    "</svg>" +
                "</div>" +
                "<div class=\"bubble-body\">" +
                    "<div class=\"bubble-summary\">Hi! Ask me anything about your past notes, walks, or ideas. What are you thinking through today?</div>" +
                    "<div class=\"prompt-grid-chips\">" +
                        "<button class=\"prompt-card\" type=\"button\" data-prompt=\"What have I noted about hydration and health?\">" +
                            "<span class=\"prompt-title\">Hydration habits</span>" +
                            "<span class=\"prompt-desc\">Past reflections on drinking water & wellness</span>" +
                        "</button>" +
                        "<button class=\"prompt-card\" type=\"button\" data-prompt=\"What were my ideas about AI agents and memory?\">" +
                            "<span class=\"prompt-title\">AI agent architectures</span>" +
                            "<span class=\"prompt-desc\">Long-horizon memory & edge intelligence</span>" +
                        "</button>" +
                        "<button class=\"prompt-card\" type=\"button\" data-prompt=\"What did I plan for my parents' anniversary?\">" +
                            "<span class=\"prompt-title\">Parents' anniversary</span>" +
                            "<span class=\"prompt-desc\">Itinerary, Carmel reservations & gift ideas</span>" +
                        "</button>" +
                        "<button class=\"prompt-card\" type=\"button\" data-prompt=\"What notes did I record during my recent walks?\">" +
                            "<span class=\"prompt-title\">Recent walk notes</span>" +
                            "<span class=\"prompt-desc\">Thoughts from Stanford Dish, Shoreline & Cupertino</span>" +
                        "</button>" +
                    "</div>" +
                "</div>" +
            "</div>";
        bindPromptChips();
        chatInput.value = "";
        chatInput.focus();
    });
}

async function handleChatSubmit() {
    if (!chatInput) return;
    const msg = chatInput.value.trim();
    if (!msg) return;

    appendChatBubble("user", msg);
    chatInput.value = "";

    const assistantBubble = appendChatBubble("assistant", "");
    const body = assistantBubble.querySelector(".bubble-body");
    body.innerHTML = 
        "<div style=\"display:flex; align-items:center; gap:8px; color:var(--text-muted); font-size:14px;\">" +
            "<div class=\"loading-spinner\" style=\"width:16px; height:16px; border-width:2px;\"></div>" +
            "<span>Searching your stash and connecting thoughts...</span>" +
        "</div>";

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                conversation_id: currentConversationId,
                message: msg,
                history: chatHistory
            })
        });

        if (!res.ok) throw new Error("Chat request failed");
        const data = await res.json();
        renderAssistantResponse(body, data);

        chatHistory.push({ role: "user", content: msg });
        chatHistory.push({ role: "model", content: data.response || data.summary || "" });

    } catch (e) {
        console.error("Chat error:", e);
        body.innerHTML = "<div style=\"color:var(--color-terracotta);\">Sorry, I encountered an error searching your notes. Please try again.</div>";
    }
}

function renderAssistantResponse(body, data) {
    let html = "";
    if (data.summary) {
        html += "<div class=\"bubble-summary\">" + escapeHtml(data.summary) + "</div>";
    }

    if (data.key_points && data.key_points.length > 0) {
        html += "<ul class=\"bubble-points-list\">";
        data.key_points.forEach(kp => {
            html += "<li>" + escapeHtml(kp) + "</li>";
        });
        html += "</ul>";
    }

    if (data.suggested_action) {
        html += 
            "<div class=\"suggested-action-box\">" +
                "<span><strong>Takeaway:</strong> " + escapeHtml(data.suggested_action) + "</span>" +
            "</div>";
    }

    if (data.context_layer_applied && data.matched_thought_count) {
        const noteCount = data.matched_thought_count;
        const noteLabel = noteCount === 1 ? "1 note" : noteCount + " notes";
        const searchBadge = data.web_search_used ? " + Google Search" : "";
        html += 
            "<div class=\"provenance-chip\">" +
                "<span>Grounded in " + noteLabel + searchBadge + "</span>" +
            "</div>";
    }

    body.innerHTML = html;
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function appendChatBubble(role, text) {
    const div = document.createElement("div");
    div.className = "chat-bubble " + role;
    const iconSvg = role === "user" ? 
        "<svg width=\"14\" height=\"14\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\"><path d=\"M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2\"/><circle cx=\"12\" cy=\"7\" r=\"4\"/></svg>" :
        "<svg width=\"18\" height=\"18\" viewBox=\"0 0 96 96\" fill=\"none\"><g stroke=\"var(--petrol)\" stroke-width=\"6\"><ellipse cx=\"48\" cy=\"80\" rx=\"30\" ry=\"8\"/><ellipse cx=\"48\" cy=\"60\" rx=\"23\" ry=\"7.5\"/><ellipse cx=\"48\" cy=\"42\" rx=\"16\" ry=\"7\"/></g><circle cx=\"48\" cy=\"22\" r=\"7\" fill=\"var(--color-amber)\"/></svg>";

    const bodyContent = text ? "<p>" + escapeHtml(text) + "</p>" : "";
    div.innerHTML = 
        "<div class=\"bubble-avatar\">" + iconSvg + "</div>" +
        "<div class=\"bubble-body\">" + bodyContent + "</div>";
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return div;
}

if (chatSendBtn) {
    chatSendBtn.addEventListener("click", handleChatSubmit);
}
if (chatInput) {
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") handleChatSubmit();
    });
}

// ── 12. Slide-In Detail Drawer ──────────────────────────────────────

function openThoughtInspector(t) {
    if (!t) return;
    drawer.dataset.currentId = t.id;

    const titleEl = document.getElementById("inspectorTitle");
    const transcriptEl = document.getElementById("inspectorTranscript");
    const dateEl = document.getElementById("inspectorDate");
    const locEl = document.getElementById("inspectorLocation");
    const topicsEl = document.getElementById("inspectorTopics");
    const insightsEl = document.getElementById("inspectorInsightsList");
    const categoryBadgeText = document.getElementById("inspectorCategoryText");

    if (titleEl) titleEl.textContent = t.summary || "Recorded Thought";
    if (transcriptEl) transcriptEl.textContent = t.transcript || "No audio transcript available.";
    if (dateEl) dateEl.textContent = formatDate(t.created_at);
    if (locEl) locEl.textContent = t.location_name || "Bay Area";
    if (categoryBadgeText) categoryBadgeText.textContent = t.thought_type || "Thought";

    if (topicsEl) {
        topicsEl.innerHTML = "";
        (t.topics || []).forEach(top => {
            const span = document.createElement("span");
            span.className = "tag-chip";
            span.textContent = top;
            topicsEl.appendChild(span);
        });
    }

    if (insightsEl) {
        insightsEl.innerHTML = "";
        const insights = t.key_insights || [];
        if (insights.length > 0) {
            insights.forEach(ins => {
                const li = document.createElement("li");
                li.textContent = ins;
                insightsEl.appendChild(li);
            });
            document.getElementById("inspectorInsightsSection").style.display = "block";
        } else {
            document.getElementById("inspectorInsightsSection").style.display = "none";
        }
    }

    drawer.style.display = "flex";
}

async function openThoughtInspectorById(id) {
    try {
        const res = await fetch("/api/thoughts/" + id);
        if (res.ok) {
            const thought = await res.json();
            openThoughtInspector(thought);
        }
    } catch (e) {
        console.error("Open inspector error:", e);
    }
}

// Global window function for map popup click
window.openThoughtInspectorById = openThoughtInspectorById;

if (closeDrawerBtn) {
    closeDrawerBtn.addEventListener("click", () => drawer.style.display = "none");
}
if (drawer) {
    drawer.addEventListener("click", (e) => {
        if (e.target === drawer) drawer.style.display = "none";
    });
}

// ── 13. Utilities ───────────────────────────────────────────────────

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// Initialize on DOM Ready
window.addEventListener("DOMContentLoaded", () => {
    initGeolocation();
    init3DAudioOrb();
    loadThoughts();
});
