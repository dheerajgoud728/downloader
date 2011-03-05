#!/usr/bin/python
import os
import pycurl
import wx
from threading import Thread
import pickle
import time
from sqlite3 import dbapi2 as db

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
     
    except: # quick semi-nasty fallback for non-windows/win32com case
        homedir = os.path.expanduser("~")
    return homedir + "/.downloader/"

def CookieExport():
    dialog = wx.FileDialog ( None, style = wx.OPEN )
    dialog.SetDirectory(get_home_directory()+"..")
    file = ""
    if dialog.ShowModal() == wx.ID_OK:
        cookie_file = dialog.GetPath()
        output_file = get_home_directory()+'cookies.txt'
        filename = ""
        if output_file[1] == ":":
            filename = cookie_file.split('\\')[-1]
        else:
            filename = cookie_file.split('/')[-1]
        #print filename
        if filename == "cookies.txt":
            ouf = open(output_file, 'w')
            inf = open(cookie_file, 'r')
            ouf.write(inf.read())
            ouf.close()
            inf.close()
        elif filename == "Cookies":       
            conn = db.connect(cookie_file)
            cur = conn.cursor()
            cur.execute('SELECT host_key, path, secure, expires_utc, name, value FROM cookies')
            f = open(output_file, 'w')
            index = 0
            for row in cur.fetchall():
                f.write("%s\tTRUE\t%s\t%s\t%d\t%s\t%s\n" % (row[0], row[1],str(bool(row[2])).upper(), row[3], str(row[4]), str(row[5])))
                index += 1
            print "%d rows written" % index
            f.close()
            conn.close()
        elif filename == "cookies.sqlite":
            conn = db.connect(cookie_file)
            cur = conn.cursor()
            cur.execute('SELECT host, path, isSecure, expiry, name, value FROM moz_cookies')
            f = open(output_file, 'w')
            index = 0
            for row in cur.fetchall():
                f.write("%s\tTRUE\t%s\t%s\t%d\t%s\t%s\n" % (row[0], row[1],str(bool(row[2])).upper(), row[3], str(row[4]), str(row[5])))
                index += 1
            print "%d rows written" % index
            f.close()
            conn.close()
    dialog.Destroy()

def getFileName(url):
    name = url.split("/")[-1]
    return str(name)


class Storage:
    def __init__(self):
        #self.contents = ''
        self.line = 0
        self.size = 0
        self.type = ""
        self.filename = ""
        self.http = ""
        self.connection = ""
        self.location = ""
    def store(self, buf):
        #print buf[:len(buf) - 1]
        pos = buf.find("HTTP/")
        if pos != -1:
            #npos = buf.find('\n')
            self.http = buf[:len(buf) - 1]
        pos = buf.find("Content-Type: ")
        if pos != -1:
            epos = buf.find('\n', pos) - 1
            self.type = buf[pos+14:epos]
        pos = buf.find("Location: ")
        if pos != -1:
            epos = buf.find('\n', pos) - 1
            self.location = buf[pos+10:epos]
        pos = buf.find("Content-Length: ")
        if pos != -1:
            epos = buf.find('\n', pos) - 1
            self.size = int(buf[pos+16:epos])
        pos = buf.find("filename=")
        if pos != -1:
            epos = buf.find('\n', pos) - 1
            self.filename = buf[pos+9:epos]
            if self.filename[0] == "'" or self.filename[0] == '"':
                self.filename = self.filename[1:-1]
        self.line = self.line + 1
        #self.contents = "%s%i: %s" % (self.contents, self.line, buf)
    #def __str__(self):
    #    return self.contents

