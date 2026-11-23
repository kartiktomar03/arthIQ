import {expect, type Page, type TestInfo} from '@playwright/test'

export async function captureWorkspace(page:Page,info:TestInfo,state:string){
  const original=page.viewportSize()!
  for(const width of [1440,1280,768,390]){
    await page.setViewportSize({width,height:850})
    const book=page.locator('.book:visible')
    if(width<=840 && await book.getAttribute('data-side')!=='1')await page.locator('.mobilebar button').click()
    if(state==='conversation')await expect(page.locator('.recharts-bar-rectangle').first()).toBeVisible()
    await page.evaluate(()=>window.scrollTo(0,0))
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await page.screenshot({path:info.outputPath(state+'-'+width+'.png'),fullPage:true})
  }
  await page.setViewportSize(original)
}
