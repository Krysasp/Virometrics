// charts.js - Plotly chart rendering for Virometrics

// Color palette
const COLORS = {
    primary: '#109b81',
    primaryLight: '#6FC3BA',
    secondary: '#2C4B7C',
    accent: '#9D5EB0',
    info: '#3498db',
    success: '#28a745',
    warning: '#ffc107',
    danger: '#e74c3c'
};

// Render category chart (pie/donut)
function renderCategoryChart() {
    const categories = virometricsData.categories;
    const labels = Object.keys(categories);
    const values = Object.values(categories);

    const colors = [
        '#4682B4', '#6A5ACD', '#20B2AA', '#DB7093', '#9370DB',
        '#4169E1', '#FF6347', '#3CB371', '#1E90FF', '#FF8C00', '#778899'
    ];

    const data = [{
        labels: labels,
        values: values,
        type: 'pie',
        hole: 0.4,
        marker: {
            colors: colors.slice(0, labels.length)
        },
        textinfo: 'label+percent',
        textposition: 'outside',
        automargin: true
    }];

    const layout = {
        margin: { t: 20, b: 20, l: 20, r: 20 },
        showlegend: true,
        legend: { orientation: 'v', x: 1, y: 0.5 },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui, sans-serif' }
    };

    Plotly.newPlot('category-chart', data, layout, { responsive: true });
}

// Render language chart (bar)
function renderLanguageChart() {
    const languages = virometricsData.languages;
    // Sort by count and take top 15
    const sorted = Object.entries(languages)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);

    const labels = sorted.map(x => x[0]);
    const values = sorted.map(x => x[1]);

    const data = [{
        x: labels,
        y: values,
        type: 'bar',
        marker: {
            color: COLORS.primary,
            opacity: 0.8
        },
        text: values,
        textposition: 'auto'
    }];

    const layout = {
        margin: { t: 20, b: 60, l: 50, r: 20 },
        xaxis: {
            tickangle: -45,
            tickfont: { size: 10 }
        },
        yaxis: {
            title: 'Number of Tools'
        },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui, sans-serif' }
    };

    Plotly.newPlot('language-chart', data, layout, { responsive: true });
}

// Render package manager chart
function renderPackageManagerChart() {
    const pkgMgrs = virometricsData.packageManagers;
    const labels = Object.keys(pkgMgrs);
    const values = Object.values(pkgMgrs);

    const data = [{
        labels: labels,
        values: values,
        type: 'bar',
        orientation: 'h',
        marker: {
            color: COLORS.info,
            opacity: 0.7
        }
    }];

    const layout = {
        margin: { t: 20, b: 40, l: 100, r: 20 },
        xaxis: { title: 'Number of Tools' },
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui, sans-serif' }
    };

    Plotly.newPlot('pkgmgr-chart', data, layout, { responsive: true });
}

// Render input format chart
function renderInputFormatChart() {
    const formats = virometricsData.inputFormats;
    // Sort by count and take top 15
    const sorted = Object.entries(formats)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);

    const labels = sorted.map(x => x[0]);
    const values = sorted.map(x => x[1]);

    const data = [{
        labels: labels,
        values: values,
        type: 'pie',
        hole: 0.3,
        marker: {
            colors: ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
                      '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5']
        },
        textinfo: 'label+value',
        automargin: true
    }];

    const layout = {
        margin: { t: 20, b: 20, l: 20, r: 20 },
        showlegend: false,
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui, sans-serif' }
    };

    Plotly.newPlot('inputfmt-chart', data, layout, { responsive: true });
}

// Render all charts
function renderAllCharts() {
    renderCategoryChart();
    renderLanguageChart();
    renderPackageManagerChart();
    renderInputFormatChart();
}