def getFileSize(url, proxy, port, creds):
    #print url
    #print proxy
    #print port
    #print creds
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
    c.setopt(pycurl.FOLLOWLOCATION, 1)
    c.setopt(pycurl.COOKIEFILE, get_home_directory() + "cookies.txt")
    c.setopt(pycurl.COOKIEJAR, get_home_directory() + "cookies.txt")
    c.setopt(c.WRITEFUNCTION, retrieved_body.store)
    c.perform()
    c.close()
    return retrieved_body
            
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
        self.to_download = end - startv + 1
        self.downloaded = 0
        self.gap = 0
        self.over = False
        self.line = 0
        self.c = pycurl.Curl()
        self.strt = 0
        self.dirty = False
        self.redirected = False
        Thread.__init__(self)
    def run(self):
        #print str(self.startv) + "-" + str(self.end)
        try:
            self.strt = os.path.getsize(self.filename)
        except:
            None
        if self.strt > 0:
            #print self.filename + ":" + str(self.strt)
            if self.strt > self.to_download:
                os.remove(self.filename)
                self.strt = 0
            else:
                self.startv = str(self.strt + int(self.startv))
                self.downloaded = self.strt
        if int(self.startv) >= int(self.end):
            self.downloaded = self.to_download
            self.over = True
            return
        #print str(self.to_download) + "/" + str(self.downloaded)
        #print str(self.startv) + "-" + str(self.end)
        header = self.get_header()
        num = header.http.find(' ')
        ret = header.http[num + 1:]
        num = ret.find(' ')
        num = int(ret[:num])
        if num < 200 or num > 399:
            print header.http + "\n" 
            return
        #c = pycurl.Curl()
        self.c.fp = open(self.filename, "ab")
        self.c.setopt(pycurl.URL, self.url)
        self.c.setopt(pycurl.WRITEDATA, self.c.fp)
        #self.c.setopt(pycurl.WRITEFUNCTION, self.write)
        self.c.setopt(pycurl.FOLLOWLOCATION, 1)
        self.c.setopt(pycurl.MAXREDIRS, 5)
        self.c.setopt(pycurl.CONNECTTIMEOUT, 30)
        self.c.setopt(pycurl.TIMEOUT, 300)
        self.c.setopt(pycurl.NOSIGNAL, 1)
        self.c.setopt(pycurl.PROXY, self.proxy)
        self.c.setopt(pycurl.PROXYPORT, self.port)
        self.c.setopt(pycurl.PROXYUSERPWD, self.creds)
        self.c.setopt(pycurl.RANGE, self.startv + "-" + self.end)
        #self.c.setopt(pycurl.RESUME_FROM, int(self.startv))
        self.c.setopt(pycurl.FOLLOWLOCATION, 1)
        self.c.setopt(pycurl.NOPROGRESS, 0)
        self.c.setopt(pycurl.PROGRESSFUNCTION, self.progress)
        self.c.setopt(pycurl.HEADERFUNCTION, self.header)
        self.c.setopt(pycurl.COOKIEFILE, get_home_directory() + "cookies.txt")
        self.c.setopt(pycurl.COOKIEJAR, get_home_directory() + "cookies.txt")
        self.line = 0
        self.c.perform()
        self.c.fp.close()
        self.c.close()
        if self.to_download == self.downloaded:
            self.over = True
        #else:
        #    print str(self.to_download) + "/" + str(self.downloaded)
        #    print str(self.startv) + "-" + str(self.end)
    def progress(self, download_t, download_d, upload_t, upload_d):
        #self.to_download = download_t 
        self.downloaded = download_d + self.strt
    def header(self, buf):
        if self.line == 0:
            num = buf.find(' ')
            ret = buf[num + 1:]
            num = ret.find(' ')
            num = int(ret[:num])
            self.line = self.line + 1
            if num < 200 or num > 399:
                self.dirty = True
                exit
            elif num >= 300 and num <= 399:
                self.redirected = True
        pos = buf.find("Content-Length: ")
        if pos != -1:
            epos = buf.find('\n', pos)
            size = int(buf[pos+16:epos])
            if size != self.to_download - self.strt and self.redirected != True:
                print "downloading size not equal to expected size : " + str(size) + "/" + str(self.to_download - self.strt) + "\n"
                self.dirty = True
                exit
        self.line = self.line + 1
    def get_header(self):
        retrieved_body = Storage()
        c1 = pycurl.Curl()
        c1.setopt(pycurl.URL, self.url)
        c1.setopt(pycurl.PROXY, self.proxy)
        c1.setopt(pycurl.PROXYPORT, self.port)
        c1.setopt(pycurl.PROXYUSERPWD, self.creds)
        c1.setopt(pycurl.RANGE, self.startv + "-" + self.end)
        c1.setopt(pycurl.HEADER, 1)
        c1.setopt(pycurl.NOPROGRESS, 1)
        c1.setopt(pycurl.NOBODY, 1)
        c1.setopt(pycurl.FOLLOWLOCATION, 1)
        c1.setopt(c1.WRITEFUNCTION, retrieved_body.store)
        c1.perform()
        c1.close()
        return retrieved_body
    def stop(self):
        self.thread.exit()
