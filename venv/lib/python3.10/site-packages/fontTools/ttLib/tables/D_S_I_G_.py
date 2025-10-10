from fontTools.misc.textTools import bytesjoin, strjoin, tobytes, tostr, safeEval
from fontTools.misc import sstruct
from . import DefaultTable
import base64

DSIG_HeaderFormat = """
	> # big endian
	ulVersion:      L
	usNumSigs:      H
	usFlag:         H
"""
# followed by an array of usNumSigs DSIG_Signature records
DSIG_SignatureFormat = """
	> # big endian
	ulFormat:       L
	ulLength:       L # length includes DSIG_SignatureBlock header
	ulOffset:       L
"""
# followed by an array of usNumSigs DSIG_SignatureBlock records,
# each followed immediately by the pkcs7 bytes
DSIG_SignatureBlockFormat = """
	> # big endian
	usReserved1:    H
	usReserved2:    H
	cbSignature:    l # length of following raw pkcs7 data
"""

#
# NOTE
# the DSIG table format allows for SignatureBlocks residing
# anywhere in the table and possibly in a different order as
# listed in the array after the first table header
#
# this implementation does not keep track of any gaps and/or data
# before or after the actual signature blocks while decompiling,
# and puts them in the same physical order as listed in the header
# on compilation with no padding whatsoever.
#


class table_D_S_I_G_(DefaultTable.DefaultTable):
    """Digital Signature table

    The ``DSIG`` table contains cryptographic signatures for the font.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/dsig
    """

    def decompile(self, data, ttFont):
        dummy, newData = sstruct.unpack2(DSIG_HeaderFormat, data, self)
        assert self.ulVersion == 1, "DSIG ulVersion must be 1"
        assert self.usFlag & ~1 == 0, "DSIG usFlag must be 0x1 or 0x0"
        self.signatureRecords = sigrecs = []
        for n in range(self.usNumSigs):
            sigrec, newData = sstruct.unpack2(
                DSIG_SignatureFormat, newData, SignatureRecord()
            )
            assert sigrec.ulFormat == 1, (
                "DSIG signature record #%d ulFormat must be 1" % n
            )
            sigrecs.append(sigrec)
        for sigrec in sigrecs:
            dummy, newData = sstruct.unpack2(
                DSIG_SignatureBlockFormat, data[sigrec.ulOffset :], sigrec
            )
            assert sigrec.usReserved1 == 0, (
                "DSIG signature record #%d usReserverd1 must be 0" % n
            )
            assert sigrec.usReserved2 == 0, (
                "DSIG signature record #%d usReserverd2 must be 0" % n
            )
            sigrec.pkcs7 = newData[: sigrec.cbSignature]

    def compile(self, ttFont):
        packed = sstruct.pack(DSIG_HeaderFormat, self)
        headers = [packed]
        offset = len(packed) + self.usNumSigs * sstruct.calcsize(DSIG_SignatureFormat)
        data = []
        for sigrec in self.signatureRecords:
            # first pack signature block
            sigrec.cbSignature = len(sigrec.pkcs7)
            packed = sstruct.pack(DSIG_SignatureBlockFormat, sigrec) + sigrec.pkcs7
            data.append(packed)
            # update redundant length field
            sigrec.ulLength = len(packed)
            # update running table offset
            sigrec.ulOffset = offset
            headers.append(sstruct.pack(DSIG_SignatureFormat, sigrec))
            offset += sigrec.ulLength
        if offset % 2:
            # Pad to even bytes
            data.append(b"\0")
        return bytesjoin(headers + data)

    def toXML(self, xmlWriter, ttFont):
        xmlWriter.comment(
            "note that the Digital Signature will be invalid after recompilation!"
        )
        xmlWriter.newline()
        xmlWriter.simpletag(
            "tableHeader",
            version=self.ulVersion,
            numSigs=self.usNumSigs,
            flag="0x%X" % self.usFlag,
        )
        for sigrec in self.signatureRecords:
            xmlWriter.newline()
            sigrec.toXML(xmlWriter, ttFont)
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "tableHeader":
            self.signatureRecords = []
            self.ulVersion = safeEval(attrs["version"])
            self.usNumSigs = safeEval(attrs["numSigs"])
            self.usFlag = safeEval(attrs["flag"])
            return
        if name == "SignatureRecord":
            sigrec = SignatureRecord()
            sigrec.fromXML(name, attrs, content, ttFont)
            self.signatureRecords.append(sigrec)


pem_spam = lambda l, spam={
    "-----BEGIN PKCS7-----": True,
    "-----END PKCS7-----": True,
    "": True,
}: not spam.get(l.strip())


def b64encode(b):
    s = base64.b64encode(b)
    # Line-break at 76 chars.
    items = []
    while s:
        items.append(tostr(s[:76]))
        items.append("\n")
        s = s[76:]
    return strjoin(items)


class SignatureRecord(object):
    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.__dict__)

    def toXML(self, writer, ttFont):
        writer.begintag(self.__class__.__name__, format=self.ulFormat)
        writer.newline()
        writer.write_noindent("-----BEGIN PKCS7-----\n")
        writer.write_noindent(b64encode(self.pkcs7))
        writer.write_noindent("-----END PKCS7-----\n")
        writer.endtag(self.__class__.__name__)

    def fromXML(self, name, attrs, content, ttFont):
        self.ulFormat = safeEval(attrs["format"])
        self.usReserved1 = safeEval(attrs.get("reserved1", "0"))
        self.usReserved2 = safeEval(attrs.get("reserved2", "0"))
        self.pkcs7 = base64.b64decode(tobytes(strjoin(filter(pem_spam, content))))
