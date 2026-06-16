document.addEventListener("DOMContentLoaded", () => {

    // ── Running plan: week total ──────────────────────────────────────────
    const distanceInputs = document.querySelectorAll("input[name$='_distance']");
    const totalEl = document.querySelector("[data-week-total]");

    function updateWeekTotal() {
        if (!totalEl) return;
        let total = 0;
        distanceInputs.forEach((input) => {
            const val = parseFloat(input.value);
            if (!Number.isNaN(val)) total += val;
        });
        totalEl.textContent = Number.isInteger(total) ? total : parseFloat(total.toFixed(2));
    }

    document.querySelectorAll("select[name$='_type']").forEach((select) => {
        select.addEventListener("change", () => {
            const day = select.name.replace("_type", "");
            const distInput = document.querySelector(`input[name="${day}_distance"]`);
            if (distInput && select.value === "rest") distInput.value = "0";
            updateWeekTotal();
        });
    });
    distanceInputs.forEach((input) => input.addEventListener("input", updateWeekTotal));
    updateWeekTotal();

    // ── Birthdays: constrain day count by month ───────────────────────────
    const birthdayDaysByMonth = {
        '01':31,'02':29,'03':31,'04':30,'05':31,'06':30,
        '07':31,'08':31,'09':30,'10':31,'11':30,'12':31,
    };

    function updateBirthdayDayOptions(monthSelect, daySelect) {
        if (!monthSelect || !daySelect) return;
        const month = monthSelect.value;
        const maxDay = birthdayDaysByMonth[month] || 31;
        const currentValue = daySelect.value;
        daySelect.innerHTML = '<option value="">Day</option>';
        for (let day = 1; day <= maxDay; day++) {
            const value = String(day).padStart(2, '0');
            const option = document.createElement('option');
            option.value = value;
            option.textContent = value;
            if (value === currentValue) option.selected = true;
            daySelect.appendChild(option);
        }
    }

    document.querySelectorAll('.birthday-form, .birthday-edit-form').forEach((form) => {
        const monthSelect = form.querySelector('select[name="month"]');
        const daySelect = form.querySelector('select[name="day"]');
        if (!monthSelect || !daySelect) return;
        monthSelect.addEventListener('change', () => updateBirthdayDayOptions(monthSelect, daySelect));
        updateBirthdayDayOptions(monthSelect, daySelect);
    });

    // ── Tab switching ─────────────────────────────────────────────────────
    const tabButtons = document.querySelectorAll('.tab-button');
    if (tabButtons.length) {
        const countdownBadge = document.getElementById('days-countdown-badge');
        const raceBadge = document.getElementById('race-countdown-badge');
        const birthdayBadge = document.getElementById('birthday-countdown-badge');

        tabButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                tabButtons.forEach(b => {
                    b.classList.remove('btn--primary');
                    b.classList.add('btn--ghost');
                    b.setAttribute('aria-selected', 'false');
                });
                document.querySelectorAll('.tab-content').forEach(c => {
                    c.style.display = 'none';
                    c.setAttribute('aria-hidden', 'true');
                });
                btn.classList.remove('btn--ghost');
                btn.classList.add('btn--primary');
                btn.setAttribute('aria-selected', 'true');
                const target = document.querySelector(btn.getAttribute('data-target'));
                if (target) { target.style.display = 'block'; target.setAttribute('aria-hidden', 'false'); }
                const selectedTab = btn.getAttribute('data-target').replace('#', '');
                if (countdownBadge) countdownBadge.classList.toggle('countdown-badge--hidden', selectedTab !== 'interview');
                if (raceBadge) raceBadge.classList.toggle('countdown-badge--hidden', selectedTab !== 'running');
                if (birthdayBadge) birthdayBadge.classList.toggle('countdown-badge--hidden', selectedTab !== 'birthdays');
                const newUrl = new URL(window.location.href);
                newUrl.searchParams.set('tab', selectedTab);
                window.history.replaceState(null, '', newUrl);
            });
        });
        let active = Array.from(tabButtons).find(b => b.getAttribute('aria-selected') === 'true');
        if (!active) active = tabButtons[0];
        tabButtons.forEach(b => {
            if (b === active) {
                b.classList.remove('btn--ghost'); b.classList.add('btn--primary'); b.setAttribute('aria-selected', 'true');
            } else {
                b.classList.remove('btn--primary'); b.classList.add('btn--ghost'); b.setAttribute('aria-selected', 'false');
            }
        });
        const activeTarget = document.querySelector(active.getAttribute('data-target'));
        if (activeTarget) {
            document.querySelectorAll('.tab-content').forEach(c => { c.style.display = 'none'; c.setAttribute('aria-hidden', 'true'); });
            activeTarget.style.display = 'block';
            activeTarget.setAttribute('aria-hidden', 'false');
        }
    }

    // ── Interview prep: type toggle (text vs LC number) ───────────────────
    function updateInterviewTaskField(typeSelect) {
        const form = typeSelect.closest('form');
        if (!form) return;
        const taskInput = form.querySelector('.interview-task-input');
        const lcRow = form.querySelector('.lc-input-row');
        if (!taskInput) return;

        if (typeSelect.value === 'leetcode') {
            taskInput.style.display = 'none';
            taskInput.removeAttribute('required');
            if (lcRow) {
                lcRow.style.display = 'flex';
                const lcNum = lcRow.querySelector('.lc-number-input');
                const lcName = lcRow.querySelector('.lc-name-display');
                const match = taskInput.value.match(/^#(\d+)\s+(.+)$/);
                if (lcNum) lcNum.value = match ? match[1] : '';
                if (lcName) lcName.textContent = match ? match[2] : '';
            }
        } else {
            taskInput.style.display = '';
            taskInput.setAttribute('required', '');
            taskInput.placeholder = 'Description';
            if (lcRow) lcRow.style.display = 'none';
        }
    }

    async function resolveLeetcodeNumber(lcNumberInput) {
        const number = parseInt(lcNumberInput.value, 10);
        const form = lcNumberInput.closest('form');
        const lcRow = lcNumberInput.closest('.lc-input-row');
        if (!form) return;

        const lcName = lcRow && lcRow.querySelector('.lc-name-display');
        const taskInput = form.querySelector('.interview-task-input');
        const slugInput = form.querySelector('input[name="leetcode_slug"]');
        const statusEl = form.querySelector('.lc-status');

        if (!number || number < 1) {
            if (lcName) lcName.textContent = '';
            if (taskInput) taskInput.value = '';
            if (slugInput) slugInput.value = '';
            return;
        }

        if (statusEl) statusEl.textContent = 'Looking up...';
        if (lcName) lcName.textContent = '';

        try {
            const res = await fetch(`/leetcode/lookup?number=${number}`);
            const data = await res.json();
            if (res.ok) {
                if (lcName) lcName.textContent = data.title;
                if (taskInput) taskInput.value = data.task;
                if (slugInput) slugInput.value = data.slug;
                if (statusEl) statusEl.textContent = '';
            } else {
                if (lcName) lcName.textContent = '';
                if (taskInput) taskInput.value = '';
                if (slugInput) slugInput.value = '';
                if (statusEl) statusEl.textContent = data.error || 'Not found';
            }
        } catch {
            if (statusEl) statusEl.textContent = 'Lookup failed';
        }
    }

    function wireInterviewLookup(typeSelect) {
        const form = typeSelect.closest('form');
        if (!form) return;
        const lcRow = form.querySelector('.lc-input-row');
        if (!lcRow) return;
        const lcNum = lcRow.querySelector('.lc-number-input');
        if (!lcNum || lcNum.dataset.wired) return;
        lcNum.dataset.wired = '1';

        let timer;
        lcNum.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(() => resolveLeetcodeNumber(lcNum), 600);
        });
    }

    document.querySelectorAll('.interview-type-select').forEach((typeSelect) => {
        typeSelect.addEventListener('change', () => updateInterviewTaskField(typeSelect));
        updateInterviewTaskField(typeSelect);
        wireInterviewLookup(typeSelect);
    });

    // ── Days until 2027 countdown ─────────────────────────────────────────
    const countdownEl = document.getElementById('countdown-days');
    if (countdownEl) {
        const target = new Date('2027-01-01');
        const now = new Date();
        const days = Math.ceil((target - now) / (1000 * 60 * 60 * 24));
        countdownEl.textContent = days.toLocaleString();
    }

    // ── Days until race countdown (dynamic from active plan) ─────────────
    const raceCountdownEl = document.getElementById('race-countdown-days');
    if (raceCountdownEl && window.RACE_DATE) {
        const raceDays = Math.ceil((new Date(window.RACE_DATE) - new Date()) / (1000 * 60 * 60 * 24));
        raceCountdownEl.textContent = Math.max(0, raceDays).toLocaleString();
    }

    // ── Claude generation modal ───────────────────────────────────────────

    const overlay    = document.getElementById('claude-modal-overlay');
    const modalTitle = document.getElementById('claude-modal-title');
    const warning    = document.getElementById('claude-modal-warning');
    const textarea   = document.getElementById('claude-custom-prompt');
    const cancelBtn  = document.getElementById('claude-modal-cancel');
    const confirmBtn = document.getElementById('claude-modal-confirm');
    const intensityBtns = overlay ? overlay.querySelectorAll('.intensity-btn') : [];

    let _pendingWeekLabel = null;
    let _pendingType = 'interview';

    const _modalConfig = {
        interview: {
            title: '✦ Generate Interview Prep',
            warning: 'Completed tasks will be preserved. Incomplete tasks will be regenerated.',
            showIntensity: true,
            placeholder: 'e.g. Exclude Wednesday from scheduling and redistribute those tasks across the remaining days.',
        },
        'running-full': {
            title: '✦ Generate Training Plan',
            warning: 'This will replace your entire running plan through October 10th.',
            showIntensity: false,
            placeholder: 'Any constraints? e.g. "I race a 5K on July 4th" or "No running on Wednesdays"',
        },
        'running-edit': {
            title: '✦ Edit with Claude',
            warning: 'The current week plan will be modified based on your instructions.',
            showIntensity: false,
            placeholder: 'What would you like to change? e.g. "Move my long run to Monday, I have plans Saturday"',
        },
    };

    const intensitySection = document.getElementById('claude-modal-intensity');

    function openClaudeModal(weekLabel, hasPlan, type) {
        if (!overlay) return;
        _pendingWeekLabel = weekLabel;
        _pendingType = type || 'interview';
        const cfg = _modalConfig[_pendingType] || _modalConfig.interview;
        if (modalTitle) modalTitle.textContent = cfg.title;
        if (warning) {
            warning.textContent = cfg.warning;
            warning.style.display = hasPlan ? 'block' : 'none';
        }
        if (intensitySection) intensitySection.style.display = cfg.showIntensity ? '' : 'none';
        if (textarea) textarea.placeholder = cfg.placeholder || '';
        textarea.value = '';
        if (cfg.showIntensity) {
            intensityBtns.forEach(b => {
                b.classList.toggle('intensity-btn--active', b.dataset.intensity === 'normal');
            });
        }
        overlay.setAttribute('aria-hidden', 'false');
        overlay.classList.add('modal--open');
        setTimeout(() => textarea.focus(), 50);
    }

    function closeClaudeModal() {
        if (!overlay) return;
        overlay.classList.remove('modal--open');
        overlay.setAttribute('aria-hidden', 'true');
        _pendingWeekLabel = null;
    }

    if (overlay) {
        intensityBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                intensityBtns.forEach(b => b.classList.remove('intensity-btn--active'));
                btn.classList.add('intensity-btn--active');
            });
        });
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeClaudeModal();
        });
        cancelBtn.addEventListener('click', closeClaudeModal);
        confirmBtn.addEventListener('click', () => {
            const intensity = overlay.querySelector('.intensity-btn--active')?.dataset.intensity || 'normal';
            const customPrompt = textarea.value.trim();
            const weekLabel = _pendingWeekLabel;
            const type = _pendingType;
            closeClaudeModal();
            startGenerate(weekLabel, intensity, customPrompt, type);
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('modal--open')) closeClaudeModal();
        });
    }

    window.handleClaudeGenerate = function handleClaudeGenerate(btn) {
        const type = btn.dataset.generateType || 'interview';
        const hasPlan = btn.dataset.hasPlan === 'true';
        openClaudeModal(btn.dataset.generateWeek, hasPlan, type);
        return false;
    };

    // ── New training plan modal (2-step) ─────────────────────────────────

    const npOverlay  = document.getElementById('new-plan-modal-overlay');
    const npStep1    = document.getElementById('np-step-1');
    const npStep2    = document.getElementById('np-step-2');
    const npIndicator = document.getElementById('np-step-indicator');

    function _readIntakeForm() {
        return {
            race_name:              document.getElementById('np-race-name')?.value.trim()     || '',
            race_date:              document.getElementById('np-race-date')?.value.trim()     || '',
            race_miles:             document.getElementById('np-race-distance')?.value.trim() || '',
            race_distance_unit:     document.getElementById('np-race-distance-unit')?.value   || 'miles',
            days_per_week:          document.getElementById('np-days-per-week')?.value        || '4',
            current_weekly_mileage: document.getElementById('np-current-mileage')?.value.trim() || '',
            recent_race_result:     document.getElementById('np-recent-race')?.value.trim()   || '',
            notes:                  document.getElementById('np-notes')?.value.trim()         || '',
        };
    }

    function _showNpStep(num) {
        if (!npStep1 || !npStep2) return;
        npStep1.style.display = num === 1 ? '' : 'none';
        npStep2.style.display = num === 2 ? '' : 'none';
        if (npIndicator) {
            npIndicator.textContent = num === 1
                ? 'Step 1 of 2 — Your details'
                : 'Step 2 of 2 — Claude\'s questions';
        }
    }

    function openNewPlanModal() {
        if (!npOverlay) return;
        _showNpStep(1);
        npOverlay.setAttribute('aria-hidden', 'false');
        npOverlay.classList.add('modal--open');
        setTimeout(() => document.getElementById('np-race-name')?.focus(), 50);
    }

    function closeNewPlanModal() {
        if (!npOverlay) return;
        npOverlay.classList.remove('modal--open');
        npOverlay.setAttribute('aria-hidden', 'true');
    }

    if (npOverlay) {
        npOverlay.addEventListener('click', (e) => { if (e.target === npOverlay) closeNewPlanModal(); });
        document.getElementById('np-cancel')?.addEventListener('click', closeNewPlanModal);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && npOverlay.classList.contains('modal--open')) closeNewPlanModal();
        });

        // Step 1 → Step 2: fetch Claude's questions
        document.getElementById('np-continue')?.addEventListener('click', async () => {
            const continueBtn = document.getElementById('np-continue');
            continueBtn.disabled = true;
            continueBtn.textContent = 'Thinking...';
            try {
                const formData = _readIntakeForm();
                const body = new URLSearchParams(formData);
                const res = await fetch('/running/intake-questions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: body.toString(),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Failed to get questions');
                const block = document.getElementById('np-questions-block');
                if (block) block.textContent = data.questions;
                document.getElementById('np-answers').value = '';
                _showNpStep(2);
                setTimeout(() => document.getElementById('np-answers')?.focus(), 50);
            } catch (e) {
                alert('Error: ' + e.message);
            } finally {
                continueBtn.disabled = false;
                continueBtn.textContent = 'Continue →';
            }
        });

        // Step 2 back button
        document.getElementById('np-back')?.addEventListener('click', () => _showNpStep(1));

        // Step 2 → generate plan
        document.getElementById('np-confirm')?.addEventListener('click', () => {
            const formData = _readIntakeForm();
            const questions = document.getElementById('np-questions-block')?.textContent || '';
            const answers = document.getElementById('np-answers')?.value.trim() || '';
            if (questions) {
                formData.qa_context = `Claude's questions:\n${questions}\n\nAthlete's answers:\n${answers}`;
            }
            closeNewPlanModal();
            startNewPlan(formData);
        });
    }

    window.handleNewPlan = function handleNewPlan() {
        openNewPlanModal();
        return false;
    };

    async function startNewPlan(formData) {
        showSkeleton('running-full');
        localStorage.setItem('claudeGenJob', JSON.stringify({type: 'running-full'}));
        try {
            const body = new URLSearchParams(formData);
            const res = await fetch('/running/generate-full-plan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: body.toString(),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to start plan generation');
            localStorage.setItem('claudeGenJob', JSON.stringify({jobId: data.job_id, type: 'running-full'}));
            pollJob(data.job_id, 'running-full');
        } catch (e) {
            hideSkeleton('running-full');
            localStorage.removeItem('claudeGenJob');
            alert('Error: ' + e.message);
        }
    }

    // ── Skeleton show/hide ────────────────────────────────────────────────

    function showSkeleton(type) {
        if (type === 'running-full' || type === 'running-edit' || type === 'running') {
            const tabBtn = document.querySelector('[data-target="#running"]');
            if (tabBtn && tabBtn.getAttribute('aria-selected') !== 'true') tabBtn.click();
            const content = document.getElementById('running-plan-content');
            if (content) content.style.display = 'none';
            const skel = document.getElementById('running-skeleton');
            if (skel) {
                skel.style.display = 'block';
                const msg = skel.querySelector('.skel-status');
                if (msg) {
                    const text = type === 'running-full'
                        ? 'Claude is building your training plan...'
                        : 'Claude is updating your plan...';
                    msg.innerHTML = `<span class="spinner"></span>${text}`;
                }
            }
        } else {
            const tabBtn = document.querySelector('[data-target="#interview"]');
            if (tabBtn && tabBtn.getAttribute('aria-selected') !== 'true') tabBtn.click();
            const overview = document.querySelector('.interview-overview');
            if (overview) overview.style.display = 'none';
            const weekGrid = document.getElementById('interview-week-grid');
            if (weekGrid) weekGrid.style.display = 'none';
            const skel = document.getElementById('claude-skeleton');
            if (skel) skel.style.display = 'block';
        }
    }

    function hideSkeleton(type) {
        if (type === 'running-full' || type === 'running-edit' || type === 'running') {
            const skel = document.getElementById('running-skeleton');
            if (skel) skel.style.display = 'none';
            const content = document.getElementById('running-plan-content');
            if (content) content.style.display = '';
        } else {
            const skel = document.getElementById('claude-skeleton');
            if (skel) skel.style.display = 'none';
            const overview = document.querySelector('.interview-overview');
            if (overview) overview.style.display = '';
            const weekGrid = document.getElementById('interview-week-grid');
            if (weekGrid) weekGrid.style.display = '';
        }
    }

    // ── Polling ───────────────────────────────────────────────────────────

    function pollJob(jobId, type) {
        let endpoint;
        if (type === 'running-full') {
            endpoint = `/running/generate-full-plan/status?job_id=${jobId}`;
        } else if (type === 'running-edit' || type === 'running') {
            endpoint = `/running/generate-ai/status?job_id=${jobId}`;
        } else {
            endpoint = `/interview/generate-ai/status?job_id=${jobId}`;
        }
        const redirectTab = type.startsWith('running') ? 'running' : 'interview';

        const timer = setInterval(async () => {
            try {
                const r = await fetch(endpoint);
                const data = await r.json();
                if (data.status === 'done') {
                    clearInterval(timer);
                    localStorage.removeItem('claudeGenJob');
                    if (document.getElementById('interview-week-grid') && !type.startsWith('running')) {
                        window.location.reload();
                    } else {
                        window.location.href = `/?tab=${redirectTab}`;
                    }
                } else if (data.status === 'error') {
                    clearInterval(timer);
                    localStorage.removeItem('claudeGenJob');
                    hideSkeleton(type);
                    alert('Claude generation failed: ' + (data.error || 'Unknown error'));
                } else if (data.message && type.startsWith('running')) {
                    const skelMsg = document.querySelector('#running-skeleton .skel-status');
                    if (skelMsg) skelMsg.innerHTML = `<span class="spinner"></span>${data.message}`;
                }
            } catch {
                // Network hiccup — keep polling
            }
        }, 2000);
    }

    // ── Start generation ──────────────────────────────────────────────────

    async function startGenerate(weekLabel, intensity, customPrompt, type) {
        showSkeleton(type);
        localStorage.setItem('claudeGenJob', JSON.stringify({weekLabel, type}));
        let endpoint, bodyParams;
        if (type === 'running-full') {
            endpoint = '/running/generate-full-plan';
            bodyParams = { custom_prompt: customPrompt || '' };
        } else if (type === 'running-edit' || type === 'running') {
            endpoint = '/running/generate-ai';
            bodyParams = { week_num: weekLabel, custom_prompt: customPrompt || '' };
        } else {
            endpoint = '/interview/generate-ai';
            bodyParams = { week_label: weekLabel, intensity: intensity || 'normal', custom_prompt: customPrompt || '' };
        }
        try {
            const body = new URLSearchParams(bodyParams);
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: body.toString(),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to start generation');
            localStorage.setItem('claudeGenJob', JSON.stringify({jobId: data.job_id, weekLabel, type}));
            pollJob(data.job_id, type);
        } catch (e) {
            hideSkeleton(type);
            localStorage.removeItem('claudeGenJob');
            alert('Error: ' + e.message);
        }
    }

    // On page load: resume polling if a job was in-flight when the page was refreshed
    const pendingJobStr = localStorage.getItem('claudeGenJob');
    if (pendingJobStr) {
        try {
            const {jobId, weekLabel, type} = JSON.parse(pendingJobStr);
            const resolvedType = type || 'interview';
            if (jobId) {
                showSkeleton(resolvedType);
                pollJob(jobId, resolvedType);
            } else {
                localStorage.removeItem('claudeGenJob');
            }
        } catch {
            localStorage.removeItem('claudeGenJob');
        }
    }

});
