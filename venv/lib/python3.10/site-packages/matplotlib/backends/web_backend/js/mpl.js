/* Put everything inside the global mpl namespace */
/* global mpl */
window.mpl = {};

mpl.get_websocket_type = function () {
    if (typeof WebSocket !== 'undefined') {
        return WebSocket;
    } else if (typeof MozWebSocket !== 'undefined') {
        return MozWebSocket;
    } else {
        alert(
            'Your browser does not have WebSocket support. ' +
                'Please try Chrome, Safari or Firefox ≥ 6. ' +
                'Firefox 4 and 5 are also supported but you ' +
                'have to enable WebSockets in about:config.'
        );
    }
};

mpl.figure = function (figure_id, websocket, ondownload, parent_element) {
    this.id = figure_id;

    this.ws = websocket;

    this.supports_binary = this.ws.binaryType !== undefined;

    if (!this.supports_binary) {
        var warnings = document.getElementById('mpl-warnings');
        if (warnings) {
            warnings.style.display = 'block';
            warnings.textContent =
                'This browser does not support binary websocket messages. ' +
                'Performance may be slow.';
        }
    }

    this.imageObj = new Image();

    this.context = undefined;
    this.message = undefined;
    this.canvas = undefined;
    this.rubberband_canvas = undefined;
    this.rubberband_context = undefined;
    this.format_dropdown = undefined;

    this.image_mode = 'full';

    this.root = document.createElement('div');
    this.root.setAttribute('style', 'display: inline-block');
    this._root_extra_style(this.root);

    parent_element.appendChild(this.root);

    this._init_header(this);
    this._init_canvas(this);
    this._init_toolbar(this);

    var fig = this;

    this.waiting = false;

    this.ws.onopen = function () {
        fig.send_message('supports_binary', { value: fig.supports_binary });
        fig.send_message('send_image_mode', {});
        if (fig.ratio !== 1) {
            fig.send_message('set_device_pixel_ratio', {
                device_pixel_ratio: fig.ratio,
            });
        }
        fig.send_message('refresh', {});
    };

    this.imageObj.onload = function () {
        if (fig.image_mode === 'full') {
            // Full images could contain transparency (where diff images
            // almost always do), so we need to clear the canvas so that
            // there is no ghosting.
            fig.context.clearRect(0, 0, fig.canvas.width, fig.canvas.height);
        }
        fig.context.drawImage(fig.imageObj, 0, 0);
    };

    this.imageObj.onunload = function () {
        fig.ws.close();
    };

    this.ws.onmessage = this._make_on_message_function(this);

    this.ondownload = ondownload;
};

mpl.figure.prototype._init_header = function () {
    var titlebar = document.createElement('div');
    titlebar.classList =
        'ui-dialog-titlebar ui-widget-header ui-corner-all ui-helper-clearfix';
    var titletext = document.createElement('div');
    titletext.classList = 'ui-dialog-title';
    titletext.setAttribute(
        'style',
        'width: 100%; text-align: center; padding: 3px;'
    );
    titlebar.appendChild(titletext);
    this.root.appendChild(titlebar);
    this.header = titletext;
};

mpl.figure.prototype._canvas_extra_style = function (_canvas_div) {};

mpl.figure.prototype._root_extra_style = function (_canvas_div) {};

