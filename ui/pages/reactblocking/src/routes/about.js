// import React, { useState, useContext, useEffect } from "react";
// import { SlDetails, SlAlert } from "@shoelace-style/shoelace/dist/react";
// import { FalconApiContext } from "../contexts/falcon-api-context";

// function About() {
//   const { falcon } = useContext(FalconApiContext);
//   const [categoryName, setCategoryName] = useState('');
//   const [urls, setUrls] = useState('');
//   const [status, setStatus] = useState(null);
//   const [existingCategories, setExistingCategories] = useState([]);
//   const [showSuggestions, setShowSuggestions] = useState(false);
//   const [filteredCategories, setFilteredCategories] = useState([]);
//   const [isLoading, setIsLoading] = useState(false);

//   // Fetch existing categories on component mount
//   useEffect(() => {
//     fetchExistingCategories();
//   }, []);

//   const fetchExistingCategories = async () => {
//     try {
//       console.log('Fetching existing categories');
//       const config = {
//         name: 'reactblock',
//         version: 1
//       };
      
//       const cloudFunction = falcon.cloudFunction(config);
//       const response = await cloudFunction.path('/categories').get();
//       console.log('Categories response:', response);

//       if (response?.body?.categories) {
//         setExistingCategories(Object.keys(response.body.categories));
//       }
//     } catch (error) {
//       console.error('Failed to fetch categories:', error);
//       setStatus({
//         type: 'error',
//         message: `Failed to fetch categories: ${error.message}`
//       });
//     }
//   };

//   // Filter categories based on input
//   useEffect(() => {
//     if (categoryName) {
//       const filtered = existingCategories.filter(cat => 
//         cat.toLowerCase().includes(categoryName.toLowerCase())
//       );
//       setFilteredCategories(filtered);
//       setShowSuggestions(filtered.length > 0);
//     } else {
//       setShowSuggestions(false);
//     }
//   }, [categoryName, existingCategories]);

//   const handleCreateCategory = async () => {
//     try {
//       setIsLoading(true);
//       console.log('Starting category creation/update');

//       if (!categoryName.trim()) {
//         throw new Error('Please enter a category name');
//       }
//       if (!urls.trim()) {
//         throw new Error('Please enter at least one URL');
//       }

//       setStatus({
//         type: 'info',
//         message: 'Processing category...'
//       });

//       const config = {
//         name: 'reactblock',
//         version: 1
//       };
      
//       const cloudFunction = falcon.cloudFunction(config);

//       console.log('Sending request with:', {
//         categoryName: categoryName.trim(),
//         urls: urls
//       });

//       const response = await cloudFunction.path('/manage-category').post({
//         categoryName: categoryName.trim(),
//         urls: urls
//       });

//       console.log('Response:', response);

//       if (response.code === 200) {
//         setStatus({
//           type: 'success',
//           message: `Category ${response.body.operation === 'create' ? 'created' : 'updated'} successfully!`
//         });
//         setCategoryName('');
//         setUrls('');
//         await fetchExistingCategories();
//       } else {
//         throw new Error(response.body.error || 'Failed to process category');
//       }
//     } catch (error) {
//       console.error('Error in handleCreateCategory:', error);
//       setStatus({
//         type: 'error',
//         message: `Error: ${error.message}`
//       });
//     } finally {
//       setIsLoading(false);
//     }
//   };

//   const handleUpdateGames = async () => {
//     try {
//         setIsLoading(true);
//         setStatus({
//             type: 'info',
//             message: 'Updating Games category...'
//         });

//         const config = {
//             name: 'reactblock',
//             version: 1
//         };
        
//         const cloudFunction = falcon.cloudFunction(config);
//         const response = await cloudFunction.path('/update-games').post();

//         if (response.code === 200) {
//             setStatus({
//                 type: 'success',
//                 message: 'Successfully updated Games category with newtest.com'
//             });
//             await fetchExistingCategories();
//         } else {
//             throw new Error(response.body.error || 'Failed to update Games category');
//         }
//     } catch (error) {
//         console.error('Error updating Games category:', error);
//         setStatus({
//             type: 'error',
//             message: `Error updating Games category: ${error.message}`
//         });
//     } finally {
//         setIsLoading(false);
//     }
//   };

//   // Click outside handler for suggestions
//   useEffect(() => {
//     const handleClickOutside = (event) => {
//       if (!event.target.closest('.category-input-container')) {
//         setShowSuggestions(false);
//       }
//     };

