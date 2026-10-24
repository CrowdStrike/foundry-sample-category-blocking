import React, { useState, useContext, useRef } from "react";
import { SlAlert, SlButton } from "@shoelace-style/shoelace/dist/react";
import { FalconApiContext } from "../contexts/falcon-api-context";
import { callFunction } from "../utils/api.js";

function About() {
  const { falcon, refreshCategories } = useContext(FalconApiContext);
  const [categoryName, setCategoryName] = useState('');
  const [urls, setUrls] = useState('');
  const [status, setStatus] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // CSV import
  const fileInputRef = useRef(null);
  const [csvFile, setCsvFile] = useState(null);
  const [isImporting, setIsImporting] = useState(false);
  const [importStatus, setImportStatus] = useState(null);

  const handleImportCsv = async () => {
    if (!csvFile) return;
    try {
      setIsImporting(true);
      setImportStatus(null);
      const csv = await csvFile.text();
      const b = await callFunction(falcon, 'POST', '/import-csv', { csv });
      setImportStatus({
        type: b.failed_imports > 0 ? 'warning' : 'success',
        message: `Imported ${b.successful_imports} categories (${b.domains_imported} domains) from ${b.total_rows} rows` +
          (b.failed_imports > 0 ? `; ${b.failed_imports} rows/categories failed (see function logs).` : '.')
      });
      setCsvFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      refreshCategories?.();
    } catch (error) {
      console.error('Import CSV error:', error);
      setImportStatus({ type: 'error', message: `Error: ${error.message}` });
    } finally {
      setIsImporting(false);
    }
  };

  const handleCreateCategory = async () => {
    try {
      setIsLoading(true);

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

      const result = await callFunction(falcon, 'POST', '/manage-category', {
        categoryName: categoryName.trim(),
        urls: cleanedUrls
      });

      setStatus({
        type: 'success',
        message: `Category created successfully with ${result.urlCount || 0} URLs!`
      });
      // Clear form
      setCategoryName('');
      setUrls('');
      refreshCategories?.();
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
            Domains (comma-separated)
          </label>
          <textarea
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
            placeholder="Enter domains separated by commas (e.g., example.com, test.com, domain.com)"
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
        <SlButton
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
        </SlButton>

        {/* Status Message */}
        {status && (
          <SlAlert
            variant={status.type === 'error' ? 'danger' : 'success'}
            open
            closable
            onSlAfterHide={() => setStatus(null)}
          >
            {status.message}
          </SlAlert>
        )}

        {/* Import CSV */}
        <div className="form-group" style={{ borderTop: '1px solid #E5E7EB', paddingTop: '24px' }}>
          <h2 className="text-lg font-semibold text-black mb-2 text-left">Import categories from CSV</h2>
          <p className="mb-2 text-sm text-gray-600">
            Format: <code>category,url</code> with a header row and one domain per row
            (e.g. <code>Games,steam.com</code>). Rows of the same category are merged and
            <code> *.domain</code> wildcards are added automatically. Existing categories are replaced.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => { setCsvFile(e.target.files?.[0] ?? null); setImportStatus(null); }}
            className="block mb-3 text-sm text-black"
          />
          <SlButton
            variant="primary"
            onClick={handleImportCsv}
            loading={isImporting}
            disabled={!csvFile}
            style={{
              '--sl-button-font-size': 'var(--sl-font-size-medium)',
              '--sl-input-height-medium': '48px',
              'background-color': '#e5e7eb',
              'color': 'black',
              'border': 'none',
              'width': '15%'
            }}
          >
            {isImporting ? 'Importing...' : 'Import CSV'}
          </SlButton>
          {importStatus && (
            <SlAlert
              className="mt-3"
              variant={importStatus.type === 'error' ? 'danger' : importStatus.type}
              open
              closable
              onSlAfterHide={() => setImportStatus(null)}
            >
              {importStatus.message}
            </SlAlert>
          )}
        </div>
      </div>
    </div>
  );
}


export { About };
