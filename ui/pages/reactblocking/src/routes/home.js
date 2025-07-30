// import React, { useContext, useState, useEffect } from "react";
// import { FalconApiContext } from "../contexts/falcon-api-context";
// import { Link } from '../components/link';

// function Home() {
//   const { falcon } = useContext(FalconApiContext);
//   const [hostGroups, setHostGroups] = useState([]);
//   const [categories, setCategories] = useState({});
//   const [selectedHostGroup, setSelectedHostGroup] = useState('');
//   const [policyName, setPolicyName] = useState('');
//   const [selectedCategories, setSelectedCategories] = useState([]);
//   const [selectedUrls, setSelectedUrls] = useState('');
//   const [status, setStatus] = useState(null);

//   useEffect(() => {
//     const loadData = async () => {
//       try {
//         const config = {
//           name: 'reactblock',
//           version: 1
//         };
        
//         const cloudFunction = falcon.cloudFunction(config);

//         const [hostGroupsResponse, categoriesResponse] = await Promise.all([
//           cloudFunction.path('/reactblock').get(),
//           cloudFunction.path('/categories').get()
//         ]);

//         if (hostGroupsResponse?.body?.host_groups) {
//           setHostGroups(hostGroupsResponse.body.host_groups);
//         }
//         if (categoriesResponse?.body?.categories) {
//           setCategories(categoriesResponse.body.categories);
//         }
//       } catch (error) {
//         setStatus({
//           type: 'error',
//           message: `Failed to load data: ${error.message}`
//         });
//       }
//     };

//     if (falcon) {
//       loadData();
//     }
//   }, [falcon]);

//   const handlePreview = () => {
//     try {
//       if (selectedCategories.length === 0) {
//         throw new Error('Please select at least one category');
//       }

//       const urls = selectedCategories
//         .map(category => categories[category])
//         .filter(Boolean)
//         .join(';');

//       setSelectedUrls(urls);
//       setStatus({
//         type: 'success',
//         message: `Preview generated successfully`
//       });
//     } catch (error) {
//       setStatus({
//         type: 'error',
//         message: error.message
//       });
//     }
//   };

//   const handleCreateRule = async () => {
//     try {
//       if (!selectedHostGroup) throw new Error('Please select a host group');
//       if (!policyName) throw new Error('Please enter a policy name');
//       if (!selectedUrls) throw new Error('Please preview URLs first');

//       setStatus({
//         type: 'info',
//         message: 'Creating blocking rule...'
//       });

//       const config = {
//         name: 'reactblock',
//         version: 1
//       };
      
//       const cloudFunction = falcon.cloudFunction(config);

//       const response = await cloudFunction.path('/create-rule').post({
//         hostGroupId: selectedHostGroup,
//         urls: selectedUrls,
//         policyName: policyName
//       });

//       if (response.code === 201) {
//         setStatus({
//           type: 'success',
//           message: 'Successfully created blocking rule!'
//         });
//         // Reset form
//         setSelectedHostGroup('');
//         setPolicyName('');
//         setSelectedCategories([]);
//         setSelectedUrls('');
//       } else {
//         throw new Error(response.body.error || 'Failed to create rule');
//       }
//     } catch (error) {
//       setStatus({
//         type: 'error',
//         message: error.message
//       });
//     }
//   };

//   return (
//     <div className="mt-4 space-y-8">
//       <p className="text-neutral">👋 Hi {falcon.data.user.username}</p>
      
//       <div className="grid grid-cols-12 gap-6">
//         {/* Left Column - Configuration */}
//         <div className="col-span-12 lg:col-span-4">
//           <div className="space-y-4">
//             {/* Policy Name Input */}
//             <div className="form-group">
//               <label className="block text-indigo-700 text-sm font-bold mb-2">
//                 Policy Name
//               </label>
//               <input
//                 type="text"
//                 value={policyName}
//                 onChange={(e) => setPolicyName(e.target.value)}
//                 placeholder="Enter a unique policy name"
//                 className="w-full p-3 border border-purple-200 rounded-lg shadow-sm"
//               />
//             </div>

