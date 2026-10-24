// Lists category names straight from the `domain` collection through the Foundry UI SDK
// (the object key IS the category name; see categoryKey() in ./keys.js). Pages with the
// `start` cursor and stops as soon as a page adds no new keys, so it is safe even if the
// cursor is ignored.
const PAGE_SIZE = 200;
const MAX_PAGES = 50;

export async function fetchCategoryNames(falcon) {
  const collection = falcon.collection({ collection: 'domain' });
  const names = new Set();
  let start;

  for (let page = 0; page < MAX_PAGES; page++) {
    const resp = await collection.list(start ? { limit: PAGE_SIZE, start } : { limit: PAGE_SIZE });
    const keys = (resp?.resources ?? [])
      .map(k => (typeof k === 'string' ? k : k.category || k._key))
      .filter(Boolean);

    const before = names.size;
    keys.forEach(k => names.add(k));
    if (keys.length < PAGE_SIZE || names.size === before) break;
    start = keys[keys.length - 1];
  }

  return [...names].sort();
}
