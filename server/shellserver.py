from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from ConfigParser import ConfigParser
from subprocess import Popen, PIPE
from uuid import uuid4
from time import time
from autopy import mouse, key, bitmap

from json import JSONDecoder
from json import JSONEncoder

json_decode = JSONDecoder().raw_decode
json_encode = JSONEncoder().encode

BUTTONS = mouse.LEFT_BUTTON, mouse.RIGHT_BUTTON, mouse.CENTER_BUTTON

CONFIG = 'shellserver.cfg'


class CommandShell(protocol.Protocol):
    def init(self):
        self.running = []
        reactor.callLater(1, self.clock_update_status)
        self.status = {}
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

    def send(self, *args, **kwargs):
        self.transport.write(json_encode(kwargs))

    def execute(self, command, arguments):
        print "running %s" % command
        cmd = self.config.get(command, 'command').split(' ')

        if (
            'log' in self.config.items(command) and
            self.config.get(command, 'log')
        ):
            process = Popen(cmd + arguments, stdout=PIPE, stderr=PIPE)
        else:
            process = Popen(cmd + arguments)

        uid = uuid4().hex
        self.status[uid] = {'command': command, 'time': time()}
        self.running[uid] = process

    def clock_update_status(self):
        self.update_status()
        reactor.callLater(1, self.clock_update_status)

    def update_status(self):
        log = ''
        to_remove = set()
        for uid in self.status:
            p = self.running[uid]
            command = self.status[uid]['command']

            if p.poll():
                to_remove.add(uid)

            if (
                'log' in self.config.items(command) and
                self.config.get(command, 'log')
            ):
                try:
                    outs = p.communicate()
                    log += outs[0].decode('utf-8')
                    log += outs[1].decode('utf-8')
                except ValueError, e:
                    if 'closed file' in e:
                        to_remove.add(uid)
                    else:
                        raise

        for uid in to_remove:
            self.running.remove(uid)
            self.status.remove(uid)

        return self.send(status=self.status, log=log)

    def kill_app(self, appid):
        if appid in self.running:
            try:
                self.running[appid].terminate()
                self.running.pop(appid)
                self.status.pop(appid)

            except OSError, e:
                if 'No such process' in e:
                    self.status.pop(appid)
                    self.running.pop(appid)
                else:
                    raise e

    def dataReceived(self, data):
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

            if command == 'list':
                self.send(commands=self.commands)

            elif command == 'mouse':
                pos = mouse.get_pos()
                action = decode.get('action')

                if action == 'click':
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

            elif command == 'status':
                    self.update_status()

            elif command == 'kill':
                self.kill_app(decode['uid'])
                self.update_status()

            elif command == 'capture':
                pos = mouse.get_pos()
                size = decode.get('size')
                rect = ((
                    max(0, pos[0] - size[0] / 2),
                    max(0, pos[1] - size[1] / 2)
                ), (size[0] / 2, size[1] / 2))

                print rect
                bitmap.capture_screen(rect).save('tmp.bmp')

                with open('tmp.bmp') as f:
                    self.send(capture=f.read().encode('base64'), size=size)

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
