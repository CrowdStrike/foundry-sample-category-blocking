// src/routes/domain-analytics.js
import React, { useState, useEffect } from 'react';
import { useFalconApiContext } from '../contexts/falcon-api-context';
import Plot from 'react-plotly.js';

export function DomainAnalytics() {
    const { falcon, isInitialized } = useFalconApiContext();
    const [analyticsData, setAnalyticsData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        // Only fetch analytics when the Falcon API is initialized
        if (isInitialized) {
            console.log("Falcon API initialized, fetching analytics...");
            fetchAnalytics();
        }
    }, [isInitialized]);

    const fetchAnalytics = async () => {
        try {
            setLoading(true);
            console.log("Making API call to fetch domain analytics data...");
            const response = await falcon.cloudFunction({ name: 'reactblock' })
                .path('/domain-analytics')
                .get();

            console.log("Response received:", response);
            
            if (response?.body) {
                console.log("Setting analytics data:", response.body);
                setAnalyticsData(response.body);
            } else {
                console.error("No body in response:", response);
                setError("No data returned from API");
            }
        } catch (err) {
            console.error("Error fetching analytics:", err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    // If Falcon API is not initialized yet, show loading
    if (!isInitialized) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-lg text-indigo-600">Connecting to Falcon API...</div>
            </div>
        );
    }

    if (loading) return (
        <div className="flex items-center justify-center min-h-screen">
            <div className="text-lg text-indigo-600">Loading analytics...</div>
        </div>
    );

    if (error) return (
        <div className="p-4 bg-red-50 text-red-600 rounded-lg m-4">
            Error: {error}
        </div>
    );

    if (!analyticsData) return (
        <div className="p-4 bg-yellow-50 text-yellow-600 rounded-lg m-4">
            No data available
        </div>
    );

    console.log("Rendering with data:", analyticsData);

    // Check if the expected data structure exists
    if (!analyticsData.visualization_data || 
        !analyticsData.visualization_data.bar_chart || 
        !analyticsData.visualization_data.comparison_chart) {
        console.error("Invalid data structure:", analyticsData);
        return (
            <div className="p-4 bg-red-50 text-red-600 rounded-lg m-4">
                Error: Invalid data structure received from API
            </div>
        );
    }

    return (
        <div className="container mx-auto p-6 space-y-6">
            <h1 className="text-2xl font-bold text-indigo-800 mb-6">
                Domain Access Analysis
            </h1>

            {/* Bar Chart */}
            <div className="bg-white rounded-xl shadow-lg p-6">
                <Plot
                    data={[
                        {
                            type: 'bar',
                            x: analyticsData.visualization_data.bar_chart.visits,
                            y: analyticsData.visualization_data.bar_chart.domains,
                            orientation: 'h',
                            text: analyticsData.visualization_data.bar_chart.visits,
                            textposition: 'auto',
                            marker: {
                                color: 'rgba(58, 71, 80, 0.6)',
                                line: {
                                    color: 'rgba(58, 71, 80, 1.0)',
                                    width: 1
                                }
                            }
                        }
                    ]}
                    layout={{
                        title: 'Top 20 Most Visited Domains (Last 15 Days)',
                        xaxis: { title: 'Number of Visits' },
                        yaxis: { title: 'Domain' },
                        height: 800,
                        margin: { l: 150 },
                        autosize: true
                    }}
                    useResizeHandler={true}
                    className="w-full"
                    style={{ width: '100%', height: '100%' }}
                />
            </div>

            {/* Comparison Chart */}
            <div className="bg-white rounded-xl shadow-lg p-6">
                <Plot
                    data={[
                        {
                            name: 'Total Visits',
                            type: 'bar',
                            x: analyticsData.visualization_data.comparison_chart.domains,
                            y: analyticsData.visualization_data.comparison_chart.visits,
                            marker: {
                                color: 'rgba(55, 83, 109, 0.7)',
                                line: {
                                    color: 'rgba(55, 83, 109, 1.0)',
                                    width: 1
                                }
                            }
                        },
                        {
                            name: 'Unique IPs',
                            type: 'bar',
                            x: analyticsData.visualization_data.comparison_chart.domains,
                            y: analyticsData.visualization_data.comparison_chart.unique_ips,
                            marker: {
                                color: 'rgba(219, 64, 82, 0.7)',
                                line: {
                                    color: 'rgba(219, 64, 82, 1.0)',
                                    width: 1
                                }
                            }
                        }
                    ]}
                    layout={{
                        title: 'Visits vs Unique IPs by Domain',
                        xaxis: { title: 'Domain' },
                        yaxis: { title: 'Count' },
                        barmode: 'group',
                        height: 600,
                        autosize: true
                    }}
                    useResizeHandler={true}
                    className="w-full"
                    style={{ width: '100%', height: '100%' }}
                />
            </div>

            {/* Data Table */}
            <div className="bg-white rounded-xl shadow-lg p-6 overflow-x-auto">
                <h2 className="text-xl font-semibold mb-4">Detailed Analysis</h2>
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Domain</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Visit Count</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Unique IPs</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Unique Hosts</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">First Seen</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last Seen</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {Object.entries(analyticsData.analysis).map(([domain, data], index) => (
                            <tr key={domain} className={index % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{domain}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{data.visit_count}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{data.unique_ips}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{data.unique_hosts}</td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                    {new Date(data.first_seen).toLocaleString()}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                    {new Date(data.last_seen).toLocaleString()}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
