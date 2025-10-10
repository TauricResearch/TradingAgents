def blocking_input_loop(figure, event_names, timeout, handler):
    """
    Run *figure*'s event loop while listening to interactive events.

    The events listed in *event_names* are passed to *handler*.

    This function is used to implement `.Figure.waitforbuttonpress`,
    `.Figure.ginput`, and `.Axes.clabel`.

    Parameters
    ----------
    figure : `~matplotlib.figure.Figure`
    event_names : list of str
        The names of the events passed to *handler*.
    timeout : float
        If positive, the event loop is stopped after *timeout* seconds.
    handler : Callable[[Event], Any]
        Function called for each event; it can force an early exit of the event
        loop by calling ``canvas.stop_event_loop()``.
    """
    if figure.canvas.manager:
        figure.show()  # Ensure that the figure is shown if we are managing it.
    # Connect the events to the on_event function call.
    cids = [figure.canvas.mpl_connect(name, handler) for name in event_names]
    try:
        figure.canvas.start_event_loop(timeout)  # Start event loop.
    finally:  # Run even on exception like ctrl-c.
        # Disconnect the callbacks.
        for cid in cids:
            figure.canvas.mpl_disconnect(cid)
