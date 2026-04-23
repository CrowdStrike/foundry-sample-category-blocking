import { test as baseTest } from '@playwright/test';
import {
  FoundryHomePage, AppCatalogPage, config,
} from '@crowdstrike/foundry-playwright';
import { CategoryBlockingPage } from './pages/CategoryBlockingPage';

type FoundryFixtures = {
  foundryHomePage: FoundryHomePage;
  appCatalogPage: AppCatalogPage;
  categoryBlockingPage: CategoryBlockingPage;
  appName: string;
};

export const test = baseTest.extend<FoundryFixtures>({
  foundryHomePage: async ({ page }, use) => { await use(new FoundryHomePage(page)); },
  appCatalogPage: async ({ page }, use) => { await use(new AppCatalogPage(page)); },
  categoryBlockingPage: async ({ page }, use) => { await use(new CategoryBlockingPage(page)); },
  appName: async ({}, use) => { await use(config.appName); },
});

export { expect } from '@playwright/test';
