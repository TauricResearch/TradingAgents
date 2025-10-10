"""Extract reference documentation from the NumPy source tree.

Copyright (C) 2008 Stefan van der Walt <stefan@mentat.za.net>, Pauli Virtanen <pav@iki.fi>

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

 1. Redistributions of source code must retain the above copyright
    notice, this list of conditions and the following disclaimer.
 2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in
    the documentation and/or other materials provided with the
    distribution.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT,
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

"""
import inspect
import textwrap
import re
import pydoc
from warnings import warn
from collections import namedtuple
from collections.abc import Callable, Mapping
import copy
import sys


def strip_blank_lines(l):
    "Remove leading and trailing blank lines from a list of lines"
    while l and not l[0].strip():
        del l[0]
    while l and not l[-1].strip():
        del l[-1]
    return l


class Reader:
    """A line-based string reader.

    """
    def __init__(self, data):
        """
        Parameters
        ----------
        data : str
           String with lines separated by '\n'.

        """
        if isinstance(data, list):
            self._str = data
        else:
            self._str = data.split('\n')  # store string as list of lines

        self.reset()

    def __getitem__(self, n):
        return self._str[n]

    def reset(self):
        self._l = 0  # current line nr

    def read(self):
        if not self.eof():
            out = self[self._l]
            self._l += 1
            return out
        else:
            return ''

    def seek_next_non_empty_line(self):
        for l in self[self._l:]:
            if l.strip():
                break
            else:
                self._l += 1

    def eof(self):
        return self._l >= len(self._str)

    def read_to_condition(self, condition_func):
        start = self._l
        for line in self[start:]:
            if condition_func(line):
                return self[start:self._l]
            self._l += 1
            if self.eof():
                return self[start:self._l+1]
        return []

    def read_to_next_empty_line(self):
        self.seek_next_non_empty_line()

        def is_empty(line):
            return not line.strip()

        return self.read_to_condition(is_empty)

    def read_to_next_unindented_line(self):
        def is_unindented(line):
            return (line.strip() and (len(line.lstrip()) == len(line)))
        return self.read_to_condition(is_unindented)

    def peek(self, n=0):
        if self._l + n < len(self._str):
            return self[self._l + n]
        else:
            return ''

    def is_empty(self):
        return not ''.join(self._str).strip()


class ParseError(Exception):
    def __str__(self):
        message = self.args[0]
        if hasattr(self, 'docstring'):
            message = f"{message} in {self.docstring!r}"
        return message


Parameter = namedtuple('Parameter', ['name', 'type', 'desc'])


