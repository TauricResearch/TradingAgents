from __future__ import annotations

import io
from pathlib import Path
import platform
import re
from xml.etree import ElementTree as ET
from typing import Any

import numpy as np
from packaging.version import parse as parse_version
import pyparsing
import pytest


import matplotlib as mpl
from matplotlib.testing.decorators import check_figures_equal, image_comparison
import matplotlib.pyplot as plt
from matplotlib import mathtext, _mathtext

pyparsing_version = parse_version(pyparsing.__version__)


# If test is removed, use None as placeholder
math_tests = [
    r'$a+b+\dot s+\dot{s}+\ldots$',
    r'$x\hspace{-0.2}\doteq\hspace{-0.2}y$',
    r'\$100.00 $\alpha \_$',
    r'$\frac{\$100.00}{y}$',
    r'$x   y$',
    r'$x+y\ x=y\ x<y\ x:y\ x,y\ x@y$',
    r'$100\%y\ x*y\ x/y x\$y$',
    r'$x\leftarrow y\ x\forall y\ x-y$',
    r'$x \sf x \bf x {\cal X} \rm x$',
    r'$x\ x\,x\;x\quad x\qquad x\!x\hspace{ 0.5 }y$',
    r'$\{ \rm braces \}$',
    r'$\left[\left\lfloor\frac{5}{\frac{\left(3\right)}{4}} y\right)\right]$',
    r'$\left(x\right)$',
    r'$\sin(x)$',
    r'$x_2$',
    r'$x^2$',
    r'$x^2_y$',
    r'$x_y^2$',
    (r'$\sum _{\genfrac{}{}{0}{}{0\leq i\leq m}{0<j<n}}f\left(i,j\right)'
     r'\mathcal{R}\prod_{i=\alpha_{i+1}}^\infty a_i \sin(2 \pi f x_i)'
     r"\sqrt[2]{\prod^\frac{x}{2\pi^2}_\infty}$"),
    r'$x = \frac{x+\frac{5}{2}}{\frac{y+3}{8}}$',
    r'$dz/dt = \gamma x^2 + {\rm sin}(2\pi y+\phi)$',
    r'Foo: $\alpha_{i+1}^j = {\rm sin}(2\pi f_j t_i) e^{-5 t_i/\tau}$',
    None,
    r'Variable $i$ is good',
    r'$\Delta_i^j$',
    r'$\Delta^j_{i+1}$',
    r'$\ddot{o}\acute{e}\grave{e}\hat{O}\breve{\imath}\tilde{n}\vec{q}$',
    r"$\arccos((x^i))$",
    r"$\gamma = \frac{x=\frac{6}{8}}{y} \delta$",
    r'$\limsup_{x\to\infty}$',
    None,
    r"$f'\quad f'''(x)\quad ''/\mathrm{yr}$",
    r'$\frac{x_2888}{y}$',
    r"$\sqrt[3]{\frac{X_2}{Y}}=5$",
    None,
    r"$\sqrt[3]{x}=5$",
    r'$\frac{X}{\frac{X}{Y}}$',
    r"$W^{3\beta}_{\delta_1 \rho_1 \sigma_2} = U^{3\beta}_{\delta_1 \rho_1} + \frac{1}{8 \pi 2} \int^{\alpha_2}_{\alpha_2} d \alpha^\prime_2 \left[\frac{ U^{2\beta}_{\delta_1 \rho_1} - \alpha^\prime_2U^{1\beta}_{\rho_1 \sigma_2} }{U^{0\beta}_{\rho_1 \sigma_2}}\right]$",
    r'$\mathcal{H} = \int d \tau \left(\epsilon E^2 + \mu H^2\right)$',
    r'$\widehat{abc}\widetilde{def}$',
    '$\\Gamma \\Delta \\Theta \\Lambda \\Xi \\Pi \\Sigma \\Upsilon \\Phi \\Psi \\Omega$',
    '$\\alpha \\beta \\gamma \\delta \\epsilon \\zeta \\eta \\theta \\iota \\lambda \\mu \\nu \\xi \\pi \\kappa \\rho \\sigma \\tau \\upsilon \\phi \\chi \\psi$',

    # The following examples are from the MathML torture test here:
    # https://www-archive.mozilla.org/projects/mathml/demo/texvsmml.xhtml
    r'${x}^{2}{y}^{2}$',
    r'${}_{2}F_{3}$',
    r'$\frac{x+{y}^{2}}{k+1}$',
    r'$x+{y}^{\frac{2}{k+1}}$',
    r'$\frac{a}{b/2}$',
    r'${a}_{0}+\frac{1}{{a}_{1}+\frac{1}{{a}_{2}+\frac{1}{{a}_{3}+\frac{1}{{a}_{4}}}}}$',
    r'${a}_{0}+\frac{1}{{a}_{1}+\frac{1}{{a}_{2}+\frac{1}{{a}_{3}+\frac{1}{{a}_{4}}}}}$',
    r'$\binom{n}{k/2}$',
    r'$\binom{p}{2}{x}^{2}{y}^{p-2}-\frac{1}{1-x}\frac{1}{1-{x}^{2}}$',
    r'${x}^{2y}$',
    r'$\sum _{i=1}^{p}\sum _{j=1}^{q}\sum _{k=1}^{r}{a}_{ij}{b}_{jk}{c}_{ki}$',
    r'$\sqrt{1+\sqrt{1+\sqrt{1+\sqrt{1+\sqrt{1+\sqrt{1+\sqrt{1+x}}}}}}}$',
    r'$\left(\frac{{\partial }^{2}}{\partial {x}^{2}}+\frac{{\partial }^{2}}{\partial {y}^{2}}\right){|\varphi \left(x+iy\right)|}^{2}=0$',
    r'${2}^{{2}^{{2}^{x}}}$',
    r'${\int }_{1}^{x}\frac{\mathrm{dt}}{t}$',
    r'$\int {\int }_{D}\mathrm{dx} \mathrm{dy}$',
    # mathtex doesn't support array
    # 'mmltt18'    : r'$f\left(x\right)=\left\{\begin{array}{cc}\hfill 1/3\hfill & \text{if_}0\le x\le 1;\hfill \\ \hfill 2/3\hfill & \hfill \text{if_}3\le x\le 4;\hfill \\ \hfill 0\hfill & \text{elsewhere.}\hfill \end{array}$',
    # mathtex doesn't support stackrel
    # 'mmltt19'    : r'$\stackrel{\stackrel{k\text{times}}{\ufe37}}{x+...+x}$',
    r'${y}_{{x}^{2}}$',
    # mathtex doesn't support the "\text" command
    # 'mmltt21'    : r'$\sum _{p\text{\prime}}f\left(p\right)={\int }_{t>1}f\left(t\right) d\pi \left(t\right)$',
    # mathtex doesn't support array
    # 'mmltt23'    : r'$\left(\begin{array}{cc}\hfill \left(\begin{array}{cc}\hfill a\hfill & \hfill b\hfill \\ \hfill c\hfill & \hfill d\hfill \end{array}\right)\hfill & \hfill \left(\begin{array}{cc}\hfill e\hfill & \hfill f\hfill \\ \hfill g\hfill & \hfill h\hfill \end{array}\right)\hfill \\ \hfill 0\hfill & \hfill \left(\begin{array}{cc}\hfill i\hfill & \hfill j\hfill \\ \hfill k\hfill & \hfill l\hfill \end{array}\right)\hfill \end{array}\right)$',
    # mathtex doesn't support array
    # 'mmltt24'   : r'$det|\begin{array}{ccccc}\hfill {c}_{0}\hfill & \hfill {c}_{1}\hfill & \hfill {c}_{2}\hfill & \hfill \dots \hfill & \hfill {c}_{n}\hfill \\ \hfill {c}_{1}\hfill & \hfill {c}_{2}\hfill & \hfill {c}_{3}\hfill & \hfill \dots \hfill & \hfill {c}_{n+1}\hfill \\ \hfill {c}_{2}\hfill & \hfill {c}_{3}\hfill & \hfill {c}_{4}\hfill & \hfill \dots \hfill & \hfill {c}_{n+2}\hfill \\ \hfill \u22ee\hfill & \hfill \u22ee\hfill & \hfill \u22ee\hfill & \hfill \hfill & \hfill \u22ee\hfill \\ \hfill {c}_{n}\hfill & \hfill {c}_{n+1}\hfill & \hfill {c}_{n+2}\hfill & \hfill \dots \hfill & \hfill {c}_{2n}\hfill \end{array}|>0$',
    r'${y}_{{x}_{2}}$',
    r'${x}_{92}^{31415}+\pi $',
    r'${x}_{{y}_{b}^{a}}^{{z}_{c}^{d}}$',
    r'${y}_{3}^{\prime \prime \prime }$',
    # End of the MathML torture tests.

    r"$\left( \xi \left( 1 - \xi \right) \right)$",  # Bug 2969451
    r"$\left(2 \, a=b\right)$",  # Sage bug #8125
    r"$? ! &$",  # github issue #466
    None,
    None,
    r"$\left\Vert \frac{a}{b} \right\Vert \left\vert \frac{a}{b} \right\vert \left\| \frac{a}{b}\right\| \left| \frac{a}{b} \right| \Vert a \Vert \vert b \vert \| a \| | b |$",
    r'$\mathring{A}  \AA$',
    r'$M \, M \thinspace M \/ M \> M \: M \; M \ M \enspace M \quad M \qquad M \! M$',
    r'$\Cap$ $\Cup$ $\leftharpoonup$ $\barwedge$ $\rightharpoonup$',
    r'$\hspace{-0.2}\dotplus\hspace{-0.2}$ $\hspace{-0.2}\doteq\hspace{-0.2}$ $\hspace{-0.2}\doteqdot\hspace{-0.2}$ $\ddots$',
    r'$xyz^kx_kx^py^{p-2} d_i^jb_jc_kd x^j_i E^0 E^0_u$',  # github issue #4873
    r'${xyz}^k{x}_{k}{x}^{p}{y}^{p-2} {d}_{i}^{j}{b}_{j}{c}_{k}{d} {x}^{j}_{i}{E}^{0}{E}^0_u$',
    r'${\int}_x^x x\oint_x^x x\int_{X}^{X}x\int_x x \int^x x \int_{x} x\int^{x}{\int}_{x} x{\int}^{x}_{x}x$',
    r'testing$^{123}$',
    None,
    r'$6-2$; $-2$; $ -2$; ${-2}$; ${  -2}$; $20^{+3}_{-2}$',
    r'$\overline{\omega}^x \frac{1}{2}_0^x$',  # github issue #5444
    r'$,$ $.$ $1{,}234{, }567{ , }890$ and $1,234,567,890$',  # github issue 5799
    r'$\left(X\right)_{a}^{b}$',  # github issue 7615
    r'$\dfrac{\$100.00}{y}$',  # github issue #1888
    r'$a=-b-c$'  # github issue #28180
]
# 'svgastext' tests switch svg output to embed text as text (rather than as
# paths).
svgastext_math_tests = [
    r'$-$-',
]
# 'lightweight' tests test only a single fontset (dejavusans, which is the
# default) and only png outputs, in order to minimize the size of baseline
# images.
lightweight_math_tests = [
    r'$\sqrt[ab]{123}$',  # github issue #8665
    r'$x \overset{f}{\rightarrow} \overset{f}{x} \underset{xx}{ff} \overset{xx}{ff} \underset{f}{x} \underset{f}{\leftarrow} x$',  # github issue #18241
    r'$\sum x\quad\sum^nx\quad\sum_nx\quad\sum_n^nx\quad\prod x\quad\prod^nx\quad\prod_nx\quad\prod_n^nx$',  # GitHub issue 18085
    r'$1.$ $2.$ $19680801.$ $a.$ $b.$ $mpl.$',
    r'$\text{text}_{\text{sub}}^{\text{sup}} + \text{\$foo\$} + \frac{\text{num}}{\mathbf{\text{den}}}\text{with space, curly brackets \{\}, and dash -}$',
    r'$\boldsymbol{abcde} \boldsymbol{+} \boldsymbol{\Gamma + \Omega} \boldsymbol{01234} \boldsymbol{\alpha * \beta}$',
    r'$\left\lbrace\frac{\left\lbrack A^b_c\right\rbrace}{\left\leftbrace D^e_f \right\rbrack}\right\rightbrace\ \left\leftparen\max_{x} \left\lgroup \frac{A}{B}\right\rgroup \right\rightparen$',
    r'$\left( a\middle. b \right)$ $\left( \frac{a}{b} \middle\vert x_i \in P^S \right)$ $\left[ 1 - \middle| a\middle| + \left( x  - \left\lfloor \dfrac{a}{b}\right\rfloor \right)  \right]$',
    r'$\sum_{\substack{k = 1\\ k \neq \lfloor n/2\rfloor}}^{n}P(i,j) \sum_{\substack{i \neq 0\\ -1 \leq i \leq 3\\ 1 \leq j \leq 5}} F^i(x,y) \sum_{\substack{\left \lfloor \frac{n}{2} \right\rfloor}} F(n)$',
]