class downloader(Thread):
    def __init__(self, url, numthreads, filesize, split, filename, proxy, port, creds, timeout = 0, inserted = False, progress = 0.00):
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
        self.timeout = timeout
        self.inserted = inserted
        self.status = "Starting"
        self.progress = progress
        Thread.__init__(self)
    def run(self):
        time.sleep(self.timeout)
        startv = 0
        end = self.split - 1
        brk = False
        self.status = "Downloading"
        for i in range(0,self.numthreads):
            if end >= self.filesize - 1:
                end = self.filesize - 1
                brk = True
            #print str(startv) + "\t" + str(end) + "\t" + str(end - startv)
            d_worker = downloadworker(self.url, startv, end, self.filename + ".part" + str(i), self.proxy, self.port, self.creds, self)
            d_worker.setDaemon(True)
            d_worker.start()
            self.workerlist.append(d_worker)
            startv = end + 1
            end = end + self.split
            #d_worker.join()
            if brk:
                self.numthreads = i + 1
                break
        can_do = True
        for d_worker in self.workerlist:
            d_worker.join()
            if not d_worker.over:
                can_do = False
                try:
                    fsize = os.path.getsize(d_worker.filename)
                    if d_worker.dirty == True and fsize > d_worker.strt:
                        f = open(d_worker.filename, 'rb')
                        bites = f.read(d_worker.strt)
                        f.close()
                        f = open(d_worker.filename, 'wb')
                        f.write(bites)
                        f.close()
                except:
                    None
        if can_do:
            self.status = "Merging"
            f = open(self.filename, "wb")  
            for d_worker in self.workerlist:
                #print str(d_worker.startv) + "\t" + str(d_worker.end) + "\t" + str(d_worker.downloaded) + "\t" + str(d_worker.to_download)
                #print d_worker.filename + "\t" + str(os.path.getsize(d_worker.filename))
                _f = open(d_worker.filename, "rb")
                f.write(_f.read())
                _f.close()
            f.close()
            nfilesize = int(os.path.getsize(self.filename))
            time.sleep(2);
            if nfilesize == self.filesize:
                self.success = True
                for i in range(0, len(self.workerlist)):
                    os.remove(self.filename + ".part" + str(i))
                self.status = "Completed"
                print "download completed."
            else:
                self.status = "Error"
                print "output filesize is not equal to input filesize."
                print self.filename + ":" + str(nfilesize) + "/" + str(self.filesize)
        else:
            self.status = "Error"
            print "Download interrupted in the middle."
        #del self.workerlist
    def pause_download(self):
        #for d_worker in self.workerlist:
        #    d_worker.stop()
        #self.status = "Paused"
        #self.thread.exit()
        print "not yet implemented"

def get_progress(trd):
    downloaded = 0
    for d_worker in trd.workerlist:
        #print "downloaded:" + str(d_worker.downloaded)
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
    #print ret
    if len(trd.workerlist) == trd.numthreads:
        trd.progress = str(float(ret[1]*100/ret[0]))
    return ret

