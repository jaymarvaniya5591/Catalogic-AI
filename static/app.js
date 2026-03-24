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
    selectedSuggestedAdditionIds: [],
    imageDisplayData: [],

    // Step 4
    heroImageUrl: null,
    heroAccepted: false,
    catalogEventSource: null,

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

    // Robustness: if the user jumps between steps, auto-trigger generation if needed.
    if (n === 4 && state.sessionId && !state.heroImageUrl) {
        generateHeroImage({ regenerate: false });
    }
    if (n === 5 && state.sessionId && state.heroAccepted) {
        if (!state.catalogImages || state.catalogImages.length === 0) {
            startCatalogGeneration();
        }
    }
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
        // Start hero generation right after analysis/answers are saved.
        generateHeroImage({ regenerate: false });
    });

    // Step 4
    document.getElementById('btn-step4-back').addEventListener('click', () => goToStep(3));
    document.getElementById('btn-step4-next').addEventListener('click', () => {
        goToStep(5);
        startCatalogGeneration();
    });

    // Step 5
    document.getElementById('btn-step5-back').addEventListener('click', () => {
        if (state.catalogEventSource) {
            try { state.catalogEventSource.close(); } catch (_) {}
            state.catalogEventSource = null;
        }
        goToStep(4);
    });

    // Hero actions
    document.getElementById('btn-accept-hero').addEventListener('click', () => {
        state.heroAccepted = true;
        const btn = document.getElementById('btn-step4-next');
        if (btn) btn.disabled = false;
        showStatus(4, 'Hero image accepted. Generating your catalog...', 'success');
    });

    document.getElementById('btn-regenerate-hero').addEventListener('click', () => {
        state.heroAccepted = false;
        const btn = document.getElementById('btn-step4-next');
        if (btn) btn.disabled = true;
        generateHeroImage({ regenerate: true });
    });

    const heroUpload = document.getElementById('hero-upload');
    if (heroUpload) {
        heroUpload.addEventListener('change', async () => {
            const file = heroUpload.files && heroUpload.files[0];
            if (!file) return;
            state.heroAccepted = false;
            const btn = document.getElementById('btn-step4-next');
            if (btn) btn.disabled = true;
            await generateHeroImage({ overrideFile: file });
        });
    }

    const btnDownload = document.getElementById('btn-download');
    if (btnDownload) {
        btnDownload.addEventListener('click', async () => {
            await downloadCatalog();
        });
    }
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
    const btn = document.getElementById('btn-step2-next');
    btn.disabled = true;
    showStatus(2, state.productFiles.length > 0 ? 'Uploading your product images...' : 'Saving product details...');

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
        renderAttributeBreakdown(state.imageDisplayData);
        renderSuggestedImages(state.analysis, state.questions);
        validateStep3();
        return;
    }

    showStatus(3, 'Analyzing competitor catalog and your product images... this may take 30-60 seconds.');
    document.getElementById('btn-step3-next').disabled = true;
    document.getElementById('attr-cards').innerHTML =
        '<div class="placeholder-message"><div class="spinner"></div><p>Analyzing images...</p></div>';
    const suggestedSection = document.getElementById('suggested-section');
    if (suggestedSection) suggestedSection.style.display = 'none';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);

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
            state.imageDisplayData = data.image_display_data || [];
            state.selectedSuggestedAdditionIds = [];
            renderAttributeBreakdown(state.imageDisplayData);
            renderSuggestedImages(data.analysis, data.questions);
            if (data.costs) updateCostDisplay(data.costs, data.total_cost_inr);
            showStatus(3, 'Analysis complete. Review and adjust values for your product.', 'success');
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

// ── Render Attribute Breakdown (Step 3 — Section 1) ──
function renderAttributeBreakdown(imageDisplayData) {
    const container = document.getElementById('attr-cards');
    container.innerHTML = '';

    const cardsData = (imageDisplayData || []).filter(d => d.questions && d.questions.length > 0);

    if (!cardsData.length) {
        container.innerHTML = '<div class="placeholder-message">No additional details needed — your product images provided everything.</div>';
        return;
    }

    cardsData.forEach(imgData => {
        const card = document.createElement('div');
        card.className = 'attr-card';

        // Left: image
        const imageCol = document.createElement('div');
        imageCol.className = 'attr-card-image';
        imageCol.innerHTML = `<img src="${imgData.image_url || ''}" alt="Image ${imgData.index + 1}" />`;

        // Right: content
        const contentCol = document.createElement('div');
        contentCol.className = 'attr-card-content';
        contentCol.innerHTML = `
            <div class="attr-card-header">
                <span class="attr-card-title">Image ${imgData.index + 1}</span>
                <span class="intent-badge">${imgData.type || 'other'}</span>
            </div>
            <p class="attr-card-summary">${imgData.summary || ''}</p>
        `;

        const qContainer = document.createElement('div');
        qContainer.className = 'attr-questions';
        imgData.questions.forEach(q => {
            qContainer.appendChild(makeQuestionRow(q, false));
        });

        contentCol.appendChild(qContainer);
        card.appendChild(imageCol);
        card.appendChild(contentCol);
        container.appendChild(card);
    });
}