digits = "0123456789"
uppercase = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
lowercase = "abcdefghijklmnopqrstuvwxyz"
uppergreek = ("\\Gamma \\Delta \\Theta \\Lambda \\Xi \\Pi \\Sigma \\Upsilon \\Phi \\Psi "
              "\\Omega")
lowergreek = ("\\alpha \\beta \\gamma \\delta \\epsilon \\zeta \\eta \\theta \\iota "
              "\\lambda \\mu \\nu \\xi \\pi \\kappa \\rho \\sigma \\tau \\upsilon "
              "\\phi \\chi \\psi")
all = [digits, uppercase, lowercase, uppergreek, lowergreek]

# Use stubs to reserve space if tests are removed
# stub should be of the form (None, N) where N is the number of strings that
# used to be tested
# Add new tests at the end.
font_test_specs: list[tuple[None | list[str], Any]] = [
    ([], all),
    (['mathrm'], all),
    (['mathbf'], all),
    (['mathit'], all),
    (['mathtt'], [digits, uppercase, lowercase]),
    (None, 3),
    (None, 3),
    (None, 3),
    (['mathbb'], [digits, uppercase, lowercase,
                  r'\Gamma \Pi \Sigma \gamma \pi']),
    (['mathrm', 'mathbb'], [digits, uppercase, lowercase,
                            r'\Gamma \Pi \Sigma \gamma \pi']),
    (['mathbf', 'mathbb'], [digits, uppercase, lowercase,
                            r'\Gamma \Pi \Sigma \gamma \pi']),
    (['mathcal'], [uppercase]),
    (['mathfrak'], [uppercase, lowercase]),
    (['mathbf', 'mathfrak'], [uppercase, lowercase]),
    (['mathscr'], [uppercase, lowercase]),
    (['mathsf'], [digits, uppercase, lowercase]),
    (['mathrm', 'mathsf'], [digits, uppercase, lowercase]),
    (['mathbf', 'mathsf'], [digits, uppercase, lowercase]),
    (['mathbfit'], all),
    ]

