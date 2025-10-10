from fontTools.misc.textTools import bytechr, byteord, bytesjoin, tobytes, tostr
from fontTools.misc import eexec
from .psOperators import (
    PSOperators,
    ps_StandardEncoding,
    ps_array,
    ps_boolean,
    ps_dict,
    ps_integer,
    ps_literal,
    ps_mark,
    ps_name,
    ps_operator,
    ps_procedure,
    ps_procmark,
    ps_real,
    ps_string,
)
import re
from collections.abc import Callable
from string import whitespace
import logging


log = logging.getLogger(__name__)

ps_special = b"()<>[]{}%"  # / is one too, but we take care of that one differently

skipwhiteRE = re.compile(bytesjoin([b"[", whitespace, b"]*"]))
endofthingPat = bytesjoin([b"[^][(){}<>/%", whitespace, b"]*"])
endofthingRE = re.compile(endofthingPat)
commentRE = re.compile(b"%[^\n\r]*")

# XXX This not entirely correct as it doesn't allow *nested* embedded parens:
stringPat = rb"""
	\(
		(
			(
				[^()]*   \   [()]
			)
			|
			(
				[^()]*  \(   [^()]*  \)
			)
		)*
		[^()]*
	\)
"""
stringPat = b"".join(stringPat.split())
stringRE = re.compile(stringPat)

hexstringRE = re.compile(bytesjoin([b"<[", whitespace, b"0-9A-Fa-f]*>"]))


class PSTokenError(Exception):
    pass


class PSError(Exception):
    pass


class PSTokenizer(object):
    def __init__(self, buf=b"", encoding="ascii"):
        # Force self.buf to be a byte string
        buf = tobytes(buf)
        self.buf = buf
        self.len = len(buf)
        self.pos = 0
        self.closed = False
        self.encoding = encoding

    def read(self, n=-1):
        """Read at most 'n' bytes from the buffer, or less if the read
        hits EOF before obtaining 'n' bytes.
        If 'n' is negative or omitted, read all data until EOF is reached.
        """
        if self.closed:
            raise ValueError("I/O operation on closed file")
        if n is None or n < 0:
            newpos = self.len
        else:
            newpos = min(self.pos + n, self.len)
        r = self.buf[self.pos : newpos]
        self.pos = newpos
        return r

    def close(self):
        if not self.closed:
            self.closed = True
            del self.buf, self.pos

    def getnexttoken(
        self,
        # localize some stuff, for performance
        len=len,
        ps_special=ps_special,
        stringmatch=stringRE.match,
        hexstringmatch=hexstringRE.match,
        commentmatch=commentRE.match,
        endmatch=endofthingRE.match,
    ):
        self.skipwhite()
        if self.pos >= self.len:
            return None, None
        pos = self.pos
        buf = self.buf
        char = bytechr(byteord(buf[pos]))
        if char in ps_special:
            if char in b"{}[]":
                tokentype = "do_special"
                token = char
            elif char == b"%":
                tokentype = "do_comment"
                _, nextpos = commentmatch(buf, pos).span()
                token = buf[pos:nextpos]
            elif char == b"(":
                tokentype = "do_string"
                m = stringmatch(buf, pos)
                if m is None:
                    raise PSTokenError("bad string at character %d" % pos)
                _, nextpos = m.span()
                token = buf[pos:nextpos]
            elif char == b"<":
                tokentype = "do_hexstring"
                m = hexstringmatch(buf, pos)
                if m is None:
                    raise PSTokenError("bad hexstring at character %d" % pos)
                _, nextpos = m.span()
                token = buf[pos:nextpos]
            else:
                raise PSTokenError("bad token at character %d" % pos)
        else:
            if char == b"/":
                tokentype = "do_literal"
                m = endmatch(buf, pos + 1)
            else:
                tokentype = ""
                m = endmatch(buf, pos)
            if m is None:
                raise PSTokenError("bad token at character %d" % pos)
            _, nextpos = m.span()
            token = buf[pos:nextpos]
        self.pos = pos + len(token)
        token = tostr(token, encoding=self.encoding)
        return tokentype, token

    def skipwhite(self, whitematch=skipwhiteRE.match):
        _, nextpos = whitematch(self.buf, self.pos).span()
        self.pos = nextpos

    def starteexec(self):
        self.pos = self.pos + 1
        self.dirtybuf = self.buf[self.pos :]
        self.buf, R = eexec.decrypt(self.dirtybuf, 55665)
        self.len = len(self.buf)
        self.pos = 4

    def stopeexec(self):
        if not hasattr(self, "dirtybuf"):
            return
        self.buf = self.dirtybuf
        del self.dirtybuf


