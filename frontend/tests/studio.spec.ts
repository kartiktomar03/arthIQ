import {captureWorkspace} from './captureWorkspace'
import { expect, test } from '@playwright/test'

test('mobile navigation, keyboard composer, follow-up, SQL and retrieval details',async({page,context})=>{
  const errors:string[]=[]
  page.on('pageerror',e=>errors.push(e.message))
  await context.grantPermissions(['clipboard-read','clipboard-write'])
  let created=false
  const questions:string[]=[]
  const sql='SELECT COUNT(*) FROM shop.orders'
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname
    let data:unknown=[]
    if(path==='/api/conversations'){
      if(route.request().method()==='POST'){created=true;data={id:'studio'}}
      else data=created?[{id:'studio',title:'Order counts'}]:[]
    }
    if(path.endsWith('/query')){
      questions.push(route.request().postDataJSON().question)
      if(questions.length===3)return route.fulfill({status:422,json:{error:{message:'Specify a metric.'}}})
      await new Promise(resolve=>setTimeout(resolve,300))
      data={id:'turn'+questions.length,question:questions.at(-1),result:{sql,columns:['count'],column_types:['int8'],rows:[[8]],
        analysis:{summary:'Completed order count is 8.',formatted_sql:'SELECT COUNT(*)\nFROM shop.orders',charts:['kpi','table'],units:['']},
        execution:{row_count:1,duration_ms:2,truncated:false},retrieval:{mode:'rag',status:'ok',tables:['orders'],relationships:[],document_count:4,expanded:false,join_count:0,duration_ms:12,datasource_id:'shop-fixture'}}}
    }
    return route.fulfill({json:data})
  })
  await page.setViewportSize({width:375,height:800})
  await page.goto('/')
  await page.getByRole('button',{name:'Contents',exact:true}).first().click()
  await page.getByRole('button',{name:'New Entry',exact:true}).click()
  await page.getByRole('button',{name:'How many completed orders do we have?'}).click()
  const input=page.getByLabel('Business question')
  await input.press('Shift+Enter')
  await expect(input).toHaveValue(/\n$/)
  await input.press('Enter')
  await expect(page.getByRole('button',{name:'Running…'})).toBeDisabled()
  await expect(page.getByText('Completed order count is 8.')).toBeVisible()
  await page.getByText('Behind the Numbers · SQL').click()
  await page.getByText('Copy executed SQL').click()
  expect(await page.evaluate(()=>navigator.clipboard.readText())).toBe(sql)
  await page.getByText('References · Schema retrieval').click()
  await expect(page.getByText('Purchase records and completion status',{exact:false})).toBeVisible()
  await input.fill('Now show only Kitchen.')
  await input.press('Enter')
  await expect(page.locator('.user-question')).toHaveText('Now show only Kitchen.')
  await page.getByRole('button',{name:'Evidence →'}).click()
  await expect(page.getByRole('cell',{name:'8',exact:true})).toBeVisible()
  await input.fill('Best?')
  await input.press('Enter')
  await expect(page.getByRole('alert')).toHaveText('Specify a metric.')
  for(const width of [375,390,430,768,1280,1440,1920]){
    await page.setViewportSize({width,height:900})
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
  }
  expect(errors).toEqual([])
})

test('ArthIQ workspace at desktop and mobile sizes',async({page},info)=>{
  await page.route('**/api/**',route=>route.fulfill({json:[]}))
  const errors:string[]=[]
  page.on('console',msg=>{if(msg.type()==='error')errors.push(msg.text())})
  for(const width of [1440,1280,768,390]){
    await page.setViewportSize({width,height:850})
    await page.goto('/')
    await expect(page).toHaveTitle(/ArthIQ/)
    await expect(page.getByRole('heading',{name:/Every Number.*Has a Story/})).toBeVisible()
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true)
    await expect(page.getByLabel('Business question')).toBeInViewport()
    
  }
  await captureWorkspace(page,info,'empty')
  expect(errors).toEqual([])
})

