import re
import ast
import json
import base64
import requests
from requests import api
from requests.api import get
from scrapy import Selector, selector
headers = {
    'authority': 'playmgtvcache.ccyjjd.com',
    'sec-ch-ua': '" Not;A Brand";v="99", "Google Chrome";v="91", "Chromium";v="91"',
    'sec-ch-ua-mobile': '?0',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'sec-fetch-site': 'none',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'accept-language': 'zh-CN,zh;q=0.9',
    # 'cookie': 'UM_distinctid=17aae9ce95d5ce-0654f3ded13f0f-6373264-1fa400-17aae9ce95e8a3; kgdjhhhhnrfr=1; kgdjhhhhudd=18824%2C0; CNZZDATA1275919267=1734180052-1626426856-%7C1626432256; kgdjhhhhuuxs=8356; kgdjhhhhph=2342244e_5; CNZZDATA1279698470=2061654313-1626424362-%7C1626429762',
}

def get_url_from_iframe(res_str):
    selector = Selector(text=res_str)
    url = selector.xpath('//iframe/@src').get()
    return url


def get_damin(url: str):
    return '/'.join(url.split('/')[:3])


# https://www.iqiyi.com/v_19rrhe0cjw.html
# https://v.qq.com/x/cover/ww18u675tfmhas6/z0039jmvia6.html
# https://v.youku.com/v_show/id_XNTE0NzYzMjMwNA==.html
# https://www.mgtv.com/b/376923/12622674.html
play_api_url = 'https://playmgtvcache.ccyjjd.com/play.php?url=https://v.qq.com/x/cover/mzc002003q7sks5/x0039d840b6.html'
response = requests.get(play_api_url, headers=headers)
jx_api_url = get_url_from_iframe(response.text)

if not jx_api_url.startswith('http'):
    jx_api_url = get_damin(play_api_url) + '/' + jx_api_url
print(jx_api_url)
jx_api_res = requests.get(jx_api_url, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': play_api_url
})

jiexi_8090_url = get_url_from_iframe(jx_api_res.text)
jiexi_8090_res = requests.get(jiexi_8090_url, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': jx_api_url
})
print(jiexi_8090_url)

laobandq_url = get_url_from_iframe(jiexi_8090_res.text)
if not laobandq_url.startswith('http'):
    if laobandq_url.startswith('//'):
        laobandq_url = 'https:' + laobandq_url
print(laobandq_url)
laobandq_res = requests.get(laobandq_url, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': jiexi_8090_url
})

new_jx_api = get_url_from_iframe(laobandq_res.text)
if not new_jx_api.startswith('http'):
    new_jx_api = '/'.join(laobandq_url.split('/')[:4]) + '/' + new_jx_api
print(new_jx_api)
new_jx_res = requests.get(new_jx_api, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': laobandq_url
})

jiex_api_url = get_url_from_iframe(new_jx_res.text)
if not jiex_api_url.startswith('http'):
    jiex_api_url = get_damin(new_jx_api) + jiex_api_url
print(jiex_api_url)
jiex_api_res = requests.get(jiex_api_url, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'referer': new_jx_api
})
params_pattern = re.compile(r'\$\.post\("api.php",({.*?}),', re.S).search(jiex_api_res.text)
params_str = params_pattern.group(1) if params_pattern else ''
api_url = '/'.join(jiex_api_url.split('/')[:4]) + '/api.php'

params_url = re.findall(r"'url':'(.*?)'", params_str)[0]
params_referer = re.findall(r"'referer':'(.*?)'", params_str)[0]
params_time = re.findall(r"'time':'(.*?)'", params_str)[0]
other_l = base64.b64encode(params_url.encode(encoding='utf-8')).decode()
data = {
    'url': params_url,
    'referer': params_referer,
    'timer': params_time,
    'other_l': other_l
}
res = requests.post(api_url, headers={
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}, data=data)
print(res.json())