class ExamplePanel(wx.Panel):
    def __init__(self, parent, *args, **kwargs):
        wx.Panel.__init__(self, parent, *args, **kwargs)
        self.SetLabel('Downloader')
        self.SetSize((700,700))
        self.trds = []
        self.prevdir = "./"
        self.listLocker = True
        # A button
        self.button = wx.Button(self, label="Save Info", pos=(50, 180))
        self.Bind(wx.EVT_BUTTON, self.OnClick,self.button)
        
        self.cb = wx.CheckBox(self, -1, 'Allow automatic retry?', (300, 180))
        self.cb.SetValue(True)


        self.go = wx.Button(self, label="Go", pos=(380, 20))
        self.Bind(wx.EVT_BUTTON, self.OnGo, self.go)
        
        self.export = wx.Button(self, label="Export Cookies", pos=(480, 20))
        self.Bind(wx.EVT_BUTTON, self.OnCookieExport, self.export)


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
        
        self.passlbl = wx.StaticText(self, label="Password :", pos=(10,155))
        self.passfld = wx.TextCtrl(self, value=data[3], pos=(90,150), size=(140,-1), style=wx.TE_PASSWORD)
        
        lid = wx.NewId()
        
        self.selbut = wx.Button(self,label = "Resume All", pos = (590,180))
        self.Bind(wx.EVT_BUTTON, self.OnCommand, self.selbut)
       
        self.rembut = wx.Button(self, label = "Remove",pos = (480,180))
        self.Bind(wx.EVT_BUTTON, self.OnRemove, self.rembut)
        
        self.downlst = wx.ListCtrl(self, lid, pos =(30,220), size=(650,200), style=wx.LC_REPORT|wx.SUNKEN_BORDER)
        self.downlst.Show(True)
        self.downlst.InsertColumn(0,"Filename", width=150)
        self.downlst.InsertColumn(1,"Status", width=150)
        self.downlst.InsertColumn(2,"Progress", width=80)
        self.downlst.InsertColumn(3,"Speed", width=100)
        self.downlst.InsertColumn(4,"Time Remaining", width=120)
        self.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnSelect, self.downlst)
        self.write = wx.TextCtrl(self, pos = (30,440), size = (650,200), style=wx.TE_MULTILINE)
        self.export = wx.Button(self, label = "Export", pos = (30, 650))
        self.Bind(wx.EVT_BUTTON, self.OnExport, self.export)
        self.timer = wx.Timer(self, 1)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.timer)
        self.timer.Start(1000)

        self.prev_data = []
        try:
            with open(get_home_directory() + "AllDetails.dat","rb") as f: 
                self.prev_data = pickle.load(f)
        except:
            None
        it = 0
        for item in self.prev_data:
            #temp_arr = [lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.success, lst.status, lst.progress]
            #downloader(lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.proxy, lst.port, lst.creds, 2, inserted = lst.inserted)
            #print item
            _downloader = downloader(item[0], item[1], item[2], item[3], item[4], str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value), progress = item[7])
            _downloader.success = item[5]
            if item[6] == "Downloading":
                _downloader.status = "Paused"
            else:
                _downloader.status = item[6]
            self.trds.append(_downloader)
            indx = self.downlst.InsertStringItem(it, item[4])
            if item[6] == "Downloading":
                self.downlst.SetStringItem(indx, 1,"Paused")
            else:
                self.downlst.SetStringItem(indx, 1, item[6])
            self.downlst.SetStringItem(indx, 2, str(item[7])[:5] + "%")
            self.downlst.SetStringItem(indx, 3,"---")
            self.downlst.SetStringItem(indx, 4,"---")
            self.downlst.SetItemTextColour(it, wx.BLACK)
            _downloader.inserted = True
            it = it + 1
      
    def OnTimer(self, event):
        storage_arr = []
        it = 0
        all_arr = []
        #print len(self.trds)
        for lst in self.trds:
            temp_arr = [lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.success, lst.status, lst.progress]
            all_arr.append(temp_arr)
            #print temp_arr
            if lst.isAlive():
                res = get_progress(lst)
                percentage = str(lst.progress)[:5] + "%"
                speed = res[2]
                if int(speed) > 900:
                    speed = str(float(speed)/1024)[:6] + "mbps"
                else:
                    speed = str(speed)[:6] + "kbps"
                trm = str(int(res[3]/60)) + "m " + str(int(res[3] % 60)) + "s"
                if lst.inserted == False:
                    indx = self.downlst.InsertStringItem(it, lst.filename)
                    self.downlst.SetStringItem(indx, 1,lst.status)
                    self.downlst.SetStringItem(indx, 2,percentage)
                    self.downlst.SetStringItem(indx, 3,speed)
                    self.downlst.SetStringItem(indx, 4,trm)
                    self.downlst.SetItemTextColour(it, wx.BLUE)
                    lst.inserted = True
                else:
                    indx =  self.downlst.GetItem(it)
                    #self.downlst.SetStringItem(indx, 0,lst.filename)
                    self.downlst.SetStringItem(it, 1,lst.status)
                    self.downlst.SetStringItem(it, 2,percentage)
                    self.downlst.SetStringItem(it, 3,speed)
                    self.downlst.SetStringItem(it, 4,trm)
                    if lst.status == "Downloading":
                        self.downlst.SetItemTextColour(it, wx.BLUE)
                    elif lst.status == "Error":
                        self.downlst.SetItemTextColour(it, wx.RED)
                    #self.downlst.SetItemText(self.downlst.GetItem(it, 0), lst.filename)
                    #self.downlst.SetItemText(self.downlst.GetItem(it, 1), lst.url)
                    #self.downlst.SetItemText(self.downlst.GetItem(it, 2), percentage)
                    #self.downlst.SetItemText(self.downlst.GetItem(it, 3), speed)
                    #self.downlst.SetItemText(self.downlst.GetItem(it, 4), trm)
                data = [lst.url, lst.filename, lst.filesize, lst.split/(1024*1024), lst.numthreads]
                storage_arr.append(data)
            elif not lst.success:
                if lst.status == "Paused":
                    #col = wx.ColourRGB()
                    self.downlst.SetItemTextColour(it, wx.BLACK)
                else:
                    if self.cb.GetValue():
                        print "Trying to download " + lst.url + " again."
                        lst = downloader(lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.proxy, lst.port, lst.creds, 2, inserted = lst.inserted, progress = lst.progress)
                        lst.start()
                        self.trds[it] = lst
                        #self.downlst.SetItemTextColour(it, wx.BLUE)
                    data = [lst.url, lst.filename, lst.filesize, lst.split/(1024*1024), lst.numthreads]
                    storage_arr.append(data)
            elif lst.success:
                lst.status = "Completed"
                indx =  self.downlst.GetItem(it)
                self.downlst.SetStringItem(it, 1,"Completed")
                self.downlst.SetStringItem(it, 2,"100.00%")
                self.downlst.SetItemTextColour(it, wx.GREEN)
            it += 1
        #f = open(get_home_directory() + "dwDetails.dat","wb")
        #pickle.dump(storage_arr, f)
        #f.close()
        f = open(get_home_directory() + "AllDetails.dat","wb")
        pickle.dump(all_arr, f)
        f.close()

    def OnClick(self,event):
        try:
            with open(get_home_directory() + "settings.dat", "wb") as f:
                ndata = [self.proxyfld.Value,self.portfld.Value,self.userfld.Value,self.passfld.Value]
                pickle.dump(ndata, f)
        except:
            None
    def OnGo(self,event):
        try:       
            header = getFileSize(str(self.urlfld.Value), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
            #time.sleep(2)
            #if len(header.location) != 0:
                #print "in if"
                #self.urlfld.Value = str(header.location)
                #header = getFileSize(str(self.urlfld.Value), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
            filesize = header.size
            http = header.http
            type = header.type
            location = header.location
            print "file_size: " + str(filesize)
            print "file_type: " + str(type)
            print "filename: " + str(header.filename)
            print "http :" + str(http)
            print "location :" + str(location)
            filename = ""
            if filesize <= 0:
                wx.MessageBox("The server returned filesize as 0 bytes", "error")
                return
            if len(header.filename) != 0:
                filename = header.filename
            elif len(header.location) != 0:
                filename = getFileName(location)
            else:
                filename = getFileName(self.urlfld.Value)
            numthreads = int(filesize/(float(self.splitfld.Value)*1024*1024)) + 1
            dialog = wx.FileDialog ( None, style = wx.SAVE | wx.OVERWRITE_PROMPT )
            dialog.SetFilename(filename)
            dialog.SetDirectory(self.prevdir)
            if dialog.ShowModal() == wx.ID_OK:
                print 'Selected:', dialog.GetPath()
                self.prevdir = dialog.GetDirectory()
                _downloader = downloader(str(self.urlfld.Value), numthreads, filesize, float(self.splitfld.Value), str(dialog.GetPath()), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                _downloader.start()
                self.trds.append(_downloader)
            dialog.Destroy()
        except:
            wx.MessageBox("Please check all fields", "Error")
    def OnExport(self, event):
        urls = self.write.GetValue().split()
        got_folder = False
        for url in urls:
            try:       
                header = getFileSize(str(url), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                filesize = header.size
                http = header.http
                type = header.type
                location = header.location
                print "file_size: " + str(filesize)
                print "file_type: " + str(type)
                print "http :" + str(http)
                print "location :" + str(location)
                filename = ""
                if filesize <= 0:
                    wx.MessageBox("The server returned filesize as 0 bytes", "error")
                    return
                if len(location) != 0:
                    filename = getFileName(location)
                else:
                    filename = getFileName(url)
                numthreads = int(filesize/(float(self.splitfld.Value)*1024*1024)) + 1
                if got_folder:
                    if self.prevdir[1] == ":":
                        filepath = self.prevdir + "\\" + filename
                    else:
                        filepath = self.prevdir + "/" + filename
                    #print filepath
                    _downloader = downloader(str(url), numthreads, filesize, float(self.splitfld.Value), str(filepath), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                    _downloader.start()
                    self.trds.append(_downloader)
                else:
                    dialog = wx.FileDialog ( None, style = wx.SAVE | wx.OVERWRITE_PROMPT )
                    dialog.SetFilename(filename)
                    dialog.SetDirectory(self.prevdir)
                    if dialog.ShowModal() == wx.ID_OK:
                        print 'Selected:', dialog.GetPath()
                        self.prevdir = dialog.GetDirectory()
                        got_folder = True
                        _downloader = downloader(str(url), numthreads, filesize, float(self.splitfld.Value), str(dialog.GetPath()), str(self.proxyfld.Value), int(self.portfld.Value), str(self.userfld.Value+":"+self.passfld.Value))
                        _downloader.start()
                        self.trds.append(_downloader)
                    dialog.Destroy()
            except:
                print "Please check all fields"
    def OnSelect(self, event):
        None
        '''
        index = event.GetIndex()
        if self.trds[index].isAlive():
            self.selbut.SetLabel("Pause")
            self.selbut.Enable(True)
        elif self.trds[index].success == True or self.trds[index].status == "Completed":
            self.selbut.Enable(False)
        else:
            self.selbut.SetLabel("Resume")
            self.selbut.Enable(True)
            '''
    def OnCommand(self, event):
        it = 0
        for lst in self.trds:
            if not lst.isAlive() and not lst.success:
                print "Trying to download " + lst.url + " again."
                lst = downloader(lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.proxy, lst.port, lst.creds, 2, inserted = lst.inserted, progress = lst.progress)
                lst.start()
                self.trds[it] = lst
            it = it + 1
        '''
        index = self.downlst.GetFocusedItem()
        if index >=0:
            if self.trds[index].isAlive():
                self.selbut.SetLabel("Pause")
                self.selbut.Enable(True)
            elif self.trds[index].success == True or self.trds[index].status == "Completed":
                self.selbut.Enable(False)
            else:
                self.selbut.SetLabel("Resume")
                self.selbut.Enable(True)
        else:
            self.selbut.Enable(False)
        if index >= 0:
            if self.trds[index].isAlive():
                self.trds[index].pause_download()
                self.selbut.SetLabel("Resume")
                self.selbut.Enable(True)
            elif self.trds[index].success == True or self.trds[index].status == "Completed":
                self.selbut.Enable(False)
            else:
                lst = self.trds[index]
                lst = downloader(lst.url, lst.numthreads, lst.filesize, lst.split/(1024*1024), lst.filename, lst.proxy, lst.port, lst.creds, 2, inserted = lst.inserted, progress = lst.progress)
                lst.inserted = True
                lst.start()
                self.trds[index] = lst
                self.selbut.SetLabel("Pause")
                self.selbut.Enable(True)
        '''        
    def OnRemove(self, event):
        new_list = []
        self.timer.Stop()
        time.sleep(1)
        for item in self.trds:
            if item.success == False or item.status != "Completed":
                new_list.append(item)
        self.trds = new_list
        self.downlst.ClearAll()
        self.downlst.InsertColumn(0,"Filename", width=150)
        self.downlst.InsertColumn(1,"Status", width=150)
        self.downlst.InsertColumn(2,"Progress", width=80)
        self.downlst.InsertColumn(3,"Speed", width=100)
        self.downlst.InsertColumn(4,"Time Remaining", width=120)
        it = 0
        for item in self.trds:
            indx = self.downlst.InsertStringItem(it, item.filename)
            self.downlst.SetStringItem(indx, 1, item.status)
            self.downlst.SetStringItem(indx, 2, str(item.progress)[:5] + "%")
            self.downlst.SetStringItem(indx, 3,"---")
            self.downlst.SetStringItem(indx, 4,"---")
            if item.status == "Downloading":
                self.downlst.SetItemTextColour(it, wx.BLUE)
            elif item.status == "Paused":
                self.downlst.SetItemTextColour(it, wx.BLACK)
            elif item.status == "Completed":
                self.downlst.SetItemTextColour(it, wx.GREEN)
            else:
                self.downlst.SetItemTextColour(it, wx.RED)
            it = it + 1
        self.timer.Start(1000)
    def OnCookieExport(self, event):
        CookieExport()
        
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
except:
    None
app = wx.App()
frame = DemoFrame(None, title="Downloader")
frame.Show()
app.MainLoop()
