import { test, expect } from '@playwright/test'

for (const [width, height] of [[1366, 768], [1440, 900], [1536, 864]]) {
  test(`compact dashboard at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    await page.clock.setFixedTime(new Date('2026-09-07T22:30:00Z'))
    const errors = []
    page.on('pageerror', error => errors.push(error.message))
    await page.goto('/')
    await expect(page.locator('.leaflet-overlay-pane path')).toHaveCount(263)
    await expect(page.getByText('Random Forest model', { exact: true })).toHaveCount(0)
    await expect(page.locator('.control-intro')).toContainText('NYC time at opening')
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const map = await page.locator('.demand-map').boundingBox()
    expect(map.height).toBeGreaterThan(350)
    const last = await page.locator('.recommendation').last().boundingBox()
    expect(last.y + last.height).toBeLessThan(height)
    const list = await page.locator('.recommendations ol').boundingBox()
    expect(last.y + last.height).toBeLessThanOrEqual(list.y + list.height + 1)
    // Selection updates styling on the existing polygon nodes, not a new layer.
    await page.locator('.leaflet-overlay-pane path').first().evaluate(node => { window.originalPolygon = node })
    await page.locator('.recommendation').first().click()
    await expect(page.locator('.selection-card')).toBeVisible()
    await page.waitForTimeout(550)
    expect(await page.evaluate(() => window.originalPolygon.isConnected)).toBe(true)
    expect(await page.evaluate(() => scrollY)).toBe(0)
    await page.getByRole('button', { name: 'Clear selected zone' }).click()
    await page.waitForTimeout(550)
    await page.screenshot({ path: `test-results/compact-${width}x${height}.png` })
    expect(errors).toEqual([])
  })
}