// ── Render Suggested Images (Step 3 — Section 2) ──
function renderSuggestedImages(analysis, questions) {
    const section = document.getElementById('suggested-section');
    const listEl = document.getElementById('suggested-list');
    const additions = analysis?.suggested_additions || [];

    if (!additions.length) {
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';
    listEl.innerHTML = '';

    // Group suggested addition questions
    const suggestedQuestions = new Map();
    (questions || []).forEach(q => {
        if (q?.group?.kind === 'suggested_addition') {
            const aid = q.group.addition_id;
            if (!suggestedQuestions.has(aid)) suggestedQuestions.set(aid, []);
            suggestedQuestions.get(aid).push(q);
        }
    });

    const selectedSet = new Set(state.selectedSuggestedAdditionIds || []);

    additions.forEach(add => {
        const id = add.id;
        const checked = selectedSet.has(id);
        const qs = suggestedQuestions.get(id) || [];

        const card = document.createElement('div');
        card.className = 'suggested-card' + (checked ? ' selected' : '');

        // Card header with checkbox
        const cardHeader = document.createElement('div');
        cardHeader.className = 'suggested-card-header';
        cardHeader.innerHTML = `
            <label class="suggested-check-label">
                <input type="checkbox" class="suggested-checkbox"
                       data-addition-id="${id}" ${checked ? 'checked' : ''} />
                <div class="suggested-card-info">
                    <strong>${add.title || id}</strong>
                    <span class="suggested-card-category">${add.category || ''}</span>
                </div>
            </label>
        `;

        // Questions body (smooth expand/collapse)
        const cardBody = document.createElement('div');
        cardBody.className = 'suggested-card-body';

        qs.forEach(q => {
            cardBody.appendChild(makeQuestionRow(q, !checked));
        });

        // Checkbox change handler
        const checkbox = cardHeader.querySelector('.suggested-checkbox');
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                if (state.selectedSuggestedAdditionIds.length >= 2 && !state.selectedSuggestedAdditionIds.includes(id)) {
                    checkbox.checked = false;
                    showStatus(3, 'You can select up to 2 suggested additions.', 'error');
                    return;
                }
                if (!state.selectedSuggestedAdditionIds.includes(id)) {
                    state.selectedSuggestedAdditionIds.push(id);
                }
            } else {
                state.selectedSuggestedAdditionIds = state.selectedSuggestedAdditionIds.filter(x => x !== id);
            }
            // Re-render this section
            renderSuggestedImages(analysis, questions);
        });

        card.appendChild(cardHeader);
        if (qs.length) card.appendChild(cardBody);
        listEl.appendChild(card);

        // Animate open after render
        if (checked && qs.length) {
            requestAnimationFrame(() => {
                cardBody.style.maxHeight = cardBody.scrollHeight + 'px';
                cardBody.style.paddingTop = '12px';
                cardBody.style.paddingBottom = '16px';
            });
        }
    });
}

