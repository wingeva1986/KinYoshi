import re
import m3u8
import time
import base64
import requests
import subprocess
import pandas as pd
from Crypto.Cipher import AES
from urllib.parse import urlparse

REDUCE_ZORE_NUM = {'01': '1', '02': '2', '03': '3', '04': '4',
                   '05': '5', '06': '6', '07': '7', '08': '8', '09': '9'}
CN_NUM = {
    '〇': '0', '一': '1', '二': '2', '三': '3', '四': '4', '五': '5', '六': '6',
    '七': '7', '八': '8', '九': '9', '零': '0', '十': '10',
    '十一': '11', '十二': '12', '十三': '13', '十四': '14', '十五': '15', '十六': '16', '十七': '17',
    '十九': '19', '二十': '20', '十八': '18',
    '壹': '1', '贰': '2', '叁': '3', '肆': '4', '伍': '5', '陆': '6', '柒': '7', '捌': '8', '玖': '9',
    '貮': '2', '两': '2',
    'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4', 'Ⅴ': '5', 'Ⅵ': '6', 'Ⅶ': '7', 'Ⅷ': '8', 'Ⅸ': '9',
    'Ⅹ': '10', 'Ⅺ': '11', 'Ⅻ': '12'
}


def remove_special_symbols(name):
    special_symbols = ['\\', '/', ':', '?', '"', '<', '>', '|', '$',
                       '[', ']', '%', '&', '#', '~', '*', '(', ')', "'", " ", "!"]
    for symbols in special_symbols:
        name = name.replace(symbols, '')
    return name


def trans_to_srt(file_path, output_path):
    '''
    将文本字幕转换成srt
    '''
    ret = True
    import platform
    SHELL = False if platform.system().startswith('Windows') else True
    cmd = f'ffmpeg -i "{file_path}" -f srt -y {output_path}'
    try:
        subprocess.check_output(
            cmd, shell=SHELL, stdin=None, stderr=subprocess.STDOUT, timeout=3600)
    except BaseException as e:
        ret = False
        print(f'trans error, {e}')
    return ret


def header_list_to_dic(header_list: list):
    '''
    将存放headers的列表转换成字典
    header_list: ['user-agent: Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36, cookie: xxx']
    header_dic: {'user-agent': Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36, 'cookie': 'xxx'}
    :param header_list:
    :return:
    '''
    header_dic: [str] = {}
    try:
        for h in header_list:
            head: str = h
            idx = head.index(':')
            n = head[:idx].strip()
            v = head[idx + 1:].strip()
            header_dic[n] = v
    except Exception as e:
        print('header_list_to_dic error %s', e)
    return header_dic


def get_header_list(headers: dict) -> list:
    '''
    将字典headers转换成列表
    :param headers:
    :return:
    '''
    header_list = []
    for key in headers.keys():
        header_str = f'{key}:{headers[key]}'
        header_list.append(header_str)
    return header_list

def number_to_str(num: str):
    num_dict = {'1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六', '7': '七', '8': '八', '9': '九', '0': '零', }
    index_dict = {1: '', 2: '十', 3: '百', 4: '千', 5: '万', 6: '十', 7: '百', 8: '千', 9: '亿'}
    while True:
        nums = list(num)
        nums_index = [x for x in range(1, len(nums) + 1)][-1::-1]

        str = ''
        for index, item in enumerate(nums):
            str = "".join((str, num_dict[item], index_dict[nums_index[index]]))
        if num == '1':
            return num_dict[num]
        else:
            if nums[0] == '1' and len(nums) < 3:
                str = re.sub("一", "", str, 1)
        str = re.sub("零[十百千零]*", "零", str)
        str = re.sub("零万", "万", str)
        str = re.sub("亿万", "亿零", str)
        str = re.sub("零零", "零", str)
        str = re.sub("零\\b", "", str)
        return str

