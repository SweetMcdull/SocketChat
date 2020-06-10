#!/usr/bin/env python
# -*- coding: utf-8 -*-
from chat.multiplexing.server import SKTServer

if __name__ == '__main__':
    server = SKTServer(encoding='gbk', handle_time=20)
    server.run()
