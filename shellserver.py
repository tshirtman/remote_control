from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from ConfigParser import ConfigParser
from simplejson import JSONDecoder, JSONEncoder
import subprocess

CONFIG = 'shellserver.cfg'


class CommandShell(protocol.Protocol):
    def init(self):
        self.running = []

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
        command = self.config.get(command, 'command')
        process = subprocess.Popen([command, ] + arguments,
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
        decode = JSONDecoder().decode(data)
        print decode

        print self.commands
        if decode.get('command') == 'list':
            self.transport.write(JSONEncoder().encode(
                {'commands': self.commands}))

        elif decode.get('command') == 'status':
            self.transport.write(JSONEncoder().encode(self.update_status()))

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
