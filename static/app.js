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
    competitorImages: [],  // URL paths on server (from scrape or upload)

    // Step 3
    analysis: null,
    questions: [],
    answers: {},

    // Step 4
    heroImageUrl: null,

    // Step 5
    catalogImages: [],
    catalogTotal: 0,
    catalogCompleted: 0,

    // Cost tracking
    totalCostInr: 0,
    costs: [],
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
        runAnalysis();
    });

    // Step 3
    document.getElementById('btn-step3-back').addEventListener('click', () => goToStep(2));
    document.getElementById('btn-step3-next').addEventListener('click', async () => {
        collectAnswers();
        const ok = await submitAnswers();
        if (!ok) return;
        goToStep(4);
    });

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
            state.competitorImages = data.images || [];
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
            state.competitorImages = data.images || [];
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

// ── API: Run Analysis (Step 3) ──
async function runAnalysis() {
    // Skip re-run if analysis already exists (user navigated back/forward)
    if (state.analysis) {
        renderAnalysisResults(state.analysis);
        renderQuestions(state.questions);
        validateStep3();
        return;
    }

    showStatus(3, 'Analyzing competitor catalog... this may take 30-60 seconds.');
    document.getElementById('btn-step3-next').disabled = true;
    document.getElementById('analysis-grid').innerHTML =
        '<div class="placeholder-message"><div class="spinner"></div><p>Analyzing competitor images...</p></div>';
    document.getElementById('questions-list').innerHTML =
        '<div class="placeholder-message">Questions will appear after analysis...</div>';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: state.sessionId }),
            signal: controller.signal,
        });
        clearTimeout(timeoutId);
        const data = await res.json();

        if (data.success) {
            state.analysis = data.analysis;
            state.questions = data.questions || [];
            renderAnalysisResults(data.analysis);
            renderQuestions(data.questions || []);
            if (data.costs) updateCostDisplay(data.costs, data.total_cost_inr);
            showStatus(3, 'Analysis complete. Answer the questions below or skip for smart defaults.', 'success');
            validateStep3();
        } else {
            showStatus(3, data.error || 'Analysis failed. Please try again.', 'error');
        }
    } catch (err) {
        clearTimeout(timeoutId);
        if (err.name === 'AbortError') {
            showStatus(3, 'Analysis timed out. Please try again.', 'error');
        } else {
            showStatus(3, 'Network error during analysis. Is the server running?', 'error');
        }
    }
}

// ── Render Analysis Results ──
function renderAnalysisResults(analysis) {
    const grid = document.getElementById('analysis-grid');
    grid.innerHTML = '';

    // Show catalog strategy above grid
    const existingStrategy = document.querySelector('.catalog-strategy');
    if (existingStrategy) existingStrategy.remove();

    if (analysis.catalog_strategy) {
        const strategyEl = document.createElement('p');
        strategyEl.className = 'catalog-strategy';
        strategyEl.textContent = analysis.catalog_strategy;
        grid.parentElement.insertBefore(strategyEl, grid);
    }

    const images = analysis.images || [];
    images.forEach(img => {
        const card = document.createElement('div');
        card.className = 'analysis-card';

        const imgUrl = state.competitorImages[img.index] || '';
        card.innerHTML = `
            <div class="analysis-image">
                <img src="${imgUrl}" alt="Competitor image ${img.index + 1}" />
            </div>
            <div class="analysis-info">
                <span class="intent-badge">${img.type}</span>
                <span class="priority-badge priority-${img.priority}">${img.priority}</span>
                <p class="intent-description">${img.intent}</p>
            </div>
        `;
        grid.appendChild(card);
    });
}

