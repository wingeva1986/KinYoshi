# coding=utf-8
import re
import requests
from scrapy import Selector
from utils.util_agent import choice_agent
from test_m3u8_downloader import IQIYIM3u8Downloader
from utils.CommonUtils import get_proxy
requests.packages.urllib3.disable_warnings()
headers = {
    'user-agent': choice_agent(),
}

# response = requests.get('https://www.2hanju.com/player/807_1_16.html', headers=headers, verify=False)
# selector = Selector(text=response.text)
# info_list = selector.xpath('//div[@class="list"]')
# for info in info_list:
#     play_url = info.xpath('a/@href').getall()
#     episode_name = info.xpath('a/text()').getall()
#     print(play_url, episode_name)


def request_redirect_url(url: str):
    response = requests.get(url, headers={"user-agent": choice_agent()}, verify=False, allow_redirects=False, proxies=get_proxy())
    if response.status_code == 200:
        return response.text
    return request_redirect_url(response.headers['Location'])

def parse_play_url(play_url: str):
    base_url = '/'.join(play_url.split('/')[:3])
    try:
        res_str = requests.get(
        play_url, headers={"user-agent": choice_agent()}, verify=False, proxies=get_proxy()).text
        selector = Selector(text=res_str)
        iframe_url = selector.xpath('//iframe/@src').get()
        iframe_url = base_url + iframe_url

        res_html = request_redirect_url(iframe_url)
        return re.findall(r"url: '(.*?)',", res_html)[0]
    except BaseException as e:
        return ''


for i in range(14, 17):
    play_url = f'https://www.2hanju.com/player/807_1_{i}.html'
    print(play_url)
    m3u8_url = parse_play_url(play_url)
    if m3u8_url:
        IQIYIM3u8Downloader().download(m3u8_url, f'E:\\YunBo\\美妙人声.{i}.ts',
                                    headers=headers, thread_num=10)