class NumpyDocString(Mapping):
    """Parses a numpydoc string to an abstract representation

    Instances define a mapping from section title to structured data.

    """

    sections = {
        'Signature': '',
        'Summary': [''],
        'Extended Summary': [],
        'Parameters': [],
        'Returns': [],
        'Yields': [],
        'Receives': [],
        'Raises': [],
        'Warns': [],
        'Other Parameters': [],
        'Attributes': [],
        'Methods': [],
        'See Also': [],
        'Notes': [],
        'Warnings': [],
        'References': '',
        'Examples': '',
        'index': {}
    }

    def __init__(self, docstring, config={}):
        orig_docstring = docstring
        docstring = textwrap.dedent(docstring).split('\n')

        self._doc = Reader(docstring)
        self._parsed_data = copy.deepcopy(self.sections)

        try:
            self._parse()
        except ParseError as e:
            e.docstring = orig_docstring
            raise

    def __getitem__(self, key):
        return self._parsed_data[key]

    def __setitem__(self, key, val):
        if key not in self._parsed_data:
            self._error_location(f"Unknown section {key}", error=False)
        else:
            self._parsed_data[key] = val

    def __iter__(self):
        return iter(self._parsed_data)

    def __len__(self):
        return len(self._parsed_data)

    def _is_at_section(self):
        self._doc.seek_next_non_empty_line()

        if self._doc.eof():
            return False

        l1 = self._doc.peek().strip()  # e.g. Parameters

        if l1.startswith('.. index::'):
            return True

        l2 = self._doc.peek(1).strip()  # ---------- or ==========
        return l2.startswith('-'*len(l1)) or l2.startswith('='*len(l1))

    def _strip(self, doc):
        i = 0
        j = 0
        for i, line in enumerate(doc):
            if line.strip():
                break

        for j, line in enumerate(doc[::-1]):
            if line.strip():
                break

        return doc[i:len(doc)-j]

    def _read_to_next_section(self):
        section = self._doc.read_to_next_empty_line()

        while not self._is_at_section() and not self._doc.eof():
            if not self._doc.peek(-1).strip():  # previous line was empty
                section += ['']

            section += self._doc.read_to_next_empty_line()

        return section

    def _read_sections(self):
        while not self._doc.eof():
            data = self._read_to_next_section()
            name = data[0].strip()

            if name.startswith('..'):  # index section
                yield name, data[1:]
            elif len(data) < 2:
                yield StopIteration
            else:
                yield name, self._strip(data[2:])

    def _parse_param_list(self, content, single_element_is_type=False):
        r = Reader(content)
        params = []
        while not r.eof():
            header = r.read().strip()
            if ' : ' in header:
                arg_name, arg_type = header.split(' : ')[:2]
            else:
                if single_element_is_type:
                    arg_name, arg_type = '', header
                else:
                    arg_name, arg_type = header, ''

            desc = r.read_to_next_unindented_line()
            desc = dedent_lines(desc)
            desc = strip_blank_lines(desc)

            params.append(Parameter(arg_name, arg_type, desc))

        return params

    # See also supports the following formats.
    #
    # <FUNCNAME>
    # <FUNCNAME> SPACE* COLON SPACE+ <DESC> SPACE*
    # <FUNCNAME> ( COMMA SPACE+ <FUNCNAME>)+ (COMMA | PERIOD)? SPACE*
    # <FUNCNAME> ( COMMA SPACE+ <FUNCNAME>)* SPACE* COLON SPACE+ <DESC> SPACE*

    # <FUNCNAME> is one of
    #   <PLAIN_FUNCNAME>
    #   COLON <ROLE> COLON BACKTICK <PLAIN_FUNCNAME> BACKTICK
    # where
    #   <PLAIN_FUNCNAME> is a legal function name, and
    #   <ROLE> is any nonempty sequence of word characters.
    # Examples: func_f1  :meth:`func_h1` :obj:`~baz.obj_r` :class:`class_j`
    # <DESC> is a string describing the function.

    _role = r":(?P<role>\w+):"
    _funcbacktick = r"`(?P<name>(?:~\w+\.)?[a-zA-Z0-9_\.-]+)`"
    _funcplain = r"(?P<name2>[a-zA-Z0-9_\.-]+)"
    _funcname = r"(" + _role + _funcbacktick + r"|" + _funcplain + r")"
    _funcnamenext = _funcname.replace('role', 'rolenext')
    _funcnamenext = _funcnamenext.replace('name', 'namenext')
    _description = r"(?P<description>\s*:(\s+(?P<desc>\S+.*))?)?\s*$"
    _func_rgx = re.compile(r"^\s*" + _funcname + r"\s*")
    _line_rgx = re.compile(
        r"^\s*" +
        r"(?P<allfuncs>" +        # group for all function names
        _funcname +
        r"(?P<morefuncs>([,]\s+" + _funcnamenext + r")*)" +
        r")" +                     # end of "allfuncs"
        r"(?P<trailing>[,\.])?" +   # Some function lists have a trailing comma (or period)  '\s*'
        _description)

    # Empty <DESC> elements are replaced with '..'
    empty_description = '..'

    def _parse_see_also(self, content):
        """
        func_name : Descriptive text
            continued text
        another_func_name : Descriptive text
        func_name1, func_name2, :meth:`func_name`, func_name3

        """

        items = []

        def parse_item_name(text):
            """Match ':role:`name`' or 'name'."""
            m = self._func_rgx.match(text)
            if not m:
                raise ParseError(f"{text} is not a item name")
            role = m.group('role')
            name = m.group('name') if role else m.group('name2')
            return name, role, m.end()

        rest = []
        for line in content:
            if not line.strip():
                continue

            line_match = self._line_rgx.match(line)
            description = None
            if line_match:
                description = line_match.group('desc')
                if line_match.group('trailing') and description:
                    self._error_location(
                        'Unexpected comma or period after function list at index %d of '
                        'line "%s"' % (line_match.end('trailing'), line),
                        error=False)
            if not description and line.startswith(' '):
                rest.append(line.strip())
            elif line_match:
                funcs = []
                text = line_match.group('allfuncs')
                while True:
                    if not text.strip():
                        break
                    name, role, match_end = parse_item_name(text)
                    funcs.append((name, role))
                    text = text[match_end:].strip()
                    if text and text[0] == ',':
                        text = text[1:].strip()
                rest = list(filter(None, [description]))
                items.append((funcs, rest))
            else:
                raise ParseError(f"{line} is not a item name")
        return items

    def _parse_index(self, section, content):
        """
        .. index: default
           :refguide: something, else, and more

        """
        def strip_each_in(lst):
            return [s.strip() for s in lst]

        out = {}
        section = section.split('::')
        if len(section) > 1:
            out['default'] = strip_each_in(section[1].split(','))[0]
        for line in content:
            line = line.split(':')
            if len(line) > 2:
                out[line[1]] = strip_each_in(line[2].split(','))
        return out

    def _parse_summary(self):
        """Grab signature (if given) and summary"""
        if self._is_at_section():
            return

        # If several signatures present, take the last one
        while True:
            summary = self._doc.read_to_next_empty_line()
            summary_str = " ".join([s.strip() for s in summary]).strip()
            compiled = re.compile(r'^([\w., ]+=)?\s*[\w\.]+\(.*\)$')
            if compiled.match(summary_str):
                self['Signature'] = summary_str
                if not self._is_at_section():
                    continue
            break

        if summary is not None:
            self['Summary'] = summary

        if not self._is_at_section():
            self['Extended Summary'] = self._read_to_next_section()

    def _parse(self):
        self._doc.reset()
        self._parse_summary()

        sections = list(self._read_sections())
        section_names = {section for section, content in sections}

        has_returns = 'Returns' in section_names
        has_yields = 'Yields' in section_names
        # We could do more tests, but we are not. Arbitrarily.
        if has_returns and has_yields:
            msg = 'Docstring contains both a Returns and Yields section.'
            raise ValueError(msg)
        if not has_yields and 'Receives' in section_names:
            msg = 'Docstring contains a Receives section but not Yields.'
            raise ValueError(msg)

        for (section, content) in sections:
            if not section.startswith('..'):
                section = (s.capitalize() for s in section.split(' '))
                section = ' '.join(section)
                if self.get(section):
                    self._error_location(f"The section {section} appears twice")

            if section in ('Parameters', 'Other Parameters', 'Attributes',
                           'Methods'):
                self[section] = self._parse_param_list(content)
            elif section in ('Returns', 'Yields', 'Raises', 'Warns', 'Receives'):
                self[section] = self._parse_param_list(
                    content, single_element_is_type=True)
            elif section.startswith('.. index::'):
                self['index'] = self._parse_index(section, content)
            elif section == 'See Also':
                self['See Also'] = self._parse_see_also(content)
            else:
                self[section] = content

    def _error_location(self, msg, error=True):
        if hasattr(self, '_obj'):
            # we know where the docs came from:
            try:
                filename = inspect.getsourcefile(self._obj)
            except TypeError:
                filename = None
            msg = msg + f" in the docstring of {self._obj} in {filename}."
        if error:
            raise ValueError(msg)
        else:
            warn(msg)

    # string conversion routines

    def _str_header(self, name, symbol='-'):
        return [name, len(name)*symbol]

    def _str_indent(self, doc, indent=4):
        out = []
        for line in doc:
            out += [' '*indent + line]
        return out

    def _str_signature(self):
        if self['Signature']:
            return [self['Signature'].replace('*', r'\*')] + ['']
        else:
            return ['']

    def _str_summary(self):
        if self['Summary']:
            return self['Summary'] + ['']
        else:
            return []

    def _str_extended_summary(self):
        if self['Extended Summary']:
            return self['Extended Summary'] + ['']
        else:
            return []

    def _str_param_list(self, name):
        out = []
        if self[name]:
            out += self._str_header(name)
            for param in self[name]:
                parts = []
                if param.name:
                    parts.append(param.name)
                if param.type:
                    parts.append(param.type)
                out += [' : '.join(parts)]
                if param.desc and ''.join(param.desc).strip():
                    out += self._str_indent(param.desc)
            out += ['']
        return out

    def _str_section(self, name):
        out = []
        if self[name]:
            out += self._str_header(name)
            out += self[name]
            out += ['']
        return out

    def _str_see_also(self, func_role):
        if not self['See Also']:
            return []
        out = []
        out += self._str_header("See Also")
        out += ['']
        last_had_desc = True
        for funcs, desc in self['See Also']:
            assert isinstance(funcs, list)
            links = []
            for func, role in funcs:
                if role:
                    link = f':{role}:`{func}`'
                elif func_role:
                    link = f':{func_role}:`{func}`'
                else:
                    link = f"`{func}`_"
                links.append(link)
            link = ', '.join(links)
            out += [link]
            if desc:
                out += self._str_indent([' '.join(desc)])
                last_had_desc = True
            else:
                last_had_desc = False
                out += self._str_indent([self.empty_description])

        if last_had_desc:
            out += ['']
        out += ['']
        return out

    def _str_index(self):
        idx = self['index']
        out = []
        output_index = False
        default_index = idx.get('default', '')
        if default_index:
            output_index = True
        out += [f'.. index:: {default_index}']
        for section, references in idx.items():
            if section == 'default':
                continue
            output_index = True
            out += [f"   :{section}: {', '.join(references)}"]
        if output_index:
            return out
        else:
            return ''

    def __str__(self, func_role=''):
        out = []
        out += self._str_signature()
        out += self._str_summary()
        out += self._str_extended_summary()
        for param_list in ('Parameters', 'Returns', 'Yields', 'Receives',
                           'Other Parameters', 'Raises', 'Warns'):
            out += self._str_param_list(param_list)
        out += self._str_section('Warnings')
        out += self._str_see_also(func_role)
        for s in ('Notes', 'References', 'Examples'):
            out += self._str_section(s)
        for param_list in ('Attributes', 'Methods'):
            out += self._str_param_list(param_list)
        out += self._str_index()
        return '\n'.join(out)


