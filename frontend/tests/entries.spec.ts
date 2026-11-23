import {expect,test} from '@playwright/test'

test('Contents tracks persisted entries independently of saved-library failures',async({page})=>{
  const entries=Array.from({length:55},(_,i)=>({id:'old'+i,title:'Earlier '+i}))
  const turns:{id:string,question:string,result:unknown}[]=[]
  const result={sql:'SELECT 1',columns:['count'],rows:[[1]],execution:{row_count:1,duration_ms:1,truncated:false}}
  let failDelete=true
  await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname.slice(5),method=req.method()
    const ok=(json:unknown)=>route.fulfill({json})
    if(path==='dashboards')return route.fulfill({status:503,json:{error:{message:'Saved library unavailable'}}})
    if(path==='conversations'){
      if(method==='GET' && turns.length===1)return route.fulfill({status:503,json:{error:{message:'Index refresh unavailable'}}})
      if(method==='GET')return ok(entries)
      entries.unshift({id:'active',title:'New conversation'});return ok({id:'active'})
    }
    if(path==='conversations/active/query'){
      const q=req.postDataJSON().question
      if(!turns.length)entries[0].title=q
      const turn={id:'run'+turns.length,question:q,result};turns.push(turn);return ok({...turn,title:entries[0].title})
    }
    if(path.startsWith('query-runs/'))return ok({...turns.find(t=>path.endsWith(t.id)),created_at:'2025-01-01'})
    const id=path.split('/')[1],i=entries.findIndex(t=>t.id===id)
    if(i===-1)return route.fulfill({status:404,json:{}})
    if(method==='PATCH'){entries[i].title=req.postDataJSON().title;return ok(entries[i])}
    if(method==='DELETE'){
      if(failDelete){failDelete=false;return route.fulfill({status:503,json:{error:{message:'Retry deletion'}}})}
      entries.splice(i,1);return ok({deleted:true})
    }
    return ok(id==='active'?turns:[])
  })
  await page.goto('/')
  const index=page.getByRole('navigation',{name:'Recent Entries'}),contents=page.getByRole('button',{name:'Contents',exact:true})
  await expect(index.locator('.entry-name')).toHaveCount(55)
  await page.getByRole('button',{name:'New Entry',exact:true}).click()
  await expect(index.locator('[aria-current=page]')).toContainText('New Entry')
  for(const q of ['Count orders','Only completed','Show the latest month']){
    await page.getByLabel('Business question').fill(q)
    await page.getByLabel('Business question').press('Enter')
    await expect(page.locator('.user-question')).toHaveText(q)
    if(turns.length===1){
      await contents.click()
      await expect(index.locator('[aria-current=page]')).toContainText('Count orders')
      await page.getByRole('button',{name:'Active conversation'}).click()
    }
  }
  await contents.click()
  await expect(index.locator('.entry-name').first()).toContainText('Count orders')
  await page.getByLabel('Filter entries').fill('Earlier 54')
  await expect(index.locator('.entry-name')).toHaveCount(2)
  await expect(index.locator('[aria-current=page]')).toContainText('Count orders')
  await page.getByRole('button',{name:'Actions for Count orders'}).click()
  await page.getByRole('button',{name:'Rename Entry',exact:true}).click()
  await page.getByLabel('Title',{exact:true}).fill('Order review')
  await page.getByRole('button',{name:'Save',exact:true}).click()
  await page.reload()
  await expect(page.locator('.user-question')).toHaveText('Show the latest month')
  await page.getByRole('button',{name:'Previous entry'}).click()
  await expect(page.locator('.user-question')).toHaveText('Only completed')
  await contents.click()
  await expect(index.locator('[aria-current=page]')).toContainText('Order review')
  for(const label of ['Earlier 54','Order review']){
    await page.getByRole('button',{name:'Actions for '+label,exact:true}).click()
    await page.getByRole('button',{name:'Delete Entry',exact:true}).click()
    await page.getByRole('button',{name:'Confirm delete'}).click()
    if(label==='Earlier 54'){
      await expect(page.getByRole('dialog').getByRole('alert')).toHaveText('Retry deletion')
      await page.getByRole('button',{name:'Confirm delete'}).click()
    }
    await expect(index.getByTitle(label,{exact:true})).toHaveCount(0)
  }
  await expect(page.getByRole('heading',{name:/Every Number/})).toBeVisible()
  expect(await page.evaluate(()=>localStorage.getItem('qp.conversation'))).toBe('new')
})
