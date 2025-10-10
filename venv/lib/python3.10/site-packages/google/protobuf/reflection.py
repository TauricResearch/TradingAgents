# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

# This code is meant to work on Python 2.4 and above only.

"""Contains a metaclass and helper functions used to create
protocol message classes from Descriptor objects at runtime.

Recall that a metaclass is the "type" of a class.
(A class is to a metaclass what an instance is to a class.)

In this case, we use the GeneratedProtocolMessageType metaclass
to inject all the useful functionality into the classes
output by the protocol compiler at compile-time.

The upshot of all this is that the real implementation
details for ALL pure-Python protocol buffers are *here in
this file*.
"""

__author__ = 'robinson@google.com (Will Robinson)'

import warnings

from google.protobuf import message_factory
from google.protobuf import symbol_database

# The type of all Message classes.
# Part of the public interface, but normally only used by message factories.
GeneratedProtocolMessageType = message_factory._GENERATED_PROTOCOL_MESSAGE_TYPE

MESSAGE_CLASS_CACHE = {}