//             {/* Host Group Select */}
//             <div className="form-group">
//               <label className="block text-indigo-700 text-sm font-bold mb-2">
//                 Host Group
//               </label>
//               <select
//                 value={selectedHostGroup}
//                 onChange={(e) => setSelectedHostGroup(e.target.value)}
//                 className="w-full p-3 border border-purple-200 rounded-lg shadow-sm"
//               >
//                 <option value="">Select a host group...</option>
//                 {hostGroups.map((group) => (
//                   <option key={group.id} value={group.id}>
//                     {group.name}
//                   </option>
//                 ))}
//               </select>
//             </div>

//             {/* Action Buttons */}
//             <div className="space-y-2">
//               <button
//                 onClick={handlePreview}
//                 className="w-full p-3 bg-gradient-to-r from-pink-500 to-purple-500 text-white rounded-lg"
//               >
//                 Preview URLs
//               </button>
//               <button
//                 onClick={handleCreateRule}
//                 className="w-full p-3 bg-gradient-to-r from-indigo-500 to-blue-500 text-white rounded-lg"
//               >
//                 Create Blocking Rule
//               </button>
//             </div>

//             {/* Status Messages */}
//             {status && (
//               <div className={`p-3 rounded-lg ${
//                 status.type === 'error' ? 'bg-red-50 text-red-600' :
//                 status.type === 'success' ? 'bg-green-50 text-green-600' :
//                 'bg-blue-50 text-blue-600'
//               }`}>
//                 {status.message}
//               </div>
//             )}
//           </div>
//         </div>

//         {/* Middle Column - Categories */}
//         <div className="col-span-12 lg:col-span-4">
//           <label className="block text-indigo-700 text-sm font-bold mb-2">
//             Categories to Block
//           </label>
//           <div className="space-y-2 max-h-[500px] overflow-y-auto p-4 bg-purple-50 rounded-lg">
//             {Object.keys(categories).map((category) => (
//               <div key={category} className="flex items-center space-x-2 p-2 bg-white rounded-lg">
//                 <input
//                   type="checkbox"
//                   id={`category-${category}`}
//                   checked={selectedCategories.includes(category)}
//                   onChange={(e) => {
//                     if (e.target.checked) {
//                       setSelectedCategories([...selectedCategories, category]);
//                     } else {
//                       setSelectedCategories(selectedCategories.filter(c => c !== category));
//                     }
//                   }}
//                   className="form-checkbox h-4 w-4 text-purple-600"
//                 />
//                 <label htmlFor={`category-${category}`} className="text-sm text-gray-700">
//                   {category}
//                 </label>
//               </div>
//             ))}
//           </div>
//         </div>

//         {/* Right Column - URL Preview */}
//         <div className="col-span-12 lg:col-span-4">
//           <label className="block text-indigo-700 text-sm font-bold mb-2">
//             Selected URLs
//           </label>
//           <textarea
//             value={selectedUrls}
//             readOnly
//             className="w-full h-[500px] p-3 border border-purple-200 rounded-lg shadow-sm bg-gray-50"
//             placeholder="URLs will appear here after preview..."
//           />
//         </div>
//       </div>

//       <div className="mt-4">
//         <Link useFalconNavigation={true} to="/crowdscore">Go to Crowdscore</Link>
//       </div>
//     </div>
//   );
// }

// export { Home };

// import React, { useContext, useState, useEffect } from "react";
// import { FalconApiContext } from "../contexts/falcon-api-context";
// import { Link } from '../components/link';
// import { SlSpinner } from "@shoelace-style/shoelace/dist/react";

// function Home() {
//   const { falcon } = useContext(FalconApiContext);
//   const [hostGroups, setHostGroups] = useState([]);
//   const [categories, setCategories] = useState({});
//   const [selectedHostGroup, setSelectedHostGroup] = useState('');
//   const [policyName, setPolicyName] = useState('');
//   const [selectedCategories, setSelectedCategories] = useState([]);
//   const [selectedUrls, setSelectedUrls] = useState('');
//   const [status, setStatus] = useState(null);
//   const [isLoading, setIsLoading] = useState(true);
//   const [loadingCategories, setLoadingCategories] = useState(true);

