// import React from "react";
// import { useLocation } from "react-router-dom";
// import { Link } from './link';
// import {
//   SlTab,
//   SlTabGroup,
//   SlTabPanel,
// } from "@shoelace-style/shoelace/dist/react";

// function TabNavigation({ children }) {
//   const location = useLocation();
  
//   return (
//     <div className="space-y-4">
//       <div className="text-center mb-6">
//         <h1 className="text-3xl font-bold text-indigo-800 mb-2">
//           Category Blocking
//         </h1>
//         <p className="text-purple-600">Configure URL blocking rules for your host groups</p>
//       </div>

//       <SlTabGroup>
//         <SlTab 
//           active={location.pathname === "/"} 
//           slot="nav" 
//           panel="url-blocking"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/">
//             URL Blocking
//           </Link>
//         </SlTab>
//         <SlTab 
//           active={location.pathname === "/about"} 
//           slot="nav" 
//           panel="custom-categories"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/about">
//             Custom Categories
//           </Link>
//         </SlTab>

//         <SlTabPanel name="url-blocking">
//           {location.pathname === "/" && children}
//         </SlTabPanel>
//         <SlTabPanel name="custom-categories">
//           {location.pathname === "/about" && children}
//         </SlTabPanel>
//       </SlTabGroup>
//     </div>
//   );
// }

// // Optional: Add custom styles for Shoelace components
// const styles = `
//   sl-tab-group::part(tabs) {
//     border-bottom: 2px solid #e2e8f0;
//   }

//   sl-tab::part(base) {
//     padding: 0.75rem 1rem;
//     color: #4a5568;
//     font-weight: 500;
//     transition: all 0.2s;
//   }

//   sl-tab[active]::part(base) {
//     color: #6b46c1;
//     border-bottom: 2px solid #6b46c1;
//   }

//   sl-tab:not([active])::part(base):hover {
//     color: #2d3748;
//   }

//   sl-tab-panel::part(base) {
//     padding: 1.5rem 0;
//   }
// `;

// // Add styles to document
// const styleSheet = new CSSStyleSheet();
// styleSheet.replaceSync(styles);
// document.adoptedStyleSheets = [...document.adoptedStyleSheets, styleSheet];

// export { TabNavigation };

// import React from "react";
// import { useLocation } from "react-router-dom";
// import { Link } from './link';
// import {
//   SlTab,
//   SlTabGroup,
//   SlTabPanel,
// } from "@shoelace-style/shoelace/dist/react";

// function TabNavigation({ children }) {
//   const location = useLocation();
  
//   return (
//     <div className="space-y-4">
//       <div className="text-center mb-6">
//         <h1 className="text-3xl font-bold text-indigo-800 mb-2">
//           Category Blocking
//         </h1>
//         <p className="text-purple-600">Configure URL blocking rules for your host groups</p>
//       </div>

//       <SlTabGroup>
//         <SlTab 
//           active={location.pathname === "/"} 
//           slot="nav" 
//           panel="url-blocking"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/">
//             URL Blocking
//           </Link>
//         </SlTab>
//         <SlTab 
//           active={location.pathname === "/about"} 
//           slot="nav" 
//           panel="custom-categories"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/about">
//             Custom Categories
//           </Link>
//         </SlTab>
//         <SlTab 
//           active={location.pathname === "/domain-analytics"} 
//           slot="nav" 
//           panel="domain-analytics"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/domain-analytics">
//             Domain Analytics
//           </Link>
//         </SlTab>

//         <SlTabPanel name="url-blocking">
//           {location.pathname === "/" && children}
//         </SlTabPanel>
//         <SlTabPanel name="custom-categories">
//           {location.pathname === "/about" && children}
//         </SlTabPanel>
//         <SlTabPanel name="domain-analytics">
//           {location.pathname === "/domain-analytics" && children}
//         </SlTabPanel>
//       </SlTabGroup>
//     </div>
//   );
// }

// // Optional: Add custom styles for Shoelace components
// const styles = `
//   sl-tab-group::part(tabs) {
//     border-bottom: 2px solid #e2e8f0;
//   }

//   sl-tab::part(base) {
//     padding: 0.75rem 1rem;
//     color: #4a5568;
//     font-weight: 500;
//     transition: all 0.2s;
//   }

//   sl-tab[active]::part(base) {
//     color: #6b46c1;
//     border-bottom: 2px solid #6b46c1;
//   }

