import {captureWorkspace} from './captureWorkspace'
import {test, expect} from '@playwright/test'

test('save, reload, inspect, rename and delete a snapshot', async ({page}) => {
  const question='Show total revenue by category.'
  const sql='SELECT category, revenue FROM revenue_by_category'
  const result={sql,columns:['category','revenue'],rows:[['Kitchen','247.00']],execution:{row_count:1,duration_ms:2,truncated:false},
    analysis:{summary:'Kitchen generated $247.00.',charts:['bar','table'],formatted_sql:sql,units:['','USD']}}
  const date='2025-01-02T12:00:00Z'
  let title='', posts=0, ran=false
  await page.route('**/api/**', async route=>{
    const path=new URL(route.request().url()).pathname
    const method=route.request().method()
    let data:unknown=[]
    if(path==='/api/conversations') data=method==='POST'?{id:'thread'}:[{id:'thread',title:'Revenue'}]
    if(path==='/api/conversations/thread') data=ran?[{id:'run',question}]:[]
    if(path==='/api/conversations/thread/query'){ran=true;data={id:'run',question,result}}
    if(path==='/api/query-runs/run') data={question,result,created_at:date}
    if(path==='/api/dashboards' && method==='POST'){
      posts++
      if(posts===1)return route.fulfill({status:503,json:{error:{message:'Try again'}}})
      expect(route.request().postDataJSON()).toEqual({title:'Sales report',run_id:'run'})
      title='Sales report';data={id:'card'}
    } else if(path==='/api/dashboards')data=title?[{id:'card',title,generated_at:date}]:[]
    if(path==='/api/dashboards/card'){
      if(method==='PATCH') title=route.request().postDataJSON().title
      if(method==='DELETE') title=''
      data={question,result,generated_at:date}
    }
    await route.fulfill({json:data})
  })
  await page.goto('/')
  await page.getByLabel('Business question').fill(question)
  await page.getByRole('button',{name:'Run query'}).click()
  const button=(name:string)=>page.getByRole('button',{name,exact:true})
  const modes=page.getByRole('group',{name:'Visualization'})
  await modes.getByRole('button',{name:'Table'}).press('Enter')
  await expect(modes.getByRole('button',{name:'Table'})).toHaveAttribute('aria-pressed','true')
  await expect(page.locator('.recharts-surface')).toHaveCount(0)
  await expect(page.getByRole('cell',{name:'247.00'})).toBeVisible()
  await modes.getByRole('button',{name:'Bar'}).press('Enter')
  await expect(page.locator('.recharts-surface').first()).toBeVisible()
  await button('Bookmark this Page').click()
  const input=page.getByLabel('Title')
  await expect(input).toHaveValue(question)
  const original=page.viewportSize()!
  for(const width of [390,768,1280,1440]){
    await page.setViewportSize({width,height:800})
    const bounds=await page.getByRole('dialog').boundingBox()
    expect(bounds).toBeTruthy()
    expect(bounds!.x).toBeGreaterThanOrEqual(0)
    expect(bounds!.y).toBeGreaterThanOrEqual(0)
    expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(width)
    expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(800)
  }
  await page.setViewportSize(original)
  await input.fill('  ')
  await expect(button('Save')).toBeDisabled()
  await input.press('Escape')
  expect(posts).toBe(0)
  await button('Bookmark this Page').click()
  await input.fill(' Sales report ')
  await button('Save').click()
  await expect(page.getByRole('alert')).toHaveText('Try again')
  await button('Save').click()
  await button('Contents').click()
  await expect(button('Sales report')).toBeVisible()
  await page.reload()
  await expect(page.locator('.user-question')).toBeVisible()
  await button('Contents').click()
  await button('Sales report').click()
  await expect(page.getByText(/^Saved bookmark ·/)).toBeVisible()
  await expect(page.getByRole('region',{name:'Query results'}).getByText(question,{exact:true})).toBeVisible()
  await expect(page.getByRole('cell',{name:'247.00'})).toBeVisible()
  await expect(page.locator('.recharts-surface').first()).toBeVisible()
  await page.getByText('Behind the Numbers · SQL').click()
  await expect(page.locator('pre')).toContainText(sql)
  await button('Contents').click()
  await button('Rename').click()
  await expect(input).toHaveValue('Sales report')
  await input.fill('Category totals')
  await button('Save').click()
  await expect(button('Category totals')).toBeVisible()
  await button('Delete').click()
  await button('Confirm delete').click()
  await expect(button('Category totals')).toHaveCount(0)
  expect(posts).toBe(2)
})

