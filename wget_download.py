# coding=utf-8
import os
import zipfile
import subprocess

def wget_downloader():
    url = 'https://legendei.to/oficial/227819/'
    file_path = 'Space Jam A New Legacy.zip'
    params = f'wget "{url}" -O "{file_path}"'
    print(params)
    subprocess.check_output(params, shell=False, stdin=None,
                            stderr=subprocess.STDOUT)


def un_zip(file_name):
    """unzip zip file"""
    files = []
    zip_file = zipfile.ZipFile(file_name)
    if os.path.isdir(file_name + "_files"):
        pass
    else:
        os.mkdir(file_name + "_files")
    for name in zip_file.namelist():
        files.append(name)
        zip_file.extract(name, file_name + "_files/")
        zip_file.close()
    return files

un_zip('Space Jam A New Legacy.zip')