font_tests: list[None | str] = []
for fonts, chars in font_test_specs:
    if fonts is None:
        font_tests.extend([None] * chars)
    else:
        wrapper = ''.join([
            ' '.join(fonts),
            ' $',
            *(r'\%s{' % font for font in fonts),
            '%s',
            *('}' for font in fonts),
            '$',
        ])
        for font_set in chars:
            font_tests.append(wrapper % font_set)


@pytest.fixture
def baseline_images(request, fontset, index, text):
    if text is None:
        pytest.skip("test has been removed")
    return ['%s_%s_%02d' % (request.param, fontset, index)]


@pytest.mark.parametrize(
    'index, text', enumerate(math_tests), ids=range(len(math_tests)))
@pytest.mark.parametrize(
    'fontset', ['cm', 'stix', 'stixsans', 'dejavusans', 'dejavuserif'])
@pytest.mark.parametrize('baseline_images', ['mathtext'], indirect=True)
@image_comparison(baseline_images=None,
                  tol=0.011 if platform.machine() in ('ppc64le', 's390x') else 0)
def test_mathtext_rendering(baseline_images, fontset, index, text):
    mpl.rcParams['mathtext.fontset'] = fontset
    fig = plt.figure(figsize=(5.25, 0.75))
    fig.text(0.5, 0.5, text,
             horizontalalignment='center', verticalalignment='center')


