import React, { useState, useEffect, useContext, useRef } from 'react';
import { FalconApiContext } from '../contexts/falcon-api-context';
import { categoryKey } from '../utils/keys.js';
import { callFunction } from '../utils/api.js';
import { plural } from '../utils/text.js';
import {
  SlButton,
  SlDialog,
  SlTextarea,
  SlSpinner,
  SlAlert,
  SlBadge,
} from '@shoelace-style/shoelace/dist/react';
import '@shoelace-style/shoelace/dist/themes/light.css';
import '@shoelace-style/shoelace/dist/themes/dark.css';

// ─── Styles ────────────────────────────────────────────────────────────────

const inputStyle = {
  fontFamily: 'var(--sl-font-sans)',
  fontSize: 'var(--sl-font-size-medium)',
  height: '40px',
  lineHeight: '40px',
  border: '1px solid #B8B7BD',
  borderRadius: '0',
  width: '100%',
  padding: '0 12px',
  background: 'white',
  outline: 'none',
  boxSizing: 'border-box',
};

const selectStyle = {
  ...inputStyle,
  appearance: 'none',
};

// ─── Platform badge colors ──────────────────────────────────────────────────

const platformVariant = (p) => {
  if (p === 'windows') return 'primary';
  if (p === 'mac') return 'success';
  if (p === 'linux') return 'warning';
  return 'neutral';
};

// ─── Component ─────────────────────────────────────────────────────────────

