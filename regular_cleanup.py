# coding=utf-8
import argparse
import os
import platform
import subprocess
import time
import logging
import os
import time
import datetime

logger = logging.getLogger(__name__)


def clean_expired_files(target_dir, expired_day_num: int = 1):
    '''
    清理指定目录下超过过期时间的文件和空文件夹, 过期天数可控
    '''
    today = datetime.datetime.now()
    offset = datetime.timedelta(days=-expired_day_num)
    expired_date = (today + offset)
    expired_date_unix = time.mktime(expired_date.timetuple())   # 转换为时间戳

    for root, dirs, files in os.walk(target_dir, topdown=False):
        # 清理空文件夹
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                if len(os.listdir(dir_path)) == 0 and os.path.getctime(dir_path) <= expired_date_unix:
                    # os.rmdir(dir_path)
                    logger.info(f'removed temp dir {dir_path}')
            except BaseException as e:
                logger.warning(f'remove temp dir error, {e}')
        # 清理过期文件
        for name in files:
            dont_del_types = ['ts', 'mp4', 'mkv']
            if [need_type for need_type in dont_del_types if str(name).endswith(f'.{need_type}') >= 0]:
                continue

            file_path = os.path.join(root, name)
            file_modify_time = os.path.getmtime(file_path)  # 文件修改时间
            time_array = time.localtime(file_modify_time)   # 时间戳->结构化时间
            format_time = time.strftime("%Y-%m-%d %H:%M:%S", time_array)  # 格式化时间

            if file_modify_time <= expired_date_unix:
                # os.remove(file_path)
                print(f"{name}, 文件修改时间: {format_time}, 已经超过{expired_day_num}天,需要删除")
            else:
                print(f"{name}, 文件修改时间: {format_time}, 未超过{expired_day_num}天,无需处理!")


def clear_dir(target_dir: str):
    while True:
        shell = True
        os_type = platform.system()
        if os_type.startswith('Windows'):
            shell = False
        cmd = 'find %s -type f -mtime +2 -name "*" -print -exec rm -rf {} \;' % target_dir
        try:
            subprocess.check_output(cmd, shell=shell, stdin=None, stderr=subprocess.STDOUT, timeout=60)
        except BaseException as e:
            logger.warning(e)
        for root, dirs, files in os.walk(target_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if len(os.listdir(dir_path)) == 0:
                        os.rmdir(dir_path)
                        logger.info(f'rm temp dir {dir_path}')
                except:
                    pass
        logger.info(f'waiting 600s')
        time.sleep(600)


def main(args):
    target_dir = args.target_dir
    # clear_dir(target_dir)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    # parser = argparse.ArgumentParser(usage="media downloader tools", description=" --help")
    # parser.add_argument("--target_dir", required=True, help="target_dir", dest="target_dir")
    # args = parser.parse_args()
    # main(args)

    

    clean_expired_files('Z:\\www\\video3\\www.hktv03.com\\transcoded')
