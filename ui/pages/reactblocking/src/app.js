import React from "react";
import { HashRouter, Routes, Route, Outlet } from "react-router-dom";
import {
  useFalconApiContext,
  FalconApiContext,
} from "./contexts/falcon-api-context.js";
import { Home } from "./routes/home.js";
import { About } from "./routes/about.js";
import { DomainAnalytics } from "./routes/domain-analytics.js";
import { FirewallRules } from './routes/FirewallRules.js';
import { Relationship } from "./routes/relationship.js";
import ReactDOM from "react-dom/client";
import { TabNavigation } from "./components/navigation.js";
import { SlSpinner } from "@shoelace-style/shoelace/dist/react";
import '@shoelace-style/shoelace/dist/themes/light.css';


function Root() {
  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <div className="max-w-screen-2xl mx-auto px-4">
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
