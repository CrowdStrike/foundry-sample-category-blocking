import { test as baseTest } from '@playwright/test';
import { CategoryBlockingPage } from './pages/CategoryBlockingPage';

type FoundryFixtures = {
  categoryBlockingPage: CategoryBlockingPage;
};

export const test = baseTest.extend<FoundryFixtures>({
  categoryBlockingPage: async ({ page }, use) => {
    await use(new CategoryBlockingPage(page));
  },
});

export { expect } from '@playwright/test';