@pytest.mark.parametrize('index, text', enumerate(svgastext_math_tests),
                         ids=range(len(svgastext_math_tests)))
@pytest.mark.parametrize('fontset', ['cm', 'dejavusans'])
@pytest.mark.parametrize('baseline_images', ['mathtext0'], indirect=True)
@image_comparison(
    baseline_images=None, extensions=['svg'],
    savefig_kwarg={'metadata': {  # Minimize image size.
        'Creator': None, 'Date': None, 'Format': None, 'Type': None}})
def test_mathtext_rendering_svgastext(baseline_images, fontset, index, text):
    mpl.rcParams['mathtext.fontset'] = fontset
    mpl.rcParams['svg.fonttype'] = 'none'  # Minimize image size.
    fig = plt.figure(figsize=(5.25, 0.75))
    fig.patch.set(visible=False)  # Minimize image size.
    fig.text(0.5, 0.5, text,
             horizontalalignment='center', verticalalignment='center')


@pytest.mark.parametrize('index, text', enumerate(lightweight_math_tests),
                         ids=range(len(lightweight_math_tests)))
@pytest.mark.parametrize('fontset', ['dejavusans'])
@pytest.mark.parametrize('baseline_images', ['mathtext1'], indirect=True)
@image_comparison(baseline_images=None, extensions=['png'])
def test_mathtext_rendering_lightweight(baseline_images, fontset, index, text):
    fig = plt.figure(figsize=(5.25, 0.75))
    fig.text(0.5, 0.5, text, math_fontfamily=fontset,
             horizontalalignment='center', verticalalignment='center')


