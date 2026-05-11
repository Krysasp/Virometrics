/**
 * Tutorial JavaScript for Virometrics.
 * Handles tutorial state management, step navigation, and progress tracking.
 */

class TutorialManager {
    constructor(tutorialData) {
        this.tutorialData = tutorialData;
        this.currentStep = 0;
        this.completedSteps = new Set();
        this.interactiveElements = {};
        
        this.init();
    }
    
    init() {
        this.renderStepIndicator();
        this.renderStep(this.currentStep);
        this.updateProgress();
        this.bindEvents();
    }
    
    renderStepIndicator() {
        const indicator = document.getElementById('stepIndicator');
        indicator.innerHTML = '';
        
        this.tutorialData.steps.forEach((step, index) => {
            const dot = document.createElement('div');
            dot.className = 'step-dot';
            dot.dataset.step = index;
            dot.onclick = () => this.goToStep(index);
            
            if (index === this.currentStep) {
                dot.classList.add('active');
            } else if (this.completedSteps.has(index)) {
                dot.classList.add('completed');
            }
            
            indicator.appendChild(dot);
        });
    }
    
    renderStep(stepIndex) {
        const content = document.getElementById('tutorialContent');
        const step = this.tutorialData.steps[stepIndex];
        
        if (stepIndex === this.tutorialData.steps.length) {
            // Completion screen
            content.innerHTML = this.renderCompletion();
        } else {
            content.innerHTML = this.renderStepContent(step, stepIndex);
        }
        
        // Update navigation buttons
        this.updateNavigation();
        
        // Bind interactive elements
        this.bindInteractiveElements();
    }
    
    renderStepContent(step, stepIndex) {
        return `
            <div class="step-container">
                <div class="step-header">
                    <div class="step-number">${stepIndex + 1}</div>
                    <div class="step-title">${step.title}</div>
                </div>
                <div class="step-content">
                    ${step.description}
                    ${step.interactive ? this.renderInteractiveDemo(step) : ''}
                    ${step.tip ? this.renderTip(step.tip) : ''}
                </div>
            </div>
        `;
    }
    
    renderInteractiveDemo(step) {
        return `
            <div class="interactive-demo" data-step="${step.index}">
                <label for="${step.demoId}">${step.demoLabel}</label>
                <input type="text" id="${step.demoId}" 
                       placeholder="${step.demoPlaceholder || 'Enter value...'}"
                       value="${step.demoValue || ''}">
                <button onclick="tutorial.runDemo(${step.index})">Run Demo</button>
                <div class="demo-output" id="output-${step.index}"></div>
            </div>
        `;
    }
    
    renderTip(tip) {
        return `
            <div class="tip-box">
                <strong>Tip:</strong> ${tip}
            </div>
        `;
    }
    
    renderCompletion() {
        return `
            <div class="step-container">
                <div class="step-header">
                    <div class="step-number">✓</div>
                    <div class="step-title">Tutorial Complete!</div>
                </div>
                <div class="step-content completion-message">
                    <h2>Congratulations!</h2>
                    <p>You've completed the Virometrics basics tutorial.</p>
                    <p>You're now ready to start using the platform for your bioinformatics analysis.</p>
                    <button class="btn-primary" onclick="tutorial.startNew()">
                        Start New Analysis
                    </button>
                </div>
            </div>
        `;
    }
    
    updateNavigation() {
        const prevBtn = document.getElementById('prevBtn');
        const nextBtn = document.getElementById('nextBtn');
        const stepProgress = document.getElementById('stepProgress');
        
        prevBtn.disabled = this.currentStep === 0;
        
        const totalSteps = this.tutorialData.steps.length;
        if (this.currentStep >= totalSteps - 1) {
            nextBtn.textContent = 'Finish';
            stepProgress.textContent = `Step ${this.currentStep + 1} of ${totalSteps}`;
        } else {
            nextBtn.textContent = 'Next →';
            stepProgress.textContent = `Step ${this.currentStep + 1} of ${totalSteps}`;
        }
    }
    
    updateProgress() {
        const progressFill = document.getElementById('progressFill');
        const totalSteps = this.tutorialData.steps.length;
        const progress = ((this.currentStep + 1) / totalSteps) * 100;
        progressFill.style.width = `${progress}%`;
    }
    
