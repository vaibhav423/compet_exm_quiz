class QuizDataManager {
    constructor() {
        this.questionsCache = new Map();
        this.apiBaseUrl = '/api';
    }

    async apiRequest(endpoint) {
        try {
            const response = await fetch(`${this.apiBaseUrl}${endpoint}`);
            
            if (!response.ok) {
                throw new Error(`API request failed: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.status !== 'success') {
                throw new Error(data.message || 'API request returned error status');
            }
            
            return data;
        } catch (error) {
            console.error(`API request error for ${endpoint}:`, error);
            throw error;
        }
    }

    async getSubjects() {
        try {
            const data = await this.apiRequest('/subjects');
            return data.subjects || [];
        } catch (error) {
            console.error('Error fetching subjects:', error);
            return [];
        }
    }

    async getDivisions(subject) {
        if (!subject) return [];
        
        try {
            const data = await this.apiRequest(`/subjects/${encodeURIComponent(subject)}/divisions`);
            return data.divisions || [];
        } catch (error) {
            console.error(`Error fetching divisions for ${subject}:`, error);
            return [];
        }
    }

    async getChapters(subject, division) {
        if (!subject || !division) return [];
        
        try {
            const data = await this.apiRequest(`/subjects/${encodeURIComponent(subject)}/${encodeURIComponent(division)}/chapters`);
            return data.chapters || [];
        } catch (error) {
            console.error(`Error fetching chapters for ${subject}/${division}:`, error);
            return [];
        }
    }

    async loadFilteredQuestions(filters) {
        const { subject, division, chapter } = filters;
        
        const params = new URLSearchParams();
        if (subject) params.append('subject', subject);
        if (division) params.append('division', division);
        if (chapter) params.append('chapter', chapter);
        
        const cacheKey = `questions:${params.toString()}`;
        
        if (this.questionsCache.has(cacheKey)) {
            return this.questionsCache.get(cacheKey);
        }

        try {
            const data = await this.apiRequest(`/questions?${params.toString()}`);
            const questions = data.questions || [];
            
            this.questionsCache.set(cacheKey, questions);
            return questions;
        } catch (error) {
            console.error('Error loading filtered questions:', error);
            return [];
        }
    }
}

class StateManager {
    constructor() {
        this.stateFile = '/quiz-state.json';
        this.state = {
            attemptedQuestions: {},
            currentFilter: {},
            currentQuestionIndex: 0,
            markedForReview: new Set(),
            lastUpdated: new Date().toISOString()
        };
    }

    async loadState() {
        try {
            const response = await fetch(this.stateFile);
            if (response.ok) {
                const loadedState = await response.json();
                this.state = {
                    ...this.state,
                    ...loadedState,
                    markedForReview: new Set(loadedState.markedForReview || [])
                };
                console.log('State loaded from file');
            }
        } catch (error) {
            console.log('No existing state file found, using defaults');
        }
    }

    async saveState() {
        try {
            const stateToSave = {
                ...this.state,
                markedForReview: Array.from(this.state.markedForReview),
                lastUpdated: new Date().toISOString()
            };

            await fetch('/api/state', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(stateToSave)
            });

            console.log('State saved to server (quiz-state.json)');
            return true;
        } catch (error) {
            console.error('Error saving state to server:', error);
            return false;
        }
    }

    async loadStateFromFile(file) {
        try {
            const text = await file.text();
            const loadedState = JSON.parse(text);
            this.state = {
                ...this.state,
                ...loadedState,
                markedForReview: new Set(loadedState.markedForReview || [])
            };
            console.log('State loaded from uploaded file');
            return true;
        } catch (error) {
            console.error('Error loading state from file:', error);
            return false;
        }
    }

    recordAttempt(questionId, selectedOption, isCorrect) {
        this.state.attemptedQuestions[questionId] = {
            attempted: true,
            selectedOption,
            correct: isCorrect,
            timestamp: new Date().toISOString()
        };
        this.saveState().catch(err => console.error('Autosave failed:', err));
    }

    isAttempted(questionId) {
        return this.state.attemptedQuestions[questionId]?.attempted || false;
    }

    getAttemptResult(questionId) {
        return this.state.attemptedQuestions[questionId];
    }

    markForReview(questionId) {
        this.state.markedForReview.add(questionId);
        this.saveState().catch(err => console.error('Autosave failed:', err));
    }

    unmarkForReview(questionId) {
        this.state.markedForReview.delete(questionId);
        this.saveState().catch(err => console.error('Autosave failed:', err));
    }

    isMarkedForReview(questionId) {
        return this.state.markedForReview.has(questionId);
    }

    setCurrentFilter(filter) {
        this.state.currentFilter = filter;
        this.saveState().catch(err => console.error('Autosave failed:', err));
    }

    getCurrentFilter() {
        return this.state.currentFilter;
    }

    setCurrentQuestionIndex(index) {
        this.state.currentQuestionIndex = index;
        this.saveState().catch(err => console.error('Autosave failed:', err));
    }

    getCurrentQuestionIndex() {
        return this.state.currentQuestionIndex;
    }

    getProgress(totalQuestions) {
        const attempted = Object.keys(this.state.attemptedQuestions).length;
        const correct = Object.values(this.state.attemptedQuestions)
            .filter(attempt => attempt.correct).length;
        
        return {
            total: totalQuestions,
            attempted,
            correct,
            percentage: totalQuestions > 0 ? (attempted / totalQuestions * 100) : 0
        };
    }
}

class FilterManager {
    constructor(dataManager, onFilterChange) {
        this.dataManager = dataManager;
        this.onFilterChange = onFilterChange;
        this.currentFilter = {};
        
        this.initializeElements();
        this.setupEventListeners();
        this.populateSubjectsPromise = this.populateSubjects();
    }

    initializeElements() {
        this.subjectFilter = document.getElementById('subject-filter');
        this.divisionFilter = document.getElementById('division-filter');
        this.chapterFilter = document.getElementById('chapter-filter');
        this.applyFilterBtn = document.getElementById('apply-filter-btn');
        this.resetFilterBtn = document.getElementById('reset-filter-btn');
    }

    setupEventListeners() {
        this.subjectFilter.addEventListener('change', () => this.onSubjectChange());
        this.divisionFilter.addEventListener('change', () => this.onDivisionChange());
        this.applyFilterBtn.addEventListener('click', () => this.applyFilter());
        this.resetFilterBtn.addEventListener('click', () => this.resetFilter());
    }

    async populateSubjects() {
        const subjects = await this.dataManager.getSubjects();
        this.subjectFilter.innerHTML = '<option value="">All Subjects</option>';
        
        subjects.forEach(subject => {
            const option = document.createElement('option');
            option.value = subject;
            option.textContent = subject.charAt(0).toUpperCase() + subject.slice(1);
            this.subjectFilter.appendChild(option);
        });
    }

    async onSubjectChange() {
        const selectedSubject = this.subjectFilter.value;
        await this.populateDivisions(selectedSubject);
        await this.populateChapters('', '');
    }

    async onDivisionChange() {
        const selectedSubject = this.subjectFilter.value;
        const selectedDivision = this.divisionFilter.value;
        await this.populateChapters(selectedSubject, selectedDivision);
    }

    async populateDivisions(subject) {
        const divisions = await this.dataManager.getDivisions(subject);
        this.divisionFilter.innerHTML = '<option value="">All Divisions</option>';
        
        if (subject) {
            divisions.forEach(division => {
                const option = document.createElement('option');
                option.value = division;
                option.textContent = division.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase());
                this.divisionFilter.appendChild(option);
            });
        }
    }

    async populateChapters(subject, division) {
        const chapters = await this.dataManager.getChapters(subject, division);
        this.chapterFilter.innerHTML = '<option value="">All Chapters</option>';
        
        if (subject && division) {
            chapters.forEach(chapter => {
                const option = document.createElement('option');
                option.value = chapter;
                option.textContent = chapter.replace('.json', '').replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase());
                this.chapterFilter.appendChild(option);
            });
        }
    }

    applyFilter() {
        this.currentFilter = {
            subject: this.subjectFilter.value,
            division: this.divisionFilter.value,
            chapter: this.chapterFilter.value
        };
        
        this.onFilterChange(this.currentFilter);
    }

    resetFilter() {
        this.subjectFilter.value = '';
        this.divisionFilter.value = '';
        this.chapterFilter.value = '';
        this.populateDivisions('');
        this.populateChapters('', '');
        
        this.currentFilter = {};
        this.onFilterChange(this.currentFilter);
    }

    async setFilter(filter) {
        if (this.populateSubjectsPromise) {
            await this.populateSubjectsPromise;
        }
        
        this.subjectFilter.value = filter.subject || '';
        await this.onSubjectChange();
        
        this.divisionFilter.value = filter.division || '';
        await this.onDivisionChange();
        
        let chapterVal = filter.chapter || '';
        if (chapterVal && !chapterVal.endsWith('.json')) {
            chapterVal = `${chapterVal}.json`;
        }
        this.chapterFilter.value = chapterVal;
        
        this.currentFilter = {
            subject: this.subjectFilter.value,
            division: this.divisionFilter.value,
            chapter: this.chapterFilter.value
        };
    }

    getCurrentFilter() {
        return this.currentFilter;
    }
}

class EnhancedQuizApp {
    constructor() {
        this.dataManager = new QuizDataManager();
        this.stateManager = new StateManager();
        this.questions = [];
        this.currentQuestionIndex = 0;
        this.selectedOption = null;
        this.isAnswered = false;
        this.zenMode = false;
        
        this.initializeElements();
        this.setupEventListeners();
    }

    async init() {
        await this.stateManager.loadState();

        this.initializeManagers();
        await this.loadInitialState();

        try {
            const pref = localStorage.getItem('quiz_night_mode');
            if (pref === '1') {
                document.body.classList.add('night-mode');
            } else {
                document.body.classList.remove('night-mode');
            }
        } catch (e) {
        }
    }

    initializeElements() {
        this.progressText = document.getElementById('progress-text');
        this.progressFill = document.getElementById('progress-fill');
        
        this.quizContainer = document.getElementById('quiz-container');
        this.noQuiz = document.getElementById('no-quiz');
        
        this.prevBtn = document.getElementById('prev-question');
        this.nextBtn = document.getElementById('next-question');
        this.questionCounter = document.getElementById('question-counter');
        
        this.comprehensionContent = document.getElementById('comprehension-content');
        this.directionContent = document.getElementById('direction-content');
        this.questionContent = document.getElementById('question-content');
        this.optionsContainer = document.getElementById('options-container');
        
        this.submitBtn = document.getElementById('submit-btn');
        this.showExplanationBtn = document.getElementById('show-explanation-btn');
        this.markReviewBtn = document.getElementById('mark-for-review');
        
        this.result = document.getElementById('result');
        this.explanation = document.getElementById('explanation');
        
        this.questionOverview = document.getElementById('question-overview');
        this.questionGrid = document.getElementById('question-grid');

        this.filterToggle = document.getElementById('filter-toggle');
        this.filterSection = document.querySelector('.filter-section');
    }

    setupEventListeners() {
        this.prevBtn.addEventListener('click', () => this.previousQuestion());
        this.nextBtn.addEventListener('click', () => this.nextQuestion());
        
        this.submitBtn.addEventListener('click', () => this.submitAnswer());
        this.markReviewBtn.addEventListener('click', () => this.toggleReviewMark());
        
        if (this.filterToggle && this.filterSection) {
            this.filterToggle.addEventListener('click', () => {
                const isOpen = this.filterSection.classList.toggle('open');
                this.filterToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            });
        }
        
        document.addEventListener('keydown', (e) => {
            const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
            if (tag === 'input' || tag === 'textarea' || tag === 'select' || (e.target && e.target.isContentEditable)) {
                return;
            }

            if (e.ctrlKey && e.shiftKey && (e.key === 'Z' || e.key === 'z' || e.code === 'KeyZ')) {
                e.preventDefault();
                this.toggleZenMode();
                return;
            }

            if (e.ctrlKey && !e.shiftKey && (e.key === 'z' || e.key === 'Z' || e.code === 'KeyZ')) {
                e.preventDefault();
                this.toggleNightMode();
                return;
            }
        }, { passive: false });
        
    }

    initializeManagers() {
        this.filterManager = new FilterManager(
            this.dataManager,
            (filter) => this.onFilterChange(filter)
        );
    }

    async loadInitialState() {
        let filterToApply = null;
        try {
            console.debug('URL flags at init:', {
                urlFilters: window.urlFilters,
                urlZen: window.urlZen,
                urlNext: window.urlNext
            });
        } catch (e) {
        }
        
        if (window.urlFilters && Object.keys(window.urlFilters).length > 0) {
            filterToApply = window.urlFilters;
            console.log('Applying URL-based filters:', filterToApply);
            
            await this.filterManager.setFilter(filterToApply);
            
            await this.onFilterChange(filterToApply);

            if (window.urlZen) {
                try {
                    this.toggleZenMode();
                } catch (e) {
                    console.warn('Failed to apply URL Zen mode:', e);
                }
            }

            if (window.urlNext) {
                try {
                    await this.jumpToNextUnattempted();
                } catch (e) {
                    console.warn('Failed to jump to next unattempted question:', e);
                }
            }
        } else {
            const savedFilter = this.stateManager.getCurrentFilter();
            if (savedFilter && Object.keys(savedFilter).length > 0) {
                filterToApply = savedFilter;
                console.log('Applying saved filters:', filterToApply);
                
                await this.filterManager.setFilter(filterToApply);
                await this.onFilterChange(filterToApply);
                
                const savedIndex = this.stateManager.getCurrentQuestionIndex();
                if (savedIndex < this.questions.length) {
                    this.currentQuestionIndex = savedIndex;
                    this.loadCurrentQuestion();
                }

                if (window.urlZen) {
                    try {
                        this.toggleZenMode();
                    } catch (e) {
                        console.warn('Failed to apply URL Zen mode:', e);
                    }
                }

                if (window.urlNext) {
                    try {
                        await this.jumpToNextUnattempted();
                    } catch (e) {
                        console.warn('Failed to jump to next unattempted question:', e);
                    }
                }
            } else {
                if (window.urlZen) {
                    try {
                        this.toggleZenMode();
                    } catch (e) {
                        console.warn('Failed to apply URL Zen mode:', e);
                    }
                }

                if (window.urlNext) {
                    try {
                        await this.jumpToNextUnattempted();
                    } catch (e) {
                        console.warn('Failed to jump to next unattempted question:', e);
                    }
                }
            }
        }
    }

    async onFilterChange(filter) {
        try {
            this.showLoading(true);
            this.questions = await this.dataManager.loadFilteredQuestions(filter);
            this.stateManager.setCurrentFilter(filter);
            
            if (this.questions.length > 0) {
                this.currentQuestionIndex = 0;
                this.loadQuestions();
                this.updateQuestionOverview();
            } else {
                this.showNoQuiz();
            }
            
            this.updateProgress();
        } catch (error) {
            console.error('Error loading questions:', error);
            this.showNoQuiz();
        } finally {
            this.showLoading(false);
        }
    }

    loadQuestions() {
        if (this.questions.length === 0) {
            this.showNoQuiz();
            return;
        }
        
        this.loadCurrentQuestion();
        this.showQuizContainer();
    }

    loadCurrentQuestion() {
        if (this.currentQuestionIndex >= this.questions.length) {
            this.currentQuestionIndex = 0;
        }
        
        try {
            const qtest = this.questions[this.currentQuestionIndex];
            console.debug('loadCurrentQuestion -> index', this.currentQuestionIndex, 'questionId', qtest && qtest.id);
        } catch (e) {}
        
        this.resetQuestionState();
        this.renderCurrentQuestion();
        this.updateNavigation();
        this.updateQuestionCounter();
        this.stateManager.setCurrentQuestionIndex(this.currentQuestionIndex);
        this.updateQuestionOverview();
    }

    resetQuestionState() {
        this.selectedOption = null;
        this.isAnswered = false;
        this.result.style.display = 'none';
        this.explanation.style.display = 'none';
        this.showExplanationBtn.style.display = 'none';
        this.submitBtn.disabled = true;
        this.submitBtn.textContent = 'Submit Answer';
        this.updateReviewButton();
    }

    renderCurrentQuestion() {
        const question = this.questions[this.currentQuestionIndex];
        
        if (question.comprehension && question.comprehension.trim()) {
            this.comprehensionContent.innerHTML = question.comprehension;
            this.comprehensionContent.style.display = 'block';
        } else {
            this.comprehensionContent.style.display = 'none';
        }
        
        if (question.direction && question.direction.trim()) {
            this.directionContent.innerHTML = question.direction;
            this.directionContent.style.display = 'block';
        } else {
            this.directionContent.style.display = 'none';
        }
        
        this.questionContent.innerHTML = question.content || 'No question content available.';
        
        this.renderOptions(question);
        
        const attemptResult = this.stateManager.getAttemptResult(question.id);
        if (attemptResult) {
            this.restoreAttemptedState(attemptResult, question);
        }
        
        this.setupAnswerExplanationToggle(question);
        
        this.renderMath();
    }

    renderOptions(question) {
        this.optionsContainer.innerHTML = '';
        
        if (question.options && question.options.length > 0) {
            question.options.forEach((option) => {
                const optionElement = document.createElement('div');
                optionElement.className = 'option';
                optionElement.dataset.identifier = option.identifier;
                
                optionElement.innerHTML = `
                    <span class="option-identifier">${option.identifier}</span>
                    <div class="option-content">${option.content}</div>
                `;
                
                optionElement.addEventListener('click', () => this.selectOption(option.identifier, optionElement));
                this.optionsContainer.appendChild(optionElement);
            });
            return;
        }
        
        const wrapper = document.createElement('div');
        wrapper.className = 'text-answer-wrapper';
        wrapper.innerHTML = `
            <label for="text-answer-input" style="display:block; margin-bottom:8px; font-weight:600;">Your answer</label>
            <input id="text-answer-input" type="text" placeholder="Type your answer here" style="width:100%; padding:8px; box-sizing:border-box;" />
            <div style="margin-top:8px; font-size:0.9em; color:#666;">This question has no options — enter your answer above and submit.</div>
        `;
        this.optionsContainer.appendChild(wrapper);
        
        const input = wrapper.querySelector('#text-answer-input');
        input.addEventListener('input', () => {
            const val = input.value.trim();
            this.submitBtn.disabled = val.length === 0 || this.isAnswered;
            this.selectedOption = val.length ? val : null;
        });
        
        this.submitBtn.disabled = true;
        this.selectedOption = null;
    }

    selectOption(identifier, optionElement) {
        if (this.isAnswered) return;
        
        document.querySelectorAll('.option').forEach(opt => opt.classList.remove('selected'));
        
        optionElement.classList.add('selected');
        this.selectedOption = identifier;
        
        this.submitBtn.disabled = false;
    }

    submitAnswer() {
        if (this.isAnswered) return;
        
        const question = this.questions[this.currentQuestionIndex];
        if ((!question.options || question.options.length === 0) && (!this.selectedOption || String(this.selectedOption).trim().length === 0)) {
            return;
        }
        if (!this.selectedOption) return;
        
        this.isAnswered = true;
        this.submitBtn.disabled = true;
        this.submitBtn.textContent = 'Answer Submitted';
        
        let isCorrect = false;
        if (question.correct_options && question.correct_options.length > 0) {
            isCorrect = question.correct_options.includes(this.selectedOption);
        } else if (question.answer) {
            const expected = String(question.answer).trim().toLowerCase();
            const actual = String(this.selectedOption).trim().toLowerCase();
            isCorrect = expected.length > 0 && actual === expected;
        }
        
        this.stateManager.recordAttempt(question.id, this.selectedOption, isCorrect);
        
        if (question.options && question.options.length > 0) {
            this.highlightOptions(question);
        }
        
        this.showResult(isCorrect, question);
        this.updateProgress();
        this.updateQuestionOverview();
        
        if (question.explanation) {
            this.showExplanationBtn.style.display = 'inline-block';
        }
    }

    highlightOptions(question) {
        document.querySelectorAll('.option').forEach(optionElement => {
            const identifier = optionElement.dataset.identifier;
            
            if (question.correct_options && question.correct_options.includes(identifier)) {
                optionElement.classList.add('correct');
            } else if (identifier === this.selectedOption) {
                optionElement.classList.add('wrong');
            }
            
            optionElement.style.pointerEvents = 'none';
        });
    }

    showResult(isCorrect, question) {
        this.result.style.display = 'block';
        this.result.className = `result ${isCorrect ? 'correct' : 'wrong'}`;
        
        if (isCorrect) {
            this.result.innerHTML = `
                <div>🎉 Correct Answer!</div>
                <div style="font-size: 0.9em; margin-top: 10px;">
                    You selected option ${this.selectedOption}, which is correct.
                </div>
            `;
        } else {
            const correctAnswers = question.correct_options ? question.correct_options.join(', ') : 'Unknown';
            this.result.innerHTML = `
                <div>❌ Incorrect Answer</div>
                <div style="font-size: 0.9em; margin-top: 10px;">
                    You selected option ${this.selectedOption}. The correct answer${question.correct_options && question.correct_options.length > 1 ? 's are' : ' is'}: ${correctAnswers}
                </div>
            `;
        }
    }

    setupAnswerExplanationToggle(question) {
        this.explanation.style.display = 'none';
        
        if ((question.correct_options && question.correct_options.length > 0) || 
            (question.explanation && question.explanation.trim())) {
            
            this.showExplanationBtn.style.display = 'inline-block';
            this.showExplanationBtn.textContent = 'Show Answer & Explanation';
            
            const newBtn = this.showExplanationBtn.cloneNode(true);
            this.showExplanationBtn.parentNode.replaceChild(newBtn, this.showExplanationBtn);
            this.showExplanationBtn = newBtn;
            
            this.showExplanationBtn.addEventListener('click', () => this.toggleAnswerExplanation());
        } else {
            this.showExplanationBtn.style.display = 'none';
        }
    }

    toggleAnswerExplanation() {
        const question = this.questions[this.currentQuestionIndex];
        
        if (this.explanation.style.display === 'block') {
            this.explanation.style.display = 'none';
            this.showExplanationBtn.textContent = 'Show Answer & Explanation';
        } else {
            let content = '';
            
            if (question.correct_options && question.correct_options.length > 0) {
                content += `
                    <h3>Correct Answer${question.correct_options.length > 1 ? 's' : ''}</h3>
                    <div style="margin-bottom: 20px; padding: 15px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; color: #155724;">
                        <strong>${question.correct_options.join(', ')}</strong>
                    </div>
                `;
            }
            
            if (question.explanation && question.explanation.trim()) {
                content += `
                    <h3>Explanation</h3>
                    <div>${question.explanation}</div>
                `;
            }
            
            this.explanation.innerHTML = content;
            this.explanation.style.display = 'block';
            this.showExplanationBtn.textContent = 'Hide Answer & Explanation';
            
            this.renderMath();
            this.explanation.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    restoreAttemptedState(attemptResult, question) {
        this.selectedOption = attemptResult.selectedOption;
        this.isAnswered = true;
        this.submitBtn.disabled = true;
        this.submitBtn.textContent = 'Answer Submitted';
        
        document.querySelectorAll('.option').forEach(optionElement => {
            const identifier = optionElement.dataset.identifier;
            
            if (identifier === attemptResult.selectedOption) {
                optionElement.classList.add('selected');
            }
            
            if (question.correct_options && question.correct_options.includes(identifier)) {
                optionElement.classList.add('correct');
            } else if (identifier === attemptResult.selectedOption) {
                optionElement.classList.add('wrong');
            }
            
            optionElement.style.pointerEvents = 'none';
        });
        
        this.showResult(attemptResult.correct, question);
        
        if (question.explanation) {
            this.showExplanationBtn.style.display = 'inline-block';
        }
    }

    previousQuestion() {
        if (this.currentQuestionIndex > 0) {
            this.currentQuestionIndex--;
            this.loadCurrentQuestion();
        }
    }

    nextQuestion() {
        if (this.currentQuestionIndex < this.questions.length - 1) {
            this.currentQuestionIndex++;
            this.loadCurrentQuestion();
        }
    }

    updateNavigation() {
        this.prevBtn.disabled = this.currentQuestionIndex === 0;
        this.nextBtn.disabled = this.currentQuestionIndex === this.questions.length - 1;
    }

    updateQuestionCounter() {
        this.questionCounter.textContent = `Question ${this.currentQuestionIndex + 1} of ${this.questions.length}`;
    }

    toggleReviewMark() {
        const question = this.questions[this.currentQuestionIndex];
        
        if (this.stateManager.isMarkedForReview(question.id)) {
            this.stateManager.unmarkForReview(question.id);
        } else {
            this.stateManager.markForReview(question.id);
        }
        
        this.updateReviewButton();
        this.updateQuestionOverview();
    }

    updateReviewButton() {
        const question = this.questions[this.currentQuestionIndex];
        const isMarked = this.stateManager.isMarkedForReview(question.id);
        
        this.markReviewBtn.textContent = isMarked ? 'Remove Review Mark' : 'Mark for Review';
        this.markReviewBtn.style.background = isMarked ? '#dc3545' : '#ffc107';
    }

    updateProgress() {
        if (this.questions.length === 0) {
            this.progressText.textContent = 'No questions loaded';
            this.progressFill.style.width = '0%';
            return;
        }
        
        const progress = this.stateManager.getProgress(this.questions.length);
        this.progressText.textContent = 
            `Progress: ${progress.attempted}/${progress.total} attempted (${progress.correct} correct)`;
        this.progressFill.style.width = `${progress.percentage}%`;
    }

    updateQuestionOverview() {
        if (this.questions.length === 0) {
            this.questionOverview.style.display = 'none';
            return;
        }
        
        this.questionOverview.style.display = 'block';
        this.questionGrid.innerHTML = '';
        
        this.questions.forEach((question, index) => {
            const questionItem = document.createElement('div');
            questionItem.className = 'question-item';
            questionItem.textContent = index + 1;
            
            if (index === this.currentQuestionIndex) {
                questionItem.classList.add('current');
            }
            
            const attemptResult = this.stateManager.getAttemptResult(question.id);
            if (attemptResult) {
                if (attemptResult.correct) {
                    questionItem.classList.add('attempted');
                } else {
                    questionItem.classList.add('incorrect');
                }
            }
            
            if (this.stateManager.isMarkedForReview(question.id)) {
                questionItem.classList.add('review');
            }
            
            questionItem.addEventListener('click', () => {
                this.currentQuestionIndex = index;
                this.loadCurrentQuestion();
            });
            
            this.questionGrid.appendChild(questionItem);
        });

        const currentEl = this.questionGrid.querySelector('.question-item.current');
        if (currentEl) {
            currentEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    async jumpToNextUnattempted() {
        if (!this.questions || this.questions.length === 0) return;
        try {
            console.debug('jumpToNextUnattempted start', {
                currentIndex: this.currentQuestionIndex,
                totalQuestions: this.questions.length,
                urlNext: window.urlNext,
                urlZen: window.urlZen
            });
        } catch (e) {}
        const total = this.questions.length;
        let idx = this.currentQuestionIndex;
        for (let i = 1; i <= total; i++) {
            const nextIdx = (idx + i) % total;
            const q = this.questions[nextIdx];
            const attempt = this.stateManager.getAttemptResult(q.id);
            if (!attempt || !attempt.attempted) {
                this.currentQuestionIndex = nextIdx;
                try {
                    console.debug('jumpToNextUnattempted -> selecting index', nextIdx, {
                        questionId: q.id,
                        questionIndex: nextIdx
                    });
                } catch (e) {}
                this.loadCurrentQuestion();
                return;
            }
        }
        console.info('No unattempted questions found in the current selection.');
    }

    async saveState() {
        const success = await this.stateManager.saveState();
        if (success) {
            alert('Progress saved successfully!');
        } else {
            alert('Error saving progress. Please try again.');
        }
    }

    async loadStateFromFile(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        const success = await this.stateManager.loadStateFromFile(file);
        if (success) {
            alert('Progress loaded successfully!');
            this.loadInitialState();
            this.updateProgress();
            this.updateQuestionOverview();
            if (this.questions.length > 0) {
                this.loadCurrentQuestion();
            }
        } else {
            alert('Error loading progress file. Please check the file format.');
        }
        
        event.target.value = '';
    }

    renderMath() {
        if (!window.MathJax) {
            console.warn('MathJax not found; skipping math typesetting.');
            return;
        }

        const elements = [
            this.comprehensionContent,
            this.directionContent,
            this.questionContent,
            this.optionsContainer,
            this.explanation
        ];

        try {
            if (typeof MathJax.typesetPromise === 'function') {
                MathJax.typesetPromise(elements).catch((err) => console.log('MathJax typeset failed: ' + err.message));
            } else if (typeof MathJax.typeset === 'function') {
                try {
                    MathJax.typeset(elements);
                } catch (err) {
                    console.log('MathJax.typeset failed: ' + err.message);
                }
            } else if (window.MathJax.Hub && typeof MathJax.Hub.Queue === 'function') {
                MathJax.Hub.Queue(["Typeset", MathJax.Hub, ...elements]);
            } else {
                console.warn('MathJax is present but does not expose a known typeset API; skipping typeset.');
            }
        } catch (err) {
            console.warn('Error while attempting MathJax typeset:', err);
        }
    }

    showQuizContainer() {
        this.noQuiz.style.display = 'none';
        this.quizContainer.style.display = 'block';
    }

    showNoQuiz() {
        this.quizContainer.style.display = 'none';
        this.questionOverview.style.display = 'none';
        this.noQuiz.style.display = 'block';
    }

    toggleZenMode() {
        this.zenMode = !this.zenMode;
        try {
            console.debug('toggleZenMode ->', this.zenMode, { urlZen: window.urlZen });
        } catch (e) {}
        document.body.classList.toggle('zen-mode', this.zenMode);
        this.applyZenMode();
    }

    applyZenMode() {
        const toHideSelectors = [
            '.filter-section',
            '.progress-section',
            '.question-overview',
            '#explanation',
            '.comprehension-content',
            '.direction-content',
            '.header h1',
            '#mark-for-review',
            '#show-explanation-btn',
            '#prev-question',
            '#question-counter'
        ];

        toHideSelectors.forEach(sel => {
            const el = document.querySelector(sel);
            if (!el) return;
            if (this.zenMode) {
                el.dataset._prevDisplay = el.style.display || '';
                el.style.display = 'none';
            } else {
                el.style.display = el.dataset._prevDisplay || '';
                delete el.dataset._prevDisplay;
            }
        });

        if (this.zenMode) {
            const essentials = ['.question-section', '.options-section', '.question-navigation', '.controls', '#submit-btn', '#next-question'];
            essentials.forEach(sel => {
                const el = document.querySelector(sel);
                if (el) el.style.display = '';
            });
        } else {
            const cleared = ['.question-section', '.options-section', '.question-navigation', '.controls', '#submit-btn', '#next-question'];
            cleared.forEach(sel => {
                const el = document.querySelector(sel);
                if (el && el.dataset._prevDisplay === '') {
                    el.style.display = '';
                }
            });
        }
    }

    toggleNightMode() {
        document.body.classList.toggle('night-mode');
        try {
            const enabled = document.body.classList.contains('night-mode');
            localStorage.setItem('quiz_night_mode', enabled ? '1' : '0');
        } catch (e) {
        }
    }

    showLoading(show) {
        if (show) {
            document.body.classList.add('loading');
        } else {
            document.body.classList.remove('loading');
        }
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    const app = new EnhancedQuizApp();
    await app.init();
});
