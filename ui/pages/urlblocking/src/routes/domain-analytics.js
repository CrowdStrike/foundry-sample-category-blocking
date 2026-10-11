import React, { useState, useEffect, useContext } from 'react';
import { FalconApiContext } from '../contexts/falcon-api-context';
import { SlSpinner, SlCard, SlAlert } from '@shoelace-style/shoelace/dist/react';
import { callFunction } from '../utils/api.js';

const thClass = 'px-6 py-3 text-left text-xs font-medium uppercase tracking-wider';
const tdClass = 'px-6 py-4 whitespace-nowrap text-sm';

function DataTable({ headers, rows }) {
    return (
        <div className="overflow-x-auto">
            <table className="min-w-full" style={{ borderCollapse: 'collapse' }}>
                <thead>
                    <tr>
                        {headers.map(header => (
                            <th key={header} className={thClass}>{header}</th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((cells, index) => (
                        <tr key={index}>
                            {cells.map((cell, i) => (
                                <td key={i} className={tdClass}>{cell}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

const formatDate = (value) => (value ? new Date(value).toLocaleString() : '-');

function DomainAnalytics() {
    const { falcon, isInitialized } = useContext(FalconApiContext);
    const [analyticsData, setAnalyticsData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!isInitialized) return;

        const fetchAnalytics = async () => {
            try {
                setLoading(true);
                setError(null);
                setAnalyticsData(await callFunction(falcon, 'GET', '/domain-analytics'));
            } catch (err) {
                console.error('Error fetching analytics:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchAnalytics();
    }, [isInitialized, falcon]);

    if (!isInitialized || loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <SlSpinner style={{ fontSize: '2rem' }}></SlSpinner>
            </div>
        );
    }

    if (error) {
        return <SlAlert variant="danger" open>{error}</SlAlert>;
    }

    const viz = analyticsData?.visualization_data;
    const bar = viz?.bar_chart;
    const comparison = viz?.comparison_chart;

    if (!bar || !comparison) {
        return <SlAlert variant="warning" open>No analytics data available</SlAlert>;
    }

    const analysis = Object.entries(analyticsData.analysis || {});

    return (
        <div className="container mx-auto p-4">
            <h2 className="text-lg font-semibold text-left mb-4">Domain access analysis</h2>

            {analyticsData.truncated && (
                <SlAlert variant="warning" open className="mb-4">
                    {analyticsData.message || 'Results may be incomplete'}
                </SlAlert>
            )}

            <SlCard>
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Top 20 Most Visited Domains (Last 15 Days)</h3>
                </div>
                <DataTable
                    headers={['#', 'Domain', 'Visits']}
                    rows={bar.domains.map((domain, i) => [i + 1, domain, bar.visits[i]])}
                />
            </SlCard>

            <SlCard className="mt-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Visits vs Unique IPs by Domain</h3>
                </div>
                <DataTable
                    headers={['Domain', 'Total Visits', 'Unique IPs']}
                    rows={comparison.domains.map((domain, i) => [
                        domain,
                        comparison.visits[i],
                        comparison.unique_ips[i],
                    ])}
                />
            </SlCard>

            <SlCard className="mt-4">
                <div slot="header">
                    <h3 className="text-lg font-semibold text-left">Detailed Analysis</h3>
                </div>
                <DataTable
                    headers={['Domain', 'Visit Count', 'Unique IPs', 'Unique Hosts', 'First Seen', 'Last Seen']}
                    rows={analysis.map(([domain, data]) => [
                        domain,
                        data.visit_count,
                        data.unique_ips,
                        data.unique_hosts,
                        formatDate(data.first_seen),
                        formatDate(data.last_seen),
                    ])}
                />
            </SlCard>
        </div>
    );
}

export { DomainAnalytics };
