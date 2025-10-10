# Protocol Buffers - Google's data interchange format
# Copyright 2025 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Nextgen Pythonic Protobuf Text Format APIs."""
from typing import AnyStr, Callable, Optional, Text, Type, Union

from google.protobuf import text_format
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message import Message

_MsgFormatter = Callable[[Message, Union[int, bool], bool], Optional[Text]]


def serialize(
    message: Message,
    as_utf8: bool = True,
    as_one_line: bool = False,
    use_short_repeated_primitives: bool = False,
    pointy_brackets: bool = False,
    use_index_order: bool = False,
    float_format: Optional[str] = None,
    double_format: Optional[str] = None,
    use_field_number: bool = False,
    descriptor_pool: Optional[DescriptorPool] = None,
    indent: int = 0,
    message_formatter: Optional[_MsgFormatter] = None,
    print_unknown_fields: bool = False,
    force_colon: bool = False,
) -> str:
  """Convert protobuf message to text format.

  Double values can be formatted compactly with 15 digits of
  precision (which is the most that IEEE 754 "double" can guarantee)
  using double_format='.15g'. To ensure that converting to text and back to a
  proto will result in an identical value, double_format='.17g' should be used.

  Args:
    message: The protocol buffers message.
    as_utf8: Return unescaped Unicode for non-ASCII characters.
    as_one_line: Don't introduce newlines between fields.
    use_short_repeated_primitives: Use short repeated format for primitives.
    pointy_brackets: If True, use angle brackets instead of curly braces for
      nesting.
    use_index_order: If True, fields of a proto message will be printed using
      the order defined in source code instead of the field number, extensions
      will be printed at the end of the message and their relative order is
      determined by the extension number. By default, use the field number
      order.
    float_format (str): If set, use this to specify float field formatting (per
      the "Format Specification Mini-Language"); otherwise, shortest float that
      has same value in wire will be printed. Also affect double field if
      double_format is not set but float_format is set.
    double_format (str): If set, use this to specify double field formatting
      (per the "Format Specification Mini-Language"); if it is not set but
      float_format is set, use float_format. Otherwise, use ``str()``
    use_field_number: If True, print field numbers instead of names.
    descriptor_pool (DescriptorPool): Descriptor pool used to resolve Any types.
    indent (int): The initial indent level, in terms of spaces, for pretty
      print.
    message_formatter (function(message, indent, as_one_line) -> unicode|None):
      Custom formatter for selected sub-messages (usually based on message
      type). Use to pretty print parts of the protobuf for easier diffing.
    print_unknown_fields: If True, unknown fields will be printed.
    force_colon: If set, a colon will be added after the field name even if the
      field is a proto message.

  Returns:
    str: A string of the text formatted protocol buffer message.
  """
  return text_format.MessageToString(
      message=message,
      as_utf8=as_utf8,
      as_one_line=as_one_line,
      use_short_repeated_primitives=use_short_repeated_primitives,
      pointy_brackets=pointy_brackets,
      use_index_order=use_index_order,
      float_format=float_format,
      double_format=double_format,
      use_field_number=use_field_number,
      descriptor_pool=descriptor_pool,
      indent=indent,
      message_formatter=message_formatter,
      print_unknown_fields=print_unknown_fields,
      force_colon=force_colon,
  )


def parse(
    message_class: Type[Message],
    text: AnyStr,
    allow_unknown_extension: bool = False,
    allow_field_number: bool = False,
    descriptor_pool: Optional[DescriptorPool] = None,
    allow_unknown_field: bool = False,
) -> Message:
  """Parses a text representation of a protocol message into a message.

  Args:
    message_class: The message meta class.
    text (str): Message text representation.
    message (Message): A protocol buffer message to merge into.
    allow_unknown_extension: if True, skip over missing extensions and keep
      parsing
    allow_field_number: if True, both field number and field name are allowed.
    descriptor_pool (DescriptorPool): Descriptor pool used to resolve Any types.
    allow_unknown_field: if True, skip over unknown field and keep parsing.
      Avoid to use this option if possible. It may hide some errors (e.g.
      spelling error on field name)

  Returns:
    Message: A new message passed from text.

  Raises:
    ParseError: On text parsing problems.
  """
  new_message = message_class()
  text_format.Parse(
      text=text,
      message=new_message,
      allow_unknown_extension=allow_unknown_extension,
      allow_field_number=allow_field_number,
      descriptor_pool=descriptor_pool,
      allow_unknown_field=allow_unknown_field,
  )
  return new_message
