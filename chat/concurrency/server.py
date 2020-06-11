#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author    : lemon
# Time      : 2020/6/11 11:37 

"""基于多线程实现的多人聊天服务器端

服务器功能:
    1.多用户同时聊天,用户上下线会进行全局通知
    2.服务器能查看所有在线的用户
    3.服务器可以给所有用户发消息
"""
import socket
import threading
import time
from typing import Dict, Optional

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
        self.closed = False


class SKTServer:
    def __init__(
            self,
            host: str = '0.0.0.0',
            port: int = 8888,
            buffer_size: int = 1024,
            handle_time: float = 10.,
            encoding: str = 'utf-8'
    ) -> None:
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
        self.server = socket.socket()
        self.clients: Dict[socket.socket, ClientInfo] = {}

    def __init(self):
        """初始化服务器"""
        logger.info(f'初始化服务器...')
        try:
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 立即释放端口
            self.server.bind((self.host, self.port))  # 绑定ip 端口
            self.server.listen()  # 开启监听
        except OSError as e:
            logger.error('服务器启动失败，请检查端口是否被占用')
            raise e
        logger.info(f'服务器启动成功,绑定地址为:{self.host}:{self.port}')

    def __register(self, conn: socket.socket, addr: str) -> None:
        """注册连接"""
        self.clients[conn] = ClientInfo(addr, time.time())
        msg = f'{addr} 加入到聊天室\n' + self.get_client_list()
        logger.info(msg)
        self.send_admin(msg)

        # 加入的客户端各自起一个现成监听消息
        thread = threading.Thread(target=self.__listen, args=(conn,))
        thread.start()

    def __unregister(self, conn: socket.socket, broke=False) -> None:
        """注销连接"""

        if conn in self.clients:
            addr = self.clients.pop(conn).addr
            if broke:
                msg = f'{addr} 异常断开\n' + self.get_client_list()
            else:
                msg = f'{addr} 离开了聊天室\n' + self.get_client_list()
            logger.info(msg)
            self.send_admin(msg)

    def __handle_msg(self, conn: socket.socket, msg: str):
        """处理客户端发送来的消息"""
        sender_info = self.clients[conn]
        sender_info.handle_time = time.time()  # 收到客户端消息则更新清理时间
        if msg.startswith('@'):  # 私聊
            # 对msg进行解析,判断是否为私聊
            # '@127.0.0.1:8888 私聊吧'
            addr, msg = msg.split('@')[-1].split(' ')
            self.__broadcast_msg(sender_info.addr, msg, is_private=True, receiver_addr=addr)
        else:  # 群发
            self.__broadcast_msg(sender_info.addr, msg)

    def __broadcast_msg(
            self,
            sender_addr: str,
            msg: str,
            is_private: bool = False,
            receiver_addr: Optional[str] = None,
    ) -> None:
        """转发消息"""
        clients = {info.addr: skt for skt, info in self.clients.items()}
        sender = clients[sender_addr]
        # 私聊消息
        if is_private:
            self.send_private(sender_addr, msg, receiver_addr)
        # 公聊
        else:
            self.send_public(sender_addr, msg)

    def send_private(self, sender_addr: str, msg: str, receiver_addr: str):
        clients = {info.addr: skt for skt, info in self.clients.items()}
        sender = clients[sender_addr]
        if receiver_addr in clients:
            msg = f'来自 {sender_addr}的私聊: {msg}\n'
            skt = clients[receiver_addr]
            skt.send(msg.encode(encoding=self.encoding))
        else:
            msg = f'管理员: 私聊失败, {receiver_addr}未找到\n'
            sender.send(msg.encode(encoding=self.encoding))

    def send_public(self, sender_addr, msg):
        clients = {info.addr: skt for skt, info in self.clients.items()}
        sender = clients[sender_addr]
        msg = f'{sender_addr}: {msg}\n'
        for skt, info in self.clients.items():
            skt.send(msg.encode(encoding=self.encoding))
            # if skt != sender:  # 不将信息发给自己
            #     skt.send(msg.encode(encoding=self.encoding))

    def send_admin(self, msg: str):
        msg = f'管理员: {msg}\n'
        for conn, info in self.clients.items():
            conn.send(msg.encode(encoding=self.encoding))

    def __listen(self, conn: socket.socket) -> None:
        client = self.clients.get(conn)
        logger.info(f'开始监听 {client.addr}')
        while True:
            try:
                msg = conn.recv(self.buffer_size)
                if msg:
                    self.__handle_msg(conn, msg.decode(self.encoding))
                else:  # 客户端调用了close
                    self.__unregister(conn)
                    break
            except ConnectionResetError as e:
                # 客户端异常断开
                self.__unregister(conn, False)
                break
            except OSError as e:
                if isinstance(e, TimeoutError):  # 客户端无响应超时
                    logger.warning(f'{client.addr} 长时间没得到响应')
                    continue
                if client.closed:
                    break
                raise e

    def get_client_list(self):
        clients_info = '当前在线用户\n'
        return clients_info + '\n'.join([f'{info.addr}' for client, info in self.clients.items()]) + '\n'

    def clean_client(self):
        """清理客户端"""
        logger.info('清理线程已启动...')
        while True:
            now_time = time.time()
            for conn in list(self.clients.keys()):
                info = self.clients[conn]
                if now_time - self.handle_time > info.handle_time:
                    info.closed = True
                    self.clients.pop(conn)
                    conn.send(f'管理员: 你长时间没聊天被管理员踢出来了'.encode(encoding=self.encoding))
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                    logger.info(f'{info.addr} 被清理了')
            time.sleep(1)

    def run(self):
        """服务器启动入口"""
        self.__init()
        logger.info('服务器开始监听连接...')
        thread = threading.Thread(target=self.clean_client)
        thread.daemon = True
        thread.start()
        while True:
            conn, addr = self.server.accept()
            addr = f'{addr[0]}:{addr[1]}'
            self.__register(conn, addr)


if __name__ == '__main__':
    server = SKTServer(handle_time=60, encoding='gbk')
    server.run()
