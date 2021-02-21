#!/usr/bin/python3 -B
#coding: UTF-8
from samplebase import SampleBase
from rgbmatrix import graphics
import time, datetime, serial


class RunText(SampleBase):
    def __init__(self, *args, **kwargs):
        super(RunText, self).__init__(*args, **kwargs)


    def run(self):
        self.canvas = self.matrix.CreateFrameCanvas()
        
        
        br = 0
        while True:
            self.matrix.brightness = br
            self.canvas.Clear()
            for i in range(0,31):
                graphics.DrawLine(self.canvas, 0, i, 63, i, graphics.Color(255, 255, 255))
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            time.sleep(0.5)
            br = br + 10
            if (br > 255):
                br = 0
            print br
            
           
            
if __name__ == "__main__":
    run_text = RunText()
    if (not run_text.process()):
        run_text.print_help()

        