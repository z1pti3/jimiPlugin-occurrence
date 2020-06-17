from core import screen

class occurrenceScreen:
    def __init__(self):
        
        self.menu = screen._screen([
            ["end", self.end],
            ], "[ occurrence ] >> ")
        self.menu.load()

    def end(self,args):
        raise KeyboardInterrupt