mpl.figure.prototype._init_canvas = function () {
    var fig = this;

    var canvas_div = (this.canvas_div = document.createElement('div'));
    canvas_div.setAttribute('tabindex', '0');
    canvas_div.setAttribute(
        'style',
        'border: 1px solid #ddd;' +
            'box-sizing: content-box;' +
            'clear: both;' +
            'min-height: 1px;' +
            'min-width: 1px;' +
            'outline: 0;' +
            'overflow: hidden;' +
            'position: relative;' +
            'resize: both;' +
            'z-index: 2;'
    );

    function on_keyboard_event_closure(name) {
        return function (event) {
            return fig.key_event(event, name);
        };
    }

    canvas_div.addEventListener(
        'keydown',
        on_keyboard_event_closure('key_press')
    );
    canvas_div.addEventListener(
        'keyup',
        on_keyboard_event_closure('key_release')
    );

    this._canvas_extra_style(canvas_div);
    this.root.appendChild(canvas_div);

    var canvas = (this.canvas = document.createElement('canvas'));
    canvas.classList.add('mpl-canvas');
    canvas.setAttribute(
        'style',
        'box-sizing: content-box;' +
            'pointer-events: none;' +
            'position: relative;' +
            'z-index: 0;'
    );

    this.context = canvas.getContext('2d');

    var backingStore =
        this.context.backingStorePixelRatio ||
        this.context.webkitBackingStorePixelRatio ||
        this.context.mozBackingStorePixelRatio ||
        this.context.msBackingStorePixelRatio ||
        this.context.oBackingStorePixelRatio ||
        this.context.backingStorePixelRatio ||
        1;

    this.ratio = (window.devicePixelRatio || 1) / backingStore;

    var rubberband_canvas = (this.rubberband_canvas = document.createElement(
        'canvas'
    ));
    rubberband_canvas.setAttribute(
        'style',
        'box-sizing: content-box;' +
            'left: 0;' +
            'pointer-events: none;' +
            'position: absolute;' +
            'top: 0;' +
            'z-index: 1;'
    );

    // Apply a ponyfill if ResizeObserver is not implemented by browser.
    if (this.ResizeObserver === undefined) {
        if (window.ResizeObserver !== undefined) {
            this.ResizeObserver = window.ResizeObserver;
        } else {
            var obs = _JSXTOOLS_RESIZE_OBSERVER({});
            this.ResizeObserver = obs.ResizeObserver;
        }
    }

    this.resizeObserverInstance = new this.ResizeObserver(function (entries) {
        // There's no need to resize if the WebSocket is not connected:
        // - If it is still connecting, then we will get an initial resize from
        //   Python once it connects.
        // - If it has disconnected, then resizing will clear the canvas and
        //   never get anything back to refill it, so better to not resize and
        //   keep something visible.
        if (fig.ws.readyState != 1) {
            return;
        }
        var nentries = entries.length;
        for (var i = 0; i < nentries; i++) {
            var entry = entries[i];
            var width, height;
            if (entry.contentBoxSize) {
                if (entry.contentBoxSize instanceof Array) {
                    // Chrome 84 implements new version of spec.
                    width = entry.contentBoxSize[0].inlineSize;
                    height = entry.contentBoxSize[0].blockSize;
                } else {
                    // Firefox implements old version of spec.
                    width = entry.contentBoxSize.inlineSize;
                    height = entry.contentBoxSize.blockSize;
                }
            } else {
                // Chrome <84 implements even older version of spec.
                width = entry.contentRect.width;
                height = entry.contentRect.height;
            }

            // Keep the size of the canvas and rubber band canvas in sync with
            // the canvas container.
            if (entry.devicePixelContentBoxSize) {
                // Chrome 84 implements new version of spec.
                canvas.setAttribute(
                    'width',
                    entry.devicePixelContentBoxSize[0].inlineSize
                );
                canvas.setAttribute(
                    'height',
                    entry.devicePixelContentBoxSize[0].blockSize
                );
            } else {
                canvas.setAttribute('width', width * fig.ratio);
                canvas.setAttribute('height', height * fig.ratio);
            }
            /* This rescales the canvas back to display pixels, so that it
             * appears correct on HiDPI screens. */
            canvas.style.width = width + 'px';
            canvas.style.height = height + 'px';

            rubberband_canvas.setAttribute('width', width);
            rubberband_canvas.setAttribute('height', height);

            // And update the size in Python. We ignore the initial 0/0 size
            // that occurs as the element is placed into the DOM, which should
            // otherwise not happen due to the minimum size styling.
            if (width != 0 && height != 0) {
                fig.request_resize(width, height);
            }
        }
    });
    this.resizeObserverInstance.observe(canvas_div);

    function on_mouse_event_closure(name) {
        /* User Agent sniffing is bad, but WebKit is busted:
         * https://bugs.webkit.org/show_bug.cgi?id=144526
         * https://bugs.webkit.org/show_bug.cgi?id=181818
         * The worst that happens here is that they get an extra browser
         * selection when dragging, if this check fails to catch them.
         */
        var UA = navigator.userAgent;
        var isWebKit = /AppleWebKit/.test(UA) && !/Chrome/.test(UA);
        if(isWebKit) {
            return function (event) {
                /* This prevents the web browser from automatically changing to
                 * the text insertion cursor when the button is pressed. We
                 * want to control all of the cursor setting manually through
                 * the 'cursor' event from matplotlib */
                event.preventDefault()
                return fig.mouse_event(event, name);
            };
        } else {
            return function (event) {
                return fig.mouse_event(event, name);
            };
        }
    }

    canvas_div.addEventListener(
        'mousedown',
        on_mouse_event_closure('button_press')
    );
    canvas_div.addEventListener(
        'mouseup',
        on_mouse_event_closure('button_release')
    );
    canvas_div.addEventListener(
        'dblclick',
        on_mouse_event_closure('dblclick')
    );
    // Throttle sequential mouse events to 1 every 20ms.
    canvas_div.addEventListener(
        'mousemove',
        on_mouse_event_closure('motion_notify')
    );

    canvas_div.addEventListener(
        'mouseenter',
        on_mouse_event_closure('figure_enter')
    );
    canvas_div.addEventListener(
        'mouseleave',
        on_mouse_event_closure('figure_leave')
    );

    canvas_div.addEventListener('wheel', function (event) {
        if (event.deltaY < 0) {
            event.step = 1;
        } else {
            event.step = -1;
        }
        on_mouse_event_closure('scroll')(event);
    });

    canvas_div.appendChild(canvas);
    canvas_div.appendChild(rubberband_canvas);

    this.rubberband_context = rubberband_canvas.getContext('2d');
    this.rubberband_context.strokeStyle = '#000000';

    this._resize_canvas = function (width, height, forward) {
        if (forward) {
            canvas_div.style.width = width + 'px';
            canvas_div.style.height = height + 'px';
        }
    };

    // Disable right mouse context menu.
    canvas_div.addEventListener('contextmenu', function (_e) {
        event.preventDefault();
        return false;
    });

    function set_focus() {
        canvas.focus();
        canvas_div.focus();
    }

    window.setTimeout(set_focus, 100);
};

