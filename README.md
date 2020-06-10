### 功能：

基于TCP协议分别使用多线程、IO 多路复用的方法实现多人聊天室

- [x] 有人进入、退出聊天室时，其他人会收到通知
- [x] 有人退出、加入聊天室会给其他人发送在线客户端的列表
- [x] 可群发/私聊消息
- [x] 超过时间不发送消息则会被踢出

### 关键点

​    [1] 使用字典保存用户信息　

​	{客户端套接字：客户端信息}

```python
class ClientInfo:
    def __init__(self, addr: str, handle_time: float):
        """客户端保持在服务的信息

        参数:
            addr:客户端地址
            handle_time:用于清理的标识时间 单位秒
        """
        self.addr = addr
        self.handle_time = handle_time
```

​	[2] 私聊/群聊

​	根据消息格式判断是否是私聊

```python
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
```

​    [3] 定时处理长时间不发消息的客户端

设置timeout=1将阻塞变为每隔一秒做一次查询,也就是每隔一秒清理一次

```python
events = self.selector.select(timeout=1)
while True:
    # timeout 为None时是有事件才处理也就是阻塞的
    self.clean_client()
    # 设置为1后每一秒会主动查询socket是否有变化
    events = self.selector.select(timeout=1)  # 调用select：优先使用epoll
```