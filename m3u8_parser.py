# coding=utf-8
import zlib
import m3u8
import logging
import requests
import traceback
from urllib.parse import urljoin
from utils.util_agent import choice_agent
logger = logging.getLogger(__name__)
requests.packages.urllib3.disable_warnings()

def get_proxy():
    # 隧道代理
    url = 'http://tps.kdlapi.com/api/gettps/?orderid=909125905835865&num=1&format=json&sep=1'
    # 隧道域名:端口号
    tunnel = requests.get(url).json()['data']['proxy_list'][0]
    # 用户名密码方式
    username = 't19125905835963'
    password = 'ggrxcogm'
    proxies = {
        "http": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel},
        "https": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel}
    }
    return proxies


class M3u8Parser(object):
    def __init__(self, url: str, headers: dict = None, timeout: int=60, **kwargs):
        self.url = url
        self.headers = {'User-Agent': choice_agent()} if not headers else headers
        self.timeout = timeout
        self.m3u8_obj = self.__get_m3u8_obj()
        self.start_url = kwargs.get('start_url', '')
    
    def __get_m3u8_obj(self):
        try:
            if self.url.find('#EXTM3U') >= 0:
                return m3u8.loads(self.url)
            elif self.url.startswith('http') >= 0:
                try:
                    m3u8_obj = m3u8.load(self.url, headers=self.headers, timeout=self.timeout)
                except BaseException as e:
                    response = requests.get(
                        self.url, headers=self.headers, timeout=self.timeout, 
                        allow_redirects=False, verify=False
                    )
                    if response.status_code == 200:
                        content = response.text
                    elif response.status_code == 302:
                        self.url = response.headers['Location']
                        return self.__get_m3u8_obj()
                    try:
                        if content and not content.startswith('#EXTM3U'):
                            content = zlib.decompress(response.content[3354:], 16 + zlib.MAX_WBITS).decode('utf-8')
                        return m3u8.loads(content)
                    except BaseException:
                        logger.warning(traceback.format_exc())
                if m3u8_obj.target_duration:
                    return m3u8_obj
                else:
                    m3u8_url = [i for i in m3u8_obj.dumps().split('\n') if i.find('m3u8') >= 0][-1]
                    if m3u8_url:
                        self.url = urljoin(self.url, m3u8_url)
                        return self.__get_m3u8_obj()
                    else:
                        return m3u8_obj
        except BaseException as e:
            logger.warning(f'get m3u8 obj error, {e}')      
    
    def get_ts_list(self):
        try:
            base_url = self.start_url if self.start_url else self.url
            return [urljoin(base_url, i) for i in self.m3u8_obj.segments.uri]
        except BaseException as e:
            logger.warning(f'ge ts list error, {e}')

    def get_keys(self):
        try:
            base_url = self.start_url if self.start_url else self.url
            keys = [key.uri for key in self.m3u8_obj.keys if key]
            if keys and keys[0]:
                keys = [urljoin(base_url, key) for key in keys if key]
            return keys
        except BaseException as e:
            logger.warning(f'get keys error, {e}')    

    def get_iv(self):
        try:
            base_url = self.start_url if self.start_url else self.url
            iv_list = [key.iv for key in self.m3u8_obj.keys if key]
            if iv_list and iv_list[0]:
                iv_list = [urljoin(base_url, iv) for iv in iv_list if iv]
            return iv_list
        except BaseException as e:
            logger.warning(f'get keys error, {e}')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    url = 'https://www.mp4er.com/10E79044B82A84F70BE1308FFA5232E4460DE9564FAA63773ACFEA5D33AEFC10C7871D05FA888BEB37226D8FC7193DB0.m3u8'
    m3u8_parser = M3u8Parser(url)
    m3u8_obj = m3u8_parser.m3u8_obj
    logger.info(m3u8_parser.get_ts_list()[:1])
    logger.info(m3u8_parser.get_keys())
    logger.info(m3u8_parser.get_iv())
