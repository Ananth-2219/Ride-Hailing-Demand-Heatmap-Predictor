import { test, expect } from '@playwright/test'

for (const timezoneId of ['Asia/Kolkata', 'America/Los_Angeles']) {
  test.describe(`browser timezone: ${timezoneId}`, () => {
    test.use({ timezoneId })

    test('NYC initialization, manual overrides, and fresh reload', async ({ page }) => {
      await page.clock.setFixedTime(new Date('2026-09-09T22:30:00Z'))
      const requests = []
      page.on('request', request => {
        if (request.url().includes('/api/demand?')) requests.push(request.url())
      })
      await page.goto('/')
      await expect(page.getByRole('combobox')).toHaveValue('Wed')
      await expect(page.getByRole('slider')).toHaveValue('18')
      await expect(page.locator('.control-intro')).toContainText('NYC time at opening: Wed, 18:30')
      await expect(page.locator('.time-badge')).toHaveText('Wednesday · 18:00')
      expect(requests[0]).toContain('day=Wed&hour=18')

      await page.getByRole('combobox').selectOption('Sat')
      await page.getByRole('slider').fill('9')
      await expect(page.locator('.time-badge')).toHaveText('Saturday · 09:00')
      // Device time changes must not overwrite the user's selection or snapshot.
      await page.clock.setFixedTime(new Date('2026-09-10T04:15:00Z'))
      await expect(page.getByRole('combobox')).toHaveValue('Sat')
      await expect(page.getByRole('slider')).toHaveValue('9')
      await expect(page.locator('.control-intro')).toContainText('Wed, 18:30')

      await page.reload()
      await expect(page.getByRole('combobox')).toHaveValue('Thu')
      await expect(page.getByRole('slider')).toHaveValue('0')
      await expect(page.locator('.time-badge')).toHaveText('Thursday · 00:00')
      await expect(page.locator('.control-intro')).toContainText('Thu, 00:15')
      await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(263)
    })
  })
}
