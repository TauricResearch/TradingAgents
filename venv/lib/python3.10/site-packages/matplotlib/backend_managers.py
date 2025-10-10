from matplotlib import _api, backend_tools, cbook, widgets


class ToolEvent:
    """Event for tool manipulation (add/remove)."""
    def __init__(self, name, sender, tool, data=None):
        self.name = name
        self.sender = sender
        self.tool = tool
        self.data = data


class ToolTriggerEvent(ToolEvent):
    """Event to inform that a tool has been triggered."""
    def __init__(self, name, sender, tool, canvasevent=None, data=None):
        super().__init__(name, sender, tool, data)
        self.canvasevent = canvasevent


class ToolManagerMessageEvent:
    """
    Event carrying messages from toolmanager.

    Messages usually get displayed to the user by the toolbar.
    """
    def __init__(self, name, sender, message):
        self.name = name
        self.sender = sender
        self.message = message


class ToolManager:
    """
    Manager for actions triggered by user interactions (key press, toolbar
    clicks, ...) on a Figure.

    Attributes
    ----------
    figure : `.Figure`
    keypresslock : `~matplotlib.widgets.LockDraw`
        `.LockDraw` object to know if the `canvas` key_press_event is locked.
    messagelock : `~matplotlib.widgets.LockDraw`
        `.LockDraw` object to know if the message is available to write.
    """

    def __init__(self, figure=None):

        self._key_press_handler_id = None

        self._tools = {}
        self._keys = {}
        self._toggled = {}
        self._callbacks = cbook.CallbackRegistry()

        # to process keypress event
        self.keypresslock = widgets.LockDraw()
        self.messagelock = widgets.LockDraw()

        self._figure = None
        self.set_figure(figure)

    @property
    def canvas(self):
        """Canvas managed by FigureManager."""
        if not self._figure:
            return None
        return self._figure.canvas

    @property
    def figure(self):
        """Figure that holds the canvas."""
        return self._figure

    @figure.setter
    def figure(self, figure):
        self.set_figure(figure)

    def set_figure(self, figure, update_tools=True):
        """
        Bind the given figure to the tools.

        Parameters
        ----------
        figure : `.Figure`
        update_tools : bool, default: True
            Force tools to update figure.
        """
        if self._key_press_handler_id:
            self.canvas.mpl_disconnect(self._key_press_handler_id)
        self._figure = figure
        if figure:
            self._key_press_handler_id = self.canvas.mpl_connect(
                'key_press_event', self._key_press)
        if update_tools:
            for tool in self._tools.values():
                tool.figure = figure

    def toolmanager_connect(self, s, func):
        """
        Connect event with string *s* to *func*.

        Parameters
        ----------
        s : str
            The name of the event. The following events are recognized:

            - 'tool_message_event'
            - 'tool_removed_event'
            - 'tool_added_event'

            For every tool added a new event is created

            - 'tool_trigger_TOOLNAME', where TOOLNAME is the id of the tool.

        func : callable
            Callback function for the toolmanager event with signature::

                def func(event: ToolEvent) -> Any

        Returns
        -------
        cid
            The callback id for the connection. This can be used in
            `.toolmanager_disconnect`.
        """
        return self._callbacks.connect(s, func)

    def toolmanager_disconnect(self, cid):
        """
        Disconnect callback id *cid*.

        Example usage::

            cid = toolmanager.toolmanager_connect('tool_trigger_zoom', onpress)
            #...later
            toolmanager.toolmanager_disconnect(cid)
        """
        return self._callbacks.disconnect(cid)

    def message_event(self, message, sender=None):
        """Emit a `ToolManagerMessageEvent`."""
        if sender is None:
            sender = self

        s = 'tool_message_event'
        event = ToolManagerMessageEvent(s, sender, message)
        self._callbacks.process(s, event)

    @property
    def active_toggle(self):
        """Currently toggled tools."""
        return self._toggled

    def get_tool_keymap(self, name):
        """
        Return the keymap associated with the specified tool.

        Parameters
        ----------
        name : str
            Name of the Tool.

        Returns
        -------
        list of str
            List of keys associated with the tool.
        """

        keys = [k for k, i in self._keys.items() if i == name]
        return keys

    def _remove_keys(self, name):
        for k in self.get_tool_keymap(name):
            del self._keys[k]

    def update_keymap(self, name, key):
        """
        Set the keymap to associate with the specified tool.

        Parameters
        ----------
        name : str
            Name of the Tool.
        key : str or list of str
            Keys to associate with the tool.
        """
        if name not in self._tools:
            raise KeyError(f'{name!r} not in Tools')
        self._remove_keys(name)
        if isinstance(key, str):
            key = [key]
        for k in key:
            if k in self._keys:
                _api.warn_external(
                    f'Key {k} changed from {self._keys[k]} to {name}')
            self._keys[k] = name

    def remove_tool(self, name):
        """
        Remove tool named *name*.

        Parameters
        ----------
        name : str
            Name of the tool.
        """
        tool = self.get_tool(name)
        if getattr(tool, 'toggled', False):  # If it's a toggled toggle tool, untoggle
            self.trigger_tool(tool, 'toolmanager')
        self._remove_keys(name)
        event = ToolEvent('tool_removed_event', self, tool)
        self._callbacks.process(event.name, event)
        del self._tools[name]

    def add_tool(self, name, tool, *args, **kwargs):
        """
        Add *tool* to `ToolManager`.

        If successful, adds a new event ``tool_trigger_{name}`` where
        ``{name}`` is the *name* of the tool; the event is fired every time the
        tool is triggered.

        Parameters
        ----------
        name : str
            Name of the tool, treated as the ID, has to be unique.
        tool : type
            Class of the tool to be added.  A subclass will be used
            instead if one was registered for the current canvas class.
        *args, **kwargs
            Passed to the *tool*'s constructor.

        See Also
        --------
        matplotlib.backend_tools.ToolBase : The base class for tools.
        """

        tool_cls = backend_tools._find_tool_class(type(self.canvas), tool)
        if not tool_cls:
            raise ValueError('Impossible to find class for %s' % str(tool))

        if name in self._tools:
            _api.warn_external('A "Tool class" with the same name already '
                               'exists, not added')
            return self._tools[name]

        tool_obj = tool_cls(self, name, *args, **kwargs)
        self._tools[name] = tool_obj

        if tool_obj.default_keymap is not None:
            self.update_keymap(name, tool_obj.default_keymap)

        # For toggle tools init the radio_group in self._toggled
        if isinstance(tool_obj, backend_tools.ToolToggleBase):
            # None group is not mutually exclusive, a set is used to keep track
            # of all toggled tools in this group
            if tool_obj.radio_group is None:
                self._toggled.setdefault(None, set())
            else:
                self._toggled.setdefault(tool_obj.radio_group, None)

            # If initially toggled
            if tool_obj.toggled:
                self._handle_toggle(tool_obj, None, None)
        tool_obj.set_figure(self.figure)

        event = ToolEvent('tool_added_event', self, tool_obj)
        self._callbacks.process(event.name, event)

        return tool_obj

    def _handle_toggle(self, tool, canvasevent, data):
        """
        Toggle tools, need to untoggle prior to using other Toggle tool.
        Called from trigger_tool.

        Parameters
        ----------
        tool : `.ToolBase`
        canvasevent : Event
            Original Canvas event or None.
        data : object
            Extra data to pass to the tool when triggering.
        """

        radio_group = tool.radio_group
        # radio_group None is not mutually exclusive
        # just keep track of toggled tools in this group
        if radio_group is None:
            if tool.name in self._toggled[None]:
                self._toggled[None].remove(tool.name)
            else:
                self._toggled[None].add(tool.name)
            return

        # If the tool already has a toggled state, untoggle it
        if self._toggled[radio_group] == tool.name:
            toggled = None
        # If no tool was toggled in the radio_group
        # toggle it
        elif self._toggled[radio_group] is None:
            toggled = tool.name
        # Other tool in the radio_group is toggled
        else:
            # Untoggle previously toggled tool
            self.trigger_tool(self._toggled[radio_group],
                              self,
                              canvasevent,
                              data)
            toggled = tool.name

        # Keep track of the toggled tool in the radio_group
        self._toggled[radio_group] = toggled

    def trigger_tool(self, name, sender=None, canvasevent=None, data=None):
        """
        Trigger a tool and emit the ``tool_trigger_{name}`` event.

        Parameters
        ----------
        name : str
            Name of the tool.
        sender : object
            Object that wishes to trigger the tool.
        canvasevent : Event
            Original Canvas event or None.
        data : object
            Extra data to pass to the tool when triggering.
        """
        tool = self.get_tool(name)
        if tool is None:
            return

        if sender is None:
            sender = self

        if isinstance(tool, backend_tools.ToolToggleBase):
            self._handle_toggle(tool, canvasevent, data)

        tool.trigger(sender, canvasevent, data)  # Actually trigger Tool.

        s = 'tool_trigger_%s' % name
        event = ToolTriggerEvent(s, sender, tool, canvasevent, data)
        self._callbacks.process(s, event)

    def _key_press(self, event):
        if event.key is None or self.keypresslock.locked():
            return

        name = self._keys.get(event.key, None)
        if name is None:
            return
        self.trigger_tool(name, canvasevent=event)

    @property
    def tools(self):
        """A dict mapping tool name -> controlled tool."""
        return self._tools

    def get_tool(self, name, warn=True):
        """
        Return the tool object with the given name.

        For convenience, this passes tool objects through.

        Parameters
        ----------
        name : str or `.ToolBase`
            Name of the tool, or the tool itself.
        warn : bool, default: True
            Whether a warning should be emitted it no tool with the given name
            exists.

        Returns
        -------
        `.ToolBase` or None
            The tool or None if no tool with the given name exists.
        """
        if (isinstance(name, backend_tools.ToolBase)
                and name.name in self._tools):
            return name
        if name not in self._tools:
            if warn:
                _api.warn_external(
                    f"ToolManager does not control tool {name!r}")
            return None
        return self._tools[name]
