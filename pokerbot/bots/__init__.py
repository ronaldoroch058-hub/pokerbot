from .cfr7 import CFR7
from .monte import Monte
from .nash import Nash

BOTS = {"CFR-7": CFR7, "MONTE": Monte, "NASH": Nash}


def make(name):
    return BOTS[name]()
