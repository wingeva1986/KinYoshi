# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/11/26 15:31
# @Version     : Python 3.6.4
__all__ = ['several_urls_download', 'SeveralURLsDownload']

import logging.handlers
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path

import requests

log_path = Path(__file__).parent / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(Path(log_path) / "several_urls_downloader.log", when="D",
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

logger = logging.getLogger('several_urls_downloader')
logger.setLevel(logging.DEBUG)


def several_urls_download(urls: list, filepath: str, headers: dict = None, *,
                          wipe_cache: bool = True, thread_num: int = 10):
    with SeveralURLsDownload(thread_num, headers) as sud:
        return sud.download(urls, filepath, wipe_cache=wipe_cache)


class SeveralURLsDownload(object):
    def __init__(self, thread_num: int = 10, headers: dict = None):
        if thread_num < 1:
            thread_num = 1
        self.executor = ThreadPoolExecutor(max_workers=thread_num)
        self.headers = headers

    def control(self, urls: list, filepath: str, *, wipe_cache: bool = True):
        dirname = Path(filepath).parent
        filename = Path(filepath).name
        new_dirname = dirname / Path(f"{filename}文件夹")
        new_filepath = new_dirname / filename
        Path(new_filepath).parent.mkdir(parents=True, exist_ok=True)
        logger.info(f'创建文件夹: {new_dirname}')
        failures = self._threads_download(list(zip(range(1, len(urls) + 1), urls)), new_filepath)
        for i in range(5):
            if failures:
                failures = self._threads_download(failures, new_filepath)
        if not failures:
            self._merge_files(new_dirname, filepath, wipe_cache)
        return not bool(failures), failures

    download = control

    @staticmethod
    def _merge_files(dirname, filepath, wipe_cache):
        logger.info(f'合并文件: {dirname} -> {filepath}')
        with open(filepath, 'ab') as fwb:
            for filename in sorted(Path(dirname).iterdir()):
                with open(filename, 'rb') as fr:
                    fwb.write(fr.read())
                    fwb.flush()
                if wipe_cache:
                    filename.unlink()
                    logger.debug(f'删除文件: {filename}')
        if wipe_cache:
            Path(dirname).rmdir()
            logger.info(f'删除文件夹: {dirname}')

    def _threads_download(self, urls, filepath):
        failures = []
        results = self.executor.map(self._download, urls, [filepath] * len(urls))
        for result in results:
            if result:
                failures.append(result)
        return failures

    def _download(self, url, filepath: str):
        all_files = [str(filename) for filename in Path(filepath).parent.iterdir()]
        index, url = url
        dirname = Path(filepath).parent
        filename = Path(filepath).name
        success_path = str(dirname / f'{index:05}1.{filename}')
        if success_path in all_files:
            logger.info(f'已存在: {success_path}')
            return
        failure_path = str(dirname / f'{index:05}0.{filename}')
        try:
            self.__download(url, failure_path)
        except requests.exceptions.RequestException as e:
            logger.warning(f'下载失败: {url}, {index}, {str(e)}')
            return index, url
        except Exception as e:
            logger.exception(f'下载异常: {url}, {index}, {e}')
            raise e
        else:
            logger.debug(f'下载成功: {url}')
            Path(failure_path).rename(success_path)

    def __download(self, url: str, filepath: str):
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/85.0.4183.102 Safari/537.36'
        }
        if self.headers:
            headers = self.headers
        with requests.session() as session:
            resp_bytes = session.request('get', url, headers=headers, timeout=30).content
            with open(filepath, 'wb') as fwb:
                fwb.write(resp_bytes)

    def close(self):
        self.executor.shutdown()
        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