def indent(str, indent=4):
    indent_str = ' '*indent
    if str is None:
        return indent_str
    lines = str.split('\n')
    return '\n'.join(indent_str + l for l in lines)


def dedent_lines(lines):
    """Deindent a list of lines maximally"""
    return textwrap.dedent("\n".join(lines)).split("\n")


def header(text, style='-'):
    return text + '\n' + style*len(text) + '\n'


class FunctionDoc(NumpyDocString):
    def __init__(self, func, role='func', doc=None, config={}):
        self._f = func
        self._role = role  # e.g. "func" or "meth"

        if doc is None:
            if func is None:
                raise ValueError("No function or docstring given")
            doc = inspect.getdoc(func) or ''
        NumpyDocString.__init__(self, doc, config)

        if not self['Signature'] and func is not None:
            func, func_name = self.get_func()
            try:
                try:
                    signature = str(inspect.signature(func))
                except (AttributeError, ValueError):
                    # try to read signature, backward compat for older Python
                    if sys.version_info[0] >= 3:
                        argspec = inspect.getfullargspec(func)
                    else:
                        argspec = inspect.getargspec(func)
                    signature = inspect.formatargspec(*argspec)
                signature = f'{func_name}{signature}'
            except TypeError:
                signature = f'{func_name}()'
            self['Signature'] = signature

    def get_func(self):
        func_name = getattr(self._f, '__name__', self.__class__.__name__)
        if inspect.isclass(self._f):
            func = getattr(self._f, '__call__', self._f.__init__)
        else:
            func = self._f
        return func, func_name

    def __str__(self):
        out = ''

        func, func_name = self.get_func()

        roles = {'func': 'function',
                 'meth': 'method'}

        if self._role:
            if self._role not in roles:
                print(f"Warning: invalid role {self._role}")
            out += f".. {roles.get(self._role, '')}:: {func_name}\n    \n\n"

        out += super().__str__(func_role=self._role)
        return out


