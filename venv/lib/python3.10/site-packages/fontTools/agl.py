# -*- coding: utf-8 -*-
# The tables below are taken from
# https://github.com/adobe-type-tools/agl-aglfn/raw/4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6/glyphlist.txt
# and
# https://github.com/adobe-type-tools/agl-aglfn/raw/4036a9ca80a62f64f9de4f7321a9a045ad0ecfd6/aglfn.txt
"""
Interface to the Adobe Glyph List

This module exists to convert glyph names from the Adobe Glyph List
to their Unicode equivalents. Example usage:

	>>> from fontTools.agl import toUnicode
	>>> toUnicode("nahiragana")
	'な'

It also contains two dictionaries, ``UV2AGL`` and ``AGL2UV``, which map from
Unicode codepoints to AGL names and vice versa:

	>>> import fontTools
	>>> fontTools.agl.UV2AGL[ord("?")]
	'question'
	>>> fontTools.agl.AGL2UV["wcircumflex"]
	373

This is used by fontTools when it has to construct glyph names for a font which
doesn't include any (e.g. format 3.0 post tables).
"""

from fontTools.misc.textTools import tostr
import re


_aglText = """\
# -----------------------------------------------------------
# Copyright 2002-2019 Adobe (http://www.adobe.com/).
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the
# following conditions are met:
#
# Redistributions of source code must retain the above
# copyright notice, this list of conditions and the following
# disclaimer.
#
# Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following
# disclaimer in the documentation and/or other materials
# provided with the distribution.
#
# Neither the name of Adobe nor the names of its contributors
# may be used to endorse or promote products derived from this
# software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# -----------------------------------------------------------
# Name:          Adobe Glyph List
# Table version: 2.0
# Date:          September 20, 2002
# URL:           https://github.com/adobe-type-tools/agl-aglfn
#
# Format: two semicolon-delimited fields:
#   (1) glyph name--upper/lowercase letters and digits
#   (2) Unicode scalar value--four uppercase hexadecimal digits
#
A;0041
AE;00C6
AEacute;01FC
AEmacron;01E2
AEsmall;F7E6
Aacute;00C1
Aacutesmall;F7E1
Abreve;0102
Abreveacute;1EAE
Abrevecyrillic;04D0
Abrevedotbelow;1EB6
Abrevegrave;1EB0
Abrevehookabove;1EB2
Abrevetilde;1EB4
Acaron;01CD
Acircle;24B6
Acircumflex;00C2
Acircumflexacute;1EA4
Acircumflexdotbelow;1EAC
Acircumflexgrave;1EA6
Acircumflexhookabove;1EA8
Acircumflexsmall;F7E2
Acircumflextilde;1EAA
Acute;F6C9
Acutesmall;F7B4
Acyrillic;0410
Adblgrave;0200
Adieresis;00C4
Adieresiscyrillic;04D2
Adieresismacron;01DE
Adieresissmall;F7E4
Adotbelow;1EA0
Adotmacron;01E0
Agrave;00C0
Agravesmall;F7E0
Ahookabove;1EA2
Aiecyrillic;04D4
Ainvertedbreve;0202
Alpha;0391
Alphatonos;0386
Amacron;0100
Amonospace;FF21
Aogonek;0104
Aring;00C5
Aringacute;01FA
Aringbelow;1E00
Aringsmall;F7E5
Asmall;F761
Atilde;00C3
Atildesmall;F7E3
Aybarmenian;0531
B;0042
Bcircle;24B7
Bdotaccent;1E02
Bdotbelow;1E04
Becyrillic;0411
Benarmenian;0532
Beta;0392
Bhook;0181
Blinebelow;1E06
Bmonospace;FF22
Brevesmall;F6F4
Bsmall;F762
Btopbar;0182
C;0043
Caarmenian;053E
Cacute;0106
Caron;F6CA
Caronsmall;F6F5
Ccaron;010C
Ccedilla;00C7
Ccedillaacute;1E08
Ccedillasmall;F7E7
Ccircle;24B8
Ccircumflex;0108
Cdot;010A
Cdotaccent;010A
Cedillasmall;F7B8
Chaarmenian;0549
Cheabkhasiancyrillic;04BC
Checyrillic;0427
Chedescenderabkhasiancyrillic;04BE
Chedescendercyrillic;04B6
Chedieresiscyrillic;04F4
Cheharmenian;0543
Chekhakassiancyrillic;04CB
Cheverticalstrokecyrillic;04B8
Chi;03A7
Chook;0187
Circumflexsmall;F6F6
Cmonospace;FF23
Coarmenian;0551
Csmall;F763
D;0044
DZ;01F1
DZcaron;01C4
Daarmenian;0534
Dafrican;0189
Dcaron;010E
Dcedilla;1E10
Dcircle;24B9
Dcircumflexbelow;1E12
Dcroat;0110
Ddotaccent;1E0A
Ddotbelow;1E0C
Decyrillic;0414
Deicoptic;03EE
Delta;2206
Deltagreek;0394
Dhook;018A
Dieresis;F6CB
DieresisAcute;F6CC
DieresisGrave;F6CD
Dieresissmall;F7A8
Digammagreek;03DC
Djecyrillic;0402
Dlinebelow;1E0E
Dmonospace;FF24
Dotaccentsmall;F6F7
Dslash;0110
Dsmall;F764
Dtopbar;018B
Dz;01F2
Dzcaron;01C5
Dzeabkhasiancyrillic;04E0
Dzecyrillic;0405
Dzhecyrillic;040F
E;0045
Eacute;00C9
Eacutesmall;F7E9
Ebreve;0114
Ecaron;011A
Ecedillabreve;1E1C
Echarmenian;0535
Ecircle;24BA
Ecircumflex;00CA
Ecircumflexacute;1EBE
Ecircumflexbelow;1E18
Ecircumflexdotbelow;1EC6
Ecircumflexgrave;1EC0
Ecircumflexhookabove;1EC2
Ecircumflexsmall;F7EA
Ecircumflextilde;1EC4
Ecyrillic;0404
Edblgrave;0204
Edieresis;00CB
Edieresissmall;F7EB
Edot;0116
Edotaccent;0116
Edotbelow;1EB8
Efcyrillic;0424
Egrave;00C8
Egravesmall;F7E8
Eharmenian;0537
Ehookabove;1EBA
Eightroman;2167
Einvertedbreve;0206
Eiotifiedcyrillic;0464
Elcyrillic;041B
Elevenroman;216A
Emacron;0112
Emacronacute;1E16
Emacrongrave;1E14
Emcyrillic;041C
Emonospace;FF25
Encyrillic;041D
Endescendercyrillic;04A2
Eng;014A
Enghecyrillic;04A4
Enhookcyrillic;04C7
Eogonek;0118
Eopen;0190
Epsilon;0395
Epsilontonos;0388
Ercyrillic;0420
Ereversed;018E
Ereversedcyrillic;042D
Escyrillic;0421
Esdescendercyrillic;04AA
Esh;01A9
Esmall;F765
Eta;0397
Etarmenian;0538
Etatonos;0389
Eth;00D0
Ethsmall;F7F0
Etilde;1EBC
Etildebelow;1E1A
Euro;20AC
Ezh;01B7
Ezhcaron;01EE
Ezhreversed;01B8
F;0046
Fcircle;24BB
Fdotaccent;1E1E
Feharmenian;0556
Feicoptic;03E4
Fhook;0191
Fitacyrillic;0472
Fiveroman;2164
Fmonospace;FF26
Fourroman;2163
Fsmall;F766
G;0047
GBsquare;3387
Gacute;01F4
Gamma;0393
Gammaafrican;0194
Gangiacoptic;03EA
Gbreve;011E
Gcaron;01E6
Gcedilla;0122
Gcircle;24BC
Gcircumflex;011C
Gcommaaccent;0122
Gdot;0120
Gdotaccent;0120
Gecyrillic;0413
Ghadarmenian;0542
Ghemiddlehookcyrillic;0494
Ghestrokecyrillic;0492
Gheupturncyrillic;0490
Ghook;0193
Gimarmenian;0533
Gjecyrillic;0403
Gmacron;1E20
Gmonospace;FF27
Grave;F6CE
Gravesmall;F760
Gsmall;F767
Gsmallhook;029B
Gstroke;01E4
H;0048
H18533;25CF
H18543;25AA
H18551;25AB
H22073;25A1
HPsquare;33CB
Haabkhasiancyrillic;04A8
Hadescendercyrillic;04B2
Hardsigncyrillic;042A
Hbar;0126
Hbrevebelow;1E2A
Hcedilla;1E28
Hcircle;24BD
Hcircumflex;0124
Hdieresis;1E26
Hdotaccent;1E22
Hdotbelow;1E24
Hmonospace;FF28
Hoarmenian;0540
Horicoptic;03E8
Hsmall;F768
Hungarumlaut;F6CF
Hungarumlautsmall;F6F8
Hzsquare;3390
I;0049
IAcyrillic;042F
IJ;0132
IUcyrillic;042E
Iacute;00CD
Iacutesmall;F7ED
Ibreve;012C
Icaron;01CF
Icircle;24BE
Icircumflex;00CE
Icircumflexsmall;F7EE
Icyrillic;0406
Idblgrave;0208
Idieresis;00CF
Idieresisacute;1E2E
Idieresiscyrillic;04E4
Idieresissmall;F7EF
Idot;0130
Idotaccent;0130
Idotbelow;1ECA
Iebrevecyrillic;04D6
Iecyrillic;0415
Ifraktur;2111
Igrave;00CC
Igravesmall;F7EC
Ihookabove;1EC8
Iicyrillic;0418
Iinvertedbreve;020A
Iishortcyrillic;0419
Imacron;012A
Imacroncyrillic;04E2
Imonospace;FF29
Iniarmenian;053B
Iocyrillic;0401
Iogonek;012E
Iota;0399
Iotaafrican;0196
Iotadieresis;03AA
Iotatonos;038A
Ismall;F769
Istroke;0197
Itilde;0128
Itildebelow;1E2C
Izhitsacyrillic;0474
Izhitsadblgravecyrillic;0476
J;004A
Jaarmenian;0541
Jcircle;24BF
Jcircumflex;0134
Jecyrillic;0408
Jheharmenian;054B
Jmonospace;FF2A
Jsmall;F76A
K;004B
KBsquare;3385
KKsquare;33CD
Kabashkircyrillic;04A0
Kacute;1E30
Kacyrillic;041A
Kadescendercyrillic;049A
Kahookcyrillic;04C3
Kappa;039A
Kastrokecyrillic;049E
Kaverticalstrokecyrillic;049C
Kcaron;01E8
Kcedilla;0136
Kcircle;24C0
Kcommaaccent;0136
Kdotbelow;1E32
Keharmenian;0554
Kenarmenian;053F
Khacyrillic;0425
Kheicoptic;03E6
Khook;0198
Kjecyrillic;040C
Klinebelow;1E34
Kmonospace;FF2B
Koppacyrillic;0480
Koppagreek;03DE
Ksicyrillic;046E
Ksmall;F76B
L;004C
LJ;01C7
LL;F6BF
Lacute;0139
Lambda;039B
Lcaron;013D
Lcedilla;013B
Lcircle;24C1
Lcircumflexbelow;1E3C
Lcommaaccent;013B
Ldot;013F
Ldotaccent;013F
Ldotbelow;1E36
Ldotbelowmacron;1E38
Liwnarmenian;053C
Lj;01C8
Ljecyrillic;0409
Llinebelow;1E3A
Lmonospace;FF2C
Lslash;0141
Lslashsmall;F6F9
Lsmall;F76C
M;004D
MBsquare;3386
Macron;F6D0
Macronsmall;F7AF
Macute;1E3E
Mcircle;24C2
Mdotaccent;1E40
Mdotbelow;1E42
Menarmenian;0544
Mmonospace;FF2D
Msmall;F76D
Mturned;019C
Mu;039C
N;004E
NJ;01CA
Nacute;0143
Ncaron;0147
Ncedilla;0145
Ncircle;24C3
Ncircumflexbelow;1E4A
Ncommaaccent;0145
Ndotaccent;1E44
Ndotbelow;1E46
Nhookleft;019D
Nineroman;2168
Nj;01CB
Njecyrillic;040A
Nlinebelow;1E48
Nmonospace;FF2E
Nowarmenian;0546
Nsmall;F76E
Ntilde;00D1
Ntildesmall;F7F1
Nu;039D
O;004F
OE;0152
OEsmall;F6FA
Oacute;00D3
Oacutesmall;F7F3
Obarredcyrillic;04E8
Obarreddieresiscyrillic;04EA
Obreve;014E
Ocaron;01D1
Ocenteredtilde;019F
Ocircle;24C4
Ocircumflex;00D4
Ocircumflexacute;1ED0
Ocircumflexdotbelow;1ED8
Ocircumflexgrave;1ED2
Ocircumflexhookabove;1ED4
Ocircumflexsmall;F7F4
Ocircumflextilde;1ED6
Ocyrillic;041E
Odblacute;0150
Odblgrave;020C
Odieresis;00D6
Odieresiscyrillic;04E6
Odieresissmall;F7F6
Odotbelow;1ECC
Ogoneksmall;F6FB
Ograve;00D2
Ogravesmall;F7F2
Oharmenian;0555
Ohm;2126
Ohookabove;1ECE
Ohorn;01A0
Ohornacute;1EDA
Ohorndotbelow;1EE2
Ohorngrave;1EDC
Ohornhookabove;1EDE
Ohorntilde;1EE0
Ohungarumlaut;0150
Oi;01A2
Oinvertedbreve;020E
Omacron;014C
Omacronacute;1E52
Omacrongrave;1E50
Omega;2126
Omegacyrillic;0460
Omegagreek;03A9
Omegaroundcyrillic;047A
Omegatitlocyrillic;047C
Omegatonos;038F
Omicron;039F
Omicrontonos;038C
Omonospace;FF2F
Oneroman;2160
Oogonek;01EA
Oogonekmacron;01EC
Oopen;0186
Oslash;00D8
Oslashacute;01FE
Oslashsmall;F7F8
Osmall;F76F
Ostrokeacute;01FE
Otcyrillic;047E
Otilde;00D5
Otildeacute;1E4C
Otildedieresis;1E4E
Otildesmall;F7F5
P;0050
Pacute;1E54
Pcircle;24C5
Pdotaccent;1E56
Pecyrillic;041F
Peharmenian;054A
Pemiddlehookcyrillic;04A6
Phi;03A6
Phook;01A4
Pi;03A0
Piwrarmenian;0553
Pmonospace;FF30
Psi;03A8
Psicyrillic;0470
Psmall;F770
Q;0051
Qcircle;24C6
Qmonospace;FF31
Qsmall;F771
R;0052
Raarmenian;054C
Racute;0154
Rcaron;0158
Rcedilla;0156
Rcircle;24C7
Rcommaaccent;0156
Rdblgrave;0210
Rdotaccent;1E58
Rdotbelow;1E5A
Rdotbelowmacron;1E5C
Reharmenian;0550
Rfraktur;211C
Rho;03A1
Ringsmall;F6FC
Rinvertedbreve;0212
Rlinebelow;1E5E
Rmonospace;FF32
Rsmall;F772
Rsmallinverted;0281
Rsmallinvertedsuperior;02B6
S;0053
SF010000;250C
SF020000;2514
SF030000;2510
SF040000;2518
SF050000;253C
SF060000;252C
SF070000;2534
SF080000;251C
SF090000;2524
SF100000;2500
SF110000;2502
SF190000;2561
SF200000;2562
SF210000;2556
SF220000;2555
SF230000;2563
SF240000;2551
SF250000;2557
SF260000;255D
SF270000;255C
SF280000;255B
SF360000;255E
SF370000;255F
SF380000;255A
SF390000;2554
SF400000;2569
SF410000;2566
SF420000;2560
SF430000;2550
SF440000;256C
SF450000;2567
SF460000;2568
SF470000;2564
SF480000;2565
SF490000;2559
SF500000;2558
SF510000;2552
SF520000;2553
SF530000;256B
SF540000;256A
Sacute;015A
Sacutedotaccent;1E64
Sampigreek;03E0
Scaron;0160
Scarondotaccent;1E66
Scaronsmall;F6FD
Scedilla;015E
Schwa;018F
Schwacyrillic;04D8
Schwadieresiscyrillic;04DA
Scircle;24C8
Scircumflex;015C
Scommaaccent;0218
Sdotaccent;1E60
Sdotbelow;1E62
Sdotbelowdotaccent;1E68
Seharmenian;054D
Sevenroman;2166
Shaarmenian;0547
Shacyrillic;0428
Shchacyrillic;0429
Sheicoptic;03E2
Shhacyrillic;04BA
Shimacoptic;03EC
Sigma;03A3
Sixroman;2165
Smonospace;FF33
Softsigncyrillic;042C
Ssmall;F773
Stigmagreek;03DA
T;0054
Tau;03A4
Tbar;0166
Tcaron;0164
Tcedilla;0162
Tcircle;24C9
Tcircumflexbelow;1E70
Tcommaaccent;0162
Tdotaccent;1E6A
Tdotbelow;1E6C
Tecyrillic;0422
Tedescendercyrillic;04AC
Tenroman;2169
Tetsecyrillic;04B4
Theta;0398
Thook;01AC
Thorn;00DE
Thornsmall;F7FE
Threeroman;2162
Tildesmall;F6FE
Tiwnarmenian;054F
Tlinebelow;1E6E
Tmonospace;FF34
Toarmenian;0539
Tonefive;01BC
Tonesix;0184
Tonetwo;01A7
Tretroflexhook;01AE
Tsecyrillic;0426
Tshecyrillic;040B
Tsmall;F774
Twelveroman;216B
Tworoman;2161
U;0055
Uacute;00DA
Uacutesmall;F7FA
Ubreve;016C
Ucaron;01D3
Ucircle;24CA
Ucircumflex;00DB
Ucircumflexbelow;1E76
Ucircumflexsmall;F7FB
Ucyrillic;0423
Udblacute;0170
Udblgrave;0214
Udieresis;00DC
Udieresisacute;01D7
Udieresisbelow;1E72
Udieresiscaron;01D9
Udieresiscyrillic;04F0
Udieresisgrave;01DB
Udieresismacron;01D5
Udieresissmall;F7FC
Udotbelow;1EE4
Ugrave;00D9
Ugravesmall;F7F9
Uhookabove;1EE6
Uhorn;01AF
Uhornacute;1EE8
Uhorndotbelow;1EF0
Uhorngrave;1EEA
Uhornhookabove;1EEC
Uhorntilde;1EEE
Uhungarumlaut;0170
Uhungarumlautcyrillic;04F2
Uinvertedbreve;0216
Ukcyrillic;0478
Umacron;016A
Umacroncyrillic;04EE
Umacrondieresis;1E7A
Umonospace;FF35
Uogonek;0172
Upsilon;03A5
Upsilon1;03D2
Upsilonacutehooksymbolgreek;03D3
Upsilonafrican;01B1
Upsilondieresis;03AB
Upsilondieresishooksymbolgreek;03D4
Upsilonhooksymbol;03D2
Upsilontonos;038E
Uring;016E
Ushortcyrillic;040E
Usmall;F775
Ustraightcyrillic;04AE
Ustraightstrokecyrillic;04B0
Utilde;0168
Utildeacute;1E78
Utildebelow;1E74
V;0056
Vcircle;24CB
Vdotbelow;1E7E
Vecyrillic;0412
Vewarmenian;054E
Vhook;01B2
Vmonospace;FF36
Voarmenian;0548
Vsmall;F776
Vtilde;1E7C
W;0057
Wacute;1E82
Wcircle;24CC
Wcircumflex;0174
Wdieresis;1E84
Wdotaccent;1E86
Wdotbelow;1E88
Wgrave;1E80
Wmonospace;FF37
Wsmall;F777
X;0058
Xcircle;24CD
Xdieresis;1E8C
Xdotaccent;1E8A
Xeharmenian;053D
Xi;039E
Xmonospace;FF38
Xsmall;F778
Y;0059
Yacute;00DD
Yacutesmall;F7FD
Yatcyrillic;0462
Ycircle;24CE
Ycircumflex;0176
Ydieresis;0178
Ydieresissmall;F7FF
Ydotaccent;1E8E
Ydotbelow;1EF4
Yericyrillic;042B
Yerudieresiscyrillic;04F8
Ygrave;1EF2
Yhook;01B3
Yhookabove;1EF6
Yiarmenian;0545
Yicyrillic;0407
Yiwnarmenian;0552
Ymonospace;FF39
Ysmall;F779
Ytilde;1EF8
Yusbigcyrillic;046A
Yusbigiotifiedcyrillic;046C
Yuslittlecyrillic;0466
Yuslittleiotifiedcyrillic;0468
Z;005A
Zaarmenian;0536
Zacute;0179
Zcaron;017D
Zcaronsmall;F6FF
Zcircle;24CF
Zcircumflex;1E90
Zdot;017B
Zdotaccent;017B
Zdotbelow;1E92
Zecyrillic;0417
Zedescendercyrillic;0498
Zedieresiscyrillic;04DE
Zeta;0396
Zhearmenian;053A
Zhebrevecyrillic;04C1
Zhecyrillic;0416
Zhedescendercyrillic;0496
Zhedieresiscyrillic;04DC
Zlinebelow;1E94
Zmonospace;FF3A
Zsmall;F77A
Zstroke;01B5
a;0061
aabengali;0986
aacute;00E1
aadeva;0906
aagujarati;0A86
aagurmukhi;0A06
aamatragurmukhi;0A3E
aarusquare;3303
aavowelsignbengali;09BE
aavowelsigndeva;093E
aavowelsigngujarati;0ABE
abbreviationmarkarmenian;055F
abbreviationsigndeva;0970
abengali;0985
abopomofo;311A
abreve;0103
abreveacute;1EAF
abrevecyrillic;04D1
abrevedotbelow;1EB7
abrevegrave;1EB1
abrevehookabove;1EB3
abrevetilde;1EB5
acaron;01CE
acircle;24D0
acircumflex;00E2
acircumflexacute;1EA5
acircumflexdotbelow;1EAD
acircumflexgrave;1EA7
acircumflexhookabove;1EA9
acircumflextilde;1EAB
acute;00B4
acutebelowcmb;0317
acutecmb;0301
acutecomb;0301
acutedeva;0954
acutelowmod;02CF
acutetonecmb;0341
acyrillic;0430
adblgrave;0201
addakgurmukhi;0A71
adeva;0905
adieresis;00E4
adieresiscyrillic;04D3
adieresismacron;01DF
adotbelow;1EA1
adotmacron;01E1
ae;00E6
aeacute;01FD
aekorean;3150
aemacron;01E3
afii00208;2015
afii08941;20A4
afii10017;0410
afii10018;0411
afii10019;0412
afii10020;0413
afii10021;0414
afii10022;0415
afii10023;0401
afii10024;0416
afii10025;0417
afii10026;0418
afii10027;0419
afii10028;041A
afii10029;041B
afii10030;041C
afii10031;041D
afii10032;041E
afii10033;041F
afii10034;0420
afii10035;0421
afii10036;0422
afii10037;0423
afii10038;0424
afii10039;0425
afii10040;0426
afii10041;0427
afii10042;0428
afii10043;0429
afii10044;042A
afii10045;042B
afii10046;042C
afii10047;042D
afii10048;042E
afii10049;042F
afii10050;0490
afii10051;0402
afii10052;0403
afii10053;0404
afii10054;0405
afii10055;0406
afii10056;0407
afii10057;0408
afii10058;0409
afii10059;040A
afii10060;040B
afii10061;040C
afii10062;040E
afii10063;F6C4
afii10064;F6C5
afii10065;0430
afii10066;0431
afii10067;0432
afii10068;0433
afii10069;0434
afii10070;0435
afii10071;0451
afii10072;0436
afii10073;0437
afii10074;0438
afii10075;0439
afii10076;043A
afii10077;043B
afii10078;043C
afii10079;043D
afii10080;043E
afii10081;043F
afii10082;0440
afii10083;0441
afii10084;0442
afii10085;0443
afii10086;0444
afii10087;0445
afii10088;0446
afii10089;0447
afii10090;0448
afii10091;0449
afii10092;044A
afii10093;044B
afii10094;044C
afii10095;044D
afii10096;044E
afii10097;044F
afii10098;0491
afii10099;0452
afii10100;0453
afii10101;0454
afii10102;0455
afii10103;0456
afii10104;0457
afii10105;0458
afii10106;0459
afii10107;045A
afii10108;045B
afii10109;045C
afii10110;045E
afii10145;040F
afii10146;0462
afii10147;0472
afii10148;0474
afii10192;F6C6
afii10193;045F
afii10194;0463
afii10195;0473
afii10196;0475
afii10831;F6C7
afii10832;F6C8
afii10846;04D9
afii299;200E
afii300;200F
afii301;200D
afii57381;066A
afii57388;060C
afii57392;0660
afii57393;0661
afii57394;0662
afii57395;0663
afii57396;0664
afii57397;0665
afii57398;0666
afii57399;0667
afii57400;0668
afii57401;0669
afii57403;061B
afii57407;061F
afii57409;0621
afii57410;0622
afii57411;0623
afii57412;0624
afii57413;0625
afii57414;0626
afii57415;0627
afii57416;0628
afii57417;0629
afii57418;062A
afii57419;062B
afii57420;062C
afii57421;062D
afii57422;062E
afii57423;062F
afii57424;0630
afii57425;0631
afii57426;0632
afii57427;0633
afii57428;0634
afii57429;0635
afii57430;0636
afii57431;0637
afii57432;0638
afii57433;0639
afii57434;063A
afii57440;0640
afii57441;0641
afii57442;0642
afii57443;0643
afii57444;0644
afii57445;0645
afii57446;0646
afii57448;0648
afii57449;0649
afii57450;064A
afii57451;064B
afii57452;064C
afii57453;064D
afii57454;064E
afii57455;064F
afii57456;0650
afii57457;0651
afii57458;0652
afii57470;0647
afii57505;06A4
afii57506;067E
afii57507;0686
afii57508;0698
afii57509;06AF
afii57511;0679
afii57512;0688
afii57513;0691
afii57514;06BA
afii57519;06D2
afii57534;06D5
afii57636;20AA
afii57645;05BE
afii57658;05C3
afii57664;05D0
afii57665;05D1
afii57666;05D2
afii57667;05D3
afii57668;05D4
afii57669;05D5
afii57670;05D6
afii57671;05D7
afii57672;05D8
afii57673;05D9
afii57674;05DA
afii57675;05DB
afii57676;05DC
afii57677;05DD
afii57678;05DE
afii57679;05DF
afii57680;05E0
afii57681;05E1
afii57682;05E2
afii57683;05E3
afii57684;05E4
afii57685;05E5
afii57686;05E6
afii57687;05E7
afii57688;05E8
afii57689;05E9
afii57690;05EA
afii57694;FB2A
afii57695;FB2B
afii57700;FB4B
afii57705;FB1F
afii57716;05F0
afii57717;05F1
afii57718;05F2
afii57723;FB35
afii57793;05B4
afii57794;05B5
afii57795;05B6
afii57796;05BB
afii57797;05B8
afii57798;05B7
afii57799;05B0
afii57800;05B2
afii57801;05B1
afii57802;05B3
afii57803;05C2
afii57804;05C1
afii57806;05B9
afii57807;05BC
afii57839;05BD
afii57841;05BF
afii57842;05C0
afii57929;02BC
afii61248;2105
afii61289;2113
afii61352;2116
afii61573;202C
afii61574;202D
afii61575;202E
afii61664;200C
afii63167;066D
afii64937;02BD
agrave;00E0
agujarati;0A85
agurmukhi;0A05
ahiragana;3042
ahookabove;1EA3
aibengali;0990
aibopomofo;311E
aideva;0910
aiecyrillic;04D5
aigujarati;0A90
aigurmukhi;0A10
aimatragurmukhi;0A48
ainarabic;0639
ainfinalarabic;FECA
aininitialarabic;FECB
ainmedialarabic;FECC
ainvertedbreve;0203
aivowelsignbengali;09C8
aivowelsigndeva;0948
aivowelsigngujarati;0AC8
akatakana;30A2
akatakanahalfwidth;FF71
akorean;314F
alef;05D0
alefarabic;0627
alefdageshhebrew;FB30
aleffinalarabic;FE8E
alefhamzaabovearabic;0623
alefhamzaabovefinalarabic;FE84
alefhamzabelowarabic;0625
alefhamzabelowfinalarabic;FE88
alefhebrew;05D0
aleflamedhebrew;FB4F
alefmaddaabovearabic;0622
alefmaddaabovefinalarabic;FE82
alefmaksuraarabic;0649
alefmaksurafinalarabic;FEF0
alefmaksurainitialarabic;FEF3
alefmaksuramedialarabic;FEF4
alefpatahhebrew;FB2E
alefqamatshebrew;FB2F
aleph;2135
allequal;224C
alpha;03B1
alphatonos;03AC
amacron;0101
amonospace;FF41
ampersand;0026
ampersandmonospace;FF06
ampersandsmall;F726
amsquare;33C2
anbopomofo;3122
angbopomofo;3124
angkhankhuthai;0E5A
angle;2220
anglebracketleft;3008
anglebracketleftvertical;FE3F
anglebracketright;3009
anglebracketrightvertical;FE40
angleleft;2329
angleright;232A
angstrom;212B
anoteleia;0387
anudattadeva;0952
anusvarabengali;0982
anusvaradeva;0902
anusvaragujarati;0A82
aogonek;0105
apaatosquare;3300
aparen;249C
apostrophearmenian;055A
apostrophemod;02BC
apple;F8FF
approaches;2250
approxequal;2248
approxequalorimage;2252
approximatelyequal;2245
araeaekorean;318E
araeakorean;318D
arc;2312
arighthalfring;1E9A
aring;00E5
aringacute;01FB
aringbelow;1E01
arrowboth;2194
arrowdashdown;21E3
arrowdashleft;21E0
arrowdashright;21E2
arrowdashup;21E1
arrowdblboth;21D4
arrowdbldown;21D3
arrowdblleft;21D0
arrowdblright;21D2
arrowdblup;21D1
arrowdown;2193
arrowdownleft;2199
arrowdownright;2198
arrowdownwhite;21E9
arrowheaddownmod;02C5
arrowheadleftmod;02C2
arrowheadrightmod;02C3
arrowheadupmod;02C4
arrowhorizex;F8E7
arrowleft;2190
arrowleftdbl;21D0
arrowleftdblstroke;21CD
arrowleftoverright;21C6
arrowleftwhite;21E6
arrowright;2192
arrowrightdblstroke;21CF
arrowrightheavy;279E
arrowrightoverleft;21C4
arrowrightwhite;21E8
arrowtableft;21E4
arrowtabright;21E5
arrowup;2191
arrowupdn;2195
arrowupdnbse;21A8
arrowupdownbase;21A8
arrowupleft;2196
arrowupleftofdown;21C5
arrowupright;2197
arrowupwhite;21E7
arrowvertex;F8E6
asciicircum;005E
asciicircummonospace;FF3E
asciitilde;007E
asciitildemonospace;FF5E
ascript;0251
ascriptturned;0252
asmallhiragana;3041
asmallkatakana;30A1
asmallkatakanahalfwidth;FF67
asterisk;002A
asteriskaltonearabic;066D
asteriskarabic;066D
asteriskmath;2217
asteriskmonospace;FF0A
asterisksmall;FE61
asterism;2042
asuperior;F6E9
asymptoticallyequal;2243
at;0040
atilde;00E3
atmonospace;FF20
atsmall;FE6B
aturned;0250
aubengali;0994
aubopomofo;3120
audeva;0914
augujarati;0A94
augurmukhi;0A14
aulengthmarkbengali;09D7
aumatragurmukhi;0A4C
auvowelsignbengali;09CC
auvowelsigndeva;094C
auvowelsigngujarati;0ACC
avagrahadeva;093D
aybarmenian;0561
ayin;05E2
ayinaltonehebrew;FB20
ayinhebrew;05E2
b;0062
babengali;09AC
backslash;005C
backslashmonospace;FF3C
badeva;092C
bagujarati;0AAC
bagurmukhi;0A2C
bahiragana;3070
bahtthai;0E3F
bakatakana;30D0
bar;007C
barmonospace;FF5C
bbopomofo;3105
bcircle;24D1
bdotaccent;1E03
bdotbelow;1E05
beamedsixteenthnotes;266C
because;2235
becyrillic;0431
beharabic;0628
behfinalarabic;FE90
behinitialarabic;FE91
behiragana;3079
behmedialarabic;FE92
behmeeminitialarabic;FC9F
behmeemisolatedarabic;FC08
behnoonfinalarabic;FC6D
bekatakana;30D9
benarmenian;0562
bet;05D1
beta;03B2
betasymbolgreek;03D0
betdagesh;FB31
betdageshhebrew;FB31
bethebrew;05D1
betrafehebrew;FB4C
bhabengali;09AD
bhadeva;092D
bhagujarati;0AAD
bhagurmukhi;0A2D
bhook;0253
bihiragana;3073
bikatakana;30D3
bilabialclick;0298
bindigurmukhi;0A02
birusquare;3331
blackcircle;25CF
blackdiamond;25C6
blackdownpointingtriangle;25BC
blackleftpointingpointer;25C4
blackleftpointingtriangle;25C0
blacklenticularbracketleft;3010
blacklenticularbracketleftvertical;FE3B
blacklenticularbracketright;3011
blacklenticularbracketrightvertical;FE3C
blacklowerlefttriangle;25E3
blacklowerrighttriangle;25E2
blackrectangle;25AC
blackrightpointingpointer;25BA
blackrightpointingtriangle;25B6
blacksmallsquare;25AA
blacksmilingface;263B
blacksquare;25A0
blackstar;2605
blackupperlefttriangle;25E4
blackupperrighttriangle;25E5
blackuppointingsmalltriangle;25B4
blackuppointingtriangle;25B2
blank;2423
blinebelow;1E07
block;2588
bmonospace;FF42
bobaimaithai;0E1A
bohiragana;307C
bokatakana;30DC
bparen;249D
bqsquare;33C3
braceex;F8F4
braceleft;007B
braceleftbt;F8F3
braceleftmid;F8F2
braceleftmonospace;FF5B
braceleftsmall;FE5B
bracelefttp;F8F1
braceleftvertical;FE37
braceright;007D
bracerightbt;F8FE
bracerightmid;F8FD
bracerightmonospace;FF5D
bracerightsmall;FE5C
bracerighttp;F8FC
bracerightvertical;FE38
bracketleft;005B
bracketleftbt;F8F0
bracketleftex;F8EF
bracketleftmonospace;FF3B
bracketlefttp;F8EE
bracketright;005D
bracketrightbt;F8FB
bracketrightex;F8FA
bracketrightmonospace;FF3D
bracketrighttp;F8F9
breve;02D8
brevebelowcmb;032E
brevecmb;0306
breveinvertedbelowcmb;032F
breveinvertedcmb;0311
breveinverteddoublecmb;0361
bridgebelowcmb;032A
bridgeinvertedbelowcmb;033A
brokenbar;00A6
bstroke;0180
bsuperior;F6EA
btopbar;0183
buhiragana;3076
bukatakana;30D6
bullet;2022
bulletinverse;25D8
bulletoperator;2219
bullseye;25CE
c;0063
caarmenian;056E
cabengali;099A
cacute;0107
cadeva;091A
cagujarati;0A9A
cagurmukhi;0A1A
calsquare;3388
candrabindubengali;0981
candrabinducmb;0310
candrabindudeva;0901
candrabindugujarati;0A81
capslock;21EA
careof;2105
caron;02C7
caronbelowcmb;032C
caroncmb;030C
carriagereturn;21B5
cbopomofo;3118
ccaron;010D
ccedilla;00E7
ccedillaacute;1E09
ccircle;24D2
ccircumflex;0109
ccurl;0255
cdot;010B
cdotaccent;010B
cdsquare;33C5
cedilla;00B8
cedillacmb;0327
cent;00A2
centigrade;2103
centinferior;F6DF
centmonospace;FFE0
centoldstyle;F7A2
centsuperior;F6E0
chaarmenian;0579
chabengali;099B
chadeva;091B
chagujarati;0A9B
chagurmukhi;0A1B
chbopomofo;3114
cheabkhasiancyrillic;04BD
checkmark;2713
checyrillic;0447
chedescenderabkhasiancyrillic;04BF
chedescendercyrillic;04B7
chedieresiscyrillic;04F5
cheharmenian;0573
chekhakassiancyrillic;04CC
cheverticalstrokecyrillic;04B9
chi;03C7
chieuchacirclekorean;3277
chieuchaparenkorean;3217
chieuchcirclekorean;3269
chieuchkorean;314A
chieuchparenkorean;3209
chochangthai;0E0A
chochanthai;0E08
chochingthai;0E09
chochoethai;0E0C
chook;0188
cieucacirclekorean;3276
cieucaparenkorean;3216
cieuccirclekorean;3268
cieuckorean;3148
cieucparenkorean;3208
cieucuparenkorean;321C
circle;25CB
circlemultiply;2297
circleot;2299
circleplus;2295
circlepostalmark;3036
circlewithlefthalfblack;25D0
circlewithrighthalfblack;25D1
circumflex;02C6
circumflexbelowcmb;032D
circumflexcmb;0302
clear;2327
clickalveolar;01C2
clickdental;01C0
clicklateral;01C1
clickretroflex;01C3
club;2663
clubsuitblack;2663
clubsuitwhite;2667
cmcubedsquare;33A4
cmonospace;FF43
cmsquaredsquare;33A0
coarmenian;0581
colon;003A
colonmonetary;20A1
colonmonospace;FF1A
colonsign;20A1
colonsmall;FE55
colontriangularhalfmod;02D1
colontriangularmod;02D0
comma;002C
commaabovecmb;0313
commaaboverightcmb;0315
commaaccent;F6C3
commaarabic;060C
commaarmenian;055D
commainferior;F6E1
commamonospace;FF0C
commareversedabovecmb;0314
commareversedmod;02BD
commasmall;FE50
commasuperior;F6E2
commaturnedabovecmb;0312
commaturnedmod;02BB
compass;263C
congruent;2245
contourintegral;222E
control;2303
controlACK;0006
controlBEL;0007
controlBS;0008
controlCAN;0018
controlCR;000D
controlDC1;0011
controlDC2;0012
controlDC3;0013
controlDC4;0014
controlDEL;007F
controlDLE;0010
controlEM;0019
controlENQ;0005
controlEOT;0004
controlESC;001B
controlETB;0017
controlETX;0003
controlFF;000C
controlFS;001C
controlGS;001D
controlHT;0009
controlLF;000A
controlNAK;0015
controlRS;001E
controlSI;000F
controlSO;000E
controlSOT;0002
controlSTX;0001
controlSUB;001A
controlSYN;0016
controlUS;001F
controlVT;000B
copyright;00A9
copyrightsans;F8E9
copyrightserif;F6D9
cornerbracketleft;300C
cornerbracketlefthalfwidth;FF62
cornerbracketleftvertical;FE41
cornerbracketright;300D
cornerbracketrighthalfwidth;FF63
cornerbracketrightvertical;FE42
corporationsquare;337F
cosquare;33C7
coverkgsquare;33C6
cparen;249E
cruzeiro;20A2
cstretched;0297
curlyand;22CF
curlyor;22CE
currency;00A4
cyrBreve;F6D1
cyrFlex;F6D2
cyrbreve;F6D4
cyrflex;F6D5
d;0064
daarmenian;0564
dabengali;09A6
dadarabic;0636
dadeva;0926
dadfinalarabic;FEBE
dadinitialarabic;FEBF
dadmedialarabic;FEC0
dagesh;05BC
dageshhebrew;05BC
dagger;2020
daggerdbl;2021
dagujarati;0AA6
dagurmukhi;0A26
dahiragana;3060
dakatakana;30C0
dalarabic;062F
dalet;05D3
daletdagesh;FB33
daletdageshhebrew;FB33
dalethatafpatah;05D3 05B2
dalethatafpatahhebrew;05D3 05B2
dalethatafsegol;05D3 05B1
dalethatafsegolhebrew;05D3 05B1
dalethebrew;05D3
dalethiriq;05D3 05B4
dalethiriqhebrew;05D3 05B4
daletholam;05D3 05B9
daletholamhebrew;05D3 05B9
daletpatah;05D3 05B7
daletpatahhebrew;05D3 05B7
daletqamats;05D3 05B8
daletqamatshebrew;05D3 05B8
daletqubuts;05D3 05BB
daletqubutshebrew;05D3 05BB
daletsegol;05D3 05B6
daletsegolhebrew;05D3 05B6
daletsheva;05D3 05B0
daletshevahebrew;05D3 05B0
dalettsere;05D3 05B5
dalettserehebrew;05D3 05B5
dalfinalarabic;FEAA
dammaarabic;064F
dammalowarabic;064F
dammatanaltonearabic;064C
dammatanarabic;064C
danda;0964
dargahebrew;05A7
dargalefthebrew;05A7
dasiapneumatacyrilliccmb;0485
dblGrave;F6D3
dblanglebracketleft;300A
dblanglebracketleftvertical;FE3D
dblanglebracketright;300B
dblanglebracketrightvertical;FE3E
dblarchinvertedbelowcmb;032B
dblarrowleft;21D4
dblarrowright;21D2
dbldanda;0965
dblgrave;F6D6
dblgravecmb;030F
dblintegral;222C
dbllowline;2017
dbllowlinecmb;0333
dbloverlinecmb;033F
dblprimemod;02BA
dblverticalbar;2016
dblverticallineabovecmb;030E
dbopomofo;3109
dbsquare;33C8
dcaron;010F
dcedilla;1E11
dcircle;24D3
dcircumflexbelow;1E13
dcroat;0111
ddabengali;09A1
ddadeva;0921
ddagujarati;0AA1
ddagurmukhi;0A21
ddalarabic;0688
ddalfinalarabic;FB89
dddhadeva;095C
ddhabengali;09A2
ddhadeva;0922
ddhagujarati;0AA2
ddhagurmukhi;0A22
ddotaccent;1E0B
ddotbelow;1E0D
decimalseparatorarabic;066B
decimalseparatorpersian;066B
decyrillic;0434
degree;00B0
dehihebrew;05AD
dehiragana;3067
deicoptic;03EF
dekatakana;30C7
deleteleft;232B
deleteright;2326
delta;03B4
deltaturned;018D
denominatorminusonenumeratorbengali;09F8
dezh;02A4
dhabengali;09A7
dhadeva;0927
dhagujarati;0AA7
dhagurmukhi;0A27
dhook;0257
dialytikatonos;0385
dialytikatonoscmb;0344
diamond;2666
diamondsuitwhite;2662
dieresis;00A8
dieresisacute;F6D7
dieresisbelowcmb;0324
dieresiscmb;0308
dieresisgrave;F6D8
dieresistonos;0385
dihiragana;3062
dikatakana;30C2
dittomark;3003
divide;00F7
divides;2223
divisionslash;2215
djecyrillic;0452
dkshade;2593
dlinebelow;1E0F
dlsquare;3397
dmacron;0111
dmonospace;FF44
dnblock;2584
dochadathai;0E0E
dodekthai;0E14
dohiragana;3069
dokatakana;30C9
dollar;0024
dollarinferior;F6E3
dollarmonospace;FF04
dollaroldstyle;F724
dollarsmall;FE69
dollarsuperior;F6E4
dong;20AB
dorusquare;3326
dotaccent;02D9
dotaccentcmb;0307
dotbelowcmb;0323
dotbelowcomb;0323
dotkatakana;30FB
dotlessi;0131
dotlessj;F6BE
dotlessjstrokehook;0284
dotmath;22C5
dottedcircle;25CC
doubleyodpatah;FB1F
doubleyodpatahhebrew;FB1F
downtackbelowcmb;031E
downtackmod;02D5
dparen;249F
dsuperior;F6EB
dtail;0256
dtopbar;018C
duhiragana;3065
dukatakana;30C5
dz;01F3
dzaltone;02A3
dzcaron;01C6
dzcurl;02A5
dzeabkhasiancyrillic;04E1
dzecyrillic;0455
dzhecyrillic;045F
e;0065
eacute;00E9
earth;2641
ebengali;098F
ebopomofo;311C
ebreve;0115
ecandradeva;090D
ecandragujarati;0A8D
ecandravowelsigndeva;0945
ecandravowelsigngujarati;0AC5
ecaron;011B
ecedillabreve;1E1D
echarmenian;0565
echyiwnarmenian;0587
ecircle;24D4
ecircumflex;00EA
ecircumflexacute;1EBF
ecircumflexbelow;1E19
ecircumflexdotbelow;1EC7
ecircumflexgrave;1EC1
ecircumflexhookabove;1EC3
ecircumflextilde;1EC5
ecyrillic;0454
edblgrave;0205
edeva;090F
edieresis;00EB
edot;0117
edotaccent;0117
edotbelow;1EB9
eegurmukhi;0A0F
eematragurmukhi;0A47
efcyrillic;0444
egrave;00E8
egujarati;0A8F
eharmenian;0567
ehbopomofo;311D
ehiragana;3048
ehookabove;1EBB
eibopomofo;311F
eight;0038
eightarabic;0668
eightbengali;09EE
eightcircle;2467
eightcircleinversesansserif;2791
eightdeva;096E
eighteencircle;2471
eighteenparen;2485
eighteenperiod;2499
eightgujarati;0AEE
eightgurmukhi;0A6E
eighthackarabic;0668
eighthangzhou;3028
eighthnotebeamed;266B
eightideographicparen;3227
eightinferior;2088
eightmonospace;FF18
eightoldstyle;F738
eightparen;247B
eightperiod;248F
eightpersian;06F8
eightroman;2177
eightsuperior;2078
eightthai;0E58
einvertedbreve;0207
eiotifiedcyrillic;0465
ekatakana;30A8
ekatakanahalfwidth;FF74
ekonkargurmukhi;0A74
ekorean;3154
elcyrillic;043B
element;2208
elevencircle;246A
elevenparen;247E
elevenperiod;2492
elevenroman;217A
ellipsis;2026
ellipsisvertical;22EE
emacron;0113
emacronacute;1E17
emacrongrave;1E15
emcyrillic;043C
emdash;2014
emdashvertical;FE31
emonospace;FF45
emphasismarkarmenian;055B
emptyset;2205
enbopomofo;3123
encyrillic;043D
endash;2013
endashvertical;FE32
endescendercyrillic;04A3
eng;014B
engbopomofo;3125
enghecyrillic;04A5
enhookcyrillic;04C8
enspace;2002
eogonek;0119
eokorean;3153
eopen;025B
eopenclosed;029A
eopenreversed;025C
eopenreversedclosed;025E
eopenreversedhook;025D
eparen;24A0
epsilon;03B5
epsilontonos;03AD
equal;003D
equalmonospace;FF1D
equalsmall;FE66
equalsuperior;207C
equivalence;2261
erbopomofo;3126
ercyrillic;0440
ereversed;0258
ereversedcyrillic;044D
escyrillic;0441
esdescendercyrillic;04AB
esh;0283
eshcurl;0286
eshortdeva;090E
eshortvowelsigndeva;0946
eshreversedloop;01AA
eshsquatreversed;0285
esmallhiragana;3047
esmallkatakana;30A7
esmallkatakanahalfwidth;FF6A
estimated;212E
esuperior;F6EC
eta;03B7
etarmenian;0568
etatonos;03AE
eth;00F0
etilde;1EBD
etildebelow;1E1B
etnahtafoukhhebrew;0591
etnahtafoukhlefthebrew;0591
etnahtahebrew;0591
etnahtalefthebrew;0591
eturned;01DD
eukorean;3161
euro;20AC
evowelsignbengali;09C7
evowelsigndeva;0947
evowelsigngujarati;0AC7
exclam;0021
exclamarmenian;055C
exclamdbl;203C
exclamdown;00A1
exclamdownsmall;F7A1
exclammonospace;FF01
exclamsmall;F721
existential;2203
ezh;0292
ezhcaron;01EF
ezhcurl;0293
ezhreversed;01B9
ezhtail;01BA
f;0066
fadeva;095E
fagurmukhi;0A5E
fahrenheit;2109
fathaarabic;064E
fathalowarabic;064E
fathatanarabic;064B
fbopomofo;3108
fcircle;24D5
fdotaccent;1E1F
feharabic;0641
feharmenian;0586
fehfinalarabic;FED2
fehinitialarabic;FED3
fehmedialarabic;FED4
feicoptic;03E5
female;2640
ff;FB00
ffi;FB03
ffl;FB04
fi;FB01
fifteencircle;246E
fifteenparen;2482
fifteenperiod;2496
figuredash;2012
filledbox;25A0
filledrect;25AC
finalkaf;05DA
finalkafdagesh;FB3A
finalkafdageshhebrew;FB3A
finalkafhebrew;05DA
finalkafqamats;05DA 05B8
finalkafqamatshebrew;05DA 05B8
finalkafsheva;05DA 05B0
finalkafshevahebrew;05DA 05B0
finalmem;05DD
finalmemhebrew;05DD
finalnun;05DF
finalnunhebrew;05DF
finalpe;05E3
finalpehebrew;05E3
finaltsadi;05E5
finaltsadihebrew;05E5
firsttonechinese;02C9
fisheye;25C9
fitacyrillic;0473
five;0035
fivearabic;0665
fivebengali;09EB
fivecircle;2464
fivecircleinversesansserif;278E
fivedeva;096B
fiveeighths;215D
fivegujarati;0AEB
fivegurmukhi;0A6B
fivehackarabic;0665
fivehangzhou;3025
fiveideographicparen;3224
fiveinferior;2085
fivemonospace;FF15
fiveoldstyle;F735
fiveparen;2478
fiveperiod;248C
fivepersian;06F5
fiveroman;2174
fivesuperior;2075
fivethai;0E55
fl;FB02
florin;0192
fmonospace;FF46
fmsquare;3399
fofanthai;0E1F
fofathai;0E1D
fongmanthai;0E4F
forall;2200
four;0034
fourarabic;0664
fourbengali;09EA
fourcircle;2463
fourcircleinversesansserif;278D
fourdeva;096A
fourgujarati;0AEA
fourgurmukhi;0A6A
fourhackarabic;0664
fourhangzhou;3024
fourideographicparen;3223
fourinferior;2084
fourmonospace;FF14
fournumeratorbengali;09F7
fouroldstyle;F734
fourparen;2477
fourperiod;248B
fourpersian;06F4
fourroman;2173
foursuperior;2074
fourteencircle;246D
fourteenparen;2481
fourteenperiod;2495
fourthai;0E54
fourthtonechinese;02CB
fparen;24A1
fraction;2044
franc;20A3
g;0067
gabengali;0997
gacute;01F5
gadeva;0917
gafarabic;06AF
gaffinalarabic;FB93
gafinitialarabic;FB94
gafmedialarabic;FB95
gagujarati;0A97
gagurmukhi;0A17
gahiragana;304C
gakatakana;30AC
gamma;03B3
gammalatinsmall;0263
gammasuperior;02E0
gangiacoptic;03EB
gbopomofo;310D
gbreve;011F
gcaron;01E7
gcedilla;0123
gcircle;24D6
gcircumflex;011D
gcommaaccent;0123
gdot;0121
gdotaccent;0121
gecyrillic;0433
gehiragana;3052
gekatakana;30B2
geometricallyequal;2251
gereshaccenthebrew;059C
gereshhebrew;05F3
gereshmuqdamhebrew;059D
germandbls;00DF
gershayimaccenthebrew;059E
gershayimhebrew;05F4
getamark;3013
ghabengali;0998
ghadarmenian;0572
ghadeva;0918
ghagujarati;0A98
ghagurmukhi;0A18
ghainarabic;063A
ghainfinalarabic;FECE
ghaininitialarabic;FECF
ghainmedialarabic;FED0
ghemiddlehookcyrillic;0495
ghestrokecyrillic;0493
gheupturncyrillic;0491
ghhadeva;095A
ghhagurmukhi;0A5A
ghook;0260
ghzsquare;3393
gihiragana;304E
gikatakana;30AE
gimarmenian;0563
gimel;05D2
gimeldagesh;FB32
gimeldageshhebrew;FB32
gimelhebrew;05D2
gjecyrillic;0453
glottalinvertedstroke;01BE
glottalstop;0294
glottalstopinverted;0296
glottalstopmod;02C0
glottalstopreversed;0295
glottalstopreversedmod;02C1
glottalstopreversedsuperior;02E4
glottalstopstroke;02A1
glottalstopstrokereversed;02A2
gmacron;1E21
gmonospace;FF47
gohiragana;3054
gokatakana;30B4
gparen;24A2
gpasquare;33AC
gradient;2207
grave;0060
gravebelowcmb;0316
gravecmb;0300
gravecomb;0300
gravedeva;0953
gravelowmod;02CE
gravemonospace;FF40
gravetonecmb;0340
greater;003E
greaterequal;2265
greaterequalorless;22DB
greatermonospace;FF1E
greaterorequivalent;2273
greaterorless;2277
greateroverequal;2267
greatersmall;FE65
gscript;0261
gstroke;01E5
guhiragana;3050
guillemotleft;00AB
guillemotright;00BB
guilsinglleft;2039
guilsinglright;203A
gukatakana;30B0
guramusquare;3318
gysquare;33C9
h;0068
haabkhasiancyrillic;04A9
haaltonearabic;06C1
habengali;09B9
hadescendercyrillic;04B3
hadeva;0939
hagujarati;0AB9
hagurmukhi;0A39
haharabic;062D
hahfinalarabic;FEA2
hahinitialarabic;FEA3
hahiragana;306F
hahmedialarabic;FEA4
haitusquare;332A
hakatakana;30CF
hakatakanahalfwidth;FF8A
halantgurmukhi;0A4D
hamzaarabic;0621
hamzadammaarabic;0621 064F
hamzadammatanarabic;0621 064C
hamzafathaarabic;0621 064E
hamzafathatanarabic;0621 064B
hamzalowarabic;0621
hamzalowkasraarabic;0621 0650
hamzalowkasratanarabic;0621 064D
hamzasukunarabic;0621 0652
hangulfiller;3164
hardsigncyrillic;044A
harpoonleftbarbup;21BC
harpoonrightbarbup;21C0
hasquare;33CA
hatafpatah;05B2
hatafpatah16;05B2
hatafpatah23;05B2
hatafpatah2f;05B2
hatafpatahhebrew;05B2
hatafpatahnarrowhebrew;05B2
hatafpatahquarterhebrew;05B2
hatafpatahwidehebrew;05B2
hatafqamats;05B3
hatafqamats1b;05B3
hatafqamats28;05B3
hatafqamats34;05B3
hatafqamatshebrew;05B3
hatafqamatsnarrowhebrew;05B3
hatafqamatsquarterhebrew;05B3
hatafqamatswidehebrew;05B3
hatafsegol;05B1
hatafsegol17;05B1
hatafsegol24;05B1
hatafsegol30;05B1
hatafsegolhebrew;05B1
hatafsegolnarrowhebrew;05B1
hatafsegolquarterhebrew;05B1
hatafsegolwidehebrew;05B1
hbar;0127
hbopomofo;310F
hbrevebelow;1E2B
hcedilla;1E29
hcircle;24D7
hcircumflex;0125
hdieresis;1E27
hdotaccent;1E23
hdotbelow;1E25
he;05D4
heart;2665
heartsuitblack;2665
heartsuitwhite;2661
hedagesh;FB34
hedageshhebrew;FB34
hehaltonearabic;06C1
heharabic;0647
hehebrew;05D4
hehfinalaltonearabic;FBA7
hehfinalalttwoarabic;FEEA
hehfinalarabic;FEEA
hehhamzaabovefinalarabic;FBA5
hehhamzaaboveisolatedarabic;FBA4
hehinitialaltonearabic;FBA8
hehinitialarabic;FEEB
hehiragana;3078
hehmedialaltonearabic;FBA9
hehmedialarabic;FEEC
heiseierasquare;337B
hekatakana;30D8
hekatakanahalfwidth;FF8D
hekutaarusquare;3336
henghook;0267
herutusquare;3339
het;05D7
hethebrew;05D7
hhook;0266
hhooksuperior;02B1
hieuhacirclekorean;327B
hieuhaparenkorean;321B
hieuhcirclekorean;326D
hieuhkorean;314E
hieuhparenkorean;320D
hihiragana;3072
hikatakana;30D2
hikatakanahalfwidth;FF8B
hiriq;05B4
hiriq14;05B4
hiriq21;05B4
hiriq2d;05B4
hiriqhebrew;05B4
hiriqnarrowhebrew;05B4
hiriqquarterhebrew;05B4
hiriqwidehebrew;05B4
hlinebelow;1E96
hmonospace;FF48
hoarmenian;0570
hohipthai;0E2B
hohiragana;307B
hokatakana;30DB
hokatakanahalfwidth;FF8E
holam;05B9
holam19;05B9
holam26;05B9
holam32;05B9
holamhebrew;05B9
holamnarrowhebrew;05B9
holamquarterhebrew;05B9
holamwidehebrew;05B9
honokhukthai;0E2E
hookabovecomb;0309
hookcmb;0309
hookpalatalizedbelowcmb;0321
hookretroflexbelowcmb;0322
hoonsquare;3342
horicoptic;03E9
horizontalbar;2015
horncmb;031B
hotsprings;2668
house;2302
hparen;24A3
hsuperior;02B0
hturned;0265
huhiragana;3075
huiitosquare;3333
hukatakana;30D5
hukatakanahalfwidth;FF8C
hungarumlaut;02DD
hungarumlautcmb;030B
hv;0195
hyphen;002D
hypheninferior;F6E5
hyphenmonospace;FF0D
hyphensmall;FE63
hyphensuperior;F6E6
hyphentwo;2010
i;0069
iacute;00ED
iacyrillic;044F
ibengali;0987
ibopomofo;3127
ibreve;012D
icaron;01D0
icircle;24D8
icircumflex;00EE
icyrillic;0456
idblgrave;0209
ideographearthcircle;328F
ideographfirecircle;328B
ideographicallianceparen;323F
ideographiccallparen;323A
ideographiccentrecircle;32A5
ideographicclose;3006
ideographiccomma;3001
ideographiccommaleft;FF64
ideographiccongratulationparen;3237
ideographiccorrectcircle;32A3
ideographicearthparen;322F
ideographicenterpriseparen;323D
ideographicexcellentcircle;329D
ideographicfestivalparen;3240
ideographicfinancialcircle;3296
ideographicfinancialparen;3236
ideographicfireparen;322B
ideographichaveparen;3232
ideographichighcircle;32A4
ideographiciterationmark;3005
ideographiclaborcircle;3298
ideographiclaborparen;3238
ideographicleftcircle;32A7
ideographiclowcircle;32A6
ideographicmedicinecircle;32A9
ideographicmetalparen;322E
ideographicmoonparen;322A
ideographicnameparen;3234
ideographicperiod;3002
ideographicprintcircle;329E
ideographicreachparen;3243
ideographicrepresentparen;3239
ideographicresourceparen;323E
ideographicrightcircle;32A8
ideographicsecretcircle;3299
ideographicselfparen;3242
ideographicsocietyparen;3233
ideographicspace;3000
ideographicspecialparen;3235
ideographicstockparen;3231
ideographicstudyparen;323B
ideographicsunparen;3230
ideographicsuperviseparen;323C
ideographicwaterparen;322C
ideographicwoodparen;322D
ideographiczero;3007
ideographmetalcircle;328E
ideographmooncircle;328A
ideographnamecircle;3294
ideographsuncircle;3290
ideographwatercircle;328C
ideographwoodcircle;328D
ideva;0907
idieresis;00EF
idieresisacute;1E2F
idieresiscyrillic;04E5
idotbelow;1ECB
iebrevecyrillic;04D7
iecyrillic;0435
ieungacirclekorean;3275
ieungaparenkorean;3215
ieungcirclekorean;3267
ieungkorean;3147
ieungparenkorean;3207
igrave;00EC
igujarati;0A87
igurmukhi;0A07
ihiragana;3044
ihookabove;1EC9
iibengali;0988
iicyrillic;0438
iideva;0908
iigujarati;0A88
iigurmukhi;0A08
iimatragurmukhi;0A40
iinvertedbreve;020B
iishortcyrillic;0439
iivowelsignbengali;09C0
iivowelsigndeva;0940
iivowelsigngujarati;0AC0
ij;0133
ikatakana;30A4
ikatakanahalfwidth;FF72
ikorean;3163
ilde;02DC
iluyhebrew;05AC
imacron;012B
imacroncyrillic;04E3
imageorapproximatelyequal;2253
imatragurmukhi;0A3F
imonospace;FF49
increment;2206
infinity;221E
iniarmenian;056B
integral;222B
integralbottom;2321
integralbt;2321
integralex;F8F5
integraltop;2320
integraltp;2320
intersection;2229
intisquare;3305
invbullet;25D8
invcircle;25D9
invsmileface;263B
iocyrillic;0451
iogonek;012F
iota;03B9
iotadieresis;03CA
iotadieresistonos;0390
iotalatin;0269
iotatonos;03AF
iparen;24A4
irigurmukhi;0A72
ismallhiragana;3043
ismallkatakana;30A3
ismallkatakanahalfwidth;FF68
issharbengali;09FA
istroke;0268
isuperior;F6ED
iterationhiragana;309D
iterationkatakana;30FD
itilde;0129
itildebelow;1E2D
iubopomofo;3129
iucyrillic;044E
ivowelsignbengali;09BF
ivowelsigndeva;093F
ivowelsigngujarati;0ABF
izhitsacyrillic;0475
izhitsadblgravecyrillic;0477
j;006A
jaarmenian;0571
jabengali;099C
jadeva;091C
jagujarati;0A9C
jagurmukhi;0A1C
jbopomofo;3110
jcaron;01F0
jcircle;24D9
jcircumflex;0135
jcrossedtail;029D
jdotlessstroke;025F
jecyrillic;0458
jeemarabic;062C
jeemfinalarabic;FE9E
jeeminitialarabic;FE9F
jeemmedialarabic;FEA0
jeharabic;0698
jehfinalarabic;FB8B
jhabengali;099D
jhadeva;091D
jhagujarati;0A9D
jhagurmukhi;0A1D
jheharmenian;057B
jis;3004
jmonospace;FF4A
jparen;24A5
jsuperior;02B2
k;006B
kabashkircyrillic;04A1
kabengali;0995
kacute;1E31
kacyrillic;043A
kadescendercyrillic;049B
kadeva;0915
kaf;05DB
kafarabic;0643
kafdagesh;FB3B
kafdageshhebrew;FB3B
kaffinalarabic;FEDA
kafhebrew;05DB
kafinitialarabic;FEDB
kafmedialarabic;FEDC
kafrafehebrew;FB4D
kagujarati;0A95
kagurmukhi;0A15
kahiragana;304B
kahookcyrillic;04C4
kakatakana;30AB
kakatakanahalfwidth;FF76
kappa;03BA
kappasymbolgreek;03F0
kapyeounmieumkorean;3171
kapyeounphieuphkorean;3184
kapyeounpieupkorean;3178
kapyeounssangpieupkorean;3179
karoriisquare;330D
kashidaautoarabic;0640
kashidaautonosidebearingarabic;0640
kasmallkatakana;30F5
kasquare;3384
kasraarabic;0650
kasratanarabic;064D
kastrokecyrillic;049F
katahiraprolongmarkhalfwidth;FF70
kaverticalstrokecyrillic;049D
kbopomofo;310E
kcalsquare;3389
kcaron;01E9
kcedilla;0137
kcircle;24DA
kcommaaccent;0137
kdotbelow;1E33
keharmenian;0584
kehiragana;3051
kekatakana;30B1
kekatakanahalfwidth;FF79
kenarmenian;056F
kesmallkatakana;30F6
kgreenlandic;0138
khabengali;0996
khacyrillic;0445
khadeva;0916
khagujarati;0A96
khagurmukhi;0A16
khaharabic;062E
khahfinalarabic;FEA6
khahinitialarabic;FEA7
khahmedialarabic;FEA8
kheicoptic;03E7
khhadeva;0959
khhagurmukhi;0A59
khieukhacirclekorean;3278
khieukhaparenkorean;3218
khieukhcirclekorean;326A
khieukhkorean;314B
khieukhparenkorean;320A
khokhaithai;0E02
khokhonthai;0E05
khokhuatthai;0E03
khokhwaithai;0E04
khomutthai;0E5B
khook;0199
khorakhangthai;0E06
khzsquare;3391
kihiragana;304D
kikatakana;30AD
kikatakanahalfwidth;FF77
kiroguramusquare;3315
kiromeetorusquare;3316
kirosquare;3314
kiyeokacirclekorean;326E
kiyeokaparenkorean;320E
kiyeokcirclekorean;3260
kiyeokkorean;3131
kiyeokparenkorean;3200
kiyeoksioskorean;3133
kjecyrillic;045C
klinebelow;1E35
klsquare;3398
kmcubedsquare;33A6
kmonospace;FF4B
kmsquaredsquare;33A2
kohiragana;3053
kohmsquare;33C0
kokaithai;0E01
kokatakana;30B3
kokatakanahalfwidth;FF7A
kooposquare;331E
koppacyrillic;0481
koreanstandardsymbol;327F
koroniscmb;0343
kparen;24A6
kpasquare;33AA
ksicyrillic;046F
ktsquare;33CF
kturned;029E
kuhiragana;304F
kukatakana;30AF
kukatakanahalfwidth;FF78
kvsquare;33B8
kwsquare;33BE
l;006C
labengali;09B2
lacute;013A
ladeva;0932
lagujarati;0AB2
lagurmukhi;0A32
lakkhangyaothai;0E45
lamaleffinalarabic;FEFC
lamalefhamzaabovefinalarabic;FEF8
lamalefhamzaaboveisolatedarabic;FEF7
lamalefhamzabelowfinalarabic;FEFA
lamalefhamzabelowisolatedarabic;FEF9
lamalefisolatedarabic;FEFB
lamalefmaddaabovefinalarabic;FEF6
lamalefmaddaaboveisolatedarabic;FEF5
lamarabic;0644
lambda;03BB
lambdastroke;019B
lamed;05DC
lameddagesh;FB3C
lameddageshhebrew;FB3C
lamedhebrew;05DC
lamedholam;05DC 05B9
lamedholamdagesh;05DC 05B9 05BC
lamedholamdageshhebrew;05DC 05B9 05BC
lamedholamhebrew;05DC 05B9
lamfinalarabic;FEDE
lamhahinitialarabic;FCCA
laminitialarabic;FEDF
lamjeeminitialarabic;FCC9
lamkhahinitialarabic;FCCB
lamlamhehisolatedarabic;FDF2
lammedialarabic;FEE0
lammeemhahinitialarabic;FD88
lammeeminitialarabic;FCCC
lammeemjeeminitialarabic;FEDF FEE4 FEA0
lammeemkhahinitialarabic;FEDF FEE4 FEA8
largecircle;25EF
lbar;019A
lbelt;026C
lbopomofo;310C
lcaron;013E
lcedilla;013C
lcircle;24DB
lcircumflexbelow;1E3D
lcommaaccent;013C
ldot;0140
ldotaccent;0140
ldotbelow;1E37
ldotbelowmacron;1E39
leftangleabovecmb;031A
lefttackbelowcmb;0318
less;003C
lessequal;2264
lessequalorgreater;22DA
lessmonospace;FF1C
lessorequivalent;2272
lessorgreater;2276
lessoverequal;2266
lesssmall;FE64
lezh;026E
lfblock;258C
lhookretroflex;026D
lira;20A4
liwnarmenian;056C
lj;01C9
ljecyrillic;0459
ll;F6C0
lladeva;0933
llagujarati;0AB3
llinebelow;1E3B
llladeva;0934
llvocalicbengali;09E1
llvocalicdeva;0961
llvocalicvowelsignbengali;09E3
llvocalicvowelsigndeva;0963
lmiddletilde;026B
lmonospace;FF4C
lmsquare;33D0
lochulathai;0E2C
logicaland;2227
logicalnot;00AC
logicalnotreversed;2310
logicalor;2228
lolingthai;0E25
longs;017F
lowlinecenterline;FE4E
lowlinecmb;0332
lowlinedashed;FE4D
lozenge;25CA
lparen;24A7
lslash;0142
lsquare;2113
lsuperior;F6EE
ltshade;2591
luthai;0E26
lvocalicbengali;098C
lvocalicdeva;090C
lvocalicvowelsignbengali;09E2
lvocalicvowelsigndeva;0962
lxsquare;33D3
m;006D
mabengali;09AE
macron;00AF
macronbelowcmb;0331
macroncmb;0304
macronlowmod;02CD
macronmonospace;FFE3
macute;1E3F
madeva;092E
magujarati;0AAE
magurmukhi;0A2E
mahapakhhebrew;05A4
mahapakhlefthebrew;05A4
mahiragana;307E
maichattawalowleftthai;F895
maichattawalowrightthai;F894
maichattawathai;0E4B
maichattawaupperleftthai;F893
maieklowleftthai;F88C
maieklowrightthai;F88B
maiekthai;0E48
maiekupperleftthai;F88A
maihanakatleftthai;F884
maihanakatthai;0E31
maitaikhuleftthai;F889
maitaikhuthai;0E47
maitholowleftthai;F88F
maitholowrightthai;F88E
maithothai;0E49
maithoupperleftthai;F88D
maitrilowleftthai;F892
maitrilowrightthai;F891
maitrithai;0E4A
maitriupperleftthai;F890
maiyamokthai;0E46
makatakana;30DE
makatakanahalfwidth;FF8F
male;2642
mansyonsquare;3347
maqafhebrew;05BE
mars;2642
masoracirclehebrew;05AF
masquare;3383
mbopomofo;3107
mbsquare;33D4
mcircle;24DC
mcubedsquare;33A5
mdotaccent;1E41
mdotbelow;1E43
meemarabic;0645
meemfinalarabic;FEE2
meeminitialarabic;FEE3
meemmedialarabic;FEE4
meemmeeminitialarabic;FCD1
meemmeemisolatedarabic;FC48
meetorusquare;334D
mehiragana;3081
meizierasquare;337E
mekatakana;30E1
mekatakanahalfwidth;FF92
mem;05DE
memdagesh;FB3E
memdageshhebrew;FB3E
memhebrew;05DE
menarmenian;0574
merkhahebrew;05A5
merkhakefulahebrew;05A6
merkhakefulalefthebrew;05A6
merkhalefthebrew;05A5
mhook;0271
mhzsquare;3392
middledotkatakanahalfwidth;FF65
middot;00B7
mieumacirclekorean;3272
mieumaparenkorean;3212
mieumcirclekorean;3264
mieumkorean;3141
mieumpansioskorean;3170
mieumparenkorean;3204
mieumpieupkorean;316E
mieumsioskorean;316F
mihiragana;307F
mikatakana;30DF
mikatakanahalfwidth;FF90
minus;2212
minusbelowcmb;0320
minuscircle;2296
minusmod;02D7
minusplus;2213
minute;2032
miribaarusquare;334A
mirisquare;3349
mlonglegturned;0270
mlsquare;3396
mmcubedsquare;33A3
mmonospace;FF4D
mmsquaredsquare;339F
mohiragana;3082
mohmsquare;33C1
mokatakana;30E2
mokatakanahalfwidth;FF93
molsquare;33D6
momathai;0E21
moverssquare;33A7
moverssquaredsquare;33A8
mparen;24A8
mpasquare;33AB
mssquare;33B3
msuperior;F6EF
mturned;026F
mu;00B5
mu1;00B5
muasquare;3382
muchgreater;226B
muchless;226A
mufsquare;338C
mugreek;03BC
mugsquare;338D
muhiragana;3080
mukatakana;30E0
mukatakanahalfwidth;FF91
mulsquare;3395
multiply;00D7
mumsquare;339B
munahhebrew;05A3
munahlefthebrew;05A3
musicalnote;266A
musicalnotedbl;266B
musicflatsign;266D
musicsharpsign;266F
mussquare;33B2
muvsquare;33B6
muwsquare;33BC
mvmegasquare;33B9
mvsquare;33B7
mwmegasquare;33BF
mwsquare;33BD
n;006E
nabengali;09A8
nabla;2207
nacute;0144
nadeva;0928
nagujarati;0AA8
nagurmukhi;0A28
nahiragana;306A
nakatakana;30CA
nakatakanahalfwidth;FF85
napostrophe;0149
nasquare;3381
nbopomofo;310B
nbspace;00A0
ncaron;0148
ncedilla;0146
ncircle;24DD
ncircumflexbelow;1E4B
ncommaaccent;0146
ndotaccent;1E45
ndotbelow;1E47
nehiragana;306D
nekatakana;30CD
nekatakanahalfwidth;FF88
newsheqelsign;20AA
nfsquare;338B
ngabengali;0999
ngadeva;0919
ngagujarati;0A99
ngagurmukhi;0A19
ngonguthai;0E07
nhiragana;3093
nhookleft;0272
nhookretroflex;0273
nieunacirclekorean;326F
nieunaparenkorean;320F
nieuncieuckorean;3135
nieuncirclekorean;3261
nieunhieuhkorean;3136
nieunkorean;3134
nieunpansioskorean;3168
nieunparenkorean;3201
nieunsioskorean;3167
nieuntikeutkorean;3166
nihiragana;306B
nikatakana;30CB
nikatakanahalfwidth;FF86
nikhahitleftthai;F899
nikhahitthai;0E4D
nine;0039
ninearabic;0669
ninebengali;09EF
ninecircle;2468
ninecircleinversesansserif;2792
ninedeva;096F
ninegujarati;0AEF
ninegurmukhi;0A6F
ninehackarabic;0669
ninehangzhou;3029
nineideographicparen;3228
nineinferior;2089
ninemonospace;FF19
nineoldstyle;F739
nineparen;247C
nineperiod;2490
ninepersian;06F9
nineroman;2178
ninesuperior;2079
nineteencircle;2472
nineteenparen;2486
nineteenperiod;249A
ninethai;0E59
nj;01CC
njecyrillic;045A
nkatakana;30F3
nkatakanahalfwidth;FF9D
nlegrightlong;019E
nlinebelow;1E49
nmonospace;FF4E
nmsquare;339A
nnabengali;09A3
nnadeva;0923
nnagujarati;0AA3
nnagurmukhi;0A23
nnnadeva;0929
nohiragana;306E
nokatakana;30CE
nokatakanahalfwidth;FF89
nonbreakingspace;00A0
nonenthai;0E13
nonuthai;0E19
noonarabic;0646
noonfinalarabic;FEE6
noonghunnaarabic;06BA
noonghunnafinalarabic;FB9F
noonhehinitialarabic;FEE7 FEEC
nooninitialarabic;FEE7
noonjeeminitialarabic;FCD2
noonjeemisolatedarabic;FC4B
noonmedialarabic;FEE8
noonmeeminitialarabic;FCD5
noonmeemisolatedarabic;FC4E
noonnoonfinalarabic;FC8D
notcontains;220C
notelement;2209
notelementof;2209
notequal;2260
notgreater;226F
notgreaternorequal;2271
notgreaternorless;2279
notidentical;2262
notless;226E
notlessnorequal;2270
notparallel;2226
notprecedes;2280
notsubset;2284
notsucceeds;2281
notsuperset;2285
nowarmenian;0576
nparen;24A9
nssquare;33B1
nsuperior;207F
ntilde;00F1
nu;03BD
nuhiragana;306C
nukatakana;30CC
nukatakanahalfwidth;FF87
nuktabengali;09BC
nuktadeva;093C
nuktagujarati;0ABC
nuktagurmukhi;0A3C
numbersign;0023
numbersignmonospace;FF03
numbersignsmall;FE5F
numeralsigngreek;0374
numeralsignlowergreek;0375
numero;2116
nun;05E0
nundagesh;FB40
nundageshhebrew;FB40
nunhebrew;05E0
nvsquare;33B5
nwsquare;33BB
nyabengali;099E
nyadeva;091E
nyagujarati;0A9E
nyagurmukhi;0A1E
o;006F
oacute;00F3
oangthai;0E2D
obarred;0275
obarredcyrillic;04E9
obarreddieresiscyrillic;04EB
obengali;0993
obopomofo;311B
obreve;014F
ocandradeva;0911
ocandragujarati;0A91
ocandravowelsigndeva;0949
ocandravowelsigngujarati;0AC9
ocaron;01D2
ocircle;24DE
ocircumflex;00F4
ocircumflexacute;1ED1
ocircumflexdotbelow;1ED9
ocircumflexgrave;1ED3
ocircumflexhookabove;1ED5
ocircumflextilde;1ED7
ocyrillic;043E
odblacute;0151
odblgrave;020D
odeva;0913
odieresis;00F6
odieresiscyrillic;04E7
odotbelow;1ECD
oe;0153
oekorean;315A
ogonek;02DB
ogonekcmb;0328
ograve;00F2
ogujarati;0A93
oharmenian;0585
ohiragana;304A
ohookabove;1ECF
ohorn;01A1
ohornacute;1EDB
ohorndotbelow;1EE3
ohorngrave;1EDD
ohornhookabove;1EDF
ohorntilde;1EE1
ohungarumlaut;0151
oi;01A3
oinvertedbreve;020F
okatakana;30AA
okatakanahalfwidth;FF75
okorean;3157
olehebrew;05AB
omacron;014D
omacronacute;1E53
omacrongrave;1E51
omdeva;0950
omega;03C9
omega1;03D6
omegacyrillic;0461
omegalatinclosed;0277
omegaroundcyrillic;047B
omegatitlocyrillic;047D
omegatonos;03CE
omgujarati;0AD0
omicron;03BF
omicrontonos;03CC
omonospace;FF4F
one;0031
onearabic;0661
onebengali;09E7
onecircle;2460
onecircleinversesansserif;278A
onedeva;0967
onedotenleader;2024
oneeighth;215B
onefitted;F6DC
onegujarati;0AE7
onegurmukhi;0A67
onehackarabic;0661
onehalf;00BD
onehangzhou;3021
oneideographicparen;3220
oneinferior;2081
onemonospace;FF11
onenumeratorbengali;09F4
oneoldstyle;F731
oneparen;2474
oneperiod;2488
onepersian;06F1
onequarter;00BC
oneroman;2170
onesuperior;00B9
onethai;0E51
onethird;2153
oogonek;01EB
oogonekmacron;01ED
oogurmukhi;0A13
oomatragurmukhi;0A4B
oopen;0254
oparen;24AA
openbullet;25E6
option;2325
ordfeminine;00AA
ordmasculine;00BA
orthogonal;221F
oshortdeva;0912
oshortvowelsigndeva;094A
oslash;00F8
oslashacute;01FF
osmallhiragana;3049
osmallkatakana;30A9
osmallkatakanahalfwidth;FF6B
ostrokeacute;01FF
osuperior;F6F0
otcyrillic;047F
otilde;00F5
otildeacute;1E4D
otildedieresis;1E4F
oubopomofo;3121
overline;203E
overlinecenterline;FE4A
overlinecmb;0305
overlinedashed;FE49
overlinedblwavy;FE4C
overlinewavy;FE4B
overscore;00AF
ovowelsignbengali;09CB
ovowelsigndeva;094B
ovowelsigngujarati;0ACB
p;0070
paampssquare;3380
paasentosquare;332B
pabengali;09AA
pacute;1E55
padeva;092A
pagedown;21DF
pageup;21DE
pagujarati;0AAA
pagurmukhi;0A2A
pahiragana;3071
paiyannoithai;0E2F
pakatakana;30D1
palatalizationcyrilliccmb;0484
palochkacyrillic;04C0
pansioskorean;317F
paragraph;00B6
parallel;2225
parenleft;0028
parenleftaltonearabic;FD3E
parenleftbt;F8ED
parenleftex;F8EC
parenleftinferior;208D
parenleftmonospace;FF08
parenleftsmall;FE59
parenleftsuperior;207D
parenlefttp;F8EB
parenleftvertical;FE35
parenright;0029
parenrightaltonearabic;FD3F
parenrightbt;F8F8
parenrightex;F8F7
parenrightinferior;208E
parenrightmonospace;FF09
parenrightsmall;FE5A
parenrightsuperior;207E
parenrighttp;F8F6
parenrightvertical;FE36
partialdiff;2202
paseqhebrew;05C0
pashtahebrew;0599
pasquare;33A9
patah;05B7
patah11;05B7
patah1d;05B7
patah2a;05B7
patahhebrew;05B7
patahnarrowhebrew;05B7
patahquarterhebrew;05B7
patahwidehebrew;05B7
pazerhebrew;05A1
pbopomofo;3106
pcircle;24DF
pdotaccent;1E57
pe;05E4
pecyrillic;043F
pedagesh;FB44
pedageshhebrew;FB44
peezisquare;333B
pefinaldageshhebrew;FB43
peharabic;067E
peharmenian;057A
pehebrew;05E4
pehfinalarabic;FB57
pehinitialarabic;FB58
pehiragana;307A
pehmedialarabic;FB59
pekatakana;30DA
pemiddlehookcyrillic;04A7
perafehebrew;FB4E
percent;0025
percentarabic;066A
percentmonospace;FF05
percentsmall;FE6A
period;002E
periodarmenian;0589
periodcentered;00B7
periodhalfwidth;FF61
periodinferior;F6E7
periodmonospace;FF0E
periodsmall;FE52
periodsuperior;F6E8
perispomenigreekcmb;0342
perpendicular;22A5
perthousand;2030
peseta;20A7
pfsquare;338A
phabengali;09AB
phadeva;092B
phagujarati;0AAB
phagurmukhi;0A2B
phi;03C6
phi1;03D5
phieuphacirclekorean;327A
phieuphaparenkorean;321A
phieuphcirclekorean;326C
phieuphkorean;314D
phieuphparenkorean;320C
philatin;0278
phinthuthai;0E3A
phisymbolgreek;03D5
phook;01A5
phophanthai;0E1E
phophungthai;0E1C
phosamphaothai;0E20
pi;03C0
pieupacirclekorean;3273
pieupaparenkorean;3213
pieupcieuckorean;3176
pieupcirclekorean;3265
pieupkiyeokkorean;3172
pieupkorean;3142
pieupparenkorean;3205
pieupsioskiyeokkorean;3174
pieupsioskorean;3144
pieupsiostikeutkorean;3175
pieupthieuthkorean;3177
pieuptikeutkorean;3173
pihiragana;3074
pikatakana;30D4
pisymbolgreek;03D6
piwrarmenian;0583
plus;002B
plusbelowcmb;031F
pluscircle;2295
plusminus;00B1
plusmod;02D6
plusmonospace;FF0B
plussmall;FE62
plussuperior;207A
pmonospace;FF50
pmsquare;33D8
pohiragana;307D
pointingindexdownwhite;261F
pointingindexleftwhite;261C
pointingindexrightwhite;261E
pointingindexupwhite;261D
pokatakana;30DD
poplathai;0E1B
postalmark;3012
postalmarkface;3020
pparen;24AB
precedes;227A
prescription;211E
primemod;02B9
primereversed;2035
product;220F
projective;2305
prolongedkana;30FC
propellor;2318
propersubset;2282
propersuperset;2283
proportion;2237
proportional;221D
psi;03C8
psicyrillic;0471
psilipneumatacyrilliccmb;0486
pssquare;33B0
puhiragana;3077
pukatakana;30D7
pvsquare;33B4
pwsquare;33BA
q;0071
qadeva;0958
qadmahebrew;05A8
qafarabic;0642
qaffinalarabic;FED6
qafinitialarabic;FED7
qafmedialarabic;FED8
qamats;05B8
qamats10;05B8
qamats1a;05B8
qamats1c;05B8
qamats27;05B8
qamats29;05B8
qamats33;05B8
qamatsde;05B8
qamatshebrew;05B8
qamatsnarrowhebrew;05B8
qamatsqatanhebrew;05B8
qamatsqatannarrowhebrew;05B8
qamatsqatanquarterhebrew;05B8
qamatsqatanwidehebrew;05B8
qamatsquarterhebrew;05B8
qamatswidehebrew;05B8
qarneyparahebrew;059F
qbopomofo;3111
qcircle;24E0
qhook;02A0
qmonospace;FF51
qof;05E7
qofdagesh;FB47
qofdageshhebrew;FB47
qofhatafpatah;05E7 05B2
qofhatafpatahhebrew;05E7 05B2
qofhatafsegol;05E7 05B1
qofhatafsegolhebrew;05E7 05B1
qofhebrew;05E7
qofhiriq;05E7 05B4
qofhiriqhebrew;05E7 05B4
qofholam;05E7 05B9
qofholamhebrew;05E7 05B9
qofpatah;05E7 05B7
qofpatahhebrew;05E7 05B7
qofqamats;05E7 05B8
qofqamatshebrew;05E7 05B8
qofqubuts;05E7 05BB
qofqubutshebrew;05E7 05BB
qofsegol;05E7 05B6
qofsegolhebrew;05E7 05B6
qofsheva;05E7 05B0
qofshevahebrew;05E7 05B0
qoftsere;05E7 05B5
qoftserehebrew;05E7 05B5
qparen;24AC
quarternote;2669
qubuts;05BB
qubuts18;05BB
qubuts25;05BB
qubuts31;05BB
qubutshebrew;05BB
qubutsnarrowhebrew;05BB
qubutsquarterhebrew;05BB
qubutswidehebrew;05BB
question;003F
questionarabic;061F
questionarmenian;055E
questiondown;00BF
questiondownsmall;F7BF
questiongreek;037E
questionmonospace;FF1F
questionsmall;F73F
quotedbl;0022
quotedblbase;201E
quotedblleft;201C
quotedblmonospace;FF02
quotedblprime;301E
quotedblprimereversed;301D
quotedblright;201D
quoteleft;2018
quoteleftreversed;201B
quotereversed;201B
quoteright;2019
quoterightn;0149
quotesinglbase;201A
quotesingle;0027
quotesinglemonospace;FF07
r;0072
raarmenian;057C
rabengali;09B0
racute;0155
radeva;0930
radical;221A
radicalex;F8E5
radoverssquare;33AE
radoverssquaredsquare;33AF
radsquare;33AD
rafe;05BF
rafehebrew;05BF
ragujarati;0AB0
ragurmukhi;0A30
rahiragana;3089
rakatakana;30E9
rakatakanahalfwidth;FF97
ralowerdiagonalbengali;09F1
ramiddlediagonalbengali;09F0
ramshorn;0264
ratio;2236
rbopomofo;3116
rcaron;0159
rcedilla;0157
rcircle;24E1
rcommaaccent;0157
rdblgrave;0211
rdotaccent;1E59
rdotbelow;1E5B
rdotbelowmacron;1E5D
referencemark;203B
reflexsubset;2286
reflexsuperset;2287
registered;00AE
registersans;F8E8
registerserif;F6DA
reharabic;0631
reharmenian;0580
rehfinalarabic;FEAE
rehiragana;308C
rehyehaleflamarabic;0631 FEF3 FE8E 0644
rekatakana;30EC
rekatakanahalfwidth;FF9A
resh;05E8
reshdageshhebrew;FB48
reshhatafpatah;05E8 05B2
reshhatafpatahhebrew;05E8 05B2
reshhatafsegol;05E8 05B1
reshhatafsegolhebrew;05E8 05B1
reshhebrew;05E8
reshhiriq;05E8 05B4
reshhiriqhebrew;05E8 05B4
reshholam;05E8 05B9
reshholamhebrew;05E8 05B9
reshpatah;05E8 05B7
reshpatahhebrew;05E8 05B7
reshqamats;05E8 05B8
reshqamatshebrew;05E8 05B8
reshqubuts;05E8 05BB
reshqubutshebrew;05E8 05BB
reshsegol;05E8 05B6
reshsegolhebrew;05E8 05B6
reshsheva;05E8 05B0
reshshevahebrew;05E8 05B0
reshtsere;05E8 05B5
reshtserehebrew;05E8 05B5
reversedtilde;223D
reviahebrew;0597
reviamugrashhebrew;0597
revlogicalnot;2310
rfishhook;027E
rfishhookreversed;027F
rhabengali;09DD
rhadeva;095D
rho;03C1
rhook;027D
rhookturned;027B
rhookturnedsuperior;02B5
rhosymbolgreek;03F1
rhotichookmod;02DE
rieulacirclekorean;3271
rieulaparenkorean;3211
rieulcirclekorean;3263
rieulhieuhkorean;3140
rieulkiyeokkorean;313A
rieulkiyeoksioskorean;3169
rieulkorean;3139
rieulmieumkorean;313B
rieulpansioskorean;316C
rieulparenkorean;3203
rieulphieuphkorean;313F
rieulpieupkorean;313C
rieulpieupsioskorean;316B
rieulsioskorean;313D
rieulthieuthkorean;313E
rieultikeutkorean;316A
rieulyeorinhieuhkorean;316D
rightangle;221F
righttackbelowcmb;0319
righttriangle;22BF
rihiragana;308A
rikatakana;30EA
rikatakanahalfwidth;FF98
ring;02DA
ringbelowcmb;0325
ringcmb;030A
ringhalfleft;02BF
ringhalfleftarmenian;0559
ringhalfleftbelowcmb;031C
ringhalfleftcentered;02D3
ringhalfright;02BE
ringhalfrightbelowcmb;0339
ringhalfrightcentered;02D2
rinvertedbreve;0213
rittorusquare;3351
rlinebelow;1E5F
rlongleg;027C
rlonglegturned;027A
rmonospace;FF52
rohiragana;308D
rokatakana;30ED
rokatakanahalfwidth;FF9B
roruathai;0E23
rparen;24AD
rrabengali;09DC
rradeva;0931
rragurmukhi;0A5C
rreharabic;0691
rrehfinalarabic;FB8D
rrvocalicbengali;09E0
rrvocalicdeva;0960
rrvocalicgujarati;0AE0
rrvocalicvowelsignbengali;09C4
rrvocalicvowelsigndeva;0944
rrvocalicvowelsigngujarati;0AC4
rsuperior;F6F1
rtblock;2590
rturned;0279
rturnedsuperior;02B4
ruhiragana;308B
rukatakana;30EB
rukatakanahalfwidth;FF99
rupeemarkbengali;09F2
rupeesignbengali;09F3
rupiah;F6DD
ruthai;0E24
rvocalicbengali;098B
rvocalicdeva;090B
rvocalicgujarati;0A8B
rvocalicvowelsignbengali;09C3
rvocalicvowelsigndeva;0943
rvocalicvowelsigngujarati;0AC3
s;0073
sabengali;09B8
sacute;015B
sacutedotaccent;1E65
sadarabic;0635
sadeva;0938
sadfinalarabic;FEBA
sadinitialarabic;FEBB
sadmedialarabic;FEBC
sagujarati;0AB8
sagurmukhi;0A38
sahiragana;3055
sakatakana;30B5
sakatakanahalfwidth;FF7B
sallallahoualayhewasallamarabic;FDFA
samekh;05E1
samekhdagesh;FB41
samekhdageshhebrew;FB41
samekhhebrew;05E1
saraaathai;0E32
saraaethai;0E41
saraaimaimalaithai;0E44
saraaimaimuanthai;0E43
saraamthai;0E33
saraathai;0E30
saraethai;0E40
saraiileftthai;F886
saraiithai;0E35
saraileftthai;F885
saraithai;0E34
saraothai;0E42
saraueeleftthai;F888
saraueethai;0E37
saraueleftthai;F887
sarauethai;0E36
sarauthai;0E38
sarauuthai;0E39
sbopomofo;3119
scaron;0161
scarondotaccent;1E67
scedilla;015F
schwa;0259
schwacyrillic;04D9
schwadieresiscyrillic;04DB
schwahook;025A
scircle;24E2
scircumflex;015D
scommaaccent;0219
sdotaccent;1E61
sdotbelow;1E63
sdotbelowdotaccent;1E69
seagullbelowcmb;033C
second;2033
secondtonechinese;02CA
section;00A7
seenarabic;0633
seenfinalarabic;FEB2
seeninitialarabic;FEB3
seenmedialarabic;FEB4
segol;05B6
segol13;05B6
segol1f;05B6
segol2c;05B6
segolhebrew;05B6
segolnarrowhebrew;05B6
segolquarterhebrew;05B6
segoltahebrew;0592
segolwidehebrew;05B6
seharmenian;057D
sehiragana;305B
sekatakana;30BB
sekatakanahalfwidth;FF7E
semicolon;003B
semicolonarabic;061B
semicolonmonospace;FF1B
semicolonsmall;FE54
semivoicedmarkkana;309C
semivoicedmarkkanahalfwidth;FF9F
sentisquare;3322
sentosquare;3323
seven;0037
sevenarabic;0667
sevenbengali;09ED
sevencircle;2466
sevencircleinversesansserif;2790
sevendeva;096D
seveneighths;215E
sevengujarati;0AED
sevengurmukhi;0A6D
sevenhackarabic;0667
sevenhangzhou;3027
sevenideographicparen;3226
seveninferior;2087
sevenmonospace;FF17
sevenoldstyle;F737
sevenparen;247A
sevenperiod;248E
sevenpersian;06F7
sevenroman;2176
sevensuperior;2077
seventeencircle;2470
seventeenparen;2484
seventeenperiod;2498
seventhai;0E57
sfthyphen;00AD
shaarmenian;0577
shabengali;09B6
shacyrillic;0448
shaddaarabic;0651
shaddadammaarabic;FC61
shaddadammatanarabic;FC5E
shaddafathaarabic;FC60
shaddafathatanarabic;0651 064B
shaddakasraarabic;FC62
shaddakasratanarabic;FC5F
shade;2592
shadedark;2593
shadelight;2591
shademedium;2592
shadeva;0936
shagujarati;0AB6
shagurmukhi;0A36
shalshelethebrew;0593
shbopomofo;3115
shchacyrillic;0449
sheenarabic;0634
sheenfinalarabic;FEB6
sheeninitialarabic;FEB7
sheenmedialarabic;FEB8
sheicoptic;03E3
sheqel;20AA
sheqelhebrew;20AA
sheva;05B0
sheva115;05B0
sheva15;05B0
sheva22;05B0
sheva2e;05B0
shevahebrew;05B0
shevanarrowhebrew;05B0
shevaquarterhebrew;05B0
shevawidehebrew;05B0
shhacyrillic;04BB
shimacoptic;03ED
shin;05E9
shindagesh;FB49
shindageshhebrew;FB49
shindageshshindot;FB2C
shindageshshindothebrew;FB2C
shindageshsindot;FB2D
shindageshsindothebrew;FB2D
shindothebrew;05C1
shinhebrew;05E9
shinshindot;FB2A
shinshindothebrew;FB2A
shinsindot;FB2B
shinsindothebrew;FB2B
shook;0282
sigma;03C3
sigma1;03C2
sigmafinal;03C2
sigmalunatesymbolgreek;03F2
sihiragana;3057
sikatakana;30B7
sikatakanahalfwidth;FF7C
siluqhebrew;05BD
siluqlefthebrew;05BD
similar;223C
sindothebrew;05C2
siosacirclekorean;3274
siosaparenkorean;3214
sioscieuckorean;317E
sioscirclekorean;3266
sioskiyeokkorean;317A
sioskorean;3145
siosnieunkorean;317B
siosparenkorean;3206
siospieupkorean;317D
siostikeutkorean;317C
six;0036
sixarabic;0666
sixbengali;09EC
sixcircle;2465
sixcircleinversesansserif;278F
sixdeva;096C
sixgujarati;0AEC
sixgurmukhi;0A6C
sixhackarabic;0666
sixhangzhou;3026
sixideographicparen;3225
sixinferior;2086
sixmonospace;FF16
sixoldstyle;F736
sixparen;2479
sixperiod;248D
sixpersian;06F6
sixroman;2175
sixsuperior;2076
sixteencircle;246F
sixteencurrencydenominatorbengali;09F9
sixteenparen;2483
sixteenperiod;2497
sixthai;0E56
slash;002F
slashmonospace;FF0F
slong;017F
slongdotaccent;1E9B
smileface;263A
smonospace;FF53
sofpasuqhebrew;05C3
softhyphen;00AD
softsigncyrillic;044C
sohiragana;305D
sokatakana;30BD
sokatakanahalfwidth;FF7F
soliduslongoverlaycmb;0338
solidusshortoverlaycmb;0337
sorusithai;0E29
sosalathai;0E28
sosothai;0E0B
sosuathai;0E2A
space;0020
spacehackarabic;0020
spade;2660
spadesuitblack;2660
spadesuitwhite;2664
sparen;24AE
squarebelowcmb;033B
squarecc;33C4
squarecm;339D
squarediagonalcrosshatchfill;25A9
squarehorizontalfill;25A4
squarekg;338F
squarekm;339E
squarekmcapital;33CE
squareln;33D1
squarelog;33D2
squaremg;338E
squaremil;33D5
squaremm;339C
squaremsquared;33A1
squareorthogonalcrosshatchfill;25A6
squareupperlefttolowerrightfill;25A7
squareupperrighttolowerleftfill;25A8
squareverticalfill;25A5
squarewhitewithsmallblack;25A3
srsquare;33DB
ssabengali;09B7
ssadeva;0937
ssagujarati;0AB7
ssangcieuckorean;3149
ssanghieuhkorean;3185
ssangieungkorean;3180
ssangkiyeokkorean;3132
ssangnieunkorean;3165
ssangpieupkorean;3143
ssangsioskorean;3146
ssangtikeutkorean;3138
ssuperior;F6F2
sterling;00A3
sterlingmonospace;FFE1
strokelongoverlaycmb;0336
strokeshortoverlaycmb;0335
subset;2282
subsetnotequal;228A
subsetorequal;2286
succeeds;227B
suchthat;220B
suhiragana;3059
sukatakana;30B9
sukatakanahalfwidth;FF7D
sukunarabic;0652
summation;2211
sun;263C
superset;2283
supersetnotequal;228B
supersetorequal;2287
svsquare;33DC
syouwaerasquare;337C
t;0074
tabengali;09A4
tackdown;22A4
tackleft;22A3
tadeva;0924
tagujarati;0AA4
tagurmukhi;0A24
taharabic;0637
tahfinalarabic;FEC2
tahinitialarabic;FEC3
tahiragana;305F
tahmedialarabic;FEC4
taisyouerasquare;337D
takatakana;30BF
takatakanahalfwidth;FF80
tatweelarabic;0640
tau;03C4
tav;05EA
tavdages;FB4A
tavdagesh;FB4A
tavdageshhebrew;FB4A
tavhebrew;05EA
tbar;0167
tbopomofo;310A
tcaron;0165
tccurl;02A8
tcedilla;0163
tcheharabic;0686
tchehfinalarabic;FB7B
tchehinitialarabic;FB7C
tchehmedialarabic;FB7D
tchehmeeminitialarabic;FB7C FEE4
tcircle;24E3
tcircumflexbelow;1E71
tcommaaccent;0163
tdieresis;1E97
tdotaccent;1E6B
tdotbelow;1E6D
tecyrillic;0442
tedescendercyrillic;04AD
teharabic;062A
tehfinalarabic;FE96
tehhahinitialarabic;FCA2
tehhahisolatedarabic;FC0C
tehinitialarabic;FE97
tehiragana;3066
tehjeeminitialarabic;FCA1
tehjeemisolatedarabic;FC0B
tehmarbutaarabic;0629
tehmarbutafinalarabic;FE94
tehmedialarabic;FE98
tehmeeminitialarabic;FCA4
tehmeemisolatedarabic;FC0E
tehnoonfinalarabic;FC73
tekatakana;30C6
tekatakanahalfwidth;FF83
telephone;2121
telephoneblack;260E
telishagedolahebrew;05A0
telishaqetanahebrew;05A9
tencircle;2469
tenideographicparen;3229
tenparen;247D
tenperiod;2491
tenroman;2179
tesh;02A7
tet;05D8
tetdagesh;FB38
tetdageshhebrew;FB38
tethebrew;05D8
tetsecyrillic;04B5
tevirhebrew;059B
tevirlefthebrew;059B
thabengali;09A5
thadeva;0925
thagujarati;0AA5
thagurmukhi;0A25
thalarabic;0630
thalfinalarabic;FEAC
thanthakhatlowleftthai;F898
thanthakhatlowrightthai;F897
thanthakhatthai;0E4C
thanthakhatupperleftthai;F896
theharabic;062B
thehfinalarabic;FE9A
thehinitialarabic;FE9B
thehmedialarabic;FE9C
thereexists;2203
therefore;2234
theta;03B8
theta1;03D1
thetasymbolgreek;03D1
thieuthacirclekorean;3279
thieuthaparenkorean;3219
thieuthcirclekorean;326B
thieuthkorean;314C
thieuthparenkorean;320B
thirteencircle;246C
thirteenparen;2480
thirteenperiod;2494
thonangmonthothai;0E11
thook;01AD
thophuthaothai;0E12
thorn;00FE
thothahanthai;0E17
thothanthai;0E10
thothongthai;0E18
thothungthai;0E16
thousandcyrillic;0482
thousandsseparatorarabic;066C
thousandsseparatorpersian;066C
three;0033
threearabic;0663
threebengali;09E9
threecircle;2462
threecircleinversesansserif;278C
threedeva;0969
threeeighths;215C
threegujarati;0AE9
threegurmukhi;0A69
threehackarabic;0663
threehangzhou;3023
threeideographicparen;3222
threeinferior;2083
threemonospace;FF13
threenumeratorbengali;09F6
threeoldstyle;F733
threeparen;2476
threeperiod;248A
threepersian;06F3
threequarters;00BE
threequartersemdash;F6DE
threeroman;2172
threesuperior;00B3
threethai;0E53
thzsquare;3394
tihiragana;3061
tikatakana;30C1
tikatakanahalfwidth;FF81
tikeutacirclekorean;3270
tikeutaparenkorean;3210
tikeutcirclekorean;3262
tikeutkorean;3137
tikeutparenkorean;3202
tilde;02DC
tildebelowcmb;0330
tildecmb;0303
tildecomb;0303
tildedoublecmb;0360
tildeoperator;223C
tildeoverlaycmb;0334
tildeverticalcmb;033E
timescircle;2297
tipehahebrew;0596
tipehalefthebrew;0596
tippigurmukhi;0A70
titlocyrilliccmb;0483
tiwnarmenian;057F
tlinebelow;1E6F
tmonospace;FF54
toarmenian;0569
tohiragana;3068
tokatakana;30C8
tokatakanahalfwidth;FF84
tonebarextrahighmod;02E5
tonebarextralowmod;02E9
tonebarhighmod;02E6
tonebarlowmod;02E8
tonebarmidmod;02E7
tonefive;01BD
tonesix;0185
tonetwo;01A8
tonos;0384
tonsquare;3327
topatakthai;0E0F
tortoiseshellbracketleft;3014
tortoiseshellbracketleftsmall;FE5D
tortoiseshellbracketleftvertical;FE39
tortoiseshellbracketright;3015
tortoiseshellbracketrightsmall;FE5E
tortoiseshellbracketrightvertical;FE3A
totaothai;0E15
tpalatalhook;01AB
tparen;24AF
trademark;2122
trademarksans;F8EA
trademarkserif;F6DB
tretroflexhook;0288
triagdn;25BC
triaglf;25C4
triagrt;25BA
triagup;25B2
ts;02A6
tsadi;05E6
tsadidagesh;FB46
tsadidageshhebrew;FB46
tsadihebrew;05E6
tsecyrillic;0446
tsere;05B5
tsere12;05B5
tsere1e;05B5
tsere2b;05B5
tserehebrew;05B5
tserenarrowhebrew;05B5
tserequarterhebrew;05B5
tserewidehebrew;05B5
tshecyrillic;045B
tsuperior;F6F3
ttabengali;099F
ttadeva;091F
ttagujarati;0A9F
ttagurmukhi;0A1F
tteharabic;0679
ttehfinalarabic;FB67
ttehinitialarabic;FB68
ttehmedialarabic;FB69
tthabengali;09A0
tthadeva;0920
tthagujarati;0AA0
tthagurmukhi;0A20
tturned;0287
tuhiragana;3064
tukatakana;30C4
tukatakanahalfwidth;FF82
tusmallhiragana;3063
tusmallkatakana;30C3
tusmallkatakanahalfwidth;FF6F
twelvecircle;246B
twelveparen;247F
twelveperiod;2493
twelveroman;217B
twentycircle;2473
twentyhangzhou;5344
twentyparen;2487
twentyperiod;249B
two;0032
twoarabic;0662
twobengali;09E8
twocircle;2461
twocircleinversesansserif;278B
twodeva;0968
twodotenleader;2025
twodotleader;2025
twodotleadervertical;FE30
twogujarati;0AE8
twogurmukhi;0A68
twohackarabic;0662
twohangzhou;3022
twoideographicparen;3221
twoinferior;2082
twomonospace;FF12
twonumeratorbengali;09F5
twooldstyle;F732
twoparen;2475
twoperiod;2489
twopersian;06F2
tworoman;2171
twostroke;01BB
twosuperior;00B2
twothai;0E52
twothirds;2154
u;0075
uacute;00FA
ubar;0289
ubengali;0989
ubopomofo;3128
ubreve;016D
ucaron;01D4
ucircle;24E4
ucircumflex;00FB
ucircumflexbelow;1E77
ucyrillic;0443
udattadeva;0951
udblacute;0171
udblgrave;0215
udeva;0909
udieresis;00FC
udieresisacute;01D8
udieresisbelow;1E73
udieresiscaron;01DA
udieresiscyrillic;04F1
udieresisgrave;01DC
udieresismacron;01D6
udotbelow;1EE5
ugrave;00F9
ugujarati;0A89
ugurmukhi;0A09
uhiragana;3046
uhookabove;1EE7
uhorn;01B0
uhornacute;1EE9
uhorndotbelow;1EF1
uhorngrave;1EEB
uhornhookabove;1EED
uhorntilde;1EEF
uhungarumlaut;0171
uhungarumlautcyrillic;04F3
uinvertedbreve;0217
ukatakana;30A6
ukatakanahalfwidth;FF73
ukcyrillic;0479
ukorean;315C
umacron;016B
umacroncyrillic;04EF
umacrondieresis;1E7B
umatragurmukhi;0A41
umonospace;FF55
underscore;005F
underscoredbl;2017
underscoremonospace;FF3F
underscorevertical;FE33
underscorewavy;FE4F
union;222A
universal;2200
uogonek;0173
uparen;24B0
upblock;2580
upperdothebrew;05C4
upsilon;03C5
upsilondieresis;03CB
upsilondieresistonos;03B0
upsilonlatin;028A
upsilontonos;03CD
uptackbelowcmb;031D
uptackmod;02D4
uragurmukhi;0A73
uring;016F
ushortcyrillic;045E
usmallhiragana;3045
usmallkatakana;30A5
usmallkatakanahalfwidth;FF69
ustraightcyrillic;04AF
ustraightstrokecyrillic;04B1
utilde;0169
utildeacute;1E79
utildebelow;1E75
uubengali;098A
uudeva;090A
uugujarati;0A8A
uugurmukhi;0A0A
uumatragurmukhi;0A42
uuvowelsignbengali;09C2
uuvowelsigndeva;0942
uuvowelsigngujarati;0AC2
uvowelsignbengali;09C1
uvowelsigndeva;0941
uvowelsigngujarati;0AC1
v;0076
vadeva;0935
vagujarati;0AB5
vagurmukhi;0A35
vakatakana;30F7
vav;05D5
vavdagesh;FB35
vavdagesh65;FB35
vavdageshhebrew;FB35
vavhebrew;05D5
vavholam;FB4B
vavholamhebrew;FB4B
vavvavhebrew;05F0
vavyodhebrew;05F1
vcircle;24E5
vdotbelow;1E7F
vecyrillic;0432
veharabic;06A4
vehfinalarabic;FB6B
vehinitialarabic;FB6C
vehmedialarabic;FB6D
vekatakana;30F9
venus;2640
verticalbar;007C
verticallineabovecmb;030D
verticallinebelowcmb;0329
verticallinelowmod;02CC
verticallinemod;02C8
vewarmenian;057E
vhook;028B
vikatakana;30F8
viramabengali;09CD
viramadeva;094D
viramagujarati;0ACD
visargabengali;0983
visargadeva;0903
visargagujarati;0A83
vmonospace;FF56
voarmenian;0578
voicediterationhiragana;309E
voicediterationkatakana;30FE
voicedmarkkana;309B
voicedmarkkanahalfwidth;FF9E
vokatakana;30FA
vparen;24B1
vtilde;1E7D
vturned;028C
vuhiragana;3094
vukatakana;30F4
w;0077
wacute;1E83
waekorean;3159
wahiragana;308F
wakatakana;30EF
wakatakanahalfwidth;FF9C
wakorean;3158
wasmallhiragana;308E
wasmallkatakana;30EE
wattosquare;3357
wavedash;301C
wavyunderscorevertical;FE34
wawarabic;0648
wawfinalarabic;FEEE
wawhamzaabovearabic;0624
wawhamzaabovefinalarabic;FE86
wbsquare;33DD
wcircle;24E6
wcircumflex;0175
wdieresis;1E85
wdotaccent;1E87
wdotbelow;1E89
wehiragana;3091
weierstrass;2118
wekatakana;30F1
wekorean;315E
weokorean;315D
wgrave;1E81
whitebullet;25E6
whitecircle;25CB
whitecircleinverse;25D9
whitecornerbracketleft;300E
whitecornerbracketleftvertical;FE43
whitecornerbracketright;300F
whitecornerbracketrightvertical;FE44
whitediamond;25C7
whitediamondcontainingblacksmalldiamond;25C8
whitedownpointingsmalltriangle;25BF
whitedownpointingtriangle;25BD
whiteleftpointingsmalltriangle;25C3
whiteleftpointingtriangle;25C1
whitelenticularbracketleft;3016
whitelenticularbracketright;3017
whiterightpointingsmalltriangle;25B9
whiterightpointingtriangle;25B7
whitesmallsquare;25AB
whitesmilingface;263A
whitesquare;25A1
whitestar;2606
whitetelephone;260F
whitetortoiseshellbracketleft;3018
whitetortoiseshellbracketright;3019
whiteuppointingsmalltriangle;25B5
whiteuppointingtriangle;25B3
wihiragana;3090
wikatakana;30F0
wikorean;315F
wmonospace;FF57
wohiragana;3092
wokatakana;30F2
wokatakanahalfwidth;FF66
won;20A9
wonmonospace;FFE6
wowaenthai;0E27
wparen;24B2
wring;1E98
wsuperior;02B7
wturned;028D
wynn;01BF
x;0078
xabovecmb;033D
xbopomofo;3112
xcircle;24E7
xdieresis;1E8D
xdotaccent;1E8B
xeharmenian;056D
xi;03BE
xmonospace;FF58
xparen;24B3
xsuperior;02E3
y;0079
yaadosquare;334E
yabengali;09AF
yacute;00FD
yadeva;092F
yaekorean;3152
yagujarati;0AAF
yagurmukhi;0A2F
yahiragana;3084
yakatakana;30E4
yakatakanahalfwidth;FF94
yakorean;3151
yamakkanthai;0E4E
yasmallhiragana;3083
yasmallkatakana;30E3
yasmallkatakanahalfwidth;FF6C
yatcyrillic;0463
ycircle;24E8
ycircumflex;0177
ydieresis;00FF
ydotaccent;1E8F
ydotbelow;1EF5
yeharabic;064A
yehbarreearabic;06D2
yehbarreefinalarabic;FBAF
yehfinalarabic;FEF2
yehhamzaabovearabic;0626
yehhamzaabovefinalarabic;FE8A
yehhamzaaboveinitialarabic;FE8B
yehhamzaabovemedialarabic;FE8C
yehinitialarabic;FEF3
yehmedialarabic;FEF4
yehmeeminitialarabic;FCDD
yehmeemisolatedarabic;FC58
yehnoonfinalarabic;FC94
yehthreedotsbelowarabic;06D1
yekorean;3156
yen;00A5
yenmonospace;FFE5
yeokorean;3155
yeorinhieuhkorean;3186
yerahbenyomohebrew;05AA
yerahbenyomolefthebrew;05AA
yericyrillic;044B
yerudieresiscyrillic;04F9
yesieungkorean;3181
yesieungpansioskorean;3183
yesieungsioskorean;3182
yetivhebrew;059A
ygrave;1EF3
yhook;01B4
yhookabove;1EF7
yiarmenian;0575
yicyrillic;0457
yikorean;3162
yinyang;262F
yiwnarmenian;0582
ymonospace;FF59
yod;05D9
yoddagesh;FB39
yoddageshhebrew;FB39
yodhebrew;05D9
yodyodhebrew;05F2
yodyodpatahhebrew;FB1F
yohiragana;3088
yoikorean;3189
yokatakana;30E8
yokatakanahalfwidth;FF96
yokorean;315B
yosmallhiragana;3087
yosmallkatakana;30E7
yosmallkatakanahalfwidth;FF6E
yotgreek;03F3
yoyaekorean;3188
yoyakorean;3187
yoyakthai;0E22
yoyingthai;0E0D
yparen;24B4
ypogegrammeni;037A
ypogegrammenigreekcmb;0345
yr;01A6
yring;1E99
ysuperior;02B8
ytilde;1EF9
yturned;028E
yuhiragana;3086
yuikorean;318C
yukatakana;30E6
yukatakanahalfwidth;FF95
yukorean;3160
yusbigcyrillic;046B
yusbigiotifiedcyrillic;046D
yuslittlecyrillic;0467
yuslittleiotifiedcyrillic;0469
yusmallhiragana;3085
yusmallkatakana;30E5
yusmallkatakanahalfwidth;FF6D
yuyekorean;318B
yuyeokorean;318A
yyabengali;09DF
yyadeva;095F
z;007A
zaarmenian;0566
zacute;017A
zadeva;095B
zagurmukhi;0A5B
zaharabic;0638
zahfinalarabic;FEC6
zahinitialarabic;FEC7
zahiragana;3056
zahmedialarabic;FEC8
zainarabic;0632
zainfinalarabic;FEB0
zakatakana;30B6
zaqefgadolhebrew;0595
zaqefqatanhebrew;0594
zarqahebrew;0598
zayin;05D6
zayindagesh;FB36
zayindageshhebrew;FB36
zayinhebrew;05D6
zbopomofo;3117
zcaron;017E
zcircle;24E9
zcircumflex;1E91
zcurl;0291
zdot;017C
zdotaccent;017C
zdotbelow;1E93
zecyrillic;0437
zedescendercyrillic;0499
zedieresiscyrillic;04DF
zehiragana;305C
zekatakana;30BC
zero;0030
zeroarabic;0660
zerobengali;09E6
zerodeva;0966
zerogujarati;0AE6
zerogurmukhi;0A66
zerohackarabic;0660
zeroinferior;2080
zeromonospace;FF10
zerooldstyle;F730
zeropersian;06F0
zerosuperior;2070
zerothai;0E50
zerowidthjoiner;FEFF
zerowidthnonjoiner;200C
zerowidthspace;200B
zeta;03B6
zhbopomofo;3113
zhearmenian;056A
zhebrevecyrillic;04C2
zhecyrillic;0436
zhedescendercyrillic;0497
zhedieresiscyrillic;04DD
zihiragana;3058
zikatakana;30B8
zinorhebrew;05AE
zlinebelow;1E95
zmonospace;FF5A
zohiragana;305E
zokatakana;30BE
zparen;24B5
zretroflexhook;0290
zstroke;01B6
zuhiragana;305A
zukatakana;30BA
# END
"""


