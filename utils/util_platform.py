import platform


def is_use_shell():
    os_type = platform.system()
    shell = True
    if os_type.startswith('Windows'):
        shell = False
    return shell


if __name__ == '__main__':
    is_use_shell()
