# coding:utf-8
import os
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait  # available since 2.4.0
from selenium.webdriver.support import expected_conditions as EC  # available since 2.26.0
from selenium.webdriver.chrome.service import Service
import time
import json
import platform
from fake_useragent import UserAgent

'''
from selenium import webdriver
# 进入浏览器设置
options = webdriver.ChromeOptions()
# 更换头部
options.add_argument('user-agent=ywy')

browser = webdriver.Chrome(options=options)
url = "https://httpbin.org/get?"

browser.get(url)
print(browser.page_source)
browser.close()
二.浏览器内核
只要你执行navigator.webdriver返回值是true就是浏览器内核访问

如果不是返回值是undefined

selenium为了解决这个需进行js 注入

from selenium import webdriver
browser = webdriver.Chrome()
script='Object.defineProperties(navigator, {webdriver:{get:()=>undefined}})'
browser.execute_script(script)
'''
def get_m3u8_url(page_url):
    chrome_options = Options()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')

    prefs = {
        # 不加载图片,加快访问速度
        "profile.managed_default_content_settings.images": 1,
        "profile.content_settings.plugin_whitelist.adobe-flash-player": 1,
        "profile.content_settings.exceptions.plugins.*,*.per_resource.adobe-flash-player": 1,
    }
    chrome_options.add_experimental_option('prefs', prefs)
    chrome_options.add_experimental_option('w3c', False)
    # 此步骤很重要，设置为开发者模式，防止被各大网站识别出来使用了Selenium
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])

    #chrome_options.add_argument('--user-agent="Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.25 Safari/537.36 Core/1.70.3741.400 QQBrowser/10.5.3863.400"')
    '''
    driver = webdriver.Chrome(chrome_options=chrome_options,
                              executable_path=r'C:\WebDrivers\ChromeDriver\chromedriver_win32\chromedriver.exe')
    '''

    d = DesiredCapabilities.CHROME
    #d['loggingPrefs'] = {'performance': 'ALL'}
    d['loggingPrefs'] = {
        'browser': 'ALL',
        'performance': 'ALL',
    }
    d['perfLoggingPrefs'] = {
        'enableNetwork': True,
        'enablePage': False,
        'enableTimeline': False
    }

    '''
    c_service = Service('chromedriver')
    c_service.command_line_args()
    c_service.start()
    '''

    browser = webdriver.Chrome('chromedriver', desired_capabilities=d, options=chrome_options)
    '''
    只要你执行navigator.webdriver返回值是true就是浏览器内核访问,如果不是返回值是undefined
    selenium为了解决这个需进行js 注入
    '''
    script = 'Object.defineProperties(navigator, {webdriver:{get:()=>undefined}})'
    browser.execute_script(script)
    for typ in browser.log_types:
        print("log_types: " + typ)
    try:
        browser.set_page_load_timeout(30)
        browser.set_script_timeout(30)
        browser.get(page_url)

        print("Title: " + browser.title)
        wait = WebDriverWait(browser, 10)
        # ch_list = driver.find_elements_by_xpath("//li[contains(@class, 'jw-video jw-reset')]")
        # get <div class="play-btn">
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'play-btn')))
            play_button = browser.find_element_by_class_name('play-btn')
            play_button.click()

        except TimeoutException:
            pass

        # 等待视频播放
        time.sleep(10)
        network_log = browser.get_log('performance')
        for entry in network_log:
            # print(entry)
            try:
                m = json.loads(entry['message'])['message']['params']['response']
                k = m['headers']['Content-Type']
                url = m['url']
                if k == 'application/vnd.apple.mpegurl' or k == 'application/dash+xml' or url.endswith('.m3u8') or ''.index("videoplayback"):
                    print("got the download url Type={},"
                          "url={} "
                          "from page="
                          "{}".format(k, url, page_url))
                    break
            except Exception as ee:
                pass
        # 需定时清除浏览器cookies
        cookies = browser.get_cookies()
        print(f"main: cookies = {cookies}")
        browser.delete_all_cookies()
    except BaseException as e:
        print('error ' + str(e))
    finally:
        browser.stop_client()
        browser.close()
        browser.quit()
        #c_service.stop()
        '''
        if (platform.system() == 'Windows'):
            os.system('taskkill /im chromedriver.exe /F')
            os.system('taskkill /im chrome.exe /F')
        else:
            os.system('killall -9 chromedriver')
            os.system('killall -9 chrome')
        '''

if __name__ == '__main__':
    urls = [
        #'http://www.ktkkt.com/yo/3019/player-0-0.html',
        #'https://v.qq.com/x/cover/2j5kilwvtepehti.html',
        'https://dood.watch/e/vltfjete1uyx'
    ]
    while True:
        for url in urls:
            get_m3u8_url(url)
        time.sleep(2)

'''
=====================================================================================================================
python + selenium + chrome 如何清理浏览器缓存
---------------------------------------------------------------------------------------------------------------------
1. 背景
在使用selenium + chrome浏览器渲染模式爬取数据时，如果并发任务过多，或者爬虫的运行时间很长，那么很容易出现浏览器崩溃的现象，如下： 
这一般是资源消耗过大造成的（据说chrome浏览器有内存泄漏的情况。或者是浏览器缓存过大，越堆越多）。selenium模拟浏览器会产生大量的临时文件，那如何解决这个问题呢？ 
之前提出一个解决方法，就是使用headless模式，减少渲染文件的产生，文章可以参考：http://blog.csdn.net/zwq912318834/article/details/79000040
  
3. 清除浏览器缓存
3.1. 只清cookie
# 清除浏览器cookies
cookies = browser.get_cookies()
print(f"main: cookies = {cookies}")
browser.delete_all_cookies()

3.2. 清除浏览器所有缓存垃圾
在selenium爬虫启动时，定时开一个窗口，在地址栏键入：chrome://settings/content 或 chrome://settings/privacy，然后由程序，像操作普通网页一样，对浏览器进行设置，“ 清除数据 ”，然后进行保存。如下所示： 
关于selenium窗口切换可以参考这篇文章：http://blog.csdn.net/zwq912318834/article/details/79206953

=====================================================================================================================
4.python selenium 执行完毕关闭chromedriver进程
---------------------------------------------------------------------------------------------------------------------
因为使用多次以后发现进程中出现了很多chromedriver的残留，造成卡顿，所以决定优化一下。
这个问题困扰了楼主很久，百度谷歌查来查去都只有java，后面根据java和selenium结合找出了python如何执行完把chromedriver进程关闭

Python控制chromedriver的开启和关闭的包是Service
#创建的时候需要把chromedriver.exe的位置写在Service的XXX部分,需要调用他的命令行方法，不然报错然后启动就可以了

---------------------------------------------------------------------------------------------------------------------
from selenium.webdriver.chrome.service import Service

c_service = Service('xxx')
c_service.command_line_args()
c_service.start()
driver = webdriver.Chrome()
driver.get("http://www.baidu.com")
#关闭的时候用quit()而不是采用close(),close只会关闭当前页面，quit会推出驱动别切关闭所关联的所有窗口
#最后执行完以后就关闭
driver.quit()
c_service.stop()

---------------------------------------------------------------------------------------------------------------------

#嫌麻烦也可以直接使用python的os模块执行下面两句话结束进程
os.system('taskkill /im chromedriver.exe /F')
os.system('taskkill /im chrome.exe /F')
=====================================================================================================================
'''