@pytest.mark.parametrize(
    'index, text', enumerate(font_tests), ids=range(len(font_tests)))
@pytest.mark.parametrize(
    'fontset', ['cm', 'stix', 'stixsans', 'dejavusans', 'dejavuserif'])
@pytest.mark.parametrize('baseline_images', ['mathfont'], indirect=True)
@image_comparison(baseline_images=None, extensions=['png'],
                  tol=0.011 if platform.machine() in ('ppc64le', 's390x') else 0)
def test_mathfont_rendering(baseline_images, fontset, index, text):
    mpl.rcParams['mathtext.fontset'] = fontset
    fig = plt.figure(figsize=(5.25, 0.75))
    fig.text(0.5, 0.5, text,
             horizontalalignment='center', verticalalignment='center')


@check_figures_equal(extensions=["png"])
def test_short_long_accents(fig_test, fig_ref):
    acc_map = _mathtext.Parser._accent_map
    short_accs = [s for s in acc_map if len(s) == 1]
    corresponding_long_accs = []
    for s in short_accs:
        l, = (l for l in acc_map if len(l) > 1 and acc_map[l] == acc_map[s])
        corresponding_long_accs.append(l)
    fig_test.text(0, .5, "$" + "".join(rf"\{s}a" for s in short_accs) + "$")
    fig_ref.text(
        0, .5, "$" + "".join(fr"\{l} a" for l in corresponding_long_accs) + "$")


def test_fontinfo():
    fontpath = mpl.font_manager.findfont("DejaVu Sans")
    font = mpl.ft2font.FT2Font(fontpath)
    table = font.get_sfnt_table("head")
    assert table is not None
    assert table['version'] == (1, 0)


# See gh-26152 for more context on this xfail
@pytest.mark.xfail(pyparsing_version.release == (3, 1, 0),
                   reason="Error messages are incorrect for this version")
