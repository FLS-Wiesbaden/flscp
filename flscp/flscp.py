#!/usr/bin/env python3

import logging
from urwid import (AttrMap, WidgetWrap, Padding, Divider, SolidFill,
                   WidgetDecoration, LineBox, Filler,

                   # widgets
                   Text, Edit, Frame, Columns, Pile, ListBox, SimpleListWalker,
                   Overlay,

                   # signals
                   signals, emit_signal, connect_signal, disconnect_signal
                   )
import urwid
from mysql.connector import errorcode
import mysql.connector
import string
from random import choice
import subprocess, shlex
import smtplib
import socket
from email.mime.text import MIMEText

DOMAIN = 2
DOMAIN_SUB = 0
DOMAIN_NAME = 'fls-wiesbaden.de'
db = None
try:
    db = mysql.connector.connect(
            user = 'root',
            password = '',
            host = 'localhost',
            port = 3306,
            database = 'imscp'
            )
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print('Something is wrong your username or password.')
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print('Database does not exist.')
    else:
        print(err)

class Scrollable:
    """A interface that makes widgets *scrollable*."""
    def scroll_up(self):
        raise NotImplementedError

    def scroll_down(self):
        raise NotImplementedError

    def scroll_top(self):
        raise NotImplementedError

    def scroll_bottom(self):
        raise NotImplementedError


class ScrollableListBox(ListBox, Scrollable):
    """
A ``urwid.ListBox`` subclass that implements the
:class:`~turses.ui.Scrollable` interface.
"""
    def __init__(self,
                 contents,
                 offset=1):
        """
Arguments:

`contents` is a list with the elements contained in the
`ScrollableListBox`.

`offset` is the number of position that `scroll_up` and `scroll_down`
shift the cursor.
"""
        self.offset = offset

        ListBox.__init__(self,
                         SimpleListWalker(contents))

    def scroll_up(self):
        focus_status, pos = self.get_focus()
        if pos is None:
            return

        new_pos = pos - self.offset
        if new_pos < 0:
            new_pos = 0
        self.set_focus(new_pos)

    def scroll_down(self):
        focus_status, pos = self.get_focus()
        if pos is None:
            return

        new_pos = pos + self.offset
        if new_pos >= len(self.body):
            new_pos = len(self.body) - 1
        self.set_focus(new_pos)

    def scroll_top(self):
        if len(self.body):
            self.set_focus(0)

    def scroll_bottom(self):
        last = len(self.body) - 1
        if last:
            self.set_focus(last)

class Banner(WidgetWrap):
    """Displays information about the program."""

    def __init__(self):
        self.text = []

        quit_key = 'q'
        self.BANNER = [
            "======================================================",
            " _____ _     ____     ____            _             _ ",
            "|  ___| |   / ___|   / ___|___  _ __ | |_ _ __ ___ | |",
            "| |_  | |   \___ \  | |   / _ \| '_ \| __| '__/ _ \| |",
            "|  _| | |___ ___) | | |__| (_) | | | | |_| | | (_) | |",
            "|_|   |_____|____/   \____\___/|_| |_|\__|_|  \___/|_|",
            "                                                      ",
            " ____                  _                              ",
            "|  _ \ __ _ _ __   ___| |                             ",
            "| |_) / _` | '_ \ / _ \ |                             ",
            "|  __/ (_| | | | |  __/ |                             ",
            "|_|   \__,_|_| |_|\___|_|                             ",
            "======================================================",
            "0.1",
            "",
            "Press '%s' to quit FLS Control Panel" % quit_key,
            "",
            "",
        ]
        self.__super.__init__(self._create_text())

    def _create_text(self):
        """Create the text to display in the welcome buffer."""
        self.text = []
        for line in self.BANNER:
            self._insert_line(line)

        return ScrollableListBox(self.text)

    def _insert_line(self, line):
        text = Text(line, align='center')
        self.text.append(text)

