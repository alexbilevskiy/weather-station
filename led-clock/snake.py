#!/usr/bin/python3 -B
#coding: UTF-8

from samplebase import SampleBase
from rgbmatrix import graphics
import time, socket, threading, datetime, json, memcache, textwrap, random, os

class Snake(SampleBase):
    def __init__(self, *args, **kwargs):
        super(Snake, self).__init__(*args, **kwargs)
        self.W = 64
        self.H = 32
        self.mc = memcache.Client(["127.0.0.1:11211"])
        self.colorW = graphics.Color(255, 255, 255)
        self.colorR = graphics.Color(255, 0, 0)
        self.colorG = graphics.Color(0, 255, 0)
        self.colorB = graphics.Color(0, 0, 255)
        self.colorY = graphics.Color(255, 255, 0)
        self.colorGray = graphics.Color(90, 90, 90)
        self.X = 1
        self.Y = 11
        self.foodX = None
        self.foodY = None
        self.foodEaten = True
        self.dir = 'stop'
        self.reversed = False
        self.length = 5
        self.body = []
        self.initBody()

    def run(self):
        self.matrix.brightness = 30
        self.server = CommandListener(5734, self.onCommand)
        self.server.daemon = True
        self.server.start()
        self.canvas = self.matrix.CreateFrameCanvas()
        
        while True:
            #text = self.mc.set('led-snake', True, 5)
            self.canvas.Clear()
            self.snake()
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            time.sleep(0.05)

    def snake(self):
        self.drawBody()
        self.putFood()
        self.drawFood()
        if self.X >= self.W or self.X < 0 or self.Y >= self.H or self.Y < 0:
            print 'reverse dir'
            self.updatePos(True)
        else:
            self.updatePos()
        if self.X == self.foodX and self.Y == self.foodY:
            self.body.append(self.body[-1])
            self.foodEaten = True
        self.moveBody()
        
    def putFood(self):
        if not self.foodEaten:
            return
        while True:
            x = random.randint(0, self.W-1)
            y = random.randint(0, self.H-1)
            inBody = False
            for slice in self.body:
                if x == slice[0] and y == slice[1]:
                    inBody = True
            if not inBody:
                break
        self.foodX = x
        self.foodY = y
        self.foodEaten = False
        
    def drawFood(self):
        self.canvas.SetPixel(self.foodX, self.foodY, 255, 0, 0)
            
    def initBody(self):
        self.body = []
        for i in range(1, self.length):
            self.body.append([self.X,self.Y])

    def drawBody(self):
        pos = 0
        l = len(self.body)
        for point in self.body:
            c = graphics.Color(random.randint(0,255), random.randint(0,255), random.randint(0,255))
            #self.canvas.SetPixel(point[0], point[1], c.red, c.green, c.blue)
            if pos == 0:
                self.canvas.SetPixel(point[0], point[1], 0,255,0)
                head = False
            else: 
                col = 255*(l-pos)/l
                self.canvas.SetPixel(point[0], point[1], col,col,col)
            pos += 1

    def moveBody(self):
        self.body.pop()
        self.body.insert(0, [self.X, self.Y])
        
    def updatePos(self, reverse = False):
        if self.dir == 'stop':
            return
        if reverse:
            if self.X < 0:
                self.dir = 'right'
            elif self.X >= self.W:
                self.dir = 'left'
            elif self.Y < 0:
                self.dir = 'down'
            elif self.Y >= self.H:
                self.dir = 'up'
                
        if self.dir == 'left':
            self.X -= 1
        elif self.dir == 'right':
            self.X += 1
        elif self.dir == 'up':
            self.Y -= 1
        elif self.dir == 'down':
            self.Y += 1

    
    
    def onCommand(self, command):
        cmd = command.strip()
        print 'command: ' + cmd
        short = {'a':'left', 'w':'up', 's': 'down', 'd':'right'}
        if cmd in short:
            cmd = short[cmd]
        if cmd in ('left', 'right', 'up', 'down', 'stop'):
            self.dir = cmd
            print 'direction changed'
        elif cmd == 'j':
            self.matrix.brightness -= 2
        elif cmd == 'k':
            self.matrix.brightness += 2
        
class CommandListener(threading.Thread):
    def __init__(self, port, callback):
        threading.Thread.__init__(self)
        self.setName('CommandListener')
        self.callback = callback
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.bind(('', port))
        self.s.setblocking(0)
        self.s.listen(5)

    def run(self):
        while True:
            #print('waiting for connection')
            try:
                conn, addr = self.s.accept()
            except socket.error:
                continue
            print('Connected by', addr)
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                self.callback(data)
        
        print "Exiting " + self.name
        
        
        
if __name__ == "__main__":
    snake = Snake()
    if (not snake.process()):
        snake.print_help()