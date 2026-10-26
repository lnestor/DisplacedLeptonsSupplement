import random

import FWCore.ParameterSet.Config as cms
from IOMC.RandomEngine.RandomServiceHelper import RandomNumberServiceHelper


def customise(process):
    RandomNumberServiceHelper(process.RandomNumberGeneratorService).populate()
    if hasattr(process, "mixData"):
        process.mixData.input.seed = cms.int32(random.SystemRandom().randint(1, 2**31 - 1))
    return process
