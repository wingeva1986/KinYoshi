# -*- coding: utf-8 -*-
# @Author      : LJQ
# @Time        : 2020/11/25 12:20
# @Version     : Python 3.6.4
"""
使用 faad 解码并修复aac文件

faad安装
    下载：
        wget https://sourceforge.net/projects/faac/files/faad2-src/faad2-2.8.0/faad2-2.8.8.tar.gz/download -O faad2-2.8.8.tar.gz
    编译：
        tar zxvf faad2-2.8.8.tar.gz
        cd faad2-2.8.8
        autoreconf -vif
        ./configure --prefix=/usr --with-mp4v2 --enable-shared
        make && make install
    添加/usr/local/lib到文件/etc/ld.so.conf
        运行  vi /etc/ld.so.conf
        末尾添加  /usr/local/lib
        运行  ldconfig

faad使用
    参数：
        input.aac：
            输入文件
        output.aac：
            输出文件
    命令：
        faad -a output.aac input.aac
"""
import os


class AAC(object):
    """
    AAC 工具类
    """

    @staticmethod
    def renovate(input_file, output_file):
        command = f'faad -a "{output_file}" "{input_file}"'
        print(command)
        code = os.system(command)
        return not code


if __name__ == '__main__':
    r = AAC.renovate(r'C:\Users\admin\Desktop\faac-1.30\盲侠大律师.aac', r'C:\Users\admin\Desktop\faac-1.30\盲侠大律师粤语.aac')
    print(r)
