"""Displays Agg images in the browser, with interactivity."""

# The WebAgg backend is divided into two modules:
#
# - `backend_webagg_core.py` contains code necessary to embed a WebAgg
#   plot inside of a web application, and communicate in an abstract
#   way over a web socket.
#
# - `backend_webagg.py` contains a concrete implementation of a basic
#   application, implemented with tornado.

from contextlib import contextmanager
import errno
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import random
import sys
import signal
import threading

try:
    import tornado.web
    import tornado.ioloop
    import tornado.websocket
except ImportError as err:
    raise RuntimeError("The WebAgg backend requires Tornado.") from err

import matplotlib as mpl
from matplotlib.backend_bases import _Backend
from matplotlib._pylab_helpers import Gcf
from . import backend_webagg_core as core
from .backend_webagg_core import (  # noqa: F401 # pylint: disable=W0611
    TimerAsyncio, TimerTornado)


webagg_server_thread = threading.Thread(
    target=lambda: tornado.ioloop.IOLoop.instance().start())


class FigureManagerWebAgg(core.FigureManagerWebAgg):
    _toolbar2_class = core.NavigationToolbar2WebAgg

    @classmethod
    def pyplot_show(cls, *, block=None):
        WebAggApplication.initialize()

        url = "http://{address}:{port}{prefix}".format(
            address=WebAggApplication.address,
            port=WebAggApplication.port,
            prefix=WebAggApplication.url_prefix)

        if mpl.rcParams['webagg.open_in_browser']:
            import webbrowser
            if not webbrowser.open(url):
                print(f"To view figure, visit {url}")
        else:
            print(f"To view figure, visit {url}")

        WebAggApplication.start()


class FigureCanvasWebAgg(core.FigureCanvasWebAggCore):
    manager_class = FigureManagerWebAgg