@pytest.mark.parametrize(
    'math, msg',
    [
        (r'$\hspace{}$', r'Expected \hspace{space}'),
        (r'$\hspace{foo}$', r'Expected \hspace{space}'),
        (r'$\sinx$', r'Unknown symbol: \sinx'),
        (r'$\dotx$', r'Unknown symbol: \dotx'),
        (r'$\frac$', r'Expected \frac{num}{den}'),
        (r'$\frac{}{}$', r'Expected \frac{num}{den}'),
        (r'$\binom$', r'Expected \binom{num}{den}'),
        (r'$\binom{}{}$', r'Expected \binom{num}{den}'),
        (r'$\genfrac$',
         r'Expected \genfrac{ldelim}{rdelim}{rulesize}{style}{num}{den}'),
        (r'$\genfrac{}{}{}{}{}{}$',
         r'Expected \genfrac{ldelim}{rdelim}{rulesize}{style}{num}{den}'),
        (r'$\sqrt$', r'Expected \sqrt{value}'),
        (r'$\sqrt f$', r'Expected \sqrt{value}'),
        (r'$\overline$', r'Expected \overline{body}'),
        (r'$\overline{}$', r'Expected \overline{body}'),
        (r'$\leftF$', r'Expected a delimiter'),
        (r'$\rightF$', r'Unknown symbol: \rightF'),
        (r'$\left(\right$', r'Expected a delimiter'),
        # PyParsing 2 uses double quotes, PyParsing 3 uses single quotes and an
        # extra backslash.
        (r'$\left($', re.compile(r'Expected ("|\'\\)\\right["\']')),
        (r'$\dfrac$', r'Expected \dfrac{num}{den}'),
        (r'$\dfrac{}{}$', r'Expected \dfrac{num}{den}'),
        (r'$\overset$', r'Expected \overset{annotation}{body}'),
        (r'$\underset$', r'Expected \underset{annotation}{body}'),
        (r'$\foo$', r'Unknown symbol: \foo'),
        (r'$a^2^2$', r'Double superscript'),
        (r'$a_2_2$', r'Double subscript'),
        (r'$a^2_a^2$', r'Double superscript'),
        (r'$a = {b$', r"Expected '}'"),
    ],
    ids=[
        'hspace without value',
        'hspace with invalid value',
        'function without space',
        'accent without space',
        'frac without parameters',
        'frac with empty parameters',
        'binom without parameters',
        'binom with empty parameters',
        'genfrac without parameters',
        'genfrac with empty parameters',
        'sqrt without parameters',
        'sqrt with invalid value',
        'overline without parameters',
        'overline with empty parameter',
        'left with invalid delimiter',
        'right with invalid delimiter',
        'unclosed parentheses with sizing',
        'unclosed parentheses without sizing',
        'dfrac without parameters',
        'dfrac with empty parameters',
        'overset without parameters',
        'underset without parameters',
        'unknown symbol',
        'double superscript',
        'double subscript',
        'super on sub without braces',
        'unclosed group',
    ]
)
def test_mathtext_exceptions(math, msg):
    parser = mathtext.MathTextParser('agg')
    match = re.escape(msg) if isinstance(msg, str) else msg
    with pytest.raises(ValueError, match=match):
        parser.parse(math)


def test_get_unicode_index_exception():
    with pytest.raises(ValueError):
        _mathtext.get_unicode_index(r'\foo')


def test_single_minus_sign():
    fig = plt.figure()
    fig.text(0.5, 0.5, '$-$')
    fig.canvas.draw()
    t = np.asarray(fig.canvas.renderer.buffer_rgba())
    assert (t != 0xff).any()  # assert that canvas is not all white.


@check_figures_equal(extensions=["png"])
def test_spaces(fig_test, fig_ref):
    fig_test.text(.5, .5, r"$1\,2\>3\ 4$")
    fig_ref.text(.5, .5, r"$1\/2\:3~4$")


