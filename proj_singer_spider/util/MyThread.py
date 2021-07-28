import logging
import threading

import time
import traceback

logger = logging.getLogger()


class MyThread(threading.Thread):
    FORVER_LOOP_COUNT = 10000000

    def __init__(self, func, args, counter, name: 'str' = '', threadLock=None, sleep: 'int' = 30, kwargs=None):
        threading.Thread.__init__(self)
        self.func = func
        self.args = args
        self.kwargs = {}
        if kwargs:
            self.kwargs = kwargs
            self.kwargs['mythread_name'] = name
        self.name = name
        self.counter = counter
        self.sleep = int(sleep)
        self.running = True
        self.forever = False
        if self.FORVER_LOOP_COUNT == counter:
            self.forever = True

    def set_stop(self):
        self.running = False

    def is_running(self):
        return self.running

    def run(self):
        logging.info("Starting thread %s", self.name)
        count = 0
        while self.running and self.counter > 0:
            logging.info("run thread %s before doing %d", self.name, count)
            if self.func:
                try:
                    self.func(*self.args, **self.kwargs)
                except BaseException as e:
                    logging.warning('self.name run %s', e)
                    logger.info("traceback %s", traceback.format_exc())

            count += 1
            logging.info("run thread %s after doing count %d", self.name, count)
            time.sleep(self.sleep)
            if self.forever:
                pass
            else:
                self.counter -= 1


def test():
    def test_run(output_dir, fake_mode):
        logger.info("test_run_func start to scan dir %s,fake_mode=%s", output_dir, fake_mode)

    output_dir = 'test_dir'
    fake_mode = False
    counter = 2
    sleep = 1
    thread1 = MyThread(func=test_run, args=(output_dir, fake_mode),
                       counter=counter,
                       sleep=sleep,
                       name='test_mythread')
    thread1.start()
    # thread2.start()
    threads = []
    # 添加线程到线程列表
    threads.append(thread1)
    # threads.append(thread2)

    logging.info("wait for to leave Main Thread")
    # 等待所有线程完成
    for t in threads:
        # t.set_stop()
        t.join()

    logging.info("Exiting Main Thread")


def test_kwargs():
    def test_run_func(output_dir, fake_mode, **kwargs):
        '''

        :param output_dir:
        :param fake_mode:
        :param kwargs:
        mythread_name:the name of the thread
        remove:True remove unused file
        :return:
        '''
        remove = kwargs.get('remove', False)
        mythread_name = kwargs.get('mythread_name', '')
        logger.info("test_run_func mythread_name %s, dir %s,fake_mode=%s,remove=%s", mythread_name, output_dir,
                    fake_mode, remove)

    output_dir = 'test_dir'
    fake_mode = False
    counter = 2
    sleep = 1
    kwargs = {
        'remove': True
    }
    thread1 = MyThread(func=test_run_func, args=(output_dir, fake_mode), kwargs=kwargs,
                       counter=counter,
                       sleep=sleep,
                       name='test_mythread_kwargs1')

    thread2 = MyThread(func=test_run_func, args=(output_dir, fake_mode),
                       counter=counter,
                       sleep=sleep,
                       name='test_mythread_kwargs2')
    thread1.start()
    thread2.start()
    threads = []
    # 添加线程到线程列表
    threads.append(thread1)
    threads.append(thread2)

    logging.info("wait for to leave Main Thread")
    # 等待所有线程完成
    for t in threads:
        # t.set_stop()
        t.join()

    logging.info("Exiting Main Thread")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    test()
    test_kwargs()
