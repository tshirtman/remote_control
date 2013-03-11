from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from ConfigParser import ConfigParser
#from subprocess import Popen, PIPE
from uuid import uuid4
from time import time
from autopy import mouse, key, bitmap, screen

from json import JSONDecoder
from json import JSONEncoder

from os import environ

json_decode = JSONDecoder().raw_decode
json_encode = JSONEncoder().encode

BUTTONS = mouse.LEFT_BUTTON, mouse.RIGHT_BUTTON, mouse.CENTER_BUTTON

CONFIG = 'shellserver.cfg'

CHUNKSIZE = 1 * 1024


class ShellProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, command_shell, uid, name, send_logs):
        self.uid = uid
        self.command_shell = command_shell
        self.name = name
        self.send_logs = send_logs

    def connectionMade(self):
        self.start_time = time()
        self.command_shell.send(name=self.name, process=self.uid,
                                status='started')
        self.transport.closeStdin()

    def outReceived(self, data):
        print "out:", data
        if self.send_logs:
            self.command_shell.send(
                process=self.uid,
                stdout=data.encode('base64'))

    def errReceived(self, data):
        print "err:", data
        if self.send_logs:
            self.command_shell.send(
                process=self.uid,
                stderr=data.encode('base64'))

    def processEnded(self, status):
        self.command_shell.send(
            process=self.uid,
            status='ended',
            autoclose=(
                self.command_shell.config.has_option(self.name, 'autoclose') and
                self.command_shell.config.get(self.name, 'autoclose')))

    def kill(self):
        self.transport.signalProcess('TERM')


class CommandShell(protocol.Protocol):
    def init(self):
        self.running = {}

    def load_config(self, *args):
        if args:
            masks = inotify.humanReadableMask(args[2])
            #print masks
            if not set(masks).intersection(set(('delete_self', ))):
                return

        self.config = ConfigParser()
        self.config.read(CONFIG)
        self.commands = self.config.items('commands')

        if args:
            print "config reloaded"

        notifier = inotify.INotify()
        notifier.startReading()
        #print "adding watcher"
        notifier.watch(filepath.FilePath(CONFIG), callbacks=[self.load_config])
        print "config watcher started"
        reactor.callLater(.5, self.send, commands=self.commands)

    def send(self, *args, **kwargs):
        self.transport.write(json_encode(kwargs))

    def send_image(self, filename):
        uuid = str(time())
        with open(filename) as f:
            c = 0
            while True:
                s = f.read(CHUNKSIZE).encode('base64')
                #print 'sending chunk %s: %s' % (c, s[:20])
                self.send(image=uuid, data=s, chunk=c)
                c += 1

                if not s:
                    #print "end"
                    break

    def execute(self, command, arguments):
        print "running %s" % command
        cmd = self.config.get(command, 'command').split(' ')
        uid = uuid4().hex

        send_logs = (
            self.config.has_option(command, 'log') and
            self.config.get(command, 'log'))

        process = ShellProcessProtocol(
            uid=uid,
            command_shell=self,
            name=command,
            send_logs=send_logs)

        reactor.spawnProcess(process, cmd[0], cmd + arguments, env=environ)

        self.running[uid] = process

    def kill_app(self, appid):
        if appid in self.running:
            self.running[appid].kill()

    def dataReceived(self, data):
        #print "datareceived", data
        while data:
            try:
                decode, index = json_decode(data)
            except ValueError:
                # something went wrong.. FIXME
                return

            data = data[index:]

            if not isinstance(decode, dict):
                # something went wrong, gtfo for now, FIXME
                return

            command = decode.get('command')
            if command == 'mouse':
                pos = mouse.get_pos()
                action = decode.get('action')

                if action == 'click':
                    for i in range(decode.get('n') or 1):
                        mouse.click(BUTTONS[decode.get('b') - 1])

                elif action == 'move':
                    try:
                        mouse.move(pos[0] + decode.get('dx'),
                                   pos[1] + decode.get('dy'))
                    except ValueError:
                        pass

                elif action == 'press':
                    mouse.toggle(True, BUTTONS[decode.get('b') - 1])

                elif action == 'release':
                    mouse.toggle(False, BUTTONS[decode.get('b') - 1])

            elif command == 'type':
                key.type_string(decode['string'])

            elif command == 'press_key':
                key.toggle(getattr(key, 'K_' + decode['key'].upper()), True)

            elif command == 'release_key':
                key.toggle(getattr(key, 'K_' + decode['key'].upper()), False)

            elif command == 'kill':
                self.kill_app(decode['uid'])

            elif command == 'capture':
                pos = mouse.get_pos()
                size = decode.get('size')
                maxx, maxy = screen.get_size()
                rect = ((
                    max(0, min((pos[0] - size[0] / 2), maxx - size[0])),
                    max(0, min((pos[1] - size[1] / 2), maxy - size[1]))
                ), (size[0], size[1]))

                try:
                    bitmap.capture_screen(rect).save('tmp.png')
                except ValueError:
                    return

                self.send(mouse_pos=(pos[0] - rect[0][0], pos[1] - rect[0][1]))

                #print "sending capture"
                self.send_image('tmp.png')

            elif decode.get('run') in zip(*self.commands)[0]:
                self.execute(decode.get('run'), decode.get('arguments'))


class CommandShellFactory(protocol.Factory):
    def buildProtocol(self, addr):
        shell = CommandShell()
        shell.init()
        shell.load_config()
        print "factory built"
        return shell

reactor.listenTCP(1234, CommandShellFactory())
reactor.run()