// ── Question Row Builder (shared by attr breakdown + suggested) ──
function makeQuestionRow(q, disabledForSelection) {
    const row = document.createElement('div');
    row.className = 'q-row';
    row.dataset.questionId = q.id;

    const defaultValue = q.default_value || 'Standard premium quality';
    const disabledAttr = disabledForSelection ? 'disabled' : '';

    // Label side
    let labelHTML = `<div class="q-row-label">
        <div>${q.text}</div>
        ${q.context ? `<div class="q-row-context">${q.context}</div>` : ''}
    </div>`;

    // Input side
    let inputHTML = '';
    if (q.type === 'choice' && q.options) {
        const pillsHTML = q.options.map(opt => {
            const isDefault = opt === defaultValue;
            return `<label class="pill-option${isDefault ? ' selected' : ''}${disabledForSelection ? ' disabled' : ''}">
                <input type="radio" name="q_${q.id}" value="${opt}"
                       class="question-answer" data-qid="${q.id}"
                       ${isDefault ? 'checked' : ''} ${disabledAttr} />
                ${opt}
            </label>`;
        }).join('');
        inputHTML = `<div class="q-row-input"><div class="pill-group">${pillsHTML}</div></div>`;
    } else if (q.type === 'image') {
        inputHTML = `<div class="q-row-input">
            <label class="btn btn-secondary btn-small"
                   style="cursor:${disabledForSelection ? 'not-allowed' : 'pointer'}; opacity:${disabledForSelection ? 0.6 : 1};">
                Upload
                <input type="file" accept="image/*"
                       class="question-answer" data-qid="${q.id}"
                       ${disabledAttr} hidden
                       onchange="handleQuestionImage(this, '${q.id}')" />
            </label>
            <span class="question-image-name" id="qimg-${q.id}"></span>
        </div>`;
    } else {
        inputHTML = `<div class="q-row-input">
            <input type="text" class="text-input question-answer"
                   data-qid="${q.id}"
                   placeholder="${defaultValue}"
                   ${disabledAttr} />
        </div>`;
    }

    row.innerHTML = labelHTML + inputHTML;

    // Pill click handlers
    if (q.type === 'choice' && q.options && !disabledForSelection) {
        row.querySelectorAll('.pill-option').forEach(pill => {
            pill.addEventListener('click', () => {
                row.querySelectorAll('.pill-option').forEach(p => p.classList.remove('selected'));
                pill.classList.add('selected');
                pill.querySelector('input').checked = true;
            });
        });
    }

    return row;
}

// ── Question Helpers ──
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
    const imageEntries = []; // { qid, file }

    for (const [k, v] of Object.entries(state.answers)) {
        if (v instanceof File) {
            imageEntries.push({ qid: k, file: v });
        } else {
            textAnswers[k] = v;
        }
    }

    const formData = new FormData();
    formData.append('session_id', state.sessionId);
    formData.append('answers_json', JSON.stringify(textAnswers));
    formData.append('selected_additions_json', JSON.stringify(state.selectedSuggestedAdditionIds || []));
    formData.append('image_qids_json', JSON.stringify(imageEntries.map(e => e.qid)));
    imageEntries.forEach(e => formData.append('image_files', e.file));

    try {
        const res = await fetch('/api/answers', { method: 'POST', body: formData });
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
async function generateHeroImage({ regenerate = false, overrideFile = null } = {}) {
    const step = 4;
    const btnAccept = document.getElementById('btn-accept-hero');
    const btnRegen = document.getElementById('btn-regenerate-hero');
    const actions = document.getElementById('hero-actions');
    const placeholder = document.getElementById('hero-placeholder');
    const imgEl = document.getElementById('hero-image');
    const step4NextBtn = document.getElementById('btn-step4-next');

    state.heroAccepted = false;
    if (step4NextBtn) step4NextBtn.disabled = true;

    if (placeholder) placeholder.style.display = 'flex';
    if (actions) actions.style.display = 'none';
    if (imgEl) imgEl.style.display = 'none';

    showStatus(step, regenerate ? 'Regenerating hero image...' : 'Generating your hero image...', '');

    const formData = new FormData();
    formData.append('session_id', state.sessionId);
    formData.append('regenerate', regenerate ? 'true' : 'false');
    if (overrideFile) {
        formData.append('hero_override', overrideFile);
    }

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 120000);

        const res = await fetch('/api/generate-hero', { method: 'POST', body: formData, signal: controller.signal });
        clearTimeout(timeoutId);

        const data = await res.json();
        if (!data.success) {
            const msg = data.message || data.error || 'Hero generation failed.';
            showStatus(step, msg, 'error');
            return false;
        }

        state.heroImageUrl = data.hero_image_url;

        if (imgEl) {
            imgEl.src = state.heroImageUrl + '?t=' + Date.now();
            imgEl.style.display = 'block';
        }
        if (actions) actions.style.display = 'flex';
        if (placeholder) placeholder.style.display = 'none';

        if (data.costs) updateCostDisplay(data.costs, data.total_cost_inr);
        showStatus(step, 'Hero image ready. Review and click Accept to continue.', 'success');
        if (btnAccept) btnAccept.disabled = false;
        if (btnRegen) btnRegen.disabled = false;

        return true;
    } catch (err) {
        showStatus(step, 'Hero generation failed or timed out. Please retry or upload your own hero.', 'error');
        return false;
    }
}

async function regenerateHero() {
    return generateHeroImage({ regenerate: true });
}