mpl.figure.prototype._init_toolbar = function () {
    var fig = this;

    var toolbar = document.createElement('div');
    toolbar.classList = 'mpl-toolbar';
    this.root.appendChild(toolbar);

    function on_click_closure(name) {
        return function (_event) {
            return fig.toolbar_button_onclick(name);
        };
    }

    function on_mouseover_closure(tooltip) {
        return function (event) {
            if (!event.currentTarget.disabled) {
                return fig.toolbar_button_onmouseover(tooltip);
            }
        };
    }

    fig.buttons = {};
    var buttonGroup = document.createElement('div');
    buttonGroup.classList = 'mpl-button-group';
    for (var toolbar_ind in mpl.toolbar_items) {
        var name = mpl.toolbar_items[toolbar_ind][0];
        var tooltip = mpl.toolbar_items[toolbar_ind][1];
        var image = mpl.toolbar_items[toolbar_ind][2];
        var method_name = mpl.toolbar_items[toolbar_ind][3];

        if (!name) {
            /* Instead of a spacer, we start a new button group. */
            if (buttonGroup.hasChildNodes()) {
                toolbar.appendChild(buttonGroup);
            }
            buttonGroup = document.createElement('div');
            buttonGroup.classList = 'mpl-button-group';
            continue;
        }

        var button = (fig.buttons[name] = document.createElement('button'));
        button.classList = 'mpl-widget';
        button.setAttribute('role', 'button');
        button.setAttribute('aria-disabled', 'false');
        button.addEventListener('click', on_click_closure(method_name));
        button.addEventListener('mouseover', on_mouseover_closure(tooltip));

        var icon_img = document.createElement('img');
        icon_img.src = '_images/' + image + '.png';
        icon_img.srcset = '_images/' + image + '_large.png 2x';
        icon_img.alt = tooltip;
        button.appendChild(icon_img);

        buttonGroup.appendChild(button);
    }

    if (buttonGroup.hasChildNodes()) {
        toolbar.appendChild(buttonGroup);
    }

    var fmt_picker = document.createElement('select');
    fmt_picker.classList = 'mpl-widget';
    toolbar.appendChild(fmt_picker);
    this.format_dropdown = fmt_picker;

    for (var ind in mpl.extensions) {
        var fmt = mpl.extensions[ind];
        var option = document.createElement('option');
        option.selected = fmt === mpl.default_extension;
        option.innerHTML = fmt;
        fmt_picker.appendChild(option);
    }

    var status_bar = document.createElement('span');
    status_bar.classList = 'mpl-message';
    toolbar.appendChild(status_bar);
    this.message = status_bar;
};

