// --- DOM Selectors ---
const output = document.getElementById('transcriptionOutput');
const downloadBtn = document.getElementById('downloadBtn');
const progressContainer = document.getElementById('progressContainer');
const progressBar = document.getElementById('progressBar');
const progressText = document.getElementById('progressText');
const progressPercent = document.getElementById('progressPercent');
const cancelJobBtn = document.getElementById('cancelJobBtn');

// Navigation & Layout
const sidebar = document.getElementById('sidebar');
const openSidebarBtn = document.getElementById('openSidebarBtn');
const closeSidebarBtn = document.getElementById('closeSidebarBtn');
const sidebarOverlay = document.getElementById('sidebarOverlay');
const navNewBtn = document.getElementById('navNewBtn');
const historyList = document.getElementById('historyList');
const newSessionSection = document.getElementById('newSessionSection');
const resultsSection = document.getElementById('resultsSection');
const exportControls = document.getElementById('exportControls');
const downloadSrtBtn = document.getElementById('downloadSrtBtn');
const downloadJsonBtn = document.getElementById('downloadJsonBtn');
const resultSubtitle = document.getElementById('resultSubtitle');

// Form & Upload
const fileUploadForm = document.getElementById('fileUploadForm');
const audioFileInput = document.getElementById('audioFileInput');
const processBtn = document.getElementById('processBtn');
const customFilenameInput = document.getElementById('customFilename');
const languageSelect = document.getElementById('languageSelect');
const initialPromptInput = document.getElementById('initialPrompt');
const fileInfo = document.getElementById('fileInfo');
const fileNameDisplay = document.getElementById('fileName');
const totalDurationDisplay = document.getElementById('totalDurationDisplay');

// Waveform UI
const waveformUI = document.getElementById('waveformUI');
const startTimeInput = document.getElementById('startTimeInput');
const endTimeInput = document.getElementById('endTimeInput');
const playFullBtn = document.getElementById('playFullBtn');
const playIcon = document.getElementById('playIcon');
const pauseIcon = document.getElementById('pauseIcon');

// Mic UI
const startRecordBtn = document.getElementById('startRecordBtn');
const stopRecordBtn = document.getElementById('stopRecordBtn');
const retakeBtn = document.getElementById('retakeBtn');
const micStatus = document.getElementById('micStatus');
const liveWaveformCanvas = document.getElementById('liveWaveformCanvas');
const micTitleInput = document.getElementById('micTitle');

// Theme
const themeToggleBtn = document.getElementById('themeToggleBtn');
const themeIconLight = document.getElementById('theme-icon-light');
const themeIconDark = document.getElementById('theme-icon-dark');

// --- Global State ---
let wavesurfer;
let wsRegions;
let currentRegion;
let mediaRecorder;
let micStream;
let audioChunks = [];
let audioContext, analyser, source, animationFrameId;
let pollInterval;
let currentJobId = null;

// --- 1. Helper Functions ---
function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function parseTime(timeString) {
    if (!timeString) return 0;
    const parts = timeString.split(':');
    if (parts.length === 2) {
        return (parseInt(parts[0], 10) * 60) + parseFloat(parts[1]);
    }
    return parseFloat(timeString);
}

// --- 2. UI Transitions & Sidebar ---
function showSection(sectionId) {
    [newSessionSection, resultsSection].forEach(s => s.classList.add('hidden'));
    document.getElementById(sectionId).classList.remove('hidden');
    if (window.innerWidth < 1024) sidebar.classList.add('-translate-x-full');
}

openSidebarBtn.addEventListener('click', () => {
    sidebar.classList.remove('-translate-x-full');
    sidebarOverlay.classList.remove('hidden');
    // slight delay for transition
    setTimeout(() => sidebarOverlay.classList.remove('opacity-0'), 10);
});
closeSidebarBtn.addEventListener('click', () => {
    sidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('opacity-0');
    setTimeout(() => sidebarOverlay.classList.add('hidden'), 300); // match transition duration
});
sidebarOverlay.addEventListener('click', () => {
    sidebar.classList.add('-translate-x-full');
    sidebarOverlay.classList.add('opacity-0');
    setTimeout(() => sidebarOverlay.classList.add('hidden'), 300);
});
navNewBtn.addEventListener('click', () => showSection('newSessionSection'));