class ItemWidget (urwid.WidgetWrap):

    def __init__ (self, id, description, status):
        self.id = id
        self.desc = description,
        self.status = status
        self.content = '# %s: %s...%s' % (str(id), description[:20], status)
        self.item = [
            ('fixed', 10, urwid.Padding(urwid.AttrWrap(
                urwid.Text('# %s' % str(id)), 'body', 'focus'), left=2)),
            urwid.AttrWrap(urwid.Text('%s' % description), 'body', 'focus'),
            urwid.AttrWrap(urwid.Text('%s' % status), 'focus' if status != 'ok' else 'body', 'focus')
        ]
        w = urwid.Columns(self.item)
        self.__super.__init__(w)

    def selectable (self):
        return True

    def keypress(self, size, key):
        return key

class MailView(WidgetWrap):
    def __init__(self):
        self.__super.__init__(self._createMailList())

    def _createMailList(self):
        mailList = []

        cursor = db.cursor()
        # READ ONLY WITH SPECIFIC domain!
        query = 'SELECT mail_id, mail_addr, `status` FROM mail_users WHERE domain_id = %s'
        cursor.execute(query, (DOMAIN,))
        for (uid, mailAddr, status) in cursor:
            mailList.append(ItemWidget(uid, mailAddr, status))

        cursor.close()

        return urwid.ListBox(urwid.SimpleFocusListWalker(mailList))

class Mail:
    def __init__(self, mailId):
        self.id = mailId
        self.setDefault()

        if self.id is not None:
            self.loadData()

    def setDefault(self):
        self.mail_id = ''
        self.mail_acc = ''
        self.mail_pass = ''
        self.mail_forward = ''
        self.domain_id = ''
        self.mail_type = ''
        self.sub_id = ''
        self.status = ''
        self.mail_auto_respond = ''
        self.mail_auto_respond_text = ''
        self.quota = ''
        self.mail_addr = ''
        self.alternative_addr = ''

    def loadData(self):
        l = logging.getLogger(__name__)
        cursor = db.cursor()
        query = 'SELECT * FROM mail_users WHERE mail_id = %s LIMIT 1'
        try:
            cursor.execute(query, (self.id, ))
        except mysql.connector.Error as err:
            l.error("Something went wrong: {}".format(err))
        l.info('Mail-ID: ' + str(self.id))
        l.info(cursor)
        l.info('Number rows: ' + str(cursor.rowcount))

        for row in cursor:
            (
                self.mail_id,
                self.mail_acc,
                self.mail_pass,
                self.mail_forward,
                self.domain_id,
                self.mail_type,
                self.sub_id,
                self.status,
                self.mail_auto_respond,
                self.mail_auto_respond_text,
                self.quota,
                self.mail_addr,
                self.alternative_addr
            ) = row
            if self.alternative_addr is None:
                self.alternative_addr = ''

        cursor.close()

def refreshList(ui):
    ui._get_original_widget().set_body(MailView())

def deleteMail(elm, ui):
    l = logging.getLogger(__name__)
    l.info('Delete: ' + str(elm.id))
    ui.setAction('delete')
    ui.setMail(elm)
    # show confirm dialog
    ui.open_pop_up()

def deleteMailConfirmed(elm, ui):
    l = logging.getLogger(__name__)
    # we delete it and than we reload the listbox.. ?
    # remove mail...
    cursor = db.cursor()
    query = 'UPDATE mail_users SET `status` = %s WHERE mail_id = %s'
    cursor.execute(query, ('delete', elm.id,))
    db.commit()
    cursor.close()

    # inform about change!
    informDaemon()

    # show new list
    ui._get_original_widget().set_body(MailView())

def existMailAddr(mailAddr, mailId = None):
    result = False
    cursor = db.cursor()
    if mailId is None:
        query = 'SELECT mail_id FROM mail_users WHERE mail_addr LIKE %s LIMIT 1'
        cursor.execute(query, (mailAddr,))
    else:
        query = 'SELECT mail_id FROM mail_users WHERE mail_addr LIKE %s AND mail_id != %s LIMIT 1'
        cursor.execute(query, (mailAddr,mailId))
    result = (cursor.rowcount > 0)
    row = cursor.fetchone()
    cursor.close()

    return result

