/* global mpl */

var comm_websocket_adapter = function (comm) {
    // Create a "websocket"-like object which calls the given IPython comm
    // object with the appropriate methods. Currently this is a non binary
    // socket, so there is still some room for performance tuning.
    var ws = {};

    ws.binaryType = comm.kernel.ws.binaryType;
    ws.readyState = comm.kernel.ws.readyState;
    function updateReadyState(_event) {
        if (comm.kernel.ws) {
            ws.readyState = comm.kernel.ws.readyState;
        } else {
            ws.readyState = 3; // Closed state.
        }
    }
    comm.kernel.ws.addEventListener('open', updateReadyState);
    comm.kernel.ws.addEventListener('close', updateReadyState);
    comm.kernel.ws.addEventListener('error', updateReadyState);

    ws.close = function () {
        comm.close();
    };
    ws.send = function (m) {
        //console.log('sending', m);
        comm.send(m);
    };
    // Register the callback with on_msg.
    comm.on_msg(function (msg) {
        //console.log('receiving', msg['content']['data'], msg);
        var data = msg['content']['data'];
        if (data['blob'] !== undefined) {
            data = {
                data: new Blob(msg['buffers'], { type: data['blob'] }),
            };
        }
        // Pass the mpl event to the overridden (by mpl) onmessage function.
        ws.onmessage(data);
    });
    return ws;
};

mpl.mpl_figure_comm = function (comm, msg) {
    // This is the function which gets called when the mpl process
    // starts-up an IPython Comm through the "matplotlib" channel.

    var id = msg.content.data.id;
    // Get hold of the div created by the display call when the Comm
    // socket was opened in Python.
    var element = document.getElementById(id);
    var ws_proxy = comm_websocket_adapter(comm);

    function ondownload(figure, _format) {
        window.open(figure.canvas.toDataURL());
    }

    var fig = new mpl.figure(id, ws_proxy, ondownload, element);

    // Call onopen now - mpl needs it, as it is assuming we've passed it a real
    // web socket which is closed, not our websocket->open comm proxy.
    ws_proxy.onopen();

    fig.parent_element = element;
    fig.cell_info = mpl.find_output_cell("<div id='" + id + "'></div>");
    if (!fig.cell_info) {
        console.error('Failed to find cell for figure', id, fig);
        return;
    }
    fig.cell_info[0].output_area.element.on(
        'cleared',
        { fig: fig },
        fig._remove_fig_handler
    );
};

mpl.figure.prototype.handle_close = function (fig, msg) {
    var width = fig.canvas.width / fig.ratio;
    fig.cell_info[0].output_area.element.off(
        'cleared',
        fig._remove_fig_handler
    );
    fig.resizeObserverInstance.unobserve(fig.canvas_div);

    // Update the output cell to use the data from the current canvas.
    fig.push_to_output();
    var dataURL = fig.canvas.toDataURL();
    // Re-enable the keyboard manager in IPython - without this line, in FF,
    // the notebook keyboard shortcuts fail.
    IPython.keyboard_manager.enable();
    fig.parent_element.innerHTML =
        '<img src="' + dataURL + '" width="' + width + '">';
    fig.close_ws(fig, msg);
};

mpl.figure.prototype.close_ws = function (fig, msg) {
    fig.send_message('closing', msg);
    // fig.ws.close()
};

mpl.figure.prototype.push_to_output = function (_remove_interactive) {
    // Turn the data on the canvas into data in the output cell.
    var width = this.canvas.width / this.ratio;
    var dataURL = this.canvas.toDataURL();
    this.cell_info[1]['text/html'] =
        '<img src="' + dataURL + '" width="' + width + '">';
};

mpl.figure.prototype.updated_canvas_event = function () {
    // Tell IPython that the notebook contents must change.
    IPython.notebook.set_dirty(true);
    this.send_message('ack', {});
    var fig = this;
    // Wait a second, then push the new image to the DOM so
    // that it is saved nicely (might be nice to debounce this).
    setTimeout(function () {
        fig.push_to_output();
    }, 1000);
};