class PSInterpreter(PSOperators):
    def __init__(self, encoding="ascii"):
        systemdict = {}
        userdict = {}
        self.encoding = encoding
        self.dictstack = [systemdict, userdict]
        self.stack = []
        self.proclevel = 0
        self.procmark = ps_procmark()
        self.fillsystemdict()

    def fillsystemdict(self):
        systemdict = self.dictstack[0]
        systemdict["["] = systemdict["mark"] = self.mark = ps_mark()
        systemdict["]"] = ps_operator("]", self.do_makearray)
        systemdict["true"] = ps_boolean(1)
        systemdict["false"] = ps_boolean(0)
        systemdict["StandardEncoding"] = ps_array(ps_StandardEncoding)
        systemdict["FontDirectory"] = ps_dict({})
        self.suckoperators(systemdict, self.__class__)

    def suckoperators(self, systemdict, klass):
        for name in dir(klass):
            attr = getattr(self, name)
            if isinstance(attr, Callable) and name[:3] == "ps_":
                name = name[3:]
                systemdict[name] = ps_operator(name, attr)
        for baseclass in klass.__bases__:
            self.suckoperators(systemdict, baseclass)

    def interpret(self, data, getattr=getattr):
        tokenizer = self.tokenizer = PSTokenizer(data, self.encoding)
        getnexttoken = tokenizer.getnexttoken
        do_token = self.do_token
        handle_object = self.handle_object
        try:
            while 1:
                tokentype, token = getnexttoken()
                if not token:
                    break
                if tokentype:
                    handler = getattr(self, tokentype)
                    object = handler(token)
                else:
                    object = do_token(token)
                if object is not None:
                    handle_object(object)
            tokenizer.close()
            self.tokenizer = None
        except:
            if self.tokenizer is not None:
                log.debug(
                    "ps error:\n"
                    "- - - - - - -\n"
                    "%s\n"
                    ">>>\n"
                    "%s\n"
                    "- - - - - - -",
                    self.tokenizer.buf[self.tokenizer.pos - 50 : self.tokenizer.pos],
                    self.tokenizer.buf[self.tokenizer.pos : self.tokenizer.pos + 50],
                )
            raise

    def handle_object(self, object):
        if not (self.proclevel or object.literal or object.type == "proceduretype"):
            if object.type != "operatortype":
                object = self.resolve_name(object.value)
            if object.literal:
                self.push(object)
            else:
                if object.type == "proceduretype":
                    self.call_procedure(object)
                else:
                    object.function()
        else:
            self.push(object)

    def call_procedure(self, proc):
        handle_object = self.handle_object
        for item in proc.value:
            handle_object(item)

    def resolve_name(self, name):
        dictstack = self.dictstack
        for i in range(len(dictstack) - 1, -1, -1):
            if name in dictstack[i]:
                return dictstack[i][name]
        raise PSError("name error: " + str(name))

    def do_token(
        self,
        token,
        int=int,
        float=float,
        ps_name=ps_name,
        ps_integer=ps_integer,
        ps_real=ps_real,
    ):
        try:
            num = int(token)
        except (ValueError, OverflowError):
            try:
                num = float(token)
            except (ValueError, OverflowError):
                if "#" in token:
                    hashpos = token.find("#")
                    try:
                        base = int(token[:hashpos])
                        num = int(token[hashpos + 1 :], base)
                    except (ValueError, OverflowError):
                        return ps_name(token)
                    else:
                        return ps_integer(num)
                else:
                    return ps_name(token)
            else:
                return ps_real(num)
        else:
            return ps_integer(num)

    def do_comment(self, token):
        pass

    def do_literal(self, token):
        return ps_literal(token[1:])

    def do_string(self, token):
        return ps_string(token[1:-1])

    def do_hexstring(self, token):
        hexStr = "".join(token[1:-1].split())
        if len(hexStr) % 2:
            hexStr = hexStr + "0"
        cleanstr = []
        for i in range(0, len(hexStr), 2):
            cleanstr.append(chr(int(hexStr[i : i + 2], 16)))
        cleanstr = "".join(cleanstr)
        return ps_string(cleanstr)

    def do_special(self, token):
        if token == "{":
            self.proclevel = self.proclevel + 1
            return self.procmark
        elif token == "}":
            proc = []
            while 1:
                topobject = self.pop()
                if topobject == self.procmark:
                    break
                proc.append(topobject)
            self.proclevel = self.proclevel - 1
            proc.reverse()
            return ps_procedure(proc)
        elif token == "[":
            return self.mark
        elif token == "]":
            return ps_name("]")
        else:
            raise PSTokenError("huh?")

    def push(self, object):
        self.stack.append(object)

    def pop(self, *types):
        stack = self.stack
        if not stack:
            raise PSError("stack underflow")
        object = stack[-1]
        if types:
            if object.type not in types:
                raise PSError(
                    "typecheck, expected %s, found %s" % (repr(types), object.type)
                )
        del stack[-1]
        return object

    def do_makearray(self):
        array = []
        while 1:
            topobject = self.pop()
            if topobject == self.mark:
                break
            array.append(topobject)
        array.reverse()
        self.push(ps_array(array))

    def close(self):
        """Remove circular references."""
        del self.stack
        del self.dictstack


def unpack_item(item):
    tp = type(item.value)
    if tp == dict:
        newitem = {}
        for key, value in item.value.items():
            newitem[key] = unpack_item(value)
    elif tp == list:
        newitem = [None] * len(item.value)
        for i in range(len(item.value)):
            newitem[i] = unpack_item(item.value[i])
        if item.type == "proceduretype":
            newitem = tuple(newitem)
    else:
        newitem = item.value
    return newitem


def suckfont(data, encoding="ascii"):
    m = re.search(rb"/FontName\s+/([^ \t\n\r]+)\s+def", data)
    if m:
        fontName = m.group(1)
        fontName = fontName.decode()
    else:
        fontName = None
    interpreter = PSInterpreter(encoding=encoding)
    interpreter.interpret(
        b"/Helvetica 4 dict dup /Encoding StandardEncoding put definefont pop"
    )
    interpreter.interpret(data)
    fontdir = interpreter.dictstack[0]["FontDirectory"].value
    if fontName in fontdir:
        rawfont = fontdir[fontName]
    else:
        # fall back, in case fontName wasn't found
        fontNames = list(fontdir.keys())
        if len(fontNames) > 1:
            fontNames.remove("Helvetica")
        fontNames.sort()
        rawfont = fontdir[fontNames[0]]
    interpreter.close()
    return unpack_item(rawfont)