class ClassDoc(NumpyDocString):

    extra_public_methods = ['__call__']

    def __init__(self, cls, doc=None, modulename='', func_doc=FunctionDoc,
                 config={}):
        if not inspect.isclass(cls) and cls is not None:
            raise ValueError(f"Expected a class or None, but got {cls!r}")
        self._cls = cls

        if 'sphinx' in sys.modules:
            from sphinx.ext.autodoc import ALL
        else:
            ALL = object()

        self.show_inherited_members = config.get(
                    'show_inherited_class_members', True)

        if modulename and not modulename.endswith('.'):
            modulename += '.'
        self._mod = modulename

        if doc is None:
            if cls is None:
                raise ValueError("No class or documentation string given")
            doc = pydoc.getdoc(cls)

        NumpyDocString.__init__(self, doc)

        _members = config.get('members', [])
        if _members is ALL:
            _members = None
        _exclude = config.get('exclude-members', [])

        if config.get('show_class_members', True) and _exclude is not ALL:
            def splitlines_x(s):
                if not s:
                    return []
                else:
                    return s.splitlines()
            for field, items in [('Methods', self.methods),
                                 ('Attributes', self.properties)]:
                if not self[field]:
                    doc_list = []
                    for name in sorted(items):
                        if (name in _exclude or
                                (_members and name not in _members)):
                            continue
                        try:
                            doc_item = pydoc.getdoc(getattr(self._cls, name))
                            doc_list.append(
                                Parameter(name, '', splitlines_x(doc_item)))
                        except AttributeError:
                            pass  # method doesn't exist
                    self[field] = doc_list

    @property
    def methods(self):
        if self._cls is None:
            return []
        return [name for name, func in inspect.getmembers(self._cls)
                if ((not name.startswith('_')
                     or name in self.extra_public_methods)
                    and isinstance(func, Callable)
                    and self._is_show_member(name))]

    @property
    def properties(self):
        if self._cls is None:
            return []
        return [name for name, func in inspect.getmembers(self._cls)
                if (not name.startswith('_') and
                    (func is None or isinstance(func, property) or
                     inspect.isdatadescriptor(func))
                    and self._is_show_member(name))]

    def _is_show_member(self, name):
        if self.show_inherited_members:
            return True  # show all class members
        if name not in self._cls.__dict__:
            return False  # class member is inherited, we do not show it
        return True
