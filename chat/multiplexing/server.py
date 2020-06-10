#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""基于selectors实现的IO多路复用版的多人聊天服务器端

服务器功能:
    1.多用户同时聊天,用户上下线会进行全局通知
    2.服务器能查看所有在线的用户
    3.服务器可以给所有用户发消息
"""

import selectors
import socket
import time

from loguru import logger


class ClientInfo:
    def __init__(self, addr: str, handle_time: float):
        """客户端保持在服务的信息

        参数:
            addr:客户端地址
            handle_time:用于清理的标识时间 单位秒
        """
        self.addr = addr
        self.handle_time = handle_time


class SKTServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 8888, buffer_size: int = 1024, handle_time: float = 10.,
                 encoding: str = 'utf-8'):
        """socket服务器初始化函数

        参数:
            host:服务器ip
            port:服务器端口
            buffer_size:接收消息的buffer size
            handle_time:清理客户端的时间
            encoding:编码
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.handle_time = handle_time
        self.encoding = encoding
        self.selector = selectors.DefaultSelector()  # 根据平台选择最佳的IO多路机制，比如linux就会选择epoll,win只支持select
        self.server = socket.socket()
        self.clients = {}

    def __init(self):
        """初始化服务器socket

        1.进行ip 端口绑定
        2.开启监听
        3.设置非阻塞
        """
        logger.info(f'初始化服务器...')
        try:
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 立即释放端口
            self.server.bind((self.host, self.port))  # 绑定ip 端口
            self.server.listen()  # 开启监听
            self.server.setblocking(False)  # 设置非阻塞
        except OSError as e:
            logger.error('服务器启动失败，请检查端口是否被占用')
            raise e
            # sys.exit()
        logger.info(f'服务器启动成功,绑定地址为:{self.host}:{self.port}')

        # 注册server到selectors
        self.register_skt(self.server, selectors.EVENT_READ, self.accept)

    def register_skt(self, skt: socket, events, callback):
        """注册skt

        参数:
            skt: 要注册到selectors的socket对象
            events: 监听事件
            callback: 监听事件的回调函数
        """
        self.selector.register(skt, events, callback)

    def __get_client_list(self):
        clients_info = '当前在线用户\n'
        return clients_info + '\n'.join([f'{info.addr}' for client, info in self.clients.items()]) + '\n'

    def accept(self, skt: socket.socket, mask):
        """接受客户端连接请求并登录"""
        conn, addr = skt.accept()
        conn.setblocking(False)  # 设置非阻塞
        addr = f'{addr[0]}:{addr[1]}'
        print(f'{addr}加入到群聊')

        # 添加客户端到用户列表
        self.clients[conn] = ClientInfo(addr=str(addr), handle_time=time.time())
        # 转播消息到所有客户端
        self.broadcast_msg(sender='管理员', msg=f'{addr}加入到群聊\n')
        self.broadcast_msg(sender='管理员', msg=self.__get_client_list())
        # 注册客户端加入事件
        self.register_skt(conn, selectors.EVENT_READ, self.read)

    def broadcast_msg(self, sender: str, msg: str):
        """转播消息到客户端"""

        if msg.startswith('@'):  # 私聊
            # 对msg进行解析,判断是否为私聊
            # '@127.0.0.1:8888 私聊吧'
            receiver, msg = msg.split('@')[-1].split(' ')
            self.private_msg(sender, receiver, msg)
        else:  # 群发
            for skt, info in self.clients.items():
                # 不给自己发消息
                if sender != info.addr:
                    data = f'{sender}: ' + msg
                    skt.send(data.encode(encoding=self.encoding))

    def private_msg(self, sender: str, receiver: str, msg: str):
        """私聊信息"""
        clients = {info.addr: skt for skt, info in self.clients.items()}
        msg = f'来自{sender}的私聊: {msg}'
        if receiver in clients:  # 地址正确
            skt = clients[receiver]
            skt.send(msg.encode(encoding=self.encoding))
        else:  # 地址不正确
            try:
                self.clients[sender].send(f'私聊失败,{receiver}未找到')
            except KeyError as e:
                logger.error(e)

    def read(self, client: socket.socket, mask):
        """接受处理客户端发送过来的消息"""
        try:
            info = self.clients[client]
            info.handle_time = time.time()
            msg = client.recv(self.buffer_size)
            print(f'{info.addr}: {msg.decode(encoding=self.encoding)}')
            if msg:  # 正常消息
                msg = msg.decode(encoding=self.encoding)
                self.broadcast_msg(sender=info.addr, msg=msg)
            else:  # 客户端调用了close
                logger.info(f'{info.addr}调用了close')
                del self.clients[client]
                self.selector.unregister(client)
                self.broadcast_msg(sender='管理员', msg=f'{info.addr}退出了群聊\n')
                self.broadcast_msg(sender='管理员', msg=self.__get_client_list())
        except Exception as e:
            self.selector.unregister(client)
            del self.clients[client]
            self.broadcast_msg(sender='管理员', msg=f'{self.clients[client]}异常退出')
            logger.error(e)
            raise e

    def run(self):
        """服务器启动入口"""
        # 初始化服务器
        self.__init()
        # 第一次调用server，register accept
        # 第二次调用client，register read
        while True:
            # timeout 为None时是有事件才处理也就是阻塞的
            self.clean_client()
            events = self.selector.select(timeout=1)  # 调用select：优先使用epoll
            # 只要不阻塞就有调用的数据，返回一个列表
            # 默认阻塞，有活动链接就返回活动的链接列表
            for key, mask in events:
                callback = key.data  # callback相当于调accept函数

                # 获取函数内存地址，加入参数
                # key.fileobj = 文件句柄
                callback(key.fileobj, mask)

    def clean_client(self):
        """清理客户端"""
        now_time = time.time()
        for skt in list(self.clients.keys()):
            info = self.clients[skt]
            if now_time - self.handle_time > info.handle_time:
                del self.clients[skt]
                self.selector.unregister(skt)
                skt.send(f'管理员: 你长时间没聊天被管理员踢出来了'.encode(encoding=self.encoding))
                skt.close()
                print(f'{info.addr}: 需要被清理了')


if __name__ == '__main__':
    server = SKTServer(encoding='gbk', handle_time=20)
    server.run()
