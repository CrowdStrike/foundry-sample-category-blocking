// Must match category_key() in functions/urlblock/app_utils.py (case is preserved)
export function categoryKey(name) {
  return String(name).trim().replace(/[^A-Za-z0-9_]/g, '_');
}