def editMail(elm, ui):
    l = logging.getLogger(__name__)
    l.info('Edit: ' + str(elm.id))
    ui.setAction('edit')
    ui.setMail(elm.id)
    ui.open_pop_up()

def saveEditMail(ui, elms):
    l = logging.getLogger(__name__)
    lab, addr, alternate, genPW, passwd, typNormal, typForward, forwards, cancel, save = elms
    mailId = ui.getMail()
    # exist mail addr?
    if len(addr.get_edit_text().strip()) < 1:
        l.error('Mail Address is invalid!')
    mailaddr = '%s@%s' % (addr.get_edit_text(), DOMAIN_NAME)
    if existMailAddr(mailaddr, mailId):
        l.error('Mail address already used!')
    mailType = 'normal_forward' if typForward.state else 'normal_mail'
    forwardList = forwards.get_edit_text().strip() if len(forwards.get_edit_text().strip()) > 0 else '_no_'

    password = None
    passwordRaw = None
    if genPW.get_state() or len(passwd.get_edit_text().strip()) > 0:
        passwordRaw = genPw() if genPW.get_state() else passwd.get_edit_text()
        password = hashPw(passwordRaw)
        password = '_no_' if typForward.state else password

    if password is None:
        query = """
        UPDATE `mail_users`
        SET
            `mail_acc` = %s,
            `mail_forward` = %s,
            `domain_id` = %s,
            `mail_type` = %s,
            `sub_id` = %s,
            `status` = %s,
            `mail_addr` = %s,
            `alternative_addr` = %s
        WHERE mail_id = %s"""
        cursor = db.cursor()
        cursor.execute(query, (
            addr.get_edit_text().strip(),
            forwardList,
            DOMAIN,
            mailType,
            DOMAIN_SUB,
            'change',
            mailaddr,
            alternate.get_edit_text().strip(),
            mailId
        ))
    else:
        query = """
        UPDATE `mail_users`
        SET
            `mail_acc` = %s,
            `mail_pass` = %s,
            `mail_forward` = %s,
            `domain_id` = %s,
            `mail_type` = %s,
            `sub_id` = %s,
            `status` = %s,
            `mail_addr` = %s,
            `alternative_addr` = %s
        WHERE mail_id = %s"""
        cursor = db.cursor()
        cursor.execute(query, (
            addr.get_edit_text().strip(),
            password,
            forwardList,
            DOMAIN,
            mailType,
            DOMAIN_SUB,
            'change',
            mailaddr,
            alternate.get_edit_text().strip(),
            mailId
        ))
    db.commit()
    cursor.close()

    # inform about change!
    informDaemon()

    if alternate.get_edit_text().strip() is not None and password != '_no_' and password != None:
        sendMail(mailaddr, alternate.get_edit_text().strip(), passwordRaw, True)

    ui._get_original_widget().set_body(MailView())

