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

    // ── Running live coach ────────────────────────────────────────────────

    function _setRunningCoachLoading(isLoading, statusMsg) {
        const btn = document.getElementById('running-coach-submit');
        const msg = document.getElementById('running-coach-message');
        const statusEl = document.getElementById('running-coach-status');
        if (isLoading) {
            if (btn) { btn.disabled = true; btn.textContent = 'Thinking…'; }
            if (msg) msg.disabled = true;
            if (statusEl) { statusEl.innerHTML = `<span class="spinner"></span>${statusMsg || 'Claude is adjusting your plan…'}`; statusEl.style.display = 'flex'; }
        } else {
            if (btn) { btn.disabled = false; btn.textContent = '✦ Ask coach'; }
            if (msg) msg.disabled = false;
            if (statusEl) statusEl.style.display = 'none';
        }
    }

    window.submitRunningCoach = async function submitRunningCoach() {
        const msg = document.getElementById('running-coach-message')?.value.trim();
        if (!msg) return;
        _setRunningCoachLoading(true);
        try {
            const res = await fetch('/running/coach', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ message: msg }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed');
            localStorage.setItem('runningCoachJob', data.job_id);
            _pollRunningCoach(data.job_id);
        } catch (e) {
            alert('Error: ' + e.message);
            _setRunningCoachLoading(false);
        }
    };

    function _pollRunningCoach(jobId) {
        const timer = setInterval(async () => {
            try {
                const r = await fetch(`/running/coach/status?job_id=${jobId}`);
                const data = await r.json();
                if (data.status === 'done') {
                    clearInterval(timer);
                    localStorage.removeItem('runningCoachJob');
                    if (data.message) localStorage.setItem('runningCoachFeedback', data.message);
                    window.location.href = '/?tab=running';
                } else if (data.status === 'error') {
                    clearInterval(timer);
                    localStorage.removeItem('runningCoachJob');
                    _setRunningCoachLoading(false);
                    alert('Coach error: ' + (data.error || 'Unknown error'));
                } else if (data.message) {
                    _setRunningCoachLoading(true, data.message);
                }
            } catch { /* network hiccup */ }
        }, 1500);
    }

    // Resume poll if page was refreshed mid-coach
    const _pendingCoachJob = localStorage.getItem('runningCoachJob');
    if (_pendingCoachJob) {
        _setRunningCoachLoading(true);
        _pollRunningCoach(_pendingCoachJob);
    }
    // Show feedback banner after redirect
    const _coachFeedback = localStorage.getItem('runningCoachFeedback');
    if (_coachFeedback) {
        localStorage.removeItem('runningCoachFeedback');
        const banner = document.getElementById('running-coach-feedback-banner');
        if (banner) { banner.textContent = _coachFeedback; banner.style.display = 'block'; }
    }

    // ── Running compliance badge ──────────────────────────────────────────

    let _complianceSummary = '';

    async function fetchRunningCompliance() {
        const badge = document.getElementById('running-compliance-badge');
        if (!badge) return;
        try {
            const r = await fetch('/running/week-compliance');
            if (!r.ok) return;
            const data = await r.json();
            if (!data.has_data) return;
            const gaps = (data.missed_runs || []).length + (data.short_runs || []).length;
            if (gaps === 0) return;
            const missedCount = (data.missed_runs || []).length;
            const shortCount = (data.short_runs || []).length;
            const parts = [];
            if (missedCount) parts.push(`${missedCount} run${missedCount > 1 ? 's' : ''} missed`);
            if (shortCount) parts.push(`${shortCount} run${shortCount > 1 ? 's' : ''} cut short`);
            badge.textContent = `⚠ ${parts.join(', ')} this week — click ✦ Edit with Claude to adjust`;
            badge.style.display = 'block';
            _complianceSummary = data.summary_text || '';
        } catch {
            // silently ignore — compliance is best-effort
        }
    }

    fetchRunningCompliance();

    // ── Days until race countdown (dynamic from active plan) ─────────────
    const raceCountdownEl = document.getElementById('race-countdown-days');
    if (raceCountdownEl && window.RACE_DATE) {
        const raceDays = Math.ceil((new Date(window.RACE_DATE) - new Date()) / (1000 * 60 * 60 * 24));
        raceCountdownEl.textContent = Math.max(0, raceDays).toLocaleString();
    }

    // ── Running day detail modal ──────────────────────────────────────────

    (function initDayDetail() {
        const overlay = document.getElementById('day-detail-modal-overlay');
        const title = document.getElementById('day-detail-modal-title');
        const body = document.getElementById('day-detail-modal-body');
        const closeBtn = document.getElementById('day-detail-modal-close');
        if (!overlay || !body) return;

        function addRow(label, value) {
            if (!value) return;
            const row = document.createElement('div');
            row.style.marginBottom = '.75rem';
            const lbl = document.createElement('div');
            lbl.className = 'modal__label';
            lbl.textContent = label;
            const val = document.createElement('div');
            val.style.fontSize = '.9rem';
            val.textContent = value;
            row.appendChild(lbl);
            row.appendChild(val);
            body.appendChild(row);
        }

        function renderDayDetail(data) {
            body.innerHTML = '';
            if (title) title.textContent = `${data.day_name}, ${data.date}`;

            const typeLabel = data.type ? data.type.charAt(0).toUpperCase() + data.type.slice(1) : 'Rest';
            addRow('Planned', data.distance_miles ? `${typeLabel} — ${data.distance_miles} mi` : typeLabel);
            addRow('Coach notes', data.notes);
            addRow('Post-run notes', data.notes_actual);

            if (data.actual) {
                const mins = Math.floor(data.actual.moving_time_s / 60);
                const secs = Math.round(data.actual.moving_time_s % 60);
                const timeStr = data.actual.moving_time_s ? ` (${mins}:${String(secs).padStart(2, '0')})` : '';
                addRow('Actual', `${data.actual.distance_miles} mi @ ${data.actual.pace_per_mile}/mi${timeStr}`);
            } else if (new Date(data.date + 'T00:00:00') < new Date(new Date().toDateString())) {
                addRow('Actual', 'No run logged');
            }

            if (data.feedback) addRow("Coach's note", data.feedback);

            if (!body.children.length) {
                const empty = document.createElement('p');
                empty.className = 'muted';
                empty.textContent = 'Nothing planned for this day.';
                body.appendChild(empty);
            }
        }

        function openDayDetail(dateStr) {
            overlay.setAttribute('aria-hidden', 'false');
            overlay.classList.add('modal--open');
            body.innerHTML = '<p class="muted">Loading…</p>';
            fetch(`/running/day-detail/${dateStr}`)
                .then((res) => res.json().then((data) => ({ ok: res.ok, data })))
                .then(({ ok, data }) => {
                    if (!ok) throw new Error(data.error || 'Failed to load');
                    renderDayDetail(data);
                })
                .catch(() => {
                    body.innerHTML = '';
                    const err = document.createElement('p');
                    err.className = 'muted';
                    err.textContent = 'Could not load day detail.';
                    body.appendChild(err);
                });
        }

        function closeDayDetail() {
            overlay.classList.remove('modal--open');
            overlay.setAttribute('aria-hidden', 'true');
        }

        document.querySelectorAll('.day-pill-hero[data-date], .day-pill[data-date]').forEach((el) => {
            el.addEventListener('click', () => openDayDetail(el.dataset.date));
        });

        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeDayDetail(); });
        closeBtn?.addEventListener('click', closeDayDetail);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && overlay.classList.contains('modal--open')) closeDayDetail();
        });
    })();

    // ── Claude generation modal ───────────────────────────────────────────

    const overlay    = document.getElementById('claude-modal-overlay');
    const modalTitle = document.getElementById('claude-modal-title');
    const warning    = document.getElementById('claude-modal-warning');
    const textarea   = document.getElementById('claude-custom-prompt');
    const cancelBtn  = document.getElementById('claude-modal-cancel');
    const confirmBtn = document.getElementById('claude-modal-confirm');
    const intensityBtns = overlay ? overlay.querySelectorAll('.intensity-btn') : [];

    let _pendingWeekLabel = null;
    let _pendingType = 'running-edit';

    const _modalConfig = {
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
        _pendingType = type || 'running-edit';
        const cfg = _modalConfig[_pendingType] || _modalConfig['running-edit'];
        if (modalTitle) modalTitle.textContent = cfg.title;
        if (warning) {
            warning.textContent = cfg.warning;
            warning.style.display = hasPlan ? 'block' : 'none';
        }
        if (intensitySection) intensitySection.style.display = cfg.showIntensity ? '' : 'none';
        if (textarea) textarea.placeholder = cfg.placeholder || '';
        textarea.value = (_pendingType === 'running-edit' && _complianceSummary) ? _complianceSummary : '';
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
        const type = btn.dataset.generateType || 'running-edit';
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
            goal_time:              document.getElementById('np-goal-time')?.value.trim()     || '',
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
            const formData = _readIntakeForm();

            // Validate: distance required when race name or date is provided
            if ((formData.race_name || formData.race_date) && !formData.race_miles) {
                const distInput = document.getElementById('np-race-distance');
                if (distInput) { distInput.focus(); distInput.style.outline = '2px solid var(--danger)'; }
                alert('Please enter the race distance — it\'s needed to build your long run progression correctly.');
                return;
            }
            if (document.getElementById('np-race-distance')) {
                document.getElementById('np-race-distance').style.outline = '';
            }

            continueBtn.disabled = true;
            continueBtn.textContent = 'Thinking...';
            try {
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
    }

    function hideSkeleton() {
        const skel = document.getElementById('running-skeleton');
        if (skel) skel.style.display = 'none';
        const content = document.getElementById('running-plan-content');
        if (content) content.style.display = '';
    }

    // ── Polling ───────────────────────────────────────────────────────────

    function pollJob(jobId, type) {
        const endpoint = type === 'running-full'
            ? `/running/generate-full-plan/status?job_id=${jobId}`
            : `/running/generate-ai/status?job_id=${jobId}`;

        const timer = setInterval(async () => {
            try {
                const r = await fetch(endpoint);
                const data = await r.json();
                if (data.status === 'done') {
                    clearInterval(timer);
                    localStorage.removeItem('claudeGenJob');
                    window.location.href = '/?tab=running';
                } else if (data.status === 'error') {
                    clearInterval(timer);
                    localStorage.removeItem('claudeGenJob');
                    hideSkeleton();
                    alert('Claude generation failed: ' + (data.error || 'Unknown error'));
                } else if (data.message) {
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
        } else {
            endpoint = '/running/generate-ai';
            bodyParams = { week_num: weekLabel, custom_prompt: customPrompt || '' };
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
            const resolvedType = type || 'running-edit';
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

    // ── Learning/projects: backfill form (log time for a past day) ────────

    (function initBackfillForm() {
        const categorySelect = document.getElementById('backfill-category');
        const itemSelect = document.getElementById('backfill-item');
        if (!categorySelect || !itemSelect) return;

        function populateItems() {
            const category = categorySelect.value;
            const items = (window.LEARNING_ITEMS_BY_CATEGORY || {})[category] || [];
            itemSelect.innerHTML = '';
            if (category === 'system_design') {
                itemSelect.style.display = 'none';
                itemSelect.required = false;
                return;
            }
            itemSelect.style.display = '';
            itemSelect.required = true;
            if (!items.length) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'No items yet';
                itemSelect.appendChild(opt);
                return;
            }
            items.forEach((item) => {
                const opt = document.createElement('option');
                opt.value = item.id;
                opt.textContent = item.title + (item.status === 'complete' ? ' (completed)' : '');
                itemSelect.appendChild(opt);
            });
        }

        categorySelect.addEventListener('change', populateItems);
        populateItems();
    })();

    // ── Learning/projects: log-time buttons ───────────────────────────────

    document.querySelectorAll('.log-time-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
            const category = btn.dataset.category;
            const itemId = btn.dataset.itemId || null;
            const minutes = parseInt(btn.dataset.minutes, 10);
            btn.disabled = true;
            try {
                const res = await fetch('/learning/log-time', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({category, item_id: itemId, minutes}),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Failed to log time');
                const totalEl = itemId
                    ? document.querySelector(`[data-today-total][data-item-id="${itemId}"]`)
                    : document.querySelector(`[data-today-total][data-category="${category}"]`);
                if (totalEl) totalEl.textContent = `${data.total_minutes}m today`;
            } catch (e) {
                alert('Error: ' + e.message);
            } finally {
                btn.disabled = false;
            }
        });
    });

    // ── Learning/projects: LeetCode today refresh ─────────────────────────

    document.getElementById('leetcode-refresh-btn')?.addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        const listEl = document.getElementById('leetcode-today-list');
        btn.disabled = true;
        try {
            const res = await fetch('/learning/leetcode-today');
            const data = await res.json();
            if (!listEl) return;
            if (data.problems && data.problems.length) {
                listEl.innerHTML = '<ul class="leetcode-list"></ul>';
                const ul = listEl.querySelector('ul');
                data.problems.forEach((p) => {
                    const li = document.createElement('li');
                    li.textContent = p.title;
                    ul.appendChild(li);
                });
            } else {
                listEl.innerHTML = '<p class="muted" style="font-size:.85rem;">Nothing solved yet today.</p>';
            }
        } catch {
            // best-effort — leave existing content in place
        } finally {
            btn.disabled = false;
        }
    });

    // ── Learning/projects: analytics ───────────────────────────────────────

    const ANALYTICS_CATEGORIES = [
        { key: 'books', label: 'Books', color: 'var(--iprep-series-1)' },
        { key: 'projects', label: 'Projects', color: 'var(--iprep-series-2)' },
        { key: 'wildcard', label: 'Wildcard', color: 'var(--iprep-series-3)' },
        { key: 'system_design', label: 'System Design', color: 'var(--iprep-series-4)' },
    ];

    const SVG_NS = 'http://www.w3.org/2000/svg';

    function _svgEl(tag, attrs) {
        const el = document.createElementNS(SVG_NS, tag);
        Object.keys(attrs || {}).forEach((k) => el.setAttribute(k, attrs[k]));
        return el;
    }

    function _ensureTooltip() {
        let tip = document.getElementById('analytics-tooltip');
        if (!tip) {
            tip = document.createElement('div');
            tip.id = 'analytics-tooltip';
            tip.className = 'analytics-tooltip';
            tip.style.display = 'none';
            document.body.appendChild(tip);
        }
        return tip;
    }

    function _showTooltip(evt, text) {
        const tip = _ensureTooltip();
        tip.textContent = text;
        tip.style.display = 'block';
        tip.style.left = `${evt.clientX + 12}px`;
        tip.style.top = `${evt.clientY + 12}px`;
    }

    function _hideTooltip() {
        const tip = document.getElementById('analytics-tooltip');
        if (tip) tip.style.display = 'none';
    }

    function _dateRange(start, end) {
        const dates = [];
        let d = new Date(start + 'T00:00:00');
        const endD = new Date(end + 'T00:00:00');
        while (d <= endD) {
            dates.push(d.toISOString().slice(0, 10));
            d.setDate(d.getDate() + 1);
        }
        return dates;
    }

    function _renderStackedBarChart(container, dates, byDay) {
        container.innerHTML = '';
        const width = Math.max(container.clientWidth || 600, 300);
        const height = 220;
        const barGap = 4;
        const barW = Math.max((width / dates.length) - barGap, 4);

        let maxTotal = 1;
        dates.forEach((d) => {
            const dayTotals = byDay[d] || {};
            const total = ANALYTICS_CATEGORIES.reduce((sum, c) => sum + (dayTotals[c.key] || 0), 0);
            if (total > maxTotal) maxTotal = total;
        });

        const svg = _svgEl('svg', { width: '100%', height, viewBox: `0 0 ${width} ${height}`, class: 'analytics-svg' });

        // Gridlines at 0, 1/2, and max
        [0, 0.5, 1].forEach((frac) => {
            const y = height - 24 - frac * (height - 40);
            const line = _svgEl('line', { x1: 0, y1: y, x2: width, y2: y, class: 'analytics-gridline' });
            svg.appendChild(line);
        });

        dates.forEach((d, i) => {
            const dayTotals = byDay[d] || {};
            const x = i * (barW + barGap);
            let cursorY = height - 24;
            ANALYTICS_CATEGORIES.forEach((c) => {
                const minutes = dayTotals[c.key] || 0;
                if (minutes <= 0) return;
                const barH = (minutes / maxTotal) * (height - 40);
                const rect = _svgEl('rect', {
                    x, y: cursorY - barH, width: barW, height: Math.max(barH - 2, 0),
                    fill: c.color, rx: 2,
                });
                rect.addEventListener('pointerenter', (e) => _showTooltip(e, `${c.label}: ${minutes}m on ${d}`));
                rect.addEventListener('pointermove', (e) => _showTooltip(e, `${c.label}: ${minutes}m on ${d}`));
                rect.addEventListener('pointerleave', _hideTooltip);
                svg.appendChild(rect);
                cursorY -= barH;
            });
        });

        container.appendChild(svg);

        // Legend
        const legend = document.createElement('div');
        legend.className = 'analytics-legend';
        ANALYTICS_CATEGORIES.forEach((c) => {
            const item = document.createElement('span');
            item.className = 'analytics-legend__item';
            const swatch = document.createElement('span');
            swatch.className = 'analytics-legend__swatch';
            swatch.style.background = c.color;
            item.appendChild(swatch);
            item.appendChild(document.createTextNode(c.label));
            legend.appendChild(item);
        });
        container.appendChild(legend);
    }

    function _renderLeetcodeChart(container, dates, leetcodeDaily) {
        container.innerHTML = '';
        const width = Math.max(container.clientWidth || 600, 300);
        const height = 140;
        const barGap = 4;
        const barW = Math.max((width / dates.length) - barGap, 4);
        const maxCount = Math.max(1, ...dates.map((d) => leetcodeDaily[d] || 0));

        const svg = _svgEl('svg', { width: '100%', height, viewBox: `0 0 ${width} ${height}`, class: 'analytics-svg' });
        dates.forEach((d, i) => {
            const count = leetcodeDaily[d] || 0;
            if (count <= 0) return;
            const x = i * (barW + barGap);
            const barH = (count / maxCount) * (height - 24);
            const rect = _svgEl('rect', {
                x, y: height - 12 - barH, width: barW, height: barH,
                fill: 'var(--success)', rx: 2,
            });
            rect.addEventListener('pointerenter', (e) => _showTooltip(e, `${count} solved on ${d}`));
            rect.addEventListener('pointermove', (e) => _showTooltip(e, `${count} solved on ${d}`));
            rect.addEventListener('pointerleave', _hideTooltip);
            svg.appendChild(rect);
        });
        container.appendChild(svg);
    }

    function _renderAnalyticsTable(container, dates, byDay, leetcodeDaily) {
        container.innerHTML = '';
        const table = document.createElement('table');
        table.className = 'analytics-table';
        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        ['Date', ...ANALYTICS_CATEGORIES.map((c) => c.label), 'LeetCode'].forEach((label) => {
            const th = document.createElement('th');
            th.textContent = label;
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        dates.forEach((d) => {
            const row = document.createElement('tr');
            const dayTotals = byDay[d] || {};
            [d, ...ANALYTICS_CATEGORIES.map((c) => `${dayTotals[c.key] || 0}m`), `${leetcodeDaily[d] || 0}`].forEach((val) => {
                const td = document.createElement('td');
                td.textContent = val;
                row.appendChild(td);
            });
            tbody.appendChild(row);
        });
        table.appendChild(tbody);
        container.appendChild(table);
    }

    async function _loadAnalytics(days) {
        const chartContainer = document.getElementById('analytics-chart-container');
        const lcContainer = document.getElementById('analytics-leetcode-container');
        const tableContainer = document.getElementById('analytics-table-container');
        if (!chartContainer) return;
        try {
            const res = await fetch(`/learning/analytics?days=${days}`);
            const data = await res.json();
            const dates = _dateRange(data.start, data.end);
            _renderStackedBarChart(chartContainer, dates, data.category_totals_by_day || {});
            if (lcContainer) _renderLeetcodeChart(lcContainer, dates, data.leetcode_daily || {});
            if (tableContainer) _renderAnalyticsTable(tableContainer, dates, data.category_totals_by_day || {}, data.leetcode_daily || {});
        } catch {
            chartContainer.textContent = 'Failed to load analytics.';
        }
    }

    function initAnalytics() {
        const rangeButtons = document.querySelectorAll('.analytics-range-btn');
        rangeButtons.forEach((btn) => {
            btn.addEventListener('click', () => {
                rangeButtons.forEach((b) => b.classList.remove('analytics-range-btn--active'));
                btn.classList.add('analytics-range-btn--active');
                _loadAnalytics(parseInt(btn.dataset.days, 10));
            });
        });
        _loadAnalytics(7);
    }

    const analyticsChartContainer = document.getElementById('analytics-chart-container');
    if (analyticsChartContainer) {
        initAnalytics();
    }

    // ── Kindle preview: click-to-tap + live mirror of the physical device ──
    const kindleScreen = document.getElementById('kindle-screen');
    if (kindleScreen) {
        const kindleImg = document.getElementById('kindle-preview-img');
        const kindleStatus = document.getElementById('kindle-preview-status');
        const tapUrl = kindleScreen.dataset.tapUrl;
        const imageUrl = kindleScreen.dataset.imageUrl;
        const nativeWidth = parseInt(kindleScreen.dataset.width, 10) || 758;
        const nativeHeight = parseInt(kindleScreen.dataset.height, 10) || 1024;
        let kindleBusy = false;

        function setKindleStatus(msg) {
            if (kindleStatus) kindleStatus.textContent = msg || '';
        }

        function reloadKindleImage() {
            kindleImg.src = `${imageUrl}?t=${Date.now()}`;
        }

        async function sendKindleTap(x, y) {
            if (kindleBusy) return;
            kindleBusy = true;
            kindleScreen.classList.add('is-tapping');
            setKindleStatus('Tapping…');
            try {
                const res = await fetch(`${tapUrl}?x=${x}&y=${y}`);
                const text = (await res.text()).trim();
                setKindleStatus(text);
            } catch (err) {
                setKindleStatus('Tap failed — is the app running?');
            } finally {
                reloadKindleImage();
                kindleScreen.classList.remove('is-tapping');
                kindleBusy = false;
            }
        }

        kindleScreen.addEventListener('click', (e) => {
            const rect = kindleImg.getBoundingClientRect();
            const relX = (e.clientX - rect.left) / rect.width;
            const relY = (e.clientY - rect.top) / rect.height;
            if (relX < 0 || relX > 1 || relY < 0 || relY > 1) return;
            const x = Math.round(relX * nativeWidth);
            const y = Math.round(relY * nativeHeight);
            sendKindleTap(x, y);
        });

        // The physical Kindle re-renders on its own (30-min scheduler, taps,
        // Strava webhooks); poll gently so the preview stays roughly in sync
        // without forcing a re-render itself.
        setInterval(() => {
            const kindleTab = document.getElementById('kindle');
            if (!kindleBusy && kindleTab && kindleTab.getAttribute('aria-hidden') === 'false') {
                reloadKindleImage();
            }
        }, 20000);
    }

});
