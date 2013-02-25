from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from ConfigParser import ConfigParser
from json import JSONDecoder, JSONEncoder
from lib.pymouse import PyMouse
from subprocess import Popen, PIPE
from uuid import uuid4
from time import time

CONFIG = 'shellserver.cfg'


class CommandShell(protocol.Protocol):
    def init(self):
        self.running = []
        self.mouse = PyMouse()
        reactor.callLater(1, self.clock_update_status)
        self.status = {}
        self.running = {}

    def load_config(self, *args):
        if args:
            masks = inotify.humanReadableMask(args[2])
            print masks
            if not set(masks).intersection(set(('delete_self', ))):
                return

        self.config = ConfigParser()
        self.config.read(CONFIG)
        self.commands = self.config.items('commands')

        if args:
            print "config reloaded"

        notifier = inotify.INotify()
        notifier.startReading()
        print "adding watcher"
        notifier.watch(filepath.FilePath(CONFIG), callbacks=[self.load_config])
        print "config watcher started"

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

            print "shouldn't be blocking"
            if p.poll():
                to_remove.add(uid)
            print "right?"

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

        return self.transport.write(JSONEncoder().encode({
            'status': self.status,
            'log': log
        }))

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
        print data
        while data:
            decode, index = JSONDecoder().raw_decode(data)
            data = data[index:]
            print decode

            print self.commands
            if decode.get('command') == 'list':
                self.transport.write(JSONEncoder().encode(
                    {'commands': self.commands}))

            elif decode.get('command') == 'mouse':
                pos = self.mouse.position()
                action = decode.get('action')

                if action == 'click':
                    self.mouse.click(*pos,
                                     button=decode.get('b'),
                                     n=decode.get('n'))

                elif action == 'move':
                    self.mouse.move(pos[0] + decode.get('dx'),
                                    pos[1] + decode.get('dy'))

                elif action == 'press':
                    self.mouse.press(*pos, button=decode.get('b'))

                elif action == 'release':
                    self.mouse.release(*pos, button=decode.get('b'))

            elif decode.get('command') == 'status':
                    self.update_status()

            elif decode.get('command') == 'kill':
                self.kill_app(decode['uid'])
                self.update_status()

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
