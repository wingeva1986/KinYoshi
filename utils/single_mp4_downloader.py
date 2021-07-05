__all__ = ['single_mp4_download', 'SingleMP4Download']

import logging.handlers
from contextlib import suppress
from pathlib import Path

import requests
from requests.utils import dict_from_cookiejar

log_path = Path(__file__).parent / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(Path(log_path) / "single_mp4_downloader.log", when="D",
                                                           interval=1, encoding='utf-8', backupCount=3)
handler_rotate.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '[%(asctime)s %(filename)s][line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s')
handler_rotate.setFormatter(formatter)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] [%(process)d-%(threadName)s-%(thread)d:] %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d-%H:%M:%S',
                    handlers=[handler_rotate]
                    )

logger = logging.getLogger('single_mp4_downloader')
logger.setLevel(logging.DEBUG)


def single_mp4_download(url: str, filepath: str, headers: dict = None):
    download_state = False
    with suppress(Exception):
        download_state = SingleMP4Download(headers).download(url, filepath)
    return download_state


class SingleMP4Download(object):
    def __init__(self, headers: dict = None):
        self.headers = headers

    def download(self, url: str, filepath: str, **kwargs):
        logger.debug(f'下载到: {filepath}')
        with suppress(FileNotFoundError):
            Path(filepath).unlink()
            logger.info(f'删除已存在文件: {filepath}')
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/85.0.4183.102 Safari/537.36'
        }
        if self.headers:
            headers = self.headers
        keys = [key.lower() for key in headers.keys()]
        if 'range' not in keys:
            headers['Range'] = f"bytes=0-"
        with requests.session() as session:
            # session.cookies.update(cookies)
            resp = session.request('get', url, headers=headers, stream=True)
            with open(filepath, 'ab') as fwb:
                for chunk in resp.iter_content(chunk_size=10 * 1024 * 1024):
                    if chunk:
                        fwb.write(chunk)
                        fwb.flush()
        logger.debug(f'下载成功: {filepath}')
        return True


def format_headers(header_list):
    '''
    格式化header list,
    1将'-H "authority: gdriveplayer.net"' 和'--header="Accept-Encoding: compress, gzip"'中的
    "--header="和"-H "去除
    2.将headers dict转换为[]
    :param header_list:
    :return:
    '''
    output_list = []
    if header_list:
        if isinstance(header_list, list):
            for header in header_list:
                output_list.append(header.replace("--header=", '').replace("-H ", "").replace("\"", ""))
        elif isinstance(header_list, dict):
            for k, v in header_list.items():
                output_list.append(f'{k}: {v}')
    return output_list


def gen_wget_headers(header_list: list):
    header_list_f = format_headers(header_list)
    wget_headers = []
    for _header in header_list_f:
        wget_headers.append(f'--header="{_header}"')
    return wget_headers


if __name__ == '__main__':
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
    }
    url = 'https://bde4.cc/god/43CFB5BDFF158FCB42C3F6BD39802BD90FD788D1559BA253C626A44970857D261A6AD32981DEED27F10E1DED1D66ECB7?sg='
    cookies = dict_from_cookiejar(requests.get(url, headers=headers).cookies)
    cookie_list = [f'{key}={cookies[key]}' for key in cookies.keys()]
    
    headers['cookie'] = ';'.join(cookie_list)
    print(headers)

    video_url = 'http://tj-download.bde4.cc/ftn_handler/Af54d7774Fe2DeBC238c78c38987A13e37b9063A79C90ff84AF2E853af30e50Ee5AE35F7f3E51BAaE1f8031905c78b2a8ED7533106F8a8B8A49c8CC887B23163/1608285377866.mp4'
    single_mp4_download(video_url, filepath='E:\\YunBo\\假面骑士.8.ts', headers=headers)