mpl.figure.prototype.request_resize = function (x_pixels, y_pixels) {
    // Request matplotlib to resize the figure. Matplotlib will then trigger a resize in the client,
    // which will in turn request a refresh of the image.
    this.send_message('resize', { width: x_pixels, height: y_pixels });
};

mpl.figure.prototype.send_message = function (type, properties) {
    properties['type'] = type;
    properties['figure_id'] = this.id;
    this.ws.send(JSON.stringify(properties));
};

mpl.figure.prototype.send_draw_message = function () {
    if (!this.waiting) {
        this.waiting = true;
        this.ws.send(JSON.stringify({ type: 'draw', figure_id: this.id }));
    }
};

mpl.figure.prototype.handle_save = function (fig, _msg) {
    var format_dropdown = fig.format_dropdown;
    var format = format_dropdown.options[format_dropdown.selectedIndex].value;
    fig.ondownload(fig, format);
};

mpl.figure.prototype.handle_resize = function (fig, msg) {
    var size = msg['size'];
    if (size[0] !== fig.canvas.width || size[1] !== fig.canvas.height) {
        fig._resize_canvas(size[0], size[1], msg['forward']);
        fig.send_message('refresh', {});
    }
};

mpl.figure.prototype.handle_rubberband = function (fig, msg) {
    var x0 = msg['x0'] / fig.ratio;
    var y0 = (fig.canvas.height - msg['y0']) / fig.ratio;
    var x1 = msg['x1'] / fig.ratio;
    var y1 = (fig.canvas.height - msg['y1']) / fig.ratio;
    x0 = Math.floor(x0) + 0.5;
    y0 = Math.floor(y0) + 0.5;
    x1 = Math.floor(x1) + 0.5;
    y1 = Math.floor(y1) + 0.5;
    var min_x = Math.min(x0, x1);
    var min_y = Math.min(y0, y1);
    var width = Math.abs(x1 - x0);
    var height = Math.abs(y1 - y0);

    fig.rubberband_context.clearRect(
        0,
        0,
        fig.canvas.width / fig.ratio,
        fig.canvas.height / fig.ratio
    );

    fig.rubberband_context.strokeRect(min_x, min_y, width, height);
};

mpl.figure.prototype.handle_figure_label = function (fig, msg) {
    // Updates the figure title.
    fig.header.textContent = msg['label'];
};

mpl.figure.prototype.handle_cursor = function (fig, msg) {
    fig.canvas_div.style.cursor = msg['cursor'];
};

mpl.figure.prototype.handle_message = function (fig, msg) {
    fig.message.textContent = msg['message'];
};

mpl.figure.prototype.handle_draw = function (fig, _msg) {
    // Request the server to send over a new figure.
    fig.send_draw_message();
};

mpl.figure.prototype.handle_image_mode = function (fig, msg) {
    fig.image_mode = msg['mode'];
};

mpl.figure.prototype.handle_history_buttons = function (fig, msg) {
    for (var key in msg) {
        if (!(key in fig.buttons)) {
            continue;
        }
        fig.buttons[key].disabled = !msg[key];
        fig.buttons[key].setAttribute('aria-disabled', !msg[key]);
    }
};

