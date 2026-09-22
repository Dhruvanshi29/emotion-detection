import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

test('landing page is calm, navigable, and has no serious axe findings', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /feelings deserve/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /begin your first check-in/i })).toBeVisible()
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
  expect(results.violations.filter((item) => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
})

test('registration keeps age and care boundaries clear on small screens', async ({ page }) => {
  await page.goto('/register')
  await expect(page.getByRole('heading', { name: /calm space/i })).toBeVisible()
  await expect(page.getByLabel('Birth year')).toBeVisible()
  await expect(page.getByText(/not emergency or medical care/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /create my private space/i })).toBeVisible()
})
