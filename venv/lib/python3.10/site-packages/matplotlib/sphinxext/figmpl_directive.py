"""
Add a ``figure-mpl`` directive that is a responsive version of ``figure``.

This implementation is very similar to ``.. figure::``, except it also allows a
``srcset=`` argument to be passed to the image tag, hence allowing responsive
resolution images.

There is no particular reason this could not be used standalone, but is meant
to be used with :doc:`/api/sphinxext_plot_directive_api`.

Note that the directory organization is a bit different than ``.. figure::``.
See the *FigureMpl* documentation below.

"""
import os
from os.path import relpath
from pathlib import PurePath, Path
import shutil

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives.images import Figure, Image
from sphinx.errors import ExtensionError

import matplotlib


class figmplnode(nodes.General, nodes.Element):
    pass


class FigureMpl(Figure):
    """
    Implements a directive to allow an optional hidpi image.

    Meant to be used with the *plot_srcset* configuration option in conf.py,
    and gets set in the TEMPLATE of plot_directive.py

    e.g.::

        .. figure-mpl:: plot_directive/some_plots-1.png
            :alt: bar
            :srcset: plot_directive/some_plots-1.png,
                     plot_directive/some_plots-1.2x.png 2.00x
            :class: plot-directive

    The resulting html (at ``some_plots.html``) is::

        <img src="sphx_glr_bar_001_hidpi.png"
            srcset="_images/some_plot-1.png,
                    _images/some_plots-1.2x.png 2.00x",
            alt="bar"
            class="plot_directive" />

    Note that the handling of subdirectories is different than that used by the sphinx
    figure directive::

        .. figure-mpl:: plot_directive/nestedpage/index-1.png
            :alt: bar
            :srcset: plot_directive/nestedpage/index-1.png
                     plot_directive/nestedpage/index-1.2x.png 2.00x
            :class: plot_directive

    The resulting html (at ``nestedpage/index.html``)::

        <img src="../_images/nestedpage-index-1.png"
            srcset="../_images/nestedpage-index-1.png,
                    ../_images/_images/nestedpage-index-1.2x.png 2.00x",
            alt="bar"
            class="sphx-glr-single-img" />

    where the subdirectory is included in the image name for uniqueness.
    """

    has_content = False
    required_arguments = 1
    optional_arguments = 2
    final_argument_whitespace = False
    option_spec = {
        'alt': directives.unchanged,
        'height': directives.length_or_unitless,
        'width': directives.length_or_percentage_or_unitless,
        'scale': directives.nonnegative_int,
        'align': Image.align,
        'class': directives.class_option,
        'caption': directives.unchanged,
        'srcset': directives.unchanged,
    }

    def run(self):

        image_node = figmplnode()

        imagenm = self.arguments[0]
        image_node['alt'] = self.options.get('alt', '')
        image_node['align'] = self.options.get('align', None)
        image_node['class'] = self.options.get('class', None)
        image_node['width'] = self.options.get('width', None)
        image_node['height'] = self.options.get('height', None)
        image_node['scale'] = self.options.get('scale', None)
        image_node['caption'] = self.options.get('caption', None)

        # we would like uri to be the highest dpi version so that
        # latex etc will use that.  But for now, lets just make
        # imagenm... maybe pdf one day?

        image_node['uri'] = imagenm
        image_node['srcset'] = self.options.get('srcset', None)

        return [image_node]


def _parse_srcsetNodes(st):
    """
    parse srcset...
    """
    entries = st.split(',')
    srcset = {}
    for entry in entries:
        spl = entry.strip().split(' ')
        if len(spl) == 1:
            srcset[0] = spl[0]
        elif len(spl) == 2:
            mult = spl[1][:-1]
            srcset[float(mult)] = spl[0]
        else:
            raise ExtensionError(f'srcset argument "{entry}" is invalid.')
    return srcset


def _copy_images_figmpl(self, node):

    # these will be the temporary place the plot-directive put the images eg:
    # ../../../build/html/plot_directive/users/explain/artists/index-1.png
    if node['srcset']:
        srcset = _parse_srcsetNodes(node['srcset'])
    else:
        srcset = None

    # the rst file's location:  eg /Users/username/matplotlib/doc/users/explain/artists
    docsource = PurePath(self.document['source']).parent

    # get the relpath relative to root:
    srctop = self.builder.srcdir
    rel = relpath(docsource, srctop).replace('.', '').replace(os.sep, '-')
    if len(rel):
        rel += '-'
    # eg: users/explain/artists

    imagedir = PurePath(self.builder.outdir, self.builder.imagedir)
    # eg: /Users/username/matplotlib/doc/build/html/_images/users/explain/artists

    Path(imagedir).mkdir(parents=True, exist_ok=True)

    # copy all the sources to the imagedir:
    if srcset:
        for src in srcset.values():
            # the entries in srcset are relative to docsource's directory
            abspath = PurePath(docsource, src)
            name = rel + abspath.name
            shutil.copyfile(abspath, imagedir / name)
    else:
        abspath = PurePath(docsource, node['uri'])
        name = rel + abspath.name
        shutil.copyfile(abspath, imagedir / name)

    return imagedir, srcset, rel