mpl.figure.prototype.handle_navigate_mode = function (fig, msg) {
    if (msg['mode'] === 'PAN') {
        fig.buttons['Pan'].classList.add('active');
        fig.buttons['Zoom'].classList.remove('active');
    } else if (msg['mode'] === 'ZOOM') {
        fig.buttons['Pan'].classList.remove('active');
        fig.buttons['Zoom'].classList.add('active');
    } else {
        fig.buttons['Pan'].classList.remove('active');
        fig.buttons['Zoom'].classList.remove('active');
    }
};

mpl.figure.prototype.updated_canvas_event = function () {
    // Called whenever the canvas gets updated.
    this.send_message('ack', {});
};

// A function to construct a web socket function for onmessage handling.
// Called in the figure constructor.
mpl.figure.prototype._make_on_message_function = function (fig) {
    return function socket_on_message(evt) {
        if (evt.data instanceof Blob) {
            var img = evt.data;
            if (img.type !== 'image/png') {
                /* FIXME: We get "Resource interpreted as Image but
                 * transferred with MIME type text/plain:" errors on
                 * Chrome.  But how to set the MIME type?  It doesn't seem
                 * to be part of the websocket stream */
                img.type = 'image/png';
            }

            /* Free the memory for the previous frames */
            if (fig.imageObj.src) {
                (window.URL || window.webkitURL).revokeObjectURL(
                    fig.imageObj.src
                );
            }

            fig.imageObj.src = (window.URL || window.webkitURL).createObjectURL(
                img
            );
            fig.updated_canvas_event();
            fig.waiting = false;
            return;
        } else if (
            typeof evt.data === 'string' &&
            evt.data.slice(0, 21) === 'data:image/png;base64'
        ) {
            fig.imageObj.src = evt.data;
            fig.updated_canvas_event();
            fig.waiting = false;
            return;
        }

        var msg = JSON.parse(evt.data);
        var msg_type = msg['type'];

        // Call the  "handle_{type}" callback, which takes
        // the figure and JSON message as its only arguments.
        try {
            var callback = fig['handle_' + msg_type];
        } catch (e) {
            console.log(
                "No handler for the '%s' message type: ",
                msg_type,
                msg
            );
            return;
        }

        if (callback) {
            try {
                // console.log("Handling '%s' message: ", msg_type, msg);
                callback(fig, msg);
            } catch (e) {
                console.log(
                    "Exception inside the 'handler_%s' callback:",
                    msg_type,
                    e,
                    e.stack,
                    msg
                );
            }
        }
    };
};

function getModifiers(event) {
    var mods = [];
    if (event.ctrlKey) {
        mods.push('ctrl');
    }
    if (event.altKey) {
        mods.push('alt');
    }
    if (event.shiftKey) {
        mods.push('shift');
    }
    if (event.metaKey) {
        mods.push('meta');
    }
    return mods;
}

/*
 * return a copy of an object with only non-object keys
 * we need this to avoid circular references
 * https://stackoverflow.com/a/24161582/3208463
 */
function simpleKeys(original) {
    return Object.keys(original).reduce(function (obj, key) {
        if (typeof original[key] !== 'object') {
            obj[key] = original[key];
        }
        return obj;
    }, {});
}

mpl.figure.prototype.mouse_event = function (event, name) {
    if (name === 'button_press') {
        this.canvas.focus();
        this.canvas_div.focus();
    }

    // from https://stackoverflow.com/q/1114465
    var boundingRect = this.canvas.getBoundingClientRect();
    var x = (event.clientX - boundingRect.left) * this.ratio;
    var y = (event.clientY - boundingRect.top) * this.ratio;

    this.send_message(name, {
        x: x,
        y: y,
        button: event.button,
        step: event.step,
        buttons: event.buttons,
        modifiers: getModifiers(event),
        guiEvent: simpleKeys(event),
    });

    return false;
};

mpl.figure.prototype._key_event_extra = function (_event, _name) {
    // Handle any extra behaviour associated with a key event
};

