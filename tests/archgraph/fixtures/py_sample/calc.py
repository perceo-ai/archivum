"""Calculator module."""
import math

class Calculator:
    def add(self, a, b):
        return a + b

    def hypot(self, a, b):
        return math.sqrt(self.add(a * a, b * b))
