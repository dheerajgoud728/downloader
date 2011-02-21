#!/usr/bin/python
import os
import sys
import pycurl
import wx
from threading import Thread
import pickle
import time


def get_home_directory():
    homedir = os.path.expanduser('~')
    
    # ...works on at least windows and linux. 
    # In windows it points to the user's folder 
    #  (the one directly under Documents and Settings, not My Documents)
    
    
    # In windows, you can choose to care about local versus roaming profiles.
    # You can fetch the current user's through PyWin32.
    #
    # For example, to ask for the roaming 'Application Data' directory:
    #  (CSIDL_APPDATA asks for the roaming, CSIDL_LOCAL_APPDATA for the local one)
    #  (See microsoft references for further CSIDL constants)
    try:
        from win32com.shell import shellcon, shell            
        homedir = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
     
    except ImportError: # quick semi-nasty fallback for non-windows/win32com case
        homedir = os.path.expanduser("~")
    return homedir + "/.downloader/"

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
        self.gap = 0
        Thread.__init__(self)
    def run(self):
        c = pycurl.Curl()
        c.fp = open(self.filename, "ab")
        strt = os.path.getsize(self.filename)
        if strt > 0:
            self.gap = strt
            self.startv = str(strt + int(self.startv))
            self.downloaded = strt
        if int(self.startv) >= int(self.end):
            c.fp.close()
            c.close()
            return
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
        strt = os.path.getsize(self.filename)
        if strt != self.to_download:
            self.run()
    def progress(self, download_t, download_d, upload_t, upload_d):
        self.to_download = download_t 
        self.downloaded = download_d + self.gap  

class downloader(Thread):
    def __init__(self, url, numthreads, filesize, split, filename, proxy, port, creds):
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
        self.success = False
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
            time.sleep(1)
        f = open(self.filename, "wb")  
        for i in range(0, len(self.workerlist)):
            _f = open(self.filename + ".part" + str(i), "rb")
            f.write(_f.read())
            _f.close()
        f.close()
        nfilesize = int(os.path.getsize(self.filename))
        if nfilesize == self.filesize:
            for i in range(0, len(self.workerlist)):
                os.remove(self.filename + ".part" + str(i))
            print "download completed."
            self.success = True
        else:
            print "output filesize is not equal to input filesize."
        #del self.workerlist

def get_progress(trd):
    downloaded = 0
    for d_worker in trd.workerlist:
        downloaded = downloaded + d_worker.downloaded
    td = time.time() - trd.stime
    trd.stime = time.time()
    speed = float(downloaded - trd.last_downloaded)/(1024 * td)
    trd.last_downloaded = downloaded
    if speed != 0:
        rtime = int((trd.filesize - downloaded)/(speed*1024))
    else:
        rtime = 0
    ret = [trd.filesize, downloaded, speed, rtime]
    return ret

