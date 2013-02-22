# encoding: utf-8
from kivy.app import App
from kivy.properties import \
    ListProperty, ObjectProperty, StringProperty, NumericProperty
from kivy.support import install_twisted_reactor

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# installing twisted reactor the kivy way before importing anything from
# twisted
install_twisted_reactor()

from twisted.internet import reactor
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from functools import partial

from json import JSONDecoder
from json import JSONEncoder

json_decode = JSONDecoder().decode
json_encode = JSONEncoder().encode

__version__ = '0.01'


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

    def on_container(self, *args):
        self.log += "got container\n"
        print self.container

    def connect(self, ip, port):
        point = TCP4ClientEndpoint(reactor, ip, port)
        d = point.connect(CommandClientFactory())
        d.addCallback(self.got_protocol)
        self.log += u"trying to connect…\n"

    def send(self, **kwargs):
        self.protocol.sendMessage(json_encode(kwargs))

    def receive(self, data):
        datadict = json_decode(data)
        self.log += 'got data: %s\n' % datadict
        if 'commands' in datadict:
            self.commands = datadict['commands']

        if 'status' in datadict:
            self.status.clear_widgets()

            for command in datadict['running']:
                box = BoxLayout()
                label = command['name']
                button = Button(text='x')
                button.bind(on_press=partial(
                    self.send, {'command': 'kill', 'id': command['id']}))
                box.add_widget(label)
                box.add_widget(button)
                self.status.add_widget(box)

    def got_protocol(self, p):
        self.log += "got protocol\n"
        self.protocol = p
        self.send(command='list')

    def on_commands(self, *args):
        self.container.clear_widgets()
        self.log += 'got a list of commands!\n'
        for command, arguments in self.commands:
            box = BoxLayout(height='30dp')
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
                  dx=round(dx * self.mouse_sensivity),
                  dy=-round(dy * self.mouse_sensivity))

    def mouse_click(self, b=1, n=2):
        self.send(command='mouse', action='click', b=b, n=n)

    def mouse_press(self, b=1):
        self.log += 'mouse pressed\n'
        self.send(command='mouse', action='press', b=b)

    def mouse_release(self, b=1):
        self.log += 'mouse released\n'
        self.send(command='mouse', action='release', b=b)

    def on_pause(self, *args):
        return True

    def on_resume(self, *args):
        return True


if __name__ == '__main__':
    global app
    app = RemoteCommand()
    app.run()
