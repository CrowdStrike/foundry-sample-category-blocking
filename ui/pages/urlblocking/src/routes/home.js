import React, { useContext, useState, useEffect } from "react";
import { FalconApiContext } from "../contexts/falcon-api-context";
import { categoryKey } from "../utils/keys.js";
import { callFunction } from "../utils/api.js";
import { Link } from '../components/link';
import { SlSpinner, SlSelect, SlOption, SlButton, SlCheckbox, SlTextarea, SlAlert } from '@shoelace-style/shoelace/dist/react';
import '@shoelace-style/shoelace/dist/themes/light.css';
import '@shoelace-style/shoelace/dist/themes/dark.css';
import '@shoelace-style/shoelace/dist/components/input/input.js';






import '@shoelace-style/shoelace/dist/components/badge/badge.js';

// Define consistent form styles
const formStyles = {
  inputBorder: {
    border: '1px solid #B8B7BD',
    borderRadius: '0'
  }
};

function Home() {
  const { falcon, cachedCategories } = useContext(FalconApiContext);
  const [hostGroups, setHostGroups] = useState([]);
  const [categories, setCategories] = useState({});
  const [selectedHostGroup, setSelectedHostGroup] = useState('');
  const [policyName, setPolicyName] = useState('');
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [platform, setPlatform] = useState('');
  const [selectedUrls, setSelectedUrls] = useState('');
  const [categoryDomains, setCategoryDomains] = useState({});
  const [previewedCategories, setPreviewedCategories] = useState([]); // selection the preview was built from
  const [whitelist, setWhitelist] = useState('');
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [simulatorFqdn, setSimulatorFqdn] = useState('');
  const [simulatorResult, setSimulatorResult] = useState(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Host groups are loaded once per visit
  useEffect(() => {
    const loadHostGroups = async () => {
      try {
        setIsLoading(true);
        const hostGroupsBody = await callFunction(falcon, 'GET', '/urlblock');
        if (hostGroupsBody?.host_groups) {
          setHostGroups(hostGroupsBody.host_groups);
        }
      } catch (error) {
        console.error('Error loading host groups:', error);
        setStatus({ type: 'error', message: `Failed to load data: ${error.message}` });
      } finally {
        setIsLoading(false);
      }
    };

    if (falcon) loadHostGroups();
  }, [falcon]);

  // Categories come from the app-wide cache (null until its first load finishes)
  useEffect(() => {
    if (cachedCategories === null) return;
    const categoriesObj = {};
    cachedCategories.forEach(category => { categoriesObj[category] = ''; });
    setCategories(categoriesObj);
    setLoadingCategories(false);
  }, [cachedCategories]);

  // Reads the domains of every selected category and stores them as the current preview.
  // Returns the {category: domains} map used to build the rule.
  const buildPreview = async () => {
    if (!selectedCategories || selectedCategories.length === 0) {
      throw new Error('Please select at least one category');
    }

    const collection = falcon.collection({ collection: 'domain' });
    const urlResults = await Promise.all(selectedCategories.map(async (category) => {
      try {
        const record = await collection.read(categoryKey(category));
        return { category, domain: record?.domain || null };
      } catch (error) {
        console.warn(`Failed to fetch domains for category ${category}:`, error);
        return { category, domain: null };
      }
    }));

    const domainsMap = {};
    urlResults.forEach(({ category, domain }) => {
      if (domain) domainsMap[category] = domain;
    });
    setCategoryDomains(domainsMap);
    setPreviewedCategories([...selectedCategories]);

    const allUrls = Object.values(domainsMap).join(';');
    setSelectedUrls(allUrls);
    if (!allUrls) {
      throw new Error('No domains found for selected categories');
    }
    return domainsMap;
  };

  const handlePreview = async () => {
    try {
      setIsPreviewLoading(true);
      setStatus({ type: 'info', message: 'Loading domains from categories...' });
      await buildPreview();
      setStatus({
        type: 'success',
        message: `Preview generated successfully with domains from ${selectedCategories.length} categories`
      });
    } catch (error) {
      console.error('Preview generation error:', error);
      setStatus({ type: 'error', message: error.message });
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleCreateRule = async () => {
    try {
      if (!selectedHostGroup) throw new Error('Please select a host group');
      if (!policyName) throw new Error('Please enter a policy name');
      if (!platform) throw new Error('Please select a platform');
      if (selectedCategories.length === 0) throw new Error('Please select at least one category');

      setIsCreating(true);

      // The rule is built from the preview: (re)generate it when missing or out of date
      const previewIsCurrent = previewedCategories.length === selectedCategories.length &&
        selectedCategories.every(c => previewedCategories.includes(c));
      let domainsMap = categoryDomains;
      if (!previewIsCurrent || Object.keys(categoryDomains).length === 0) {
        setStatus({ type: 'info', message: 'Loading domains from categories...' });
        domainsMap = await buildPreview();
      }

      const withoutDomains = selectedCategories.filter(c => !domainsMap[c]);
      if (withoutDomains.length > 0) {
        throw new Error(`No domains found for: ${withoutDomains.join(', ')}. Unselect them or fix the categories.`);
      }

      setStatus({ type: 'info', message: 'Creating blocking rule...' });

      const categoriesPayload = {};
      selectedCategories.forEach(category => {
        categoriesPayload[category] = domainsMap[category];
      });

      const hostGroupName = hostGroups.find(g => g.id === selectedHostGroup)?.name;

      const result = await callFunction(falcon, 'POST', '/create-rule', {
        hostGroupId: selectedHostGroup,
        hostGroupName: hostGroupName,
        policyName: policyName,
        platform: platform.toLowerCase(),
        categories: categoriesPayload,
        whitelist: whitelist.trim(),
        // Falcon session user; the backend prefers the request context when it has one
        username: falcon?.data?.user?.username || ''
      });

      setStatus({
        type: 'success',
        message: `Successfully created ${result.rulesCreated} rule(s) and assigned ${selectedCategories.length} categories!`
      });

      // Reset form
      setSelectedHostGroup('');
      setPolicyName('');
      setSelectedCategories([]);
      setPlatform('');
      setSelectedUrls('');
      setCategoryDomains({});
      setPreviewedCategories([]);
      setWhitelist('');

    } catch (error) {
      console.error('Operation failed:', error);
      setStatus({ type: 'error', message: error.message });
    } finally {
      setIsCreating(false);
    }
  };

  // FASE 5: Policy Simulator handler
  const handleSimulate = async () => {
    if (!simulatorFqdn.trim()) return;
    setIsSimulating(true);
    setSimulatorResult(null);
    try {
      // fqdn travels as a query param (request.params.query in the function)
      const fqdn = encodeURIComponent(simulatorFqdn.trim().toLowerCase());
      setSimulatorResult(await callFunction(falcon, 'GET', '/simulate-policy?fqdn=' + fqdn));
    } catch (error) {
      console.error('Simulator error:', error);
      setSimulatorResult({ error: error.message });
    } finally {
      setIsSimulating(false);
    }
  };

  if (isLoading) {

    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <SlSpinner style={{ fontSize: '2rem' }} />
          <p className="mt-4 text-gray-600">Loading data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Form Section - All in one line */}
      <div className="flex items-end space-x-4">
        <div className="flex-1">
          <label className="block text-sm font-bold text-black mb-2">
            Policy name
          </label>
          <input
            type="text"
            value={policyName}
            onChange={(e) => setPolicyName(e.target.value)}
            placeholder="Enter a unique name"
            className="w-full px-3 bg-white outline-none"
            style={{
              fontFamily: 'var(--sl-font-sans)',
              fontSize: 'var(--sl-font-size-medium)',
              height: '40px',
              lineHeight: '40px',
              border: '1px solid #B8B7BD',
              borderRadius: '0'
            }}
          />
        </div>

        <div className="flex-1">
          <label className="block text-sm font-bold text-black mb-2">
            Host group
          </label>
          <SlSelect value={selectedHostGroup} onSlChange={(e) => setSelectedHostGroup(e.target.value)} placeholder="Select">
            
            {hostGroups.map((group) => (
              <SlOption key={group.id} value={group.id}>
                {group.name}
              </SlOption>
            ))}
          </SlSelect>
        </div>


{/* Platform Dropdown */}
<div className="flex-1">
  <label className="block text-sm font-bold text-black mb-2">
    Platform
  </label>
  <SlSelect value={platform} onSlChange={(e) => setPlatform(e.target.value)} placeholder="Select">
    
    <SlOption value="windows">windows</SlOption>
    <SlOption value="mac">mac</SlOption>
    <SlOption value="linux">linux</SlOption>{/* FASE 5: Linux support added */}
  </SlSelect>
</div>

        <SlButton
          variant="primary"
          onClick={handlePreview}
          loading={isPreviewLoading}
          style={{
            '--sl-button-font-size': 'var(--sl-font-size-medium)',
            '--sl-input-height-medium': '40px',
            'background-color': '#e5e7eb',
            'color': 'black',
            'border': 'none',
            'min-width': '120px'
          }}
        >
          Preview Domains
        </SlButton>

        <SlButton
          variant="primary"
          onClick={handleCreateRule}
          loading={isCreating}
          disabled={isPreviewLoading}
          style={{
            '--sl-button-font-size': 'var(--sl-font-size-medium)',
            '--sl-input-height-medium': '40px',
            'background-color': '#e5e7eb',
            'color': 'black',
            'border': 'none',
            'min-width': '160px'
          }}
        >
          Create blocking rule
        </SlButton>
      </div>

      {/* Categories Section with HTML Checkboxes */}
      <div>
        <div className="flex justify-between items-center mb-2">
          <h2 className="text-sm font-medium text-gray-700"><b>Categories to block</b></h2>
          <Link to="/about" className="text-black no-underline text-sm hover:text-gray-600">
            Add custom categories
          </Link>
        </div>
        <div
          className="grid grid-cols-4 gap-x-6 gap-y-2 max-h-[400px] overflow-y-auto p-4"
          style={{
            border: '1px solid #B8B7BD',
            borderRadius: '0'
          }}
        >
          {loadingCategories ? (
            <div className="col-span-4 flex items-center justify-center py-4">
              <SlSpinner style={{ fontSize: '1.5rem' }} />
              <span className="ml-2 text-gray-600">Loading categories...</span>
            </div>
          ) : (
            Object.keys(categories).sort().map((category) => (
              <div key={category} className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id={`category-${category}`}
                  checked={selectedCategories.includes(category)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      setSelectedCategories(prev => [...prev, category]);
                    } else {
                      setSelectedCategories(prev =>
                        prev.filter(c => c !== category)
                      );
                    }
                  }}
                  className="h-4 w-4 text-gray-600 border-gray-300 focus:ring-0"
                />
                <label
                  htmlFor={`category-${category}`}
                  className="text-sm text-gray-700 cursor-pointer select-none"
                >
                  {category}
                </label>
              </div>
            ))
          )}
        </div>
      </div>

      {/* URL Preview Section */}
      <div>
        <h2 className="text-sm font-medium text-gray-700 mb-2"><b>Selected domains preview</b></h2>
        <SlTextarea
          value={selectedUrls}
          readonly
          rows="8"
          placeholder="Select Preview"
          resize="vertical"
          style={{
            '--sl-input-font-size': 'var(--sl-font-size-medium)',
            '--sl-color-neutral-300': '#E0E0E0',
            'width': '100%',
            '--sl-input-border-color': '#B8B7BD',
            '--sl-input-border-radius-medium': '0'
          }}
        ></SlTextarea>
      </div>

      {/* Whitelist Section */}
      <div>
        <h2 className="text-sm font-medium text-gray-700 mb-2">
          <b>Excluded Domains (Whitelist)</b>
        </h2>
        <p className="text-xs text-gray-500 mb-2">
          These domains will be added as an <strong>ALLOW</strong> rule with the highest
          priority. Separate multiple domains with semicolons (;).
        </p>
        <SlTextarea
          value={whitelist}
          onSlInput={(e) => setWhitelist(e.target.value)}
          rows="3"
          placeholder="e.g. exception.com;*.exception.com;intranet.example.com"
          resize="vertical"
          style={{
            '--sl-input-font-size': 'var(--sl-font-size-medium)',
            '--sl-color-neutral-300': '#E0E0E0',
            'width': '100%',
            '--sl-input-border-color': '#B8B7BD',
            '--sl-input-border-radius-medium': '0'
          }}
        ></SlTextarea>
      </div>

      {/* Policy Simulator Section */}
      <div
        style={{
          border: '1px solid #B8B7BD',
          borderRadius: '0',
          padding: '16px'
        }}
      >
        <h2 className="text-sm font-bold text-black mb-2">🔍 Domain Policy Simulator</h2>
        <p className="text-xs text-gray-500 mb-3">
          Enter a domain to check whether it is registered under any blocking category.
        </p>
        <div className="flex items-center space-x-3">
          <input
            type="text"
            value={simulatorFqdn}
            onChange={(e) => setSimulatorFqdn(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSimulate(); }}
            placeholder="e.g. facebook.com"
            className="flex-1 px-3 bg-white outline-none"
            style={{
              fontFamily: 'var(--sl-font-sans)',
              fontSize: 'var(--sl-font-size-medium)',
              height: '40px',
              lineHeight: '40px',
              border: '1px solid #B8B7BD',
              borderRadius: '0'
            }}
          />
          <SlButton
            variant="primary"
            onClick={handleSimulate}
            loading={isSimulating}
            style={{
              '--sl-button-font-size': 'var(--sl-font-size-medium)',
              '--sl-input-height-medium': '40px',
              'background-color': '#e5e7eb',
              'color': 'black',
              'border': 'none',
              'min-width': '120px'
            }}
          >
            Check domain
          </SlButton>
        </div>

        {/* Simulator result badge */}
        {simulatorResult && !isSimulating && (
          <div className="mt-4">
            {simulatorResult.error ? (
              <div
                style={{
                  padding: '10px 14px',
                  background: '#fee2e2',
                  border: '1px solid #fca5a5',
                  borderRadius: '4px',
                  fontSize: '13px',
                  color: '#991b1b'
                }}
              >
                ❌ Error: {simulatorResult.error}
              </div>
            ) : simulatorResult.found ? (
              <div
                style={{
                  padding: '10px 14px',
                  background: '#fef9c3',
                  border: '1px solid #fde047',
                  borderRadius: '4px',
                  fontSize: '13px',
                  color: '#713f12'
                }}
              >
                🚫 <strong>BLOCKED</strong> — {simulatorResult.message}
                <br />
                <span style={{ fontSize: '12px', color: '#92400e' }}>
                  Category: <strong>{simulatorResult.category}</strong>
                </span>
              </div>
            ) : (
              <div
                style={{
                  padding: '10px 14px',
                  background: '#dcfce7',
                  border: '1px solid #86efac',
                  borderRadius: '4px',
                  fontSize: '13px',
                  color: '#166534'
                }}
              >
                ✅ <strong>NOT BLOCKED</strong> — {simulatorResult.message}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Status Messages */}
      {status && (
        <SlAlert
          variant={status.type === 'error' ? 'danger' : status.type === 'success' ? 'success' : 'info'}
          open
          closable
          onSlAfterHide={() => setStatus(null)}
        >
          {status.message}
        </SlAlert>
      )}
    </div>
  );
}

export { Home };