    goToStep(stepIndex) {
        // Can only jump to completed steps or current step
        if (stepIndex <= this.currentStep) {
            this.currentStep = stepIndex;
            this.renderStep(stepIndex);
            this.renderStepIndicator();
            this.updateProgress();
        }
    }
    
    nextStep() {
        if (this.currentStep < this.tutorialData.steps.length) {
            // Mark current step as completed
            this.completedSteps.add(this.currentStep);
            
            this.currentStep++;
            this.renderStep(this.currentStep);
            this.renderStepIndicator();
            this.updateProgress();
        }
    }
    
    prevStep() {
        if (this.currentStep > 0) {
            this.currentStep--;
            this.renderStep(this.currentStep);
            this.renderStepIndicator();
            this.updateProgress();
        }
    }
    
    bindEvents() {
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') {
                this.nextStep();
            } else if (e.key === 'ArrowLeft') {
                this.prevStep();
            }
        });
    }
    
    bindInteractiveElements() {
        const step = this.tutorialData.steps[this.currentStep];
        if (step && step.demoId) {
            const input = document.getElementById(step.demoId);
            if (input) {
                input.addEventListener('input', (e) => {
                    this.onInputChange(step.index, e.target.value);
                });
            }
        }
    }
    
    onInputChange(stepIndex, value) {
        const output = document.getElementById(`output-${stepIndex}`);
        if (output && this.tutorialData.steps[stepIndex].onInput) {
            output.textContent = this.tutorialData.steps[stepIndex].onInput(value);
        }
    }
    
    runDemo(stepIndex) {
        const step = this.tutorialData.steps[stepIndex];
        const output = document.getElementById(`output-${stepIndex}`);
        const input = document.getElementById(step.demoId);
        
        if (step.onExecute) {
            const result = step.onExecute(input ? input.value : '');
            output.textContent = result;
            
            // Mark step as completed
            this.completedSteps.add(stepIndex);
            this.renderStepIndicator();
        }
    }
    
    startNew() {
        this.currentStep = 0;
        this.completedSteps.clear();
        this.renderStep(0);
        this.renderStepIndicator();
        this.updateProgress();
    }
    
    getProgress() {
        return {
            currentStep: this.currentStep,
            totalSteps: this.tutorialData.steps.length,
            completedSteps: this.completedSteps.size,
            percentage: (this.completedSteps.size / this.tutorialData.steps.length) * 100
        };
    }
    
    saveProgress() {
        const progress = this.getProgress();
        localStorage.setItem(`virometrics_tutorial_${this.tutorialData.id}`, JSON.stringify(progress));
    }
    
    loadProgress() {
        const saved = localStorage.getItem(`virometrics_tutorial_${this.tutorialData.id}`);
        if (saved) {
            const progress = JSON.parse(saved);
            this.currentStep = progress.currentStep;
            this.completedSteps = new Set(progress.completedSteps || []);
        }
    }
}

// Global tutorial instance
let tutorial;

// Initialize tutorial when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Load tutorial data from JSON file
    fetch('../data/tutorials/getting_started.json')
        .then(response => response.json())
        .then(data => {
            tutorial = new TutorialManager(data);
        })
        .catch(error => {
            console.error('Failed to load tutorial data:', error);
            // Fallback to basic tutorial
            tutorial = new TutorialManager({
                id: 'getting_started',
                title: 'Getting Started',
                steps: [
                    {
                        title: 'Welcome',
                        description: '<p>Welcome to Virometrics! This tutorial will guide you through the basic features.</p>'
                    },
                    {
                        title: 'Loading Data',
                        description: '<p>Start by loading your sequence data using the Data browser.</p>',
                        interactive: true,
                        demoId: 'dataInput',
                        demoLabel: 'Enter FASTA file path:',
                        demoPlaceholder: '/path/to/data.fasta',
                        onInput: (value) => value ? `Validating: ${value}` : 'Enter a file path',
                        onExecute: (value) => value ? `Loaded: ${value}` : 'No file specified'
                    },
                    {
                        title: 'Running Analysis',
                        description: '<p>Select a tool and configure parameters for your analysis.</p>',
                        tip: 'Always validate your inputs before running!'
                    },
                    {
                        title: 'Viewing Results',
                        description: '<p>Results are automatically saved and can be browsed in the Data section.</p>'
                    },
                    {
                        title: 'Exporting',
                        description: '<p>Export your results in various formats for publication or further analysis.</p>'
                    }
                ]
            });
        });
});
