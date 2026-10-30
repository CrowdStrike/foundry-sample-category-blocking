import FalconApi from '@crowdstrike/foundry-js';
import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import { fetchCategoryNames } from '../utils/categories.js';

const FalconApiContext = createContext(null);

function useFalconApiContext() {
  const [isInitialized, setIsInitialized] = useState(false);
  const [cachedCategories, setCachedCategories] = useState(null);
  
  const falcon = useMemo(() => new FalconApi(), []);
  const navigation = useMemo(() => falcon.isConnected ? falcon.navigation : undefined, [falcon.isConnected]);

  // (Re)load the category names cache; call after creating/importing categories
  const refreshCategories = useCallback(async () => {
    try {
      setCachedCategories(await fetchCategoryNames(falcon));
    } catch (err) {
      console.error("Failed to load categories cache", err);
      setCachedCategories(prev => prev ?? []);  // stop waiting; pages show no categories
    }
  }, [falcon]);

  useEffect(() => {
    (async () => {
      await falcon.connect();
      setIsInitialized(true);
      refreshCategories();
    })();
  }, [falcon, refreshCategories]);

  return { falcon, navigation, isInitialized, cachedCategories, refreshCategories };
}

export { useFalconApiContext, FalconApiContext };