//   useEffect(() => {
//     const loadData = async () => {
//       try {
//         setIsLoading(true);
//         setLoadingCategories(true);
//         console.log("Starting to load data");

//         // Load host groups
//         const config = {
//           name: 'reactblock',
//           version: 1
//         };
        
//         const cloudFunction = falcon.cloudFunction(config);
//         const hostGroupsResponse = await cloudFunction.path('/reactblock').get();

//         if (hostGroupsResponse?.body?.host_groups) {
//           console.log("Host groups loaded:", hostGroupsResponse.body.host_groups);
//           setHostGroups(hostGroupsResponse.body.host_groups);
//         }

//         // Load categories directly from collection
//         const collection = falcon.collection({
//           collection: 'domain'
//         });

//         console.log("Fetching categories from collection");
//         const response = await collection.list({
//           limit: 100
//         });

//         console.log("Collection response:", response);

//         if (response && response.resources && Array.isArray(response.resources)) {
//           // Create categories object with empty domains initially
//           const categoriesObj = {};
//           response.resources.forEach(category => {
//             if (typeof category === 'string') {
//               categoriesObj[category] = ''; // Initialize with empty string, we'll fetch domains later
//             }
//           });

//           // Now fetch details for each category
//           for (const category of Object.keys(categoriesObj)) {
//             try {
//               const categoryDetails = await collection.get({
//                 id: category.toLowerCase().replace(/\s+/g, '_')
//               });
              
//               if (categoryDetails && categoryDetails.data && categoryDetails.data.domain) {
//                 categoriesObj[category] = categoryDetails.data.domain;
//               }
//             } catch (error) {
//               console.warn(`Failed to fetch details for category ${category}:`, error);
//             }
//           }

//           console.log("Processed categories:", categoriesObj);
//           setCategories(categoriesObj);
//         }

//       } catch (error) {
//         console.error('Error loading data:', error);
//         setStatus({
//           type: 'error',
//           message: `Failed to load data: ${error.message}`
//         });
//       } finally {
//         setIsLoading(false);
//         setLoadingCategories(false);
//       }
//     };

//     if (falcon) {
//       loadData();
//     }
//   }, [falcon]);

//   const handlePreview = () => {
//     try {
//       if (selectedCategories.length === 0) {
//         throw new Error('Please select at least one category');
//       }

//       const urls = selectedCategories
//         .map(category => categories[category])
//         .filter(Boolean)
//         .join(';');

//       setSelectedUrls(urls);
//       setStatus({
//         type: 'success',
//         message: `Preview generated successfully`
//       });
//     } catch (error) {
//       setStatus({
//         type: 'error',
//         message: error.message
//       });
//     }
//   };

//   const handleCreateRule = async () => {
//     try {
//       if (!selectedHostGroup) throw new Error('Please select a host group');
//       if (!policyName) throw new Error('Please enter a policy name');
//       if (!selectedUrls) throw new Error('Please preview URLs first');

//       setStatus({
//         type: 'info',
//         message: 'Creating blocking rule...'
//       });

//       const config = {
//         name: 'reactblock',
//         version: 1
//       };
      
//       const cloudFunction = falcon.cloudFunction(config);

//       const response = await cloudFunction.path('/create-rule').post({
//         hostGroupId: selectedHostGroup,
//         urls: selectedUrls,
//         policyName: policyName
//       });

//       if (response.code === 201 || response.code === 200) {
//         setStatus({
//           type: 'success',
//           message: 'Successfully created blocking rule!'
//         });
//         // Reset form
//         setSelectedHostGroup('');
//         setPolicyName('');
//         setSelectedCategories([]);
//         setSelectedUrls('');
//       } else {
//         throw new Error(response.body.error || 'Failed to create rule');
//       }
//     } catch (error) {
//       setStatus({
//         type: 'error',
//         message: error.message
//       });
//     }
//   };

