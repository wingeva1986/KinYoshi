# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/9/27 10:55
# @Version     : Python 3.6.4
__all__ = ['several_mp4s_download', 'SeveralMp4sDownload']

import logging.handlers
import os
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import requests

log_path = Path(__file__).parent / 'log'
log_path.mkdir(parents=True, exist_ok=True)
handler_rotate = logging.handlers.TimedRotatingFileHandler(Path(log_path) / "several_mp4s_downloader.log", when="D",
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

logger = logging.getLogger('several_mp4s_downloader')
logger.setLevel(logging.DEBUG)


def several_mp4s_download(urls: list, filepath: str, headers: dict = None, *,
                          wipe_cache: bool = True, thread_num: int = 10):
    with SeveralMp4sDownload(thread_num, headers) as imd:
        if urls:
            return imd.download(urls, filepath, wipe_cache=wipe_cache)
        else:
            return bool(urls), urls


class SeveralMp4sDownload(object):
    def __init__(self, thread_num: int = 10, headers: dict = None):
        if thread_num < 1:
            thread_num = 1
        self.executor = ThreadPoolExecutor(max_workers=thread_num)
        self.headers = headers

    def control(self, urls: list, filepath: str, *, wipe_cache: bool = True):
        dirname = Path(filepath).parent
        filename = Path(filepath).name
        new_dirname = dirname / Path(f"{filename}?????????")
        new_filepath = new_dirname / filename
        Path(new_filepath).parent.mkdir(parents=True, exist_ok=True)
        logger.info(f'???????????????: {new_dirname}')
        failures = self._threads_download(list(zip(range(1, len(urls) + 1), urls)), new_filepath)
        for i in range(5):
            if failures:
                failures = self._threads_download(failures, new_filepath)
        if not failures:
            self._merge_files(new_dirname, filepath, wipe_cache)
        return not bool(failures), failures

    download = control

    @staticmethod
    def _merge_files(dirname, source_filepath, wipe_cache):
        if source_filepath.endswith('.tmp'):
            filepath = source_filepath[:-4]
        else:
            filepath = source_filepath
        merge_file = filepath + '.txt.tmp'
        content = []
        for file in sorted(Path(dirname).iterdir()):
            content.append(f"file '{file}'")
        with open(merge_file, 'w', encoding='utf-8') as fw:
            fw.write('\n'.join(content))
        # 'ffmpeg -f concat -i video.txt -c copy concat.mp4'
        command = f'ffmpeg -f concat -safe 0 -i "{merge_file}" -c copy "{filepath}" -y'
        logger.info(f'ffmpeg ?????? mp4 ??????: {dirname} -> {filepath}\n{command}')
        os.system(command)
        if wipe_cache:
            Path(merge_file).unlink()
            for filename in sorted(Path(dirname).iterdir()):
                filename.unlink()
                logger.debug(f'????????????: {filename}')
            Path(dirname).rmdir()
            logger.info(f'???????????????: {dirname}')
        Path(filepath).rename(source_filepath)

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
            logger.info(f'?????????: {success_path}')
            return
        failure_path = str(dirname / f'{index:05}0.{filename}')
        try:
            self.__download(url, failure_path)
        except requests.exceptions.RequestException as e:
            logger.warning(f'????????????: {url}, {index}, {str(e)}')
            return index, url
        except Exception as e:
            logger.exception(f'????????????: {url}, {index}, {e}')
            raise e
        else:
            logger.debug(f'????????????: {url}')
            Path(failure_path).rename(success_path)

    @staticmethod
    def _get_size(filepath: str):
        try:
            size = os.path.getsize(filepath)
        except FileNotFoundError:
            size = 0
        return size

    def __download(self, url: str, filepath: str, chunk_size: int = 10 * 1024 * 1024):
        with suppress(FileNotFoundError):
            Path(filepath).unlink()
            logger.info(f'?????????????????????: {filepath}')
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
            resp = session.request('get', url, stream=True, headers=headers)
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            if resp.status_code == 206 and 'content-range' in resp_headers:
                max_length = int(resp.headers['content-range'].rsplit('/', 1)[-1])
                logger.debug(f'???????????????: {filepath}, max_length: {max_length}')
                print(f'???????????????: {filepath}, max_length: {max_length}')
                with open(filepath, 'ab') as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            f.flush()
            else:
                logger.debug(f'?????????: {filepath}')
                with open(filepath, 'wb') as f:
                    f.write(resp.content)

    def close(self):
        self.executor.shutdown()
        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