class WebAggApplication(tornado.web.Application):
    initialized = False
    started = False

    class FavIcon(tornado.web.RequestHandler):
        def get(self):
            self.set_header('Content-Type', 'image/png')
            self.write(Path(mpl.get_data_path(),
                            'images/matplotlib.png').read_bytes())

    class SingleFigurePage(tornado.web.RequestHandler):
        def __init__(self, application, request, *, url_prefix='', **kwargs):
            self.url_prefix = url_prefix
            super().__init__(application, request, **kwargs)

        def get(self, fignum):
            fignum = int(fignum)
            manager = Gcf.get_fig_manager(fignum)

            ws_uri = f'ws://{self.request.host}{self.url_prefix}/'
            self.render(
                "single_figure.html",
                prefix=self.url_prefix,
                ws_uri=ws_uri,
                fig_id=fignum,
                toolitems=core.NavigationToolbar2WebAgg.toolitems,
                canvas=manager.canvas)

    class AllFiguresPage(tornado.web.RequestHandler):
        def __init__(self, application, request, *, url_prefix='', **kwargs):
            self.url_prefix = url_prefix
            super().__init__(application, request, **kwargs)

        def get(self):
            ws_uri = f'ws://{self.request.host}{self.url_prefix}/'
            self.render(
                "all_figures.html",
                prefix=self.url_prefix,
                ws_uri=ws_uri,
                figures=sorted(Gcf.figs.items()),
                toolitems=core.NavigationToolbar2WebAgg.toolitems)

    class MplJs(tornado.web.RequestHandler):
        def get(self):
            self.set_header('Content-Type', 'application/javascript')

            js_content = core.FigureManagerWebAgg.get_javascript()

            self.write(js_content)

    class Download(tornado.web.RequestHandler):
        def get(self, fignum, fmt):
            fignum = int(fignum)
            manager = Gcf.get_fig_manager(fignum)
            self.set_header(
                'Content-Type', mimetypes.types_map.get(fmt, 'binary'))
            buff = BytesIO()
            manager.canvas.figure.savefig(buff, format=fmt)
            self.write(buff.getvalue())

    class WebSocket(tornado.websocket.WebSocketHandler):
        supports_binary = True

        def open(self, fignum):
            self.fignum = int(fignum)
            self.manager = Gcf.get_fig_manager(self.fignum)
            self.manager.add_web_socket(self)
            if hasattr(self, 'set_nodelay'):
                self.set_nodelay(True)

        def on_close(self):
            self.manager.remove_web_socket(self)

        def on_message(self, message):
            message = json.loads(message)
            # The 'supports_binary' message is on a client-by-client
            # basis.  The others affect the (shared) canvas as a
            # whole.
            if message['type'] == 'supports_binary':
                self.supports_binary = message['value']
            else:
                manager = Gcf.get_fig_manager(self.fignum)
                # It is possible for a figure to be closed,
                # but a stale figure UI is still sending messages
                # from the browser.
                if manager is not None:
                    manager.handle_json(message)

        def send_json(self, content):
            self.write_message(json.dumps(content))

        def send_binary(self, blob):
            if self.supports_binary:
                self.write_message(blob, binary=True)
            else:
                data_uri = "data:image/png;base64,{}".format(
                    blob.encode('base64').replace('\n', ''))
                self.write_message(data_uri)

    def __init__(self, url_prefix=''):
        if url_prefix:
            assert url_prefix[0] == '/' and url_prefix[-1] != '/', \
                'url_prefix must start with a "/" and not end with one.'

        super().__init__(
            [
                # Static files for the CSS and JS
                (url_prefix + r'/_static/(.*)',
                 tornado.web.StaticFileHandler,
                 {'path': core.FigureManagerWebAgg.get_static_file_path()}),

                # Static images for the toolbar
                (url_prefix + r'/_images/(.*)',
                 tornado.web.StaticFileHandler,
                 {'path': Path(mpl.get_data_path(), 'images')}),

                # A Matplotlib favicon
                (url_prefix + r'/favicon.ico', self.FavIcon),

                # The page that contains all of the pieces
                (url_prefix + r'/([0-9]+)', self.SingleFigurePage,
                 {'url_prefix': url_prefix}),

                # The page that contains all of the figures
                (url_prefix + r'/?', self.AllFiguresPage,
                 {'url_prefix': url_prefix}),

                (url_prefix + r'/js/mpl.js', self.MplJs),

                # Sends images and events to the browser, and receives
                # events from the browser
                (url_prefix + r'/([0-9]+)/ws', self.WebSocket),

                # Handles the downloading (i.e., saving) of static images
                (url_prefix + r'/([0-9]+)/download.([a-z0-9.]+)',
                 self.Download),
            ],
            template_path=core.FigureManagerWebAgg.get_static_file_path())

    @classmethod
    def initialize(cls, url_prefix='', port=None, address=None):
        if cls.initialized:
            return

        # Create the class instance
        app = cls(url_prefix=url_prefix)

        cls.url_prefix = url_prefix

        # This port selection algorithm is borrowed, more or less
        # verbatim, from IPython.
        def random_ports(port, n):
            """
            Generate a list of n random ports near the given port.

            The first 5 ports will be sequential, and the remaining n-5 will be
            randomly selected in the range [port-2*n, port+2*n].
            """
            for i in range(min(5, n)):
                yield port + i
            for i in range(n - 5):
                yield port + random.randint(-2 * n, 2 * n)

        if address is None:
            cls.address = mpl.rcParams['webagg.address']
        else:
            cls.address = address
        cls.port = mpl.rcParams['webagg.port']
        for port in random_ports(cls.port,
                                 mpl.rcParams['webagg.port_retries']):
            try:
                app.listen(port, cls.address)
            except OSError as e:
                if e.errno != errno.EADDRINUSE:
                    raise
            else:
                cls.port = port
                break
        else:
            raise SystemExit(
                "The webagg server could not be started because an available "
                "port could not be found")

        cls.initialized = True

    @classmethod
    def start(cls):
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            cls.started = True

        if cls.started:
            return

        """
        IOLoop.running() was removed as of Tornado 2.4; see for example
        https://groups.google.com/forum/#!topic/python-tornado/QLMzkpQBGOY
        Thus there is no correct way to check if the loop has already been
        launched. We may end up with two concurrently running loops in that
        unlucky case with all the expected consequences.
        """
        ioloop = tornado.ioloop.IOLoop.instance()

        def shutdown():
            ioloop.stop()
            print("Server is stopped")
            sys.stdout.flush()
            cls.started = False

        @contextmanager
        def catch_sigint():
            old_handler = signal.signal(
                signal.SIGINT,
                lambda sig, frame: ioloop.add_callback_from_signal(shutdown))
            try:
                yield
            finally:
                signal.signal(signal.SIGINT, old_handler)

        # Set the flag to True *before* blocking on ioloop.start()
        cls.started = True

        print("Press Ctrl+C to stop WebAgg server")
        sys.stdout.flush()
        with catch_sigint():
            ioloop.start()


def ipython_inline_display(figure):
    import tornado.template

    WebAggApplication.initialize()
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if not webagg_server_thread.is_alive():
            webagg_server_thread.start()

    fignum = figure.number
    tpl = Path(core.FigureManagerWebAgg.get_static_file_path(),
               "ipython_inline_figure.html").read_text()
    t = tornado.template.Template(tpl)
    return t.generate(
        prefix=WebAggApplication.url_prefix,
        fig_id=fignum,
        toolitems=core.NavigationToolbar2WebAgg.toolitems,
        canvas=figure.canvas,
        port=WebAggApplication.port).decode('utf-8')


@_Backend.export
class _BackendWebAgg(_Backend):
    FigureCanvas = FigureCanvasWebAgg
    FigureManager = FigureManagerWebAgg