function startCatalogGeneration() {
    const step = 5;
    if (state.catalogEventSource) {
        try { state.catalogEventSource.close(); } catch (_) {}
        state.catalogEventSource = null;
    }

    const grid = document.getElementById('catalog-grid');
    const placeholder = document.getElementById('catalog-placeholder');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const downloadSection = document.getElementById('download-section');

    if (grid) grid.innerHTML = '';
    if (progressFill) progressFill.style.width = '0%';
    if (progressText) progressText.textContent = '0 / 0 images';
    if (downloadSection) downloadSection.style.display = 'none';

    // Immediate placeholder (before SSE start)
    if (grid) {
        const ph = document.createElement('div');
        ph.className = 'placeholder-message';
        ph.id = 'catalog-placeholder';
        ph.textContent = 'Generating catalog images...';
        grid.appendChild(ph);
    }

    showStatus(step, 'Catalog generation started...', '');

    const esUrl = `/api/generate-catalog/stream?session_id=${encodeURIComponent(state.sessionId)}`;
    const es = new EventSource(esUrl);
    state.catalogEventSource = es;

    state.catalogImages = [];
    state.catalogCompleted = 0;
    state.catalogTotal = 0;

    const renderCard = (key, imageUrl, status, error) => {
        const gridEl = document.getElementById('catalog-grid');
        if (!gridEl) return;

        // Remove placeholder once first image arrives
        const ph = document.getElementById('catalog-placeholder');
        if (ph) ph.remove();

        const card = document.createElement('div');
        card.className = 'catalog-card';

        const content = status === 'success'
            ? `<div class="catalog-image-wrapper">
                    <img src="${imageUrl}" alt="${key}" class="catalog-image loaded" />
               </div>`
            : `<div class="catalog-image-wrapper" style="display:flex;align-items:center;justify-content:center;">
                    <div style="padding:12px;text-align:center;color:var(--text-secondary);font-size:13px;">
                        Failed: ${status}${error ? '<br/>' + error.substring(0,80) : ''}
                    </div>
               </div>`;

        card.innerHTML = content + `
            <div class="catalog-card-footer">
                <span style="color:var(--text-secondary);font-size:12px;">${key}</span>
                <span style="color:var(--text-muted);font-size:12px;">${status}</span>
            </div>
        `;
        gridEl.appendChild(card);
    };

    es.addEventListener('catalog_start', (e) => {
        const data = JSON.parse(e.data || '{}');
        state.catalogTotal = data.total || 0;
        if (progressText) progressText.textContent = `0 / ${state.catalogTotal} images`;
        showStatus(step, `Generating ${state.catalogTotal} images...`, '');
    });

    es.addEventListener('catalog_image', (e) => {
        const data = JSON.parse(e.data || '{}');
        state.catalogCompleted += 1;

        const pct = state.catalogTotal > 0 ? Math.round((state.catalogCompleted / state.catalogTotal) * 100) : 0;
        if (progressFill) progressFill.style.width = `${pct}%`;
        if (progressText) progressText.textContent = `${state.catalogCompleted} / ${state.catalogTotal} images`;

        if (data.status === 'success') {
            renderCard(data.key, data.image_url, 'success');
            if (data.cost) updateCostDisplay([data.cost], null);
        } else {
            renderCard(data.key, null, data.status || 'failed', data.error);
        }
    });

    es.addEventListener('catalog_done', (e) => {
        try { es.close(); } catch (_) {}
        state.catalogEventSource = null;
        if (downloadSection) downloadSection.style.display = 'block';
        showStatus(step, 'Catalog generation complete.', 'success');
    });

    es.onerror = () => {
        try { es.close(); } catch (_) {}
        state.catalogEventSource = null;
        showStatus(step, 'Catalog generation connection error.', 'error');
    };
}

async function regenerateCatalogImage(index) {
    // Not wired in UI yet; keep as a small helper for future work.
    try {
        const formData = new FormData();
        formData.append('session_id', state.sessionId);
        formData.append('image_key', index);
        const res = await fetch('/api/regenerate', { method: 'POST', body: formData });
        const data = await res.json();
        return data.success ? data.image_url : null;
    } catch (_) {
        return null;
    }
}

async function downloadCatalog() {
    try {
        const res = await fetch(`/api/download/${encodeURIComponent(state.sessionId)}`);
        if (!res.ok) {
            showStatus(5, 'Download failed.', 'error');
            return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = 'catalog.zip';
        document.body.appendChild(a);
        a.click();
        a.remove();

        setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (err) {
        showStatus(5, 'Download failed.', 'error');
    }
}

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initUploadZone('competitor-upload-zone', 'competitor-files', 'competitor-preview-grid', 'competitorFiles');
    initUploadZone('product-upload-zone', 'product-files', 'product-preview-grid', 'productFiles');
    initNavigation();
    initStepClicks();
    goToStep(1);
});
