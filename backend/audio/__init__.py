# OpenCue Audio Module

# CRITICAL: Fix for soundcard + NumPy 2.x compatibility
# numpy.fromstring was removed in NumPy 2.0, soundcard uses it internally
# This MUST happen before soundcard is imported anywhere
import numpy
if not hasattr(numpy, 'fromstring'):
    numpy.fromstring = numpy.frombuffer