async function loadHistory() {
    try {
        const res = await fetch('/history');
        const data = await res.json();
        historyList.innerHTML = data.length ? '' : '<div class="px-4 py-8 text-center text-slate-400 text-sm">No recent activity</div>';

        data.forEach(job => {
            const item = document.createElement('button');
            item.className = 'w-full text-left px-4 py-3 rounded-xl history-item group transition-all animate-fade-in';
            const date = new Date(job.created_at).toLocaleDateString();
            item.innerHTML = `
                <div class="flex flex-col">
                    <span class="text-sm font-semibold truncate text-slate-700 dark:text-slate-300 group-hover:text-primary-600 transition-colors">${job.custom_name || job.filename}</span>
                    <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">${date} • ${job.status}</span>
                </div>
            `;
            item.onclick = () => showJobResult(job);
            historyList.appendChild(item);
        });
    } catch (e) {
        console.error("History load failed", e);
    }
}

function showJobResult(job) {
    showSection('resultsSection');
    output.textContent = job.result_text || 'No transcription text available.';
    resultSubtitle.textContent = job.custom_name || job.filename;

    if (job.status === 'completed' && job.result_text) {
        exportControls.classList.remove('hidden');
        downloadBtn.href = job.download_url || `/download_transcription/${job.filename}.txt`;
        downloadSrtBtn.href = `/download_export/${job.id}/srt`;
        downloadJsonBtn.href = `/download_export/${job.id}/json`;
    } else {
        exportControls.classList.add('hidden');
    }

    if (job.status === 'processing' || job.status === 'queued') {
        progressContainer.classList.remove('hidden');
        pollJob(job.id);
    } else {
        progressContainer.classList.add('hidden');
    }
}

// --- 3. Theme Logic ---
function updateThemeIcons(theme) {
    if (theme === 'dark') {
        themeIconLight.classList.remove('hidden');
        themeIconDark.classList.add('hidden');
    } else {
        themeIconLight.classList.add('hidden');
        themeIconDark.classList.remove('hidden');
    }
}
themeToggleBtn.addEventListener('click', () => {
    document.documentElement.classList.toggle('dark');
    const isDark = document.documentElement.classList.contains('dark');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    updateThemeIcons(isDark ? 'dark' : 'light');
});
updateThemeIcons(document.documentElement.classList.contains('dark') ? 'dark' : 'light');

// --- 4. WaveSurfer Logic ---
audioFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (wavesurfer) wavesurfer.destroy();

    fileInfo.classList.remove('hidden');
    waveformUI.classList.remove('hidden');
    fileNameDisplay.textContent = file.name;

    wavesurfer = WaveSurfer.create({
        container: '#waveform',
        waveColor: '#6366f133',
        progressColor: '#6366f1',
        cursorColor: '#6366f1',
        barWidth: 3,
        barRadius: 4,
        height: 120,
        url: URL.createObjectURL(file),
    });

    wsRegions = wavesurfer.registerPlugin(WaveSurfer.Regions.create());

    wavesurfer.on('decode', () => {
        const duration = wavesurfer.getDuration();
        totalDurationDisplay.textContent = formatTime(duration);
        wsRegions.clearRegions();
        currentRegion = wsRegions.addRegion({
            start: 0,
            end: duration,
            color: 'rgba(99, 102, 241, 0.15)',
            drag: true,
            resize: true
        });
        startTimeInput.value = formatTime(0);
        endTimeInput.value = formatTime(duration);
    });

    wsRegions.on('region-updated', (region) => {
        currentRegion = region;
        startTimeInput.value = formatTime(region.start);
        endTimeInput.value = formatTime(region.end);
    });
});

playFullBtn.addEventListener('click', () => {
    if (wavesurfer) {
        wavesurfer.playPause();
        const isPlaying = wavesurfer.isPlaying();
        playIcon.classList.toggle('hidden', isPlaying);
        pauseIcon.classList.toggle('hidden', !isPlaying);
    }
});

if (wavesurfer) {
    wavesurfer.on('finish', () => {
        playIcon.classList.remove('hidden');
        pauseIcon.classList.add('hidden');
    });
}

// --- 5. Processing & Polling ---
function updateProgress(percent, text) {
    progressBar.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;
    if (text) progressText.textContent = text;
}

