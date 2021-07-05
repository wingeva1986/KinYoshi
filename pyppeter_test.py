import logging
import asyncio
from pyppeteer import launch
from pyquery import PyQuery as pq
from pyppeteer.errors import TimeoutError


logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(levelname)s: %(message)s')
INDEX_URL = 'https://dynamic2.scrape.cuiqingcai.com/page/{page}'
TIMEOUT = 10
TOTAL_PAGE = 10
WINDOW_WIDTH, WINDOW_HEIGHT = 1366, 768
HEADLESS = False
# import pyppeteer.chromium_downloader
# print('默认版本是：{}'.format(pyppeteer.__chromium_revision__))
# print('可执行文件默认路径：{}'.format(pyppeteer.chromium_downloader.chromiumExecutable.get('win64')))
# print('win64平台下载链接为：{}'.format(pyppeteer.chromium_downloader.downloadURLs.get('win64')))

browser, tab = None, None
async def init():
    global browser, tab
    browser = await launch(headless=HEADLESS, args=['--disable-infobars', f'--window-size={WINDOW_WIDTH},{WINDOW_HEIGHT}'])
    tab = await browser.newPage()
    await tab.setViewport({'width': WINDOW_WIDTH, 'height': WINDOW_HEIGHT})


async def scrape_page(url, selector):
    logging.info('scraping %s', url)
    js = '''() =>{
        Object.defineProperties(navigator,{
        webdriver:{
            get: () => false
            }
        })
    }'''
    try:
        await tab.goto(url)
        await tab.evaluate(js)
        await tab.waitForSelector(selector, options={
            'timeout': TIMEOUT * 1000
        })
    except TimeoutError:
        logging.error('error occurred while scraping %s', url, exc_info=True)

async  def  scrape_index(page):
    url = INDEX_URL.format(page=page)
    await  scrape_page(url, '.item  .name')

async def parse_index():
    return await tab.querySelectorAllEval('.item .name', 'nodes => nodes.map(node => node.href)')

async def main():
   await init()
   try:
       for page in range(1, TOTAL_PAGE + 1):
           await scrape_index(page)
           detail_urls = await parse_index()
           logging.info('detail_urls %s', detail_urls)
   finally:
       await browser.close()
if __name__ == '__main__':
   asyncio.get_event_loop().run_until_complete(main())