//   if (isLoading) {
//     return (
//       <div className="flex items-center justify-center min-h-[400px]">
//         <div className="text-center">
//           <SlSpinner style={{ fontSize: '2rem' }} />
//           <p className="mt-4 text-gray-600">Loading data...</p>
//         </div>
//       </div>
//     );
//   }

//   return (
//     <div className="mt-4 space-y-8">
//       <p className="text-neutral">👋 Hi {falcon.data.user.username}</p>
      
//       <div className="grid grid-cols-12 gap-6">
//         {/* Left Column - Configuration */}
//         <div className="col-span-12 lg:col-span-4">
//           <div className="space-y-4">
//             {/* Policy Name Input */}
//             <div className="form-group">
//               <label className="block text-indigo-700 text-sm font-bold mb-2">
//                 Policy Name
//               </label>
//               <input
//                 type="text"
//                 value={policyName}
//                 onChange={(e) => setPolicyName(e.target.value)}
//                 placeholder="Enter a unique policy name"
//                 className="w-full p-3 border border-purple-200 rounded-lg shadow-sm focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition"
//               />
//             </div>

//             {/* Host Group Select */}
//             <div className="form-group">
//               <label className="block text-indigo-700 text-sm font-bold mb-2">
//                 Host Group
//               </label>
//               <select
//                 value={selectedHostGroup}
//                 onChange={(e) => setSelectedHostGroup(e.target.value)}
//                 className="w-full p-3 border border-purple-200 rounded-lg shadow-sm focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition"
//               >
//                 <option value="">Select a host group...</option>
//                 {hostGroups.map((group) => (
//                   <option key={group.id} value={group.id}>
//                     {group.name}
//                   </option>
//                 ))}
//               </select>
//             </div>

//             {/* Action Buttons */}
//             <div className="space-y-2">
//               <button
//                 onClick={handlePreview}
//                 className="w-full p-3 bg-gradient-to-r from-pink-500 to-purple-500 text-white rounded-lg hover:from-pink-600 hover:to-purple-600 transition transform hover:scale-[1.02]"
//               >
//                 Preview URLs
//               </button>
//               <button
//                 onClick={handleCreateRule}
//                 className="w-full p-3 bg-gradient-to-r from-indigo-500 to-blue-500 text-white rounded-lg hover:from-indigo-600 hover:to-blue-600 transition transform hover:scale-[1.02]"
//               >
//                 Create Blocking Rule
//               </button>
//             </div>

//             {/* Status Messages */}
//             {status && (
//               <div className={`p-4 rounded-lg transition-all duration-300 ${
//                 status.type === 'error' ? 'bg-red-50 text-red-600 border border-red-200' :
//                 status.type === 'success' ? 'bg-green-50 text-green-600 border border-green-200' :
//                 'bg-blue-50 text-blue-600 border border-blue-200'
//               }`}>
//                 {status.message}
//               </div>
//             )}
//           </div>
//         </div>

//         {/* Middle Column - Categories */}
//         <div className="col-span-12 lg:col-span-4">
//           <label className="block text-indigo-700 text-sm font-bold mb-2">
//             Categories to Block
//           </label>
//           <div className="space-y-2 max-h-[500px] overflow-y-auto p-4 bg-purple-50 rounded-lg">
//             {loadingCategories ? (
//               <div className="flex items-center justify-center py-4">
//                 <SlSpinner style={{ fontSize: '1.5rem' }} />
//                 <span className="ml-2 text-gray-600">Loading categories...</span>
//               </div>
//             ) : Object.keys(categories).length > 0 ? (
//               Object.keys(categories).sort().map((category) => (
//                 <div key={category} className="flex items-center space-x-2 p-2 bg-white rounded-lg hover:bg-purple-50 transition-colors">
//                   <input
//                     type="checkbox"
//                     id={`category-${category}`}
//                     checked={selectedCategories.includes(category)}
//                     onChange={(e) => {
//                       if (e.target.checked) {
//                         setSelectedCategories([...selectedCategories, category]);
//                       } else {
//                         setSelectedCategories(selectedCategories.filter(c => c !== category));
//                       }
//                     }}
//                     className="form-checkbox h-4 w-4 text-purple-600 rounded"
//                   />
//                   <label 
//                     htmlFor={`category-${category}`} 
//                     className="text-sm text-gray-700 hover:text-purple-700 cursor-pointer"
//                   >
//                     {category}
//                   </label>
//                 </div>
//               ))
//             ) : (
//               <div className="text-center py-4 text-gray-500">
//                 No categories available
//               </div>
//             )}
//           </div>
//           {Object.keys(categories).length > 0 && (
//             <p className="mt-2 text-sm text-gray-600">
//               {Object.keys(categories).length} categories available
//             </p>
//           )}
//         </div>