_aglfnText = """\
# -----------------------------------------------------------
# Copyright 2002-2019 Adobe (http://www.adobe.com/).
#
# Redistribution and use in source and binary forms, with or
# without modification, are permitted provided that the
# following conditions are met:
#
# Redistributions of source code must retain the above
# copyright notice, this list of conditions and the following
# disclaimer.
#
# Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following
# disclaimer in the documentation and/or other materials
# provided with the distribution.
#
# Neither the name of Adobe nor the names of its contributors
# may be used to endorse or promote products derived from this
# software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
# CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# -----------------------------------------------------------
# Name:          Adobe Glyph List For New Fonts
# Table version: 1.7
# Date:          November 6, 2008
# URL:           https://github.com/adobe-type-tools/agl-aglfn
#
# Description:
#
# AGLFN (Adobe Glyph List For New Fonts) provides a list of base glyph
# names that are recommended for new fonts, which are compatible with
# the AGL (Adobe Glyph List) Specification, and which should be used
# as described in Section 6 of that document. AGLFN comprises the set
# of glyph names from AGL that map via the AGL Specification rules to
# the semantically correct UV (Unicode Value). For example, "Asmall"
# is omitted because AGL maps this glyph name to the PUA (Private Use
# Area) value U+F761, rather than to the UV that maps from the glyph
# name "A." Also omitted is "ffi," because AGL maps this to the
# Alphabetic Presentation Forms value U+FB03, rather than decomposing
# it into the following sequence of three UVs: U+0066, U+0066, and
# U+0069. The name "arrowvertex" has been omitted because this glyph
# now has a real UV, and AGL is now incorrect in mapping it to the PUA
# value U+F8E6. If you do not find an appropriate name for your glyph
# in this list, then please refer to Section 6 of the AGL
# Specification.
#
# Format: three semicolon-delimited fields:
#   (1) Standard UV or CUS UV--four uppercase hexadecimal digits
#   (2) Glyph name--upper/lowercase letters and digits
#   (3) Character names: Unicode character names for standard UVs, and
#       descriptive names for CUS UVs--uppercase letters, hyphen, and
#       space
#
# The records are sorted by glyph name in increasing ASCII order,
# entries with the same glyph name are sorted in decreasing priority
# order, the UVs and Unicode character names are provided for
# convenience, lines starting with "#" are comments, and blank lines
# should be ignored.
#
# Revision History:
#
# 1.7 [6 November 2008]
# - Reverted to the original 1.4 and earlier mappings for Delta,
#   Omega, and mu.
# - Removed mappings for "afii" names. These should now be assigned
#   "uni" names.
# - Removed mappings for "commaaccent" names. These should now be
#   assigned "uni" names.
#
# 1.6 [30 January 2006]
# - Completed work intended in 1.5.
#
# 1.5 [23 November 2005]
# - Removed duplicated block at end of file.
# - Changed mappings:
#   2206;Delta;INCREMENT changed to 0394;Delta;GREEK CAPITAL LETTER DELTA
#   2126;Omega;OHM SIGN changed to 03A9;Omega;GREEK CAPITAL LETTER OMEGA
#   03BC;mu;MICRO SIGN changed to 03BC;mu;GREEK SMALL LETTER MU
# - Corrected statement above about why "ffi" is omitted.
#
# 1.4 [24 September 2003]
# - Changed version to 1.4, to avoid confusion with the AGL 1.3.
# - Fixed spelling errors in the header.
# - Fully removed "arrowvertex," as it is mapped only to a PUA Unicode
#   value in some fonts.
#
# 1.1 [17 April 2003]
# - Renamed [Tt]cedilla back to [Tt]commaaccent.
#
# 1.0 [31 January 2003]
# - Original version.
# - Derived from the AGLv1.2 by:
#   removing the PUA area codes;
#   removing duplicate Unicode mappings; and
#   renaming "tcommaaccent" to "tcedilla" and "Tcommaaccent" to "Tcedilla"
#
0041;A;LATIN CAPITAL LETTER A
00C6;AE;LATIN CAPITAL LETTER AE
01FC;AEacute;LATIN CAPITAL LETTER AE WITH ACUTE
00C1;Aacute;LATIN CAPITAL LETTER A WITH ACUTE
0102;Abreve;LATIN CAPITAL LETTER A WITH BREVE
00C2;Acircumflex;LATIN CAPITAL LETTER A WITH CIRCUMFLEX
00C4;Adieresis;LATIN CAPITAL LETTER A WITH DIAERESIS
00C0;Agrave;LATIN CAPITAL LETTER A WITH GRAVE
0391;Alpha;GREEK CAPITAL LETTER ALPHA
0386;Alphatonos;GREEK CAPITAL LETTER ALPHA WITH TONOS
0100;Amacron;LATIN CAPITAL LETTER A WITH MACRON
0104;Aogonek;LATIN CAPITAL LETTER A WITH OGONEK
00C5;Aring;LATIN CAPITAL LETTER A WITH RING ABOVE
01FA;Aringacute;LATIN CAPITAL LETTER A WITH RING ABOVE AND ACUTE
00C3;Atilde;LATIN CAPITAL LETTER A WITH TILDE
0042;B;LATIN CAPITAL LETTER B
0392;Beta;GREEK CAPITAL LETTER BETA
0043;C;LATIN CAPITAL LETTER C
0106;Cacute;LATIN CAPITAL LETTER C WITH ACUTE
010C;Ccaron;LATIN CAPITAL LETTER C WITH CARON
00C7;Ccedilla;LATIN CAPITAL LETTER C WITH CEDILLA
0108;Ccircumflex;LATIN CAPITAL LETTER C WITH CIRCUMFLEX
010A;Cdotaccent;LATIN CAPITAL LETTER C WITH DOT ABOVE
03A7;Chi;GREEK CAPITAL LETTER CHI
0044;D;LATIN CAPITAL LETTER D
010E;Dcaron;LATIN CAPITAL LETTER D WITH CARON
0110;Dcroat;LATIN CAPITAL LETTER D WITH STROKE
2206;Delta;INCREMENT
0045;E;LATIN CAPITAL LETTER E
00C9;Eacute;LATIN CAPITAL LETTER E WITH ACUTE
0114;Ebreve;LATIN CAPITAL LETTER E WITH BREVE
011A;Ecaron;LATIN CAPITAL LETTER E WITH CARON
00CA;Ecircumflex;LATIN CAPITAL LETTER E WITH CIRCUMFLEX
00CB;Edieresis;LATIN CAPITAL LETTER E WITH DIAERESIS
0116;Edotaccent;LATIN CAPITAL LETTER E WITH DOT ABOVE
00C8;Egrave;LATIN CAPITAL LETTER E WITH GRAVE
0112;Emacron;LATIN CAPITAL LETTER E WITH MACRON
014A;Eng;LATIN CAPITAL LETTER ENG
0118;Eogonek;LATIN CAPITAL LETTER E WITH OGONEK
0395;Epsilon;GREEK CAPITAL LETTER EPSILON
0388;Epsilontonos;GREEK CAPITAL LETTER EPSILON WITH TONOS
0397;Eta;GREEK CAPITAL LETTER ETA
0389;Etatonos;GREEK CAPITAL LETTER ETA WITH TONOS
00D0;Eth;LATIN CAPITAL LETTER ETH
20AC;Euro;EURO SIGN
0046;F;LATIN CAPITAL LETTER F
0047;G;LATIN CAPITAL LETTER G
0393;Gamma;GREEK CAPITAL LETTER GAMMA
011E;Gbreve;LATIN CAPITAL LETTER G WITH BREVE
01E6;Gcaron;LATIN CAPITAL LETTER G WITH CARON
011C;Gcircumflex;LATIN CAPITAL LETTER G WITH CIRCUMFLEX
0120;Gdotaccent;LATIN CAPITAL LETTER G WITH DOT ABOVE
0048;H;LATIN CAPITAL LETTER H
25CF;H18533;BLACK CIRCLE
25AA;H18543;BLACK SMALL SQUARE
25AB;H18551;WHITE SMALL SQUARE
25A1;H22073;WHITE SQUARE
0126;Hbar;LATIN CAPITAL LETTER H WITH STROKE
0124;Hcircumflex;LATIN CAPITAL LETTER H WITH CIRCUMFLEX
0049;I;LATIN CAPITAL LETTER I
0132;IJ;LATIN CAPITAL LIGATURE IJ
00CD;Iacute;LATIN CAPITAL LETTER I WITH ACUTE
012C;Ibreve;LATIN CAPITAL LETTER I WITH BREVE
00CE;Icircumflex;LATIN CAPITAL LETTER I WITH CIRCUMFLEX
00CF;Idieresis;LATIN CAPITAL LETTER I WITH DIAERESIS
0130;Idotaccent;LATIN CAPITAL LETTER I WITH DOT ABOVE
2111;Ifraktur;BLACK-LETTER CAPITAL I
00CC;Igrave;LATIN CAPITAL LETTER I WITH GRAVE
012A;Imacron;LATIN CAPITAL LETTER I WITH MACRON
012E;Iogonek;LATIN CAPITAL LETTER I WITH OGONEK
0399;Iota;GREEK CAPITAL LETTER IOTA
03AA;Iotadieresis;GREEK CAPITAL LETTER IOTA WITH DIALYTIKA
038A;Iotatonos;GREEK CAPITAL LETTER IOTA WITH TONOS
0128;Itilde;LATIN CAPITAL LETTER I WITH TILDE
004A;J;LATIN CAPITAL LETTER J
0134;Jcircumflex;LATIN CAPITAL LETTER J WITH CIRCUMFLEX
004B;K;LATIN CAPITAL LETTER K
039A;Kappa;GREEK CAPITAL LETTER KAPPA
004C;L;LATIN CAPITAL LETTER L
0139;Lacute;LATIN CAPITAL LETTER L WITH ACUTE
039B;Lambda;GREEK CAPITAL LETTER LAMDA
013D;Lcaron;LATIN CAPITAL LETTER L WITH CARON
013F;Ldot;LATIN CAPITAL LETTER L WITH MIDDLE DOT
0141;Lslash;LATIN CAPITAL LETTER L WITH STROKE
004D;M;LATIN CAPITAL LETTER M
039C;Mu;GREEK CAPITAL LETTER MU
004E;N;LATIN CAPITAL LETTER N
0143;Nacute;LATIN CAPITAL LETTER N WITH ACUTE
0147;Ncaron;LATIN CAPITAL LETTER N WITH CARON
00D1;Ntilde;LATIN CAPITAL LETTER N WITH TILDE
039D;Nu;GREEK CAPITAL LETTER NU
004F;O;LATIN CAPITAL LETTER O
0152;OE;LATIN CAPITAL LIGATURE OE
00D3;Oacute;LATIN CAPITAL LETTER O WITH ACUTE
014E;Obreve;LATIN CAPITAL LETTER O WITH BREVE
00D4;Ocircumflex;LATIN CAPITAL LETTER O WITH CIRCUMFLEX
00D6;Odieresis;LATIN CAPITAL LETTER O WITH DIAERESIS
00D2;Ograve;LATIN CAPITAL LETTER O WITH GRAVE
01A0;Ohorn;LATIN CAPITAL LETTER O WITH HORN
0150;Ohungarumlaut;LATIN CAPITAL LETTER O WITH DOUBLE ACUTE
014C;Omacron;LATIN CAPITAL LETTER O WITH MACRON
2126;Omega;OHM SIGN
038F;Omegatonos;GREEK CAPITAL LETTER OMEGA WITH TONOS
039F;Omicron;GREEK CAPITAL LETTER OMICRON
038C;Omicrontonos;GREEK CAPITAL LETTER OMICRON WITH TONOS
00D8;Oslash;LATIN CAPITAL LETTER O WITH STROKE
01FE;Oslashacute;LATIN CAPITAL LETTER O WITH STROKE AND ACUTE
00D5;Otilde;LATIN CAPITAL LETTER O WITH TILDE
0050;P;LATIN CAPITAL LETTER P
03A6;Phi;GREEK CAPITAL LETTER PHI
03A0;Pi;GREEK CAPITAL LETTER PI
03A8;Psi;GREEK CAPITAL LETTER PSI
0051;Q;LATIN CAPITAL LETTER Q
0052;R;LATIN CAPITAL LETTER R
0154;Racute;LATIN CAPITAL LETTER R WITH ACUTE
0158;Rcaron;LATIN CAPITAL LETTER R WITH CARON
211C;Rfraktur;BLACK-LETTER CAPITAL R
03A1;Rho;GREEK CAPITAL LETTER RHO
0053;S;LATIN CAPITAL LETTER S
250C;SF010000;BOX DRAWINGS LIGHT DOWN AND RIGHT
2514;SF020000;BOX DRAWINGS LIGHT UP AND RIGHT
2510;SF030000;BOX DRAWINGS LIGHT DOWN AND LEFT
2518;SF040000;BOX DRAWINGS LIGHT UP AND LEFT
253C;SF050000;BOX DRAWINGS LIGHT VERTICAL AND HORIZONTAL
252C;SF060000;BOX DRAWINGS LIGHT DOWN AND HORIZONTAL
2534;SF070000;BOX DRAWINGS LIGHT UP AND HORIZONTAL
251C;SF080000;BOX DRAWINGS LIGHT VERTICAL AND RIGHT
2524;SF090000;BOX DRAWINGS LIGHT VERTICAL AND LEFT
2500;SF100000;BOX DRAWINGS LIGHT HORIZONTAL
2502;SF110000;BOX DRAWINGS LIGHT VERTICAL
2561;SF190000;BOX DRAWINGS VERTICAL SINGLE AND LEFT DOUBLE
2562;SF200000;BOX DRAWINGS VERTICAL DOUBLE AND LEFT SINGLE
2556;SF210000;BOX DRAWINGS DOWN DOUBLE AND LEFT SINGLE
2555;SF220000;BOX DRAWINGS DOWN SINGLE AND LEFT DOUBLE
2563;SF230000;BOX DRAWINGS DOUBLE VERTICAL AND LEFT
2551;SF240000;BOX DRAWINGS DOUBLE VERTICAL
2557;SF250000;BOX DRAWINGS DOUBLE DOWN AND LEFT
255D;SF260000;BOX DRAWINGS DOUBLE UP AND LEFT
255C;SF270000;BOX DRAWINGS UP DOUBLE AND LEFT SINGLE
255B;SF280000;BOX DRAWINGS UP SINGLE AND LEFT DOUBLE
255E;SF360000;BOX DRAWINGS VERTICAL SINGLE AND RIGHT DOUBLE
255F;SF370000;BOX DRAWINGS VERTICAL DOUBLE AND RIGHT SINGLE
255A;SF380000;BOX DRAWINGS DOUBLE UP AND RIGHT
2554;SF390000;BOX DRAWINGS DOUBLE DOWN AND RIGHT
2569;SF400000;BOX DRAWINGS DOUBLE UP AND HORIZONTAL
2566;SF410000;BOX DRAWINGS DOUBLE DOWN AND HORIZONTAL
2560;SF420000;BOX DRAWINGS DOUBLE VERTICAL AND RIGHT
2550;SF430000;BOX DRAWINGS DOUBLE HORIZONTAL
256C;SF440000;BOX DRAWINGS DOUBLE VERTICAL AND HORIZONTAL
2567;SF450000;BOX DRAWINGS UP SINGLE AND HORIZONTAL DOUBLE
2568;SF460000;BOX DRAWINGS UP DOUBLE AND HORIZONTAL SINGLE
2564;SF470000;BOX DRAWINGS DOWN SINGLE AND HORIZONTAL DOUBLE
2565;SF480000;BOX DRAWINGS DOWN DOUBLE AND HORIZONTAL SINGLE
2559;SF490000;BOX DRAWINGS UP DOUBLE AND RIGHT SINGLE
2558;SF500000;BOX DRAWINGS UP SINGLE AND RIGHT DOUBLE
2552;SF510000;BOX DRAWINGS DOWN SINGLE AND RIGHT DOUBLE
2553;SF520000;BOX DRAWINGS DOWN DOUBLE AND RIGHT SINGLE
256B;SF530000;BOX DRAWINGS VERTICAL DOUBLE AND HORIZONTAL SINGLE
256A;SF540000;BOX DRAWINGS VERTICAL SINGLE AND HORIZONTAL DOUBLE
015A;Sacute;LATIN CAPITAL LETTER S WITH ACUTE
0160;Scaron;LATIN CAPITAL LETTER S WITH CARON
015E;Scedilla;LATIN CAPITAL LETTER S WITH CEDILLA
015C;Scircumflex;LATIN CAPITAL LETTER S WITH CIRCUMFLEX
03A3;Sigma;GREEK CAPITAL LETTER SIGMA
0054;T;LATIN CAPITAL LETTER T
03A4;Tau;GREEK CAPITAL LETTER TAU
0166;Tbar;LATIN CAPITAL LETTER T WITH STROKE
0164;Tcaron;LATIN CAPITAL LETTER T WITH CARON
0398;Theta;GREEK CAPITAL LETTER THETA
00DE;Thorn;LATIN CAPITAL LETTER THORN
0055;U;LATIN CAPITAL LETTER U
00DA;Uacute;LATIN CAPITAL LETTER U WITH ACUTE
016C;Ubreve;LATIN CAPITAL LETTER U WITH BREVE
00DB;Ucircumflex;LATIN CAPITAL LETTER U WITH CIRCUMFLEX
00DC;Udieresis;LATIN CAPITAL LETTER U WITH DIAERESIS
00D9;Ugrave;LATIN CAPITAL LETTER U WITH GRAVE
01AF;Uhorn;LATIN CAPITAL LETTER U WITH HORN
0170;Uhungarumlaut;LATIN CAPITAL LETTER U WITH DOUBLE ACUTE
016A;Umacron;LATIN CAPITAL LETTER U WITH MACRON
0172;Uogonek;LATIN CAPITAL LETTER U WITH OGONEK
03A5;Upsilon;GREEK CAPITAL LETTER UPSILON
03D2;Upsilon1;GREEK UPSILON WITH HOOK SYMBOL
03AB;Upsilondieresis;GREEK CAPITAL LETTER UPSILON WITH DIALYTIKA
038E;Upsilontonos;GREEK CAPITAL LETTER UPSILON WITH TONOS
016E;Uring;LATIN CAPITAL LETTER U WITH RING ABOVE
0168;Utilde;LATIN CAPITAL LETTER U WITH TILDE
0056;V;LATIN CAPITAL LETTER V
0057;W;LATIN CAPITAL LETTER W
1E82;Wacute;LATIN CAPITAL LETTER W WITH ACUTE
0174;Wcircumflex;LATIN CAPITAL LETTER W WITH CIRCUMFLEX
1E84;Wdieresis;LATIN CAPITAL LETTER W WITH DIAERESIS
1E80;Wgrave;LATIN CAPITAL LETTER W WITH GRAVE
0058;X;LATIN CAPITAL LETTER X
039E;Xi;GREEK CAPITAL LETTER XI
0059;Y;LATIN CAPITAL LETTER Y
00DD;Yacute;LATIN CAPITAL LETTER Y WITH ACUTE
0176;Ycircumflex;LATIN CAPITAL LETTER Y WITH CIRCUMFLEX
0178;Ydieresis;LATIN CAPITAL LETTER Y WITH DIAERESIS
1EF2;Ygrave;LATIN CAPITAL LETTER Y WITH GRAVE
005A;Z;LATIN CAPITAL LETTER Z
0179;Zacute;LATIN CAPITAL LETTER Z WITH ACUTE
017D;Zcaron;LATIN CAPITAL LETTER Z WITH CARON
017B;Zdotaccent;LATIN CAPITAL LETTER Z WITH DOT ABOVE
0396;Zeta;GREEK CAPITAL LETTER ZETA
0061;a;LATIN SMALL LETTER A
00E1;aacute;LATIN SMALL LETTER A WITH ACUTE
0103;abreve;LATIN SMALL LETTER A WITH BREVE
00E2;acircumflex;LATIN SMALL LETTER A WITH CIRCUMFLEX
00B4;acute;ACUTE ACCENT
0301;acutecomb;COMBINING ACUTE ACCENT
00E4;adieresis;LATIN SMALL LETTER A WITH DIAERESIS
00E6;ae;LATIN SMALL LETTER AE
01FD;aeacute;LATIN SMALL LETTER AE WITH ACUTE
00E0;agrave;LATIN SMALL LETTER A WITH GRAVE
2135;aleph;ALEF SYMBOL
03B1;alpha;GREEK SMALL LETTER ALPHA
03AC;alphatonos;GREEK SMALL LETTER ALPHA WITH TONOS
0101;amacron;LATIN SMALL LETTER A WITH MACRON
0026;ampersand;AMPERSAND
2220;angle;ANGLE
2329;angleleft;LEFT-POINTING ANGLE BRACKET
232A;angleright;RIGHT-POINTING ANGLE BRACKET
0387;anoteleia;GREEK ANO TELEIA
0105;aogonek;LATIN SMALL LETTER A WITH OGONEK
2248;approxequal;ALMOST EQUAL TO
00E5;aring;LATIN SMALL LETTER A WITH RING ABOVE
01FB;aringacute;LATIN SMALL LETTER A WITH RING ABOVE AND ACUTE
2194;arrowboth;LEFT RIGHT ARROW
21D4;arrowdblboth;LEFT RIGHT DOUBLE ARROW
21D3;arrowdbldown;DOWNWARDS DOUBLE ARROW
21D0;arrowdblleft;LEFTWARDS DOUBLE ARROW
21D2;arrowdblright;RIGHTWARDS DOUBLE ARROW
21D1;arrowdblup;UPWARDS DOUBLE ARROW
2193;arrowdown;DOWNWARDS ARROW
2190;arrowleft;LEFTWARDS ARROW
2192;arrowright;RIGHTWARDS ARROW
2191;arrowup;UPWARDS ARROW
2195;arrowupdn;UP DOWN ARROW
21A8;arrowupdnbse;UP DOWN ARROW WITH BASE
005E;asciicircum;CIRCUMFLEX ACCENT
007E;asciitilde;TILDE
002A;asterisk;ASTERISK
2217;asteriskmath;ASTERISK OPERATOR
0040;at;COMMERCIAL AT
00E3;atilde;LATIN SMALL LETTER A WITH TILDE
0062;b;LATIN SMALL LETTER B
005C;backslash;REVERSE SOLIDUS
007C;bar;VERTICAL LINE
03B2;beta;GREEK SMALL LETTER BETA
2588;block;FULL BLOCK
007B;braceleft;LEFT CURLY BRACKET
007D;braceright;RIGHT CURLY BRACKET
005B;bracketleft;LEFT SQUARE BRACKET
005D;bracketright;RIGHT SQUARE BRACKET
02D8;breve;BREVE
00A6;brokenbar;BROKEN BAR
2022;bullet;BULLET
0063;c;LATIN SMALL LETTER C
0107;cacute;LATIN SMALL LETTER C WITH ACUTE
02C7;caron;CARON
21B5;carriagereturn;DOWNWARDS ARROW WITH CORNER LEFTWARDS
010D;ccaron;LATIN SMALL LETTER C WITH CARON
00E7;ccedilla;LATIN SMALL LETTER C WITH CEDILLA
0109;ccircumflex;LATIN SMALL LETTER C WITH CIRCUMFLEX
010B;cdotaccent;LATIN SMALL LETTER C WITH DOT ABOVE
00B8;cedilla;CEDILLA
00A2;cent;CENT SIGN
03C7;chi;GREEK SMALL LETTER CHI
25CB;circle;WHITE CIRCLE
2297;circlemultiply;CIRCLED TIMES
2295;circleplus;CIRCLED PLUS
02C6;circumflex;MODIFIER LETTER CIRCUMFLEX ACCENT
2663;club;BLACK CLUB SUIT
003A;colon;COLON
20A1;colonmonetary;COLON SIGN
002C;comma;COMMA
2245;congruent;APPROXIMATELY EQUAL TO
00A9;copyright;COPYRIGHT SIGN
00A4;currency;CURRENCY SIGN
0064;d;LATIN SMALL LETTER D
2020;dagger;DAGGER
2021;daggerdbl;DOUBLE DAGGER
010F;dcaron;LATIN SMALL LETTER D WITH CARON
0111;dcroat;LATIN SMALL LETTER D WITH STROKE
00B0;degree;DEGREE SIGN
03B4;delta;GREEK SMALL LETTER DELTA
2666;diamond;BLACK DIAMOND SUIT
00A8;dieresis;DIAERESIS
0385;dieresistonos;GREEK DIALYTIKA TONOS
00F7;divide;DIVISION SIGN
2593;dkshade;DARK SHADE
2584;dnblock;LOWER HALF BLOCK
0024;dollar;DOLLAR SIGN
20AB;dong;DONG SIGN
02D9;dotaccent;DOT ABOVE
0323;dotbelowcomb;COMBINING DOT BELOW
0131;dotlessi;LATIN SMALL LETTER DOTLESS I
22C5;dotmath;DOT OPERATOR
0065;e;LATIN SMALL LETTER E
00E9;eacute;LATIN SMALL LETTER E WITH ACUTE
0115;ebreve;LATIN SMALL LETTER E WITH BREVE
011B;ecaron;LATIN SMALL LETTER E WITH CARON
00EA;ecircumflex;LATIN SMALL LETTER E WITH CIRCUMFLEX
00EB;edieresis;LATIN SMALL LETTER E WITH DIAERESIS
0117;edotaccent;LATIN SMALL LETTER E WITH DOT ABOVE
00E8;egrave;LATIN SMALL LETTER E WITH GRAVE
0038;eight;DIGIT EIGHT
2208;element;ELEMENT OF
2026;ellipsis;HORIZONTAL ELLIPSIS
0113;emacron;LATIN SMALL LETTER E WITH MACRON
2014;emdash;EM DASH
2205;emptyset;EMPTY SET
2013;endash;EN DASH
014B;eng;LATIN SMALL LETTER ENG
0119;eogonek;LATIN SMALL LETTER E WITH OGONEK
03B5;epsilon;GREEK SMALL LETTER EPSILON
03AD;epsilontonos;GREEK SMALL LETTER EPSILON WITH TONOS
003D;equal;EQUALS SIGN
2261;equivalence;IDENTICAL TO
212E;estimated;ESTIMATED SYMBOL
03B7;eta;GREEK SMALL LETTER ETA
03AE;etatonos;GREEK SMALL LETTER ETA WITH TONOS
00F0;eth;LATIN SMALL LETTER ETH
0021;exclam;EXCLAMATION MARK
203C;exclamdbl;DOUBLE EXCLAMATION MARK
00A1;exclamdown;INVERTED EXCLAMATION MARK
2203;existential;THERE EXISTS
0066;f;LATIN SMALL LETTER F
2640;female;FEMALE SIGN
2012;figuredash;FIGURE DASH
25A0;filledbox;BLACK SQUARE
25AC;filledrect;BLACK RECTANGLE
0035;five;DIGIT FIVE
215D;fiveeighths;VULGAR FRACTION FIVE EIGHTHS
0192;florin;LATIN SMALL LETTER F WITH HOOK
0034;four;DIGIT FOUR
2044;fraction;FRACTION SLASH
20A3;franc;FRENCH FRANC SIGN
0067;g;LATIN SMALL LETTER G
03B3;gamma;GREEK SMALL LETTER GAMMA
011F;gbreve;LATIN SMALL LETTER G WITH BREVE
01E7;gcaron;LATIN SMALL LETTER G WITH CARON
011D;gcircumflex;LATIN SMALL LETTER G WITH CIRCUMFLEX
0121;gdotaccent;LATIN SMALL LETTER G WITH DOT ABOVE
00DF;germandbls;LATIN SMALL LETTER SHARP S
2207;gradient;NABLA
0060;grave;GRAVE ACCENT
0300;gravecomb;COMBINING GRAVE ACCENT
003E;greater;GREATER-THAN SIGN
2265;greaterequal;GREATER-THAN OR EQUAL TO
00AB;guillemotleft;LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
00BB;guillemotright;RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
2039;guilsinglleft;SINGLE LEFT-POINTING ANGLE QUOTATION MARK
203A;guilsinglright;SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
0068;h;LATIN SMALL LETTER H
0127;hbar;LATIN SMALL LETTER H WITH STROKE
0125;hcircumflex;LATIN SMALL LETTER H WITH CIRCUMFLEX
2665;heart;BLACK HEART SUIT
0309;hookabovecomb;COMBINING HOOK ABOVE
2302;house;HOUSE
02DD;hungarumlaut;DOUBLE ACUTE ACCENT
002D;hyphen;HYPHEN-MINUS
0069;i;LATIN SMALL LETTER I
00ED;iacute;LATIN SMALL LETTER I WITH ACUTE
012D;ibreve;LATIN SMALL LETTER I WITH BREVE
00EE;icircumflex;LATIN SMALL LETTER I WITH CIRCUMFLEX
00EF;idieresis;LATIN SMALL LETTER I WITH DIAERESIS
00EC;igrave;LATIN SMALL LETTER I WITH GRAVE
0133;ij;LATIN SMALL LIGATURE IJ
012B;imacron;LATIN SMALL LETTER I WITH MACRON
221E;infinity;INFINITY
222B;integral;INTEGRAL
2321;integralbt;BOTTOM HALF INTEGRAL
2320;integraltp;TOP HALF INTEGRAL
2229;intersection;INTERSECTION
25D8;invbullet;INVERSE BULLET
25D9;invcircle;INVERSE WHITE CIRCLE
263B;invsmileface;BLACK SMILING FACE
012F;iogonek;LATIN SMALL LETTER I WITH OGONEK
03B9;iota;GREEK SMALL LETTER IOTA
03CA;iotadieresis;GREEK SMALL LETTER IOTA WITH DIALYTIKA
0390;iotadieresistonos;GREEK SMALL LETTER IOTA WITH DIALYTIKA AND TONOS
03AF;iotatonos;GREEK SMALL LETTER IOTA WITH TONOS
0129;itilde;LATIN SMALL LETTER I WITH TILDE
006A;j;LATIN SMALL LETTER J
0135;jcircumflex;LATIN SMALL LETTER J WITH CIRCUMFLEX
006B;k;LATIN SMALL LETTER K
03BA;kappa;GREEK SMALL LETTER KAPPA
0138;kgreenlandic;LATIN SMALL LETTER KRA
006C;l;LATIN SMALL LETTER L
013A;lacute;LATIN SMALL LETTER L WITH ACUTE
03BB;lambda;GREEK SMALL LETTER LAMDA
013E;lcaron;LATIN SMALL LETTER L WITH CARON
0140;ldot;LATIN SMALL LETTER L WITH MIDDLE DOT
003C;less;LESS-THAN SIGN
2264;lessequal;LESS-THAN OR EQUAL TO
258C;lfblock;LEFT HALF BLOCK
20A4;lira;LIRA SIGN
2227;logicaland;LOGICAL AND
00AC;logicalnot;NOT SIGN
2228;logicalor;LOGICAL OR
017F;longs;LATIN SMALL LETTER LONG S
25CA;lozenge;LOZENGE
0142;lslash;LATIN SMALL LETTER L WITH STROKE
2591;ltshade;LIGHT SHADE
006D;m;LATIN SMALL LETTER M
00AF;macron;MACRON
2642;male;MALE SIGN
2212;minus;MINUS SIGN
2032;minute;PRIME
00B5;mu;MICRO SIGN
00D7;multiply;MULTIPLICATION SIGN
266A;musicalnote;EIGHTH NOTE
266B;musicalnotedbl;BEAMED EIGHTH NOTES
006E;n;LATIN SMALL LETTER N
0144;nacute;LATIN SMALL LETTER N WITH ACUTE
0149;napostrophe;LATIN SMALL LETTER N PRECEDED BY APOSTROPHE
0148;ncaron;LATIN SMALL LETTER N WITH CARON
0039;nine;DIGIT NINE
2209;notelement;NOT AN ELEMENT OF
2260;notequal;NOT EQUAL TO
2284;notsubset;NOT A SUBSET OF
00F1;ntilde;LATIN SMALL LETTER N WITH TILDE
03BD;nu;GREEK SMALL LETTER NU
0023;numbersign;NUMBER SIGN
006F;o;LATIN SMALL LETTER O
00F3;oacute;LATIN SMALL LETTER O WITH ACUTE
014F;obreve;LATIN SMALL LETTER O WITH BREVE
00F4;ocircumflex;LATIN SMALL LETTER O WITH CIRCUMFLEX
00F6;odieresis;LATIN SMALL LETTER O WITH DIAERESIS
0153;oe;LATIN SMALL LIGATURE OE
02DB;ogonek;OGONEK
00F2;ograve;LATIN SMALL LETTER O WITH GRAVE
01A1;ohorn;LATIN SMALL LETTER O WITH HORN
0151;ohungarumlaut;LATIN SMALL LETTER O WITH DOUBLE ACUTE
014D;omacron;LATIN SMALL LETTER O WITH MACRON
03C9;omega;GREEK SMALL LETTER OMEGA
03D6;omega1;GREEK PI SYMBOL
03CE;omegatonos;GREEK SMALL LETTER OMEGA WITH TONOS
03BF;omicron;GREEK SMALL LETTER OMICRON
03CC;omicrontonos;GREEK SMALL LETTER OMICRON WITH TONOS
0031;one;DIGIT ONE
2024;onedotenleader;ONE DOT LEADER
215B;oneeighth;VULGAR FRACTION ONE EIGHTH
00BD;onehalf;VULGAR FRACTION ONE HALF
00BC;onequarter;VULGAR FRACTION ONE QUARTER
2153;onethird;VULGAR FRACTION ONE THIRD
25E6;openbullet;WHITE BULLET
00AA;ordfeminine;FEMININE ORDINAL INDICATOR
00BA;ordmasculine;MASCULINE ORDINAL INDICATOR
221F;orthogonal;RIGHT ANGLE
00F8;oslash;LATIN SMALL LETTER O WITH STROKE
01FF;oslashacute;LATIN SMALL LETTER O WITH STROKE AND ACUTE
00F5;otilde;LATIN SMALL LETTER O WITH TILDE
0070;p;LATIN SMALL LETTER P
00B6;paragraph;PILCROW SIGN
0028;parenleft;LEFT PARENTHESIS
0029;parenright;RIGHT PARENTHESIS
2202;partialdiff;PARTIAL DIFFERENTIAL
0025;percent;PERCENT SIGN
002E;period;FULL STOP
00B7;periodcentered;MIDDLE DOT
22A5;perpendicular;UP TACK
2030;perthousand;PER MILLE SIGN
20A7;peseta;PESETA SIGN
03C6;phi;GREEK SMALL LETTER PHI
03D5;phi1;GREEK PHI SYMBOL
03C0;pi;GREEK SMALL LETTER PI
002B;plus;PLUS SIGN
00B1;plusminus;PLUS-MINUS SIGN
211E;prescription;PRESCRIPTION TAKE
220F;product;N-ARY PRODUCT
2282;propersubset;SUBSET OF
2283;propersuperset;SUPERSET OF
221D;proportional;PROPORTIONAL TO
03C8;psi;GREEK SMALL LETTER PSI
0071;q;LATIN SMALL LETTER Q
003F;question;QUESTION MARK
00BF;questiondown;INVERTED QUESTION MARK
0022;quotedbl;QUOTATION MARK
201E;quotedblbase;DOUBLE LOW-9 QUOTATION MARK
201C;quotedblleft;LEFT DOUBLE QUOTATION MARK
201D;quotedblright;RIGHT DOUBLE QUOTATION MARK
2018;quoteleft;LEFT SINGLE QUOTATION MARK
201B;quotereversed;SINGLE HIGH-REVERSED-9 QUOTATION MARK
2019;quoteright;RIGHT SINGLE QUOTATION MARK
201A;quotesinglbase;SINGLE LOW-9 QUOTATION MARK
0027;quotesingle;APOSTROPHE
0072;r;LATIN SMALL LETTER R
0155;racute;LATIN SMALL LETTER R WITH ACUTE
221A;radical;SQUARE ROOT
0159;rcaron;LATIN SMALL LETTER R WITH CARON
2286;reflexsubset;SUBSET OF OR EQUAL TO
2287;reflexsuperset;SUPERSET OF OR EQUAL TO
00AE;registered;REGISTERED SIGN
2310;revlogicalnot;REVERSED NOT SIGN
03C1;rho;GREEK SMALL LETTER RHO
02DA;ring;RING ABOVE
2590;rtblock;RIGHT HALF BLOCK
0073;s;LATIN SMALL LETTER S
015B;sacute;LATIN SMALL LETTER S WITH ACUTE
0161;scaron;LATIN SMALL LETTER S WITH CARON
015F;scedilla;LATIN SMALL LETTER S WITH CEDILLA
015D;scircumflex;LATIN SMALL LETTER S WITH CIRCUMFLEX
2033;second;DOUBLE PRIME
00A7;section;SECTION SIGN
003B;semicolon;SEMICOLON
0037;seven;DIGIT SEVEN
215E;seveneighths;VULGAR FRACTION SEVEN EIGHTHS
2592;shade;MEDIUM SHADE
03C3;sigma;GREEK SMALL LETTER SIGMA
03C2;sigma1;GREEK SMALL LETTER FINAL SIGMA
223C;similar;TILDE OPERATOR
0036;six;DIGIT SIX
002F;slash;SOLIDUS
263A;smileface;WHITE SMILING FACE
0020;space;SPACE
2660;spade;BLACK SPADE SUIT
00A3;sterling;POUND SIGN
220B;suchthat;CONTAINS AS MEMBER
2211;summation;N-ARY SUMMATION
263C;sun;WHITE SUN WITH RAYS
0074;t;LATIN SMALL LETTER T
03C4;tau;GREEK SMALL LETTER TAU
0167;tbar;LATIN SMALL LETTER T WITH STROKE
0165;tcaron;LATIN SMALL LETTER T WITH CARON
2234;therefore;THEREFORE
03B8;theta;GREEK SMALL LETTER THETA
03D1;theta1;GREEK THETA SYMBOL
00FE;thorn;LATIN SMALL LETTER THORN
0033;three;DIGIT THREE
215C;threeeighths;VULGAR FRACTION THREE EIGHTHS
00BE;threequarters;VULGAR FRACTION THREE QUARTERS
02DC;tilde;SMALL TILDE
0303;tildecomb;COMBINING TILDE
0384;tonos;GREEK TONOS
2122;trademark;TRADE MARK SIGN
25BC;triagdn;BLACK DOWN-POINTING TRIANGLE
25C4;triaglf;BLACK LEFT-POINTING POINTER
25BA;triagrt;BLACK RIGHT-POINTING POINTER
25B2;triagup;BLACK UP-POINTING TRIANGLE
0032;two;DIGIT TWO
2025;twodotenleader;TWO DOT LEADER
2154;twothirds;VULGAR FRACTION TWO THIRDS
0075;u;LATIN SMALL LETTER U
00FA;uacute;LATIN SMALL LETTER U WITH ACUTE
016D;ubreve;LATIN SMALL LETTER U WITH BREVE
00FB;ucircumflex;LATIN SMALL LETTER U WITH CIRCUMFLEX
00FC;udieresis;LATIN SMALL LETTER U WITH DIAERESIS
00F9;ugrave;LATIN SMALL LETTER U WITH GRAVE
01B0;uhorn;LATIN SMALL LETTER U WITH HORN
0171;uhungarumlaut;LATIN SMALL LETTER U WITH DOUBLE ACUTE
016B;umacron;LATIN SMALL LETTER U WITH MACRON
005F;underscore;LOW LINE
2017;underscoredbl;DOUBLE LOW LINE
222A;union;UNION
2200;universal;FOR ALL
0173;uogonek;LATIN SMALL LETTER U WITH OGONEK
2580;upblock;UPPER HALF BLOCK
03C5;upsilon;GREEK SMALL LETTER UPSILON
03CB;upsilondieresis;GREEK SMALL LETTER UPSILON WITH DIALYTIKA
03B0;upsilondieresistonos;GREEK SMALL LETTER UPSILON WITH DIALYTIKA AND TONOS
03CD;upsilontonos;GREEK SMALL LETTER UPSILON WITH TONOS
016F;uring;LATIN SMALL LETTER U WITH RING ABOVE
0169;utilde;LATIN SMALL LETTER U WITH TILDE
0076;v;LATIN SMALL LETTER V
0077;w;LATIN SMALL LETTER W
1E83;wacute;LATIN SMALL LETTER W WITH ACUTE
0175;wcircumflex;LATIN SMALL LETTER W WITH CIRCUMFLEX
1E85;wdieresis;LATIN SMALL LETTER W WITH DIAERESIS
2118;weierstrass;SCRIPT CAPITAL P
1E81;wgrave;LATIN SMALL LETTER W WITH GRAVE
0078;x;LATIN SMALL LETTER X
03BE;xi;GREEK SMALL LETTER XI
0079;y;LATIN SMALL LETTER Y
00FD;yacute;LATIN SMALL LETTER Y WITH ACUTE
0177;ycircumflex;LATIN SMALL LETTER Y WITH CIRCUMFLEX
00FF;ydieresis;LATIN SMALL LETTER Y WITH DIAERESIS
00A5;yen;YEN SIGN
1EF3;ygrave;LATIN SMALL LETTER Y WITH GRAVE
007A;z;LATIN SMALL LETTER Z
017A;zacute;LATIN SMALL LETTER Z WITH ACUTE
017E;zcaron;LATIN SMALL LETTER Z WITH CARON
017C;zdotaccent;LATIN SMALL LETTER Z WITH DOT ABOVE
0030;zero;DIGIT ZERO
03B6;zeta;GREEK SMALL LETTER ZETA
# END
"""