@check_figures_equal(extensions=["png"])
def test_operator_space(fig_test, fig_ref):
    fig_test.text(0.1, 0.1, r"$\log 6$")
    fig_test.text(0.1, 0.2, r"$\log(6)$")
    fig_test.text(0.1, 0.3, r"$\arcsin 6$")
    fig_test.text(0.1, 0.4, r"$\arcsin|6|$")
    fig_test.text(0.1, 0.5, r"$\operatorname{op} 6$")  # GitHub issue #553
    fig_test.text(0.1, 0.6, r"$\operatorname{op}[6]$")
    fig_test.text(0.1, 0.7, r"$\cos^2$")
    fig_test.text(0.1, 0.8, r"$\log_2$")
    fig_test.text(0.1, 0.9, r"$\sin^2 \cos$")  # GitHub issue #17852

    fig_ref.text(0.1, 0.1, r"$\mathrm{log\,}6$")
    fig_ref.text(0.1, 0.2, r"$\mathrm{log}(6)$")
    fig_ref.text(0.1, 0.3, r"$\mathrm{arcsin\,}6$")
    fig_ref.text(0.1, 0.4, r"$\mathrm{arcsin}|6|$")
    fig_ref.text(0.1, 0.5, r"$\mathrm{op\,}6$")
    fig_ref.text(0.1, 0.6, r"$\mathrm{op}[6]$")
    fig_ref.text(0.1, 0.7, r"$\mathrm{cos}^2$")
    fig_ref.text(0.1, 0.8, r"$\mathrm{log}_2$")
    fig_ref.text(0.1, 0.9, r"$\mathrm{sin}^2 \mathrm{\,cos}$")


@check_figures_equal(extensions=["png"])
def test_inverted_delimiters(fig_test, fig_ref):
    fig_test.text(.5, .5, r"$\left)\right($", math_fontfamily="dejavusans")
    fig_ref.text(.5, .5, r"$)($", math_fontfamily="dejavusans")


@check_figures_equal(extensions=["png"])
def test_genfrac_displaystyle(fig_test, fig_ref):
    fig_test.text(0.1, 0.1, r"$\dfrac{2x}{3y}$")

    thickness = _mathtext.TruetypeFonts.get_underline_thickness(
        None, None, fontsize=mpl.rcParams["font.size"],
        dpi=mpl.rcParams["savefig.dpi"])
    fig_ref.text(0.1, 0.1, r"$\genfrac{}{}{%f}{0}{2x}{3y}$" % thickness)


def test_mathtext_fallback_valid():
    for fallback in ['cm', 'stix', 'stixsans', 'None']:
        mpl.rcParams['mathtext.fallback'] = fallback


def test_mathtext_fallback_invalid():
    for fallback in ['abc', '']:
        with pytest.raises(ValueError, match="not a valid fallback font name"):
            mpl.rcParams['mathtext.fallback'] = fallback


@pytest.mark.parametrize(
    "fallback,fontlist",
    [("cm", ['DejaVu Sans', 'mpltest', 'STIXGeneral', 'cmr10', 'STIXGeneral']),
     ("stix", ['DejaVu Sans', 'mpltest', 'STIXGeneral', 'STIXGeneral', 'STIXGeneral'])])
def test_mathtext_fallback(fallback, fontlist):
    mpl.font_manager.fontManager.addfont(
        str(Path(__file__).resolve().parent / 'mpltest.ttf'))
    mpl.rcParams["svg.fonttype"] = 'none'
    mpl.rcParams['mathtext.fontset'] = 'custom'
    mpl.rcParams['mathtext.rm'] = 'mpltest'
    mpl.rcParams['mathtext.it'] = 'mpltest:italic'
    mpl.rcParams['mathtext.bf'] = 'mpltest:bold'
    mpl.rcParams['mathtext.bfit'] = 'mpltest:italic:bold'
    mpl.rcParams['mathtext.fallback'] = fallback

    test_str = r'a$A\AA\breve\gimel$'

    buff = io.BytesIO()
    fig, ax = plt.subplots()
    fig.text(.5, .5, test_str, fontsize=40, ha='center')
    fig.savefig(buff, format="svg")
    tspans = (ET.fromstring(buff.getvalue())
              .findall(".//{http://www.w3.org/2000/svg}tspan[@style]"))
    char_fonts = [
        re.search(r"font-family: '([\w ]+)'", tspan.attrib["style"]).group(1)
        for tspan in tspans]
    assert char_fonts == fontlist, f'Expected {fontlist}, got {char_fonts}'
    mpl.font_manager.fontManager.ttflist.pop()


def test_math_to_image(tmp_path):
    mathtext.math_to_image('$x^2$', tmp_path / 'example.png')
    mathtext.math_to_image('$x^2$', io.BytesIO())
    mathtext.math_to_image('$x^2$', io.BytesIO(), color='Maroon')


