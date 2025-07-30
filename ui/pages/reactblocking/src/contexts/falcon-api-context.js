// import FalconApi from '@crowdstrike/foundry-js';
// import { createContext, useEffect, useMemo, useState } from 'react';

// const FalconApiContext = createContext(null);

// function useFalconApiContext() {
//   console.log("useFalconApiContext called"); 
//   const [isInitialized, setIsInitialized] = useState(false);
//   const [cloudFunction, setCloudFunction] = useState(null);
//   const falcon = useMemo(() => new FalconApi(), []);
//   console.log("Creating new FalconApi instance");
//   const navigation = useMemo(() => falcon.isConnected ? falcon.navigation : undefined, [falcon.isConnected]);

//   useEffect(() => {
//     (async () => {
//       try {
//         await falcon.connect();
        
//         // Initialize cloud function
//         const config = {
//           name: 'reactblock',
//           version: 1
//         };
//         setCloudFunction(falcon.cloudFunction(config));
//         setIsInitialized(true);
//       } catch (error) {
//         console.error('Failed to initialize Falcon API:', error);
//       }
//     })();
//   }, []);

//   // Add API functions for URL blocking
//   const api = useMemo(() => ({
//     // Get host groups
//     async getHostGroups() {
//       if (!cloudFunction) throw new Error('Cloud function not initialized');
//       const response = await cloudFunction.path('/reactblock').get();
//       return response.body.host_groups || [];
//     },

//     // Get categories
//     async getCategories() {
//       if (!cloudFunction) throw new Error('Cloud function not initialized');
//       const response = await cloudFunction.path('/categories').get();
//       return response.body.categories || {};
//     },

//     // Create blocking rule
//     async createRule(hostGroupId, urls, policyName) {
//       if (!cloudFunction) throw new Error('Cloud function not initialized');
//       return await cloudFunction.path('/create-rule').post({
//         hostGroupId,
//         urls,
//         policyName
//       });
//     },

//     // Create custom category
//     async createCategory(categoryName, urls) {
//       if (!cloudFunction) throw new Error('Cloud function not initialized');
//       return await cloudFunction.path('/create-category').post({
//         categoryName,
//         urls
//       });
//     }
//   }), [cloudFunction]);

//   return { 
//     falcon, 
//     navigation, 
//     isInitialized,
//     cloudFunction,
//     api 
//   };
// }

// // Custom hook for using the API
// function useUrlBlocking() {
//   const context = useFalconApiContext();
//   if (!context) {
//     throw new Error('useUrlBlocking must be used within a FalconApiContext.Provider');
//   }
//   return context.api;
// }

// export { useFalconApiContext, FalconApiContext, useUrlBlocking };

import FalconApi from '@crowdstrike/foundry-js';
import { createContext, useEffect, useMemo, useState } from 'react';

const FalconApiContext = createContext(null);

function useFalconApiContext() {
  const [isInitialized, setIsInitialized] = useState(false);
  const falcon = useMemo(() => new FalconApi(), []);
  const navigation = useMemo(() => falcon.isConnected ? falcon.navigation : undefined, [falcon.isConnected]);

  useEffect(() => {
    (async () => {
      await falcon.connect();
      setIsInitialized(true);
    })();
  }, []);

  return { falcon, navigation, isInitialized };
}

export { useFalconApiContext, FalconApiContext };


