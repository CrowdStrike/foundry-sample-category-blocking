import React, { useState, useEffect } from 'react';
import { useFalconApiContext } from '../contexts/falcon-api-context';
import Plot from 'react-plotly.js';
import { SlSpinner, SlCard, SlIcon } from '@shoelace-style/shoelace/dist/react';

function DomainAnalytics() {
    const { falcon, isInitialized } = useFalconApiContext();
    const [analyticsData, setAnalyticsData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    
    // Function to check if dark mode is active
    const isDarkTheme = () => document.documentElement.classList.contains('theme-dark');
    
    // Track dark mode for Plotly charts
    const [isDarkMode, setIsDarkMode] = useState(isDarkTheme());
    
    // Preserve theme when component mounts and during its lifecycle
    useEffect(() => {
        // Log initial theme state
        console.log("DomainAnalytics mounted, theme:", isDarkTheme() ? "dark" : "light");
        
        // Function to detect theme changes
        const detectTheme = () => {
            const isDark = isDarkTheme();
            setIsDarkMode(isDark);
        };
        
        // Set up observer to detect theme changes
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    detectTheme();
                }
            });
        });
        
        observer.observe(document.documentElement, { 
            attributes: true,
            attributeFilter: ['class']
        });
        
        // Clean up observer on unmount
        return () => observer.disconnect();
    }, []);

    // Fetch analytics data when API is initialized
    useEffect(() => {
        if (isInitialized) {
            fetchAnalytics();
        }
    }, [isInitialized]);

    const fetchAnalytics = async () => {
        try {
            setLoading(true);
            const response = await falcon.cloudFunction({ name: 'reactblock' })
                .path('/domain-analytics')
                .get();
            
            if (response?.body) {
                setAnalyticsData(response.body);
            } else {
                setError("No data returned from API");
            }
        } catch (err) {
            console.error("Error fetching analytics:", err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    // Update Plotly charts when theme changes
    useEffect(() => {
        if (!analyticsData) return;
        
        const updatePlotlyTheme = () => {
            const plots = document.querySelectorAll('.js-plotly-plot');
            plots.forEach(plot => {
                if (plot && plot._fullLayout) {
                    try {
                        Plotly.relayout(plot, {
                            'font.color': isDarkMode ? '#ffffff' : '#333333',
                            'paper_bgcolor': 'transparent',
                            'plot_bgcolor': 'transparent',
                            'xaxis.color': isDarkMode ? '#ffffff' : '#333333',
                            'xaxis.gridcolor': isDarkMode ? '#444444' : '#e5e5e5',
                            'yaxis.color': isDarkMode ? '#ffffff' : '#333333',
                            'yaxis.gridcolor': isDarkMode ? '#444444' : '#e5e5e5',
                            'legend.font.color': isDarkMode ? '#ffffff' : '#333333',
                        });
                    } catch (err) {
                        console.error("Error updating plot theme:", err);
                    }
                }
            });
        };
        
        // Update theme after a short delay to ensure plots are rendered
        const timer = setTimeout(updatePlotlyTheme, 100);
        return () => clearTimeout(timer);
    }, [analyticsData, isDarkMode]);

    if (!isInitialized || loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <SlSpinner style={{ fontSize: '3rem' }} />
            </div>
        );
    }

    if (error) {
        return (
            <SlCard className="m-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Error</h3>
                </div>
                <div style={{ color: 'var(--sl-color-danger-600)' }}>
                    <SlIcon name="exclamation-triangle" style={{ marginRight: '0.5rem' }} />
                    {error}
                </div>
            </SlCard>
        );
    }

    if (!analyticsData || !analyticsData.visualization_data || 
        !analyticsData.visualization_data.bar_chart || 
        !analyticsData.visualization_data.comparison_chart) {
        return (
            <SlCard className="m-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">No Data</h3>
                </div>
                <div style={{ color: 'var(--sl-color-warning-600)' }}>
                    <SlIcon name="info-circle" style={{ marginRight: '0.5rem' }} />
                    No analytics data available
                </div>
            </SlCard>
        );
    }

    // Simple chart layouts with theme-aware colors
    const barChartLayout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        title: {
            text: 'Top 20 Most Visited Domains (Last 15 Days)',
            font: {
                color: isDarkMode ? '#ffffff' : '#333333'
            }
        },
        xaxis: { 
            title: 'Number of Visits',
            side: 'top',
            color: isDarkMode ? '#ffffff' : '#333333',
            gridcolor: isDarkMode ? '#444444' : '#e5e5e5'
        },
        yaxis: { 
            title: 'Domain',
            showticklabels: false,
            color: isDarkMode ? '#ffffff' : '#333333',
            gridcolor: isDarkMode ? '#444444' : '#e5e5e5'
        },
        height: 800,
        margin: { l: 20, r: 20, t: 50, b: 20 },
        autosize: true,
        font: {
            color: isDarkMode ? '#ffffff' : '#333333'
        }
    };

    const comparisonChartLayout = {
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        title: {
            text: 'Visits vs Unique IPs by Domain',
            font: {
                color: isDarkMode ? '#ffffff' : '#333333'
            }
        },
        xaxis: { 
            title: 'Domain',
            color: isDarkMode ? '#ffffff' : '#333333',
            gridcolor: isDarkMode ? '#444444' : '#e5e5e5'
        },
        yaxis: { 
            title: 'Count',
            color: isDarkMode ? '#ffffff' : '#333333',
            gridcolor: isDarkMode ? '#444444' : '#e5e5e5'
        },
        barmode: 'group',
        height: 600,
        autosize: true,
        font: {
            color: isDarkMode ? '#ffffff' : '#333333'
        },
        legend: {
            font: {
                color: isDarkMode ? '#ffffff' : '#333333'
            }
        }
    };

    // Create text annotations for the bar chart
    const barChartAnnotations = analyticsData.visualization_data.bar_chart.domains.map((domain, i) => {
        const visits = analyticsData.visualization_data.bar_chart.visits[i];
        return {
            x: visits / 2, // Position text in middle of bar
            y: i,
            text: domain,
            showarrow: false,
            font: {
                color: 'white', // White text for contrast
                size: 12
            },
            xanchor: 'center'
        };
    });

    // Add annotations to layout
    barChartLayout.annotations = barChartAnnotations;

    // Use Falcon Shoelace color variables
    const primaryColor = isDarkMode ? 
        'var(--sl-color-primary-600, #0078d4)' : 
        'var(--sl-color-primary-600, #0078d4)';
    
    const secondaryColor = isDarkMode ? 
        'var(--sl-color-secondary-600, #6264a7)' : 
        'var(--sl-color-secondary-600, #6264a7)';

    return (
        <div className="container mx-auto p-4">
            <h2 className="text-lg font-semibold text-left mb-4">Domain access analysis</h2>
            
            <SlCard>
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Top Domains</h3>
                </div>
                
                <Plot
                    key={`bar-chart-${isDarkMode ? 'dark' : 'light'}`}
                    data={[
                        {
                            type: 'bar',
                            x: analyticsData.visualization_data.bar_chart.visits,
                            y: analyticsData.visualization_data.bar_chart.domains,
                            orientation: 'h',
                            text: analyticsData.visualization_data.bar_chart.visits,
                            textposition: 'outside',
                            insidetextanchor: 'middle',
                            marker: {
                                color: primaryColor,
                                line: {
                                    color: primaryColor,
                                    width: 1
                                }
                            },
                            hovertemplate: '<b>%{y}</b><br>Visits: %{x}<extra></extra>'
                        }
                    ]}
                    layout={barChartLayout}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ 
                        responsive: true,
                        displayModeBar: false
                    }}
                />
            </SlCard>

            <SlCard className="mt-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Comparison Analysis</h3>
                </div>
                
                <Plot
                    key={`comparison-chart-${isDarkMode ? 'dark' : 'light'}`}
                    data={[
                        {
                            name: 'Total Visits',
                            type: 'bar',
                            x: analyticsData.visualization_data.comparison_chart.domains,
                            y: analyticsData.visualization_data.comparison_chart.visits,
                            text: analyticsData.visualization_data.comparison_chart.visits,
                            textposition: 'auto',
                            marker: {
                                color: primaryColor,
                                line: {
                                    color: primaryColor,
                                    width: 1
                                }
                            }
                        },
                        {
                            name: 'Unique IPs',
                            type: 'bar',
                            x: analyticsData.visualization_data.comparison_chart.domains,
                            y: analyticsData.visualization_data.comparison_chart.unique_ips,
                            text: analyticsData.visualization_data.comparison_chart.unique_ips,
                            textposition: 'auto',
                            marker: {
                                color: secondaryColor,
                                line: {
                                    color: secondaryColor,
                                    width: 1
                                }
                            }
                        }
                    ]}
                    layout={comparisonChartLayout}
                    useResizeHandler={true}
                    style={{ width: '100%', height: '100%' }}
                    config={{ 
                        responsive: true,
                        displayModeBar: false
                    }}
                />
            </SlCard>

            {/* Table section using standard HTML with Falcon Shoelace styling */}
            <SlCard className="mt-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Detailed Analysis</h3>
                </div>
                
                <div className="overflow-x-auto">
                    <table className="min-w-full" style={{ borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                {['Domain', 'Visit Count', 'Unique IPs', 'Unique Hosts', 'First Seen', 'Last Seen'].map(header => (
                                    <th key={header} 
                                        className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider">
                                        {header}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {Object.entries(analyticsData.analysis).map(([domain, data], index) => (
                                <tr key={domain} className={index % 2 === 0 ? 'bg-gray-50' : 'bg-white'}>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">{domain}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">{data.visit_count}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">{data.unique_ips}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">{data.unique_hosts}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        {new Date(data.first_seen).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        {new Date(data.last_seen).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </SlCard>
        </div>
    );
}

export { DomainAnalytics };

