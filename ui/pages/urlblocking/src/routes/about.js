import React, { useState, useContext } from "react";
import { SlAlert } from "@shoelace-style/shoelace/dist/react";
import { FalconApiContext } from "../contexts/falcon-api-context";

function About() {
  const { falcon } = useContext(FalconApiContext);
  const [categoryName, setCategoryName] = useState('');
  const [urls, setUrls] = useState('');
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleCreateCategory = async () => {
    try {
      setIsLoading(true);
      console.log('Starting category creation');

      if (!categoryName.trim()) {
        throw new Error('Please enter a category name');
      }
      if (!urls.trim()) {
        throw new Error('Please enter at least one URL');
      }

      // Clean up URLs: remove extra spaces and empty entries
      const cleanedUrls = urls
        .split(',')
        .map(url => url.trim())
        .filter(url => url.length > 0)
        .join(',');

      const config = {
        name: 'urlblock',
        version: 1
      };
      
      const cloudFunction = falcon.cloudFunction(config);

      console.log('Sending request with:', {
        categoryName: categoryName.trim(),
        urls: cleanedUrls
      });

      const response = await cloudFunction.path('/manage-category').post({
        categoryName: categoryName.trim(),
        urls: cleanedUrls
      });

      console.log('Response:', response);

      if (response.code === 200) {
        setStatus({
          type: 'success',
          message: `Category created successfully with ${response.body.urlCount || 0} URLs!`
        });
        // Clear form
        setCategoryName('');
        setUrls('');
      } else {
        throw new Error(response.body.error || 'Failed to create category');
      }
    } catch (error) {
      console.error('Error in handleCreateCategory:', error);
      setStatus({
        type: 'error',
        message: `Error: ${error.message}`
      });
    } finally {
      setIsLoading(false);
    }
  };


return (
    <div className="container mx-auto p-4">
        <h2 className="text-lg font-semibold text-black mb-4 text-left">Create custom category</h2>
      
      <div className="space-y-6">
        {/* Category Name Input */}
        <div className="form-group">
          <label className="block text-sm font-bold text-black mb-2">
            Category Name
          </label>
          <input
            type="text"
            value={categoryName}
            onChange={(e) => setCategoryName(e.target.value)}
            placeholder="Enter category name"
            className="w-1/2 py-3 px-4 bg-white border border-gray-300 focus:border-gray-400 outline-none"
            style={{
              fontFamily: 'var(--sl-font-sans)',
              fontSize: 'var(--sl-font-size-medium)',
              height: '40px',
              lineHeight: '40px',
    border: '1px solid #B8B7BD',  // Added this line
    borderRadius: '0'  
            }}
          />
        </div>

        {/* URLs Input */}
        <div className="form-group">
          <label className="block text-sm font-bold text-black mb-2">
            URLs (comma-separated)
          </label>
          <textarea
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
            placeholder="Enter URLs separated by commas (e.g., example.com, test.com, domain.com)"
            rows="6"
            className="w-1/2 py-3 px-4 bg-white border border-gray-300 focus:border-gray-400 outline-none font-mono text-sm"
            style={{
              fontFamily: 'var(--sl-font-sans)',
              fontSize: 'var(--sl-font-size-medium)',
              height: '70px',
              lineHeight: '70px',
    border: '1px solid #B8B7BD',  // Added this line
    borderRadius: '0'  
            }}
          />
          <p className="mt-2 text-sm text-gray-600">
            Example: example.com, test.com, domain.com
          </p>
        </div>

        {/* Create Button */}
        <sl-button
          variant="primary"
          onClick={handleCreateCategory}
          loading={isLoading}
          style={{
            '--sl-button-font-size': 'var(--sl-font-size-medium)',
            '--sl-input-height-medium': '48px',
            'background-color': '#e5e7eb',
            'color': 'black',
            'border': 'none',
            'width': '15%'
          }}
        >
          {isLoading ? 'Creating Category...' : 'Create Category'}
        </sl-button>

        {/* Status Message */}
        {status && (
          <sl-alert
            variant={status.type === 'error' ? 'danger' : 'success'}
            closable
            onSlAfterHide={() => setStatus(null)}
          >
            {status.message}
          </sl-alert>
        )}
      </div>
    </div>
  );
}


export { About };