def sendMail(mailAddr, alternateAddr, password, update = False):
    msg = MIMEText("""
Guten Tag,

Ein Administrator des Website-Teams der Friedrich-List-Schule
Wiesbaden hat soeben eine E-Mail-Adresse fuer Sie %s.

Aus Sicherheitsgruenden erhalten Sie in diesem Schreiben Ihr Kennwort.
Sie koennen es jederzeit in der Webmail-Applikation online aendern.

E-Mail-Adresse und
Benutzername: %s
Kennwort    : %s

Die Webmail-Applikation erreichen Sie unter webmail.fls-wiesbaden.de

Beim erstmaligem Aufruf der Seite erscheint die Meldung "Es besteht ein Problem mit dem Sicherheitszertifikat der Website.
Es wird empfohlen, dass Sie diese Website schliessen." bzw. "Das Sicherheitszertifikat der Website ist nicht vertrauenswuerdig!".

Sie koennen das Laden dieser Webseite mit beruhigten Gewissen fortsetzen. Unsere Webseite ist mit einer Firewall, Spam-Filter und
aktuellem Virenschutz-Programm umfassend geschuetzt. Die Meldung erscheint, weil wir uns die recht hohen und jaehrlich anfallenden 
Kosten zum Erwerb eines Sicherheitszertifikats ersparen wollten. 


Ihr Website-Team
---
Friedrich-List-Schule Wiesbaden
Brunhildenstrasse 142
65189 Wiesbaden

Telefon : 0611-315100
Telefax : 0611-313989
E-Mail  : info@fls-wiesbaden.de
E-Mail Website-Team: website-team@fls-wiesbaden.de
Internet: www.fls-wiesbaden.de
    """ % ('geaendert' if update else 'eingerichtet', mailAddr, password))

    msg['Subject'] = '[FLS] Ihre neue E-Mail-Adresse'
    msg['From'] = 'website-team@fls-wiesbaden.de'
    msg['To'] = alternateAddr

    s = smtplib.SMTP('localhost')
    s.sendmail('website-team@fls-wiesbaden.de', [alternateAddr], msg.as_string())
    s.quit()

def newMail(ui):
    l = logging.getLogger(__name__)
    l.info('Starting new mail account thing..')
    ui.setAction('new')
    ui.setMail(None)
    ui.open_pop_up()

def genPw(size = 9):
    return ''.join([choice(string.ascii_letters + string.digits) for i in range(size)])

def hashPw(pw):
    cmd = shlex.split('php Encryption.php hash "%s"' % (pw,))
    # uhhh... we have to use SaltEncrypt...
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    p.wait()
    pwHash = ''
    if p.stdout is not None:
        pwHash = p.stdout.read()

    return pwHash

