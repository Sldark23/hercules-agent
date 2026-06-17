import { z } from 'zod'
import { randomUUID } from 'node:crypto'
import type { RegisteredTool } from './registry.js'

export const BrowserInput = z.object({
  action: z.enum([
    'navigate', 'click', 'type', 'screenshot', 'extract',
    'scroll', 'back', 'forward', 'close',
  ]),
  url: z.string().url().optional(),
  selector: z.string().optional(),
  text: z.string().optional(),
  waitUntil: z.enum(['load', 'domcontentloaded', 'networkidle']).optional().default('load'),
  timeout: z.number().positive().max(60_000).optional().default(30_000),
  fullPage: z.boolean().optional().default(false),
})

export type BrowserInput = z.infer<typeof BrowserInput>

export async function runBrowser(input: BrowserInput): Promise<string> {
  const { execSync } = await import('node:child_process')

  const script = buildPlaywrightScript(input)
  const result = execSync(`node -e "${script.replace(/"/g, '\\"').replace(/\n/g, ' ')}"`, {
    timeout: input.timeout + 5_000,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024,
  })

  return result.toString().trim()
}

function buildPlaywrightScript(input: BrowserInput): string {
  const id = randomUUID().slice(0, 8)

  switch (input.action) {
    case 'navigate': {
      if (!input.url) throw new Error('url required for navigate')
      return `
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ headless: true });
          const page = await browser.newPage();
          await page.goto('${input.url}', { waitUntil: '${input.waitUntil}', timeout: ${input.timeout} });
          const title = await page.title();
          const url = page.url();
          const content = await page.evaluate(() => document.body.innerText.slice(0, 5000));
          await browser.close();
          console.log(JSON.stringify({ title, url, content: content.slice(0, 2000) }));
        })();
      `
    }
    case 'screenshot': {
      if (!input.url) throw new Error('url required for screenshot')
      return `
        const { chromium } = require('playwright');
        const fs = require('fs');
        (async () => {
          const browser = await chromium.launch({ headless: true });
          const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
          await page.goto('${input.url}', { waitUntil: '${input.waitUntil}', timeout: ${input.timeout} });
          const buffer = await page.screenshot({ fullPage: ${input.fullPage} });
          console.log('data:image/png;base64,' + buffer.toString('base64'));
          await browser.close();
        })();
      `
    }
    case 'extract': {
      if (!input.url) throw new Error('url required for extract')
      return `
        const { chromium } = require('playwright');
        (async () => {
          const browser = await chromium.launch({ headless: true });
          const page = await browser.newPage();
          await page.goto('${input.url}', { waitUntil: '${input.waitUntil}', timeout: ${input.timeout} });
          const data = await page.evaluate(() => ({
            title: document.title,
            text: document.body.innerText.slice(0, 10000),
            html: document.body.innerHTML.slice(0, 5000),
            links: Array.from(document.querySelectorAll('a[href]')).map(a => ({ text: a.textContent?.trim(), href: a.href })).slice(0, 100),
          }));
          console.log(JSON.stringify(data));
          await browser.close();
        })();
      `
    }
    default:
      throw new Error(`Browser action "${input.action}" not yet implemented in inline mode`)
  }
}

export function createBrowserTool(): RegisteredTool {
  return {
    name: 'browser',
    description: 'Control a web browser — navigate, click, type, screenshot, extract content.',
    inputSchema: BrowserInput,
    category: 'web',
    requiresApproval: true,
    handler: async (input) => {
      const result = await runBrowser(input as BrowserInput)
      return { toolCallId: '', output: result }
    },
  }
}
