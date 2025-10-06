import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import "@shoelace-style/shoelace/dist/themes/light.css";
import { SlTab, SlTabGroup } from "@shoelace-style/shoelace/dist/react";

const customStyles = `
  sl-tab-group {
    position: relative;
  }
  sl-tab-group::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 1px;
    background-color: #E5E7EB;
  }
  sl-tab-group::part(base) {
    --sl-border-width: 0;
  }
  sl-tab-group::part(nav) {
    border: none !important;
  }
  sl-tab-group::part(tabs) {
    border: none !important;
  }
  sl-tab::part(base) {
    font-weight: 400;
    color: var(--sl-color-neutral-700);
    border-bottom: 2px solid transparent;
    transition: border-color 0.2s ease;
    position: relative;
    z-index: 1;
  }
  sl-tab[active]::part(base) {
    font-weight: 600;
    color: var(--sl-color-neutral-700);
    border-bottom: 2px solid rgb(26, 115, 232);
  }
`;

const styles = {
  header: {
    fontSize: '2rem',
    fontWeight: '600',
    marginBottom: '12px',
    textAlign: 'center',
  },
  subHeader: {
    fontSize: '0.875rem',
    color: 'var(--sl-color-neutral-500)',
    textAlign: 'center'
  },
  nav: {
    position: 'relative'
  },
  tabList: {
    display: 'flex',
    gap: '2rem',
  },
  tabGroup: {
    '--sl-spacing-medium': '0',
    position:'relative',
    borderBottom: '1px solid #E5E7EB',
    display: 'flex',
    justifyContent: 'center'
  },
  tab: {
    padding: '8px 16px',
    color: 'var(--sl-color-neutral-700)',
    position: 'relative',
  },
  activeTab: {
    fontWeight: '600',
  },
  content: {
    paddingTop: '1.5rem',
  }
};

export function TabNavigation({ children }) {
  const location = useLocation();

  return (
    <div className="max-w-screen-2xl mx-auto px-4">
      <style>{customStyles}</style>
      <div style={styles.container}>
        <h1 style={styles.header}>Category Blocking</h1>
        <p style={styles.subHeader}>Configure category based blocking rules for your host groups</p>
      </div>

      <SlTabGroup
        placement="bottom"
        style={styles.tabGroup}
      >
        <nav style={styles.nav}>
          <div style={styles.tabList}>
            {[
              { path: '/', label: 'Category Blocking Policy' },
              { path: '/about', label: 'Custom Categories' },
              { path: '/domain-analytics', label: 'Domain Analytics' },
              { path: '/firewall-rules', label: 'Firewall Rules' },
              { path: '/relationship', label: 'Relationship Graph' }
            ].map(({ path, label }) => (
              <SlTab
                key={path}
                panel={path.substring(1) || 'home'}
                active={location.pathname === path}
                style={{
                  ...styles.tab,
                  ...(location.pathname === path ? styles.activeTab : {})
                }}
              >
                <NavLink
                  to={path}
                  style={{
                    textDecoration: 'none',
                    color: 'inherit',
                  }}
                >
                  {label}
                </NavLink>
              </SlTab>
            ))}
          </div>
        </nav>
      </SlTabGroup>

      <div style={styles.content}>
        {children}
      </div>
    </div>
  );
}
