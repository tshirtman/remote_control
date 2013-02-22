Remote control
==============

This is a simple remote control program, intended to allow to run specific
(configured) commands, on the computer where the server runs, from a device
where the client runs.

Both client and server uses twisted to communicate, so python and twisted are
necessary on both. 

Server
======

The server reads from the `shellserver.cfg` file in the directory it was started from.
The main section is the [commands] one, which list the available commands by name, e.g:

```
[commands]
tv=
```

to each command must correspond a section of the same name:

```
[tv]
command=vlc some_internet_playlist.m3u
```

Commands can define parameters the user will be able to input from the interface.

```
[commands]
my_command=str,
```

will automatically add a TextInput on the line of the command button, and the
value will be passed to the command. Currently, only `str` is managed, but it
can be extended if need arise.

If the config file is changed, the server will reload the it automatically.

Client
======

Client needs to connect to the ip/port of the server (server listen to port
1234 by default). When connected, the list of commands is retrieved, and the
buttons are created.

The client feature a mouse control, which works a bit like a touchpad, with
buttons to click on the right, and a slider to control sensibility on the fly.


Credits
=======

Remote Control uses:
Twisted for the network management, which make things so much easier
Kivy for the client gui
PyMouse for cross plateform mouse control on the server side.