@image_comparison(baseline_images=['math_fontfamily_image.png'],
                  savefig_kwarg={'dpi': 40})
def test_math_fontfamily():
    fig = plt.figure(figsize=(10, 3))
    fig.text(0.2, 0.7, r"$This\ text\ should\ have\ one\ font$",
             size=24, math_fontfamily='dejavusans')
    fig.text(0.2, 0.3, r"$This\ text\ should\ have\ another$",
             size=24, math_fontfamily='stix')


def test_default_math_fontfamily():
    mpl.rcParams['mathtext.fontset'] = 'cm'
    test_str = r'abc$abc\alpha$'
    fig, ax = plt.subplots()

    text1 = fig.text(0.1, 0.1, test_str, font='Arial')
    prop1 = text1.get_fontproperties()
    assert prop1.get_math_fontfamily() == 'cm'
    text2 = fig.text(0.2, 0.2, test_str, fontproperties='Arial')
    prop2 = text2.get_fontproperties()
    assert prop2.get_math_fontfamily() == 'cm'

    fig.draw_without_rendering()


def test_argument_order():
    mpl.rcParams['mathtext.fontset'] = 'cm'
    test_str = r'abc$abc\alpha$'
    fig, ax = plt.subplots()

    text1 = fig.text(0.1, 0.1, test_str,
                     math_fontfamily='dejavusans', font='Arial')
    prop1 = text1.get_fontproperties()
    assert prop1.get_math_fontfamily() == 'dejavusans'
    text2 = fig.text(0.2, 0.2, test_str,
                     math_fontfamily='dejavusans', fontproperties='Arial')
    prop2 = text2.get_fontproperties()
    assert prop2.get_math_fontfamily() == 'dejavusans'
    text3 = fig.text(0.3, 0.3, test_str,
                     font='Arial', math_fontfamily='dejavusans')
    prop3 = text3.get_fontproperties()
    assert prop3.get_math_fontfamily() == 'dejavusans'
    text4 = fig.text(0.4, 0.4, test_str,
                     fontproperties='Arial', math_fontfamily='dejavusans')
    prop4 = text4.get_fontproperties()
    assert prop4.get_math_fontfamily() == 'dejavusans'

    fig.draw_without_rendering()


def test_mathtext_cmr10_minus_sign():
    # cmr10 does not contain a minus sign and used to issue a warning
    # RuntimeWarning: Glyph 8722 missing from current font.
    mpl.rcParams['font.family'] = 'cmr10'
    mpl.rcParams['axes.formatter.use_mathtext'] = True
    fig, ax = plt.subplots()
    ax.plot(range(-1, 1), range(-1, 1))
    # draw to make sure we have no warnings
    fig.canvas.draw()


def test_mathtext_operators():
    test_str = r'''
    \increment \smallin \notsmallowns
    \smallowns \QED \rightangle
    \smallintclockwise \smallvarointclockwise
    \smallointctrcclockwise
    \ratio \minuscolon \dotsminusdots
    \sinewave \simneqq \nlesssim
    \ngtrsim \nlessgtr \ngtrless
    \cupleftarrow \oequal \rightassert
    \rightModels \hermitmatrix \barvee
    \measuredrightangle \varlrtriangle
    \equalparallel \npreccurlyeq \nsucccurlyeq
    \nsqsubseteq \nsqsupseteq \sqsubsetneq
    \sqsupsetneq  \disin \varisins
    \isins \isindot \varisinobar
    \isinobar \isinvb \isinE
    \nisd \varnis \nis
    \varniobar \niobar \bagmember
    \triangle'''.split()

    fig = plt.figure()
    for x, i in enumerate(test_str):
        fig.text(0.5, (x + 0.5)/len(test_str), r'${%s}$' % i)

    fig.draw_without_rendering()


@check_figures_equal(extensions=["png"])
def test_boldsymbol(fig_test, fig_ref):
    fig_test.text(0.1, 0.2, r"$\boldsymbol{\mathrm{abc0123\alpha}}$")
    fig_ref.text(0.1, 0.2, r"$\mathrm{abc0123\alpha}$")