//   sl-tab:not([active])::part(base):hover {
//     color: #2d3748;
//   }

//   sl-tab-panel::part(base) {
//     padding: 1.5rem 0;
//   }

//   /* Added styles for analytics tab */
//   sl-tab[panel="domain-analytics"]::part(base) {
//     display: flex;
//     align-items: center;
//     gap: 0.5rem;
//   }

//   sl-tab[panel="domain-analytics"][active]::part(base) {
//     background-color: rgba(107, 70, 193, 0.05);
//   }
// `;

// // Add styles to document
// const styleSheet = new CSSStyleSheet();
// styleSheet.replaceSync(styles);
// document.adoptedStyleSheets = [...document.adoptedStyleSheets, styleSheet];

// export { TabNavigation };

// import React from "react";
// import { useLocation } from "react-router-dom";
// import { Link } from './link';
// import {
//   SlTab,
//   SlTabGroup,
//   SlTabPanel,
// } from "@shoelace-style/shoelace/dist/react";

// function TabNavigation({ children }) {
//   const location = useLocation();
  
//   return (
//     <div className="space-y-4">
//       <div className="text-center mb-6">
//         <h1 className="text-3xl font-bold text-indigo-800 mb-2">
//           Category Blocking
//         </h1>
//         <p className="text-purple-600">Configure URL blocking rules for your host groups</p>
//       </div>

//       <SlTabGroup>
//         <SlTab 
//           active={location.pathname === "/"} 
//           slot="nav" 
//           panel="url-blocking"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/">
//             URL Blocking
//           </Link>
//         </SlTab>
//         <SlTab 
//           active={location.pathname === "/about"} 
//           slot="nav" 
//           panel="custom-categories"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/about">
//             Custom Categories
//           </Link>
//         </SlTab>
//         <SlTab 
//           active={location.pathname === "/domain-analytics"} 
//           slot="nav" 
//           panel="domain-analytics"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/domain-analytics">
//             Domain Analytics
//           </Link>
//         </SlTab>
//         {/* New Firewall Rules Tab */}
//         <SlTab 
//           active={location.pathname === "/firewall-rules"} 
//           slot="nav" 
//           panel="firewall-rules"
//           className="text-purple-700 hover:text-purple-900"
//         >
//           <Link className="no-underline" to="/firewall-rules">
//             Firewall Rules
//           </Link>
//         </SlTab>

//         <SlTabPanel name="url-blocking">
//           {location.pathname === "/" && children}
//         </SlTabPanel>
//         <SlTabPanel name="custom-categories">
//           {location.pathname === "/about" && children}
//         </SlTabPanel>
//         <SlTabPanel name="domain-analytics">
//           {location.pathname === "/domain-analytics" && children}
//         </SlTabPanel>
//         {/* New Firewall Rules Panel */}
//         <SlTabPanel name="firewall-rules">
//           {location.pathname === "/firewall-rules" && children}
//         </SlTabPanel>
//       </SlTabGroup>
      
//       <SlTab active={location.pathname === "/relationship"} slot="nav" panel="relationship">
//     <Link className="no-underline" to="/relationship">
//         relationship
//     </Link>
// </SlTab>
// <SlTabPanel name="relationship">{children}</SlTabPanel>

//     </div>
//   );
// }

// // Update the styles to include firewall-rules tab
// const styles = `
//   sl-tab-group::part(tabs) {
//     border-bottom: 2px solid #e2e8f0;
//   }

//   sl-tab::part(base) {
//     padding: 0.75rem 1rem;
//     color: #4a5568;
//     font-weight: 500;
//     transition: all 0.2s;
//   }

//   sl-tab[active]::part(base) {
//     color: #6b46c1;
//     border-bottom: 2px solid #6b46c1;
//   }

//   sl-tab:not([active])::part(base):hover {
//     color: #2d3748;
//   }

//   sl-tab-panel::part(base) {
//     padding: 1.5rem 0;
//   }

//   sl-tab[panel="domain-analytics"]::part(base),
//   sl-tab[panel="firewall-rules"]::part(base) {
//     display: flex;
//     align-items: center;
//     gap: 0.5rem;
//   }

//   sl-tab[panel="domain-analytics"][active]::part(base),
//   sl-tab[panel="firewall-rules"][active]::part(base) {
//     background-color: rgba(107, 70, 193, 0.05);
//   }
// `;