//     document.addEventListener('mousedown', handleClickOutside);
//     return () => {
//       document.removeEventListener('mousedown', handleClickOutside);
//     };
//   }, []);

//   return (
//     <div className="mt-4 space-y-8" style={{ maxWidth: "800px" }}>
//       <SlDetails summary="Create or Update Category" open>
//         <div className="space-y-4 p-4">
//           {/* Category Name Input with Autocomplete */}
//           <div className="form-group relative category-input-container">
//             <label className="block text-indigo-700 text-sm font-bold mb-2">
//               Category Name {existingCategories.includes(categoryName) && 
//                 <span className="text-purple-600 ml-2">(Existing Category)</span>
//               }
//             </label>
//             <input
//               type="text"
//               value={categoryName}
//               onChange={(e) => setCategoryName(e.target.value)}
//               onFocus={() => setShowSuggestions(true)}
//               placeholder="Enter or select category name"
//               className="w-full p-3 border border-purple-200 rounded-lg shadow-sm 
//                        focus:ring-2 focus:ring-purple-500 focus:border-purple-500
//                        bg-white hover:bg-purple-50 transition-colors"
//             />
//             {/* Category Suggestions */}
//             {showSuggestions && filteredCategories.length > 0 && (
//               <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg">
//                 <ul className="py-1 max-h-60 overflow-auto">
//                   {filteredCategories.map((cat, index) => (
//                     <li
//                       key={index}
//                       className="px-4 py-2 hover:bg-purple-50 cursor-pointer text-sm"
//                       onClick={() => {
//                         setCategoryName(cat);
//                         setShowSuggestions(false);
//                       }}
//                     >
//                       {cat}
//                     </li>
//                   ))}
//                 </ul>
//               </div>
//             )}
//           </div>

//           {/* URLs Input */}
//           <div className="form-group">
//             <label className="block text-indigo-700 text-sm font-bold mb-2">
//               URLs (one per line)
//             </label>
//             <textarea
//               value={urls}
//               onChange={(e) => setUrls(e.target.value)}
//               placeholder="Enter URLs (one per line)"
//               rows="10"
//               className="w-full p-3 border border-purple-200 rounded-lg shadow-sm 
//                        focus:ring-2 focus:ring-purple-500 focus:border-purple-500
//                        bg-white hover:bg-purple-50 transition-colors"
//             />
//           </div>

//           {/* Create/Update Button */}
//           <button
//             onClick={handleCreateCategory}
//             disabled={isLoading}
//             className={`w-full p-3 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg
//                      transition-all duration-200 focus:outline-none focus:ring-2 
//                      focus:ring-purple-500 focus:ring-offset-2 shadow-lg
//                      ${isLoading 
//                        ? 'opacity-50 cursor-not-allowed' 
//                        : 'hover:from-indigo-600 hover:to-purple-600 hover:shadow-xl'}`}
//           >
//             {isLoading ? 'Processing...' : (existingCategories.includes(categoryName) ? 'Update Category' : 'Create Category')}
//           </button>

//           {/* Status Message */}
//           {status && (
//             <SlAlert 
//               variant={
//                 status.type === 'error' ? 'danger' :
//                 status.type === 'success' ? 'success' :
//                 'primary'
//               }
//               closable
//               className="mt-4"
//             >
//               {status.message}
//             </SlAlert>
//           )}
//         </div>
//       </SlDetails>

//       <SlDetails summary="Quick Actions" open>
//         <div className="space-y-4 p-4">
//             <h3 className="font-bold text-lg text-indigo-800">Quick Category Updates</h3>
//             <div className="space-y-4">
//                 <button
//                     onClick={handleUpdateGames}
//                     disabled={isLoading}
//                     className={`w-full p-3 bg-gradient-to-r from-green-500 to-blue-500 text-white rounded-lg
//                                 transition-all duration-200 focus:outline-none focus:ring-2 
//                                 focus:ring-green-500 focus:ring-offset-2 shadow-lg
//                                 ${isLoading 
//                                     ? 'opacity-50 cursor-not-allowed' 
//                                     : 'hover:from-green-600 hover:to-blue-600 hover:shadow-xl'}`}
//                 >
//                     <div className="flex items-center justify-center space-x-2">
//                         <span>{isLoading ? 'Processing...' : 'Update Games Category'}</span>
//                         {!isLoading && <span className="text-xs bg-white bg-opacity-20 px-2 py-1 rounded">Adds newtest.com</span>}
//                     </div>
//                 </button>
//                 <p className="text-sm text-gray-600 mt-2">
//                     Click to automatically append newtest.com to the Games category
//                 </p>
//             </div>
//         </div>
//       </SlDetails>