// ── Render Smart Questions ──
function renderQuestions(questions) {
    const list = document.getElementById('questions-list');
    list.innerHTML = '';

    if (!questions.length) {
        list.innerHTML = '<div class="placeholder-message">No additional questions needed.</div>';
        return;
    }

    questions.forEach(q => {
        const card = document.createElement('div');
        card.className = 'question-card';
        card.dataset.questionId = q.id;

        let inputHTML = '';
        if (q.type === 'choice' && q.options) {
            const optionsHTML = q.options.map(opt =>
                `<label class="choice-option">
                    <input type="radio" name="q_${q.id}" value="${opt}" class="question-answer" data-qid="${q.id}" />
                    <span>${opt}</span>
                </label>`
            ).join('');
            inputHTML = `
                <div class="question-choices">${optionsHTML}</div>
                <button class="btn btn-skip" onclick="skipQuestion('${q.id}', this)">Skip</button>
            `;
        } else if (q.type === 'image') {
            inputHTML = `
                <div class="question-input">
                    <label class="btn btn-secondary btn-small" style="cursor:pointer;">
                        Upload Image
                        <input type="file" accept="image/*" class="question-answer"
                               data-qid="${q.id}" hidden onchange="handleQuestionImage(this, '${q.id}')" />
                    </label>
                    <span class="question-image-name" id="qimg-${q.id}"></span>
                    <button class="btn btn-skip" onclick="skipQuestion('${q.id}', this)">Skip</button>
                </div>
            `;
        } else {
            // Default: text input
            inputHTML = `
                <div class="question-input">
                    <input type="text" class="text-input question-answer"
                           data-qid="${q.id}"
                           placeholder="${q.default_value || 'Type your answer...'}" />
                    <button class="btn btn-skip" onclick="skipQuestion('${q.id}', this)">Skip</button>
                </div>
            `;
        }

        card.innerHTML = `
            <p class="question-text">${q.text}</p>
            ${q.context ? `<p class="question-context">${q.context}</p>` : ''}
            ${inputHTML}
            <p class="question-default" id="default-${q.id}" style="display:none;">
                Using default: <em>${q.default_value || 'Standard premium quality'}</em>
            </p>
        `;
        list.appendChild(card);
    });
}

// ── Question Helpers ──
function skipQuestion(qid, btn) {
    state.answers[qid] = null; // null = use default
    const card = btn.closest('.question-card');
    card.classList.add('skipped');
    document.getElementById(`default-${qid}`).style.display = 'block';
    card.querySelectorAll('.question-answer').forEach(i => i.disabled = true);
    btn.textContent = 'Skipped';
    btn.disabled = true;
    validateStep3();
}

function handleQuestionImage(input, qid) {
    if (input.files.length > 0) {
        state.answers[qid] = input.files[0];
        document.getElementById(`qimg-${qid}`).textContent = input.files[0].name;
        validateStep3();
    }
}

function validateStep3() {
    const btn = document.getElementById('btn-step3-next');
    btn.disabled = !state.analysis;
}

function collectAnswers() {
    document.querySelectorAll('.question-answer').forEach(el => {
        const qid = el.dataset.qid;
        if (!qid || qid in state.answers) return; // already set (skipped or image)

        if (el.type === 'text') {
            state.answers[qid] = el.value.trim() || null;
        } else if (el.type === 'radio' && el.checked) {
            state.answers[qid] = el.value;
        }
    });
}

async function submitAnswers() {
    const textAnswers = {};
    for (const [k, v] of Object.entries(state.answers)) {
        if (v instanceof File) {
            textAnswers[k] = `[image: ${v.name}]`;
        } else {
            textAnswers[k] = v;
        }
    }

    try {
        const res = await fetch('/api/answers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: state.sessionId, answers: textAnswers }),
        });
        const data = await res.json();
        return data.success;
    } catch (err) {
        showStatus(3, 'Failed to save answers.', 'error');
        return false;
    }
}

// ── Cost Display ──
function updateCostDisplay(newCosts, totalInr) {
    if (!newCosts || !newCosts.length) return;

    state.costs.push(...newCosts);
    state.totalCostInr = totalInr || state.costs.reduce((sum, c) => sum + (c.cost_inr || 0), 0);

    const ticker = document.getElementById('cost-ticker');
    const valueEl = document.getElementById('cost-value');
    ticker.style.display = 'flex';
    valueEl.textContent = `₹${state.totalCostInr.toFixed(2)}`;

    // Pulse animation
    ticker.classList.remove('cost-pulse');
    void ticker.offsetWidth; // trigger reflow
    ticker.classList.add('cost-pulse');

    // Update breakdown
    renderCostDetails();
}

function renderCostDetails() {
    const details = document.getElementById('cost-details');
    let html = '';
    state.costs.forEach(c => {
        const tokens = (c.input_tokens || 0) + (c.output_tokens || 0);
        const tokenStr = tokens > 1000 ? `${(tokens / 1000).toFixed(1)}K` : tokens;
        html += `
            <div class="cost-row">
                <span class="cost-op">${c.operation || c.model}</span>
                <span class="cost-tokens">${tokenStr} tokens</span>
                <span class="cost-amount">₹${(c.cost_inr || 0).toFixed(2)}</span>
            </div>
        `;
    });
    html += `
        <div class="cost-row cost-total-row">
            <span class="cost-op">Total</span>
            <span></span>
            <span class="cost-amount">₹${state.totalCostInr.toFixed(2)}</span>
        </div>
    `;
    details.innerHTML = html;
}

function toggleCostDetails() {
    const details = document.getElementById('cost-details');
    details.classList.toggle('open');
}

// ── API Stubs (Phase 4+) ──
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
