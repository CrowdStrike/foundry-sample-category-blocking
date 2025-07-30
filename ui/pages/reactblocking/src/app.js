// import React from "react";
// import { HashRouter, Routes, Route, Outlet } from "react-router-dom";
// import {
//   useFalconApiContext,
//   FalconApiContext,
// } from "./contexts/falcon-api-context.js";
// import { Home } from "./routes/home.js";
// import { About } from "./routes/about.js";
// import ReactDOM from "react-dom/client";
// import { TabNavigation } from "./components/navigation.js";

// function Root() {
//   return (
//     <div className="container mx-auto p-4">
//       <div className="bg-white rounded-xl shadow-lg p-6">
//         <h1 className="text-2xl font-bold text-indigo-800 mb-6 text-center">
//           URL Category Blocking
//         </h1>
//         <Routes>
//           <Route
//             element={
//               <TabNavigation>
//                 <Outlet />
//               </TabNavigation>
//             }
//           >
//             <Route index path="/" element={<Home />} />
//             <Route path="/about" element={<About />} />
//           </Route>
//         </Routes>
//       </div>
//     </div>
//   );
// }

// function LoadingScreen() {
//   return (
//     <div className="flex items-center justify-center min-h-screen bg-gray-50">
//       <div className="text-center p-6 bg-white rounded-lg shadow-lg">
//         <h1 className="text-xl font-bold text-indigo-600 mb-2">
//           Initializing Application...
//         </h1>
//         <p className="text-gray-600">
//           Please wait while we set up your environment
//         </p>
//       </div>
//     </div>
//   );
// }

// function ErrorScreen({ message }) {
//   return (
//     <div className="flex items-center justify-center min-h-screen bg-gray-50">
//       <div className="text-center p-6 bg-white rounded-lg shadow-lg">
//         <h1 className="text-xl font-bold text-red-600 mb-2">
//           Application Error
//         </h1>
//         <p className="text-gray-600">{message}</p>
//       </div>
//     </div>
//   );
// }

// function App() {
//   const { falcon, navigation, isInitialized } = useFalconApiContext();

//   // Show loading screen while initializing
//   if (!isInitialized) {
//     return <LoadingScreen />;
//   }

//   // Check if we have the required data
//   if (!falcon || !falcon.data) {
//     return <ErrorScreen message="Failed to initialize Falcon API" />;
//   }

//   return (
//     <React.StrictMode>
//       <FalconApiContext.Provider 
//         value={{ 
//           falcon, 
//           navigation, 
//           isInitialized,
//           user: falcon.data.user 
//         }}
//       >
//         <HashRouter>
//           <Root />
//         </HashRouter>
//       </FalconApiContext.Provider>
//     </React.StrictMode>
//   );
// }

// // Initialize the application with error handling
// function initializeApp() {
//   try {
//     const domContainer = document.querySelector("#app");
//     if (!domContainer) {
//       throw new Error("Could not find #app element");
//     }

//     // Clear any existing content
//     domContainer.innerHTML = '';

//     // Create and render the root
//     const root = ReactDOM.createRoot(domContainer);
//     root.render(<App />);

//     // Log successful initialization
//     console.log('Application initialized successfully');
//   } catch (error) {
//     // Log the error
//     console.error('Failed to initialize application:', error);

//     // Show error UI
//     document.body.innerHTML = `
//       <div class="flex items-center justify-center min-h-screen bg-gray-50">
//         <div class="text-center p-6 bg-white rounded-lg shadow-lg max-w-md">
//           <h1 class="text-xl font-bold text-red-600 mb-2">
//             Application Error
//           </h1>
//           <p class="text-gray-600">
//             ${error.message || 'An unexpected error occurred'}
//           </p>
//           ${error.stack ? `
//             <pre class="mt-4 p-4 bg-gray-100 rounded text-left text-sm overflow-auto">
//               ${error.stack}
//             </pre>
//           ` : ''}
//         </div>
//       </div>
//     `;
//   }
// }

// // Start the application
// console.log('Starting application initialization...');
// initializeApp();

// // Add error boundary for uncaught errors
// window.addEventListener('error', (event) => {
//   console.error('Uncaught error:', event.error);
//   // Optionally show error UI for uncaught errors
// });

// // Add unhandled promise rejection handler
// window.addEventListener('unhandledrejection', (event) => {
//   console.error('Unhandled promise rejection:', event.reason);
//   // Optionally show error UI for unhandled promises
// });

// 2

// import React from "react";
// import { HashRouter, Routes, Route, Outlet } from "react-router-dom";
// import {
//   useFalconApiContext,
//   FalconApiContext,
// } from "./contexts/falcon-api-context.js";
// import { Home } from "./routes/home.js";
// import { About } from "./routes/about.js";
// import ReactDOM from "react-dom/client";
// import { TabNavigation } from "./components/navigation.js";

// function Root() {
//   return (
//     <Routes>
//       <Route
//         element={
//           <TabNavigation>
//             <Outlet />
//           </TabNavigation>
//         }
//       >
//         <Route index path="/" element={<Home />} />
//         <Route path="/about" element={<About />} />
//       </Route>
//     </Routes>
//   );
// }

// function App() {
//   const { falcon, navigation, isInitialized } = useFalconApiContext();

//   if (!isInitialized) {
//     return null;
//   }

//   return (
//     <React.StrictMode>
//       <FalconApiContext.Provider value={{ falcon, navigation, isInitialized }}>
//         <HashRouter>
//           <Root />
//         </HashRouter>
//       </FalconApiContext.Provider>
//     </React.StrictMode>
//   );
// }

// const domContainer = document.querySelector("#app");
// const root = ReactDOM.createRoot(domContainer);

// root.render(<App />);

import React from "react";
import { HashRouter, Routes, Route, Outlet } from "react-router-dom";
import {
  useFalconApiContext,
  FalconApiContext,
} from "./contexts/falcon-api-context.js";
import { Home } from "./routes/home.js";
import { About } from "./routes/about.js";
import { DomainAnalytics } from "./routes/domain-analytics";
import { FirewallRules } from './routes/FirewallRules';
import { Relationship } from "./routes/relationship.js";
import ReactDOM from "react-dom/client";
import { TabNavigation } from "./components/navigation.js";
import { SlSpinner } from "@shoelace-style/shoelace/dist/react";

function Root() {
  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-7xl mx-auto">
        <Routes>
          <Route
            element={
              <TabNavigation>
                <Outlet />
              </TabNavigation>
            }
          >
            <Route index path="/" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/domain-analytics" element={<DomainAnalytics />} />
            <Route path="/firewall-rules" element={<FirewallRules />} />
            <Route path="/relationship" element={<Relationship />} />
          </Route>
        </Routes>
      </div>
    </div>
  );
}

function App() {
  const { falcon, navigation, isInitialized } = useFalconApiContext();

  if (!isInitialized) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <SlSpinner style={{ fontSize: '2rem' }} />
          <p className="mt-4 text-gray-600">Initializing application...</p>
        </div>
      </div>
    );
  }

  return (
    <React.StrictMode>
      <FalconApiContext.Provider value={{ falcon, navigation, isInitialized }}>
        <HashRouter>
          <Root />
        </HashRouter>
      </FalconApiContext.Provider>
    </React.StrictMode>
  );
}

const domContainer = document.querySelector("#app");
if (!domContainer) {
  console.error("Could not find #app element");
} else {
  const root = ReactDOM.createRoot(domContainer);
  root.render(<App />);
}
