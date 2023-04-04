import sys
if "--debugcrash" in sys.argv:
    import faulthandler
    faulthandler.enable()

try:
    _globals = globals
    import sys, os, win32mica, glob, subprocess, socket, hashlib, time
    from threading import Thread
    from urllib.request import urlopen
    from PySide6.QtGui import *
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
    import wingetHelpers, scoopHelpers
    from mainWindow import *
    from tools import *
    from tools import _
    from api_backend import runBackendApi

    import globals
    from external.blurwindow import GlobalBlur, ExtendFrameIntoClientArea


    class MainApplication(QApplication):
        kill = Signal()
        callInMain = Signal(object)
        setLoadBarValue = Signal(str)
        startAnim = Signal(QVariantAnimation)
        changeBarOrientation = Signal()
        showProgram = Signal(str)
        updatesMenu: QMenu = None
        installedMenu: QMenu = None
        running = True
        
        def __init__(self):
            try:
                super().__init__(sys.argv + ["-platform", f"windows:darkmode=0"])
                self.isDaemon: bool = "--daemon" in sys.argv
                self.popup = DraggableWindow()
                self.popup.setFixedSize(QSize(600, 400))
                self.popup.setWindowFlag(Qt.FramelessWindowHint)
                self.popup.setLayout(QVBoxLayout())
                self.popup.layout().addStretch()
                titlewidget = QHBoxLayout()
                titlewidget.addStretch()
                icon = QLabel()
                icon.setPixmap(QPixmap(getMedia("icon", autoIconMode = False)).scaledToWidth(128, Qt.TransformationMode.SmoothTransformation))
                text = QLabel("WingetUI")
                text.setStyleSheet(f"font-family: \"{globals.dispfont}\";font-weight: bold; color: {'white' if isDark() else 'black'};font-size: 50pt;")
                titlewidget.addWidget(icon)
                titlewidget.addWidget(text)
                titlewidget.addStretch()
                self.popup.layout().addLayout(titlewidget)
                self.popup.layout().addStretch()
                self.loadingText = QLabel(_("Loading WingetUI..."))
                self.loadingText.setStyleSheet(f"font-family: \"{globals.textfont}\"; color: {'white' if isDark() else 'black'};font-size: 12px;")
                self.popup.layout().addWidget(self.loadingText)
                ApplyMenuBlur(self.popup.winId().__int__(), self.popup)
                
                skipButton = QPushButton(_("Stuck here? Skip initialization"), self.popup)
                skipButton.setFlat(True)
                skipButton.move(390, 350)
                skipButton.setStyleSheet(f"color: {'white' if isDark() else 'black'}; border-radius: 4px; background-color: rgba({'255, 255, 255, 7%' if isDark() else '0, 0, 0, 7%'}); border: 1px solid rgba({'255, 255, 255, 10%' if isDark() else '0, 0, 0, 10%'})")
                skipButton.resize(200, 30)
                skipButton.hide()
                
                def forceContinue():
                    self.loadStatus = 1000 # Override loading status
                
                skipButton.clicked.connect(forceContinue)
                Thread(target=lambda: (time.sleep(15), self.callInMain.emit(skipButton.show))).start()
                
                
                self.loadingProgressBar = QProgressBar(self.popup)
                self.loadingProgressBar.setStyleSheet(f"""QProgressBar {{border-radius: 2px;height: 4px;border: 0px;background-color: transparent;}}QProgressBar::chunk {{background-color: rgb({colors[2 if isDark() else 3]});border-radius: 2px;}}""")
                self.loadingProgressBar.setRange(0, 1000)
                self.loadingProgressBar.setValue(0)
                self.loadingProgressBar.setGeometry(QRect(0, 396, 600, 4))
                self.loadingProgressBar.setFixedHeight(4)
                self.loadingProgressBar.setTextVisible(False)
                self.setLoadBarValue.connect(self.loadingProgressBar.setValue)
                self.startAnim.connect(lambda anim: anim.start())
                self.changeBarOrientation.connect(lambda: self.loadingProgressBar.setInvertedAppearance(not(self.loadingProgressBar.invertedAppearance())))
            
                self.leftSlow = QVariantAnimation()
                self.leftSlow.setStartValue(0)
                self.leftSlow.setEndValue(1000)
                self.leftSlow.setDuration(700)
                self.leftSlow.valueChanged.connect(lambda v: self.loadingProgressBar.setValue(v))
                self.leftSlow.finished.connect(lambda: (self.rightSlow.start(), self.changeBarOrientation.emit()))
                
                self.rightSlow = QVariantAnimation()
                self.rightSlow.setStartValue(1000)
                self.rightSlow.setEndValue(0)
                self.rightSlow.setDuration(700)
                self.rightSlow.valueChanged.connect(lambda v: self.loadingProgressBar.setValue(v))
                self.rightSlow.finished.connect(lambda: (self.leftFast.start(), self.changeBarOrientation.emit()))
                
                self.leftFast = QVariantAnimation()
                self.leftFast.setStartValue(0)
                self.leftFast.setEndValue(1000)
                self.leftFast.setDuration(300)
                self.leftFast.valueChanged.connect(lambda v: self.loadingProgressBar.setValue(v))
                self.leftFast.finished.connect(lambda: (self.rightFast.start(), self.changeBarOrientation.emit()))

                self.rightFast = QVariantAnimation()
                self.rightFast.setStartValue(1000)
                self.rightFast.setEndValue(0)
                self.rightFast.setDuration(300)
                self.rightFast.valueChanged.connect(lambda v: self.loadingProgressBar.setValue(v))
                self.rightFast.finished.connect(lambda: (self.leftSlow.start(), self.changeBarOrientation.emit()))
                
                if not self.isDaemon:
                    self.leftSlow.start()
                    self.popup.show()

                if not getSettings("AutoDisabledScoopCacheRemoval"):
                    getSettings("EnableScoopCleanup", False)
                    getSettings("AutoDisabledScoopCacheRemoval", True)
                    
                print("🔵 Starting main application...")
                os.chdir(os.path.expanduser("~"))
                self.kill.connect(lambda: (self.popup.hide(), sys.exit(0)))
                self.callInMain.connect(lambda f: f())
                if getSettings("AskedAbout3PackageManagers") == False or "--welcomewizard" in sys.argv:
                    self.askAboutPackageManagers(onclose=lambda: Thread(target=self.loadStuffThread, daemon=True).start())
                else:
                    Thread(target=self.loadStuffThread, daemon=True).start()
                    self.loadingText.setText(_("Checking for other running instances..."))
            except Exception as e:
                raise e

        def askAboutPackageManagers(self, onclose: object):
            self.w = NotClosableWidget()
            self.w.setObjectName("micawin")
            self.w.setWindowFlag(Qt.WindowType.Window)
            self.w.setWindowTitle(_("\x20"))
            pixmap = QPixmap(4, 4)
            pixmap.fill(Qt.GlobalColor.transparent)
            self.w.setWindowIcon(pixmap)
            self.w.setAutoFillBackground(True)
            self.w.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
            self.w.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
            self.w.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            self.w.setWindowModality(Qt.WindowModality.WindowModal)
            
            self.w.setMinimumWidth(750)
            self.w.setContentsMargins(20, 0, 20, 10)
            mainLayout = QVBoxLayout()
            label = (QLabel("<p style='font-size: 25pt;font-weight: bold;'>"+_("Welcome to WingetUI")+"</p><p style='font-size: 17pt;font-weight: bold;'>"+_("You may now choose your weapons")+"</p>"))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            mainLayout.addWidget(label)
            label = (QLabel(_("WingetUI is based on package managers. They are the engines used to load, install update and remove software from your computer. Please select the desired package managers and hit \"Apply\" to continue. The default ones are Winget and Chocolatey")))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)
            mainLayout.addWidget(label)

            
            winget = PackageManager(_("Enable {pm}").format(pm="Winget"), _("Microsoft's official package manager. It contains well known software such as browsers, PDF readers, windows add-ons and other utilities, as well as other less-known but useful software, such as Microsoft Visual C++ Redistributables. Packages from Winget have been carefully validated"), getMedia("winget"))
            winget.setChecked(True)
            scoop = PackageManager(_("Enable {pm}").format(pm="Scoop"), _("From scoop you will be able to download utilities that might not be suitable for everybody. Install CLI utilities such as nano, sudo or nmap for Windows. And with the ability to add custom buckets, you will be able to download unlimited amounts of different utilities, apps, fonts, games, and any other thing you can dream of."), getMedia("scoop"))
            scoop.setChecked(False)
            if (getSettings("ScoopAlreadySetup") or getSettings("ScoopEnabledByAssistant")) and not getSettings("DisableScoop"):
                scoop.setChecked(True)
            choco = PackageManager(_("Enable {pm}").format(pm="Chocolatey"), _("The package manager for Windows by default. With more than {0} packages on their repositories, you will find anything you want to install. From Firefox to Sysinternals, almost every package is available to download from Chocolatey servers").format("9500"), getMedia("choco"))
            choco.setChecked(True)
            
            mainLayout.addSpacing(20)
            mainLayout.addWidget(winget)
            mainLayout.addWidget(scoop)
            mainLayout.addWidget(choco)
            mainLayout.addSpacing(20)
            
            mainLayout.addStretch()
            
            
            blayout = QHBoxLayout()
            mainLayout.addLayout(blayout)
            blayout.addStretch()
            
            def performSelectionAndContinue():
                self.w.close()
                setSettings("AskedAbout3PackageManagers", True)
                setSettings("DisableWinget", not winget.isChecked())
                setSettings("DisableScoop", not scoop.isChecked())
                setSettings("ScoopEnabledByAssistant", scoop.isChecked())
                setSettings("DisableChocolatey", not choco.isChecked())
                if choco.isChecked() and shutil.which("choco") != None:
                    setSettings("UseSystemChocolatey", True)
                if scoop.isChecked() and shutil.which("scoop") == None:
                    os.startfile(os.path.join(realpath, "resources/install_scoop.cmd"))
                else:
                    onclose()
                    
            
            okbutton = QPushButton(_("Apply and start WingetUI"))
            okbutton.setFixedSize(190, 30)
            okbutton.setObjectName("AccentButton")
            okbutton.clicked.connect(performSelectionAndContinue)
            blayout.addWidget(okbutton)
            
            w = QWidget(self.w)
            w.setObjectName("mainbg")
            w.setLayout(mainLayout)
            l = QHBoxLayout()
            l.addWidget(w)
            self.w.setLayout(l)
            
            r = ApplyMica(self.w.winId(), MICAMODE.DARK if isDark() else MICAMODE.LIGHT)
            if r != 0:
                self.w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                self.w.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
            self.w.setStyleSheet(darkCSS.replace("mainbg", "transparent" if r == 0x0 else "#202020") if isDark() else lightCSS.replace("mainbg", "transparent" if r == 0x0 else "#f5f5f5"))
            self.w.show()

        def loadStuffThread(self):
            try:
                self.loadStatus = 0 # There are 9 items (preparation threads)
                setSettings("CachingChocolatey", False)
                
                # Preparation threads
                Thread(target=self.checkForRunningInstances, daemon=True).start()
                Thread(target=self.downloadPackagesMetadata, daemon=True).start()
                if not getSettings("DisableApi"):
                    Thread(target=runBackendApi, args=(self.showProgram,), daemon=True).start()
                if not getSettings("DisableWinget"):
                    Thread(target=self.detectWinget, daemon=True).start()
                else:
                    self.loadStatus += 2
                    globals.componentStatus["wingetFound"] = False
                    globals.componentStatus["wingetVersion"] = _("{0} is disabled").format("Winget")
                if not getSettings("DisableChocolatey"):
                    Thread(target=self.detectChocolatey, daemon=True).start()
                else:
                    self.loadStatus += 1
                    globals.componentStatus["chocoFound"] = False
                    globals.componentStatus["chocoVersion"] = _("{0} is disabled").format("Chocolatey")
                if not getSettings("DisableScoop"):
                    Thread(target=self.detectScoop, daemon=True).start()
                else:
                    self.loadStatus += 3
                    globals.componentStatus["scoopFound"] = False
                    globals.componentStatus["scoopVersion"] = _("{0} is disabled").format("Scoop")
                Thread(target=self.detectSudo, daemon=True).start()

                # Daemon threads
                Thread(target=self.instanceThread, daemon=True).start()
                Thread(target=self.updateIfPossible, daemon=True).start()
                
                while self.loadStatus < 9:
                    time.sleep(0.01)
            except Exception as e:
                print(e)
            finally:
                self.callInMain.emit(lambda: self.loadingText.setText(_("Loading UI components...")))
                self.callInMain.emit(lambda: self.loadingText.repaint())
                self.callInMain.emit(self.loadMainUI)
                print(globals.componentStatus)

        def checkForRunningInstances(self):
                print("Scanning for instances...")
                self.nowTime = time.time()
                self.lockFileName = f"WingetUI_{self.nowTime}"
                setSettings(self.lockFileName, True)
                try:
                    timestamps = [float(file.replace(os.path.join(os.path.join(os.path.expanduser("~"), ".wingetui"), "WingetUI_"), "")) for file in glob.glob(os.path.join(os.path.join(os.path.expanduser("~"), ".wingetui"), "WingetUI_*"))] # get a list with the timestamps
                    validTimestamps = [timestamp for timestamp in timestamps if timestamp < self.nowTime]
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Checking found instace(s)...")))
                    print("Found lock file(s), reactivating...")
                    for tst in validTimestamps:
                        setSettings("RaiseWindow_"+str(tst), True)
                    if validTimestamps != [] and timestamps != [self.nowTime]:
                        for i in range(16):
                            time.sleep(0.1)
                            self.callInMain.emit(lambda: self.loadingText.setText(_("Sent handshake. Waiting for instance listener's answer... ({0}%)").format(int(i/15*100))))
                            for tst in validTimestamps:
                                if not getSettings("RaiseWindow_"+str(tst), cache = False):
                                    print(f"Instance {tst} responded, quitting...")
                                    self.callInMain.emit(lambda: self.loadingText.setText(_("Instance {0} responded, quitting...").format(tst)))
                                    setSettings(self.lockFileName, False)
                                    self.kill.emit()
                                    sys.exit(0)
                        self.callInMain.emit(lambda: self.loadingText.setText(_("Starting daemons...")))
                        print("Reactivation signal ignored: RaiseWindow_"+str(validTimestamps))
                        for tst in validTimestamps:
                            setSettings("RaiseWindow_"+str(tst), False)
                            setSettings("WingetUI_"+str(tst), False)
                except Exception as e:
                    print(e)
                self.loadStatus += 1

        def detectWinget(self):
            try:
                self.callInMain.emit(lambda: self.loadingText.setText(_("Locating {pm}...").format(pm = "Winget")))
                o = subprocess.run(f"{wingetHelpers.winget} -v", shell=True, stdout=subprocess.PIPE)
                print(o.stdout)
                print(o.stderr)
                globals.componentStatus["wingetFound"] = o.returncode == 0
                globals.componentStatus["wingetVersion"] = o.stdout.decode('utf-8').replace("\n", "")
                self.callInMain.emit(lambda: self.loadingText.setText(_("{pm} found: {state}").format(pm = "Winget", state = globals.componentStatus['wingetFound'])))
            except Exception as e:
                print(e)
            self.loadStatus += 1
            print("updating winget")
            try:
                if not getSettings("DisableUpdateIndexes"):
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Updating Winget sources...")))
                    o = subprocess.run(f"{wingetHelpers.winget} source update --name winget", shell=True, stdout=subprocess.PIPE)
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Updated Winget sources")))
            except Exception as e:
                print(e)
            self.loadStatus += 1
            
        def detectChocolatey(self):
            try:
                self.callInMain.emit(lambda: self.loadingText.setText(_("Locating {pm}...").format(pm = "Chocolatey")))
                o = subprocess.run(f"{chocoHelpers.choco} -v", shell=True, stdout=subprocess.PIPE)
                print(o.stdout)
                print(o.stderr)
                globals.componentStatus["chocoFound"] = o.returncode == 0
                globals.componentStatus["chocoVersion"] = o.stdout.decode('utf-8').replace("\n", "")
                self.callInMain.emit(lambda: self.loadingText.setText(_("{pm} found: {state}").format(pm = "Chocolatey", state = globals.componentStatus['chocoFound'])))
            except Exception as e:
                print(e)
            self.loadStatus += 1
            
        def detectScoop(self):
            try:
                self.callInMain.emit(lambda: self.loadingText.setText(_("Locating {pm}...").format(pm = "Scoop")))
                o = subprocess.run(f"{scoopHelpers.scoop} -v", shell=True, stdout=subprocess.PIPE)
                print(o.stdout)
                print(o.stderr)
                globals.componentStatus["scoopFound"] = o.returncode == 0
                globals.componentStatus["scoopVersion"] = o.stdout.decode('utf-8').split("\n")[1]
                self.callInMain.emit(lambda: self.loadingText.setText(_("{pm} found: {state}").format(pm = "Scoop", state = globals.componentStatus['scoopFound'])))
            except Exception as e:
                print(e)
            self.loadStatus += 1
            try:
                if getSettings("EnableScoopCleanup"):
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Clearing Scoop cache...")))
                    p = subprocess.Popen(f"{scoopHelpers.scoop} cache rm *", shell=True, stdout=subprocess.PIPE)
                    p2 = subprocess.Popen(f"{scoopHelpers.scoop} cleanup --all --cache", shell=True, stdout=subprocess.PIPE)
                    p3 = subprocess.Popen(f"{scoopHelpers.scoop} cleanup --all --global --cache", shell=True, stdout=subprocess.PIPE)
                    p.wait()
                    p2.wait()
                    p3.wait()
            except Exception as e:
                report(e)
            self.loadStatus += 1
            try:
                if not getSettings("DisableUpdateIndexes"):
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Updating Scoop sources...")))
                    o = subprocess.run(f"{scoopHelpers.scoop} update", shell=True, stdout=subprocess.PIPE)
                    self.callInMain.emit(lambda: self.loadingText.setText(_("Updated Scoop sources")))
            except Exception as e:
                print(e)
            self.loadStatus += 1

        def detectSudo(self):
            global sudoLocation
            try:
                self.callInMain.emit(lambda: self.loadingText.setText(_("Locating {pm}...").format(pm = "sudo")))
                o = subprocess.run(f"{sudoPath} -v", shell=True, stdout=subprocess.PIPE)
                globals.componentStatus["sudoFound"] = o.returncode == 0
                globals.componentStatus["sudoVersion"] = o.stdout.decode('utf-8').split("\n")[0]
                self.callInMain.emit(lambda: self.loadingText.setText(_("{pm} found: {state}").format(pm = "Sudo", state = globals.componentStatus['sudoFound'])))
            except Exception as e:
                print(e)
            self.loadStatus += 1

        def downloadPackagesMetadata(self):
            try: 
                self.callInMain.emit(lambda: self.loadingText.setText(_("Downloading package metadata...")))
                data = urlopen("https://raw.githubusercontent.com/marticliment/WingetUI/main/WebBasedData/screenshot-database-v2.json").read()
                try:
                    os.makedirs(os.path.join(os.path.expanduser("~"), f".wingetui/cachedmeta"))
                except FileExistsError:
                    pass
                with open(os.path.join(os.path.expanduser("~"), f".wingetui/cachedmeta/packages.json"), "wb") as f:
                    f.write(data)
                print("🟢 Downloaded latest metadata to local file")
            except Exception as e:
                report(e)
            try:
                with open(os.path.join(os.path.expanduser("~"), f".wingetui/cachedmeta/packages.json"), "rb") as f:
                    globals.packageMeta = json.load(f)
                print("🔵 Loaded metadata from local file")
            except Exception as e:
                report(e)
            self.loadStatus += 1

        def loadMainUI(self):
            print("Reached main ui load milestone")
            try:
                globals.trayIcon = QSystemTrayIcon()
                self.trayIcon = globals.trayIcon
                globals.app = self
                self.trayIcon.setIcon(QIcon(getMedia("icon", autoIconMode = False)))
                self.trayIcon.setToolTip(_("Initializing WingetUI..."))
                self.trayIcon.setVisible(True)

                menu = QMenu("WingetUI")
                globals.trayMenu = menu
                self.trayIcon.setContextMenu(menu)
                self.discoverPackages = QAction(_("Discover Packages"), menu)
                menu.addAction(self.discoverPackages)
                menu.addSeparator()
                
                self.updatePackages = QAction(_("Software Updates"), menu)
                globals.updatesAction = self.updatePackages
                menu.addAction(self.updatePackages)
                
                self.updatesMenu = menu.addMenu(_("0 updates found"))
                self.updatesMenu.menuAction().setIcon(QIcon(getMedia("list")))
                self.updatesMenu.setParent(menu)
                globals.trayMenuUpdatesList = self.updatesMenu
                menu.addMenu(self.updatesMenu)
                
                globals.updatesHeader = QAction(f"{_('App Name')}  \t{_('Installed Version')} \t → \t {_('New version')}", menu)
                globals.updatesHeader.setEnabled(False)
                globals.updatesHeader.setIcon(QIcon(getMedia("version")))
                self.updatesMenu.addAction(globals.updatesHeader)
                
                self.uaAction = QAction(_("Update all"), menu)
                self.uaAction.setIcon(QIcon(getMedia("menu_installall")))
                menu.addAction(self.uaAction)
                menu.addSeparator()
                
                self.uninstallPackages = QAction(_("Installed Packages"),menu)
                menu.addAction(self.uninstallPackages)
                
                self.installedMenu = menu.addMenu(_("0 packages found"))
                self.installedMenu.menuAction().setIcon(QIcon(getMedia("list")))
                self.installedMenu.setParent(menu)
                globals.trayMenuInstalledList = self.installedMenu
                menu.addMenu(self.installedMenu)
                menu.addSeparator()
                
                globals.installedHeader = QAction(f"{_('App Name')}\t{_('Installed Version')}", menu)
                globals.installedHeader.setIcon(QIcon(getMedia("version")))
                globals.installedHeader.setEnabled(False)
                self.installedMenu.addAction(globals.installedHeader)
                
                self.infoAction = QAction(_("About WingetUI version {0}").format(versionName), menu)
                self.infoAction.setIcon(QIcon(getMedia("info")))
                menu.addAction(self.infoAction)
                self.showAction = QAction(_("Show WingetUI"), menu)
                self.showAction.setIcon(QIcon(getMedia("icon")))
                menu.addAction(self.showAction)
                menu.addSeparator()

                self.settings = QAction(_("WingetUI Settings"), menu)
                menu.addAction(self.settings)
                

                self.quitAction = QAction(menu)
                self.quitAction.setIcon(QIcon(getMedia("menu_close")))
                self.quitAction.setText(_("Quit"))
                self.quitAction.triggered.connect(lambda: (self.quit(), sys.exit(0)))
                menu.addAction(self.quitAction)
                
                self.updatePackages.setIcon(QIcon(getMedia("alert_laptop")))
                self.discoverPackages.setIcon(QIcon(getMedia("desktop_download")))
                self.settings.setIcon(QIcon(getMedia("settings_gear")))
                self.uninstallPackages.setIcon(QIcon(getMedia("workstation")))
                
                def showWindow():
                    # This function will be defined when the mainWindow gets defined
                    pass
                
                def showMenu():
                    pos = QCursor.pos()   
                    s = self.screenAt(pos)
                    if isW11 and (pos.y()+48) > (s.geometry().y() + s.geometry().height()):
                            menu.move(pos)
                            menu.show()
                            sy = s.geometry().y()+s.geometry().height()
                            sx = s.geometry().x()+s.geometry().width()
                            pos.setY(sy-menu.height()-54) # Show the context menu a little bit over the taskbar
                            pos.setX(sx-menu.width()-6) # Show the context menu a little bit over the taskbar
                            menu.move(pos)
                    else:
                        menu.exec(pos)
                self.trayIcon.activated.connect(lambda r: (applyMenuStyle(), showMenu()) if r == QSystemTrayIcon.Context else showWindow())
                
                self.trayIcon.messageClicked.connect(lambda: showWindow())
                self.installedMenu.aboutToShow.connect(lambda: applyMenuStyle())
                self.updatesMenu.aboutToShow.connect(lambda: applyMenuStyle())

                def applyMenuStyle():
                    for mn in (menu, self.updatesMenu, self.installedMenu):
                        mn.setObjectName("MenuMenuMenu")
                        if not isDark():
                            ss = f'#{mn.objectName()}{{background-color: {"rgba(220, 220, 220, 1%)" if isW11 else "rgba(255, 255, 255, 30%);border-radius: 0px;" };}}'
                        else:
                            ss = f'#{mn.objectName()}{{background-color: {"rgba(220, 220, 220, 1%)" if isW11 else "rgba(20, 20, 20, 25%);border-radius: 0px;"};}}'
                        if isDark():
                            ExtendFrameIntoClientArea(mn.winId().__int__())
                            mn.setStyleSheet(menuDarkCSS+ss)
                            GlobalBlur(mn.winId().__int__(), Acrylic=True, hexColor="#21212140", Dark=True)
                        else:
                            ExtendFrameIntoClientArea(mn.winId().__int__())
                            mn.setStyleSheet(menuLightCSS+ss)
                            GlobalBlur(mn.winId().__int__(), Acrylic=True, hexColor="#eeeeee40", Dark=False)

                self.setStyle("winvowsvista")
                globals.darkCSS = darkCSS.replace("Segoe UI Variable Text", globals.textfont).replace("Segoe UI Variable Display", globals.dispfont).replace("Segoe UI Variable Display Semib", globals.dispfontsemib)
                globals.lightCSS = lightCSS.replace("Segoe UI Variable Text", globals.textfont).replace("Segoe UI Variable Display", globals.dispfont).replace("Segoe UI Variable Display Semib", globals.dispfontsemib)
                self.window = RootWindow()
                self.showProgram.connect(lambda id: (self.discoverPackages.trigger(), globals.discover.loadShared(id)))
                self.discoverPackages.triggered.connect(lambda: self.window.showWindow(0))
                self.updatePackages.triggered.connect(lambda: self.window.showWindow(1))
                self.uninstallPackages.triggered.connect(lambda: self.window.showWindow(2))
                self.infoAction.triggered.connect(lambda: self.window.showWindow(4))
                self.settings.triggered.connect(lambda: self.window.showWindow(3))
                globals.mainWindow = self.window
                self.showAction.triggered.connect(lambda: self.window.showWindow())
                self.uaAction.triggered.connect(self.window.updates.upgradeAllAction.trigger)
                showWindow = self.showAction.trigger
                self.loadingText.setText(_("Latest details..."))
                if not self.isDaemon:
                    self.window.show()
                    if(self.window.isAdmin()):
                        if not getSettings("AlreadyWarnedAboutAdmin"):
                            self.window.warnAboutAdmin()
                            setSettings("AlreadyWarnedAboutAdmin", True)
                            
            except Exception as e:
                import webbrowser, traceback, platform
                try:
                    from tools import version as appversion
                except Exception as e:
                    appversion = "Unknown"
                os_info = f"" + \
                    f"                        OS: {platform.system()}\n"+\
                    f"                   Version: {platform.win32_ver()}\n"+\
                    f"           OS Architecture: {platform.machine()}\n"+\
                    f"          APP Architecture: {platform.architecture()[0]}\n"+\
                    f"               APP Version: {appversion}\n"+\
                    f"                   Program: WingetUI\n"+\
                    f"           Program section: UI Loading"+\
                    "\n\n-----------------------------------------------------------------------------------------"
                traceback_info = "Traceback (most recent call last):\n"
                try:
                    for line in traceback.extract_tb(e.__traceback__).format():
                        traceback_info += line
                    traceback_info += f"\n{type(e).__name__}: {str(e)}"
                except:
                    traceback_info += "\nUnable to get traceback"
                traceback_info += str(type(e))
                traceback_info += ": "
                traceback_info += str(e)
                webbrowser.open(("https://www.marticliment.com/error-report/?appName=WingetUI&errorBody="+os_info.replace('\n', '{l}').replace(' ', '{s}')+"{l}{l}{l}{l}WingetUI Log:{l}"+str("\n\n\n\n"+traceback_info).replace('\n', '{l}').replace(' ', '{s}')).replace("#", "|=|"))
                print(traceback_info)
            self.popup.hide()

        def reloadWindow(self):
            cprint("Reloading...")
            self.infoAction.setIcon(QIcon(getMedia("info")))
            self.updatesMenu.menuAction().setIcon(QIcon(getMedia("list")))
            globals.updatesHeader.setIcon(QIcon(getMedia("version")))
            self.uaAction.setIcon(QIcon(getMedia("menu_installall")))
            self.iAction.setIcon(QIcon(getMedia("menu_uninstall")))
            self.installedMenu.menuAction().setIcon(QIcon(getMedia("list")))
            globals.installedHeader.setIcon(QIcon(getMedia("version")))
            self.quitAction.setIcon(QIcon(getMedia("menu_close")))
            self.showAction.setIcon(QIcon(getMedia("menu_show")))
            globals.themeChanged = True 
            globals.mainWindow.setAttribute(Qt.WA_DeleteOnClose, True)
            globals.mainWindow.close()
            globals.mainWindow.deleteLater()
            self.window = RootWindow()
            globals.mainWindow = self.window
            self.showAction.triggered.disconnect()
            self.showAction.triggered.connect(self.window.showWindow)

        def instanceThread(self):
            while True:
                try:
                    for file in glob.glob(os.path.join(os.path.join(os.path.expanduser("~"), ".wingetui"), "RaiseWindow_*")):
                        if getSettings("RaiseWindow_"+str(self.nowTime), cache = False):
                            print("🟢 Found reactivation lock file...")
                            setSettings("RaiseWindow_"+str(self.nowTime), False)
                            if not self.window.isMaximized():
                                self.callInMain.emit(self.window.hide)
                                self.callInMain.emit(self.window.showMinimized)
                                self.callInMain.emit(self.window.show)
                                self.callInMain.emit(self.window.showNormal)
                            else:
                                self.callInMain.emit(self.window.hide)
                                self.callInMain.emit(self.window.showMinimized)
                                self.callInMain.emit(self.window.show)
                                self.callInMain.emit(self.window.showMaximized)
                            self.callInMain.emit(self.window.setFocus)
                            self.callInMain.emit(self.window.raise_)
                            self.callInMain.emit(self.window.activateWindow)
                except Exception as e:
                    print(e)
                time.sleep(0.5)

        def updateIfPossible(self):
            if not getSettings("DisableAutoUpdateWingetUI"):
                print("🔵 Starting update check")
                integrityPass = False
                dmname = socket.gethostbyname_ex("versions.marticliment.com")[0]
                if(dmname == dmname): # Check provider IP to prevent exploits
                    integrityPass = True
                try:
                    response = urlopen("https://versions.marticliment.com/versions/wingetui.ver")
                except Exception as e:
                    print(e)
                    response = urlopen("http://www.marticliment.com/versions/wingetui.ver")
                    integrityPass = True
                print("🔵 Version URL:", response.url)
                response = response.read().decode("utf8")
                new_version_number = response.split("///")[0]
                provided_hash = response.split("///")[1].replace("\n", "").lower()
                if float(new_version_number) > version:
                    print("🟢 Updates found!")
                    if(integrityPass):
                        url = "https://github.com/marticliment/WingetUI/releases/latest/download/WingetUI.Installer.exe"
                        filedata = urlopen(url)
                        datatowrite = filedata.read()
                        filename = ""
                        downloadPath = os.environ["temp"] if "temp" in os.environ.keys() else os.path.expanduser("~")
                        with open(os.path.join(downloadPath, "wingetui-updater.exe"), 'wb') as f:
                            f.write(datatowrite)
                            filename = f.name
                        if(hashlib.sha256(datatowrite).hexdigest().lower() == provided_hash):
                            print("🔵 Hash: ", provided_hash)
                            print("🟢 Hash ok, starting update")
                            globals.updatesAvailable = True
                            while globals.mainWindow == None:
                                time.sleep(1)
                            globals.canUpdate = not globals.mainWindow.isVisible()
                            while not globals.canUpdate:
                                time.sleep(0.1)
                            if not getSettings("DisableAutoUpdateWingetUI"):
                                subprocess.run('start /B "" "{0}" /silent'.format(filename), shell=True)
                        else:
                            print("🟠 Hash not ok")
                            print("🟠 File hash: ", hashlib.sha256(datatowrite).hexdigest())
                            print("🟠 Provided hash: ", provided_hash)
                    else:
                        print("🟠 Can't verify update server authenticity, aborting")
                        print("🟠 Provided DmName:", dmname)
                        print("🟠 Expected DmNane: 769432b9-3560-4f94-8f90-01c95844d994.id.repl.co")
                else:
                    print("🟢 Updates not found")

    colors = getColors()
    isW11 = False
    try:
        import platform
        if int(platform.version().split('.')[2]) >= 22000:
            isW11 = True
    except Exception as e:
        report(e)

    darkCSS = f"""
    * {{
        background-color: transparent;
        color: #eeeeee;
        font-family: "Segoe UI Variable Text";
        outline: none;
    }}
    *::disabled {{
        color: gray;
    }}
    QInputDialog {{
        background-color: #202020;
    }}
    #micawin {{
        background-color: mainbg;
    }}
    QMenu {{
        padding: 2px;
        outline: 0px;
        color: white;
        background: transparent;
        border-radius: 8px;
    }}
    QMenu::separator {{
        margin: 2px;
        height: 1px;
        background: rgb(60, 60, 60);
    }}
    QMenu::icon{{
        padding-left: 10px;
    }}
    QMenu::item{{
        height: 30px;
        border: none;
        background: transparent;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
        margin: 2px;
    }} 
    QMenu::item:disabled{{
        background: transparent;
        height: 30px;
        color: grey;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QMenu::item:selected{{
        background: rgba(255, 255, 255, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}  
    QMenu::item:selected:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QComboBox {{
        width: {(100)}px;
        background-color:rgba(81, 81, 81, 25%);
        border-radius: 8px;
        border: 1px solidrgba(86, 86, 86, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-top: 1px solidrgba(99, 99, 99, 25%);
    }}
    QComboBox:disabled {{
        width: {(100)}px;
        background-color: #303030;
        color: #bbbbbb;
        border-radius: 8px;
        border: 0.6px solid #262626;
        height: {(25)}px;
        padding-left: 10px;
    }}
    QComboBox:hover {{
        background-color:rgba(86, 86, 86, 25%);
        border-radius: 8px;
        border: 1px solidrgba(100, 100, 100, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-top: 1px solid rgba(107, 107, 107, 25%);
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        padding: 5px;
        border-radius: 8px;
        border: none;
        width: 30px;
    }}
    QComboBox::down-arrow {{
        image: url("{getMedia(f"collapse")}");
        height: 8px;
        width: 8px;
    }}
    QComboBox::down-arrow:disabled {{
        image: url("{getMedia(f"collapse")}");
        height: 8px;
        width: 8px;
    }}
    QMessageBox{{
        background-color: #202020;
    }}
    #greyLabel {{
        color: #bbbbbb;
    }}
    QPushButton,#FocusLabel {{
        width: 150px;
        background-color:rgba(81, 81, 81, 25%);
        border-radius: 6px;
        border: 1px solid rgba(86, 86, 86, 25%);
        height: 25px;
        font-size: 9pt;
        border-top: 1px solid rgba(99, 99, 99, 25%);
        margin: 0px;
        font-family: "Segoe UI Variable Display Semib";
    }}
    #FlatButton {{
        width: 150px;
        background-color: rgba(255, 255, 255, 1%);
        border-radius: 6px;
        border: 0px solid rgba(255, 255, 255, 1%);
        height: 25px;
        font-size: 9pt;
        border-top: 0px solid rgba(255, 255, 255, 1%);
    }}
    QPushButton:hover {{
        background-color:rgba(86, 86, 86, 25%);
        border-radius: 6px;
        border: 1px solid rgba(100, 100, 100, 25%);
        height: 30px;
        border-top: 1px solid rgba(107, 107, 107, 25%);
    }}
    #Headerbutton {{
        width: 150px;
        background-color:rgba(0, 0, 0, 1%);
        border-radius: 6px;
        border: 0px solid transparent;
        height: 25px;
        font-size: 9pt;
        margin: 0px;
        font-family: "Segoe UI Variable Display Semib";
        font-size: 9pt;
    }}
    #Headerbutton:hover {{
        background-color:rgba(100, 100, 100, 12%);
        border-radius: 8px;
        height: 30px;
    }}
    #Headerbutton:checked {{
        background-color:rgba(100, 100, 100, 25%);
        border-radius: 8px;
        border: 0px solid rgba(100, 100, 100, 25%);
        height: 30px;
    }}
    #buttonier {{
        border: 0px solid rgba(100, 100, 100, 25%);
        border-radius: 12px;
    }}
    #AccentButton{{
        color: #202020;
        font-size: 9pt;
        font-family: "Segoe UI Variable Display Semib";
        background-color: rgb({colors[1]});
        border-color: rgb({colors[1]});
        border-bottom-color: rgb({colors[2]});
    }}
    #AccentButton:hover{{
        background-color: rgba({colors[1]}, 80%);
        border-color: rgb({colors[2]});
        border-bottom-color: rgb({colors[2]});
    }}
    #AccentButton:pressed{{
        color: #555555;
        background-color: rgba({colors[1]}, 80%);
        border-color: rgb({colors[2]});
        border-bottom-color: rgb({colors[2]});
    }}
    #AccentButton:disabled{{
        color: grey;
        background-color: rgba(50,50,50, 80%);
        border-color: rgb(50, 50, 50);
        border-bottom-color: rgb(50, 50, 50);
    }}
    QLineEdit {{
        background-color: rgba(81, 81, 81, 25%);
        font-family: "Segoe UI Variable Text";
        font-size: 9pt;
        width: 300px;
        padding: 5px;
        border-radius: 6px;
        border: 0.6px solid rgba(86, 86, 86, 25%);
        border-bottom: 2px solid rgb({colors[4]});
        selection-background-color: rgb({colors[2]});
    }}
    QLineEdit:disabled {{
        background-color: rgba(81, 81, 81, 25%);
        font-family: "Segoe UI Variable Text";
        font-size: 9pt;
        width: 300px;
        padding: 5px;
        border-radius: 6px;
        border: 0.6px solid rgba(86, 86, 86, 25%);
    }}
    QLabel{{
        selection-background-color: rgb({colors[2]});
    }}
    QScrollBar:vertical {{
        background: transparent;
        border: 1px solid #1f1f1f;
        margin: 3px;
        width: 18px;
        border: none;
        border-radius: 4px;
    }}
    QScrollBar::handle {{
        margin: 3px;
        min-height: 20px;
        min-width: 20px;
        border-radius: 3px;
        background: #505050;
    }}
    QScrollBar::handle:hover {{
        margin: 3px;
        border-radius: 3px;
        background: #808080;
    }}
    QScrollBar::add-line {{
        height: 0;
        subcontrol-position: bottom;
        subcontrol-origin: margin;
    }}
    QScrollBar::sub-line {{
        height: 0;
        subcontrol-position: top;
        subcontrol-origin: margin;
    }}
    QScrollBar::up-arrow, QScrollBar::down-arrow {{
        background: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: none;
    }}
    QHeaderView,QAbstractItemView {{
        background-color: #55303030;
        border-radius: 6px;
        border: none;
        padding: 1px;
        height: 25px;
        border: 1px solid #1f1f1f;
        margin-bottom: 5px;
        margin-left: 10px;
        margin-right: 10px;
    }}
    QHeaderView::section {{
        background-color: transparent;
        border-radius: 6px;
        padding: 4px;
        height: 25px;
        margin: 1px;
    }}
    QHeaderView::section:first {{
        background-color: transparent;
        border-radius: 6px;
        padding: 4px;
        height: 25px;
        margin: 1px;
        margin-left: -20px;
        padding-left: 30px;
    }}
    QTreeWidget {{
        show-decoration-selected: 0;
        background-color: transparent;
        padding: 5px;
        margin: 0px;
        outline: none;
        border-radius: 6px;
        border: 0px solid #1f1f1f;
    }}
    QTreeWidget::item {{
        margin-top: 3px;
        margin-bottom: 3px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        background-color: rgba(48, 48, 48, 20%);
        height: 25px;
        border-bottom: 1px solid #1f1f1f;
        border-top: 1px solid #1f1f1f;
    }}
    QTreeWidget::item:selected {{
        margin-top: 2px;
        margin-bottom: 2px;
        padding: 0px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        background-color: rgba(48, 48, 48, 35%);
        height: 25px;
        border-bottom: 1px solid #303030;
        border-top: 1px solid #303030;
        color: rgb({colors[2]});
    }}
    QTreeWidget::item:hover {{
        margin-top: 2px;
        margin-bottom: 2px;
        padding: 0px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        background-color: rgba(48, 48, 48, 45%);
        height: 25px;
        border-bottom: 1px solid #303030;
        border-top: 1px solid #303030;
    }}
    QTreeWidget::item:first {{
        border-top-left-radius: 6px;
        border-bottom-left-radius: 6px;
        border-left: 1px solid #1f1f1f;
        margin-left: 0px;
    }}
    QTreeWidget::item:last {{
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        border-right: 1px solid #1f1f1f;
        margin-right: 0px;
    }}
    QTreeWidget::item:first:selected {{
        border-left: 1px solid #303030;
    }}
    QTreeWidget::item:last:selected {{
        border-right: 1px solid #303030;
    }}
    QTreeWidget::item:first:hover {{
        border-left: 1px solid #303030;
    }}
    QTreeWidget::item:last:hover {{
        border-right: 1px solid #303030;
    }}
    QProgressBar {{
        border-radius: 2px;
        height: 4px;
        border: 0px;
    }}
    QProgressBar::chunk {{
        background-color: rgb({colors[2]});
        border-radius: 2px;
    }}
    QCheckBox::indicator{{
        height: 16px;
        width: 16px;
    }}
    QTreeView::indicator{{
        height:18px;
        width: 18px;
        margin: 0px;
        margin-left: 4px;
        margin-top: 2px;
    }}
    QTreeView::indicator:unchecked,QCheckBox::indicator:unchecked {{
        background-color: rgba(30, 30, 30, 25%);
        border: 1px solid #444444;
        border-radius: 4px;
    }}
    QTreeView::indicator:disabled,QCheckBox::indicator:disabled {{
        background-color: rgba(30, 30, 30, 5%);
        color: #dddddd;
        border: 1px solid rgba(255, 255, 255, 5%);
        border-radius: 4px;
    }}
    QTreeView::indicator:unchecked:hover,QCheckBox::indicator:unchecked:hover {{
        background-color: #2a2a2a;
        border: 1px solid #444444;
        border-radius: 4px;
    }}
    QTreeView::indicator:checked,QCheckBox::indicator:checked {{
        border: 1px solid #444444;
        background-color: rgba({colors[1]}, 80%);
        border-radius: 4px;
        image: url("{getMedia("tick")}");
    }}
    QTreeView::indicator:disabled,QCheckBox::indicator:checked:disabled {{
        border: 1px solid #444444;
        background-color: #303030;
        color: #dddddd;
        border-radius:4px;
    }}
    QTreeView::indicator:checked:hover,QCheckBox::indicator:checked:hover {{
        border: 1px solid #444444;
        background-color: rgb({colors[2]});
        border-radius: 4px;
    }}
    QComboBox {{
        width: 100px;
        background-color:rgba(81, 81, 81, 25%);
        border-radius: 6px;
        border: 1px solid rgba(86, 86, 86, 25%);
        height: 30px;
        padding-left: 10px;
        border: 1px solid rgba(86, 86, 86, 25%);
    }}
    QComboBox:disabled {{
        width: 100px;
        background-color: #303030;
        color: #bbbbbb;
        border-radius: 6px;
        border: 0.6px solid #262626;
        height: 25px;
        padding-left: 10px;
    }}
    QComboBox:hover {{
        background-color:rgba(86, 86, 86, 25%);
        border-radius: 6px;
        border: 1px solidrgba(100, 100, 100, 25%);
        height: 25px;
        padding-left: 10px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        background-color: none;
        padding: 5px;
        border-radius: 6px;
        border: none;
        width: 30px;
    }}
    QComboBox::down-arrow {{
        image: url("{getMedia("drop-down")}");
        height: 8px;
        width: 8px;
    }}
    QComboBox::down-arrow:disabled {{
        image: url("{getMedia("drop-down")}");
        height: 8px;
        width: 8px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid rgba(36, 36, 36, 50%);
        padding: 4px;
        margin: 0px;
        outline: 0px;
        background-color: #303030;
        border-radius: 8px;
    }}
    QComboBox QAbstractItemView::item{{
        height: 30px;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QComboBox QAbstractItemView::item:selected{{
        background: rgba(255, 255, 255, 6%);
        height: 30px;
        outline: none;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    #package {{
        margin: 0px;
        padding: 0px;
        background-color: #55303030;
        border-radius: 8px;
        border: 1px solid #1f1f1f;
    }}
    QListWidget{{
        border: 0px;
        background-color: transparent;
        color: transparent;
    }}
    QListWidget::item{{
        border: 0px;
        background-color: transparent;
        color: transparent;
    }}
    QPlainTextEdit{{
        border: 1px solid #1b1b1b;
        border-radius: 6px;
        padding: 6px;
        color: white;
        background-color: #212121;
        font-family: "Consolas";
    }}
    QToolTip {{
        background-color: #303030;
        border: 1px solid #202020;
        border-radius: 0px;
    }}
    QToolButton {{
        background-color:rgba(0, 0, 0, 1%);
        border-radius: 4px;
        border: 0px solid transparent;
        margin: 5px;
        margin-right: 0px;
        font-size: 9pt;
        font-family: "Segoe UI Variable Display Semib";
        font-size: 9pt;
        padding: 4px;
    }}
    QToolButton:hover {{
        background-color:rgba(100, 100, 100, 12%);
        border-radius: 4px;
        margin: 5px;
        margin-right: 0px;
        padding: 4px;
    }}
    QToolBar:separator {{
        width: 1px;
        margin: 5px;
        margin-right: 0px;
        background-color: rgba(255, 255, 255, 10%);
    }}
    #greyishLabel {{
        color: #aaaaaa;
    }}
    #subtitleLabelHover {{
        background-color: rgba(20, 20, 20, 0.01);
        margin: 10px;
        margin-top: 0;
        margin-bottom: 0;
        border-radius: 4px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        border: 1px solid transparent;
    }}
    #subtitleLabelHover:hover{{
        background-color: rgba(255, 255, 255, 3%);
        margin: 10px;
        margin-top: 0;
        margin-bottom: 0;
        padding-left: {(20)}px;
        padding-top: 0;
        padding-bottom: 0;
        border: 1px solid rgba(255, 255, 255, 7%);
        font-size: 13pt;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    #subtitleLabelHover:pressed{{
        background-color: rgba(0, 0, 0, 12%);
        margin: 10px;
        margin-top: 0;
        margin-bottom: 0;
        padding-left: {(20)}px;
        padding-top: 0;
        padding-bottom: 0;
        border: 1px solid rgba(255, 255, 255, 7%);
        font-size: 13pt;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    #micaRegularBackground {{
        border: 0 solid transparent;
        margin: 1px;
        background-color: rgba(255, 255, 255, 5%);
        border-radius: 8px;
    }}
    #subtitleLabel{{
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        padding-left: {(20)}px;
        padding-top: {(15)}px;
        padding-bottom: {(15)}px;
        border: 1px solid rgba(25, 25, 25, 50%);
        font-size: 13pt;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    #StLbl{{
        padding: 0;
        background-color: rgba(71, 71, 71, 0%);
        margin: 0;
        border:none;
        font-size: {(11)}px;
    }}
    #stBtn{{
        background-color: rgba(255, 255, 255, 5%);
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        border: 1px solid rgba(25, 25, 25, 50%);
        border-bottom-left-radius: 8px;
        border-bottom-right-radius: 8px;
    }}
    #lastWidget{{
        border-bottom-left-radius: 4px;
        border-bottom-right-radius: 4px;
    }}
    #stChkBg{{
        padding: {(15)}px;
        padding-left: {(45)}px;
        background-color: rgba(255, 255, 255, 5%);
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        border: 1px solid rgba(25, 25, 25, 50%);
        border-bottom: 0;
    }}
    #stChk::indicator{{
        height: {(20)}px;
        width: {(20)}px;
    }}
    #stChk::indicator:unchecked {{
        background-color: rgba(30, 30, 30, 25%);
        border: 1px solid #444444;
        border-radius: 6px;
    }}
    #stChk::indicator:disabled {{
        background-color: rgba(71, 71, 71, 0%);
        color: #bbbbbb;
        border: 1px solid #444444;
        border-radius: 6px;
    }}
    #stChk::indicator:unchecked:hover {{
        background-color: #2a2a2a;
        border: 1px solid #444444;
        border-radius: 6px;
    }}
    #stChk::indicator:checked {{
        border: 1px solid #444444;
        background-color: rgb({colors[1]});
        border-radius: 6px;
        image: url("{getPath("tick_white.png")}");
    }}
    #stChk::indicator:checked:disabled {{
        border: 1px solid #444444;
        background-color: #303030;
        color: #bbbbbb;
        border-radius: 6px;
        image: url("{getPath("tick_black.png")}");
    }}
    #stChk::indicator:checked:hover {{
        border: 1px solid #444444;
        background-color: rgb({colors[2]});
        border-radius: 6px;
        image: url("{getPath("tick_white.png")}");
    }}
    #stCmbbx {{
        width: {(100)}px;
        background-color:rgba(81, 81, 81, 25%);
        border-radius: 8px;
        border: 1px solidrgba(86, 86, 86, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-top: 1px solidrgba(99, 99, 99, 25%);
    }}
    #stCmbbx:disabled {{
        width: {(100)}px;
        background-color: #303030;
        color: #bbbbbb;
        border-radius: 8px;
        border: 0.6px solid #262626;
        height: {(25)}px;
        padding-left: 10px;
    }}
    #stCmbbx:hover {{
        background-color:rgba(86, 86, 86, 25%);
        border-radius: 8px;
        border: 1px solidrgba(100, 100, 100, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-top: 1px solid rgba(107, 107, 107, 25%);
    }}
    #stCmbbx::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        padding: 5px;
        border-radius: 8px;
        border: none;
        width: 30px;
    }}
    #stCmbbx QAbstractItemView {{
        border: 1px solid rgba(36, 36, 36, 50%);
        padding: 4px;
        outline: 0;
        padding-right: 0;
        background-color: #303030;
        border-radius: 8px;
    }}
    #stCmbbx QAbstractItemView::item{{
        height: 30px;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    #stCmbbx QAbstractItemView::item:selected{{
        background: rgba(255, 255, 255, 6%);
        height: 30px;
        outline: none;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    """

    menuDarkCSS = f"""
    * {{
        border-radius: 8px;
        background-color: transparent;
    }}
    QWidget{{
        background-color: transparent;
        border-radius: 8px;
        menu-scrollable: 1;
    }}
    QMenu {{
        padding: 2px;
        outline: 0px;
        color: white;
        font-family: "Segoe UI Variable Text";
        border-radius: 8px;
    }}
    QMenu::separator {{
        margin: 2px;
        height: 1px;
        background: rgb(60, 60, 60);
    }}
    QMenu::icon{{
        padding-left: 10px;
    }}
    QMenu::item{{
        height: 30px;
        border: none;
        background: transparent;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
        margin: 2px;
    }}
    QMenu::item:selected{{
        background: rgba(255, 255, 255, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}  
    QMenu::item:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        border: none;
        color: grey;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QMenu::item:selected:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}"""

    lightCSS = f"""
    * {{
        background-color: transparent;
        color: #000000;
        font-family: "Segoe UI Variable Text";
        outline: none;
    }}
    *::disabled {{
        color: gray;
    }}
    QInputDialog {{
        background-color: #f5f5f5;
    }}
    #micawin {{
        background-color: mainbg;
        color: red;
    }}
    QMenu {{
        border: 1px solid rgb(200, 200, 200);
        padding: 2px;
        outline: 0px;
        color: black;
        background: #eeeeee;
        border-radius: 8px;
    }}
    QMenu::separator {{
        margin: 2px;
        height: 1px;
        background: rgb(200, 200, 200);
    }}
    QMenu::icon{{
        padding-left: 10px;
    }}
    QMenu::item{{
        height: 30px;
        border: none;
        background: transparent;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
        margin: 2px;
    }}
    QMenu::item:selected{{
        background: rgba(0, 0, 0, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}  
    QMenu::item:selected:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        border: none;
        padding-right: 10px;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid rgba(196, 196, 196, 25%);
        padding: 4px;
        outline: 0px;
        background-color: rgba(255, 255, 255, 10%);
        border-radius: 8px;
    }}
    QComboBox QAbstractItemView::item{{
        height: 10px;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QComboBox QAbstractItemView::item:selected{{
        background: rgba(0, 0, 0, 6%);
        height: 10px;
        outline: none;
        color: black;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    QMessageBox{{
        background-color: #f9f9f9;
    }}
    #greyLabel {{
        color: #404040;
    }}
    QPushButton,#FocusLabel {{
        width: 150px;
        background-color:rgba(255, 255, 255, 55%);
        border: 1px solid rgba(220, 220, 220, 55%);
        border-top: 1px solid rgba(220, 220, 220, 75%);
        border-radius: 6px;
        height: 25px;
        font-size: 9pt;
        margin: 0px;
        font-family: "Segoe UI Variable Display Semib";
    }}
    #FlatButton {{
        width: 150px;
        background-color: rgba(255, 255, 255, 0.1%);
        border-radius: 6px;
        border: 0px solid rgba(255, 255, 255, 1%);
        height: 25px;
        font-size: 9pt;
        border-top: 0px solid rgba(255, 255, 255, 1%);
    }}
    QPushButton:hover {{
        background-color: rgba(255, 255, 255, 90%);
        border: 1px solid rgba(220, 220, 220, 65%);
        border-top: 1px solid rgba(220, 220, 220, 80%);
        border-radius: 6px;
        height: 30px;
    }}
    #AccentButton{{
        color: #000000;
        font-size: 9pt;
        background-color: rgb({colors[2]});
        border-color: rgb({colors[3]});
        border-bottom-color: rgb({colors[4]});
        font-family: "Segoe UI Variable Display Semib";
    }}
    #AccentButton:hover{{
        background-color: rgba({colors[3]}, 80%);
        border-color: rgb({colors[4]});
        border-bottom-color: rgb({colors[5]});
    }}
    #AccentButton:pressed{{
        color: #000000;
        background-color: rgba({colors[4]}, 80%);
        border-color: rgb({colors[5]});
        border-bottom-color: rgb({colors[5]});
    }}
    #AccentButton:disabled{{
        color: #000000;
        background-color: rgba(200,200,200, 80%);
        border-color: rgb(200, 200, 200);
        border-bottom-color: rgb(200, 200, 200);
    }}
    #Headerbutton {{
        width: 150px;
        background-color:rgba(255, 255, 255, 1%);
        border-radius: 6px;
        border: 0px solid transparent;
        height: 25px;
        font-size: 9pt;
        margin: 0px;
        font-family: "Segoe UI Variable Display";
        font-size: 9pt;
    }}
    #Headerbutton:hover {{
        background-color:rgba(0, 0, 0, 5%);
        border-radius: 8px;
        height: 30px;
    }}
    #Headerbutton:checked {{
        background-color:rgba(0, 0, 0, 10%);
        border-radius: 8px;
        border: 0px solid rgba(100, 100, 100, 25%);
        height: 30px;
    }}
    #buttonier {{
        border: 0px solid rgba(100, 100, 100, 25%);
        border-radius: 12px;
    }}
    QLineEdit {{
        background-color: rgba(255, 255, 255, 25%);
        font-family: "Segoe UI Variable Text";
        font-size: 9pt;
        width: 300px;
        color: black;
        padding: 5px;
        border-radius: 6px;
        border: 1px solid rgba(86, 86, 86, 25%);
        border-bottom: 2px solid rgb({colors[3]});
    }}
    QLineEdit:disabled {{
        background-color: rgba(255, 255, 255, 25%);
        font-family: "Segoe UI Variable Text";
        font-size: 9pt;
        width: 300px;
        padding: 5px;
        border-radius: 6px;
        border: 1px solid rgba(255, 255, 255, 55%);
    }}
    QScrollBar:vertical {{
        background: transparent;
        border: 1px solid rgba(240, 240, 240, 55%);
        margin: 3px;
        width: 18px;
        border: none;
        border-radius: 4px;
    }}
    QScrollBar::handle {{
        margin: 3px;
        min-height: 20px;
        min-width: 20px;
        border-radius: 3px;
        background: #a0a0a0;
    }}
    QScrollBar::handle:hover {{
        margin: 3px;
        border-radius: 3px;
        background: #808080;
    }}
    QScrollBar::add-line {{
        height: 0;
        subcontrol-position: bottom;
        subcontrol-origin: margin;
    }}
    QScrollBar::sub-line {{
        height: 0;
        subcontrol-position: top;
        subcontrol-origin: margin;
    }}
    QScrollBar::up-arrow, QScrollBar::down-arrow {{
        background: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: none;
    }}
    QHeaderView,QAbstractItemView {{
        background-color: rgba(255, 255, 255, 55%);
        border-radius: 6px;
        border: none;
        padding: 1px;
        height: 25px;
        border: 1px solid rgba(220, 220, 220, 55%);
        margin-bottom: 5px;
        margin-left: 10px;
        margin-right: 10px;
    }}
    QHeaderView::section {{
        background-color: transparent;
        border-radius: 6px;
        padding: 4px;
        height: 25px;
        margin: 1px;
    }}
    QHeaderView::section:first {{
        background-color: transparent;
        border-radius: 6px;
        padding: 4px;
        height: 25px;
        margin: 1px;
        margin-left: -20px;
        padding-left: 10px;
    }}
    QTreeWidget {{
        show-decoration-selected: 0;
        background-color: transparent;
        padding: 5px;
        outline: none;
        border-radius: 6px;
        border: 0px solid rgba(240, 240, 240, 55%);
    }}
    QTreeWidget::item {{
        margin-top: 3px;
        margin-bottom: 3px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        height: 25px;
        background-color:rgba(255, 255, 255, 55%);
        border-top: 1px solid rgba(220, 220, 220, 55%);
        border-bottom: 1px solid rgba(220, 220, 220, 55%);
    }}
    QTreeWidget::item:selected {{
        margin-top: 2px;
        margin-bottom: 2px;
        padding: 0px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        background-color: rgba(240, 240, 240, 90%);
        height: 25px;
        border-bottom: 1px solid rgba(220, 220, 220, 70%);
        border-top: 1px solid rgba(220, 220, 220, 80%);
        color: rgb({colors[5]});
    }}
    QTreeWidget::branch {{
        background-color: transparent;
    }}
    QTreeWidget::item:hover {{
        margin-top: 2px;
        margin-bottom: 2px;
        padding: 0px;
        padding-top: 3px;
        padding-bottom: 3px;
        outline: none;
        background-color: rgba(230, 230, 230, 90%);
        height: 25px;
        border-bottom: 1px solid rgba(230, 230, 230, 70%);
        border-top: 1px solid rgba(220, 220, 220, 80%);
    }}
    QTreeWidget::item:first {{
        border-top-left-radius: 6px;
        border-bottom-left-radius: 6px;
        border-left: 1px solid rgba(220, 220, 220, 55%);
    }}
    QTreeWidget::item:last {{
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
        border-right: 1px solid rgba(220, 220, 220, 55%);
    }}
    QTreeWidget::item:first:selected {{
        border-left: 1px solid rgba(220, 220, 220, 80%);
    }}
    QTreeWidget::item:last:selected {{
        border-right: 1px solid rgba(220, 220, 220, 80%);
    }}
    QTreeWidget::item:first:hover {{
        border-left: 1px solid rgba(220, 220, 220, 80%);
    }}
    QTreeWidget::item:last:hover {{
        border-right: 1px solid rgba(220, 220, 220, 80%);
    }}
    QProgressBar {{
        border-radius: 2px;
        height: 4px;
        border: 0px;
    }}
    QProgressBar::chunk {{
        background-color: rgb({colors[3]});
        border-radius: 2px;
    }}
    QCheckBox::indicator{{
        height: 16px;
        width: 16px;
    }}
    QTreeView::indicator{{
        height:18px;
        width: 18px;
        margin: 0px;
        margin-left: 4px;
        margin-top: 2px;
    }}
    QTreeView::indicator:unchecked,QCheckBox::indicator:unchecked {{
        background-color: rgba(255, 255, 255, 25%);
        border: 1px solid rgba(0, 0, 0, 10%);
        border-radius: 4px;
    }}
    QTreeView::indicator:disabled,QCheckBox::indicator:disabled {{
        background-color: rgba(240, 240, 240, 0%);
        color: #444444;
        border: 1px solid rgba(0, 0, 0, 5%);
        border-radius: 4px;
    }}
    QTreeView::indicator:unchecked:hover,QCheckBox::indicator:unchecked:hover {{
        background-color: rgba(0, 0, 0, 5%);
        border: 1px solid rgba(0, 0, 0, 20%);
        border-radius: 4px;
    }}
    QTreeView::indicator:checked,QCheckBox::indicator:checked {{
        border: 1px solid rgb({colors[3]});
        background-color: rgb({colors[2]});
        border-radius: 4px;
        image: url("{getMedia("tick")}");
    }}
    QTreeView::indicator:checked:disabled,QCheckBox::indicator:checked:disabled {{
        border: 1px solid #444444;
        background-color: #303030;
        color: #444444;
        border-radius: 4px;
    }}
    QTreeView::indicator:checked:hover,QCheckBox::indicator:checked:hover {{
        border: 1px solid rgb({colors[3]});
        background-color: rgb({colors[3]});
        border-radius: 4px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        background-color: none;
        padding: 5px;
        border-radius: 6px;
        border: none;
        color: white;
        width: 30px;
    }}
    QComboBox::down-arrow {{
        image: url("{getMedia("drop-down")}");
        height: 8px;
        width: 8px;
    }}
    QComboBox::down-arrow:disabled {{
        image: url("{getMedia("drop-down")}");
        height: 2px;
        width: 2px;
    }}
    QComboBox QAbstractItemView {{
        padding: 0px;
        margin: 0px;
        outline: 0px;
        background-color: #ffffff;
        border-radius: 8px;
        color: black;
    }}
    QComboBox QAbstractItemView::item{{
        height: 30px;
        margin: 4px;
        border: none;
        padding-left: 10px;
        color: black;
        border-radius: 4px;
        background: rgba(255, 255, 255, 1%);
    }}
    QComboBox QAbstractItemView::item:hover{{
        background: rgba(0, 0, 0, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-left: 10px;
        color: black;
        border-radius: 4px;
    }}
    QComboBox QAbstractItemView::item:selected{{
        background: rgba(0, 0, 0, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-left: 10px;
        color: black;
        border-radius: 4px;
    }}
    QComboBox {{
        width: 150px;
        background-color:rgba(255, 255, 255, 55%);
        border: 1px solid rgba(220, 220, 220, 55%);
        border-top: 1px solid rgba(220, 220, 220, 75%);
        border-radius: 6px;
        height: 30px;
        padding-left: 10px;
        font-size: 9pt;
        margin: 0px;
    }}
    QComboBox:hover {{
        background-color: rgba(255, 255, 255, 90%);
        border: 1px solid rgba(220, 220, 220, 65%);
        border-top: 1px solid rgba(220, 220, 220, 80%);
        border-radius: 6px;
        height: 30px;
    }}
    QComboBox:disabled{{
        color: #000000;
        background-color: rgba(200,200,200, 80%);
        border-color: rgb(200, 200, 200);
        border-bottom-color: rgb(200, 200, 200);
    }}
    #package {{
        margin: 0px;
        padding: 0px;
        border-radius: 8px;
        background-color:rgba(255, 255, 255, 55%);
        border: 1px solid rgba(220, 220, 220, 55%);
    }}
    QPlainTextEdit{{
        border: 1px solid #eeeeee;
        border-radius: 6px;
        padding: 6px;
        color: black;
        background-color: #ffffff;
        font-family: "Consolas";
    }}
    QLabel{{
        selection-background-color: rgb({colors[3]});
    }}
    QToolButton {{
        background-color:rgba(255, 255, 255, 1%);
        border-radius: 4px;
        border: 0px solid transparent;
        margin: 5px;
        margin-right: 0px;
        font-size: 9pt;
        font-family: "Segoe UI Variable Display Semib";
        font-size: 9pt;
        padding: 4px;
    }}
    QToolButton:hover {{
        background-color:rgba(0, 0, 0, 6%);
        border-radius: 4px;
        margin: 5px;
        margin-right: 0px;
        padding: 4px;
    }}
    QToolBar:separator {{
        width: 1px;
        margin: 5px;
        margin-right: 0px;
        background-color: rgba(0, 0, 0, 10%);
    }}
    #greyishLabel {{
        color: #888888;
    }}
    #subtitleLabel{{
        background-color: white;
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        padding-left: {(20)}px;
        padding-top: {(15)}px;
        padding-bottom: {(15)}px;
        border-radius: 8px;
        border: 1 solid rgba(222, 222, 222, 50%);
        font-size: 13pt;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    #subtitleLabelHover {{
        background-color: rgba(255, 255, 255, 1%);
        margin: 10px;
        margin-top: 0;
        margin-bottom: 0;
        border-radius: 8px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        border: 1px solid transparent;
    }}
    #subtitleLabelHover:hover{{
        background-color: rgba(0, 0, 0, 3%);
        margin: 10px;
        margin-top: 0;
        margin-bottom: 0;
        padding-left: {(20)}px;
        padding-top: {(15)}px;
        padding-bottom: {(15)}px;
        border: 1px solid rgba(196, 196, 196, 25%);
        font-size: 13pt;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    #StLbl{{
        padding: 0;
        background-color: rgba(255, 255, 255, 10%);
        margin: 0;
        border:none;
        font-size: {(11)}px;
    }}
    #stBtn{{
        background-color: rgba(255, 255, 255, 10%);
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        border: 1px solid rgba(196, 196, 196, 25%);
        border-bottom: 0;
        border-bottom-left-radius: 0;
        border-bottom-right-radius: 0;
    }}
    #lastWidget{{
        border-bottom-left-radius: 4px;
        border-bottom-right-radius: 4px;
        border-bottom: 1px;
    }}
    #stChkBg{{
        padding: {(15)}px;
        padding-left: {(45)}px;
        background-color: rgba(255, 255, 255, 10%);
        margin: 10px;
        margin-bottom: 0;
        margin-top: 0;
        border: 1px solid rgba(196, 196, 196, 25%);
        border-bottom: 0;
    }}
    #stChk::indicator{{
        height: {(20)}px;
        width: {(20)}px;
    }}
    #stChk::indicator:unchecked {{
        background-color: rgba(255, 255, 255, 10%);
        border: 1px solid rgba(136, 136, 136, 25%);
        border-radius: 6px;
    }}
    #stChk::indicator:disabled {{
        background-color: #eeeeee;
        color: rgba(136, 136, 136, 25%);
        border: 1px solid rgba(136, 136, 136, 25%);
        border-radius: 6px;
    }}
    #stChk::indicator:unchecked:hover {{
        background-color: #eeeeee;
        border: 1px solid rgba(136, 136, 136, 25%);
        border-radius: 6px;
    }}
    #stChk::indicator:checked {{
        border: 0 solid rgba(136, 136, 136, 25%);
        background-color: rgb({colors[4]});
        border-radius: 5px;
        image: url("{getPath("tick_black.png")}");
    }}
    #stChk::indicator:checked:hover {{
        border: 0 solid rgba(136, 136, 136, 25%);
        background-color: rgb({colors[3]});
        border-radius: 5px;
        image: url("{getPath("tick_black.png")}");
    }}
    #stChk::indicator:checked:disabled {{
        border: 1px solid rgba(136, 136, 136, 25%);
        background-color: #eeeeee;
        color: rgba(136, 136, 136, 25%);
        border-radius: 6px;
        image: url("{getPath("tick_white.png")}");
    }}
    #stCmbbx {{
        width: {(100)}px;
        background-color: rgba(255, 255, 255, 10%);
        border-radius: 8px;
        border: 1px solid rgba(196, 196, 196, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-bottom: 1px solid rgba(204, 204, 204, 25%);
    }}
    #stCmbbx:disabled {{
        width: {(100)}px;
        background-color: #eeeeee;
        border-radius: 8px;
        border: 1px solid rgba(196, 196, 196, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-top: 1px solid rgba(196, 196, 196, 25%);
    }}
    #stCmbbx:hover {{
        background-color: rgba(238, 238, 238, 25%);
        border-radius: 8px;
        border: 1px solid rgba(196, 196, 196, 25%);
        height: {(25)}px;
        padding-left: 10px;
        border-bottom: 1px solid rgba(204, 204, 204, 25%);
    }}
    #stCmbbx::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        padding: 5px;
        border-radius: 8px;
        border: none;
        width: 30px;
    }}
    #stCmbbx QAbstractItemView {{
        border: 1px solid rgba(196, 196, 196, 25%);
        padding: 4px;
        outline: 0;
        background-color: rgba(255, 255, 255, 10%);
        border-radius: 8px;
    }}
    #stCmbbx QAbstractItemView::item{{
        height: 30px;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    #stCmbbx QAbstractItemView::item:selected{{
        background: rgba(0, 0, 0, 6%);
        height: 30px;
        outline: none;
        color: black;
        border: none;
        padding-left: 10px;
        border-radius: 4px;
    }}
    """

    menuLightCSS = f"""
    QWidget{{
        background-color: transparent;
        menu-scrollable: 1;
        border-radius: 8px;
    }}
    QMenu {{
        font-family: "Segoe UI Variable Text";
        border: 1px solid rgb(200, 200, 200);
        padding: 2px;
        outline: 0px;
        color: black;
        icon-size: 32px;
        background: rgba(220, 220, 220, 1%)/*#262626*/;
        border-radius: 8px;
    }}
    QMenu::separator {{
        margin: -2px;
        margin-top: 2px;
        margin-bottom: 2px;
        height: 1px;
        background-color: rgba(0, 0, 0, 20%);
    }}
    QMenu::icon{{
        padding-left: 10px;
    }}
    QMenu::item{{
        height: 30px;
        border: none;
        background: transparent;
        padding-right: 20px;
        padding-left: 0px;
        border-radius: 4px;
        margin: 2px;
    }}
    QMenu::item:selected{{
        background: rgba(0, 0, 0, 10%);
        height: 30px;
        outline: none;
        border: none;
        padding-right: 20px;
        padding-left: 0px;
        border-radius: 4px;
    }}
    QMenu::item:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        color: grey;
        border: none;
        padding-right: 20px;
        padding-left: 0px;
        border-radius: 4px;
    }}   
    QMenu::item:selected:disabled{{
        background: transparent;
        height: 30px;
        outline: none;
        border: none;
        padding-right: 20px;
        padding-left: 0px;
        border-radius: 4px;
    }}           
    """
    if "--daemon" in sys.argv:
        if getSettings("DisableAutostart"):
            sys.exit(0)
    translator = QTranslator()
    translator.load(f"qtbase_{langName}.qm", QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    a = MainApplication()
    a.installTranslator(translator)
    a.exec()
    a.running = False
    sys.exit(0)
except Exception as e:
    import webbrowser, traceback, platform
    try:
        from tools import version as appversion
    except Exception as e2:
        appversion = "Unknown"
    os_info = f"" + \
        f"                        OS: {platform.system()}\n"+\
        f"                   Version: {platform.win32_ver()}\n"+\
        f"           OS Architecture: {platform.machine()}\n"+\
        f"          APP Architecture: {platform.architecture()[0]}\n"+\
        f"               APP Version: {appversion}\n"+\
        f"                   Program: WingetUI\n"+\
        f"           Program section: Main script"+\
        "\n\n-----------------------------------------------------------------------------------------"
    traceback_info = "Traceback (most recent call last):\n"
    try:
        for line in traceback.extract_tb(e.__traceback__).format():
            traceback_info += line
        traceback_info += f"\n{type(e).__name__}: {str(e)}"
    except:
        traceback_info += "\nUnable to get traceback"
    traceback_info += str(type(e))
    traceback_info += ": "
    traceback_info += str(e)
    webbrowser.open(("https://www.marticliment.com/error-report/?appName=WingetUI&errorBody="+os_info.replace('\n', '{l}').replace(' ', '{s}')+"{l}{l}{l}{l}WingetUI Log:{l}"+str("\n\n\n\n"+traceback_info).replace('\n', '{l}').replace(' ', '{s}')).replace("#", "|=|"))
    print(traceback_info)