def visit_figmpl_html(self, node):

    imagedir, srcset, rel = _copy_images_figmpl(self, node)

    # /doc/examples/subd/plot_1.rst
    docsource = PurePath(self.document['source'])
    # /doc/
    # make sure to add the trailing slash:
    srctop = PurePath(self.builder.srcdir, '')
    # examples/subd/plot_1.rst
    relsource = relpath(docsource, srctop)
    # /doc/build/html
    desttop = PurePath(self.builder.outdir, '')
    # /doc/build/html/examples/subd
    dest = desttop / relsource

    # ../../_images/ for dirhtml and ../_images/ for html
    imagerel = PurePath(relpath(imagedir, dest.parent)).as_posix()
    if self.builder.name == "dirhtml":
        imagerel = f'..{imagerel}'

    # make uri also be relative...
    nm = PurePath(node['uri'][1:]).name
    uri = f'{imagerel}/{rel}{nm}'
    img_attrs = {'src': uri, 'alt': node['alt']}

    # make srcset str.  Need to change all the prefixes!
    maxsrc = uri
    if srcset:
        maxmult = -1
        srcsetst = ''
        for mult, src in srcset.items():
            nm = PurePath(src[1:]).name
            # ../../_images/plot_1_2_0x.png
            path = f'{imagerel}/{rel}{nm}'
            srcsetst += path
            if mult == 0:
                srcsetst += ', '
            else:
                srcsetst += f' {mult:1.2f}x, '

            if mult > maxmult:
                maxmult = mult
                maxsrc = path

        # trim trailing comma and space...
        img_attrs['srcset'] = srcsetst[:-2]

    if node['class'] is not None:
        img_attrs['class'] = ' '.join(node['class'])
    for style in ['width', 'height', 'scale']:
        if node[style]:
            if 'style' not in img_attrs:
                img_attrs['style'] = f'{style}: {node[style]};'
            else:
                img_attrs['style'] += f'{style}: {node[style]};'

    # <figure class="align-default" id="id1">
    # <a class="reference internal image-reference" href="_images/index-1.2x.png">
    # <img alt="_images/index-1.2x.png"
    #  src="_images/index-1.2x.png" style="width: 53%;" />
    # </a>
    # <figcaption>
    # <p><span class="caption-text">Figure caption is here....</span>
    # <a class="headerlink" href="#id1" title="Permalink to this image">#</a></p>
    # </figcaption>
    # </figure>
    self.body.append(
        self.starttag(
            node, 'figure',
            CLASS=f'align-{node["align"]}' if node['align'] else 'align-center'))
    self.body.append(
        self.starttag(node, 'a', CLASS='reference internal image-reference',
                      href=maxsrc) +
        self.emptytag(node, 'img', **img_attrs) +
        '</a>\n')
    if node['caption']:
        self.body.append(self.starttag(node, 'figcaption'))
        self.body.append(self.starttag(node, 'p'))
        self.body.append(self.starttag(node, 'span', CLASS='caption-text'))
        self.body.append(node['caption'])
        self.body.append('</span></p></figcaption>\n')
    self.body.append('</figure>\n')


def visit_figmpl_latex(self, node):

    if node['srcset'] is not None:
        imagedir, srcset = _copy_images_figmpl(self, node)
        maxmult = -1
        # choose the highest res version for latex:
        maxmult = max(srcset, default=-1)
        node['uri'] = PurePath(srcset[maxmult]).name

    self.visit_figure(node)


def depart_figmpl_html(self, node):
    pass


def depart_figmpl_latex(self, node):
    self.depart_figure(node)


def figurempl_addnode(app):
    app.add_node(figmplnode,
                 html=(visit_figmpl_html, depart_figmpl_html),
                 latex=(visit_figmpl_latex, depart_figmpl_latex))


def setup(app):
    app.add_directive("figure-mpl", FigureMpl)
    figurempl_addnode(app)
    metadata = {'parallel_read_safe': True, 'parallel_write_safe': True,
                'version': matplotlib.__version__}
    return metadata
