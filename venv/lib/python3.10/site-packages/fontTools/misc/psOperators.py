_accessstrings = {0: "", 1: "readonly", 2: "executeonly", 3: "noaccess"}


class ps_object(object):
    literal = 1
    access = 0
    value = None

    def __init__(self, value):
        self.value = value
        self.type = self.__class__.__name__[3:] + "type"

    def __repr__(self):
        return "<%s %s>" % (self.__class__.__name__[3:], repr(self.value))


class ps_operator(ps_object):
    literal = 0

    def __init__(self, name, function):
        self.name = name
        self.function = function
        self.type = self.__class__.__name__[3:] + "type"

    def __repr__(self):
        return "<operator %s>" % self.name


class ps_procedure(ps_object):
    literal = 0

    def __repr__(self):
        return "<procedure>"

    def __str__(self):
        psstring = "{"
        for i in range(len(self.value)):
            if i:
                psstring = psstring + " " + str(self.value[i])
            else:
                psstring = psstring + str(self.value[i])
        return psstring + "}"


class ps_name(ps_object):
    literal = 0

    def __str__(self):
        if self.literal:
            return "/" + self.value
        else:
            return self.value


class ps_literal(ps_object):
    def __str__(self):
        return "/" + self.value


class ps_array(ps_object):
    def __str__(self):
        psstring = "["
        for i in range(len(self.value)):
            item = self.value[i]
            access = _accessstrings[item.access]
            if access:
                access = " " + access
            if i:
                psstring = psstring + " " + str(item) + access
            else:
                psstring = psstring + str(item) + access
        return psstring + "]"

    def __repr__(self):
        return "<array>"


_type1_pre_eexec_order = [
    "FontInfo",
    "FontName",
    "Encoding",
    "PaintType",
    "FontType",
    "FontMatrix",
    "FontBBox",
    "UniqueID",
    "Metrics",
    "StrokeWidth",
]

_type1_fontinfo_order = [
    "version",
    "Notice",
    "FullName",
    "FamilyName",
    "Weight",
    "ItalicAngle",
    "isFixedPitch",
    "UnderlinePosition",
    "UnderlineThickness",
]

_type1_post_eexec_order = ["Private", "CharStrings", "FID"]


def _type1_item_repr(key, value):
    psstring = ""
    access = _accessstrings[value.access]
    if access:
        access = access + " "
    if key == "CharStrings":
        psstring = psstring + "/%s %s def\n" % (
            key,
            _type1_CharString_repr(value.value),
        )
    elif key == "Encoding":
        psstring = psstring + _type1_Encoding_repr(value, access)
    else:
        psstring = psstring + "/%s %s %sdef\n" % (str(key), str(value), access)
    return psstring


def _type1_Encoding_repr(encoding, access):
    encoding = encoding.value
    psstring = "/Encoding 256 array\n0 1 255 {1 index exch /.notdef put} for\n"
    for i in range(256):
        name = encoding[i].value
        if name != ".notdef":
            psstring = psstring + "dup %d /%s put\n" % (i, name)
    return psstring + access + "def\n"


def _type1_CharString_repr(charstrings):
    items = sorted(charstrings.items())
    return "xxx"


class ps_font(ps_object):
    def __str__(self):
        psstring = "%d dict dup begin\n" % len(self.value)
        for key in _type1_pre_eexec_order:
            try:
                value = self.value[key]
            except KeyError:
                pass
            else:
                psstring = psstring + _type1_item_repr(key, value)
        items = sorted(self.value.items())
        for key, value in items:
            if key not in _type1_pre_eexec_order + _type1_post_eexec_order:
                psstring = psstring + _type1_item_repr(key, value)
        psstring = psstring + "currentdict end\ncurrentfile eexec\ndup "
        for key in _type1_post_eexec_order:
            try:
                value = self.value[key]
            except KeyError:
                pass
            else:
                psstring = psstring + _type1_item_repr(key, value)
        return (
            psstring
            + "dup/FontName get exch definefont pop\nmark currentfile closefile\n"
            + 8 * (64 * "0" + "\n")
            + "cleartomark"
            + "\n"
        )

    def __repr__(self):
        return "<font>"


class ps_file(ps_object):
    pass


class ps_dict(ps_object):
    def __str__(self):
        psstring = "%d dict dup begin\n" % len(self.value)
        items = sorted(self.value.items())
        for key, value in items:
            access = _accessstrings[value.access]
            if access:
                access = access + " "
            psstring = psstring + "/%s %s %sdef\n" % (str(key), str(value), access)
        return psstring + "end "

    def __repr__(self):
        return "<dict>"


class ps_mark(ps_object):
    def __init__(self):
        self.value = "mark"
        self.type = self.__class__.__name__[3:] + "type"


class ps_procmark(ps_object):
    def __init__(self):
        self.value = "procmark"
        self.type = self.__class__.__name__[3:] + "type"


class ps_null(ps_object):
    def __init__(self):
        self.type = self.__class__.__name__[3:] + "type"


class ps_boolean(ps_object):
    def __str__(self):
        if self.value:
            return "true"
        else:
            return "false"


