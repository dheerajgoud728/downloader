#!/usr/bin/python
import os
import sys
import pycurl
import wx
from threading import Thread
import pickle
import time

def getFileName(url):
    directory=os.curdir

    name="%s%s%s" % (
        directory,
        os.sep,
        url.split("/")[-1]
    )
    return name[2:]


class Storage:
    def __init__(self):
        self.contents = ''
        self.line = 0
        self.size = 0
    def store(self, buf):
        pos = buf.find("Content-Length: ")
        if pos != -1:
            epos = buf.find('\n', pos)
            self.size = int(buf[pos+16:epos])
        self.line = self.line + 1
        self.contents = "%s%i: %s" % (self.contents, self.line, buf)
    def __str__(self):
        return self.contents

def getFileSize(url, proxy, port, creds):
    retrieved_body = Storage()
    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(pycurl.PROXY, proxy)
    c.setopt(pycurl.PROXYPORT, port)
    c.setopt(pycurl.PROXYTYPE, pycurl.PROXYTYPE_HTTP) 
    c.setopt(pycurl.PROXYUSERPWD, creds)
    c.setopt(pycurl.HEADER, 1)
    c.setopt(pycurl.NOPROGRESS, 1)
    c.setopt(pycurl.NOBODY, 1)
    c.setopt(c.WRITEFUNCTION, retrieved_body.store)
    c.perform()
    c.close()
    return retrieved_body.size
            
class downloadworker(Thread):
    def __init__(self, url, startv, end, filename, proxy, port, creds, prnt):
        self.url = str(url)
        self.startv = str(startv)
        self.end = str(end)
        self.filename = str(filename)
        self.proxy = str(proxy)
        self.port = int(port)
        self.creds = str(creds)
        self.prnt = prnt
        self.to_download = end - startv
        self.downloaded = 0
        Thread.__init__(self)
        #print "=="+url+"=="
    def run(self):
        c = pycurl.Curl()
        c.fp = open(self.filename, "wb")
        c.setopt(pycurl.URL, self.url)
        c.setopt(pycurl.WRITEDATA, c.fp)
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.setopt(pycurl.MAXREDIRS, 5)
        c.setopt(pycurl.CONNECTTIMEOUT, 30)
        c.setopt(pycurl.TIMEOUT, 300)
        c.setopt(pycurl.NOSIGNAL, 1)
        c.setopt(pycurl.PROXY, self.proxy)
        c.setopt(pycurl.PROXYPORT, self.port)
        c.setopt(pycurl.PROXYUSERPWD, self.creds)
        c.setopt(pycurl.RANGE, self.startv + "-" + self.end)
        c.setopt(pycurl.NOPROGRESS, 0)
        c.setopt(pycurl.PROGRESSFUNCTION, self.progress)
        c.perform()
        c.fp.close()
        c.close()
    def progress(self, download_t, download_d, upload_t, upload_d):
        self.to_download = download_t
        self.downloaded = download_d

class downloader(Thread):
    def __init__(self, frame, url, numthreads, filesize, split, filename, proxy, port, creds):
        self.frame = frame
        self.url = str(url)
        self.numthreads = int(numthreads)
        self.filesize = int(filesize)
        self.split = int(float(split) * 1024 * 1024)
        self.filename = str(filename)
        self.proxy = str(proxy)
        self.port = int(port)
        self.creds = str(creds)
        self.workerlist = []
        self.last_downloaded = 0
        self.stime = time.time()
        Thread.__init__(self)
    def run(self):
        startv = 0
        end = 0
        for i in range(0,self.numthreads):
            end = end + self.split
            brk = False
            if end >= self.filesize:
                end = self.filesize
                brk = True
            d_worker = downloadworker(self.url, startv, end, self.filename + ".part" + str(i), self.proxy, self.port, self.creds, self)
            d_worker.start()
            self.workerlist.append(d_worker)
            startv = end + 1
            if brk:
                break
        for d_worker in self.workerlist:
            d_worker.join()
        f = open(self.filename, "wb")  
        for i in range(0, len(self.workerlist)):
            res = self.get_progress()
            self.frame.count = int(res[1] * 50 / res[0])
            lbl = "Speed : " + str(res[2]) + "kbps Time Left: " + str(int(res[3]/60)) + "m " + str(int(res[3] % 60)) + "s"
            self.frame.text.SetLabel(lbl)
            _f = open(self.filename + ".part" + str(i), "rb")
            f.write(_f.read())
            _f.close()
        f.close()
        nfilesize = int(os.path.getsize(self.filename))
        if nfilesize == self.filesize:
            for i in range(0, len(self.workerlist)):
                os.remove(self.filename + ".part" + str(i))
        else:
            print "output filesize is not equal to input filesize."
        del self.workerlist
    
    def get_progress(self):
        downloaded = 0
        for d_worker in self.workerlist:
            downloaded = downloaded + d_worker.downloaded
        td = time.time() - self.stime
        self.stime = time.time()
        speed = (downloaded - self.last_downloaded)/(1024 * td)
        self.last_downloaded = downloaded
        rtime = (self.filesize - downloaded)*1024/speed
        ret = [self.filesize, downloaded, speed, rtime]
        return ret

