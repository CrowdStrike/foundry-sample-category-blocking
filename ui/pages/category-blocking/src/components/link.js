import React, { useContext } from "react";
import { Link as ReactRouterLink } from "react-router-dom";
import { FalconApiContext } from "../contexts/falcon-api-context.js";

function Link({ 
  children, 
  useFalconNavigation = false, 
  to, 
  className = "", 
  variant = "default" 
}) {
  const { navigation } = useContext(FalconApiContext);

  // Base styles for different variants
  const styles = {
    default: "text-purple-600 hover:text-purple-800 transition-colors duration-200",
    button: "inline-block px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-all duration-200 shadow-sm hover:shadow-md",
    tab: "px-3 py-2 text-sm font-medium hover:text-purple-700 transition-colors duration-200",
    subtle: "text-gray-600 hover:text-purple-600 transition-colors duration-200 text-sm"
  };

  // Combine provided className with variant styles
  const combinedClassName = `${styles[variant]} ${className}`.trim();

  if (useFalconNavigation) {
    return (
      <a 
        onClick={(e) => {
          e.preventDefault();
          navigation.onClick(e);
        }} 
        href={to}
        className={combinedClassName}
      >
        {children}
      </a>
    );
  }

  return (
    <ReactRouterLink 
      to={to} 
      className={combinedClassName}
    >
      {children}
    </ReactRouterLink>
  );
}

// Example usage:
// <Link variant="button" to="/create">Create New</Link>
// <Link variant="tab" to="/categories">Categories</Link>
// <Link variant="subtle" to="/help">Help</Link>

export { Link };