//         {/* Right Column - URL Preview */}
//         <div className="col-span-12 lg:col-span-4">
//           <label className="block text-indigo-700 text-sm font-bold mb-2">
//             Selected URLs
//           </label>
//           <textarea
//             value={selectedUrls}
//             readOnly
//             className="w-full h-[500px] p-3 border border-purple-200 rounded-lg shadow-sm bg-gray-50 font-mono text-sm"
//             placeholder="URLs will appear here after preview..."
//           />
//         </div>
//       </div>
//     </div>
//   );
// }

// export { Home };
import React, { useContext, useState, useEffect } from "react";
import { FalconApiContext } from "../contexts/falcon-api-context";
import { Link } from '../components/link';
import { SlSpinner } from "@shoelace-style/shoelace/dist/react";

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

  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);
        setLoadingCategories(true);
        console.log("Starting to load data");

        // Load host groups
        const config = {
          name: 'reactblock',
          version: 1
        };
        
        const cloudFunction = falcon.cloudFunction(config);
        const hostGroupsResponse = await cloudFunction.path('/reactblock').get();

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
      if (selectedCategories.length === 0) {
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


  // const handleCreateRule = async () => {
  //   try {
  //     if (!selectedHostGroup) throw new Error('Please select a host group');
  //     if (!policyName) throw new Error('Please enter a policy name');
  //     if (!selectedUrls) throw new Error('Please preview URLs first');

  //     setStatus({
  //       type: 'info',
  //       message: 'Creating blocking rule...'
  //     });

  //     const config = {
  //       name: 'reactblock',
  //       version: 1
  //     };
      
  //     const cloudFunction = falcon.cloudFunction(config);

  //     const response = await cloudFunction.path('/create-rule').post({
  //       hostGroupId: selectedHostGroup,
  //       urls: selectedUrls,
  //       policyName: policyName
  //     });

  //     if (response.code === 201 || response.code === 200) {
  //       setStatus({
  //         type: 'success',
  //         message: 'Successfully created blocking rule!'
  //       });
  //       // Reset form
  //       setSelectedHostGroup('');
  //       setPolicyName('');
  //       setSelectedCategories([]);
  //       setSelectedUrls('');
  //     } else {
  //       throw new Error(response.body.error || 'Failed to create rule');
  //     }
  //   } catch (error) {
  //     setStatus({
  //       type: 'error',
  //       message: error.message
  //     });
  //   }
  // };


// const handleCreateRule = async () => {
//     try {
//       if (!selectedHostGroup) throw new Error('Please select a host group');
//       if (!policyName) throw new Error('Please enter a policy name');
//       if (!selectedUrls) throw new Error('Please preview URLs first');

//       setStatus({
//         type: 'info',
//         message: 'Creating blocking rule...'
//       });

//       const config = {
//         name: 'reactblock',
//         version: 1
//       };
      
//       const cloudFunction = falcon.cloudFunction(config);

//       // Create rule
//       console.log('[1] Creating rule with:', {
//         hostGroupId: selectedHostGroup,
//         urls: selectedUrls,
//         policyName: policyName
//       });

//       const response = await cloudFunction.path('/create-rule').post({
//         hostGroupId: selectedHostGroup,
//         urls: selectedUrls,
//         policyName: policyName
//       });

//       console.log('[2] Rule creation response:', response);

//       // Get host group name for relationship
//       const hostGroupName = hostGroups.find(g => g.id === selectedHostGroup)?.name;
//       console.log('[3] Found host group name:', hostGroupName);
      
//       // Create relationship for selected categories
//       try {
//         console.log('[4] Creating relationship for categories:', selectedCategories);
        
//         for (const category of selectedCategories) {
//           // Create relationship data matching the schema exactly
//           const relationshipData = {
//             category_name: category,
//             rule_group_id: response.body.ruleGroupId,
//             rule_group_name: `${policyName}_RuleGroup`,
//             host_group_id: selectedHostGroup,
//             host_group_name: hostGroupName,
//             policy_name: policyName,
//             created_at: new Date().toISOString(),
//             created_by: falcon.data.user.username
//           };

//           console.log(`[5] Creating relationship with data:`, relationshipData);

//           const relationshipResponse = await cloudFunction.path('/manage-relationship').post(relationshipData);
          
//           console.log(`[6] Relationship response for ${category}:`, relationshipResponse);

//           if (relationshipResponse.status_code !== 200) {
//             console.error(`Failed to create relationship for ${category}:`, relationshipResponse);
//             throw new Error(relationshipResponse.body?.error || 'Failed to create relationship');
//           }
//         }

//         console.log('[7] All relationship created successfully');

//         setStatus({
//           type: 'success',
//           message: `Successfully created blocking rule and ${selectedCategories.length} relationship!`
//         });

//         // Reset form
//         setSelectedHostGroup('');
//         setPolicyName('');
//         setSelectedCategories([]);
//         setSelectedUrls('');

//       } catch (relError) {
//         console.error('[ERROR] Relationship creation failed:', relError);
//         setStatus({
//           type: 'error',
//           message: `Rule created but failed to create relationship: ${relError.message}`
//         });
//       }
//     } catch (error) {
//       console.error('[ERROR] Operation failed:', error);
//       setStatus({
//         type: 'error',
//         message: error.message
//       });
//     }
//   };
// Add this function at the beginning of your component
const createRelationshipInCollection = async (relationshipData) => {
  try {
    // Initialize the relationship collection
    const relationshipCollection = falcon.collection({
      collection: 'relationship'
    });

    // Generate a unique key for the relationship
    const relationshipKey = `rel-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

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

// Modify your handleCreateRule function to use the new collection-based approach
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
      name: 'reactblock',
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

// Add a function to validate relationship data against schema
const validateRelationshipData = (data) => {
  const requiredFields = ['category_name', 'rule_group_id', 'host_group_id'];
  const missingFields = requiredFields.filter(field => !data[field]);
  
  if (missingFields.length > 0) {
    throw new Error(`Missing required fields: ${missingFields.join(', ')}`);
  }

  return true;
};

// Optional: Add a function to query existing relationship
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
// Helper function to generate a unique key
const generateRelationshipKey = (prefix = 'rel') => {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
};

// Helper function to format dates consistently
const formatDate = (date = new Date()) => {
  return date.toISOString();
};

// Helper function to batch update relationship
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
    <div className="mt-4 space-y-8">
      <p className="text-neutral">👋 Hi {falcon.data.user.username}</p>
      
      <div className="grid grid-cols-12 gap-6">
        {/* Left Column - Configuration */}
        <div className="col-span-12 lg:col-span-4">
          <div className="space-y-4">
            {/* Policy Name Input */}
            <div className="form-group">
              <label className="block text-indigo-700 text-sm font-bold mb-2">
                Policy Name
              </label>
              <input
                type="text"
                value={policyName}
                onChange={(e) => setPolicyName(e.target.value)}
                placeholder="Enter a unique policy name"
                className="w-full p-3 border border-purple-200 rounded-lg shadow-sm focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition"
              />
            </div>

            {/* Host Group Select */}
            <div className="form-group">
              <label className="block text-indigo-700 text-sm font-bold mb-2">
                Host Group
              </label>
              <select
                value={selectedHostGroup}
                onChange={(e) => setSelectedHostGroup(e.target.value)}
                className="w-full p-3 border border-purple-200 rounded-lg shadow-sm focus:ring-2 focus:ring-purple-300 focus:border-purple-300 transition"
              >
                <option value="">Select a host group...</option>
                {hostGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Action Buttons */}
            <div className="space-y-2">
              <button
                onClick={handlePreview}
                disabled={isPreviewLoading}
                className={`w-full p-3 bg-gradient-to-r from-pink-500 to-purple-500 text-white rounded-lg 
                          hover:from-pink-600 hover:to-purple-600 transition transform hover:scale-[1.02]
                          ${isPreviewLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {isPreviewLoading ? (
                  <div className="flex items-center justify-center">
                    <SlSpinner className="mr-2" />
                    Loading URLs...
                  </div>
                ) : (
                  'Preview URLs'
                )}
              </button>
              <button
                onClick={handleCreateRule}
                disabled={isPreviewLoading}
                className="w-full p-3 bg-gradient-to-r from-indigo-500 to-blue-500 text-white rounded-lg hover:from-indigo-600 hover:to-blue-600 transition transform hover:scale-[1.02]"
              >
                Create Blocking Rule
              </button>
            </div>

            {/* Status Messages */}
            {status && (
              <div className={`p-4 rounded-lg transition-all duration-300 ${
                status.type === 'error' ? 'bg-red-50 text-red-600 border border-red-200' :
                status.type === 'success' ? 'bg-green-50 text-green-600 border border-green-200' :
                'bg-blue-50 text-blue-600 border border-blue-200'
              }`}>
                {status.message}
              </div>
            )}
          </div>
        </div>

        {/* Middle Column - Categories */}
        <div className="col-span-12 lg:col-span-4">
          <label className="block text-indigo-700 text-sm font-bold mb-2">
            Categories to Block
          </label>
          <div className="space-y-2 max-h-[500px] overflow-y-auto p-4 bg-purple-50 rounded-lg">
            {loadingCategories ? (
              <div className="flex items-center justify-center py-4">
                <SlSpinner style={{ fontSize: '1.5rem' }} />
                <span className="ml-2 text-gray-600">Loading categories...</span>
              </div>
            ) : Object.keys(categories).length > 0 ? (
              Object.keys(categories).sort().map((category) => (
                <div key={category} className="flex items-center space-x-2 p-2 bg-white rounded-lg hover:bg-purple-50 transition-colors">
                  <input
                    type="checkbox"
                    id={`category-${category}`}
                    checked={selectedCategories.includes(category)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedCategories([...selectedCategories, category]);
                      } else {
                        setSelectedCategories(selectedCategories.filter(c => c !== category));
                      }
                    }}
                    className="form-checkbox h-4 w-4 text-purple-600 rounded"
                  />
                  <label 
                    htmlFor={`category-${category}`} 
                    className="text-sm text-gray-700 hover:text-purple-700 cursor-pointer"
                  >
                    {category}
                  </label>
                </div>
              ))
            ) : (
              <div className="text-center py-4 text-gray-500">
                No categories available
              </div>
            )}
          </div>
          {Object.keys(categories).length > 0 && (
            <p className="mt-2 text-sm text-gray-600">
              {Object.keys(categories).length} categories available
            </p>
          )}
        </div>

        {/* Right Column - URL Preview */}
        <div className="col-span-12 lg:col-span-4">
          <label className="block text-indigo-700 text-sm font-bold mb-2">
            Selected URLs
          </label>
          <div className="relative">
            <textarea
              value={selectedUrls}
              readOnly
              className={`w-full h-[500px] p-3 border border-purple-200 rounded-lg shadow-sm 
                        bg-gray-50 font-mono text-sm ${isPreviewLoading ? 'opacity-50' : ''}`}
              placeholder="URLs will appear here after preview..."
            />
            {isPreviewLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-white bg-opacity-75">
                <div className="text-center">
                  <SlSpinner style={{ fontSize: '2rem' }} />
                  <p className="mt-2 text-gray-600">Loading URLs...</p>
                </div>
              </div>
            )}
          </div>
          {selectedUrls && (
            <p className="mt-2 text-sm text-gray-600">
              {selectedUrls.split(';').length} URLs loaded
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export { Home };