class ExamplePanel(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        wx.Panel.__init__(self, parent, *args, **kwargs)
        self.SetLabel('Downloader')
        self.SetSize((700,500))
        self.trds = []
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
        self.downlst = wx.ListCtrl(self, lid, pos =(30,220), size=(650,200), style=wx.LC_REPORT|wx.SUNKEN_BORDER)
        self.downlst.Show(True)
        self.downlst.InsertColumn(0,"Filename", width=150)
        self.downlst.InsertColumn(1,"URL", width=150)
        self.downlst.InsertColumn(2,"Progress", width=60)
        self.downlst.InsertColumn(3,"Speed", width=60)
        self.downlst.InsertColumn(4,"Time Remaining", width=120)

        self.timer = wx.Timer(self, 1)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(1000)

        self.prev_data = []
        try:
            with open(get_home_directory() + "dwDetails.dat","rb") as f: 
                self.prev_data = pickle.load(f)
        except IOError as (errno, strerror):
            None
        
        for item in self.prev_data:
            if wx.MessageBox("Do you want to continue this download?\n" + str(item[0]), "Interrupted Download", wx.YES_NO) == wx.YES:
                _downloader = downloader(item[0], int(item[4]), int(item[2]), float(item[3]), str(item[1]), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                _downloader.start()
                self.trds.append(_downloader)
      
    def OnTimer(self, event):
        storage_arr = []
        self.downlst.ClearAll()
        self.downlst.InsertColumn(0,"Filename", width=150)
        self.downlst.InsertColumn(1,"URL", width=150)
        self.downlst.InsertColumn(2,"Progress", width=80)
        self.downlst.InsertColumn(3,"Speed", width=100)
        self.downlst.InsertColumn(4,"Time Remaining", width=120)
        it = 0
        for lst in self.trds:
            if lst.isAlive():
                res = get_progress(lst)
                percentage = str(float(res[1]*100/res[0]))
                percentage = str(percentage[:6]) + "%"
                speed = res[2]
                if int(speed) > 900:
                    speed = str(float(speed)/1024)[:6] + "mbps"
                else:
                    speed = str(speed)[:6] + "kbps"
                trm = str(int(res[3]/60)) + "m " + str(int(res[3] % 60)) + "s"
                indx = self.downlst.InsertStringItem(it, lst.filename)
                self.downlst.SetStringItem(indx, 1,lst.url)
                self.downlst.SetStringItem(indx, 2,percentage)
                self.downlst.SetStringItem(indx, 3,speed)
                self.downlst.SetStringItem(indx, 4,trm)
                data = [lst.url, lst.filename, lst.filesize, lst.split/(1024*1024), lst.numthreads]
                storage_arr.append(data)
            elif not lst.success:
                #lst = downloader(lst.url, lst.numthreads, lst.filesize, lst.split, lst.fileName, lst.port, lst.creds)
                #lst.start()
                #self.trds[it] = lst
                data = [lst.url, lst.filename, lst.filesize, lst.split/(1024*1024), lst.numthreads]
                storage_arr.append(data)
            it += 1
        f = open(get_home_directory() + "dwDetails.dat","wb")
        pickle.dump(storage_arr, f)
        f.close()

    def OnClick(self,event):
        try:
            with open(get_home_directory() + "settings.dat", "wb") as f:
                ndata = [self.proxyfld.Value,self.portfld.Value,self.userfld.Value,self.passfld.Value]
                pickle.dump(ndata, f)
        except IOError as (errno, strerror):
            None
    def OnGo(self,event):
        try:       
            filesize = getFileSize(str(self.urlfld.Value), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
            filename = getFileName(str(self.urlfld.Value))
            numthreads = int(filesize/(float(self.splitfld.Value)*1024*1024)) + 1
            dialog = wx.FileDialog ( None, style = wx.SAVE | wx.OVERWRITE_PROMPT )
            dialog.SetFilename(filename)
            if dialog.ShowModal() == wx.ID_OK:
                print 'Selected:', dialog.GetPath()
                _downloader = downloader(str(self.urlfld.Value), numthreads, filesize, float(self.splitfld.Value), str(dialog.GetPath()), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                _downloader.start()
                self.trds.append(_downloader)
            dialog.Destroy()
        except ValueError:
            wx.MessageBox("Please check all fields", "Error")
        
class DemoFrame(wx.Frame):
    """Main Frame holding the Panel."""
    def __init__(self, *args, **kwargs):
        """Create the DemoFrame."""
        wx.Frame.__init__(self, *args, **kwargs)
        
        favicon = wx.Icon('downloader.ico', wx.BITMAP_TYPE_ICO)
        self.SetIcon(favicon)
        
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
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def OnQuit(self, event=None):
        """Exit application."""
        os._exit(1)
        
    def OnClose(self, event):
        """Exit application."""
        os._exit(1)

d = os.path.dirname(get_home_directory())
if not os.path.exists(d):
    os.makedirs(d)
data = ["202.141.80.20", "3128", "username", "password"]
try:
    with open(get_home_directory() + "settings.dat","rb") as f: 
        data = pickle.load(f)
except IOError as (errno, strerror):
    None
app = wx.App()
frame = DemoFrame(None, title="Downloader")
frame.Show()
app.MainLoop()