mpl.figure.prototype.key_event = function (event, name) {
    // Prevent repeat events
    if (name === 'key_press') {
        if (event.key === this._key) {
            return;
        } else {
            this._key = event.key;
        }
    }
    if (name === 'key_release') {
        this._key = null;
    }

    var value = '';
    if (event.ctrlKey && event.key !== 'Control') {
        value += 'ctrl+';
    }
    else if (event.altKey && event.key !== 'Alt') {
        value += 'alt+';
    }
    else if (event.shiftKey && event.key !== 'Shift') {
        value += 'shift+';
    }

    value += 'k' + event.key;

    this._key_event_extra(event, name);

    this.send_message(name, { key: value, guiEvent: simpleKeys(event) });
    return false;
};

mpl.figure.prototype.toolbar_button_onclick = function (name) {
    if (name === 'download') {
        this.handle_save(this, null);
    } else {
        this.send_message('toolbar_button', { name: name });
    }
};

mpl.figure.prototype.toolbar_button_onmouseover = function (tooltip) {
    this.message.textContent = tooltip;
};

///////////////// REMAINING CONTENT GENERATED BY embed_js.py /////////////////
// prettier-ignore
var _JSXTOOLS_RESIZE_OBSERVER=function(A){var t,i=new WeakMap,n=new WeakMap,a=new WeakMap,r=new WeakMap,o=new Set;function s(e){if(!(this instanceof s))throw new TypeError("Constructor requires 'new' operator");i.set(this,e)}function h(){throw new TypeError("Function is not a constructor")}function c(e,t,i,n){e=0 in arguments?Number(arguments[0]):0,t=1 in arguments?Number(arguments[1]):0,i=2 in arguments?Number(arguments[2]):0,n=3 in arguments?Number(arguments[3]):0,this.right=(this.x=this.left=e)+(this.width=i),this.bottom=(this.y=this.top=t)+(this.height=n),Object.freeze(this)}function d(){t=requestAnimationFrame(d);var s=new WeakMap,p=new Set;o.forEach((function(t){r.get(t).forEach((function(i){var r=t instanceof window.SVGElement,o=a.get(t),d=r?0:parseFloat(o.paddingTop),f=r?0:parseFloat(o.paddingRight),l=r?0:parseFloat(o.paddingBottom),u=r?0:parseFloat(o.paddingLeft),g=r?0:parseFloat(o.borderTopWidth),m=r?0:parseFloat(o.borderRightWidth),w=r?0:parseFloat(o.borderBottomWidth),b=u+f,F=d+l,v=(r?0:parseFloat(o.borderLeftWidth))+m,W=g+w,y=r?0:t.offsetHeight-W-t.clientHeight,E=r?0:t.offsetWidth-v-t.clientWidth,R=b+v,z=F+W,M=r?t.width:parseFloat(o.width)-R-E,O=r?t.height:parseFloat(o.height)-z-y;if(n.has(t)){var k=n.get(t);if(k[0]===M&&k[1]===O)return}n.set(t,[M,O]);var S=Object.create(h.prototype);S.target=t,S.contentRect=new c(u,d,M,O),s.has(i)||(s.set(i,[]),p.add(i)),s.get(i).push(S)}))})),p.forEach((function(e){i.get(e).call(e,s.get(e),e)}))}return s.prototype.observe=function(i){if(i instanceof window.Element){r.has(i)||(r.set(i,new Set),o.add(i),a.set(i,window.getComputedStyle(i)));var n=r.get(i);n.has(this)||n.add(this),cancelAnimationFrame(t),t=requestAnimationFrame(d)}},s.prototype.unobserve=function(i){if(i instanceof window.Element&&r.has(i)){var n=r.get(i);n.has(this)&&(n.delete(this),n.size||(r.delete(i),o.delete(i))),n.size||r.delete(i),o.size||cancelAnimationFrame(t)}},A.DOMRectReadOnly=c,A.ResizeObserver=s,A.ResizeObserverEntry=h,A}; // eslint-disable-line
