from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from ConfigParser import ConfigParser
from json import JSONDecoder, JSONEncoder
from lib.pymouse import PyMouse
import subprocess

CONFIG = 'shellserver.cfg'


class CommandShell(protocol.Protocol):
    def init(self):
        self.running = []
        self.mouse = PyMouse()

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
        command = self.config.get(command, 'command').split(' ')
        process = subprocess.Popen(command + arguments,
                                   stdout=subprocess.PIPE)
        self.running.append((command, process))

    def update_status(self):
        status = {}
        for c, p in self.running:
            status[c] = {}
            status[c]['status'] = p.poll()
            if p.poll():
                self.running.remove(p)
            if self.config.get(c, 'output'):
                status[c]['output'] = p.stdout.read().decode('utf-8')
        return status

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
                self.transport.write(JSONEncoder().encode(
                    self.update_status()))

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