// // Add styles to document
// const styleSheet = new CSSStyleSheet();
// styleSheet.replaceSync(styles);
// document.adoptedStyleSheets = [...document.adoptedStyleSheets, styleSheet];

// export { TabNavigation };

import React from "react";
import { useLocation } from "react-router-dom";
import { Link } from './link';
import {
  SlTab,
  SlTabGroup,
  SlTabPanel,
} from "@shoelace-style/shoelace/dist/react";

function TabNavigation({ children }) {
  const location = useLocation();
  
  return (
    <div className="space-y-4">
      <div className="text-center mb-6">
        <h1 className="text-3xl font-bold text-indigo-800 mb-2">
          Category Blocking
        </h1>
        <p className="text-purple-600">Configure URL blocking rules for your host groups</p>
      </div>

      <SlTabGroup>
        <SlTab 
          active={location.pathname === "/"} 
          slot="nav" 
          panel="url-blocking"
          className="text-purple-700 hover:text-purple-900"
        >
          <Link className="no-underline" to="/">
            URL Blocking
          </Link>
        </SlTab>
        <SlTab 
          active={location.pathname === "/about"} 
          slot="nav" 
          panel="custom-categories"
          className="text-purple-700 hover:text-purple-900"
        >
          <Link className="no-underline" to="/about">
            Custom Categories
          </Link>
        </SlTab>
        <SlTab 
          active={location.pathname === "/domain-analytics"} 
          slot="nav" 
          panel="domain-analytics"
          className="text-purple-700 hover:text-purple-900"
        >
          <Link className="no-underline" to="/domain-analytics">
            Domain Analytics
          </Link>
        </SlTab>
        <SlTab 
          active={location.pathname === "/firewall-rules"} 
          slot="nav" 
          panel="firewall-rules"
          className="text-purple-700 hover:text-purple-900"
        >
          <Link className="no-underline" to="/firewall-rules">
            Firewall Rules
          </Link>
        </SlTab>
        {/* relationship Tab - Added inside SlTabGroup */}
        <SlTab 
          active={location.pathname === "/relationship"} 
          slot="nav" 
          panel="relationship"
          className="text-purple-700 hover:text-purple-900"
        >
          <Link className="no-underline" to="/relationship">
            relationship
          </Link>
        </SlTab>

        <SlTabPanel name="url-blocking">
          {location.pathname === "/" && children}
        </SlTabPanel>
        <SlTabPanel name="custom-categories">
          {location.pathname === "/about" && children}
        </SlTabPanel>
        <SlTabPanel name="domain-analytics">
          {location.pathname === "/domain-analytics" && children}
        </SlTabPanel>
        <SlTabPanel name="firewall-rules">
          {location.pathname === "/firewall-rules" && children}
        </SlTabPanel>
        {/* relationship Panel */}
        <SlTabPanel name="relationship">
          {location.pathname === "/relationship" && children}
        </SlTabPanel>
      </SlTabGroup>
    </div>
  );
}

// Styles
const styles = `
  sl-tab-group::part(tabs) {
    border-bottom: 2px solid #e2e8f0;
    display: flex;
    justify-content: center;
    gap: 1rem;
  }

  sl-tab::part(base) {
    padding: 0.75rem 1rem;
    color: #4a5568;
    font-weight: 500;
    transition: all 0.2s;
    border-radius: 0.375rem;
  }

  sl-tab[active]::part(base) {
    color: #6b46c1;
    border-bottom: 2px solid #6b46c1;
    background-color: rgba(107, 70, 193, 0.05);
  }

  sl-tab:not([active])::part(base):hover {
    color: #2d3748;
    background-color: rgba(107, 70, 193, 0.02);
  }

  sl-tab-panel::part(base) {
    padding: 1.5rem 0;
  }

  sl-tab[panel="domain-analytics"]::part(base),
  sl-tab[panel="firewall-rules"]::part(base),
  sl-tab[panel="relationship"]::part(base) {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  sl-tab[panel="domain-analytics"][active]::part(base),
  sl-tab[panel="firewall-rules"][active]::part(base),
  sl-tab[panel="relationship"][active]::part(base) {
    background-color: rgba(107, 70, 193, 0.05);
  }
`;

// Add styles to document
const styleSheet = new CSSStyleSheet();
styleSheet.replaceSync(styles);
document.adoptedStyleSheets = [...document.adoptedStyleSheets, styleSheet];

export { TabNavigation };