class AGLError(Exception):
    pass


LEGACY_AGL2UV = {}
AGL2UV = {}
UV2AGL = {}


def _builddicts():
    import re

    lines = _aglText.splitlines()

    parseAGL_RE = re.compile("([A-Za-z0-9]+);((?:[0-9A-F]{4})(?: (?:[0-9A-F]{4}))*)$")

    for line in lines:
        if not line or line[:1] == "#":
            continue
        m = parseAGL_RE.match(line)
        if not m:
            raise AGLError("syntax error in glyphlist.txt: %s" % repr(line[:20]))
        unicodes = m.group(2)
        assert len(unicodes) % 5 == 4
        unicodes = [int(unicode, 16) for unicode in unicodes.split()]
        glyphName = tostr(m.group(1))
        LEGACY_AGL2UV[glyphName] = unicodes

    lines = _aglfnText.splitlines()

    parseAGLFN_RE = re.compile("([0-9A-F]{4});([A-Za-z0-9]+);.*?$")

    for line in lines:
        if not line or line[:1] == "#":
            continue
        m = parseAGLFN_RE.match(line)
        if not m:
            raise AGLError("syntax error in aglfn.txt: %s" % repr(line[:20]))
        unicode = m.group(1)
        assert len(unicode) == 4
        unicode = int(unicode, 16)
        glyphName = tostr(m.group(2))
        AGL2UV[glyphName] = unicode
        UV2AGL[unicode] = glyphName