async function pollJob(jobId) {
    currentJobId = jobId;
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/job_status/${jobId}`);
            const data = await res.json();

            if (data.status === 'failed' || data.status === 'cancelled') {
                clearInterval(pollInterval);
                output.textContent = data.message || "Job failed or cancelled";
                progressContainer.classList.add('hidden');
                loadHistory();
                return;
            }

            updateProgress(data.progress, data.message);

            if (data.status === 'completed') {
                clearInterval(pollInterval);
                updateProgress(100, "Success");
                setTimeout(() => {
                    output.textContent = data.result.transcript;
                    exportControls.classList.remove('hidden');
                    downloadBtn.href = data.result.download_url;
                    downloadSrtBtn.href = `/download_export/${jobId}/srt`;
                    downloadJsonBtn.href = `/download_export/${jobId}/json`;
                    progressContainer.classList.add('hidden');
                    resultSubtitle.textContent = data.custom_name || data.filename;
                    loadHistory();
                }, 500);
            }
        } catch (e) { console.error(e); }
    }, 1500);
}

fileUploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!audioFileInput.files[0]) return;

    showSection('resultsSection');
    progressContainer.classList.remove('hidden');
    updateProgress(0, "Preparing...");

    const formData = new FormData();
    formData.append('audio_file', audioFileInput.files[0]);
    if (customFilenameInput.value) formData.append('custom_filename', customFilenameInput.value);
    if (languageSelect.value) formData.append('language', languageSelect.value);
    if (initialPromptInput.value) formData.append('initial_prompt', initialPromptInput.value);

    if (currentRegion) {
        formData.append('startTime', currentRegion.start.toFixed(2));
        formData.append('endTime', currentRegion.end.toFixed(2));
    }

    try {
        const res = await fetch('/start_upload_job', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.job_id) pollJob(data.job_id);
    } catch (err) {
        console.error(err);
        output.textContent = "Error starting job.";
    }
});

cancelJobBtn.addEventListener('click', async () => {
    if (currentJobId) {
        await fetch(`/cancel_job/${currentJobId}`, { method: 'POST' });
        clearInterval(pollInterval);
        progressContainer.classList.add('hidden');
        output.textContent = "Current session cancelled.";
        loadHistory();
    }
});

// --- 6. Microphone Logic (Simplified for brevity, same core logic) ---
startRecordBtn.addEventListener('click', async () => {
    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(micStream);
        audioChunks = [];
        liveWaveformCanvas.classList.remove('hidden');
        setupLiveWaveform(micStream);

        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = () => {
            micStream.getTracks().forEach(t => t.stop());
            stopLiveWaveform();
            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            uploadMic(blob);
        };

        mediaRecorder.start();
        micStatus.textContent = "Recording...";
        startRecordBtn.classList.add('hidden');
        stopRecordBtn.classList.remove('hidden', 'opacity-0');
        stopRecordBtn.disabled = false;
        retakeBtn.classList.remove('hidden', 'opacity-0');
        retakeBtn.disabled = false;
    } catch (err) { alert(err.message); }
});

stopRecordBtn.addEventListener('click', () => mediaRecorder.stop());
retakeBtn.addEventListener('click', () => {
    mediaRecorder.stop();
    resetMicUI();
});

function resetMicUI() {
    startRecordBtn.classList.remove('hidden');
    stopRecordBtn.classList.add('hidden', 'opacity-0');
    retakeBtn.classList.add('hidden', 'opacity-0');
    micStatus.textContent = "Microphone idle";
}

async function uploadMic(blob) {
    showSection('resultsSection');
    progressContainer.classList.remove('hidden');
    resetMicUI();
    const formData = new FormData();
    formData.append('audio_blob', blob);
    if (micTitleInput.value) {
        formData.append('custom_name', micTitleInput.value);
    }
    const res = await fetch('/start_mic_job', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.job_id) pollJob(data.job_id);
    micTitleInput.value = ''; // Reset input after upload
}

function setupLiveWaveform(stream) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioContext.createAnalyser();
    source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const ctx = liveWaveformCanvas.getContext('2d');
    function draw() {
        if (!analyser) return;
        animationFrameId = requestAnimationFrame(draw);
        analyser.getByteTimeDomainData(dataArray);
        ctx.clearRect(0, 0, liveWaveformCanvas.width, liveWaveformCanvas.height);
        ctx.lineWidth = 3;
        ctx.strokeStyle = '#10b981';
        ctx.beginPath();
        const sliceWidth = liveWaveformCanvas.width * 1.0 / bufferLength;
        let x = 0;
        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 128.0;
            const y = v * liveWaveformCanvas.height / 2;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            x += sliceWidth;
        }
        ctx.stroke();
    }
    draw();
}

function stopLiveWaveform() {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    if (audioContext) audioContext.close();
    analyser = null;
    liveWaveformCanvas.classList.add('hidden');
}

// Init
loadHistory();