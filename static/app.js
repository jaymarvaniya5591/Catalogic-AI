// ── State ──
const state = {
    currentStep: 1,
    sessionId: null,

    // Step 1
    competitorMode: 'url',
    competitorUrl: '',
    competitorFiles: [],
    competitorDescription: '',
    scraped: null,

    // Step 2
    productFiles: [],
    productDescription: '',

    // Step 3
    analysis: null,
    questions: [],
    answers: {},

    // Step 4
    heroImageUrl: null,

    // Step 5
    catalogImages: [],
    catalogTotal: 0,
    catalogCompleted: 0
};

// ── Step Navigation ──
function goToStep(n) {
    if (n < 1 || n > 5) return;

    const current = document.querySelector('.step-section.active');
    if (current) current.classList.remove('active');

    document.getElementById(`step-${n}`).classList.add('active');
    updateStepProgress(n);
    state.currentStep = n;

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateStepProgress(activeStep) {
    const indicators = document.querySelectorAll('.step-indicator');
    const connectors = document.querySelectorAll('.step-connector');

    indicators.forEach((el, i) => {
        const step = i + 1;
        el.classList.remove('active', 'completed');
        if (step === activeStep) el.classList.add('active');
        else if (step < activeStep) el.classList.add('completed');
    });

    connectors.forEach((el, i) => {
        el.classList.toggle('completed', i + 1 < activeStep);
    });
}

// ── Tab Switching (Step 1) ──
function initTabs() {
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.tab;

            // Update tab buttons
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Update tab content
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.getElementById(`tab-${target}`).classList.add('active');

            state.competitorMode = target;
            validateStep1();
        });
    });
}

// ── Upload Zones ──
function initUploadZone(zoneId, fileInputId, previewGridId, fileKey) {
    const zone = document.getElementById(zoneId);
    const input = document.getElementById(fileInputId);
    const grid = document.getElementById(previewGridId);

    if (!zone || !input) return;

    // Click to browse
    zone.addEventListener('click', () => input.click());

    // File selected
    input.addEventListener('change', () => {
        addFiles(Array.from(input.files), fileKey, grid);
        input.value = '';
    });

    // Drag & drop
    zone.addEventListener('dragenter', e => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragover', e => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
        addFiles(files, fileKey, grid);
    });
}

function addFiles(newFiles, fileKey, grid) {
    state[fileKey] = [...state[fileKey], ...newFiles];
    renderPreviews(state[fileKey], grid, fileKey);

    if (fileKey === 'competitorFiles') validateStep1();
    if (fileKey === 'productFiles') validateStep2();
}

function renderPreviews(files, grid, fileKey) {
    grid.innerHTML = '';
    files.forEach((file, i) => {
        const thumb = document.createElement('div');
        thumb.className = 'preview-thumb';

        const img = document.createElement('img');
        img.src = URL.createObjectURL(file);
        img.alt = file.name;

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-btn';
        removeBtn.textContent = '\u00d7';
        removeBtn.addEventListener('click', e => {
            e.stopPropagation();
            state[fileKey].splice(i, 1);
            renderPreviews(state[fileKey], grid, fileKey);
        });

        thumb.appendChild(img);
        thumb.appendChild(removeBtn);
        grid.appendChild(thumb);
    });
}

// ── Validation ──
function validateStep1() {
    const btn = document.getElementById('btn-step1-next');
    if (state.competitorMode === 'url') {
        const url = document.getElementById('competitor-url').value.trim();
        state.competitorUrl = url;
        btn.disabled = !url;
    } else {
        btn.disabled = state.competitorFiles.length === 0;
    }
}

function validateStep2() {
    const btn = document.getElementById('btn-step2-next');
    const desc = document.getElementById('product-description').value.trim();
    state.productDescription = desc;
    btn.disabled = state.productFiles.length === 0 && !desc;
}

// ── Status Messages ──
function showStatus(stepNum, message, type = '') {
    const el = document.getElementById(`step${stepNum}-status`);
    if (!el) return;
    el.textContent = message;
    el.className = 'status-message' + (type ? ` ${type}` : '');
}

function clearStatus(stepNum) {
    showStatus(stepNum, '');
}

// ── Navigation Buttons ──
function initNavigation() {
    // Step 1
    document.getElementById('competitor-url').addEventListener('input', validateStep1);
    document.getElementById('btn-scrape').addEventListener('click', scrapeCompetitorUrl);
    document.getElementById('competitor-url').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); scrapeCompetitorUrl(); }
    });
    document.getElementById('btn-step1-next').addEventListener('click', async () => {
        if (state.competitorMode === 'upload') {
            const ok = await uploadCompetitorImages();
            if (!ok) return;
        }
        goToStep(2);
    });

    // Step 2
    document.getElementById('product-description').addEventListener('input', validateStep2);
    document.getElementById('btn-step2-back').addEventListener('click', () => goToStep(1));
    document.getElementById('btn-step2-next').addEventListener('click', async () => {
        const ok = await uploadProductImages();
        if (!ok) return;
        goToStep(3);
    });

    // Step 3
    document.getElementById('btn-step3-back').addEventListener('click', () => goToStep(2));
    document.getElementById('btn-step3-next').addEventListener('click', () => goToStep(4));

    // Step 4
    document.getElementById('btn-step4-back').addEventListener('click', () => goToStep(3));
    document.getElementById('btn-step4-next').addEventListener('click', () => goToStep(5));

    // Step 5
    document.getElementById('btn-step5-back').addEventListener('click', () => goToStep(4));
}