def createNewMail(ui, elms):
    l = logging.getLogger(__name__)
    lab, addr, alternate, genPW, passwd, typNormal, typForward, forwards, cancel, save = elms
    # exist mail addr?
    if len(addr.get_edit_text().strip()) < 1:
        l.error('Mail Address is invalid!')
    mailaddr = '%s@%s' % (addr.get_edit_text(), DOMAIN_NAME)
    if existMailAddr(mailaddr):
        l.error('Mail address already used!')
    mailType = 'normal_forward' if typForward.state else 'normal_mail'
    forwardList = forwards.get_edit_text().strip() if len(forwards.get_edit_text().strip()) > 0 else '_no_'
    passwordRaw = genPw() if genPW.get_state() else passwd.get_edit_text()
    password = hashPw(passwordRaw)
    password = '_no_' if typForward.state else password
    query = """
    INSERT INTO `mail_users`
    (`mail_acc`,`mail_pass`,`mail_forward`,`domain_id`,`mail_type`,`sub_id`,`status`,`mail_addr`,`alternative_addr`)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    cursor = db.cursor()
    cursor.execute(query, (
        addr.get_edit_text().strip(),
        password,
        forwardList,
        DOMAIN,
        mailType,
        DOMAIN_SUB,
        'toadd',
        mailaddr,
        alternate.get_edit_text().strip()
    ))
    db.commit()
    cursor.close()

    # inform about change!
    informDaemon()

    if alternate.get_edit_text().strip() is not None and password != '_no_':
        sendMail(mailaddr, alternate.get_edit_text().strip(), passwordRaw)

    ui._get_original_widget().set_body(MailView())

def informDaemon():
    l = logging.getLogger(__name__)
    host = '127.0.0.1'
    port = 9876
    answer = '999'
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((host, port))
        # Read one line
        msg = s.recv(4096)
        if not msg:
            return '999'
        msg = msg.decode('utf-8').replace('\n', '')
        l.info('Reply: ' + msg)
        msg = msg.split(' ')
        if msg[0] == '999':
            return msg[0]

        # send helo msg
        msg = ('helo %s\r\n' % ('1.0.3.0')).encode('utf-8')
        s.sendall(msg)

        # Read one line with helo answer
        msg = s.recv(4096)
        if not msg:
            return '999'
        msg = msg.decode('utf-8').replace('\n', '')
        l.info('Reply: ' + msg)
        msg = msg.split(' ')
        if msg[0] == '999':
            return msg[0]

        # send execute msg
        msg = 'execute query\r\n'.encode('utf-8')
        s.sendall(msg)

        # Read one line with helo answer
        msg = s.recv(4096)
        if not msg:
            return '999'
        msg = msg.decode('utf-8').replace('\n', '')
        l.info('Reply: ' + msg)
        msg = msg.split(' ')
        if msg[0] == '999':
            return msg[0]
        answer = msg[0]
        l.info('Daemon answer: %s' % (answer,))

        # send quit msg
        msg = 'bye\r\n'.encode('utf-8')
        s.sendall(msg)

        # Read one line with helo answer
        msg = s.recv(4096)
        if not msg:
            return '999'
        msg = msg.decode('utf-8').replace('\n', '')
        l.info('Reply: ' + msg)
        msg = msg.split(' ')
        if msg[0] == '999':
            return msg[0]

        s.shutdown(2)
    except socket.error as e:
        l.error('Could not inform daemon about changes!: ' + str(e))

    return answer

class ConfirmDialog(urwid.WidgetWrap):
    signals = ['yes', 'no']
    def __init__(self, action):
        self.action = action
        yes_button = urwid.Button("Ja")
        no_button = urwid.Button("Nein")
        urwid.connect_signal(yes_button, 'click',
            lambda button:self._emit("yes"))
        urwid.connect_signal(no_button, 'click',
            lambda button:self._emit("no"))
        pile = urwid.Pile([urwid.LineBox(Text(self.getMessage())),
            yes_button, no_button])
        fill = urwid.Filler(pile)
        self.__super.__init__(urwid.AttrWrap(fill, 'head'))

    def getMessage(self):
        if self.action == 'delete':
            return 'Wollen Sie die E-Mail-Adresse wirklich entfernen?'
        else:
            return 'Keine Aktion hinterlegt!'

class NewMailDialog(urwid.WidgetWrap):
    signals = ['save', 'cancel']
    def __init__(self, action, mail):
        self.action = action
        self.mail   = Mail(mail)
        l = logging.getLogger(__name__)
        l.info(vars(self.mail))
        save_button = urwid.Button("Speichern")
        cancel_button = urwid.Button("Abbrechen")
        radios = []
        elements = [
                urwid.LineBox(urwid.Text('Neuanlage' if mail is None else 'Bearbeiten')),
                urwid.Edit('Mail-Adresse o. Domain: ', self.mail.mail_acc),
                urwid.Edit('Alternative Mail: ', self.mail.alternative_addr),
                urwid.CheckBox('PW generieren', True if mail is None else False),
                urwid.Edit('Kennwort: ', mask='*'),
                urwid.RadioButton(radios, 'Normales Konto (beides)', True if mail is None or self.mail.mail_type == 'normal_mail' else False),
                urwid.RadioButton(radios, 'Weiterleitung', True if mail is not None and self.mail.mail_type == 'normal_forward' else False),
                urwid.Edit('Weiterleitung (je Zeile): ', self.mail.mail_forward, multiline=True),
                cancel_button,
                save_button
                ]
        layout = urwid.GridFlow(elements, 30, 1, 1, 'center')
        layout.set_focus(1)
        urwid.connect_signal(save_button, 'click',
            lambda button:self._emit("save", (elements,)))
        urwid.connect_signal(cancel_button, 'click',
            lambda button:self._emit("cancel"))
        pile = urwid.Pile([layout])
        fill = urwid.Filler(pile)
        self.__super.__init__(urwid.AttrWrap(fill, 'head'))

class FLSFrame(urwid.PopUpLauncher):
    def __init__(self, widget):
        self.__super.__init__(widget)
        self.mail = None
        self.action = 'delete'
        self.l = logging.getLogger(__name__)

    def create_pop_up(self):
        logging.getLogger(__name__).info('the action: ' + self.action)
        if self.action == 'delete':
            return self.createConfirmDialog()
        elif self.action in ('new', 'edit'):
            return self.createNewDialog()

    def createConfirmDialog(self):
        pop_up = ConfirmDialog(self.action)
        urwid.connect_signal(pop_up, 'yes',
            lambda button: self.yes())
        urwid.connect_signal(pop_up, 'no',
            lambda button: self.no())
        return pop_up

    def createNewDialog(self):
        pop_up = NewMailDialog(self.action, self.mail)
        urwid.connect_signal(pop_up, 'save',
            lambda *button: self.save(button))
        urwid.connect_signal(pop_up, 'cancel',
            lambda button: self.cancel())
        return pop_up

    def setMail(self, mail):
        self.mail = mail

    def getMail(self):
        return self.mail

    def setAction(self, action):
        self.action = action

    def yes(self):
        self.l.info('Ja gesagt!')
        self.close_pop_up()

        if self.action == 'delete':
            deleteMailConfirmed(self.mail, self)

    def no(self):
        self.l.info('Nein gesagt!')
        self.close_pop_up()

    def save(self, *args):
        self.close_pop_up()
        if self.action == 'new':
            createNewMail(self, args[0][1][0])
        elif self.action == 'edit':
            saveEditMail(self, args[0][1][0])

    def cancel(self):
        self.l.info('Abgebrochen')
        self.close_pop_up()

    def get_pop_up_parameters(self):
        if self.action in ('new', 'edit'):
            return {'left':10, 'top':10, 'overlay_width':50, 'overlay_height':30}
        else:
            return {'left':15, 'top':15, 'overlay_width':40, 'overlay_height':10}

def main():
    palette = [
            ('banner', 'black', 'light gray'),
            ('streak', 'black', 'dark red'),
            ('bg', 'yellow,bold', 'dark blue'),
            ('body','dark cyan', '', 'standout'),
            ('focus','dark red', '', 'standout'),
            ('head','dark blue,bold', 'black'),
    ]
    logging.basicConfig(filename='logging.log', level=logging.DEBUG)

    def inOutHandler(key):
        l = logging.getLogger(__name__)
        l.info('Key pressed: ' + str(key))
        if key in ('q', 'Q'):
            raise urwid.ExitMainLoop()
        elif key in ('e', 'E'):
            focus = mailView._w.get_focus()[0]
            editMail(focus, ui)
        elif key in ('d', 'D'):
            focus = mailView._w.get_focus()[0]
            deleteMail(focus, ui)
        elif key in ('f5', 'F5'):
            refreshList(ui)
        elif key in ('f8', 'F8'):
            newMail(ui)

    mailView = MailView()
    header = urwid.AttrMap(urwid.LineBox(urwid.Text('FLS Wiesbaden Control Panel - E-Mail')), 'head')
    body = urwid.AttrWrap(mailView, 'body')

    footerColumns = urwid.Columns(
            [
                ('pack', urwid.Text('q = Beenden')),
                ('pack', urwid.Text('e = Bearbeiten')),
                ('pack', urwid.Text('d = Entfernen')),
                ('pack', urwid.Text('F5 = Aktualisieren')),
                ('pack', urwid.Text('F8 = Neuanlage')),
                urwid.Text('Copyright (c) 2012 by Website-Team', align='right')
            ], 2
    )
    footer = urwid.AttrMap(footerColumns, 'bg')

    ui = FLSFrame(Frame(body, header=header, footer=footer))
    loop = urwid.MainLoop(ui, palette, unhandled_input=inOutHandler, pop_ups=True)
    loop.run()

if __name__ == '__main__':
    main()
    if db is not None:
        db.close()

