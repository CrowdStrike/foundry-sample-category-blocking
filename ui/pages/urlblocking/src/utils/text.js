// Same as plural() in functions/urlblock/app_utils.py: '1 rule', '2 rules' (or pluralForm)
export function plural(count, singular, pluralForm) {
  return `${count} ${count === 1 ? singular : (pluralForm || `${singular}s`)}`;
}