class ExamplePanel(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        wx.Panel.__init__(self, parent, *args, **kwargs)
        self.SetLabel('Downloader')
        self.SetSize((500,500))
        # A button
        self.button =wx.Button(self, label="Save Info", pos=(50, 180))
        self.Bind(wx.EVT_BUTTON, self.OnClick,self.button)

        self.go =wx.Button(self, label="Go", pos=(380, 20))
        self.Bind(wx.EVT_BUTTON, self.OnGo,self.go)

        # the edit control - one line version.
        self.urllbl = wx.StaticText(self, label="Url :", pos=(10,25))
        self.urlfld = wx.TextCtrl(self, value="", pos=(90, 20), size=(280,-1))
        
        self.splitlbl = wx.StaticText(self, label="Fragment Size:", pos=(10,55))
        self.splitfld = wx.TextCtrl(self, value="50", pos=(110,50), size=(50,-1))
        
        self.proxylbl = wx.StaticText(self, label="Proxy :", pos=(10,95))
        self.proxyfld = wx.TextCtrl(self, value=data[0], pos=(90, 90), size=(140,-1))
        
        self.portlbl = wx.StaticText(self, label=":", pos=(230,95))
        self.portfld = wx.TextCtrl(self, value=data[1], pos=(235,90), size=(50,-1))
        
        self.userlbl = wx.StaticText(self, label="Username :", pos=(10,125))
        self.userfld = wx.TextCtrl(self, value=data[2], pos=(90,120), size=(140,-1))
        
        self.passlbl = wx.StaticText(self, label="Passsword :", pos=(10,155))
        self.passfld = wx.TextCtrl(self, value=data[3], pos=(90,150), size=(140,-1), style=wx.TE_PASSWORD)
        
        lid = wx.NewId()
        self.downlst = wx.ListCtrl(self, lid, pos =(30,220), size=(450,200), style=wx.LC_REPORT|wx.SUNKEN_BORDER)
        self.downlst.Show(True)
        self.downlst.InsertColumn(0,"Filename")
        self.downlst.InsertColumn(1,"URL")
        self.downlst.InsertColumn(2,"Progress")
        self.downlst.InsertColumn(3,"Speed")
    def OnClick(self,event):
        try:
            with open("settings.dat", "wb") as f:
                ndata = [self.proxyfld.Value,self.portfld.Value,self.userfld.Value,self.passfld.Value]
                pickle.dump(ndata, f)
        except IOError as (errno, strerror):
            None
    def OnGo(self,event):
        #try:       
            filesize = getFileSize(str(self.urlfld.Value), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
            filename = getFileName(str(self.urlfld.Value))
            print ("fname="+filename)
            print filesize
            numthreads = int(filesize/(float(self.splitfld.Value)*1024*1024)) + 1
            print numthreads
            dialog = wx.FileDialog ( None, style = wx.SAVE | wx.OVERWRITE_PROMPT )
            dialog.SetFilename(filename)
            if dialog.ShowModal() == wx.ID_OK:
                print 'Selected:', dialog.GetPath()
                _downloader = runFrame(str(self.urlfld.Value), numthreads, filesize, float(self.splitfld.Value), str(dialog.GetPath()), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                _downloader.start()
            dialog.Destroy()
        #except ValueError:
        #    wx.MessageBox("Please check all fields", "Error")
        
class DemoFrame(wx.Frame):
    """Main Frame holding the Panel."""
    def __init__(self, *args, **kwargs):
        """Create the DemoFrame."""
        wx.Frame.__init__(self, *args, **kwargs)

        # Build the menu bar
        MenuBar = wx.MenuBar()

        FileMenu = wx.Menu()
        
        item = FileMenu.Append(wx.ID_EXIT, text="&Quit")
        self.Bind(wx.EVT_MENU, self.OnQuit, item)

        MenuBar.Append(FileMenu, "&File")
        self.SetMenuBar(MenuBar)

        # Add the Widget Panel
        self.Panel = ExamplePanel(self)

        self.Fit()

    def OnQuit(self, event=None):
        """Exit application."""
        self.Close()

class runFrame(Thread):
    def __init__(self, url, numthreads, filesize, split, filename, proxy, port, creds):
        self.url = str(url)
        self.numthreads = int(numthreads)
        self.filesize = int(filesize)
        self.split = int(float(split) * 1024 * 1024)
        self.filename = str(filename)
        self.proxy = str(proxy)
        self.port = int(port)
        self.creds = str(creds)
        self.app = wx.App()
        self.wid = wx.NewId()
        self.frame = SmallFrame(self, None, self.wid, title="Downloader")
        self.downloader_ = downloader(self.frame, str(self.url), self.numthreads, self.filesize, float(self.split), self.filename, self.proxy, self.port, self.creds)
        Thread.__init__(self)
    def run(self):
        self.downloader_.start()
        self.frame.Show()
        self.app.MainLoop()
        
class SmallFrame(wx.Frame):
    def __init__(self, prnt, parent, id, title):
        self.prnt = prnt
        wx.Frame.__init__(self, parent, id, title)

        self.timer = wx.Timer(self, 1)
        self.count = 0
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        panel = wx.Panel(self, -1)
        vbox = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        hbox3 = wx.BoxSizer(wx.HORIZONTAL)

        self.gauge = wx.Gauge(panel, -1, 50, size=(250, 25))
        self.btn1 = wx.Button(panel, wx.ID_OK)
        self.btn2 = wx.Button(panel, wx.ID_STOP)
        self.text = wx.StaticText(panel, -1, 'Task to be done')

        self.Bind(wx.EVT_BUTTON, self.OnOk, self.btn1)
        self.Bind(wx.EVT_BUTTON, self.OnStop, self.btn2)

        hbox1.Add(self.gauge, 1, wx.ALIGN_CENTRE)
        hbox2.Add(self.btn1, 1, wx.RIGHT, 10)
        hbox2.Add(self.btn2, 1)
        hbox3.Add(self.text, 1)
        vbox.Add((0, 50), 0)
        vbox.Add(hbox1, 0, wx.ALIGN_CENTRE)
        vbox.Add((0, 30), 0)
        vbox.Add(hbox2, 1, wx.ALIGN_CENTRE)
        vbox.Add(hbox3, 1, wx.ALIGN_CENTRE)
        panel.SetSizer(vbox)
        self.Centre()
        self.timer.Start(100)
    def OnOk(self, event):
        if self.count >= 50:
            return
        self.timer.Start(100)
        self.text.SetLabel('Task in Progress')

    def OnStop(self, event):
        if self.count == 0 or self.count >= 50 or not self.timer.IsRunning():
            return
        self.timer.Stop()
        self.text.SetLabel('Task Interrupted')
        wx.Bell()

    def OnTimer(self, event):
        #self.count = self.count +1
        #ret = self.prnt.downloader_.get_progress()
        #self.count = int(ret[1]*50/ret[0])
        #self.gauge.SetValue(self.count)
        #tyme = str(int(ret[3]/60)) + "m " + str(int(ret[3] % 60)) + "s"
        #self.text.SetLabel("Speed: " + str(ret[2]) + " kbps" + tyme)
        if self.count == 50:
            self.timer.Stop()
            self.text.SetLabel('Task Completed')

data = ["202.141.80.20", "3128", "username", "password"]
try:
    with open("settings.dat","rb") as f: 
        data = pickle.load(f)
except IOError as (errno, strerror):
    None
app = wx.App()
frame = DemoFrame(None, title="Downloader")
frame.Show()
app.MainLoop()
'''
url = raw_input("Enter url:")
filesize = getFileSize(url)
filename = getFileName(url)
print ("fname="+filename)
print filesize
numthreads = int(filesize/50000000)
'''