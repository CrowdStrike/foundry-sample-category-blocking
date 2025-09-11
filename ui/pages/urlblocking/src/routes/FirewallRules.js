import React, { useState, useEffect, useContext } from 'react';
import { FalconApiContext } from '../contexts/falcon-api-context';
import { SlDetails, SlAlert, SlDialog } from '@shoelace-style/shoelace/dist/react';
import '@shoelace-style/shoelace/dist/themes/light.css';


// Logging utility
const logMessage = (message, data = null, type = 'info') => {
    const timestamp = new Date().toISOString();
    const logFunc = type === 'error' ? console.error : console.log;
    if (data) {
        logFunc(`[${timestamp}] ${message}:`, data);
    } else {
        logFunc(`[${timestamp}] ${message}`);
    }
};

// Helper functions
const createValidKey = (str) => {
    // Replace any invalid characters with underscores and ensure it's within length limits
    return str.replace(/[^a-zA-Z0-9._-]/g, '_').substring(0, 999);
};

const safeReadCollection = async (collection, key) => {
    try {
        const record = await collection.read(key);
        return record;
    } catch (error) {
        logMessage(`Error reading collection for key ${key}:`, error.message);
        return null;
    }
};

function FirewallRules() {
    const { falcon } = useContext(FalconApiContext);
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [selectedCategory, setSelectedCategory] = useState(null);
    const [showDetails, setShowDetails] = useState(false);
    const [categoryData, setCategoryData] = useState(null);
    const [ruleUpdateStatus, setRuleUpdateStatus] = useState({});
    const [updateDetails, setUpdateDetails] = useState([]);
    // Add this to your component's state
const [hasImported, setHasImported] = useState(false);

    useEffect(() => {
        fetchCategories();
    }, []);

    const fetchCategories = async () => {
        logMessage('Fetching categories');
        try {
            setLoading(true);
            const collection = falcon.collection({
                collection: 'domain'
            });

            const response = await collection.list({
                limit: 100
            });

            logMessage('Categories response:', response);

            if (response && response.resources) {
                setCategories(response.resources);
                setError(null);
            }
        } catch (err) {
            logMessage('Error fetching categories:', err, 'error');
            setError('Failed to fetch categories: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleUpdateRules = async (categoryName, newDomain) => {
        logMessage(`Starting rule update for category: ${categoryName}`);
        try {
            setLoading(true);

            // First get relationships for this category
            const relationshipCollection = falcon.collection({
                collection: 'relationship'
            });

            const response = await relationshipCollection.list({
                limit: 1000
            });

            logMessage('List response:', response);

            if (!response || !response.resources) {
                throw new Error('No resources found in response');
            }

            // Get all relationships data
            const relationships = [];
            for (const key of response.resources) {
                try {
                    const record = await relationshipCollection.read(key);
                    if (record && record.category_name === categoryName) {
                        relationships.push(record);
                    }
                } catch (error) {
                    logMessage(`Error fetching relationship for key ${key}:`, error.message);
                }
            }

            if (relationships.length === 0) {
                throw new Error(`No relationships found for category: ${categoryName}`);
            }

            // Call update-rules with only the new domain
            const config = {
                name: 'urlblock',
                version: 1
            };
            
            const cloudFunction = falcon.cloudFunction(config);
            const updateResponse = await cloudFunction.path('/update-rules').post({
                category_name: categoryName,
                new_urls: newDomain,  // Send only the new URLs
                relationships: relationships
            });

            logMessage('Rule update response:', updateResponse);

            if (updateResponse.body && updateResponse.body.success) {
                const results = updateResponse.body.results || [];
                
                // Update status for each rule group
                const newStatus = {};
                results.forEach(result => {
                    newStatus[result.rule_group_id] = {
                        name: result.rule_group_name,
                        status: result.status === 'success' ? 'Updated successfully' : 'Failed',
                        details: result.details || result.error,
                        timestamp: new Date().toISOString()
                    };
                });

                setRuleUpdateStatus(prev => ({ ...prev, ...newStatus }));
                setUpdateDetails(results);
            } else {
                throw new Error(updateResponse.body?.error || 'Failed to update rules');
            }

        } catch (error) {
            logMessage('Error in handleUpdateRules:', error, 'error');
            setError(`Failed to update rules: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };
    const handleCategoryClick = async (category) => {
        logMessage(`Fetching details for category: ${category}`);
        try {
            setLoading(true);
            const collection = falcon.collection({
                collection: 'domain'
            });

            const categoryData = await collection.read(category);
            logMessage('Category data:', categoryData);

            if (categoryData) {
                setCategoryData(categoryData);
                setSelectedCategory(category);
                setShowDetails(true);
                setRuleUpdateStatus({});
                setUpdateDetails([]);
            }
        } catch (err) {
            logMessage('Error fetching category details:', err, 'error');
            setError('Failed to fetch category details: ' + err.message);
        } finally {
            setLoading(false);
        }
    };


    const handleAddDomain = async (domain) => {
    if (!domain.trim()) {
        setError('Please enter a valid domain');
        return;
    }

    logMessage(`Adding domain: ${domain} to category: ${selectedCategory}`);
    try {
        setLoading(true);
        
        // First add domain to collection
        const collection = falcon.collection({
            collection: 'domain'
        });

        // Create a valid key for the collection
        const safeKey = createValidKey(selectedCategory);

        // Get current category data
        const currentData = await safeReadCollection(collection, safeKey);
        const existingDomains = currentData?.domain || '';
        
        // Add both the original domain and the starred version
        const starredDomain = domain.startsWith('*') ? domain : `*${domain}`;
        const domainsToAdd = `${domain};${starredDomain}`;
        
        const updatedDomains = existingDomains 
            ? `${existingDomains};${domainsToAdd}`
            : domainsToAdd;

        // Update domain in collection
        await collection.write(safeKey, {
            ...currentData,
            domain: updatedDomains,
            last_updated: new Date().toISOString()
        });

        // Then update rules with both domains
        await handleUpdateRules(selectedCategory, domainsToAdd);
        
        // Refresh category details
        await handleCategoryClick(selectedCategory);
        
        setError(null);
        logMessage(`Successfully added domain and starred version, and updated rules`);

    } catch (err) {
        logMessage('Error adding domain:', err, 'error');
        setError('Failed to add domain: ' + err.message);
    } finally {
        setLoading(false);
    }
};

    

    const handleImport = async () => {
        logMessage('Starting category import');
        try {
            setLoading(true);
            const config = {
                name: 'urlblock',
                version: 1
            };
            
            const cloudFunction = falcon.cloudFunction(config);
            const response = await cloudFunction.path('/import-csv').post({
                collection_name: 'domain'
            });


            logMessage('Import response:', response);

            if (response.body.success) {
                await fetchCategories();
                setHasImported(true);
                setError(null);
            }
        } catch (err) {
            logMessage('Import error:', err, 'error');
            setError('Import failed: ' + err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
    <div className="container mx-auto p-4 max-w-screen-2xl">
        <h2 className="text-lg font-semibold text-black mb-4 text-left">Domain Categories Management</h2>

        {/* Import Section */}
        <div className="mb-6">
            <sl-button
                variant="primary"
                onClick={handleImport}
                disabled={loading}
                style={{
                    '--sl-button-font-size': 'var(--sl-font-size-medium)',
                    '--sl-input-height-medium': '36px',
                }}
            >
                {loading ? 'Importing...' : 'Import Categories'}
            </sl-button>
        </div>

        {/* Error Display */}
        {error && (
            <SlAlert variant="danger" className="mb-4">
                {error}
            </SlAlert>
        )}

        {/* Loading Indicator */}
        {loading && (
            <div className="text-center py-4">
                <sl-spinner style={{ fontSize: '2rem' }}></sl-spinner>
                <p className="mt-2 text-gray-600">Loading...</p>
            </div>
        )}

        {/* Categories Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {categories.map((category) => (
                <sl-card
                    key={category}
                    class="cursor-pointer hover:bg-gray-50 transition-colors"
                    onClick={() => handleCategoryClick(category)}
                >
                    <strong>{category}</strong>
                </sl-card>
            ))}
        </div>

        {/* Category Details Dialog */}
        <SlDialog 
            open={showDetails} 
            onSlAfterHide={() => setShowDetails(false)}
            label={`Category Details: ${selectedCategory}`}
            style={{ '--width': '500px' }}
        >
            {categoryData && (
                <div className="p-4">
                    <h3 className="font-bold mb-2">Domains:</h3>
                    <sl-details open>
                        <div className="max-h-96 overflow-y-auto">
                            {categoryData.domain?.split(';')
                                .filter(domain => domain && !domain.startsWith('*'))
                                .map((domain, index) => (
                                    <div key={index} className="py-1 px-2 hover:bg-gray-50">
                                        {domain}
                                    </div>
                                ))
                            }
                        </div>
                    </sl-details>

                    {/* Add Domain Input */}
                    <div className="mt-4">
                        <sl-input
                            placeholder="Add new domain"
                            onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                    handleAddDomain(e.target.value);
                                    e.target.value = '';
                                }
                            }}
                            style={{ width: '100%' }}
                        ></sl-input>
                        <p className="mt-1 text-sm text-gray-500">
                            Press Enter to add domain
                        </p>
                    </div>

                    {/* Rule Update Status */}
                    {Object.keys(ruleUpdateStatus).length > 0 && (
                        <div className="mt-4 border-t pt-4">
                            <h4 className="font-semibold mb-2">Rule Update Status:</h4>
                            {Object.entries(ruleUpdateStatus).map(([ruleGroupId, status]) => (
                                <sl-card key={ruleGroupId} class="mb-4">
                                    <div className="flex items-center justify-between">
                                        <span className="font-medium">{status.name}</span>
                                        <sl-badge variant={
                                            status.status === 'Updated successfully' 
                                                ? 'success'
                                                : status.status === 'Updating...'
                                                    ? 'info'
                                                    : 'danger'
                                        }>
                                            {status.status}
                                        </sl-badge>
                                    </div>
                                    {status.details && (
                                        <div className="mt-2 text-sm text-gray-600">
                                            {typeof status.details === 'object' 
                                                ? JSON.stringify(status.details, null, 2)
                                                : status.details
                                            }
                                        </div>
                                    )}
                                    <div className="mt-1 text-xs text-gray-500">
                                        {status.timestamp && new Date(status.timestamp).toLocaleString()}
                                    </div>
                                </sl-card>
                            ))}
                        </div>
                    )}

                    {/* Debug Information */}
                    {process.env.NODE_ENV === 'development' && updateDetails.length > 0 && (
                        <sl-details class="mt-4">
                            <div slot="summary" className="text-sm text-gray-600">
                                Debug Information
                            </div>
                            <pre className="mt-2 p-4 bg-gray-50 rounded-lg text-xs overflow-auto max-h-96">
                                {JSON.stringify(updateDetails, null, 2)}
                            </pre>
                        </sl-details>
                    )}

                    <div className="mt-4 text-sm text-gray-600">
                        Last Updated: {new Date(categoryData.imported_at * 1000).toLocaleString()}
                    </div>
                </div>
            )}
            <div slot="footer">
                <sl-button variant="neutral" onClick={() => setShowDetails(false)}>
                    Close
                </sl-button>
            </div>
        </SlDialog>
    </div>
);


}

export { FirewallRules };
