import { test as baseTest } from '@playwright/test';
import { FoundryHomePage } from './pages/FoundryHomePage';
import { AppCatalogPage } from './pages/AppCatalogPage';
import { CategoryBlockingPage } from './pages/CategoryBlockingPage';
import { config } from './config/TestConfig';

type FoundryFixtures = {
  foundryHomePage: FoundryHomePage;
  appCatalogPage: AppCatalogPage;
  categoryBlockingPage: CategoryBlockingPage;
  appName: string;
};

export const test = baseTest.extend<FoundryFixtures>({
  // Configure page with centralized settings
  page: async ({ page }, use) => {
    const timeouts = config.getPlaywrightTimeouts();
    page.setDefaultTimeout(timeouts.timeout);

    // Log configuration on first use
    if (!process.env.CONFIG_LOGGED) {
      config.logSummary();
      process.env.CONFIG_LOGGED = 'true';
    }

    await use(page);
  },

  // Page object fixtures with dependency injection
  foundryHomePage: async ({ page }, use) => {
    await use(new FoundryHomePage(page));
  },

  appCatalogPage: async ({ page }, use) => {
    await use(new AppCatalogPage(page));
  },

  categoryBlockingPage: async ({ page }, use) => {
    await use(new CategoryBlockingPage(page));
  },

  // App name from centralized config
  appName: async ({}, use) => {
    await use(config.appName);
  },
});

export { expect } from '@playwright/test';