//       <SlDetails summary="Instructions">
//         <div className="space-y-4 p-4">
//           <h3 className="font-bold text-lg text-indigo-800">How to Create or Update a Category</h3>
//           <ol className="list-decimal pl-5 space-y-2">
//             <li>Enter a category name (or select an existing one to update)</li>
//             <li>Add your URLs (one per line)</li>
//             <li>Click "Create Category" or "Update Category" to save</li>
//           </ol>
//           <p className="text-sm text-gray-600 mt-4">
//             Note: When updating an existing category, new URLs will be added to the existing ones.
//           </p>
//         </div>
//       </SlDetails>

//       <SlDetails summary="Format Guidelines">
//         <div className="space-y-4 p-4">
//           <h3 className="font-bold text-lg text-indigo-800">URL Format Guidelines</h3>
//           <ul className="list-disc pl-5 space-y-2">
//             <li>Enter each URL on a new line</li>
//             <li>URLs can be with or without 'http://' or 'https://'</li>
//             <li>Wildcards (*.example.com) are supported</li>
//             <li>No spaces or special characters in URLs</li>
//           </ul>
//           <div className="bg-gray-50 p-4 rounded-lg mt-4">
//             <h4 className="font-bold mb-2">Example:</h4>
//             <pre className="text-sm text-gray-600">
//               example.com{'\n'}
//               *.example.com{'\n'}
//               subdomain.example.com
//             </pre>
//           </div>
//         </div>
//       </SlDetails>
//     </div>
//   );
// }

// export { About };

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
        name: 'reactblock',
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
    <div className="mt-4 max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-sm">
      <h2 className="text-2xl font-bold text-indigo-800 mb-6">Create Custom Category</h2>
      
      <div className="space-y-6">
        {/* Category Name Input */}
        <div className="form-group">
          <label className="block text-indigo-700 text-sm font-bold mb-2">
            Category Name
          </label>
          <input
            type="text"
            value={categoryName}
            onChange={(e) => setCategoryName(e.target.value)}
            placeholder="Enter category name"
            className="w-full p-3 border border-purple-200 rounded-lg shadow-sm 
                     focus:ring-2 focus:ring-purple-500 focus:border-purple-500
                     bg-white hover:bg-purple-50 transition-colors"
          />
        </div>

        {/* URLs Input */}
        <div className="form-group">
          <label className="block text-indigo-700 text-sm font-bold mb-2">
            URLs (comma-separated)
          </label>
          <textarea
            value={urls}
            onChange={(e) => setUrls(e.target.value)}
            placeholder="Enter URLs separated by commas (e.g., example.com, test.com, domain.com)"
            rows="6"
            className="w-full p-3 border border-purple-200 rounded-lg shadow-sm 
                     focus:ring-2 focus:ring-purple-500 focus:border-purple-500
                     bg-white hover:bg-purple-50 transition-colors
                     font-mono text-sm"
          />
          <p className="mt-2 text-sm text-gray-600">
            Example: example.com, test.com, domain.com
          </p>
        </div>

        {/* Create Button */}
        <button
          onClick={handleCreateCategory}
          disabled={isLoading}
          className={`w-full p-3 bg-gradient-to-r from-indigo-500 to-purple-500 
                     text-white rounded-lg transition-all duration-200 
                     focus:outline-none focus:ring-2 focus:ring-purple-500 
                     focus:ring-offset-2 shadow-lg
                     ${isLoading 
                       ? 'opacity-50 cursor-not-allowed' 
                       : 'hover:from-indigo-600 hover:to-purple-600 hover:shadow-xl'}`}
        >
          {isLoading ? 'Creating Category...' : 'Create Category'}
        </button>

        {/* Status Message */}
        {status && (
          <SlAlert 
            variant={status.type === 'error' ? 'danger' : 'success'}
            closable
            className="mt-4"
          >
            {status.message}
          </SlAlert>
        )}
      </div>
    </div>
  );
}

export { About };