mpl.figure.prototype._init_toolbar = function () {
    var fig = this;

    var toolbar = document.createElement('div');
    toolbar.classList = 'btn-toolbar';
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
    buttonGroup.classList = 'btn-group';
    var button;
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
            buttonGroup.classList = 'btn-group';
            continue;
        }

        button = fig.buttons[name] = document.createElement('button');
        button.classList = 'btn btn-default';
        button.href = '#';
        button.title = name;
        button.innerHTML = '<i class="fa ' + image + ' fa-lg"></i>';
        button.addEventListener('click', on_click_closure(method_name));
        button.addEventListener('mouseover', on_mouseover_closure(tooltip));
        buttonGroup.appendChild(button);
    }

    if (buttonGroup.hasChildNodes()) {
        toolbar.appendChild(buttonGroup);
    }

    // Add the status bar.
    var status_bar = document.createElement('span');
    status_bar.classList = 'mpl-message pull-right';
    toolbar.appendChild(status_bar);
    this.message = status_bar;

    // Add the close button to the window.
    var buttongrp = document.createElement('div');
    buttongrp.classList = 'btn-group inline pull-right';
    button = document.createElement('button');
    button.classList = 'btn btn-mini btn-primary';
    button.href = '#';
    button.title = 'Stop Interaction';
    button.innerHTML = '<i class="fa fa-power-off icon-remove icon-large"></i>';
    button.addEventListener('click', function (_evt) {
        fig.handle_close(fig, {});
    });
    button.addEventListener(
        'mouseover',
        on_mouseover_closure('Stop Interaction')
    );
    buttongrp.appendChild(button);
    var titlebar = this.root.querySelector('.ui-dialog-titlebar');
    titlebar.insertBefore(buttongrp, titlebar.firstChild);
};

mpl.figure.prototype._remove_fig_handler = function (event) {
    var fig = event.data.fig;
    if (event.target !== this) {
        // Ignore bubbled events from children.
        return;
    }
    fig.close_ws(fig, {});
};

mpl.figure.prototype._root_extra_style = function (el) {
    el.style.boxSizing = 'content-box'; // override notebook setting of border-box.
};

mpl.figure.prototype._canvas_extra_style = function (el) {
    // this is important to make the div 'focusable
    el.setAttribute('tabindex', 0);
    // reach out to IPython and tell the keyboard manager to turn it's self
    // off when our div gets focus

    // location in version 3
    if (IPython.notebook.keyboard_manager) {
        IPython.notebook.keyboard_manager.register_events(el);
    } else {
        // location in version 2
        IPython.keyboard_manager.register_events(el);
    }
};

mpl.figure.prototype._key_event_extra = function (event, _name) {
    // Check for shift+enter
    if (event.shiftKey && event.which === 13) {
        this.canvas_div.blur();
        // select the cell after this one
        var index = IPython.notebook.find_cell_index(this.cell_info[0]);
        IPython.notebook.select(index + 1);
    }
};

mpl.figure.prototype.handle_save = function (fig, _msg) {
    fig.ondownload(fig, null);
};

mpl.find_output_cell = function (html_output) {
    // Return the cell and output element which can be found *uniquely* in the notebook.
    // Note - this is a bit hacky, but it is done because the "notebook_saving.Notebook"
    // IPython event is triggered only after the cells have been serialised, which for
    // our purposes (turning an active figure into a static one), is too late.
    var cells = IPython.notebook.get_cells();
    var ncells = cells.length;
    for (var i = 0; i < ncells; i++) {
        var cell = cells[i];
        if (cell.cell_type === 'code') {
            for (var j = 0; j < cell.output_area.outputs.length; j++) {
                var data = cell.output_area.outputs[j];
                if (data.data) {
                    // IPython >= 3 moved mimebundle to data attribute of output
                    data = data.data;
                }
                if (data['text/html'] === html_output) {
                    return [cell, data, j];
                }
            }
        }
    }
};

// Register the function which deals with the matplotlib target/channel.
// The kernel may be null if the page has been refreshed.
if (IPython.notebook.kernel !== null) {
    IPython.notebook.kernel.comm_manager.register_target(
        'matplotlib',
        mpl.mpl_figure_comm
    );
}
