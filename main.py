# encoding: utf-8
from kivy.app import App
from kivy.lang import Builder
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.support import install_twisted_reactor

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

# installing twisted reactor the kivy way before importing anything from
# twisted
install_twisted_reactor()

from twisted.internet import reactor
from twisted.internet.protocol import Factory, Protocol
from twisted.internet.endpoints import TCP4ClientEndpoint

from functools import partial

from simplejson import JSONDecoder
from simplejson import JSONEncoder

json_decode = JSONDecoder().decode
json_encode = JSONEncoder().encode

__version__ = '0.01'


kvbase = '''
BoxLayout:
    orientation: 'vertical'
    BoxLayout:
        size_hint_y: None
        height: '35dp'

        TextInput:
            id: address

        TextInput:
            id: port

        Button:
            text: 'connect'
            size_hint_x: None
            width: self.texture_size[0] + dp(2)
            on_press: app.connect(address.text, int(port.text))

    ScrollView:
        do_scroll_x: False
        do_scroll_y: True

        BoxLayout:
            on_parent: app.container = self
            orientation: 'vertical'
            size_hint_y: None
            height: sum((x.height for x in self.children))
            Button:
                text: 'placeholder'

    ScrollView:
        size_hint_y: .3
        Label:
            size_hint_y: None
            text_size: self.width, None
            height: self.texture_size[1]
            text: app.log

            canvas:
                Color:
                    rgba: .3, .3, .3, .5
                Rectangle:
                    pos: 0, 0
                    size: self.width, self.top
'''


class CommandClient(Protocol):
    def sendMessage(self, msg):
        self.transport.write(msg)

    def dataReceived(self, data):
        app.receive(data)


class CommandClientFactory(Factory):
    def buildProtocol(self, *args):
        return CommandClient()


class RemoteCommand(App):
    commands = ListProperty([])
    container = ObjectProperty(None)
    log = StringProperty('')

    def on_container(self, *args):
        self.log += "got container\n"
        print self.container

    def build(self):
        return Builder.load_string(kvbase)

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

    def got_protocol(self, p):
        self.log += "got protocol\n"
        self.protocol = p
        self.send(command='list')

    def on_commands(self, *args):
        self.container.clear_widgets()
        self.log += 'got a list of commands!\n'
        for command, arguments in self.commands:
            box = BoxLayout()
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


if __name__ == '__main__':
    global app
    app = RemoteCommand()
    app.run()