def trans_to_alb(chn):
    '''
    将中文数字转换成阿拉伯数字
    :param chn:
    :return:
    '''
    def _trans(s):
        num = 0
        digit = {'一': 1, '二': 2, '三': 3, '四': 4,
                 '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
        if s:
            idx_q, idx_b, idx_s = s.find('千'), s.find('百'), s.find('十')
        if idx_q != -1:
            num += digit[s[idx_q - 1:idx_q]] * 1000
        if idx_b != -1:
            num += digit[s[idx_b - 1:idx_b]] * 100
        if idx_s != -1:
            # 十前忽略一的处理
            num += digit.get(s[idx_s - 1:idx_s], 1) * 10
        if s[-1] in digit:
            num += digit[s[-1]]
        return num

    chn = chn.replace('零', '')
    idx_y, idx_w = chn.rfind('亿'), chn.rfind('万')
    if idx_w < idx_y:
        idx_w = -1
    num_y, num_w = 100000000, 10000
    if idx_y != -1 and idx_w != -1:
        return trans_to_alb(chn[:idx_y]) * num_y + _trans(chn[idx_y + 1:idx_w]) * num_w + _trans(chn[idx_w + 1:])
    elif idx_y != -1:
        return trans_to_alb(chn[:idx_y]) * num_y + _trans(chn[idx_y + 1:])
    elif idx_w != -1:
        return _trans(chn[:idx_w]) * num_w + _trans(chn[idx_w + 1:])
    return _trans(chn)


def get_proxy():
    # 隧道代理
    url = 'http://tps.kdlapi.com/api/gettps/?orderid=909125905835865&num=1&format=json&sep=1'
    # url = 'http://dps.kdlapi.com/api/getdps/?orderid=999462867019163&num=1&pt=1&sep=1'
    # 隧道域名:端口号
    tunnel = requests.get(url).json()['data']['proxy_list'][0]
    # 用户名密码方式
    username = 't19125905835963'
    password = 'ggrxcogm'
    proxies = {
        "http": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel},
        # "http": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": proxy_ip},
        "https": "http://%(user)s:%(pwd)s@%(proxy)s/" % {"user": username, "pwd": password, "proxy": tunnel}
    }
    return proxies


def read_all_sheet(file_name):
    '''
    读取excel内容并转化为df
    '''
    try:
        df = pd.ExcelFile(file_name)

        df_new = pd.DataFrame()
        for name in df.sheet_names:
            # 循环读取每个Sheet表内容，同时设置列为字符串，避免长数字文本被识别为数字
            df_pre = df.parse(sheet_name=name, dtype={'columns_name': str})
            df_new = df_new.append(df_pre)
        return df_new
    except Exception as e:
        print(f'read sheet error {e}')


def pkcs7padding(text):
    """
    明文使用PKCS7填充
    最终调用AES加密方法时，传入的是一个byte数组，要求是16的整数倍，因此需要对明文进行处理
    :param text: 待加密内容(明文)
    :return:
    """
    bs = AES.block_size  # 16
    length = len(text)
    bytes_length = len(bytes(text, encoding='utf-8'))
    # tips：utf-8编码时，英文占1个byte，而中文占3个byte
    padding_size = length if (bytes_length == length) else bytes_length
    padding = bs - padding_size % bs
    # tips：chr(padding)看与其它语言的约定，有的会使用'\0'
    padding_text = chr(padding) * padding
    return text + padding_text


def pkcs7unpadding(text):
    """
    处理使用PKCS7填充过的数据
    :param text: 解密后的字符串
    :return:
    """
    length = len(text)
    unpadding = ord(text[length - 1])
    return text[0:length - unpadding]


def aec_encrypt(message, key: bytes, iv: bytes):
    '''
    AES, CBC模式加密
    '''
    try:
        crypt = AES.new(key, AES.MODE_CBC, iv)
    except Exception as e:
        print(f'aes初始化失败, error={e}')
        return ''

    # 处理明文
    content_padding = pkcs7padding(message)
    data_str = content_padding.encode("utf-8")
    result = base64.b64encode(crypt.encrypt(data_str)).decode()
    return result


