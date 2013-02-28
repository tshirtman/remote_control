# encoding: utf-8
from kivy.app import App
from kivy.properties import \
    ListProperty, ObjectProperty, StringProperty, NumericProperty
from kivy.support import install_twisted_reactor

from kivy.metrics import dp, sp
from kivy.clock import Clock

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.dropdown import DropDown

# installing twisted reactor the kivy way before importing anything from
# twisted
install_twisted_reactor()

from twisted.internet import reactor
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from ConfigParser import ConfigParser

from functools import partial

from json import JSONDecoder
from json import JSONEncoder

json_decode = JSONDecoder().raw_decode
json_encode = JSONEncoder().encode

__version__ = '0.01'

CONFIG = 'remote_command.cfg'


class CommandClient(Protocol):
    def sendMessage(self, msg):
        self.transport.write(msg)

    def dataReceived(self, data):
        app.receive(data)


class CommandClientFactory(Factory):
    def buildProtocol(self, *args):
        return CommandClient()


class MousePad(Widget):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            if touch.is_double_tap:
                touch.ud['pressed'] = True
                app.mouse_press()
            return True
        return super(MousePad, self).on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current == self:
            app.mouse_move(touch.dx, touch.dy)
            return True
        return super(MousePad, self).on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current == self:
            touch.ungrab(self)
            if 'pressed' in touch.ud:
                app.mouse_release()
            return True
        return super(MousePad, self).on_touch_up(touch)


class RemoteCommand(App):
    commands = ListProperty([])
    container = ObjectProperty(None)
    status = ObjectProperty(None)
    log = StringProperty('')
    mouse_sensivity = NumericProperty(1)
    screen_texture = ObjectProperty(None)
    image_size = NumericProperty(7)
    dropdown = ObjectProperty(None)

    def connect(self, ip, port):
        point = TCP4ClientEndpoint(reactor, ip, int(port))
        d = point.connect(CommandClientFactory())
        d.addCallback(self.got_protocol)
        self.log += u"trying to connect…\n"

        if ip not in self.config.items('connections'):
            self.config.set('connections', ip, str(port))

    def send(self, *args, **kwargs):
        self.protocol.sendMessage(json_encode(kwargs))

    def update_screen(self, *args):
        self.send(command='capture', size=(self.image_size, self.image_size))

    def propose_addresses(self, address_input):
        if address_input.focus:
            if not self.dropdown:
                self.dropdown = DropDown()
                #self.dropdown.bind(on_select=self.complete_address)
            else:
                self.dropdown.clear_widgets()

            connections = self.config.items('connections')

            for c in connections:
                if c[0].startswith(address_input.text):
                    lbl = Button(text=':'.join(c), size_hint_y=None,
                                 height=sp(20))
                    lbl.bind(on_press=lambda x:
                             self.connect(*x.text.split(':')))
                    self.dropdown.add_widget(lbl)

            Clock.schedule_once(lambda *x:
                                self.dropdown.open(address_input.parent), 1)

    def receive(self, data):
        while data:
            try:
                datadict, index = json_decode(data)
            except ValueError:
                # corrupted data? gtfo for now, FIXME
                return

            data = data[index:]

            #self.log += 'got data: %s\n' % datadict
            if not isinstance(datadict, dict):
                # something went wrong, gtfo for now, FIXME
                return

            if 'commands' in datadict:
                self.commands = datadict['commands']

            if 'status' in datadict:
                status = datadict['status']
                self.status.clear_widgets()

                for uid, command in status.items():
                    box = BoxLayout(size_hint_y='None', height='30dp')
                    label = Label(text=' '.join(command['command']))
                    button = Button(text='x')
                    button.bind(on_press=partial(
                        self.send, command='kill', uid=uid))
                    box.add_widget(label)
                    box.add_widget(button)
                    self.status.add_widget(box)

            if 'capture' in datadict:
                with open('tmp.bmp', 'w') as f:
                    f.write(datadict['capture'].decode('base64'))

                self.screen_texture.reload()

    def got_protocol(self, p):
        self.log += "got protocol\n"
        self.protocol = p
        self.send(command='list')
        Clock.schedule_interval(self.update_screen, .1)

    def on_commands(self, *args):
        self.container.clear_widgets()
        self.log += 'got a list of commands!\n'
        for command, arguments in self.commands:
            box = BoxLayout(height=dp(30))
            button = Button(text=command)

            args_inputs = []
            for arg in arguments.split(','):
                if arg == 'str':
                    txtinput = TextInput()
                    args_inputs.append(txtinput)
                    box.add_widget(txtinput)

            button.bind(on_press=partial(
                self.execute, command, arguments.split(','), args_inputs))
            box.add_widget(button)

            self.container.add_widget(box)

    def execute(self, command, arguments, args_inputs, *args):
        values = []
        for arg_type, arg_input in zip(arguments, args_inputs):
            if arg_type == 'str':
                values.append(arg_input.text)

        self.send(run=command, arguments=values)

    def mouse_move(self, dx, dy):
        self.send(command='mouse', action='move',
                  dx=int(round(dx * self.mouse_sensivity)),
                  dy=-int(round(dy * self.mouse_sensivity)))

    def mouse_click(self, b=1, n=2):
        self.send(command='mouse', action='click', b=b, n=n)

    def mouse_press(self, b=1):
        self.log += 'mouse pressed\n'
        self.send(command='mouse', action='press', b=b)

    def mouse_release(self, b=1):
        self.log += 'mouse released\n'
        self.send(command='mouse', action='release', b=b)

    def send_keys(self, string):
        self.send(command='type', string=string)

    def press_special_key(self, key):
        self.send(command='press_key', key=key.text)

    def release_special_key(self, key):
        self.send(command='release_key', key=key.text)

    def on_start(self, *args):
        self.config = ConfigParser()
        self.config.read(CONFIG)

        if not self.config.has_section('connections'):
            self.config.add_section('connections')

            with open(CONFIG, 'w') as f:
                self.config.write(f)

    def on_pause(self, *args):
        with open(CONFIG, 'w') as f:
            self.config.write(f)
        return True

    def on_resume(self, *args):
        return True

    def on_stop(self, *args):
        with open(CONFIG, 'w') as f:
            self.config.write(f)
        return True

    def populate_keyboard(self, grid):
        b = Button(text='escape')
        b.bind(on_press=self.press_special_key)
        b.bind(on_release=self.release_special_key)
        grid.add_widget(b)

        for f in range(12):
            b = Button(text='f%d' % (f + 1))
            b.bind(on_press=self.press_special_key)
            b.bind(on_release=self.release_special_key)
            grid.add_widget(b)

        for i in range(13):
            grid.add_widget(Widget())

        grid.add_widget(Widget())

        b = Button(text='up')
        b.bind(on_press=self.press_special_key)
        b.bind(on_release=self.release_special_key)
        grid.add_widget(b)

        for i in range(11):
            grid.add_widget(Widget())

        for t in 'left', 'down', 'right':
            b = Button(text=t)
            b.bind(on_press=self.press_special_key)
            b.bind(on_release=self.release_special_key)
            grid.add_widget(b)

        grid.add_widget(Widget())

        for t in 'up', 'down':
            b = Button(text='pg%s' % t)
            b.bind(on_press=self.press_special_key)
            b.bind(on_release=self.release_special_key)
            grid.add_widget(b)

        grid.add_widget(Widget())

        b = Button(text='return')
        b.bind(on_press=self.press_special_key)
        b.bind(on_release=self.release_special_key)
        grid.add_widget(b)


if __name__ == '__main__':
    global app
    app = RemoteCommand()
    app.run()