_builddicts()


def toUnicode(glyph, isZapfDingbats=False):
    """Convert glyph names to Unicode, such as ``'longs_t.oldstyle'`` --> ``u'ſt'``

    If ``isZapfDingbats`` is ``True``, the implementation recognizes additional
    glyph names (as required by the AGL specification).
    """
    # https://github.com/adobe-type-tools/agl-specification#2-the-mapping
    #
    # 1. Drop all the characters from the glyph name starting with
    #    the first occurrence of a period (U+002E; FULL STOP), if any.
    glyph = glyph.split(".", 1)[0]

    # 2. Split the remaining string into a sequence of components,
    #    using underscore (U+005F; LOW LINE) as the delimiter.
    components = glyph.split("_")

    # 3. Map each component to a character string according to the
    #    procedure below, and concatenate those strings; the result
    #     is the character string to which the glyph name is mapped.
    result = [_glyphComponentToUnicode(c, isZapfDingbats) for c in components]
    return "".join(result)


def _glyphComponentToUnicode(component, isZapfDingbats):
    # If the font is Zapf Dingbats (PostScript FontName: ZapfDingbats),
    # and the component is in the ITC Zapf Dingbats Glyph List, then
    # map it to the corresponding character in that list.
    dingbat = _zapfDingbatsToUnicode(component) if isZapfDingbats else None
    if dingbat:
        return dingbat

    # Otherwise, if the component is in AGL, then map it
    # to the corresponding character in that list.
    uchars = LEGACY_AGL2UV.get(component)
    if uchars:
        return "".join(map(chr, uchars))

    # Otherwise, if the component is of the form "uni" (U+0075,
    # U+006E, and U+0069) followed by a sequence of uppercase
    # hexadecimal digits (0–9 and A–F, meaning U+0030 through
    # U+0039 and U+0041 through U+0046), if the length of that
    # sequence is a multiple of four, and if each group of four
    # digits represents a value in the ranges 0000 through D7FF
    # or E000 through FFFF, then interpret each as a Unicode scalar
    # value and map the component to the string made of those
    # scalar values. Note that the range and digit-length
    # restrictions mean that the "uni" glyph name prefix can be
    # used only with UVs in the Basic Multilingual Plane (BMP).
    uni = _uniToUnicode(component)
    if uni:
        return uni

    # Otherwise, if the component is of the form "u" (U+0075)
    # followed by a sequence of four to six uppercase hexadecimal
    # digits (0–9 and A–F, meaning U+0030 through U+0039 and
    # U+0041 through U+0046), and those digits represents a value
    # in the ranges 0000 through D7FF or E000 through 10FFFF, then
    # interpret it as a Unicode scalar value and map the component
    # to the string made of this scalar value.
    uni = _uToUnicode(component)
    if uni:
        return uni

    # Otherwise, map the component to an empty string.
    return ""


