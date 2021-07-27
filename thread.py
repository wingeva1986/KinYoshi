# coding=utf-8
import threading
import time

exitFlag = 0

class myThread (threading.Thread):
    def __init__(self,func, args, name, daemon=False, kwargs=None):
        threading.Thread.__init__(self)
        self.func = func
        self.args = args
        self.name = name
        self.kwargs = {}
        self.daemon = daemon
        if kwargs:
            self.kwargs = kwargs
    def run(self):
        print ("开始线程：" + self.name)
        self.func(*self.args, **self.kwargs)
        print ("退出线程：" + self.name)

def print_time(threadName, delay, counter, **kwargs):
    while counter:
        time.sleep(delay)
        print ("%s: %s" % (threadName, time.ctime(time.time())))
        counter -= 1

def get_time(threadName, delay):
    print("%s: %s" % (threadName, time.ctime(time.time())))
    time.sleep(delay)

# 创建新线程
thread1 = myThread(func=print_time, name="Thread-1", args=('Thread-1', 1, 5), daemon=True)
thread2 = myThread(func=get_time, name="Thread-2", args=('Thread-2', 2))
thread_list = [thread1, thread2]

# 开启新线程
for thread in thread_list:
    thread.start()

# 阻塞线程
# for thread in thread_list:
#     thread.join()
# thread1.start()
# thread2.start()
# thread1.join()
# thread2.join()
print ("退出主线程")

