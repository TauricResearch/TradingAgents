# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Any helper APIs."""

from typing import Optional, TypeVar

from google.protobuf import descriptor
from google.protobuf.message import Message

from google.protobuf.any_pb2 import Any


_MessageT = TypeVar('_MessageT', bound=Message)


def pack(
    msg: Message,
    type_url_prefix: Optional[str] = 'type.googleapis.com/',
    deterministic: Optional[bool] = None,
) -> Any:
  any_msg = Any()
  any_msg.Pack(
      msg=msg, type_url_prefix=type_url_prefix, deterministic=deterministic
  )
  return any_msg


def unpack(any_msg: Any, msg: Message) -> bool:
  return any_msg.Unpack(msg=msg)


def unpack_as(any_msg: Any, message_type: type[_MessageT]) -> _MessageT:
  unpacked = message_type()
  if unpack(any_msg, unpacked):
    return unpacked
  else:
    raise TypeError(
        f'Attempted to unpack {type_name(any_msg)} to'
        f' {message_type.__qualname__}'
    )


def type_name(any_msg: Any) -> str:
  return any_msg.TypeName()


def is_type(any_msg: Any, des: descriptor.Descriptor) -> bool:
  return any_msg.Is(des)