# https://github.com/adobe-type-tools/agl-aglfn/blob/master/zapfdingbats.txt
_AGL_ZAPF_DINGBATS = (
    " ✁✂✄☎✆✝✞✟✠✡☛☞✌✍✎✏✑✒✓✔✕✖✗✘✙✚✛✜✢✣✤✥✦✧★✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺✻✼✽✾✿❀"
    "❁❂❃❄❅❆❇❈❉❊❋●❍■❏❑▲▼◆❖ ◗❘❙❚❯❱❲❳❨❩❬❭❪❫❴❵❛❜❝❞❡❢❣❤✐❥❦❧♠♥♦♣    ✉✈✇"
    "①②③④⑤⑥⑦⑧⑨⑩❶❷❸❹❺❻❼❽❾❿➀➁➂➃➄➅➆➇➈➉➊➋➌➍➎➏➐➑➒➓➔→➣↔"
    "↕➙➛➜➝➞➟➠➡➢➤➥➦➧➨➩➫➭➯➲➳➵➸➺➻➼➽➾➚➪➶➹➘➴➷➬➮➱✃❐❒❮❰"
)


def _zapfDingbatsToUnicode(glyph):
    """Helper for toUnicode()."""
    if len(glyph) < 2 or glyph[0] != "a":
        return None
    try:
        gid = int(glyph[1:])
    except ValueError:
        return None
    if gid < 0 or gid >= len(_AGL_ZAPF_DINGBATS):
        return None
    uchar = _AGL_ZAPF_DINGBATS[gid]
    return uchar if uchar != " " else None


_re_uni = re.compile("^uni([0-9A-F]+)$")


def _uniToUnicode(component):
    """Helper for toUnicode() to handle "uniABCD" components."""
    match = _re_uni.match(component)
    if match is None:
        return None
    digits = match.group(1)
    if len(digits) % 4 != 0:
        return None
    chars = [int(digits[i : i + 4], 16) for i in range(0, len(digits), 4)]
    if any(c >= 0xD800 and c <= 0xDFFF for c in chars):
        # The AGL specification explicitly excluded surrogate pairs.
        return None
    return "".join([chr(c) for c in chars])


_re_u = re.compile("^u([0-9A-F]{4,6})$")


def _uToUnicode(component):
    """Helper for toUnicode() to handle "u1ABCD" components."""
    match = _re_u.match(component)
    if match is None:
        return None
    digits = match.group(1)
    try:
        value = int(digits, 16)
    except ValueError:
        return None
    if (value >= 0x0000 and value <= 0xD7FF) or (value >= 0xE000 and value <= 0x10FFFF):
        return chr(value)
    return None