function FirewallRules() {
  const { falcon, cachedCategories } = useContext(FalconApiContext);

  // ── Table state
  const [policies, setPolicies]         = useState([]);
  const [isLoading, setIsLoading]       = useState(true);
  const [tableError, setTableError]     = useState(null);
  const [deletingId, setDeletingId]     = useState(null);
  const [deleteStatus, setDeleteStatus] = useState(null); // {type, message}

  // ── Available categories (for edit modal checkboxes)
  const [allCategories, setAllCategories] = useState([]);

  // ── Edit modal state
  const [editOpen, setEditOpen]           = useState(false);
  const [editPolicy, setEditPolicy]       = useState(null); // policy being edited
  const [editCategories, setEditCategories] = useState([]); // selected category names
  const [editWhitelist, setEditWhitelist]   = useState('');
  const [isSaving, setIsSaving]             = useState(false);
  const [saveStatus, setSaveStatus]         = useState(null); // {type, message}

  const dialogRef = useRef(null);

  // ── Load policies on mount
  useEffect(() => {
    loadPolicies();
  }, []);

  // Categories come from the app-wide cache (null until its first load finishes)
  useEffect(() => {
    if (cachedCategories !== null) setAllCategories(cachedCategories);
  }, [cachedCategories]);

  // ─────────────────────────────────────────────────────────────────────────
  // Data fetchers
  // ─────────────────────────────────────────────────────────────────────────


  const loadPolicies = async () => {
    setIsLoading(true);
    setTableError(null);
    try {
      const body = await callFunction(falcon, 'GET', '/list-policies');
      setPolicies(body?.policies ?? []);
    } catch (err) {
      console.error('loadPolicies error:', err);
      setTableError('Could not load policies. Try reloading the page.');
    } finally {
      setIsLoading(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Delete handler
  // ─────────────────────────────────────────────────────────────────────────

  const handleDelete = async (ruleGroupId, policyName) => {
    if (!window.confirm(`Delete policy "${policyName}"? This action cannot be undone.`)) {
      return;
    }
    setDeletingId(ruleGroupId);
    setDeleteStatus(null);
    try {
      // The backend resolves the policy from its own records for this rule group
      let result;
      try {
        result = await callFunction(falcon, 'POST', '/delete-policy', { rule_group_id: ruleGroupId });
      } catch (err) {
        // 409: a legacy record whose Falcon policy can't be confirmed. Offer to stop tracking it
        if (err.status !== 409 || !window.confirm(
          `${err.message}\n\nRemove "${policyName}" from this app only? Nothing will be changed in Falcon.`)) {
          throw err;
        }
        result = await callFunction(falcon, 'POST', '/delete-policy',
                                    { rule_group_id: ruleGroupId, forget_record: true });
      }
      await loadPolicies();
      if (result?.warnings?.length) {
        setDeleteStatus({ type: 'warning', message: 'Policy deleted with warnings: ' + result.warnings.join(' ') });
      }
    } catch (err) {
      console.error('handleDelete error:', err);
      alert('Failed to delete policy: ' + err.message);
    } finally {
      setDeletingId(null);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Edit modal handlers
  // ─────────────────────────────────────────────────────────────────────────

  const openEdit = (policy) => {
    setEditPolicy(policy);
    setEditCategories([...policy.categories]);
    setEditWhitelist(policy.whitelist ?? '');
    setSaveStatus(null);
    setEditOpen(true);
  };

  const toggleCategory = (cat) => {
    setEditCategories(prev =>
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  const handleSave = async () => {
    if (editCategories.length === 0) {
      setSaveStatus({ type: 'warning', message: 'Select at least one category.' });
      return;
    }

    setIsSaving(true);
    setSaveStatus(null);
    try {
      // 1. Resolve domains for each selected category
      const collection = falcon.collection({ collection: 'domain' });
      const categoriesPayload = {};

      await Promise.all(editCategories.map(async (cat) => {
        try {
          const record = await collection.read(categoryKey(cat));
          if (record?.domain) {
            categoriesPayload[cat] = record.domain;
          }
        } catch (err) {
          console.error(`Could not read domains for category ${cat}:`, err);
        }
      }));

      // Never update with a smaller set: the rule group would silently stop blocking those categories
      const withoutDomains = editCategories.filter(c => !categoriesPayload[c]);
      if (withoutDomains.length > 0) {
        setSaveStatus({
          type: 'danger',
          message: `No domains found for: ${withoutDomains.join(', ')}. Unselect them or fix the categories. The policy was not changed.`
        });
        return;
      }

      // 2. Call update-policy
      const result = await callFunction(falcon, 'POST', '/update-policy', {
        ruleGroupId: editPolicy.rule_group_id,
        policyName:  editPolicy.policy_name,
        hostGroupId: editPolicy.host_group_id,
        hostGroupName: editPolicy.host_group_name,
        platform:    editPolicy.platform,
        categories:  categoriesPayload,
        whitelist:   editWhitelist.trim(),
        username:    falcon?.data?.user?.username || '',
      });

      await loadPolicies();
      if (result?.warnings?.length) {
        setSaveStatus({ type: 'warning', message: 'Policy updated with warnings: ' + result.warnings.join(' ') });
        return;
      }
      setSaveStatus({ type: 'success', message: 'Policy updated successfully!' });

      // Close modal after short delay
      setTimeout(() => {
        setEditOpen(false);
        setSaveStatus(null);
      }, 1500);

    } catch (err) {
      console.error('handleSave error:', err);
      setSaveStatus({ type: 'danger', message: 'Failed to update policy: ' + err.message });
    } finally {
      setIsSaving(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-black">Active Blocking Policies</h2>
        <SlButton
          size="small"
          onClick={loadPolicies}
          disabled={isLoading}
          style={{ '--sl-input-height-small': '32px' }}
        >
          {isLoading ? <SlSpinner style={{ fontSize: '1rem' }} /> : '↻ Refresh'}
        </SlButton>
      </div>

      {/* ── Error banner ────────────────────────────────────────────────── */}
      {tableError && (
        <SlAlert variant="danger" open closable onSlAfterHide={() => setTableError(null)}>
          {tableError}
        </SlAlert>
      )}

      {/* ── Delete warnings ─────────────────────────────────────────────── */}
      {deleteStatus && (
        <SlAlert variant={deleteStatus.type} open closable onSlAfterHide={() => setDeleteStatus(null)}>
          {deleteStatus.message}
        </SlAlert>
      )}

      {/* ── Loading ─────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <SlSpinner style={{ fontSize: '2rem' }} />
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {!isLoading && policies.length === 0 && !tableError && (
        <div
          className="text-center py-12 text-gray-500 text-sm"
          style={{ border: '1px solid #B8B7BD' }}
        >
          No active policies found. Create one from the <strong>Category Blocking Policy</strong> tab.
        </div>
      )}

      {/* ── Policies table ──────────────────────────────────────────────── */}
      {!isLoading && policies.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '13px',
              border: '1px solid #B8B7BD',
            }}
          >
            <thead>
              <tr style={{ background: '#f9f9f9', borderBottom: '2px solid #B8B7BD' }}>
                {['Policy Name', 'Host Group', 'Platform', 'Categories', 'Whitelist', 'Actions'].map(h => (
                  <th
                    key={h}
                    style={{
                      padding: '10px 12px',
                      textAlign: 'left',
                      fontWeight: 600,
                      color: '#111',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {policies.map((pol, i) => (
                <tr
                  key={pol.rule_group_id}
                  style={{
                    borderBottom: '1px solid #E5E7EB',
                    background: i % 2 === 0 ? '#fff' : '#fafafa',
                  }}
                >
                  {/* Policy Name */}
                  <td style={{ padding: '10px 12px', fontWeight: 500 }}>
                    {pol.policy_name || '—'}
                  </td>

                  {/* Host Group */}
                  <td style={{ padding: '10px 12px', color: '#555' }}>
                    {pol.host_group_name || pol.host_group_id || '—'}
                  </td>

                  {/* Platform */}
                  <td style={{ padding: '10px 12px' }}>
                    <SlBadge variant={platformVariant(pol.platform)} pill>
                      {pol.platform || '—'}
                    </SlBadge>
                  </td>

                  {/* Categories */}
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {(pol.categories ?? []).map(cat => (
                        <span
                          key={cat}
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            background: '#e5e7eb',
                            borderRadius: '12px',
                            fontSize: '11px',
                            color: '#374151',
                          }}
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  </td>

                  {/* Whitelist preview */}
                  <td style={{ padding: '10px 12px', color: '#555', maxWidth: '220px' }}>
                    {pol.whitelist ? (
                      <span
                        style={{
                          display: 'block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={pol.whitelist}
                      >
                        {pol.whitelist}
                      </span>
                    ) : (
                      <span style={{ color: '#aaa', fontStyle: 'italic' }}>None</span>
                    )}
                  </td>

                  {/* Actions */}
                  <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                    <SlButton
                      size="small"
                      variant="neutral"
                      onClick={() => openEdit(pol)}
                      style={{ marginRight: '6px' }}
                    >
                      ✏️ Edit
                    </SlButton>
                    <SlButton
                      size="small"
                      variant="danger"
                      loading={deletingId === pol.rule_group_id}
                      onClick={() => handleDelete(pol.rule_group_id, pol.policy_name)}
                    >
                      🗑 Delete
                    </SlButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Edit Modal ──────────────────────────────────────────────────── */}
      <SlDialog
        ref={dialogRef}
        open={editOpen}
        label={`Edit policy: ${editPolicy?.policy_name ?? ''}`}
        style={{ '--width': '700px' }}
        onSlAfterHide={() => {
          setEditOpen(false);
          setSaveStatus(null);
        }}
      >
        {editPolicy && (
          <div className="space-y-5">

            {/* Read-only metadata */}
            <div
              className="grid grid-cols-3 gap-4"
              style={{ fontSize: '13px', color: '#555' }}
            >
              <div>
                <div style={{ fontWeight: 600, color: '#111', marginBottom: '2px' }}>Policy name</div>
                <div style={{ padding: '8px 12px', border: '1px solid #B8B7BD', background: '#f5f5f5' }}>
                  {editPolicy.policy_name}
                </div>
              </div>
              <div>
                <div style={{ fontWeight: 600, color: '#111', marginBottom: '2px' }}>Host group</div>
                <div style={{ padding: '8px 12px', border: '1px solid #B8B7BD', background: '#f5f5f5' }}>
                  {editPolicy.host_group_name || editPolicy.host_group_id}
                </div>
              </div>
              <div>
                <div style={{ fontWeight: 600, color: '#111', marginBottom: '2px' }}>Platform</div>
                <div style={{ padding: '8px 12px', border: '1px solid #B8B7BD', background: '#f5f5f5' }}>
                  {editPolicy.platform}
                </div>
              </div>
            </div>

            {/* Categories checkboxes */}
            <div>
              <div style={{ fontWeight: 600, color: '#111', marginBottom: '6px', fontSize: '13px' }}>
                Categories to block
              </div>
              <div
                style={{
                  border: '1px solid #B8B7BD',
                  padding: '12px',
                  maxHeight: '260px',
                  overflowY: 'auto',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: '6px 20px',
                }}
              >
                {allCategories.length === 0 ? (
                  <div className="col-span-3 text-center py-4">
                    <SlSpinner style={{ fontSize: '1.2rem' }} />
                  </div>
                ) : (
                  allCategories.sort().map(cat => (
                    <div key={cat} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        type="checkbox"
                        id={`edit-cat-${cat}`}
                        checked={editCategories.includes(cat)}
                        onChange={() => toggleCategory(cat)}
                        style={{ width: '14px', height: '14px', cursor: 'pointer' }}
                      />
                      <label
                        htmlFor={`edit-cat-${cat}`}
                        style={{ fontSize: '12px', cursor: 'pointer', color: '#374151' }}
                      >
                        {cat}
                      </label>
                    </div>
                  ))
                )}
              </div>
              <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '4px' }}>
                {plural(editCategories.length, 'category', 'categories')} selected
              </div>
            </div>

            {/* Whitelist */}
            <div>
              <div style={{ fontWeight: 600, color: '#111', marginBottom: '4px', fontSize: '13px' }}>
                Excluded Domains (Whitelist)
              </div>
              <p style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '6px' }}>
                These domains will be added as an <strong>ALLOW</strong> rule with highest priority.
                Separate with semicolons (;).
              </p>
              <SlTextarea
                value={editWhitelist}
                onSlInput={(e) => setEditWhitelist(e.target.value)}
                rows="3"
                placeholder="e.g. excepcion.com;*.excepcion.com"
                resize="vertical"
                style={{
                  '--sl-input-font-size': 'var(--sl-font-size-medium)',
                  'width': '100%',
                  '--sl-input-border-color': '#B8B7BD',
                  '--sl-input-border-radius-medium': '0',
                }}
              />
            </div>

            {/* Save status */}
            {saveStatus && (
              <SlAlert
                variant={saveStatus.type === 'warning' ? 'warning' : saveStatus.type === 'success' ? 'success' : 'danger'}
                open
              >
                {saveStatus.message}
              </SlAlert>
            )}
          </div>
        )}

        {/* Dialog footer */}
        <div slot="footer" style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <SlButton
            variant="neutral"
            onClick={() => setEditOpen(false)}
            disabled={isSaving}
          >
            Cancel
          </SlButton>
          <SlButton
            variant="primary"
            onClick={handleSave}
            loading={isSaving}
            style={{
              '--sl-button-font-size': 'var(--sl-font-size-medium)',
              'background-color': '#1a73e8',
              'color': 'white',
            }}
          >
            Save changes
          </SlButton>
        </div>
      </SlDialog>
    </div>
  );
}

export { FirewallRules };