class ps_string(ps_object):
    def __str__(self):
        return "(%s)" % repr(self.value)[1:-1]


class ps_integer(ps_object):
    def __str__(self):
        return repr(self.value)


class ps_real(ps_object):
    def __str__(self):
        return repr(self.value)


class PSOperators(object):
    def ps_def(self):
        obj = self.pop()
        name = self.pop()
        self.dictstack[-1][name.value] = obj

    def ps_bind(self):
        proc = self.pop("proceduretype")
        self.proc_bind(proc)
        self.push(proc)

    def proc_bind(self, proc):
        for i in range(len(proc.value)):
            item = proc.value[i]
            if item.type == "proceduretype":
                self.proc_bind(item)
            else:
                if not item.literal:
                    try:
                        obj = self.resolve_name(item.value)
                    except:
                        pass
                    else:
                        if obj.type == "operatortype":
                            proc.value[i] = obj

    def ps_exch(self):
        if len(self.stack) < 2:
            raise RuntimeError("stack underflow")
        obj1 = self.pop()
        obj2 = self.pop()
        self.push(obj1)
        self.push(obj2)

    def ps_dup(self):
        if not self.stack:
            raise RuntimeError("stack underflow")
        self.push(self.stack[-1])

    def ps_exec(self):
        obj = self.pop()
        if obj.type == "proceduretype":
            self.call_procedure(obj)
        else:
            self.handle_object(obj)

    def ps_count(self):
        self.push(ps_integer(len(self.stack)))

    def ps_eq(self):
        any1 = self.pop()
        any2 = self.pop()
        self.push(ps_boolean(any1.value == any2.value))

    def ps_ne(self):
        any1 = self.pop()
        any2 = self.pop()
        self.push(ps_boolean(any1.value != any2.value))

    def ps_cvx(self):
        obj = self.pop()
        obj.literal = 0
        self.push(obj)

    def ps_matrix(self):
        matrix = [
            ps_real(1.0),
            ps_integer(0),
            ps_integer(0),
            ps_real(1.0),
            ps_integer(0),
            ps_integer(0),
        ]
        self.push(ps_array(matrix))

    def ps_string(self):
        num = self.pop("integertype").value
        self.push(ps_string("\0" * num))

    def ps_type(self):
        obj = self.pop()
        self.push(ps_string(obj.type))

    def ps_store(self):
        value = self.pop()
        key = self.pop()
        name = key.value
        for i in range(len(self.dictstack) - 1, -1, -1):
            if name in self.dictstack[i]:
                self.dictstack[i][name] = value
                break
        self.dictstack[-1][name] = value

    def ps_where(self):
        name = self.pop()
        # XXX
        self.push(ps_boolean(0))

    def ps_systemdict(self):
        self.push(ps_dict(self.dictstack[0]))

    def ps_userdict(self):
        self.push(ps_dict(self.dictstack[1]))

    def ps_currentdict(self):
        self.push(ps_dict(self.dictstack[-1]))

    def ps_currentfile(self):
        self.push(ps_file(self.tokenizer))

    def ps_eexec(self):
        f = self.pop("filetype").value
        f.starteexec()

    def ps_closefile(self):
        f = self.pop("filetype").value
        f.skipwhite()
        f.stopeexec()

    def ps_cleartomark(self):
        obj = self.pop()
        while obj != self.mark:
            obj = self.pop()

    def ps_readstring(self, ps_boolean=ps_boolean, len=len):
        s = self.pop("stringtype")
        oldstr = s.value
        f = self.pop("filetype")
        # pad = file.value.read(1)
        # for StringIO, this is faster
        f.value.pos = f.value.pos + 1
        newstr = f.value.read(len(oldstr))
        s.value = newstr
        self.push(s)
        self.push(ps_boolean(len(oldstr) == len(newstr)))

    def ps_known(self):
        key = self.pop()
        d = self.pop("dicttype", "fonttype")
        self.push(ps_boolean(key.value in d.value))

    def ps_if(self):
        proc = self.pop("proceduretype")
        if self.pop("booleantype").value:
            self.call_procedure(proc)

    def ps_ifelse(self):
        proc2 = self.pop("proceduretype")
        proc1 = self.pop("proceduretype")
        if self.pop("booleantype").value:
            self.call_procedure(proc1)
        else:
            self.call_procedure(proc2)

    def ps_readonly(self):
        obj = self.pop()
        if obj.access < 1:
            obj.access = 1
        self.push(obj)

    def ps_executeonly(self):
        obj = self.pop()
        if obj.access < 2:
            obj.access = 2
        self.push(obj)

    def ps_noaccess(self):
        obj = self.pop()
        if obj.access < 3:
            obj.access = 3
        self.push(obj)

    def ps_not(self):
        obj = self.pop("booleantype", "integertype")
        if obj.type == "booleantype":
            self.push(ps_boolean(not obj.value))
        else:
            self.push(ps_integer(~obj.value))

    def ps_print(self):
        str = self.pop("stringtype")
        print("PS output --->", str.value)

    def ps_anchorsearch(self):
        seek = self.pop("stringtype")
        s = self.pop("stringtype")
        seeklen = len(seek.value)
        if s.value[:seeklen] == seek.value:
            self.push(ps_string(s.value[seeklen:]))
            self.push(seek)
            self.push(ps_boolean(1))
        else:
            self.push(s)
            self.push(ps_boolean(0))

    def ps_array(self):
        num = self.pop("integertype")
        array = ps_array([None] * num.value)
        self.push(array)

    def ps_astore(self):
        array = self.pop("arraytype")
        for i in range(len(array.value) - 1, -1, -1):
            array.value[i] = self.pop()
        self.push(array)

    def ps_load(self):
        name = self.pop()
        self.push(self.resolve_name(name.value))

    def ps_put(self):
        obj1 = self.pop()
        obj2 = self.pop()
        obj3 = self.pop("arraytype", "dicttype", "stringtype", "proceduretype")
        tp = obj3.type
        if tp == "arraytype" or tp == "proceduretype":
            obj3.value[obj2.value] = obj1
        elif tp == "dicttype":
            obj3.value[obj2.value] = obj1
        elif tp == "stringtype":
            index = obj2.value
            obj3.value = obj3.value[:index] + chr(obj1.value) + obj3.value[index + 1 :]

    def ps_get(self):
        obj1 = self.pop()
        if obj1.value == "Encoding":
            pass
        obj2 = self.pop(
            "arraytype", "dicttype", "stringtype", "proceduretype", "fonttype"
        )
        tp = obj2.type
        if tp in ("arraytype", "proceduretype"):
            self.push(obj2.value[obj1.value])
        elif tp in ("dicttype", "fonttype"):
            self.push(obj2.value[obj1.value])
        elif tp == "stringtype":
            self.push(ps_integer(ord(obj2.value[obj1.value])))
        else:
            assert False, "shouldn't get here"

    def ps_getinterval(self):
        obj1 = self.pop("integertype")
        obj2 = self.pop("integertype")
        obj3 = self.pop("arraytype", "stringtype")
        tp = obj3.type
        if tp == "arraytype":
            self.push(ps_array(obj3.value[obj2.value : obj2.value + obj1.value]))
        elif tp == "stringtype":
            self.push(ps_string(obj3.value[obj2.value : obj2.value + obj1.value]))

    def ps_putinterval(self):
        obj1 = self.pop("arraytype", "stringtype")
        obj2 = self.pop("integertype")
        obj3 = self.pop("arraytype", "stringtype")
        tp = obj3.type
        if tp == "arraytype":
            obj3.value[obj2.value : obj2.value + len(obj1.value)] = obj1.value
        elif tp == "stringtype":
            newstr = obj3.value[: obj2.value]
            newstr = newstr + obj1.value
            newstr = newstr + obj3.value[obj2.value + len(obj1.value) :]
            obj3.value = newstr

    def ps_cvn(self):
        self.push(ps_name(self.pop("stringtype").value))

    def ps_index(self):
        n = self.pop("integertype").value
        if n < 0:
            raise RuntimeError("index may not be negative")
        self.push(self.stack[-1 - n])

    def ps_for(self):
        proc = self.pop("proceduretype")
        limit = self.pop("integertype", "realtype").value
        increment = self.pop("integertype", "realtype").value
        i = self.pop("integertype", "realtype").value
        while 1:
            if increment > 0:
                if i > limit:
                    break
            else:
                if i < limit:
                    break
            if type(i) == type(0.0):
                self.push(ps_real(i))
            else:
                self.push(ps_integer(i))
            self.call_procedure(proc)
            i = i + increment

    def ps_forall(self):
        proc = self.pop("proceduretype")
        obj = self.pop("arraytype", "stringtype", "dicttype")
        tp = obj.type
        if tp == "arraytype":
            for item in obj.value:
                self.push(item)
                self.call_procedure(proc)
        elif tp == "stringtype":
            for item in obj.value:
                self.push(ps_integer(ord(item)))
                self.call_procedure(proc)
        elif tp == "dicttype":
            for key, value in obj.value.items():
                self.push(ps_name(key))
                self.push(value)
                self.call_procedure(proc)

    def ps_definefont(self):
        font = self.pop("dicttype")
        name = self.pop()
        font = ps_font(font.value)
        self.dictstack[0]["FontDirectory"].value[name.value] = font
        self.push(font)

    def ps_findfont(self):
        name = self.pop()
        font = self.dictstack[0]["FontDirectory"].value[name.value]
        self.push(font)

    def ps_pop(self):
        self.pop()

    def ps_dict(self):
        self.pop("integertype")
        self.push(ps_dict({}))

    def ps_begin(self):
        self.dictstack.append(self.pop("dicttype").value)

    def ps_end(self):
        if len(self.dictstack) > 2:
            del self.dictstack[-1]
        else:
            raise RuntimeError("dictstack underflow")


notdef = ".notdef"
from fontTools.encodings.StandardEncoding import StandardEncoding

ps_StandardEncoding = list(map(ps_name, StandardEncoding))