// ── Step Progress Clicks ──
function initStepClicks() {
    document.querySelectorAll('.step-indicator').forEach(el => {
        el.addEventListener('click', () => {
            const step = parseInt(el.dataset.step);
            if (step <= state.currentStep) {
                goToStep(step);
            }
        });
    });
}

// ── API: Scrape Competitor URL ──
async function scrapeCompetitorUrl() {
    const url = document.getElementById('competitor-url').value.trim();
    if (!url) return;

    const btn = document.getElementById('btn-scrape');
    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    showStatus(1, 'Scraping product page... this takes 20-30 seconds, please wait.');

    // Timeout after 90 seconds to prevent infinite hang
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 90000);

    try {
        const res = await fetch('/api/scrape', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        // Handle non-OK HTTP responses (500, 422, etc.)
        if (!res.ok) {
            let errorMsg = `Server error (${res.status})`;
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errData.error || errorMsg;
            } catch (_) {
                // Response wasn't JSON — try text
                try { errorMsg = (await res.text()).substring(0, 200) || errorMsg; } catch (_) {}
            }
            console.error('Scrape failed:', res.status, errorMsg);
            showStatus(1, errorMsg + ' You can switch to the "Upload Images" tab.', 'error');
            return;
        }

        const data = await res.json();

        if (data.success) {
            state.sessionId = data.session_id;
            state.scraped = data;
            state.competitorUrl = url;
            showScrapedResults(data);
            showStatus(1, `Found ${data.images.length} images from ${data.platform}`, 'success');
            document.getElementById('btn-step1-next').disabled = false;
        } else {
            showStatus(1, (data.error || 'Scraping failed.') + ' You can switch to the "Upload Images" tab.', 'error');
            if (data.session_id) state.sessionId = data.session_id;
        }
    } catch (err) {
        clearTimeout(timeoutId);
        console.error('Scrape error:', err);
        if (err.name === 'AbortError') {
            showStatus(1, 'Scraping timed out after 90 seconds. Try a different URL or upload images manually.', 'error');
        } else {
            showStatus(1, 'Could not reach server. Make sure the server is running (.\\serve).', 'error');
        }
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analyze URL';
    }
}

// ── Display Scraped Results ──
function showScrapedResults(data) {
    const container = document.getElementById('scraped-results');
    container.style.display = 'block';
    container.innerHTML = '';

    if (data.title) {
        const titleEl = document.createElement('p');
        titleEl.className = 'scraped-title';
        titleEl.textContent = data.title;
        container.appendChild(titleEl);
    }

    const grid = document.createElement('div');
    grid.className = 'image-preview-grid';
    data.images.forEach(imgUrl => {
        const thumb = document.createElement('div');
        thumb.className = 'preview-thumb';
        const img = document.createElement('img');
        img.src = imgUrl;
        img.alt = 'Scraped product image';
        thumb.appendChild(img);
        grid.appendChild(thumb);
    });
    container.appendChild(grid);

    if (data.description) {
        const descEl = document.createElement('p');
        descEl.className = 'scraped-description';
        descEl.textContent = data.description.substring(0, 200) + (data.description.length > 200 ? '...' : '');
        container.appendChild(descEl);
    }
}

// ── API: Upload Competitor Images ──
async function uploadCompetitorImages() {
    if (state.competitorFiles.length === 0) return false;

    const btn = document.getElementById('btn-step1-next');
    btn.disabled = true;
    showStatus(1, 'Uploading competitor images...');

    const formData = new FormData();
    state.competitorFiles.forEach(file => formData.append('images', file));
    formData.append('description', document.getElementById('competitor-description').value.trim());
    if (state.sessionId) formData.append('session_id', state.sessionId);

    try {
        const res = await fetch('/api/upload-competitor', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.success) {
            state.sessionId = data.session_id;
            showStatus(1, `Uploaded ${data.images.length} images`, 'success');
            return true;
        } else {
            showStatus(1, data.error || 'Upload failed', 'error');
            return false;
        }
    } catch (err) {
        showStatus(1, 'Network error. Please try again.', 'error');
        return false;
    } finally {
        btn.disabled = false;
    }
}

// ── API: Upload Product Images ──
async function uploadProductImages() {
    if (state.productFiles.length === 0) return false;

    const btn = document.getElementById('btn-step2-next');
    btn.disabled = true;
    showStatus(2, 'Uploading your product images...');

    const formData = new FormData();
    state.productFiles.forEach(file => formData.append('images', file));
    formData.append('description', document.getElementById('product-description').value.trim());
    formData.append('session_id', state.sessionId);

    try {
        const res = await fetch('/api/upload-product', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.success) {
            state.productDescription = data.description;
            showStatus(2, `Uploaded ${data.images.length} product images`, 'success');
            return true;
        } else {
            showStatus(2, data.error || 'Upload failed', 'error');
            return false;
        }
    } catch (err) {
        showStatus(2, 'Network error. Please try again.', 'error');
        return false;
    } finally {
        btn.disabled = false;
    }
}

// ── API Stubs (Phase 3+) ──
async function runAnalysis() { /* POST /api/analyze */ }
async function generateHeroImage() { /* POST /api/generate-hero */ }
async function regenerateHero() { /* POST /api/generate-hero */ }
function startCatalogGeneration() { /* GET /api/generate-catalog/stream via EventSource */ }
async function regenerateCatalogImage(index) { /* POST /api/regenerate */ }
async function downloadCatalog() { /* GET /api/download/{sessionId} */ }

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initUploadZone('competitor-upload-zone', 'competitor-files', 'competitor-preview-grid', 'competitorFiles');
    initUploadZone('product-upload-zone', 'product-files', 'product-preview-grid', 'productFiles');
    initNavigation();
    initStepClicks();
    goToStep(1);
});