def aec_decrypt(message, key: bytes, iv: bytes):
    try:
        crypt = AES.new(key, AES.MODE_CBC, iv)
    except Exception as e:
        print(f'aes初始化失败, error={e}')
        return ''
    # 处理明文
    data_str = message.encode("utf-8")
    decode_res = crypt.decrypt(base64.b64decode(data_str)).decode()
    result = pkcs7unpadding(decode_res)
    return result


def get_ts_list(url, **kwargs):
    callback_count = kwargs.get("callback_count")
    old_path = kwargs.get('old_path', '')

    def get_http_url(path, __m3u8, domain, **kwargs):
        old_path = kwargs.get('old_path', '')
        if __m3u8:
            if 'http' not in __m3u8:
                # 判断解析出的m3u8部分链接是否有 '/'
                __m3u8 = '/' + __m3u8 if not __m3u8.startswith('/') else __m3u8
                # 拼接处域名外完整的m3u8部分链接
                if old_path:
                    if old_path not in __m3u8 and ('m3u8' in __m3u8 or 'ts' in __m3u8):
                        __m3u8 = path + __m3u8
                else:
                    if path not in __m3u8 and ('m3u8' in __m3u8 or 'ts' in __m3u8):
                        __m3u8 = path + __m3u8
                # 判断拼接后的部分m3u8链接是否以‘/’开始，并拼接完整的m3u8链接
                __m3u8 = '/' + __m3u8 if not __m3u8.startswith('/') else __m3u8
                _m3u8 = domain + __m3u8
            else:
                _m3u8 = __m3u8
        else:
            __m3u8 = ''
        return _m3u8

    def get_keys_list(playlist, domain):
        # 如果m3u8加密，获取所有的keys，如果没有加密，则keys为空列表
        __keys = [key for key in playlist.keys]
        keys = []
        for key in __keys:
            if key:
                if not key.uri:
                    # key_url = ''
                    continue
                else:
                    key_url = get_http_url(
                        url, key.uri, domain, old_path=old_path)
                keys.append(key_url)
        return keys
    parse_result = urlparse(url)
    scheme = parse_result.scheme
    netloc = parse_result.netloc
    path = parse_result.path.split('index.m3u8')[0].strip('/')
    domain = scheme+"://"+netloc
    for i in range(3):
        try:
            playlist = m3u8.load(url, timeout=10)
            if i > 0:
                print(f'重复请求{i+1}次')
            if playlist:
                break
        except Exception as e:
            ts_list = []
            print(f'请求m3u8：{url}，失败!{e}')
            time.sleep(1)
            if i == 2:
                return ts_list, []
    dump_text = playlist.dumps()
    target_duration = playlist.target_duration
    # 判断是否有ts切片
    if target_duration:
        segments_uris = playlist.segments.uri
        keys = get_keys_list(playlist, domain)
        if len(keys) < 2:
            key = keys and keys[0] or None
            keys = [key for _ in range(len(segments_uris))]
            print('******', len(segments_uris))
        ts_list = []
        for segment in segments_uris:
            __ts = get_http_url(path, segment, domain, old_path=old_path)
            ts_list.append(__ts)
        return ts_list, keys

    else:
        __m3u8 = [i for i in dump_text.split('\n') if i][-1]
        print(f'__m3u8:{__m3u8}')
        old_path = ''
        if 'm3u8' not in __m3u8:
            old_path = path
        _m3u8 = get_http_url(path, __m3u8, domain, old_path='')
        print(f'跳转m3u8：{_m3u8}.......')
        if callback_count > 2:
            print(f"回调{callback_count}次，退出调用")
            return [], []
        print(f"回调次数：{callback_count}")
        callback_count += 1
        ts_list, keys = get_ts_list(
            _m3u8, old_path=old_path, callback_count=callback_count)
        return ts_list, keys