test('saves an earlier turn and a selected dashboard across reload', async ({page},info)=>{
  const questions=['First analysis','Middle analysis','Last analysis']
  const date='2025-01-02T12:00:00Z'
  const runs=questions.map((question,i)=>({id:'run'+i,question,created_at:date,
    result:{sql:'SELECT '+i,columns:i===0?['category','revenue']:['count'],rows:i===0?[['Kitchen','247.00']]:[[i]],analysis:{summary:i===0?'Kitchen generated $247.00.':'Order count is '+i+'.',charts:i===0?['bar','table']:['kpi','table'],units:i===0?['','USD']:['']},execution:{row_count:1,duration_ms:1,truncated:false}}}))
  let count=0,title=''
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname,method=route.request().method()
    let data:unknown=[]
    if(path==='/api/conversations')data=method==='POST'?{id:'c'}:[{id:'c',title:'Research'}]
    if(path==='/api/conversations/c')data=runs.slice(0,count)
    if(path==='/api/conversations/c/query')data=runs[count++]
    if(path.startsWith('/api/query-runs/'))data=runs.find(r=>path.endsWith(r.id))
    if(path==='/api/dashboards'&&method==='POST'){
      expect(route.request().postDataJSON()).toEqual({title:questions[0],run_id:'run0'})
      data={id:'single'}
    }else if(path==='/api/dashboards')data=title?[{id:'group',title,generated_at:date}]:[]
    if(path==='/api/conversations/c/dashboards'){
      const body=route.request().postDataJSON()
      expect(body.run_ids.sort()).toEqual(['run0','run2'])
      title=body.title;data={id:'group'}
    }
    if(path==='/api/dashboards/group'){
      if(method==='PATCH')title=route.request().postDataJSON().title
      if(method==='DELETE')title=''
      data={analyses:[runs[0],runs[2]].map(r=>({...r,generated_at:date}))}
    }
    await route.fulfill({json:data})
  })
  await page.goto('/')
  for(const q of questions){
    await page.getByLabel('Business question').fill(q)
    await page.getByRole('button',{name:'Run query'}).click()
    await expect(page.locator('.user-question').last()).toHaveText(q)
  }
  await page.getByRole('button',{name:'Previous entry'}).click()
  await expect(page.locator('.user-question')).toHaveText(questions[1])
  await page.getByRole('button',{name:'Previous entry'}).click()
  await expect(page.locator('.user-question')).toHaveText(questions[0])
  await captureWorkspace(page,info,'conversation')
  await page.getByRole('button',{name:'Bookmark this Page'}).first().click()
  await page.getByRole('dialog').getByRole('button',{name:'Save',exact:true}).click()
  await expect(page.getByText('Page bookmarked.')).toBeVisible()
  await page.getByRole('button',{name:'Contents',exact:true}).click()
  await page.getByLabel('Select Last analysis').check()
  await page.getByLabel('Select First analysis').check()
  await page.getByRole('button',{name:'Create Chapter'}).click()
  await page.getByLabel('Title').fill('Board')
  await page.getByRole('dialog').getByRole('button',{name:'Save',exact:true}).click()
  await expect(page.getByRole('button',{name:'Board',exact:true})).toBeVisible()
  await page.reload()
  await expect(page.locator('.user-question')).toBeVisible()
  await page.getByRole('button',{name:'Contents',exact:true}).click()
  await page.getByRole('button',{name:'Board',exact:true}).click()
  await expect(page.locator('.chapterpages strong')).toHaveText([questions[0],questions[2]])
  await captureWorkspace(page,info,'dashboard')
  await page.getByRole('button',{name:'Rename'}).click()
  await page.getByLabel('Title').fill('Reviewed')
  await page.getByRole('dialog').getByRole('button',{name:'Save',exact:true}).click()
  await page.getByRole('button',{name:'Open chapter'}).click()
  await expect(page.locator('.user-question')).toHaveText(questions[0])
  await page.getByRole('button',{name:'Next entry'}).click()
  await expect(page.locator('.user-question')).toHaveText(questions[2])
  await page.getByRole('button',{name:'Chapter',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Reviewed'})).toBeVisible()
  await page.getByRole('button',{name:'Delete',exact:true}).click()
  await page.getByRole('button',{name:'Confirm delete'}).click()
  await expect(page.getByRole('button',{name:'Reviewed'})).toHaveCount(0)
})


test('standalone question explains why the page cannot be bookmarked',async({page})=>{
  await page.route('**/api/**',route=>route.fulfill({json:route.request().url().endsWith('/api/query')
    ?{sql:'SELECT 1',columns:['count'],rows:[[1]],execution:{row_count:1,duration_ms:1,truncated:false}}:[]}))
  await page.goto('/')
  await page.getByRole('button',{name:'Single question',exact:true}).click()
  await page.getByLabel('Business question').fill('Count orders')
  await page.getByLabel('Business question').press('Enter')
  await expect(page.getByRole('button',{name:'Bookmark unavailable'})).toBeDisabled()
  await expect(page.getByText(/Single questions have no saved run/)).toBeVisible()
  await expect(page.getByRole('button',{name:'Bookmark this Page'})).toHaveCount(0)
})

test('multi-metric chart modes keep exact table values',async({page})=>{
  const result={sql:'SELECT day, sales, refunds',columns:['day','sales','refunds'],
    rows:[['2026-01-01','247.00','20.10'],['2026-01-02','220.50','9.90']],
    analysis:{charts:['line','bar','table'],units:['','USD','USD'],summary:'Daily totals',formatted_sql:'SELECT day, sales, refunds'},
    execution:{row_count:2,duration_ms:2,truncated:false}}
  await page.route('**/api/**',route=>route.fulfill({json:route.request().url().endsWith('/api/query')?result:[]}))
  await page.goto('/')
  await page.getByRole('button',{name:'Single question',exact:true}).click()
  await page.getByLabel('Business question').fill('Compare daily sales and refunds')
  await page.getByLabel('Business question').press('Enter')
  const modes=page.getByRole('group',{name:'Visualization'})
  await expect(modes.getByRole('button',{name:'Line'})).toHaveAttribute('aria-pressed','true')
  await expect(page.locator('.recharts-line')).toHaveCount(2)
  await modes.getByRole('button',{name:'Grouped bar'}).press('Space')
  await expect(page.locator('.recharts-bar')).toHaveCount(2)
  await modes.getByRole('button',{name:'Table'}).click()
  await expect(page.getByRole('cell',{name:'9.90',exact:true})).toBeVisible()
  await expect(modes.getByRole('button',{name:'KPI'})).toHaveCount(0)
})
