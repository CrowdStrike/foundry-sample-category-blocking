import React, { useContext, useState, useEffect } from "react";
import { FalconApiContext } from "../contexts/falcon-api-context";
import { Link } from '../components/link';
import { SlSpinner } from "@shoelace-style/shoelace/dist/react";
import '@shoelace-style/shoelace/dist/themes/light.css';
import '@shoelace-style/shoelace/dist/components/input/input.js';
import '@shoelace-style/shoelace/dist/components/select/select.js';
import '@shoelace-style/shoelace/dist/components/option/option.js';
import '@shoelace-style/shoelace/dist/components/button/button.js';
import '@shoelace-style/shoelace/dist/components/checkbox/checkbox.js';
import '@shoelace-style/shoelace/dist/components/textarea/textarea.js';
import '@shoelace-style/shoelace/dist/components/alert/alert.js';
import '@shoelace-style/shoelace/dist/components/select/select.js';
import '@shoelace-style/shoelace/dist/components/option/option.js';

// Define consistent form styles
const formStyles = {
  inputBorder: {
    border: '1px solid #B8B7BD',
    borderRadius: '0'
  }
};

function Home() {
  const { falcon } = useContext(FalconApiContext);
  const [hostGroups, setHostGroups] = useState([]);
  const [categories, setCategories] = useState({});
  const [selectedHostGroup, setSelectedHostGroup] = useState('');
  const [policyName, setPolicyName] = useState('');
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [selectedUrls, setSelectedUrls] = useState('');
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  // At the top of your component
  useEffect(() => {
    console.log('Selected categories updated:', selectedCategories);
  }, [selectedCategories]); // Add this effect to monitor state changes

  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);
        setLoadingCategories(true);
        console.log("Starting to load data");

        // Load host groups
        const config = {
          name: 'urlblock',
          version: 1
        };

        const cloudFunction = falcon.cloudFunction(config);
        const hostGroupsResponse = await cloudFunction.path('/urlblock').get();

        if (hostGroupsResponse?.body?.host_groups) {
          console.log("Host groups loaded:", hostGroupsResponse.body.host_groups);
          setHostGroups(hostGroupsResponse.body.host_groups);
        }

        // Load categories directly from collection
        const collection = falcon.collection({
          collection: 'domain'
        });

        console.log("Fetching categories from collection");
        const response = await collection.list({
          limit: 100
        });

        console.log("Collection response:", response);

        if (response && response.resources && Array.isArray(response.resources)) {
          // Create categories object with empty domains initially
          const categoriesObj = {};
          response.resources.forEach(category => {
            if (typeof category === 'string') {
              categoriesObj[category] = ''; // Initialize with empty string
            }
          });

          console.log("Processed categories:", categoriesObj);
          setCategories(categoriesObj);
        }

      } catch (error) {
        console.error('Error loading data:', error);
        setStatus({
          type: 'error',
          message: `Failed to load data: ${error.message}`
        });
      } finally {
        setIsLoading(false);
        setLoadingCategories(false);
      }
    };

    if (falcon) {
      loadData();
    }
  }, [falcon]);

  const handlePreview = async () => {
    try {
      // Debug logging
      console.log('HandlePreview called');
      console.log('Selected Categories State:', selectedCategories);
      console.log('Selected Categories Length:', selectedCategories.length);

      if (!selectedCategories || selectedCategories.length === 0) {
        console.log('No categories selected, throwing error');
        throw new Error('Please select at least one category');
      }

      setIsPreviewLoading(true);
      setStatus({
        type: 'info',
        message: 'Loading URLs from categories...'
      });

      const collection = falcon.collection({
        collection: 'domain'
      });

      // Fetch URLs for all selected categories
      const urlPromises = selectedCategories.map(async (category) => {
        try {
          const objectKey = category;
          console.log(`Fetching URLs for category: ${category}, key: ${objectKey}`);

          const record = await collection.read(objectKey);
          console.log(`Record for ${category}:`, record);

          // Access the domain directly from the record
          if (record && record.domain) {
            return record.domain;
          }
          return null;
        } catch (error) {
          console.warn(`Failed to fetch URLs for category ${category}:`, error);
          return null;
        }
      });

      const urlResults = await Promise.all(urlPromises);
      const urls = urlResults.filter(Boolean).join(';');

      if (!urls) {
        throw new Error('No URLs found for selected categories');
      }

      console.log('Combined URLs:', urls);
      setSelectedUrls(urls);
      setStatus({
        type: 'success',
        message: `Preview generated successfully with URLs from ${selectedCategories.length} categories`
      });

    } catch (error) {
      console.error('Preview generation error:', error);
      setStatus({
        type: 'error',
        message: error.message
      });
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const createRelationshipInCollection = async (relationshipData) => {
    try {
      // Initialize the relationship collection
      const relationshipCollection = falcon.collection({
        collection: 'relationship'
      });

      // Generate a unique key for the relationship
      const randomBytes = new Uint32Array(1);
      crypto.getRandomValues(randomBytes);
      const relationshipKey = `rel-${Date.now()}-${randomBytes[0].toString(36)}`;

      // Ensure the data matches the schema exactly
      const formattedData = {
        category_name: relationshipData.category_name,
        rule_group_id: relationshipData.rule_group_id,
        rule_group_name: relationshipData.rule_group_name,
        host_group_id: relationshipData.host_group_id,
        host_group_name: relationshipData.host_group_name,
        policy_name: relationshipData.policy_name,
        created_at: new Date().toISOString(),
        created_by: falcon.data.user.username
      };

      // Write to collection
      const result = await relationshipCollection.write(relationshipKey, formattedData);
      console.log(`Relationship created with key ${relationshipKey}:`, result);
      return result;

    } catch (error) {
      console.error('Error creating relationship in collection:', error);
      throw error;
    }
  };

  const handleCreateRule = async () => {
    try {
      if (!selectedHostGroup) throw new Error('Please select a host group');
      if (!policyName) throw new Error('Please enter a policy name');
      if (!selectedUrls) throw new Error('Please preview URLs first');

      setStatus({
        type: 'info',
        message: 'Creating blocking rule...'
      });

      // Create rule using existing cloud function
      const config = {
        name: 'urlblock',
        version: 1
      };

      const cloudFunction = falcon.cloudFunction(config);
      const response = await cloudFunction.path('/create-rule').post({
        hostGroupId: selectedHostGroup,
        urls: selectedUrls,
        policyName: policyName
      });

      console.log('Rule creation response:', response);

      // Get host group name
      const hostGroupName = hostGroups.find(g => g.id === selectedHostGroup)?.name;

      // Create relationship in collection for each selected category
      const relationshipPromises = selectedCategories.map(category => {
        const relationshipData = {
          category_name: category,
          rule_group_id: response.body.ruleGroupId,
          rule_group_name: `${policyName}_RuleGroup`,
          host_group_id: selectedHostGroup,
          host_group_name: hostGroupName,
          policy_name: policyName,
          created_at: new Date().toISOString(),
          created_by: falcon.data.user.username
        };

        return createRelationshipInCollection(relationshipData);
      });

      // Wait for all relationship to be created
      await Promise.all(relationshipPromises);

      setStatus({
        type: 'success',
        message: `Successfully created blocking rule and ${selectedCategories.length} relationship!`
      });

      // Reset form
      setSelectedHostGroup('');
      setPolicyName('');
      setSelectedCategories([]);
      setSelectedUrls('');

    } catch (error) {
      console.error('Operation failed:', error);
      setStatus({
        type: 'error',
        message: error.message
      });
    }
  };

  const validateRelationshipData = (data) => {
    const requiredFields = ['category_name', 'rule_group_id', 'host_group_id'];
    const missingFields = requiredFields.filter(field => !data[field]);

    if (missingFields.length > 0) {
      throw new Error(`Missing required fields: ${missingFields.join(', ')}`);
    }

    return true;
  };

  const queryrelationship = async (filter) => {
    try {
      const relationshipCollection = falcon.collection({
        collection: 'relationship'
      });

      const response = await relationshipCollection.search({
        filter: filter // e.g., "category_name:'YourCategory'"
      });

      return response.resources;
    } catch (error) {
      console.error('Error querying relationship:', error);
      throw error;
    }
  };

  const generateRelationshipKey = (prefix = 'rel') => {
    const randomBytes = new Uint32Array(1);
    crypto.getRandomValues(randomBytes);
    return `${prefix}-${Date.now()}-${randomBytes[0].toString(36)}`;
  };

  const formatDate = (date = new Date()) => {
    return date.toISOString();
  };

  const batchUpdaterelationship = async (updates) => {
    const relationshipCollection = falcon.collection({
      collection: 'relationship'
    });

    const updatePromises = updates.map(({ key, data }) =>
      relationshipCollection.write(key, data)
    );

    return Promise.all(updatePromises);
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
          <select
            value={selectedHostGroup}
            onChange={(e) => setSelectedHostGroup(e.target.value)}
            className="w-full px-3 bg-white outline-none appearance-none"
            style={{
              fontFamily: 'var(--sl-font-sans)',
              fontSize: 'var(--sl-font-size-medium)',
              height: '40px',
              lineHeight: '40px',
              border: '1px solid #B8B7BD',
              borderRadius: '0'
            }}
          >
            <option value="">Select</option>
            {hostGroups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </div>

        <sl-button
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
        </sl-button>

        <sl-button
          variant="primary"
          onClick={handleCreateRule}
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
        </sl-button>
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
        <h2 className="text-sm font-medium text-gray-700 mb-2"><b>Selected URLs preview</b></h2>
        <sl-textarea
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
        ></sl-textarea>
      </div>

      {/* Status Messages */}
      {status && (
        <sl-alert
          variant={status.type === 'error' ? 'danger' : status.type === 'success' ? 'success' : 'info'}
          closable
          onSlAfterHide={() => setStatus(null)}
        >
          {status.message}
        </sl-alert>
      )}
    </div>
  );
}

export { Home };

