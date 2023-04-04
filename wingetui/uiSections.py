from __future__ import annotations
import glob # to fix NameError: name 'TreeWidgetItemWithQAction' is not defined
import wingetHelpers, scoopHelpers, chocoHelpers, sys, subprocess, time, os, json
from threading import Thread
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
from tools import *
from storeEngine import *
from data.translations import untranslatedPercentage, languageCredits
from data.contributors import contributorsInfo

import globals
from customWidgets import *
from tools import _

class DiscoverSoftwareSection(QWidget):

    addProgram = Signal(str, str, str, str)
    finishLoading = Signal(str)
    askForScoopInstall = Signal(str)
    setLoadBarValue = Signal(str)
    startAnim = Signal(QVariantAnimation)
    changeBarOrientation = Signal()
    callInMain = Signal(object)
    discoverLabelDefaultWidth: int = 0
    discoverLabelIsSmall: bool = False
    isToolbarSmall: bool = False
    toolbarDefaultWidth: int = 0
    packages: dict[str:dict] = {}
    packageItems: list[TreeWidgetItemWithQAction] = []
    showableItems: list[TreeWidgetItemWithQAction] = []
    addedItems: list[TreeWidgetItemWithQAction] = []
    showedItems: list[TreeWidgetItemWithQAction] = []
        
    wingetLoaded = False
    scoopLoaded = False
    chocoLoaded = False

    def __init__(self, parent = None):
        super().__init__(parent = parent)
        self.infobox = globals.infobox
        self.setStyleSheet("margin: 0px;")

        self.programbox = QWidget()
        self.callInMain.connect(lambda f: f())

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.layout)

        self.reloadButton = QPushButton()
        self.reloadButton.setFixedSize(30, 30)
        self.reloadButton.setStyleSheet("margin-top: 0px;")
        self.reloadButton.clicked.connect(self.reload)
        self.reloadButton.setIcon(QIcon(getMedia("reload")))
        self.reloadButton.setAccessibleName(_("Reload"))

        self.searchButton = QPushButton()
        self.searchButton.setFixedSize(30, 30)
        self.searchButton.setStyleSheet("margin-top: 0px;")
        self.searchButton.clicked.connect(self.filter)
        self.searchButton.setIcon(QIcon(getMedia("search")))
        self.searchButton.setAccessibleName(_("Search"))

        hLayout = QHBoxLayout()
        hLayout.setContentsMargins(25, 0, 25, 0)

        self.forceCheckBox = QCheckBox(_("Instant search"))
        self.forceCheckBox.setFixedHeight(30)
        self.forceCheckBox.setLayoutDirection(Qt.RightToLeft)
        self.forceCheckBox.setStyleSheet("margin-top: 0px;")
        self.forceCheckBox.setChecked(True)
        self.forceCheckBox.setChecked(not getSettings("DisableInstantSearchOnInstall"))
        self.forceCheckBox.clicked.connect(lambda v: setSettings("DisableInstantSearchOnInstall", bool(not v)))
         
        self.query = CustomLineEdit()
        self.query.setPlaceholderText(" "+_("Search for packages"))
        self.query.returnPressed.connect(lambda: (self.filter()))
        self.query.editingFinished.connect(lambda: (self.filter()))
        self.query.textChanged.connect(lambda: self.filter() if self.forceCheckBox.isChecked() else print())
        self.query.setFixedHeight(30)
        self.query.setStyleSheet("margin-top: 0px;")
        self.query.setMinimumWidth(100)
        self.query.setMaximumWidth(250)
        self.query.setBaseSize(250, 30)
        
        sct = QShortcut(QKeySequence("Ctrl+F"), self)
        sct.activated.connect(lambda: (self.query.setFocus(), self.query.setSelection(0, len(self.query.text()))))

        sct = QShortcut(QKeySequence("Ctrl+R"), self)
        sct.activated.connect(self.reload)
        
        sct = QShortcut(QKeySequence("F5"), self)
        sct.activated.connect(self.reload)

        sct = QShortcut(QKeySequence("Esc"), self)
        sct.activated.connect(self.query.clear)
        

        img = QLabel()
        img.setFixedWidth(80)
        img.setPixmap(QIcon(getMedia("desktop_download")).pixmap(QSize(64, 64)))
        hLayout.addWidget(img)

        v = QVBoxLayout()
        v.setSpacing(0)
        v.setContentsMargins(0, 0, 0, 0)
        self.discoverLabel = QLabel(_("Discover Packages"))
        self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        v.addWidget(self.discoverLabel)

        self.titleWidget = QWidget()
        self.titleWidget.setContentsMargins(0, 0, 0, 0)
        self.titleWidget.setFixedHeight(70)
        self.titleWidget.setLayout(v)

        hLayout.addWidget(self.titleWidget, stretch=1)
        hLayout.addStretch()
        forceCheckBox = QVBoxLayout()
        forceCheckBox.addWidget(self.forceCheckBox)
        hLayout.addLayout(forceCheckBox)
        hLayout.addWidget(self.query)
        hLayout.addWidget(self.searchButton)
        hLayout.addWidget(self.reloadButton)

        self.packageListScrollBar = CustomScrollBar()
        self.packageListScrollBar.setOrientation(Qt.Vertical)
        self.packageListScrollBar.valueChanged.connect(lambda v: self.addItemsToTreeWidget() if v==self.packageListScrollBar.maximum() else None)

        self.packageList = TreeWidget("a")
        self.packageList.setHeaderLabels(["", _("Package Name"), _("Package ID"), _("Version"), _("Source")])
        self.packageList.setColumnCount(5)
        self.packageList.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.packageList.setSortingEnabled(True)
        self.packageList.setVerticalScrollBar(self.packageListScrollBar)
        self.packageList.connectCustomScrollbar(self.packageListScrollBar)
        self.packageList.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.packageList.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        self.packageList.setIconSize(QSize(24, 24))
        self.packageList.itemDoubleClicked.connect(lambda item, column: self.openInfo(item.text(1), item.text(2), item.text(4), item) if not getSettings("InstallOnDoubleClick") else self.fastinstall(item.text(1), item.text(2), item.text(4), packageItem=item))
        self.packageList.currentItemChanged.connect(lambda: self.addItemsToTreeWidget() if self.packageList.indexOfTopLevelItem(self.packageList.currentItem())+20 > self.packageList.topLevelItemCount() else None)

        sct = QShortcut(Qt.Key.Key_Return, self.packageList)
        sct.activated.connect(lambda: self.filter() if self.query.hasFocus() else self.packageList.itemDoubleClicked.emit(self.packageList.currentItem(), 0))
        
        def toggleItemState():
            item = self.packageList.currentItem()
            checked = item.checkState(0) == Qt.CheckState.Checked
            item.setCheckState(0, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

        sct = QShortcut(QKeySequence(Qt.Key_Space), self.packageList)
        sct.activated.connect(toggleItemState)
        
        def showMenu(pos: QPoint):
            if not self.packageList.currentItem():
                return
            if self.packageList.currentItem().isHidden():
                return
            contextMenu = QMenu(self)
            contextMenu.setParent(self)
            contextMenu.setStyleSheet("* {background: red;color: black}")
            ApplyMenuBlur(contextMenu.winId().__int__(), contextMenu)
            inf = QAction(_("Show info"))
            inf.triggered.connect(lambda: (contextMenu.close(), self.openInfo(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem())))
            inf.setIcon(QIcon(getMedia("info")))
            ins1 = QAction(_("Install"))
            ins1.setIcon(QIcon(getMedia("newversion")))
            ins1.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem()))
            ins2 = QAction(_("Install as administrator"))
            ins2.setIcon(QIcon(getMedia("runasadmin")))
            ins2.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), admin=True, packageItem=self.packageList.currentItem()))
            ins3 = QAction(_("Skip hash check"))
            ins3.setIcon(QIcon(getMedia("checksum")))
            ins3.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), skiphash=True, packageItem=self.packageList.currentItem()))
            ins4 = QAction(_("Interactive installation"))
            ins4.setIcon(QIcon(getMedia("interactive")))
            ins4.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), interactive=True, packageItem=self.packageList.currentItem()))
            contextMenu.addAction(ins1)
            contextMenu.addSeparator()
            contextMenu.addAction(ins2)
            if not "scoop" in self.packageList.currentItem().text(4).lower():
                contextMenu.addAction(ins4)
            contextMenu.addAction(ins3)
            contextMenu.addSeparator()
            contextMenu.addAction(inf)
            contextMenu.exec(QCursor.pos())

        self.packageList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.packageList.customContextMenuRequested.connect(showMenu)

        header = self.packageList.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.sectionClicked.connect(lambda: self.finishFiltering(self.query.text()))
        self.packageList.setColumnWidth(0, 10)
        self.packageList.setColumnWidth(3, 150)
        self.packageList.setColumnWidth(4, 150)
        
        
        self.loadingProgressBar = QProgressBar()
        self.loadingProgressBar.setRange(0, 1000)
        self.loadingProgressBar.setValue(0)
        self.loadingProgressBar.setFixedHeight(4)
        self.loadingProgressBar.setTextVisible(False)
        self.loadingProgressBar.setStyleSheet("margin: 0px; margin-left: 15px;margin-right: 15px;")

        layout = QVBoxLayout()
        w = QWidget()
        w.setLayout(layout)
        w.setMaximumWidth(1300)

        self.bodyWidget = QWidget()
        l = QHBoxLayout()
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        l.addWidget(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        l.addWidget(self.packageListScrollBar)
        self.bodyWidget.setLayout(l)

        self.toolbar = QToolBar(self.window())
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.toolbar.addWidget(TenPxSpacer())
        self.upgradeSelected = QAction(QIcon(getMedia("newversion")), "", self.toolbar)
        self.upgradeSelected.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), packageItem=self.packageList.currentItem()))
        self.toolbar.addAction(self.upgradeSelected)
        
        inf = QAction("", self.toolbar)# ("Show info")
        inf.triggered.connect(lambda: self.openInfo(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), self.packageList.currentItem()))
        inf.setIcon(QIcon(getMedia("info")))
        ins2 = QAction("", self.toolbar)# ("Run as administrator")
        ins2.setIcon(QIcon(getMedia("runasadmin")))
        ins2.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), packageItem=self.packageList.currentItem(), admin=True))
        ins3 = QAction("", self.toolbar)# ("Skip hash check")
        ins3.setIcon(QIcon(getMedia("checksum")))
        ins3.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), packageItem=self.packageList.currentItem(), skiphash=True))
        ins4 = QAction("", self.toolbar)# ("Interactive update")
        ins4.setIcon(QIcon(getMedia("interactive")))
        ins4.triggered.connect(lambda: self.fastinstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), packageItem=self.packageList.currentItem(), interactive=True))
        ins5 = QAction("", self.toolbar)
        ins5.setIcon(QIcon(getMedia("share")))
        ins5.triggered.connect(lambda: self.sharePackage(self.packageList.currentItem()))

        
        for action in [self.upgradeSelected, inf, ins2, ins3, ins4, ins5]:
            self.toolbar.addAction(action)
            self.toolbar.widgetForAction(action).setFixedSize(40, 45)

        self.toolbar.addSeparator()
        
        self.installSelectedAction = QAction(QIcon(getMedia("list")), _("Install selected"), self.toolbar)
        self.installSelectedAction.triggered.connect(lambda: self.installSelected())
        self.toolbar.addAction(self.installSelectedAction)
        
        self.toolbar.addSeparator()
        
        def setAllSelected(checked: bool) -> None:
            itemList = []
            self.packageList.setSortingEnabled(False)
            for i in range(self.packageList.topLevelItemCount()):
                itemList.append(self.packageList.topLevelItem(i))
            for program in itemList:
                if not program.isHidden():
                    program.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.packageList.setSortingEnabled(True)

        self.selectNoneAction = QAction(QIcon(getMedia("selectnone")), "", self.toolbar)
        self.selectNoneAction.triggered.connect(lambda: setAllSelected(False))
        self.toolbar.addAction(self.selectNoneAction)
        self.toolbar.widgetForAction(self.selectNoneAction).setFixedSize(40, 45)
        
        self.toolbar.addSeparator()

        self.importAction = QAction(_("Import packages from a file"), self.toolbar)
        self.importAction.setIcon(QIcon(getMedia("import")))
        self.importAction.triggered.connect(lambda: self.importPackages())
        self.toolbar.addAction(self.importAction)

        self.exportAction = QAction(QIcon(getMedia("export")), _("Export selected packages to a file"), self.toolbar)
        self.exportAction.triggered.connect(lambda: self.exportSelection())
        self.toolbar.addAction(self.exportAction)


        tooltips = {
            self.upgradeSelected: _("Install package"),
            inf: _("Show package info"),
            ins2: _("Run the installer with administrator privileges"),
            ins3: _("Skip the hash check"),
            ins4: _("Interactive installation"),
            ins5: _("Share"),
            self.installSelectedAction: _("Install selected"),
            self.selectNoneAction: _("Clear selection"),
            self.importAction: _("Import packages from a file"),
            self.exportAction: _("Export selected packages to a file")
        }

            
        for action in tooltips.keys():
            self.toolbar.widgetForAction(action).setAccessibleName(tooltips[action])
            self.toolbar.widgetForAction(action).setToolTip(tooltips[action])
            
            
        self.toolbar.addWidget(TenPxSpacer())
        self.toolbar.addWidget(TenPxSpacer())

        self.countLabel = QLabel(_("Searching for packages..."))
        self.packageList.label.setText(self.countLabel.text())
        self.countLabel.setObjectName("greyLabel")
        v.addWidget(self.countLabel)
        layout.addLayout(hLayout)
        layout.addWidget(self.toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.countLabel)
        
        self.cachingChocoLabel = ClosableOpaqueMessage()
        self.cachingChocoLabel.setText(_("Chocolatey packages are being loaded. Since this is the first time, it might take a while, and they will show here once loaded."))
        self.cachingChocoLabel.image.hide()
        self.cachingChocoLabel.hide()
        
        layout.addWidget(self.loadingProgressBar)
        layout.addWidget(self.cachingChocoLabel)
        hl2 = QHBoxLayout()
        hl2.addWidget(self.packageList)
        hl2.addWidget(self.packageListScrollBar)
        hl2.setSpacing(0)
        hl2.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(hl2)
        self.programbox.setLayout(l)
        self.layout.addWidget(self.programbox, stretch=1)
        self.infobox.hide()

        self.addProgram.connect(self.addItem)

        self.finishLoading.connect(self.finishLoadingIfNeeded)
        self.infobox.addProgram.connect(self.addInstallation)
        self.setLoadBarValue.connect(self.loadingProgressBar.setValue)
        self.startAnim.connect(lambda anim: anim.start())
        self.changeBarOrientation.connect(lambda: self.loadingProgressBar.setInvertedAppearance(not(self.loadingProgressBar.invertedAppearance())))
        
        self.reloadButton.setEnabled(False)
        self.searchButton.setEnabled(False)
        self.query.setEnabled(False)
        
        self.installIcon = QIcon(getMedia("install"))
        self.IDIcon = QIcon(getMedia("ID"))
        self.versionIcon = QIcon(getMedia("newversion"))
        self.wingetIcon = QIcon(getMedia("winget"))
        self.scoopIcon = QIcon(getMedia("scoop"))
        self.chocolateyIcon = QIcon(getMedia("choco"))

        if not getSettings("DisableWinget"):
            Thread(target=wingetHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.wingetLoaded = True
        if not getSettings("DisableScoop"):
            Thread(target=scoopHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.scoopLoaded = True
        if not getSettings("DisableChocolatey"):
            Thread(target=chocoHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.chocoLoaded = True
        self.finishLoadingIfNeeded("none")
        print("🟢 Discover tab loaded")

        g = self.packageList.geometry()
            
        
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
        
        self.leftSlow.start()
        
    def sharePackage(self, package):
        self.shareUI = ShareUI(self, id=package.text(2), name=package.text(1))

    def loadShared(self, id):
        if id in self.packages:
            package = self.packages[id]
            self.infobox.loadProgram(package["name"], id, useId=not("…" in id), store=package["store"], packageItem=package["item"], version=package["store"])
            self.infobox.show()
            cprint("shown")
        else:
            self.err = ErrorMessage(self.window())
            errorData = {
                    "titlebarTitle": _("Unable to find package"),
                    "mainTitle": _("Unable to find package"),
                    "mainText": _("We could not load detailed information about this package, because it was found in any of your package sources"),
                    "buttonTitle": _("Ok"),
                    "errorDetails": _("This is probably due to the fact that the package you were sent was removed, or published on a package manager that you don't have enabled. The received ID is {0}").format(id),
                    "icon": QIcon(getMedia("notif_warn")),
                }
            self.err.showErrorMessage(errorData, showNotification=False)

    def exportSelection(self) -> None:
        """
        Export all selected packages into a file.

        """
        wingetPackagesList = []
        scoopPackageList = []
        chocoPackageList = []

        try:
            for item in self.packageItems:
                if ((item.checkState(0) ==  Qt.CheckState.Checked) and item.text(4).lower() == "winget"):
                    id = item.text(2).strip()
                    wingetPackage = {"PackageIdentifier": id}
                    wingetPackagesList.append(wingetPackage)
                elif ((item.checkState(0) ==  Qt.CheckState.Checked) and "scoop" in item.text(4).lower()):
                    scoopPackage = {"Name": item.text(2)}
                    scoopPackageList.append(scoopPackage)
                elif ((item.checkState(0) ==  Qt.CheckState.Checked) and item.text(4).lower() == "chocolatey"):
                    chocoPackage = {"Name": item.text(2)}
                    chocoPackageList.append(chocoPackage)

            wingetDetails = {
                "Argument": "https://cdn.winget.microsoft.com/cache",
                "Identifier" : "Microsoft.Winget.Source_8wekyb3d8bbwe",
                "Name": "winget",
                "Type" : "Microsoft.PreIndexed.Package"
            }
            wingetExportSchema = {
                "$schema" : "https://aka.ms/winget-packages.schema.2.0.json",
                "CreationDate" : "2022-08-16T20:55:44.415-00:00", # TODO: get data automatically
                "Sources": [{
                    "Packages": wingetPackagesList,
                    "SourceDetails": wingetDetails}],
                "WinGetVersion" : "1.4.2161-preview" # TODO: get installed winget version
            }
            scoopExportSchema = {
                "apps": scoopPackageList,
            }
            chocoExportSchema = {
                "apps": chocoPackageList,
            }
            overAllSchema = {
                "winget": wingetExportSchema,
                "scoop": scoopExportSchema,
                "chocolatey": chocoExportSchema
            }

            filename = QFileDialog.getSaveFileName(self, _("Save File"), _("wingetui exported packages"), filter='JSON (*.json)')
            if filename[0] != "":
                with open(filename[0], 'w') as f:
                    f.write(json.dumps(overAllSchema, indent=4))

        except Exception as e:
            report(e)

    def installSelected(self) -> None:
            for package in self.packageItems:
                    try:
                        if package.checkState(0) ==  Qt.CheckState.Checked:
                           self.fastinstall(package.text(1), package.text(2), package.text(4), packageItem=package)
                    except AttributeError:
                        pass

    def importPackages(self):
        try:
            packageList = []
            file = QFileDialog.getOpenFileName(self, _("Select package file"), filter="JSON (*.json)")[0]
            if file != "":
                f = open(file, "r")
                contents = json.load(f)
                f.close()
                try:
                    packages = contents["winget"]["Sources"][0]["Packages"]
                    for pkg in packages:
                        packageList.append(pkg["PackageIdentifier"])
                except KeyError as e:
                    print("🟠 Invalid winget section")
                try:
                    packages = contents["scoop"]["apps"]
                    for pkg in packages:
                        packageList.append(pkg["Name"])
                except KeyError as e:
                    print("🟠 Invalid scoop section")
                try:
                    packages = contents["chocolatey"]["apps"]
                    for pkg in packages:
                        packageList.append(pkg["Name"])
                except KeyError as e:
                    print("🟠 Invalid chocolatey section")
                for packageId in packageList:
                    try:
                        item = self.packages[packageId]["item"]
                        self.fastinstall(item.text(1), item.text(2), item.text(4))
                    except KeyError:
                        print(f"🟠 Can't find package {packageId} in the package reference")
        except Exception as e:
            report(e)
        
    def finishLoadingIfNeeded(self, store: str) -> None:
        if(store == "winget"):
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(len(self.packageItems))))
            if len(self.packageItems) == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            self.wingetLoaded = True
            self.reloadButton.setEnabled(True)
            self.finishFiltering(self.query.text())
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
            self.addItemsToTreeWidget()
        elif(store == "scoop"):
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(len(self.packageItems))))
            if len(self.packageItems) == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            self.scoopLoaded = True
            self.reloadButton.setEnabled(True)
            self.finishFiltering(self.query.text())
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        elif("chocolatey" in store):
            msg = store.split("-")[-1]
            if msg == "caching":
                self.cachingChocoLabel.show()
            else:
                if msg == "finishedcache":
                    self.reload()
                self.cachingChocoLabel.hide()
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(len(self.packageItems))))
            if len(self.packageItems) == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            self.chocoLoaded = True
            self.reloadButton.setEnabled(True)
            self.finishFiltering(self.query.text())
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        if(self.wingetLoaded and self.scoopLoaded and self.chocoLoaded):
            self.reloadButton.setEnabled(True)
            self.finishFiltering(self.query.text())
            self.loadingProgressBar.hide()
            self.countLabel.setText(_("Found packages: {0}").format(str(len(self.packageItems))))
            self.packageList.label.setText("")
            print("🟢 Total packages: "+str(len(self.packageItems)))

    def resizeEvent(self, event: QResizeEvent):
        self.adjustWidgetsSize()
        return super().resizeEvent(event)
    
    def addItem(self, name: str, id: str, version: str, store) -> None:
        if not "---" in name and not name in ("+", "Everything", "Scoop", "At", "The", "But") and not version in ("the", "is"):
            item = TreeWidgetItemWithQAction(self)
            item.setText(1, name)
            item.setText(2, id)
            item.setIcon(1, self.installIcon)
            item.setIcon(2, self.IDIcon)
            item.setIcon(3, self.versionIcon)
            if "scoop" in store.lower():
                item.setIcon(4, self.scoopIcon)
            elif "winget" in store.lower():
                item.setIcon(4, self.wingetIcon)
            else:
                item.setIcon(4, self.chocolateyIcon)
            item.setText(4, store)
            item.setText(3, version)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            self.packages[id] = {
                "name": name,
                "version": version,
                "store": store,
                "item": item
            }
            self.packageItems.append(item)
            if self.containsQuery(item, self.query.text()):
                self.showableItems.append(item)
            
    def addItemsToTreeWidget(self, reset: bool = False):
        if reset:
            for item in self.showedItems:
                item.setHidden(True)
            nextItem = 0
            self.showedItems = []
        else:
            nextItem = self.packageList.topLevelItemCount()
        addedItems = 0
        while addedItems < 100:
            if nextItem >= len(self.showableItems):
                break
            itemToAdd = self.showableItems[nextItem]
            if itemToAdd not in self.addedItems:
                self.packageList.addTopLevelItem(itemToAdd)
                self.addedItems.append(itemToAdd)
            else:
                itemToAdd.setHidden(False)
            self.showedItems.append(itemToAdd)
            addedItems += 1
            nextItem += 1
    
    def filter(self) -> None:
        print(f"🟢 Searching for string \"{self.query.text()}\"")
        Thread(target=lambda: (time.sleep(0.1), self.callInMain.emit(partial(self.finishFiltering, self.query.text())))).start()
        
    def containsQuery(self, item: QTreeWidgetItem, text: str) -> bool:
        return text.lower() in item.text(0).lower() or text.lower() in item.text(1).lower()
    
    def finishFiltering(self, text: str):
        def getTitle(item: QTreeWidgetItem) -> str:
            return item.text(1)
        def getID(item: QTreeWidgetItem) -> str:
            return item.text(2)
        def getVersion(item: QTreeWidgetItem) -> str:
            return item.text(3)
        def getSource(item: QTreeWidgetItem) -> str:
            return item.text(4)
        
        if self.query.text() != text:
            return
        self.showableItems = []
        found = 0
        
        sortColumn = self.packageList.sortColumn()
        descendingSort = self.packageList.header().sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
        match sortColumn:
            case 1:
                self.packageItems.sort(key=getTitle, reverse=descendingSort)
            case 2:
                self.packageItems.sort(key=getID, reverse=descendingSort)
            case 3:
                self.packageItems.sort(key=getVersion, reverse=descendingSort)
            case 4:
                self.packageItems.sort(key=getSource, reverse=descendingSort)
        
        for item in self.packageItems:
            try:
                if self.containsQuery(item, text):
                    self.showableItems.append(item)
                    found += 1
            except RuntimeError:
                print("nullitem")
        if found == 0:
            if self.packageList.label.text() == "":
                self.packageList.label.show()
                self.packageList.label.setText(_("No packages found matching the input criteria"))
        else:
            if self.packageList.label.text() == _("No packages found matching the input criteria"):
                self.packageList.label.hide()
                self.packageList.label.setText("")
        self.addItemsToTreeWidget(reset = True)
        self.packageList.scrollToItem(self.packageList.currentItem())
    
    def showQuery(self) -> None:
        self.programbox.show()
        self.infobox.hide()

    def openInfo(self, title: str, id: str, store: str, packageItem: TreeWidgetItemWithQAction) -> None:
        self.infobox.loadProgram(title, id, useId=not("…" in id), store=store, packageItem=packageItem, version=packageItem.text(3))
        self.infobox.show()

    def fastinstall(self, title: str, id: str, store: str, admin: bool = False, interactive: bool = False, skiphash: bool = False, packageItem: TreeWidgetItemWithQAction = None) -> None:
        if "winget" == store.lower():
            self.addInstallation(PackageInstallerWidget(title, "winget", useId=not("…" in id), packageId=id, admin=admin, args=list(filter(None, ["--interactive" if interactive else "--silent", "--ignore-security-hash" if skiphash else "", "--force"])), packageItem=packageItem))
        elif "chocolatey" == store.lower():
            self.addInstallation(PackageInstallerWidget(title, "chocolatey", useId=True, packageId=id, admin=admin, args=list(filter(None, ["--force" if skiphash else "", "--ignore-checksums" if skiphash else "", "--notsilent" if interactive else ""])), packageItem=packageItem))
        else:
            self.addInstallation(PackageInstallerWidget(title, store, useId=not("…" in id), packageId=id, admin=admin, args=["--skip" if skiphash else ""], packageItem=packageItem))
    
    def reload(self) -> None:
        if self.wingetLoaded and self.scoopLoaded and self.chocoLoaded:
            self.packageItems = []
            self.packages = {}
            self.showedItems = []
            self.addedItems = []
            self.scoopLoaded = False
            self.wingetLoaded = False
            self.chocoLoaded = False
            self.loadingProgressBar.show()
            self.reloadButton.setEnabled(False)
            self.searchButton.setEnabled(False)
            self.query.setEnabled(False)
            self.packageList.clear()
            self.query.setText("")
            self.countLabel.setText(_("Searching for packages..."))
            self.packageList.label.setText(self.countLabel.text())
            if not getSettings("DisableWinget"):
                Thread(target=wingetHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.wingetLoaded = True
            if not getSettings("DisableScoop"):
                Thread(target=scoopHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.scoopLoaded = True
            if not getSettings("DisableChocolatey"):
                Thread(target=chocoHelpers.searchForPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.chocoLoaded = True
            self.finishLoadingIfNeeded("none")
    
    def addInstallation(self, p) -> None:
        globals.installersWidget.addItem(p)
    
    def destroyAnims(self) -> None:
        for anim in (self.leftSlow, self.leftFast, self.rightFast, self.rightSlow):
            anim: QVariantAnimation
            anim.pause()
            anim.stop()
            anim.valueChanged.disconnect()
            anim.finished.disconnect()
            anim.deleteLater()

    def showEvent(self, event: QShowEvent) -> None:
        self.adjustWidgetsSize()
        return super().showEvent(event)

    def adjustWidgetsSize(self) -> None:
        if self.discoverLabelDefaultWidth == 0:
            self.discoverLabelDefaultWidth = self.discoverLabel.sizeHint().width()
        if self.discoverLabelDefaultWidth > self.titleWidget.width():
            if not self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = True
                self.discoverLabel.setStyleSheet(f"font-size: 15pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        else:
            if self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = False
                self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")

        self.forceCheckBox.setFixedWidth(self.forceCheckBox.sizeHint().width()+10)
        if self.toolbarDefaultWidth == 0:
            self.toolbarDefaultWidth = self.toolbar.sizeHint().width()+2
        if self.toolbarDefaultWidth != 0:
            if self.toolbarDefaultWidth > self.toolbar.width():
                if not self.isToolbarSmall:
                    self.isToolbarSmall = True
                    self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
            else:
                if self.isToolbarSmall:
                    self.isToolbarSmall = False
                    self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.forceCheckBox.setFixedWidth(self.forceCheckBox.sizeHint().width()+10)

class UpdateSoftwareSection(QWidget):

    addProgram = Signal(str, str, str, str, str)
    finishLoading = Signal(str)
    askForScoopInstall = Signal(str)
    setLoadBarValue = Signal(str)
    startAnim = Signal(QVariantAnimation)
    changeBarOrientation = Signal()
    callInMain = Signal(object)
    availableUpdates: int = 0
    discoverLabelDefaultWidth: int = 0
    discoverLabelIsSmall: bool = False
    isToolbarSmall: bool = False
    toolbarDefaultWidth: int = 0
    packages: dict[str:dict] = {}
    
    scoopLoaded = False
    wingetLoaded = False
    chocoLoaded = False

    def __init__(self, parent = None):
        super().__init__(parent = parent)
        
        self.callInMain.connect(lambda f: f())
        self.infobox = globals.infobox
        self.setStyleSheet("margin: 0px;")

        self.programbox = QWidget()
        self.setContentsMargins(0, 0, 0, 0)
        self.programbox.setContentsMargins(0, 0, 0, 0)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.layout)

        self.reloadButton = QPushButton()
        self.reloadButton.setFixedSize(30, 30)
        self.reloadButton.setStyleSheet("margin-top: 0px;")
        self.reloadButton.clicked.connect(self.reload)
        self.reloadButton.setIcon(QIcon(getMedia("reload")))
        self.reloadButton.setAccessibleName(_("Reload"))

        self.searchButton = QPushButton()
        self.searchButton.setFixedSize(30, 30)
        self.searchButton.setStyleSheet("margin-top: 0px;")
        self.searchButton.clicked.connect(self.filter)
        self.searchButton.setIcon(QIcon(getMedia("search")))
        self.searchButton.setAccessibleName(_("Search"))

        hLayout = QHBoxLayout()
        hLayout.setContentsMargins(25, 0, 25, 0)

        self.query = CustomLineEdit()
        self.query.setPlaceholderText(" "+_("Search on available updates"))
        self.query.returnPressed.connect(self.filter)
        self.query.textChanged.connect(lambda: self.filter() if self.forceCheckBox.isChecked() else print())
        self.query.setFixedHeight(30)
        self.query.setStyleSheet("margin-top: 0px;")
        self.query.setMinimumWidth(100)
        self.query.setMaximumWidth(250)
        self.query.setBaseSize(250, 30)

        sct = QShortcut(QKeySequence("Ctrl+F"), self)
        sct.activated.connect(lambda: (self.query.setFocus(), self.query.setSelection(0, len(self.query.text()))))

        sct = QShortcut(QKeySequence("Ctrl+R"), self)
        sct.activated.connect(self.reload)
        
        sct = QShortcut(QKeySequence("F5"), self)
        sct.activated.connect(self.reload)

        sct = QShortcut(QKeySequence("Esc"), self)
        sct.activated.connect(self.query.clear)

        self.forceCheckBox = QCheckBox(_("Instant search"))
        self.forceCheckBox.setFixedHeight(30)
        self.forceCheckBox.setLayoutDirection(Qt.RightToLeft)
        self.forceCheckBox.setFixedWidth(98)
        self.forceCheckBox.setStyleSheet("margin-top: 0px;")
        self.forceCheckBox.setChecked(True)
        self.forceCheckBox.setChecked(not getSettings("DisableInstantSearchOnUpgrade"))
        self.forceCheckBox.clicked.connect(lambda v: setSettings("DisableInstantSearchOnUpgrade", bool(not v)))

        self.img = QLabel()
        self.img.setFixedWidth(80)
        self.img.setPixmap(QIcon(getMedia("checked_laptop")).pixmap(QSize(64, 64)))
        hLayout.addWidget(self.img)

        v = QVBoxLayout()
        v.setSpacing(0)
        v.setContentsMargins(0, 0, 0, 0)
        self.discoverLabel = QLabel(_("Software Updates"))
        self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        v.addWidget(self.discoverLabel)

        self.titleWidget = QWidget()
        self.titleWidget.setContentsMargins(0, 0, 0, 0)
        self.titleWidget.setLayout(v)
        self.titleWidget.setFixedHeight(70)

        hLayout.addWidget(self.titleWidget, stretch=1)
        hLayout.addWidget(self.forceCheckBox)
        hLayout.addWidget(self.query)
        hLayout.addWidget(self.searchButton)
        hLayout.addWidget(self.reloadButton)

        self.packageListScrollBar = CustomScrollBar()
        self.packageListScrollBar.setOrientation(Qt.Vertical)

        self.packageList = TreeWidget("ª")
        self.packageList.setIconSize(QSize(24, 24))
        self.packageList.setColumnCount(6)
        self.packageList.setHeaderLabels(["", _("Package Name"), _("Package ID"), _("Installed Version"), _("New Version"), _("Source")])

        self.packageList.setSortingEnabled(True)
        self.packageList.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.packageList.setVerticalScrollBar(self.packageListScrollBar)
        self.packageList.connectCustomScrollbar(self.packageListScrollBar)
        self.packageList.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.packageList.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        
        sct = QShortcut(Qt.Key.Key_Return, self.packageList)
        sct.activated.connect(lambda: self.filter() if self.query.hasFocus() else self.packageList.itemDoubleClicked.emit(self.packageList.currentItem(), 0))

        self.packageList.itemDoubleClicked.connect(lambda item, column: (self.update(item.text(1), item.text(2), item.text(5), packageItem=item) if not getSettings("DoNotUpdateOnDoubleClick") else self.openInfo(item.text(1), item.text(2), item.text(5), item)))
        
        def showMenu(pos: QPoint):
            if not self.packageList.currentItem():
                return
            if self.packageList.currentItem().isHidden():
                return
            contextMenu = QMenu(self)
            contextMenu.setParent(self)
            contextMenu.setStyleSheet("* {background: red;color: black}")
            ApplyMenuBlur(contextMenu.winId().__int__(), contextMenu)
            inf = QAction(_("Show info"))
            inf.triggered.connect(lambda: self.openInfo(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), self.packageList.currentItem()))
            inf.setIcon(QIcon(getMedia("info")))
            ins1 = QAction(_("Update"))
            ins1.setIcon(QIcon(getMedia("menu_updates")))
            ins1.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem()))
            ins2 = QAction(_("Update as administrator"))
            ins2.setIcon(QIcon(getMedia("runasadmin")))
            ins2.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), admin=True))
            ins3 = QAction(_("Skip hash check"))
            ins3.setIcon(QIcon(getMedia("checksum")))
            ins3.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), skiphash=True))
            ins4 = QAction(_("Interactive update"))
            ins4.setIcon(QIcon(getMedia("interactive")))
            ins4.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), interactive=True))
            ins5 = QAction(_("Uninstall package"))
            ins5.setIcon(QIcon(getMedia("menu_uninstall")))
            ins5.triggered.connect(lambda: globals.uninstall.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5), packageItem=globals.uninstall.packages[self.packageList.currentItem().text(2)]["item"]))
            contextMenu.addAction(ins1)
            contextMenu.addSeparator()
            contextMenu.addAction(ins2)
            if not "scoop" in self.packageList.currentItem().text(5).lower():
                contextMenu.addAction(ins4)
            contextMenu.addAction(ins3)
            contextMenu.addSeparator()
            ins6 = QAction(_("Ignore updates for this package"))
            ins6.setIcon(QIcon(getMedia("blacklist")))
            ins6.triggered.connect(lambda: (setSettingsValue("BlacklistedUpdates", getSettingsValue("BlacklistedUpdates")+self.packageList.currentItem().text(2)+","), self.packageList.currentItem().setHidden(True), self.updatePackageNumber()))
            contextMenu.addAction(ins6)
            contextMenu.addAction(ins5)
            contextMenu.addSeparator()
            contextMenu.addAction(inf)
            contextMenu.exec(QCursor.pos())

        self.packageList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.packageList.customContextMenuRequested.connect(showMenu)

        header = self.packageList.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.packageList.setColumnWidth(0, 10)
        self.packageList.setColumnWidth(3, 130)
        self.packageList.setColumnWidth(4, 130)
        self.packageList.setColumnWidth(5, 150)

        def toggleItemState():
            item = self.packageList.currentItem()
            checked = item.checkState(0) == Qt.CheckState.Checked
            item.setCheckState(0, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

        sct = QShortcut(QKeySequence(Qt.Key_Space), self.packageList)
        sct.activated.connect(toggleItemState)
        
        self.loadingProgressBar = QProgressBar()
        self.loadingProgressBar.setRange(0, 1000)
        self.loadingProgressBar.setValue(0)
        self.loadingProgressBar.setFixedHeight(4)
        self.loadingProgressBar.setTextVisible(False)
        self.loadingProgressBar.setStyleSheet("margin: 0px; margin-left: 15px;margin-right: 15px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        w = QWidget()
        w.setLayout(layout)
        w.setMaximumWidth(1300)

        self.bodyWidget = QWidget()
        l = QHBoxLayout()
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        l.addWidget(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        l.addWidget(self.packageListScrollBar)
        self.bodyWidget.setLayout(l)

        def blacklistSelectedPackages():
            for i in range(self.packageList.topLevelItemCount()):
                program: TreeWidgetItemWithQAction = self.packageList.topLevelItem(i)
                if not program.isHidden():
                    try:
                        if program.checkState(0) ==  Qt.CheckState.Checked:
                            setSettingsValue("BlacklistedUpdates", getSettingsValue("BlacklistedUpdates")+program.text(2)+",")
                            program.setHidden(True)
                    except AttributeError:
                        pass
            self.updatePackageNumber()

        def setAllSelected(checked: bool) -> None:
            itemList = []
            self.packageList.setSortingEnabled(False)
            for i in range(self.packageList.topLevelItemCount()):
                itemList.append(self.packageList.topLevelItem(i))
            for program in itemList:
                if not program.isHidden():
                    program.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.packageList.setSortingEnabled(True)


        self.toolbar = QToolBar(self.window())
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.toolbar.addWidget(TenPxSpacer())
        self.upgradeSelected = QAction(QIcon(getMedia("menu_updates")), "", self.toolbar)
        self.upgradeSelected.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem()))
        self.toolbar.addAction(self.upgradeSelected)
        
        inf = QAction("", self.toolbar)# ("Show info")
        inf.triggered.connect(lambda: self.openInfo(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), self.packageList.currentItem()))
        inf.setIcon(QIcon(getMedia("info")))
        ins2 = QAction("", self.toolbar)# ("Run as administrator")
        ins2.setIcon(QIcon(getMedia("runasadmin")))
        ins2.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), admin=True))
        ins3 = QAction("", self.toolbar)# ("Skip hash check")
        ins3.setIcon(QIcon(getMedia("checksum")))
        ins3.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), skiphash=True))
        ins4 = QAction("", self.toolbar)# ("Interactive update")
        ins4.setIcon(QIcon(getMedia("interactive")))
        ins4.triggered.connect(lambda: self.update(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(5).lower(), packageItem=self.packageList.currentItem(), interactive=True))
        ins5 = QAction("", self.toolbar)
        ins5.setIcon(QIcon(getMedia("share")))
        ins5.triggered.connect(lambda: self.sharePackage(self.packageList.currentItem()))



        for action in [self.upgradeSelected, inf, ins2, ins3, ins4, ins5]:
            self.toolbar.addAction(action)
            self.toolbar.widgetForAction(action).setFixedSize(40, 45)
            
        self.toolbar.addSeparator()

        self.upgradeAllAction = QAction(QIcon(getMedia("installall")), "", self.toolbar)
        self.upgradeAllAction.triggered.connect(lambda: self.updateAll()) # Required for the systray context menu
        self.upgradeSelectedAction = QAction(QIcon(getMedia("list")), _("Update selected"), self.toolbar)
        self.upgradeSelectedAction.triggered.connect(lambda: self.updateSelected())
        self.toolbar.addAction(self.upgradeSelectedAction)

        self.toolbar.addSeparator()

        self.selectAllAction = QAction(QIcon(getMedia("selectall")), "", self.toolbar)
        self.selectAllAction.triggered.connect(lambda: setAllSelected(True))
        self.toolbar.addAction(self.selectAllAction)
        self.toolbar.widgetForAction(self.selectAllAction).setFixedSize(40, 45)
        self.selectNoneAction = QAction(QIcon(getMedia("selectnone")), "", self.toolbar)
        self.selectNoneAction.triggered.connect(lambda: setAllSelected(False))
        self.toolbar.addAction(self.selectNoneAction)
        self.toolbar.widgetForAction(self.selectNoneAction).setFixedSize(40, 45)
        self.toolbar.widgetForAction(self.selectNoneAction).setToolTip(_("Clear selection"))
        self.toolbar.widgetForAction(self.selectAllAction).setToolTip(_("Select all"))

        self.toolbar.addSeparator()

        self.blacklistAction = QAction(QIcon(getMedia("blacklist")), _("Blacklist packages"), self.toolbar)
        self.blacklistAction.triggered.connect(lambda: blacklistSelectedPackages())
        self.toolbar.addAction(self.blacklistAction)
        self.resetBlackList = QAction(QIcon(getMedia("undelete")), _("Reset blacklist"), self.toolbar)
        self.resetBlackList.triggered.connect(lambda: (setSettingsValue("BlacklistedUpdates", ""), self.reload()))
        self.toolbar.addAction(self.resetBlackList)

        self.showUnknownSection = QCheckBox(_("Show unknown versions"))
        self.showUnknownSection.setFixedHeight(30)
        self.showUnknownSection.setLayoutDirection(Qt.RightToLeft)
        self.showUnknownSection.setFixedWidth(190)
        self.showUnknownSection.setStyleSheet("margin-top: 0px;")
        self.showUnknownSection.setChecked(getSettings("ShowUnknownResults"))
        self.showUnknownSection.clicked.connect(lambda v: (setSettings("ShowUnknownResults", bool(v)), updatelist()))
        def updatelist(selff = None):
            if not selff:
                nonlocal self
            else:
                self = selff
            for item in [self.packageList.topLevelItem(i) for i in range(self.packageList.topLevelItemCount())]:
                if item.text(3) == "Unknown":
                    item.setHidden(not self.showUnknownSection.isChecked())
            self.updatePackageNumber()
        self.updatelist = updatelist

        tooltips = {
            self.upgradeSelected: _("Update package"),
            inf: _("Show package info"),
            ins2: _("Update with administrator privileges"),
            ins3: _("Skip the hash check"),
            ins4: _("Interactive update"),
            ins5: _("Share"),
            self.selectAllAction: _("Select all"),
            self.selectNoneAction: _("Clear selection"),
            self.upgradeSelectedAction: _("Update selected"),
            self.resetBlackList: _("Reset blacklist"),
            self.blacklistAction: _("Blacklist packages")
        }
            
        for action in tooltips.keys():
            self.toolbar.widgetForAction(action).setAccessibleName(tooltips[action])
            self.toolbar.widgetForAction(action).setToolTip(tooltips[action])
            
        w = QWidget()
        w.setMinimumWidth(1)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar.addWidget(w)
        self.toolbar.addWidget(self.showUnknownSection)
        self.toolbar.addWidget(TenPxSpacer())
        self.toolbar.addWidget(TenPxSpacer())

        self.countLabel = QLabel(_("Checking for updates..."))
        self.packageList.label.setText(self.countLabel.text())
        self.countLabel.setObjectName("greyLabel")
        layout.addLayout(hLayout)
        layout.addWidget(self.toolbar)
        v.addWidget(self.countLabel)
        layout.addWidget(self.loadingProgressBar)
        layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.countLabel)
        layout.addWidget(self.loadingProgressBar)
        hl2 = QHBoxLayout()
        hl2.addWidget(self.packageList)
        hl2.addWidget(self.packageListScrollBar)
        hl2.setSpacing(0)
        hl2.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(hl2)
        self.programbox.setLayout(l)
        self.layout.addWidget(self.programbox, stretch=1)
        self.infobox.hide()

        self.addProgram.connect(self.addItem)

        self.finishLoading.connect(self.finishLoadingIfNeeded)
        self.infobox.addProgram.connect(self.addInstallation)
        self.setLoadBarValue.connect(self.loadingProgressBar.setValue)
        self.startAnim.connect(lambda anim: anim.start())
        self.changeBarOrientation.connect(lambda: self.loadingProgressBar.setInvertedAppearance(not(self.loadingProgressBar.invertedAppearance())))
        
        self.reloadButton.setEnabled(False)
        self.searchButton.setEnabled(False)
        self.query.setEnabled(False)
        
        self.installIcon = QIcon(getMedia("install"))
        self.IDIcon = QIcon(getMedia("ID"))
        self.versionIcon = QIcon(getMedia("version"))
        self.newVersionIcon = QIcon(getMedia("newversion"))
        self.wingetIcon = QIcon(getMedia("winget"))
        self.scoopIcon = QIcon(getMedia("scoop"))
        self.chocoIcon = QIcon(getMedia("choco"))

        self.blacklist = getSettingsValue("BlacklistedUpdates")
        if not getSettings("DisableWinget"):
            Thread(target=wingetHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.wingetLoaded = True
        if not getSettings("DisableScoop"):
            Thread(target=scoopHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.scoopLoaded = True
        if not getSettings("DisableChocolatey"):
            Thread(target=chocoHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.chocoLoaded = True
        self.finishLoadingIfNeeded("none")
        print("🟢 Upgrades tab loaded")

        g = self.packageList.geometry()
                    
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
        
        self.leftSlow.start()

    def finishLoadingIfNeeded(self, store: str) -> None:
        if(store == "winget"):
            self.countLabel.setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            globals.trayMenuUpdatesList.menuAction().setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            self.wingetLoaded = True
            self.reloadButton.setEnabled(True)
            self.filter()
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        elif(store == "scoop"):
            self.countLabel.setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            globals.trayMenuUpdatesList.menuAction().setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            self.scoopLoaded = True
            self.filter()
            self.reloadButton.setEnabled(True)
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        elif(store == "chocolatey"):
            self.countLabel.setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            globals.trayMenuUpdatesList.menuAction().setText(_("Available updates: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            self.chocoLoaded = True
            self.filter()
            self.reloadButton.setEnabled(True)
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        if(self.wingetLoaded and self.scoopLoaded and self.chocoLoaded):
            self.reloadButton.setEnabled(True)
            self.loadingProgressBar.hide()
            self.loadingProgressBar.hide()
            globals.trayMenuUpdatesList.menuAction().setText(_("Available updates: {0}").format(str(self.packageList.topLevelItemCount())))
            count = 0
            lastVisibleItem = None
            for i in range(self.packageList.topLevelItemCount()):
                if not self.packageList.topLevelItem(i).isHidden():
                    count += 1
                    lastVisibleItem = self.packageList.topLevelItem(i)
            self.packageList.label.setText(str(count))
            if getSettings("AutomaticallyUpdatePackages") or "--updateapps" in sys.argv:
                self.updateAll()
                if not getSettings("DisableUpdatesNotifications"):
                    if count > 1:
                        notify(_("Updates found!"), _("{0} packages are being updated").format(count))
                    elif count == 1:
                        notify(_("Update found!"), _("{0} is being updated").format(lastVisibleItem.text(1)))
            else:
                if not getSettings("DisableUpdatesNotifications"):
                    if count > 1:
                        notify(_("Updates found!"), _("{0} packages can be updated").format(count))
                    elif count == 1:
                        notify(_("Update found!"), _("{0} can be updated").format(lastVisibleItem.text(1)))
            if count > 0:
                globals.trayIcon.setIcon(QIcon(getMedia("greenicon")))
            else:
                globals.trayIcon.setIcon(QIcon(getMedia("greyicon")))
            self.updatePackageNumber()
            self.packageList.label.setText("")
            self.filter()
            self.updatelist()
            if not getSettings("DisableAutoCheckforUpdates"):
                try:
                    waitTime = int(getSettingsValue("UpdatesCheckInterval"))
                except ValueError:
                    print(f"🟡 Can't get custom interval time! (got value was '{getSettingsValue('UpdatesCheckInterval')}')")
                    waitTime = 3600
                Thread(target=lambda: (time.sleep(waitTime), self.reloadSources()), daemon=True, name="AutoCheckForUpdates Thread").start()
            print("🟢 Total packages: "+str(self.packageList.topLevelItemCount()))
            

    def resizeEvent(self, event: QResizeEvent):
        self.adjustWidgetsSize()
        return super().resizeEvent(event)
    
    def changeStore(self, item: TreeWidgetItemWithQAction, store: str, id: str):
        time.sleep(3)
        try:
            store = globals.uninstall.packages[id]["store"]
        except KeyError as e:
            print(f"🟠 Package {id} found in the updates section but not in the installed one, happened again")
        self.callInMain.emit(partial(item.setText, 5, store))

    def addItem(self, name: str, id: str, version: str, newVersion: str, store) -> None:
        if not "---" in name and not name in ("+", "Everything", "Scoop", "At", "The", "But") and not version in ("the", "is"):
            if not id in self.blacklist:
                item = TreeWidgetItemWithQAction()
                item.setText(1, name)
                item.setIcon(1, self.installIcon)
                item.setText(2, id)
                item.setIcon(2, self.IDIcon)
                item.setText(3, version)
                item.setIcon(3, self.versionIcon)
                item.setText(4, newVersion)
                item.setIcon(4, self.newVersionIcon)
                if "scoop" in store.lower():
                    try:
                        if version == globals.uninstall.packages[id]["version"]:
                            store = globals.uninstall.packages[id]["store"]
                        item.setText(5, store)
                    except KeyError as e:
                        item.setText(5, _("Loading..."))
                        print(f"🟡 Package {id} found in the updates section but not in the installed one, might be a temporal issue, retrying in 3 seconds...")
                        Thread(target=self.changeStore, args=(item, store, id)).start()
                else:
                    item.setText(5, store)

                
                self.packages[id] = {
                    "name": name,
                    "version": version,
                    "newVersion": newVersion,
                    "store": store,
                    "item": item,
                }
                if "scoop" in store.lower():
                    item.setIcon(5, self.scoopIcon)
                elif "winget" in store.lower():
                    item.setIcon(5, self.wingetIcon)
                else:
                    item.setIcon(5, self.chocoIcon)
                self.packageList.addTopLevelItem(item)
                item.setCheckState(0, Qt.CheckState.Checked)
                #c = QCheckBox()
                #c.setChecked(True)
                #c.setStyleSheet("margin-top: 1px; margin-left: 8px;")
                #c.stateChanged.connect(lambda: item.setText(0, str(" " if c.isChecked() else "")))
                #self.packageList.setItemWidget(item, 0, c)
                action = QAction(name+"  \t"+version+"\t → \t"+newVersion, globals.trayMenuUpdatesList)
                action.triggered.connect(lambda : self.update(name, id, store, packageItem=item))
                action.setShortcut(version)
                item.setAction(action)
                globals.trayMenuUpdatesList.addAction(action)
            else:
                print(id,"was blackisted")
    
    def filter(self) -> None:
        resultsFound = self.packageList.findItems(self.query.text(), Qt.MatchContains, 1)
        resultsFound += self.packageList.findItems(self.query.text(), Qt.MatchContains, 2)
        print(f"🟢 Searching for string \"{self.query.text()}\"")
        found = 0
        for item in self.packageList.findItems('', Qt.MatchContains, 1):
            if not(item in resultsFound):
                item.setHidden(True)
                #item.treeWidget().itemWidget(item, 0).hide()
            else:
                item.setHidden(False)
                if item.text(3) == "Unknown":
                    item.setHidden(not self.showUnknownSection.isChecked())
                    if self.showUnknownSection.isChecked():
                        found += 1
                else:
                    found += 1
        if found == 0:
            if self.packageList.label.text() == "":
                self.packageList.label.show()
                self.packageList.label.setText(_("No packages found matching the input criteria"))
        else:
            if self.packageList.label.text() == _("No packages found matching the input criteria"):
                self.packageList.label.hide()
                self.packageList.label.setText("")
        self.packageList.scrollToItem(self.packageList.currentItem())

    def updatePackageNumber(self, showQueried: bool = False, foundResults: int = 0):
        self.availableUpdates = 0
        for item in self.packageList.findItems('', Qt.MatchContains, 1):
            if not item.isHidden():
                self.availableUpdates += 1
        self.countLabel.setText(_("Available updates: {0}").format(self.availableUpdates))
        globals.trayIcon.setToolTip(_("WingetUI - Everything is up to date") if self.availableUpdates == 0 else (_("WingetUI - 1 update is available") if self.availableUpdates == 1 else _("WingetUI - {0} updates are available").format(self.availableUpdates)) )
        globals.trayMenuUpdatesList.menuAction().setText(_("No updates are available" if self.availableUpdates == 0 else "Available updates: {0}").format(self.availableUpdates))
        if self.availableUpdates > 0:
            self.packageList.label.hide()
            self.packageList.label.setText("")
            self.img.setPixmap(QIcon(getMedia("alert_laptop")).pixmap(QSize(64, 64)))
            globals.updatesAction.setIcon(QIcon(getMedia("alert_laptop")))
            globals.app.uaAction.setEnabled(True)
            globals.trayMenuUpdatesList.menuAction().setEnabled(True)
            globals.trayIcon.setIcon(QIcon(getMedia("greenicon")))
        else:
            self.packageList.label.setText(_("Hooray! No updates were found!"))
            self.packageList.label.show()
            globals.app.uaAction.setEnabled(False)
            globals.trayMenuUpdatesList.menuAction().setEnabled(False)
            globals.updatesAction.setIcon(QIcon(getMedia("checked_laptop")))
            globals.trayIcon.setIcon(QIcon(getMedia("greyicon")))
            self.img.setPixmap(QIcon(getMedia("checked_laptop")).pixmap(QSize(64, 64)))
    
    def showQuery(self) -> None:
        self.programbox.show()
        self.infobox.hide()

    def updateAll(self) -> None:
        for i in range(self.packageList.topLevelItemCount()):
            program: TreeWidgetItemWithQAction = self.packageList.topLevelItem(i)
            if not program.isHidden():
                self.update(program.text(1), program.text(2), program.text(5), packageItem=program)

    def updateSelected(self) -> None:
            for i in range(self.packageList.topLevelItemCount()):
                program: TreeWidgetItemWithQAction = self.packageList.topLevelItem(i)
                if not program.isHidden():
                    try:
                        if program.checkState(0) ==  Qt.CheckState.Checked:
                           self.update(program.text(1), program.text(2), program.text(5), packageItem=program)
                    except AttributeError:
                        pass
    
    def update(self, title: str, id: str, store: str, all: bool = False, selected: bool = False, packageItem: TreeWidgetItemWithQAction = None, admin: bool = False, skiphash: bool = False, interactive: bool = False) -> None:
            if "winget" == store.lower():
                    self.addInstallation(PackageUpdaterWidget(title, "winget", useId=not("…" in id), packageId=id, packageItem=packageItem, admin=admin, args=list(filter(None, ["--interactive" if interactive else "--silent", "--ignore-security-hash" if skiphash else "", "--force"]))))
            elif "chocolatey" == store.lower():
                self.addInstallation(PackageUpdaterWidget(title, "chocolatey", useId=True, packageId=id, admin=admin, args=list(filter(None, ["--force" if skiphash else "", "--ignore-checksums" if skiphash else "", "--notsilent" if interactive else ""])), packageItem=packageItem))
            else:
                self.addInstallation(PackageUpdaterWidget(title, store,  useId=not("…" in id), packageId=id, packageItem=packageItem, admin=admin, args=["--skip" if skiphash else ""]))
     

    def openInfo(self, title: str, id: str, store: str, packageItem: TreeWidgetItemWithQAction = None) -> None:
        self.infobox.loadProgram(title, id, useId=not("…" in id), store=store, update=True, packageItem=packageItem, version=packageItem.text(4), installedVersion=packageItem.text(3))
        self.infobox.show()

    def reloadSources(self):
        print("Reloading sources...")
        try:
            o1 = subprocess.run(f"powershell -Command scoop update", shell=True, stdout=subprocess.PIPE)
            print("Updated scoop packages with result", o1.returncode)
            o2 = subprocess.run(f"{wingetHelpers.winget} source update --name winget", shell=True, stdout=subprocess.PIPE)
            print("Updated Winget packages with result", o2.returncode)
            o2 = subprocess.run(f"{chocoHelpers.choco} source update --name winget", shell=True, stdout=subprocess.PIPE)

            print(o1.stdout)
            print(o2.stdout)
        except Exception as e:
            report(e)
        self.callInMain.emit(self.reload)
    
    def reload(self) -> None:
        if self.wingetLoaded and self.scoopLoaded and self.chocoLoaded:
            self.availableUpdates = 0
            self.scoopLoaded = False
            self.wingetLoaded = False
            self.chocoLoaded = False
            self.loadingProgressBar.show()
            self.reloadButton.setEnabled(False)
            self.searchButton.setEnabled(False)
            self.query.setEnabled(False)
            self.packageList.clear()
            self.query.setText("")
            for action in globals.trayMenuUpdatesList.actions():
                globals.trayMenuUpdatesList.removeAction(action)
            globals.trayMenuUpdatesList.addAction(globals.updatesHeader)
            self.countLabel.setText(_("Checking for updates..."))
            self.packageList.label.setText(self.countLabel.text())
            self.blacklist = getSettingsValue("BlacklistedUpdates")
            if not getSettings("DisableWinget"):
                Thread(target=wingetHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.wingetLoaded = True
            if not getSettings("DisableScoop"):
                Thread(target=scoopHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.scoopLoaded = True
            if not getSettings("DisableChocolatey"):
                Thread(target=chocoHelpers.searchForUpdates, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.chocoLoaded = True
            self.finishLoadingIfNeeded("none")
    
    def addInstallation(self, p) -> None:
        globals.installersWidget.addItem(p)

    def destroyAnims(self) -> None:
        for anim in (self.leftSlow, self.leftFast, self.rightFast, self.rightSlow):
            anim: QVariantAnimation
            anim.deleteLater()
            anim.stop()
            anim.start(anim.DeleteWhenStopped)
            anim.pause()
            anim.stop()
            anim.valueChanged.disconnect()
            anim.finished.disconnect()

    def adjustWidgetsSize(self) -> None:
        if self.discoverLabelDefaultWidth == 0:
            self.discoverLabelDefaultWidth = self.discoverLabel.sizeHint().width()
        if self.discoverLabelDefaultWidth > self.titleWidget.width():
            if not self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = True
                self.discoverLabel.setStyleSheet(f"font-size: 15pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        else:
            if self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = False
                self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")

        if self.toolbarDefaultWidth == 0:
            self.toolbarDefaultWidth = self.toolbar.sizeHint().width()+10
        if self.toolbarDefaultWidth > self.toolbar.width():
            if not self.isToolbarSmall:
                self.isToolbarSmall = True
                self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        else:
            if self.isToolbarSmall:
                self.isToolbarSmall = False
                self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.forceCheckBox.setFixedWidth(self.forceCheckBox.sizeHint().width()+10)
        self.showUnknownSection.setFixedWidth(self.showUnknownSection.sizeHint().width()+10)


    def showEvent(self, event: QShowEvent) -> None:
        self.adjustWidgetsSize()
        return super().showEvent(event)

    def sharePackage(self, package):
        self.shareUI = ShareUI(self, id=package.text(2), name=package.text(1))


class UninstallSoftwareSection(QWidget):

    addProgram = Signal(str, str, str, str)
    finishLoading = Signal(str)
    callInMain = Signal(object)
    askForScoopInstall = Signal(str)
    setLoadBarValue = Signal(str)
    startAnim = Signal(QVariantAnimation)
    changeBarOrientation = Signal()
    discoverLabelDefaultWidth: int = 0
    discoverLabelIsSmall: bool = False
    isToolbarSmall: bool = False
    toolbarDefaultWidth: int = 0
    packages: dict[str:dict] = {}
    
    wingetLoaded = False
    scoopLoaded =  False
    chocoLoaded = False

    def __init__(self, parent = None):
        super().__init__(parent = parent)
        self.callInMain.connect(lambda f: f())
        self.infobox = globals.infobox
        self.setStyleSheet("margin: 0px;")
        self.infobox.onClose.connect(self.showQuery)
        self.allPkgSelected = False

        self.programbox = QWidget()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(self.layout)

        self.reloadButton = QPushButton()
        self.reloadButton.setFixedSize(30, 30)
        self.reloadButton.setStyleSheet("margin-top: 0px;")
        self.reloadButton.clicked.connect(self.reload)
        self.reloadButton.setIcon(QIcon(getMedia("reload")))
        self.reloadButton.setAccessibleName(_("Reload"))

        self.searchButton = QPushButton()
        self.searchButton.setFixedSize(30, 30)
        self.searchButton.setStyleSheet("margin-top: 0px;")
        self.searchButton.clicked.connect(self.filter)
        self.searchButton.setIcon(QIcon(getMedia("search")))
        self.searchButton.setAccessibleName(_("Search"))

        hLayout = QHBoxLayout()
        hLayout.setContentsMargins(25, 0, 25, 0)

        self.query = CustomLineEdit()
        self.query.setPlaceholderText(" "+_("Search on your software"))
        self.query.returnPressed.connect(self.filter)
        self.query.textChanged.connect(lambda: self.filter() if self.forceCheckBox.isChecked() else print())
        self.query.setFixedHeight(30)
        self.query.setStyleSheet("margin-top: 0px;")
        self.query.setMinimumWidth(100)
        self.query.setMaximumWidth(250)
        self.query.setBaseSize(250, 30)

        sct = QShortcut(QKeySequence("Ctrl+F"), self)
        sct.activated.connect(lambda: (self.query.setFocus(), self.query.setSelection(0, len(self.query.text()))))

        sct = QShortcut(QKeySequence("Ctrl+R"), self)
        sct.activated.connect(self.reload)

        sct = QShortcut(QKeySequence("F5"), self)
        sct.activated.connect(self.reload)

        sct = QShortcut(QKeySequence("Esc"), self)
        sct.activated.connect(self.query.clear)


        self.forceCheckBox = QCheckBox(_("Instant search"))
        self.forceCheckBox.setFixedHeight(30)
        self.forceCheckBox.setLayoutDirection(Qt.RightToLeft)
        self.forceCheckBox.setFixedWidth(98)
        self.forceCheckBox.setStyleSheet("margin-top: 0px;")
        self.forceCheckBox.setChecked(True)
        self.forceCheckBox.setChecked(not getSettings("DisableInstantSearchOnUninstall"))
        self.forceCheckBox.clicked.connect(lambda v: setSettings("DisableInstantSearchOnUninstall", bool(not v)))


        img = QLabel()
        img.setFixedWidth(80)
        img.setPixmap(QIcon(getMedia("workstation")).pixmap(QSize(64, 64)))
        hLayout.addWidget(img)

        v = QVBoxLayout()
        v.setSpacing(0)
        v.setContentsMargins(0, 0, 0, 0)
        self.discoverLabel = QLabel(_("Installed Packages"))
        self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        v.addWidget(self.discoverLabel)

        self.titleWidget = QWidget()
        self.titleWidget.setFixedHeight(70)
        self.titleWidget.setContentsMargins(0, 0, 0, 0)
        self.titleWidget.setLayout(v)

        hLayout.addWidget(self.titleWidget, stretch=1)
        hLayout.addWidget(self.forceCheckBox)
        hLayout.addWidget(self.query)
        hLayout.addWidget(self.searchButton)
        hLayout.addWidget(self.reloadButton)
        
        self.packageListScrollBar = CustomScrollBar()
        self.packageListScrollBar.setOrientation(Qt.Vertical)

        self.packageList = TreeWidget(_("Found 0 Packages"))
        
        sct = QShortcut(Qt.Key.Key_Return, self.packageList)
        sct.activated.connect(lambda: self.filter() if self.query.hasFocus() else self.packageList.itemDoubleClicked.emit(self.packageList.currentItem(), 0))
        
        self.packageList.setIconSize(QSize(24, 24))
        self.headers = ["", _("Package Name"), _("Package ID"), _("Installed Version"), _("Source")] # empty header added for checkbox

        self.packageList.setColumnCount(len(self.headers))
        self.packageList.setHeaderLabels(self.headers)
        self.packageList.setColumnWidth(0, 10)
        self.packageList.setColumnHidden(3, False)
        self.packageList.setColumnWidth(4, 130)
        self.packageList.setSortingEnabled(True)
        self.packageList.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        header = self.packageList.header()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.packageList.sortByColumn(1, Qt.AscendingOrder)
        
        def toggleItemState():
            item = self.packageList.currentItem()
            checked = item.checkState(0) == Qt.CheckState.Checked
            item.setCheckState(0, Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)

        sct = QShortcut(QKeySequence(Qt.Key_Space), self.packageList)
        sct.activated.connect(toggleItemState)

        self.packageList.setVerticalScrollBar(self.packageListScrollBar)
        self.packageList.connectCustomScrollbar(self.packageListScrollBar)
        self.packageList.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.packageList.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        self.packageList.itemDoubleClicked.connect(lambda item, column: self.uninstall(item.text(1), item.text(2), item.text(4), packageItem=item))
        
        def showMenu(pos: QPoint):
            if not self.packageList.currentItem():
                return
            if self.packageList.currentItem().isHidden():
                return
            contextMenu = QMenu(self)
            contextMenu.setParent(self)
            contextMenu.setStyleSheet("* {background: red;color: black}")
            ApplyMenuBlur(contextMenu.winId().__int__(), contextMenu)
            ins1 = QAction(_("Uninstall"))
            ins1.setIcon(QIcon(getMedia("menu_uninstall")))
            ins1.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem()))
            ins2 = QAction(_("Uninstall as administrator"))
            ins2.setIcon(QIcon(getMedia("runasadmin")))
            ins2.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem(), admin=True))
            ins3 = QAction(_("Remove permanent data"))
            ins3.setIcon(QIcon(getMedia("menu_close")))
            ins3.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem(), removeData=True))
            ins5 = QAction(_("Interactive uninstall"))
            ins5.setIcon(QIcon(getMedia("interactive")))
            ins5.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem(), interactive=True))
            ins4 = QAction(_("Show info"))
            ins4.setIcon(QIcon(getMedia("info")))
            ins4.triggered.connect(lambda: self.openInfo(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), self.packageList.currentItem()))
            contextMenu.addAction(ins1)
            contextMenu.addSeparator()
            contextMenu.addAction(ins2)
            if "scoop" in self.packageList.currentItem().text(4).lower():
                contextMenu.addAction(ins3)
                contextMenu.addSeparator()
            else:
                contextMenu.addAction(ins5)
            if self.packageList.currentItem().text(4) not in ((_("Local PC"), "Microsoft Store", "Steam", "GOG", "Ubisoft Connect")):
                contextMenu.addAction(ins4)

            contextMenu.exec(QCursor.pos())

        self.packageList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.packageList.customContextMenuRequested.connect(showMenu)
        
        self.loadingProgressBar = QProgressBar()
        self.loadingProgressBar.setRange(0, 1000)
        self.loadingProgressBar.setValue(0)
        self.loadingProgressBar.setFixedHeight(4)
        self.loadingProgressBar.setTextVisible(False)
        self.loadingProgressBar.setStyleSheet("margin: 0px; margin-left: 15px;margin-right: 15px;")
        
        layout = QVBoxLayout()
        w = QWidget()
        w.setLayout(layout)
        w.setMaximumWidth(1300)

        self.bodyWidget = QWidget()
        l = QHBoxLayout()
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        l.addWidget(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(ScrollWidget(self.packageList), stretch=0)
        self.bodyWidget.setLayout(l)

        self.toolbar = QToolBar(self.window())
        self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.toolbar.addWidget(TenPxSpacer())
        self.upgradeSelected = QAction(QIcon(getMedia("menu_uninstall")), "", self.toolbar)
        self.upgradeSelected.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4).lower(), packageItem=self.packageList.currentItem()))
        self.toolbar.addAction(self.upgradeSelected)
        self.toolbar.widgetForAction(self.upgradeSelected).setFixedSize(40, 45)

        def showInfo():
            item = self.packageList.currentItem()
            if item.text(4) in ((_("Local PC"), "Microsoft Store", "Steam", "GOG", "Ubisoft Connect")):
                self.err = ErrorMessage(self.window())
                errorData = {
                        "titlebarTitle": _("Unable to load informarion"),
                        "mainTitle": _("Unable to load informarion"),
                        "mainText": _("We could not load detailed information about this package, because it was not installed neither from Winget nor Scoop."),
                        "buttonTitle": _("Ok"),
                        "errorDetails": _("Uninstallable packages with the origin listed as \"{0}\" are not published on any package manager, so there's no information available to show about them.").format(item.text(4)),
                        "icon": QIcon(getMedia("notif_warn")),
                    }
                self.err.showErrorMessage(errorData, showNotification=False)
            else:
                self.openInfo(item.text(1), item.text(2), item.text(5).lower(), item)

        inf = QAction("", self.toolbar)# ("Show info")
        inf.triggered.connect(showInfo)
        inf.setIcon(QIcon(getMedia("info")))
        ins2 = QAction("", self.toolbar)# ("Run as administrator")
        ins2.setIcon(QIcon(getMedia("runasadmin")))
        ins2.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), packageItem=self.packageList.currentItem(), admin=True))
        ins5 = QAction("", self.toolbar)# ("Interactive uninstall")
        ins5.setIcon(QIcon(getMedia("interactive")))
        ins5.triggered.connect(lambda: self.uninstall(self.packageList.currentItem().text(1), self.packageList.currentItem().text(2), self.packageList.currentItem().text(4), interactive=True))
        ins6 = QAction("", self.toolbar)
        ins6.setIcon(QIcon(getMedia("share")))
        ins6.triggered.connect(lambda: self.sharePackage(self.packageList.currentItem()))


        for action in [self.upgradeSelected, inf, ins2, ins5, ins6]:
            self.toolbar.addAction(action)
            self.toolbar.widgetForAction(action).setFixedSize(40, 45)

        self.toolbar.addSeparator()

        self.upgradeSelectedAction = QAction(QIcon(getMedia("list")), _("Uninstall selected packages"), self.toolbar)
        self.upgradeSelectedAction.triggered.connect(lambda: self.uninstallSelected())
        self.toolbar.addAction(self.upgradeSelectedAction)

        self.toolbar.addSeparator()

        def setAllSelected(checked: bool) -> None:
            itemList = []
            self.packageList.setSortingEnabled(False)
            for i in range(self.packageList.topLevelItemCount()):
                itemList.append(self.packageList.topLevelItem(i))
            for program in itemList:
                if not program.isHidden():
                    program.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.packageList.setSortingEnabled(True)

        self.selectAllAction = QAction(QIcon(getMedia("selectall")), "", self.toolbar)
        self.selectAllAction.triggered.connect(lambda: setAllSelected(True))
        self.toolbar.addAction(self.selectAllAction)
        self.toolbar.widgetForAction(self.selectAllAction).setFixedSize(40, 45)
        self.selectNoneAction = QAction(QIcon(getMedia("selectnone")), "", self.toolbar)
        self.selectNoneAction.triggered.connect(lambda: setAllSelected(False))
        self.toolbar.addAction(self.selectNoneAction)
        self.toolbar.widgetForAction(self.selectNoneAction).setFixedSize(40, 45)
        self.toolbar.widgetForAction(self.selectNoneAction).setToolTip(_("Clear selection"))
        self.toolbar.widgetForAction(self.selectAllAction).setToolTip(_("Select all"))

        self.toolbar.addSeparator()

        self.exportSelectedAction = QAction(QIcon(getMedia("export")), _("Export selected packages to a file"), self.toolbar)
        self.exportSelectedAction.triggered.connect(lambda: self.exportSelection())
        self.toolbar.addAction(self.exportSelectedAction)

        self.exportAction = QAction(QIcon(getMedia("export")), _("Export all"), self.toolbar)
        self.exportAction.triggered.connect(lambda: self.exportSelection(all=True))
        #self.toolbar.addAction(self.exportAction)

        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.toolbar.addWidget(w)
        self.toolbar.addWidget(TenPxSpacer())
        self.toolbar.addWidget(TenPxSpacer())
         
        tooltips = {
            self.upgradeSelected: _("Uninstall package"),
            inf: _("Show package info"),
            ins2: _("Uninstall with administrator privileges"),
            ins5: _("Interactive uninstall"),
            ins6: _("Share"),
            self.upgradeSelectedAction: _("Uninstall selected packages"),
            self.selectNoneAction: _("Clear selection"),
            self.selectAllAction: _("Select all"),
            self.exportSelectedAction: _("Export selected packages to a file")
        }

        for action in tooltips.keys():
            self.toolbar.widgetForAction(action).setToolTip(tooltips[action])
            self.toolbar.widgetForAction(action).setAccessibleName(tooltips[action])

        self.countLabel = QLabel(_("Searching for installed packages..."))
        self.packageList.label.setText(self.countLabel.text())
        self.countLabel.setObjectName("greyLabel")
        layout.addLayout(hLayout)
        layout.addWidget(self.toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.countLabel)
        layout.addWidget(self.loadingProgressBar)
        hl2 = QHBoxLayout()
        hl2.addWidget(self.packageList)
        hl2.addWidget(self.packageListScrollBar)
        hl2.setSpacing(0)
        hl2.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(hl2)
        self.programbox.setLayout(l)
        self.layout.addWidget(self.programbox, stretch=1)
        self.infobox.hide()

        self.addProgram.connect(self.addItem)

        self.finishLoading.connect(self.finishLoadingIfNeeded)
        self.infobox.addProgram.connect(self.addInstallation)
        self.setLoadBarValue.connect(self.loadingProgressBar.setValue)
        self.startAnim.connect(lambda anim: anim.start())
        self.changeBarOrientation.connect(lambda: self.loadingProgressBar.setInvertedAppearance(not(self.loadingProgressBar.invertedAppearance())))
        

        self.reloadButton.setEnabled(False)
        self.searchButton.setEnabled(False)
        self.query.setEnabled(False)
        
        self.installIcon = QIcon(getMedia("install"))
        self.IDIcon = QIcon(getMedia("ID"))
        self.versionIcon = QIcon(getMedia("version"))
        self.wingetIcon = QIcon(getMedia("winget"))
        self.scoopIcon = QIcon(getMedia("scoop"))
        self.localIcon = QIcon(getMedia("localpc"))
        self.MSStoreIcon = QIcon(getMedia("msstore"))
        self.SteamIcon = QIcon(getMedia("steam"))
        self.GOGIcon = QIcon(getMedia("gog"))
        self.UPLAYIcon = QIcon(getMedia("uplay"))
        self.chocoIcon = QIcon(getMedia("choco"))
        
    
        if not getSettings("DisableWinget"):
            Thread(target=wingetHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.wingetLoaded = True
        if not getSettings("DisableScoop"):
            Thread(target=scoopHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.scoopLoaded = True
        if not getSettings("DisableChocolatey"):
            Thread(target=chocoHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
        else:
            self.chocoLoaded = True

        self.finishLoadingIfNeeded("none")
        print("🟢 Discover tab loaded")

        g = self.packageList.geometry()
            
        
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
        
        self.leftSlow.start()

    def uninstallSelected(self) -> None:
        toUninstall = []
        for i in range(self.packageList.topLevelItemCount()):
            program: TreeWidgetItemWithQAction = self.packageList.topLevelItem(i)
            if not program.isHidden():
                try:
                    if program.checkState(0) ==  Qt.CheckState.Checked:
                        toUninstall.append(program)
                except AttributeError:
                    pass
        a = ErrorMessage(self)
        Thread(target=self.confirmUninstallSelected, args=(toUninstall, a,)).start()
        
    def confirmUninstallSelected(self, toUninstall: list[TreeWidgetItemWithQAction], a: ErrorMessage):
        questionData = {
            "titlebarTitle": "Wait!",
            "mainTitle": _("Are you sure?"),
            "mainText": _("Do you really want to uninstall {0}?").format(toUninstall[0].text(1)) if len(toUninstall) == 1 else  _("Do you really want to uninstall {0} packages?").format(len(toUninstall)),
            "acceptButtonTitle": _("Yes"),
            "cancelButtonTitle": _("No"),
            "icon": QIcon(),
        }
        if a.askQuestion(questionData):
            for program in toUninstall:
                self.callInMain.emit(partial(self.uninstall, program.text(1), program.text(2), program.text(4), packageItem=program, avoidConfirm=True))

    def openInfo(self, title: str, id: str, store: str, packageItem: TreeWidgetItemWithQAction) -> None:
        self.infobox.loadProgram(title, id, useId=not("…" in id), store=store, packageItem=packageItem, version=packageItem.text(3), uninstall=True)
        self.infobox.show()

    def updatePackageNumber(self, showQueried: bool = False, foundResults: int = 0):
        self.foundPackages = 0
        for item in self.packageList.findItems('', Qt.MatchContains, 1):
            self.foundPackages += 1
        self.countLabel.setText(_("{0} packages found").format(self.foundPackages))
        globals.trayMenuInstalledList.menuAction().setText(_("{0} packages were found" if self.foundPackages!=1 else "{0} package was found").format(self.foundPackages))
        if self.foundPackages > 0:
            self.packageList.label.hide()
            self.packageList.label.setText("")
        else:
            self.packageList.label.setText(_("Hooray! No updates were found!"))
            self.packageList.label.show()

    def finishLoadingIfNeeded(self, store: str) -> None:
        if(store == "winget"):
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            globals.trayMenuInstalledList.setTitle(_("{0} packages found").format(str(self.packageList.topLevelItemCount())))
            self.wingetLoaded = True
            self.reloadButton.setEnabled(True)
            self.searchButton.setEnabled(True)
            self.filter()
            self.query.setEnabled(True)
        elif(store == "scoop"):
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            globals.trayMenuInstalledList.setTitle(_("{0} packages found").format(str(self.packageList.topLevelItemCount())))
            self.scoopLoaded = True
            self.reloadButton.setEnabled(True)
            self.filter()
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        elif(store == "chocolatey"):
            self.countLabel.setText(_("Found packages: {0}, not finished yet...").format(str(self.packageList.topLevelItemCount())))
            if self.packageList.topLevelItemCount() == 0:
                self.packageList.label.setText(self.countLabel.text())
            else:
                self.packageList.label.setText("")
            globals.trayMenuInstalledList.setTitle(_("{0} packages found").format(str(self.packageList.topLevelItemCount())))
            self.chocoLoaded = True
            self.reloadButton.setEnabled(True)
            self.filter()
            self.searchButton.setEnabled(True)
            self.query.setEnabled(True)
        if(self.wingetLoaded and self.scoopLoaded and self.chocoLoaded):
            self.reloadButton.setEnabled(True)
            self.filter()
            self.loadingProgressBar.hide()
            globals.trayMenuInstalledList.setTitle(_("{0} packages found").format(str(self.packageList.topLevelItemCount())))
            self.countLabel.setText(_("Found packages: {0}").format(str(self.packageList.topLevelItemCount())))
            self.packageList.label.setText("")
            print("🟢 Total packages: "+str(self.packageList.topLevelItemCount()))

    def adjustWidgetsSize(self) -> None:
        if self.discoverLabelDefaultWidth == 0:
            self.discoverLabelDefaultWidth = self.discoverLabel.sizeHint().width()
        if self.discoverLabelDefaultWidth > self.titleWidget.width():
            if not self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = True
                self.discoverLabel.setStyleSheet(f"font-size: 15pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        else:
            if self.discoverLabelIsSmall:
                self.discoverLabelIsSmall = False
                self.discoverLabel.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")

        if self.toolbarDefaultWidth == 0:
            self.toolbarDefaultWidth = self.toolbar.sizeHint().width()+2
        if self.toolbarDefaultWidth != 0:
            if self.toolbarDefaultWidth > self.toolbar.width():
                if not self.isToolbarSmall:
                    self.isToolbarSmall = True
                    self.toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
            else:
                if self.isToolbarSmall:
                    self.isToolbarSmall = False
                    self.toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.forceCheckBox.setFixedWidth(self.forceCheckBox.sizeHint().width()+10)

    def resizeEvent(self, event: QResizeEvent):
        self.adjustWidgetsSize()
        return super().resizeEvent(event)
        
    def showEvent(self, event: QShowEvent) -> None:
        self.adjustWidgetsSize()
        return super().showEvent(event)


    def addItem(self, name: str, id: str, version: str, store: str) -> None:
        if not "---" in name and not name in ("+", "Everything", "Scoop", "At", "The", "But") and not version in ("the", "is"):
            item = TreeWidgetItemWithQAction()
            if store.lower() == "winget":
                for illegal_char in ("{", "}", " "):
                    if illegal_char in id:
                        store = (_("Local PC"))
                        break
                
                if store.lower() == "winget":
                    if id.count(".") != 1:
                        store = (_("Local PC"))
                        if id.count(".") > 1:
                            for letter in id:
                                if letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                                    store = "Winget"
                                    break
                
                if store == (_("Local PC")):
                    if id == "Steam":
                        store = "Steam"
                    if id == "Uplay":
                        store = "Ubisoft Connect"
                    if id.count("_is1") == 1:
                        store = "GOG"
                        for number in id.split("_is1")[0]:
                            if number not in "0123456789":
                                store = (_("Local PC"))
                                break
                        if len(id) != 14:
                            store = (_("Local PC"))
                        if id.count("GOG") == 1:
                            store = "GOG"
                
                if store.lower() == "winget":
                    if len(id.split("_")[-1]) == 13 and len(id.split("_"))==2:
                        store = "Microsoft Store"
                    elif len(id.split("_")[-1]) <= 13 and len(id.split("_"))==2 and "…" == id.split("_")[-1][-1]: # Delect microsoft store ellipsed packages 
                        store = "Microsoft Store"

            item.setText(1, name)
            item.setText(2, id)
            item.setIcon(1, self.installIcon)
            item.setIcon(2, self.IDIcon)
            item.setIcon(3, self.versionIcon)
            item.setText(3, version)
            if "scoop" in store.lower():
                item.setIcon(4, self.scoopIcon)
            elif "winget" in store.lower():
                item.setIcon(4, self.wingetIcon)
            elif (_("Local PC")) in store:
                item.setIcon(4, self.localIcon)
            elif "steam" in store.lower():
                item.setIcon(4, self.SteamIcon)
            elif "gog" in store.lower():
                item.setIcon(4, self.GOGIcon)
            elif "ubisoft connect" in store.lower():
                item.setIcon(4, self.UPLAYIcon)
            elif "chocolatey" in store.lower():
                item.setIcon(4, self.chocoIcon)
            else:
                item.setIcon(4, self.MSStoreIcon)
            item.setText(4, store)
            self.packages[id] = {
                "name": name,
                "version": version,
                "store": store,
                "item": item,
            }
            #c = QCheckBox()
            #c.setChecked(False)
            #c.setStyleSheet("margin-top: 1px; margin-left: 8px;")
            #c.stateChanged.connect(lambda: item.setText(0, str(" " if c.isChecked() else "")))


            self.packageList.addTopLevelItem(item)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            #self.packageList.setItemWidget(item, 0, c)
            action = QAction(name+" \t"+version, globals.trayMenuInstalledList)
            action.triggered.connect(lambda: (self.uninstall(name, id, store, packageItem=item), print(name, id, store, item)))
            action.setShortcut(version)
            item.setAction(action)
            globals.trayMenuInstalledList.addAction(action)
    
    def filter(self) -> None:
        resultsFound = self.packageList.findItems(self.query.text(), Qt.MatchContains, 1)
        resultsFound += self.packageList.findItems(self.query.text(), Qt.MatchContains, 2)
        print(f"🟢 Searching for string \"{self.query.text()}\"")
        found = 0
        for item in self.packageList.findItems('', Qt.MatchContains, 0):
            if not(item in resultsFound):
                item.setHidden(True)
            else:
                item.setHidden(False)
                found += 1
        if found == 0:
            if self.packageList.label.text() == "":
                self.packageList.label.show()
                self.packageList.label.setText(_("No packages found matching the input criteria"))
        else:
            if self.packageList.label.text() == _("No packages found matching the input criteria"):
                self.packageList.label.hide()
                self.packageList.label.setText("")
        self.packageList.scrollToItem(self.packageList.currentItem())
    
    def showQuery(self) -> None:
        self.programbox.show()
        self.infobox.hide()
                
    def confirmUninstallSelected(self, toUninstall: list[TreeWidgetItemWithQAction], a: ErrorMessage, admin: bool = False, interactive: bool = False, removeData: bool = False):
        questionData = {
            "titlebarTitle": "Wait!",
            "mainTitle": _("Are you sure?"),
            "mainText": _("Do you really want to uninstall {0}?").format(toUninstall[0].text(1)) if len(toUninstall) == 1 else  _("Do you really want to uninstall {0} packages?").format(len(toUninstall)),
            "acceptButtonTitle": _("Yes"),
            "cancelButtonTitle": _("No"),
            "icon": QIcon(),
        }
        if a.askQuestion(questionData):
            for program in toUninstall:
                self.callInMain.emit(partial(self.uninstall, program.text(1), program.text(2), program.text(4), program, admin, interactive, removeData, avoidConfirm=True))


    def uninstall(self, title: str, id: str, store: str, packageItem: TreeWidgetItemWithQAction = None, admin: bool = False, removeData: bool = False, interactive: bool = False, avoidConfirm: bool = False) -> None:
        if not avoidConfirm:
            a = ErrorMessage(self)
            Thread(target=self.confirmUninstallSelected, args=([packageItem], a, admin, interactive, removeData)).start()
        else:
            print("🔵 Uninstalling", id)
            if "winget" == store.lower():
                self.addInstallation(PackageUninstallerWidget(title, "winget", useId=not("…" in id), packageId=id, packageItem=packageItem, admin=admin, removeData=removeData, args=["--interactive" if interactive else "--silent", "--force"]))
            elif "chocolatey" == store.lower():
                self.addInstallation(PackageUninstallerWidget(title, "chocolatey", useId=True, packageId=id, admin=admin, packageItem=packageItem, args=list(filter(None, ["--notsilent" if interactive else ""]))))
            else: # Scoop
                self.addInstallation(PackageUninstallerWidget(title, store, useId=not("…" in id), packageId=id, packageItem=packageItem, admin=admin, removeData=removeData))

    def reload(self) -> None:
        if self.wingetLoaded and self.scoopLoaded and self.chocoLoaded:
            self.scoopLoaded = False
            self.wingetLoaded = False
            self.chocoLoaded = False
            self.loadingProgressBar.show()
            self.reloadButton.setEnabled(False)
            self.searchButton.setEnabled(False)
            self.query.setEnabled(False)
            self.packageList.clear()
            self.query.setText("")
            self.countLabel.setText(_("Searching for installed packages..."))
            self.packageList.label.setText(self.countLabel.text())
            if not getSettings("DisableWinget"):
                Thread(target=wingetHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.wingetLoaded = True
            if not getSettings("DisableScoop"):
                Thread(target=scoopHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.scoopLoaded = True
            if not getSettings("DisableChocolatey"):
                Thread(target=chocoHelpers.searchForInstalledPackage, args=(self.addProgram, self.finishLoading), daemon=True).start()
            else:
                self.chocoLoaded = True
            self.finishLoadingIfNeeded("none")
            for action in globals.trayMenuInstalledList.actions():
                globals.trayMenuInstalledList.removeAction(action)
            globals.trayMenuInstalledList.addAction(globals.installedHeader)
    
    def addInstallation(self, p) -> None:
        globals.installersWidget.addItem(p)

    def selectAllInstalled(self) -> None:
        self.allPkgSelected = not self.allPkgSelected
        for item in [self.packageList.topLevelItem(i) for i in range(self.packageList.topLevelItemCount())]:
            item.setCheckState(Qt.CheckState.Checked if self.allPkgSelected else Qt.CheckState.Unchecked)
    
    def exportSelection(self, all: bool = False) -> None:
        """
        Export all selected packages into a file.

        """
        wingetPackagesList = []
        scoopPackageList = []
        chocoPackageList = []

        try:
            for i in range(self.packageList.topLevelItemCount()):
                item = self.packageList.topLevelItem(i)
                if ((item.checkState(0) ==  Qt.CheckState.Checked or all) and item.text(4).lower() == "winget"):
                    id = item.text(2).strip()
                    wingetPackage = {"PackageIdentifier": id}
                    wingetPackagesList.append(wingetPackage)
                elif ((item.checkState(0) ==  Qt.CheckState.Checked or all) and "scoop" in item.text(4).lower()):
                    scoopPackage = {"Name": item.text(2)}
                    scoopPackageList.append(scoopPackage)
                elif ((item.checkState(0) ==  Qt.CheckState.Checked or all) and item.text(4).lower() == "chocolatey"):
                    chocoPackage = {"Name": item.text(2)}
                    chocoPackageList.append(chocoPackage)

            wingetDetails = {
                "Argument": "https://cdn.winget.microsoft.com/cache",
                "Identifier" : "Microsoft.Winget.Source_8wekyb3d8bbwe",
                "Name": "winget",
                "Type" : "Microsoft.PreIndexed.Package"
            }
            wingetExportSchema = {
                "$schema" : "https://aka.ms/winget-packages.schema.2.0.json",
                "CreationDate" : "2022-08-16T20:55:44.415-00:00", # TODO: get data automatically
                "Sources": [{
                    "Packages": wingetPackagesList,
                    "SourceDetails": wingetDetails}],
                "WinGetVersion" : "1.4.2161-preview" # TODO: get installed winget version
            }
            scoopExportSchema = {
                "apps": scoopPackageList,
            }
            chocoExportSchema = {
                "apps": chocoPackageList,
            }
            overAllSchema = {
                "winget": wingetExportSchema,
                "scoop": scoopExportSchema,
                "chocolatey": chocoExportSchema
            }

            filename = QFileDialog.getSaveFileName(self, _("Save File"), _("wingetui exported packages"), filter='JSON (*.json)')
            if filename[0] != "":
                with open(filename[0], 'w') as f:
                    f.write(json.dumps(overAllSchema, indent=4))

        except Exception as e:
            report(e)

    def destroyAnims(self) -> None:
        for anim in (self.leftSlow, self.leftFast, self.rightFast, self.rightSlow):
            anim: QVariantAnimation
            anim.pause()
            anim.stop()
            anim.valueChanged.disconnect()
            anim.finished.disconnect()
            anim.deleteLater()
            
    def sharePackage(self, package):
        self.shareUI = ShareUI(self, id=package.text(2), name=package.text(1))


class AboutSection(QScrollArea):
    def __init__(self, parent = None):
        super().__init__(parent = parent)
        self.setFrameShape(QFrame.NoFrame)
        self.widget = QWidget()
        self.setWidgetResizable(True)
        self.setStyleSheet("margin-left: 0px;")
        self.layout = QVBoxLayout()
        w = QWidget()
        w.setLayout(self.layout)
        w.setMaximumWidth(1300)
        l = QHBoxLayout()
        l.addSpacing(20)
        l.addStretch()
        l.addWidget(w, stretch=0)
        l.addStretch()
        self.widget.setLayout(l)
        self.setWidget(self.widget)
        self.announcements = QAnnouncements()
        self.layout.addWidget(self.announcements)
        title = QLabel(_("Component Information"))
        title.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        self.layout.addWidget(title)

        self.layout.addSpacing(15)
        try:
            table = QTableWidget()
            table.setAutoFillBackground(True)
            table.setStyleSheet("*{border: 0px solid transparent; background-color: transparent;}QHeaderView{font-size: 13pt;padding: 0px;margin: 0px;}QTableCornerButton::section,QHeaderView,QHeaderView::section,QTableWidget,QWidget,QTableWidget::item{background-color: transparent;border: 0px solid transparent}")
            table.setColumnCount(2)
            table.setRowCount(4)
            table.setEnabled(False)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setShowGrid(False)
            table.setHorizontalHeaderLabels([("" if isDark() else "   ")+_("Status"), _("Version")])
            table.setColumnWidth(1, 500)
            table.setColumnWidth(0, 150)
            table.verticalHeader().setFixedWidth(100)
            table.setVerticalHeaderLabels(["Winget ", "Scoop ", "Chocolatey ", " GSudo "])
            table.setItem(0, 0, QTableWidgetItem("  "+_("Found") if globals.componentStatus["wingetFound"] else _("Not found")))
            table.setItem(0, 1, QTableWidgetItem(" "+str(globals.componentStatus["wingetVersion"])))
            table.setItem(1, 0, QTableWidgetItem("  "+_("Found") if globals.componentStatus["scoopFound"] else _("Not found")))
            table.setItem(1, 1, QTableWidgetItem(" "+str(globals.componentStatus["scoopVersion"])))
            table.setItem(2, 0, QTableWidgetItem("  "+_("Found") if globals.componentStatus["chocoFound"] else _("Not found")))
            table.setItem(2, 1, QTableWidgetItem(" "+str(globals.componentStatus["chocoVersion"])))
            table.setItem(3, 0, QTableWidgetItem("  "+_("Found") if globals.componentStatus["sudoFound"] else _("Not found")))
            table.setItem(3, 1, QTableWidgetItem(" "+str(globals.componentStatus["sudoVersion"])))
            table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignLeft)
            table.setRowHeight(0, 35)
            table.setRowHeight(1, 35)
            table.setRowHeight(2, 35)
            table.setRowHeight(3, 35)
            table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignLeft)
            table.verticalHeaderItem(0).setTextAlignment(Qt.AlignRight)
            table.verticalHeaderItem(1).setTextAlignment(Qt.AlignRight)
            table.verticalHeaderItem(2).setTextAlignment(Qt.AlignRight)
            table.verticalHeaderItem(3).setTextAlignment(Qt.AlignRight)
            table.setCornerWidget(QLabel(""))
            table.setCornerButtonEnabled(False)
            table.setFixedHeight(190)
            table.cornerWidget().setStyleSheet("background: transparent;")
            self.layout.addWidget(table)
            title = QLabel(_("About WingetUI version {0}").format(versionName))
            title.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
            self.layout.addWidget(title)
            self.layout.addSpacing(5)
            description = QLinkLabel(_("The main goal of this project is to create an intuitive UI to manage the most common CLI package managers for Windows, such as Winget and Scoop.")+"\n"+_("This project has no connection with the official {0} project — it's completely unofficial.").format(f"<a style=\"color: {blueColor};\" href=\"https://github.com/microsoft/winget-cli\">Winget</a>"))
            self.layout.addWidget(description)
            self.layout.addSpacing(5)
            self.layout.addWidget(QLinkLabel(f"{_('Homepage')}:   <a style=\"color: {blueColor};\" href=\"https://marticliment.com/wingetui\">https://marticliment.com/wingetui</a>"))
            self.layout.addWidget(QLinkLabel(f"{_('Repository')}:   <a style=\"color: {blueColor};\" href=\"https://github.com/marticliment/wingetui\">https://github.com/marticliment/wingetui</a>"))
            self.layout.addSpacing(30)

            self.layout.addWidget(QLinkLabel(f"{_('Contributors')}:", f"font-size: 22pt;font-family: \"{globals.dispfont}\";font-weight: bold;"))        
            self.layout.addWidget(QLinkLabel(_("WingetUI wouldn't have been possible with the help of our dear contributors. Check out their GitHub profile, WingetUI wouldn't be possible without them!")))
            contributorsHTMLList = "<ul>"
            for contributor in contributorsInfo:
                contributorsHTMLList += f"<li><a style=\"color:{blueColor}\" href=\"{contributor.get('link')}\">{contributor.get('name')}</a></li>"
            contributorsHTMLList += "</ul>"
            self.layout.addWidget(QLinkLabel(contributorsHTMLList))
            self.layout.addSpacing(15)

            self.layout.addWidget(QLinkLabel(f"{_('Translators')}:", f"font-size: 22pt;font-family: \"{globals.dispfont}\";font-weight: bold;"))        
            self.layout.addWidget(QLinkLabel(_("WingetUI has not been machine translated. The following users have been in charge of the translations:")))
            translatorsHTMLList = "<ul>"
            translatorList = []
            translatorData: dict[str, str] = {}
            for key, value in languageCredits.items():
                langName = languageReference[key] if (key in languageReference) else key
                for translator in value:
                    link = translator.get("link")
                    name = translator.get("name")
                    translatorLine = name
                    if (link):
                        translatorLine = f"<a style=\"color:{blueColor}\" href=\"{link}\">{name}</a>"
                    translatorKey = f"{name}{langName}" # for sort
                    translatorList.append(translatorKey)
                    translatorData[translatorKey] = f"{translatorLine} ({langName})"
            translatorList.sort(key=str.casefold)
            for translator in translatorList:
                translatorsHTMLList += f"<li>{translatorData[translator]}</li>"
            translatorsHTMLList += "</ul><br>"
            translatorsHTMLList += _("Do you want to translate WingetUI to your language? See how to contribute <a style=\"color:{0}\" href=\"{1}\"a>HERE!</a>").format(blueColor, "https://github.com/marticliment/WingetUI/wiki#translating-wingetui")
            self.layout.addWidget(QLinkLabel(translatorsHTMLList))
            self.layout.addSpacing(15)
            
            self.layout.addWidget(QLinkLabel(f"{_('About the dev')}:", f"font-size: 22pt;font-family: \"{globals.dispfont}\";font-weight: bold;"))        
            self.layout.addWidget(QLinkLabel(_("Hi, my name is Martí, and i am the <i>developer</i> of WingetUI. WingetUI has been entirely made on my free time!")))
            try:
                self.layout.addWidget(QLinkLabel(_("Check out my {0} and my {1}!").format(f"<a style=\"color:{blueColor}\" href=\"https://github.com/marticliment\">{_('GitHub profile')}</a>", f"<a style=\"color:{blueColor}\" href=\"http://www.marticliment.com\">{_('homepage')}</a>")))
            except Exception as e:
                print(e)
                print(blueColor)
                print(_('homepage'))
                print(_('GitHub profile'))
            self.layout.addWidget(QLinkLabel(_("Do you find WingetUI useful? You'd like to support the developer? If so, you can {0}, it helps a lot!").format(f"<a style=\"color:{blueColor}\" href=\"https://ko-fi.com/martinet101\">{_('buy me a coffee')}</a>")))

            self.layout.addSpacing(15)
            self.layout.addWidget(QLinkLabel(f"{_('Licenses')}:", f"font-size: 22pt;font-family: \"{globals.dispfont}\";font-weight: bold;"))
            self.layout.addWidget(QLabel())
            self.layout.addWidget(QLinkLabel(f"WingetUI:&nbsp;&nbsp;&nbsp;&nbsp;LGPL v2.1:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;<a style=\"color: {blueColor};\" href=\"https://github.com/marticliment/WinGetUI/blob/main/LICENSE\">https://github.com/marticliment/WinGetUI/blob/main/LICENSE</a>"))
            self.layout.addWidget(QLabel())
            self.layout.addWidget(QLinkLabel(f"PySide6:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LGPLv3:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a style=\"color: {blueColor};\" href=\"https://www.gnu.org/licenses/lgpl-3.0.html\">https://www.gnu.org/licenses/lgpl-3.0.html</a>"))
            self.layout.addWidget(QLinkLabel(f"Python3:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_('PSF License')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a style=\"color: {blueColor};\" href=\"https://docs.python.org/3/license.html#psf-license\">https://docs.python.org/3/license.html#psf-license</a>"))
            self.layout.addWidget(QLinkLabel(f"Pywin32:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_('PSF License')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a style=\"color: {blueColor};\" href=\"https://spdx.org/licenses/PSF-2.0.html\">https://spdx.org/licenses/PSF-2.0.html</a>"))
            self.layout.addWidget(QLinkLabel(f"Win23mica:&thinsp;{_('MIT License')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a style=\"color: {blueColor};\" href=\"https://github.com/marticliment/win32mica/blob/main/LICENSE\">https://github.com/marticliment/win32mica/blob/main/LICENSE</a>"))
            self.layout.addWidget(QLinkLabel())
            self.layout.addWidget(QLinkLabel(f"Winget:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{_('MIT License')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<a style=\"color: {blueColor};\" href=\"https://github.com/microsoft/winget-cli/blob/master/LICENSE\">https://github.com/microsoft/winget-cli/blob/master/LICENSE</a>"))
            self.layout.addWidget(QLinkLabel(f"Scoop:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;{_('Unlicense')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;<a style=\"color: {blueColor};\" href=\"https://github.com/lukesampson/scoop/blob/master/LICENSE\">https://github.com/lukesampson/scoop/blob/master/LICENSE</a>"))
            self.layout.addWidget(QLinkLabel(f"Chocolatey:&thinsp;Apache v2:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;<a style=\"color: {blueColor};\" href=\"https://github.com/chocolatey/choco/blob/master/LICENSE\">https://github.com/chocolatey/choco/blob/master/LICENSE</a>"))
            self.layout.addWidget(QLinkLabel(f"GSudo:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;{_('MIT License')}:&thinsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;<a style=\"color: {blueColor};\" href=\"https://github.com/gerardog/gsudo/blob/master/LICENSE.txt\">https://github.com/gerardog/gsudo/blob/master/LICENSE.txt</a>"))
            self.layout.addWidget(QLinkLabel())
            self.layout.addWidget(QLinkLabel(f"{_('Icons')}:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;{_('By Icons8')}:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&thinsp;<a style=\"color: {blueColor};\" href=\"https://icons8.com\">https://icons8.com</a>"))
            self.layout.addWidget(QLinkLabel())
            self.layout.addWidget(QLinkLabel())
            button = QPushButton(_("About Qt6"))
            button.setFixedWidth(710)
            button.setFixedHeight(25)
            button.clicked.connect(lambda: MessageBox.aboutQt(self, _("WingetUI - About Qt6")))
            self.layout.addWidget(button)
            self.layout.addWidget(QLinkLabel())
            self.layout.addStretch()
        except Exception as e:
            self.layout.addWidget(QLabel("An error occurred while loading the about section"))
            self.layout.addWidget(QLabel(str(e)))
            report(e)
        print("🟢 About tab loaded!")
        
    def showEvent(self, event: QShowEvent) -> None:
        Thread(target=self.announcements.loadAnnouncements, daemon=True, name="Settings: Announce loader").start()
        return super().showEvent(event)

class SettingsSection(QScrollArea):
    def __init__(self, parent = None):
        super().__init__(parent = parent)
        self.setFrameShape(QFrame.NoFrame)
        self.widget = QWidget()
        self.setWidgetResizable(True)
        self.setStyleSheet("margin-left: 0px;")
        self.layout = QVBoxLayout()
        w = QWidget()
        w.setLayout(self.layout)
        w.setMaximumWidth(1300)
        l = QHBoxLayout()
        l.addSpacing(20)
        l.addStretch()
        l.addWidget(w, stretch=0)
        l.addStretch()
        self.widget.setLayout(l)
        self.setWidget(self.widget)
        self.announcements = QAnnouncements()
        self.announcements.setMinimumWidth(800)
        self.layout.addWidget(self.announcements)
        title = QLabel(_("WingetUI Settings"))

        title.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        self.layout.addWidget(title)
        self.layout.addSpacing(20)

        self.generalTitle = QSettingsTitle(_("General preferences"), getMedia("settings"), _("Language, theme and other miscellaneous preferences"))
        self.layout.addWidget(self.generalTitle)

        self.language = QSettingsComboBox(_("WingetUI display language:")+" (Language)")
        self.generalTitle.addWidget(self.language)
        self.language.restartButton.setText(_("Restart WingetUI")+" (Restart)")
        self.language.setStyleSheet("QWidget#stBtn{border-bottom-left-radius: 0;border-bottom-right-radius: 0;border-bottom: 0;}")

        langListWithPercentage = []
        langDictWithPercentage = {}
        invertedLangDict = {}
        for key, value in languageReference.items():
            if (key in untranslatedPercentage):
                perc = untranslatedPercentage[key]
                if (perc == "0%"): continue
                if not key in lang["locale"]:
                    langListWithPercentage.append(f"{value} ({perc})")
                    langDictWithPercentage[key] = f"{value} ({perc})"
                    invertedLangDict[f"{value} ({perc})"] = key
                else:
                    k = len(lang.keys())
                    v = len([val for val in lang.values() if val != None])
                    perc = f"{int(v/k*100)}%"
                    langListWithPercentage.append(f"{value} ({perc})")
                    langDictWithPercentage[key] = f"{value} ({perc})"
                    invertedLangDict[f"{value} ({perc})"] = key
            else:
                invertedLangDict[value] = key
                langDictWithPercentage[key] = value
                langListWithPercentage.append(value)
        try:
            self.language.combobox.insertItems(0, langListWithPercentage)
            self.language.combobox.setCurrentIndex(langListWithPercentage.index(langDictWithPercentage[langName]))
        except Exception as e:
            report(e)
            self.language.combobox.insertItems(0, langListWithPercentage)

        def changeLang():
            self.language.restartButton.setVisible(True)
            i = self.language.combobox.currentIndex()
            selectedLang = invertedLangDict[self.language.combobox.currentText()] # list(languageReference.keys())[i]
            cprint(invertedLangDict[self.language.combobox.currentText()])
            self.language.toggleRestartButton(selectedLang != langName)
            setSettingsValue("PreferredLanguage", selectedLang)

        def restartElevenClockByLangChange():
            subprocess.run(str("start /B \"\" \""+sys.executable)+"\"", shell=True)
            globals.app.quit()

        self.language.restartButton.clicked.connect(restartElevenClockByLangChange)
        self.language.combobox.currentTextChanged.connect(changeLang)
        
        updateCheckBox = QSettingsCheckBox(_("Update WingetUI automatically"))
        updateCheckBox.setChecked(not getSettings("DisableAutoUpdateWingetUI"))
        updateCheckBox.stateChanged.connect(lambda v: setSettings("DisableAutoUpdateWingetUI", not bool(v)))
        self.generalTitle.addWidget(updateCheckBox)
        dontUseBuiltInGsudo = QSettingsCheckBox(_("Use installed GSudo instead of the bundled one (requires app restart)"))
        dontUseBuiltInGsudo.setChecked(getSettings("UseUserGSudo"))
        dontUseBuiltInGsudo.stateChanged.connect(lambda v: setSettings("UseUserGSudo", bool(v)))
        self.generalTitle.addWidget(dontUseBuiltInGsudo)
        

        self.theme = QSettingsComboBox(_("Application theme:"))
        self.generalTitle.addWidget(self.theme)
        self.theme.restartButton.setText(_("Restart WingetUI"))
        
        themes = {
            _("Light"): "light",
            _("Dark"): "dark",
            _("Follow system color scheme"): "auto"
        }
        invertedThemes = {
            "light" : _("Light"),
            "dark" : _("Dark"),
            "auto" : _("Follow system color scheme")
        }

        self.theme.combobox.insertItems(0, list(themes.keys()))
        currentValue = getSettingsValue("PreferredTheme")
        try:
            self.theme.combobox.setCurrentText(invertedThemes[currentValue])
        except KeyError:
            self.theme.combobox.setCurrentText(_("Follow system color scheme"))
        except Exception as e:
            report(e)
        
        self.theme.combobox.currentTextChanged.connect(lambda v: (setSettingsValue("PreferredTheme", themes[v]), self.theme.restartButton.setVisible(True)))
        self.theme.restartButton.clicked.connect(restartElevenClockByLangChange)

        self.startup = QSettingsTitle(_("Startup options"), getMedia("launch"), _("WingetUI autostart behaviour, application launch settings"))    
        self.layout.addWidget(self.startup)
        doCloseWingetUI = QSettingsCheckBox(_("Autostart WingetUI in the notifications area"))
        doCloseWingetUI.setChecked(not getSettings("DisableAutostart"))
        doCloseWingetUI.stateChanged.connect(lambda v: setSettings("DisableAutostart", not bool(v)))
        self.startup.addWidget(doCloseWingetUI)
        disableUpdateIndexes = QSettingsCheckBox(_("Do not update package indexes on launch"))
        disableUpdateIndexes.setChecked(getSettings("DisableUpdateIndexes"))
        self.startup.addWidget(disableUpdateIndexes)
        enableScoopCleanup = QSettingsCheckBox(_("Enable Scoop cleanup on launch"))
        disableUpdateIndexes.stateChanged.connect(lambda v: setSettings("DisableUpdateIndexes", bool(v)))
        enableScoopCleanup.setChecked(getSettings("EnableScoopCleanup"))
        enableScoopCleanup.stateChanged.connect(lambda v: setSettings("EnableScoopCleanup", bool(v)))
        enableScoopCleanup.setStyleSheet("QWidget#stChkBg{border-bottom-left-radius: 8px;border-bottom-right-radius: 8px;border-bottom: 1px;}")

        self.startup.addWidget(enableScoopCleanup)
        
        self.UITitle = QSettingsTitle(_("User interface preferences"), getMedia("interactive"), _("Action when double-clicking packages, hide successful installations"))
        self.layout.addWidget(self.UITitle)
        changeDefaultInstallAction = QSettingsCheckBox(_("Directly install when double-clicking an item on the Discover Software tab (instead of showing the package info)"))
        changeDefaultInstallAction.setChecked(getSettings("InstallOnDoubleClick"))
        changeDefaultInstallAction.stateChanged.connect(lambda v: setSettings("InstallOnDoubleClick", bool(v)))
        self.UITitle.addWidget(changeDefaultInstallAction)
        changeDefaultUpdateAction = QSettingsCheckBox(_("Show info about the package on the Updates tab"))
        changeDefaultUpdateAction.setChecked(not getSettings("DoNotUpdateOnDoubleClick"))
        changeDefaultUpdateAction.stateChanged.connect(lambda v: setSettings("DoNotUpdateOnDoubleClick", bool(not v)))
        self.UITitle.addWidget(changeDefaultUpdateAction)
        dontUseBuiltInGsudo = QSettingsCheckBox(_("Remove successful installs/uninstalls/updates from the installation list"))
        dontUseBuiltInGsudo.setChecked(not getSettings("MaintainSuccessfulInstalls"))
        dontUseBuiltInGsudo.stateChanged.connect(lambda v: setSettings("MaintainSuccessfulInstalls", not bool(v)))
        self.UITitle.addWidget(dontUseBuiltInGsudo)
        


        self.trayIcon = QSettingsTitle(_("Notification tray options"), getMedia("systemtray"), _("WingetUI tray application preferences"))
        self.layout.addWidget(self.trayIcon)

        doCloseWingetUI = QSettingsCheckBox(_("Close WingetUI to the notification area"))
        doCloseWingetUI.setChecked(not getSettings("DisablesystemTray"))
        doCloseWingetUI.stateChanged.connect(lambda v: setSettings("DisablesystemTray", not bool(v)))
        self.trayIcon.addWidget(doCloseWingetUI)
        checkForUpdates = QSettingsCheckBox(_("Check for package updates periodically"))
        checkForUpdates.setChecked(not getSettings("DisableAutoCheckforUpdates"))
        self.trayIcon.addWidget(checkForUpdates)

        frequencyCombo = QSettingsComboBox(_("Check for updates every:"), buttonEnabled=False)
        
        times = {
            _("{0} minutes").format(10):   "600",
            _("{0} minutes").format(30):  "1800",
            _("1 hour")                :  "3600",
            _("{0} hours").format(2)   :  "7200",
            _("{0} hours").format(4)   : "14400",
            _("{0} hours").format(8)   : "28800",
            _("{0} hours").format(12)  : "43200",
            _("1 day")                 : "86400",
            _("{0} days").format(2)    :"172800",
            _("{0} days").format(3)    :"259200",
            _("1 week")                :"604800",
        }
        invertedTimes = {
            "600"   : _("{0} minutes").format(10),
            "1800"  : _("{0} minutes").format(30),
            "3600"  : _("1 hour"),
            "7200"  : _("{0} hours").format(2),
            "14400" : _("{0} hours").format(4),
            "28800" : _("{0} hours").format(8),
            "43200" : _("{0} hours").format(12),
            "86400" : _("1 day"),
            "172800": _("{0} days").format(2),
            "259200": _("{0} days").format(3),
            "604800": _("1 week")
        }

        frequencyCombo.setEnabled(checkForUpdates.isChecked())
        checkForUpdates.stateChanged.connect(lambda v: (setSettings("DisableAutoCheckforUpdates", not bool(v)), frequencyCombo.setEnabled(bool(v))))
        frequencyCombo.combobox.insertItems(0, list(times.keys()))
        currentValue = getSettingsValue("UpdatesCheckInterval")
        try:
            frequencyCombo.combobox.setCurrentText(invertedTimes[currentValue])
        except KeyError:
            frequencyCombo.combobox.setCurrentText(_("1 hour"))
        except Exception as e:
            report(e)
        
        frequencyCombo.combobox.currentTextChanged.connect(lambda v: setSettingsValue("UpdatesCheckInterval", times[v]))

        self.trayIcon.addWidget(frequencyCombo)
        frequencyCombo.setStyleSheet("QWidget#stBtn{border-bottom-left-radius: 0px;border-bottom-right-radius:0 ;border-bottom: 0px;}")


        notifyAboutUpdates = QSettingsCheckBox(_("Show a notification when there are available updates"))
        notifyAboutUpdates.setChecked(not getSettings("DisableUpdatesNotifications"))
        notifyAboutUpdates.stateChanged.connect(lambda v: setSettings("DisableUpdatesNotifications", not bool(v)))
        self.trayIcon.addWidget(notifyAboutUpdates)

        automaticallyInstallUpdates = QSettingsCheckBox(_("Update packages automatically"))
        automaticallyInstallUpdates.setChecked(getSettings("AutomaticallyUpdatePackages"))
        automaticallyInstallUpdates.stateChanged.connect(lambda v: setSettings("AutomaticallyUpdatePackages", bool(v)))
        automaticallyInstallUpdates.setStyleSheet("QWidget#stChkBg{border-bottom-left-radius: 8px;border-bottom-right-radius: 8px;border-bottom: 1px;}")
        self.trayIcon.addWidget(automaticallyInstallUpdates)

        self.advancedOptions = QSettingsTitle(_("Experimental settings and developer options"), getMedia("testing"), _("Beta features and other options that shouldn't be touched"))
        self.layout.addWidget(self.advancedOptions)
        disableShareApi = QSettingsCheckBox(_("Disable new share API (port 7058)"))
        disableShareApi.setChecked(getSettings("DisableApi"))
        disableShareApi.stateChanged.connect(lambda v: setSettings("DisableApi", bool(v)))
        self.advancedOptions.addWidget(disableShareApi)

        enableSystemWinget = QSettingsCheckBox(_("Use system Winget (Needs a restart)"))
        enableSystemWinget.setChecked(getSettings("UseSystemWinget"))
        enableSystemWinget.stateChanged.connect(lambda v: setSettings("UseSystemWinget", bool(v)))
        self.advancedOptions.addWidget(enableSystemWinget)
        disableLangUpdates = QSettingsCheckBox(_("Do not download new app translations from GitHub automatically"))
        disableLangUpdates.setChecked(getSettings("DisableLangAutoUpdater"))
        disableLangUpdates.stateChanged.connect(lambda v: setSettings("DisableLangAutoUpdater", bool(v)))
        self.advancedOptions.addWidget(disableLangUpdates)
        resetyWingetUICache = QSettingsButton(_("Reset WingetUI icon and screenshot cache"), _("Reset"))
        resetyWingetUICache.clicked.connect(lambda: (shutil.rmtree(os.path.join(os.path.expanduser("~"), ".wingetui/cachedmeta/")), notify("WingetUI", _("Cache was reset successfully!"))))
        resetyWingetUICache.setStyleSheet("QWidget#stBtn{border-bottom-left-radius: 0px;border-bottom-right-radius: 0px;border-bottom: 0px;}")
        self.advancedOptions.addWidget(resetyWingetUICache)

        def resetWingetUIStore():
            sd = getSettings("DisableScoop")
            wd = getSettings("DisableWinget")
            for file in glob.glob(os.path.join(os.path.expanduser("~"), ".wingetui/*")):
                if not "Running" in file:
                    try:
                        os.remove(file)
                    except:
                        pass
            setSettings("DisableScoop", sd)
            setSettings("DisableWinget", wd)
            restartElevenClockByLangChange()
        
        resetWingetUI = QSettingsButton(_("Reset WingetUI and its preferences"), _("Reset"))
        resetWingetUI.clicked.connect(lambda: resetWingetUIStore())
        self.advancedOptions.addWidget(resetWingetUI)

        title = QLabel(_("Package manager preferences"))
        self.layout.addSpacing(40)
        title.setStyleSheet(f"font-size: 30pt;font-family: \"{globals.dispfont}\";font-weight: bold;")
        self.layout.addWidget(title)
        self.layout.addSpacing(20)

        self.wingetPreferences = QSettingsTitle(_("{pm} preferences").format(pm = "Winget"), getMedia("winget"), _("{pm} package manager specific preferences").format(pm = "Winget"))
        self.layout.addWidget(self.wingetPreferences)
        disableWinget = QSettingsCheckBox(_("Enable {pm}").format(pm = "Winget"))
        disableWinget.setChecked(not getSettings("DisableWinget"))
        disableWinget.stateChanged.connect(lambda v: (setSettings("DisableWinget", not bool(v)), parallelInstalls.setEnabled(v), button.setEnabled(v), enableSystemWinget.setEnabled(v)))
        self.wingetPreferences.addWidget(disableWinget)

        parallelInstalls = QSettingsCheckBox(_("Allow parallel installs (NOT RECOMMENDED)"))
        parallelInstalls.setChecked(getSettings("AllowParallelInstalls"))
        parallelInstalls.stateChanged.connect(lambda v: setSettings("AllowParallelInstalls", bool(v)))
        self.wingetPreferences.addWidget(parallelInstalls)
        button = QSettingsButton(_("Reset Winget sources (might help if no packages are listed)"), _("Reset"))
        button.clicked.connect(lambda: (os.startfile(os.path.join(realpath, "resources/reset_winget_sources.cmd"))))
        self.wingetPreferences.addWidget(button)
        button.setStyleSheet("QWidget#stChkBg{border-bottom-left-radius: 8px;border-bottom-right-radius: 8px;border-bottom: 1px;}")
        
        parallelInstalls.setEnabled(disableWinget.isChecked())
        button.setEnabled(disableWinget.isChecked())
        enableSystemWinget.setEnabled(disableWinget.isChecked())

        
        self.scoopPreferences = QSettingsTitle(_("{pm} preferences").format(pm = "Scoop"), getMedia("scoop"), _("{pm} package manager specific preferences").format(pm = "Scoop"))
        self.layout.addWidget(self.scoopPreferences)

        disableScoop = QSettingsCheckBox(_("Enable {pm}").format(pm = "Scoop"))
        disableScoop.setChecked(not getSettings("DisableScoop"))
        disableScoop.stateChanged.connect(lambda v: (setSettings("DisableScoop", not bool(v)), scoopPreventCaps.setEnabled(v), bucketManager.setEnabled(v), uninstallScoop.setEnabled(v), enableScoopCleanup.setEnabled(v)))
        self.scoopPreferences.addWidget(disableScoop)
        scoopPreventCaps = QSettingsCheckBox(_("Show Scoop packages in lowercase"))
        scoopPreventCaps.setChecked(getSettings("LowercaseScoopApps"))
        scoopPreventCaps.stateChanged.connect(lambda v: setSettings("LowercaseScoopApps", bool(v)))
        self.scoopPreferences.addWidget(scoopPreventCaps)
        bucketManager = ScoopBucketManager()
        bucketManager.setStyleSheet("QWidget#stBtn{border-bottom-left-radius: 0;border-bottom-right-radius: 0;border-bottom: 0;}")
        self.scoopPreferences.addWidget(bucketManager)
        installScoop = QSettingsButton(_("Install Scoop"), _("Install"))
        installScoop.setStyleSheet("QWidget#stBtn{border-bottom-left-radius: 0;border-bottom-right-radius: 0;border-bottom: 0;}")
        installScoop.clicked.connect(lambda: (setSettings("DisableScoop", False), disableScoop.setChecked(False), os.startfile(os.path.join(realpath, "resources/install_scoop.cmd"))))
        self.scoopPreferences.addWidget(installScoop)
        uninstallScoop = QSettingsButton(_("Uninstall Scoop (and its packages)"), _("Uninstall"))
        uninstallScoop.clicked.connect(lambda: (setSettings("DisableScoop", True), disableScoop.setChecked(True), os.startfile(os.path.join(realpath, "resources/uninstall_scoop.cmd"))))
        self.scoopPreferences.addWidget(uninstallScoop)
        
        scoopPreventCaps.setEnabled(disableScoop.isChecked())
        bucketManager.setEnabled(disableScoop.isChecked())
        uninstallScoop.setEnabled(disableScoop.isChecked())
        enableScoopCleanup.setEnabled(disableScoop.isChecked())
        
        self.chocoPreferences = QSettingsTitle(_("{pm} preferences").format(pm = "Chocolatey"), getMedia("choco"), _("{pm} package manager specific preferences").format(pm = "Chocolatey"))
        self.layout.addWidget(self.chocoPreferences)
        disableChocolatey = QSettingsCheckBox(_("Enable {pm}").format(pm = "Chocolatey"))
        disableChocolatey.setChecked(not getSettings("DisableChocolatey"))
        disableChocolatey.stateChanged.connect(lambda v: (setSettings("DisableChocolatey", not bool(v))))
        self.chocoPreferences.addWidget(disableChocolatey)
        enableSystemChocolatey = QSettingsCheckBox(_("Use system Chocolatey (Needs a restart)"))
        enableSystemChocolatey.setChecked(getSettings("UseSystemChocolatey"))
        enableSystemChocolatey.stateChanged.connect(lambda v: setSettings("UseSystemChocolatey", bool(v)))
        self.chocoPreferences.addWidget(enableSystemChocolatey)
        resetChocoCache = QSettingsButton(_("Reset chocolatey cache"), _("Reset"))
        resetChocoCache.clicked.connect(lambda: (os.remove(os.path.join(os.path.expanduser("~"), ".wingetui/cacheddata/chocolateypackages")), notify("WingetUI", _("Cache was reset successfully!"))))
        self.chocoPreferences.addWidget(resetChocoCache)



        
        self.layout.addStretch()


        
        print("🟢 Settings tab loaded!")
        
    def scoopAddExtraBucket(self) -> None:
        r = QInputDialog.getItem(self, _("Scoop bucket manager"), _("Which bucket do you want to add?"), ["main", "extras", "versions", "nirsoft", "php", "nerd-fonts", "nonportable", "java", "games"], 1, editable=False)
        if r[1]:
            print(r[0])
            globals.installersWidget.addItem(PackageInstallerWidget(_("{0} Scoop bucket").format(r[0]), "custom", customCommand=f"{scoopHelpers.scoop} bucket add {r[0]}"))
    
    def scoopRemoveExtraBucket(self) -> None:
        r = QInputDialog.getItem(self, _("Scoop bucket manager"), _("Which bucket do you want to remove?"), ["main", "extras", "versions", "nirsoft", "php", "nerd-fonts", "nonportable", "java", "games"], 1, editable=False)
        if r[1]:
            print(r[0])
            
            globals.installersWidget.addItem(PackageUninstallerWidget(_("{0} Scoop bucket").format(r[0]), "custom", customCommand=f"{scoopHelpers.scoop} bucket rm {r[0]}"))

    def showEvent(self, event: QShowEvent) -> None:
        Thread(target=self.announcements.loadAnnouncements, daemon=True, name="Settings: Announce loader").start()
        return super().showEvent(event)

class DebuggingSection(QWidget):
    def __init__(self):
        super().__init__()
        class QPlainTextEditWithFluentMenu(QPlainTextEdit):
            def __init__(self):
                super().__init__()

            def contextMenuEvent(self, e: QContextMenuEvent) -> None:
                menu = self.createStandardContextMenu()
                menu.addSeparator()

                a = QAction()
                a.setText(_("Reload log"))
                a.triggered.connect(lambda: (print("🔵 Reloading log..."), self.setPlainText(buffer.getvalue()), self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())))
                menu.addAction(a)

                
                a4 = QAction()
                a4.setText(_("Show missing translation strings"))
                a4.triggered.connect(lambda: self.setPlainText('\n'.join(missingTranslationList)))#buffer.getvalue()))
                menu.addAction(a4)


                a2 = QAction()
                a2.setText(_("Export log as a file"))
                a2.triggered.connect(lambda: saveLog())
                menu.addAction(a2)

                a3 = QAction()
                a3.setText(_("Copy log to clipboard"))
                a3.triggered.connect(lambda: copyLog())
                menu.addAction(a3)

                ApplyMenuBlur(menu.winId().__int__(), menu)
                menu.exec(e.globalPos())

        self.setObjectName("background")

        self.setLayout(QVBoxLayout())
        self.setContentsMargins(0, 0, 0, 0)

        self.textEdit = QPlainTextEditWithFluentMenu()
        self.textEdit.setReadOnly(True)
        if isDark():
            self.textEdit.setStyleSheet(f"QPlainTextEdit{{margin: 10px;border-radius: 6px;border: 1px solid #161616;}}")
        else:
            self.textEdit.setStyleSheet(f"QPlainTextEdit{{margin: 10px;border-radius: 6px;border: 1px solid #dddddd;}}")

        self.textEdit.setPlainText(buffer.getvalue())

        reloadButton = QPushButton(_("Reload log"))
        reloadButton.setFixedWidth(200)        
        reloadButton.clicked.connect(lambda: (print("🔵 Reloading log..."), self.textEdit.setPlainText(buffer.getvalue()), self.textEdit.verticalScrollBar().setValue(self.textEdit.verticalScrollBar().maximum())))

        def saveLog():
            try:
                print("🔵 Saving log...")
                f = QFileDialog.getSaveFileName(self, _("Export log"), os.path.expanduser("~"), f"{_('Text file')} (.txt)")
                if f[0]:
                    fpath = f[0]
                    if not ".txt" in fpath.lower():
                        fpath += ".txt"
                    with open(fpath, "wb") as fobj:
                        fobj.write(buffer.getvalue().encode("utf-8"))
                        fobj.close()
                    os.startfile(fpath)
                    print("🟢 log saved successfully")
                    self.textEdit.setPlainText(buffer.getvalue())
                else:
                    print("🟡 log save cancelled!")
                    self.textEdit.setPlainText(buffer.getvalue())
            except Exception as e:
                report(e)
                self.textEdit.setPlainText(buffer.getvalue())

        exportButtom = QPushButton(_("Export log as a file"))
        exportButtom.setFixedWidth(200)
        exportButtom.clicked.connect(lambda: saveLog())

        def copyLog():
            try:
                print("🔵 Copying log to the clipboard...")
                globals.app.clipboard().setText(buffer.getvalue())
                print("🟢 Log copied to the clipboard successfully!")
                self.textEdit.setPlainText(buffer.getvalue())
            except Exception as e:
                report(e)
                self.textEdit.setPlainText(buffer.getvalue())

        copyButton = QPushButton(_("Copy log to clipboard"))
        copyButton.setFixedWidth(200)
        copyButton.clicked.connect(lambda: copyLog())

        hl = QHBoxLayout()
        hl.setSpacing(5)
        hl.setContentsMargins(10, 10, 10, 0)
        hl.addWidget(exportButtom)
        hl.addWidget(copyButton)
        hl.addStretch()
        hl.addWidget(reloadButton)

        self.layout().setSpacing(0)
        self.layout().setContentsMargins(5, 5, 5, 5)
        self.layout().addLayout(hl, stretch=0)
        self.layout().addWidget(self.textEdit, stretch=1)

        self.setAutoFillBackground(True)

    def showEvent(self, event: QShowEvent) -> None:
        self.textEdit.setPlainText(buffer.getvalue())
        return super().showEvent(event)

class ScoopBucketManager(QWidget):
    addBucketsignal = Signal(str, str, str, str)
    finishLoading = Signal()
    setLoadBarValue = Signal(str)
    startAnim = Signal(QVariantAnimation)
    changeBarOrientation = Signal()
    
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_StyledBackground)
        self.setObjectName("stBtn")
        self.addBucketsignal.connect(self.addItem)
        layout = QVBoxLayout()
        hLayout = QHBoxLayout()
        hLayout.addWidget(QLabel(_("Manage scoop buckets")))
        hLayout.addStretch()
        
        self.loadingProgressBar = QProgressBar(self)
        self.loadingProgressBar.setRange(0, 1000)
        self.loadingProgressBar.setValue(0)
        self.loadingProgressBar.setFixedHeight(4)
        self.loadingProgressBar.setTextVisible(False)
        self.loadingProgressBar.hide()
        self.finishLoading.connect(lambda: self.loadingProgressBar.hide())
        self.setLoadBarValue.connect(self.loadingProgressBar.setValue)
        self.startAnim.connect(lambda anim: anim.start())
        self.changeBarOrientation.connect(lambda: self.loadingProgressBar.setInvertedAppearance(not(self.loadingProgressBar.invertedAppearance())))
        
        self.reloadButton = QPushButton()
        self.reloadButton.clicked.connect(self.loadBuckets)
        self.reloadButton.setFixedSize(30, 30)
        self.reloadButton.setIcon(QIcon(getMedia("reload")))
        self.reloadButton.setAccessibleName(_("Reload"))
        self.addBucketButton = QPushButton(_("Add bucket"))
        self.addBucketButton.setFixedHeight(30)
        self.addBucketButton.clicked.connect(self.scoopAddExtraBucket)
        hLayout.addWidget(self.addBucketButton)
        hLayout.addWidget(self.reloadButton)
        hLayout.setContentsMargins(10, 0, 15, 0)
        layout.setContentsMargins(60, 10, 5, 10)
        self.bucketList = TreeWidget()
        self.bucketList.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        if isDark():
            self.bucketList.setStyleSheet("QTreeWidget{border: 1px solid #222222; background-color: rgba(30, 30, 30, 50%); border-radius: 8px; padding: 8px; margin-right: 15px;}")
        else:
            self.bucketList.setStyleSheet("QTreeWidget{border: 1px solid #f5f5f5; background-color: rgba(255, 255, 255, 50%); border-radius: 8px; padding: 8px; margin-right: 15px;}")

        self.bucketList.label.setText(_("Loading buckets..."))
        self.bucketList.label.show()
        self.bucketList.setColumnCount(4)
        self.bucketList.setHeaderLabels([_("Name"), _("Source"), _("Update date"), _("Manifests"), _("Remove")])
        self.bucketList.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.bucketList.setSortingEnabled(True)
        self.bucketList.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        self.bucketList.setIconSize(QSize(24, 24))
        self.bucketList.setColumnWidth(0, 120)
        self.bucketList.setColumnWidth(1, 280)
        self.bucketList.setColumnWidth(2, 120)
        self.bucketList.setColumnWidth(3, 80)
        self.bucketList.setColumnWidth(4, 50)
        layout.addLayout(hLayout)
        layout.addWidget(self.loadingProgressBar)
        layout.addWidget(self.bucketList)
        self.setLayout(layout)
        self.loadBuckets()
        self.bucketIcon = QIcon(getMedia("bucket"))
        
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
        
        self.leftSlow.start()
        
        
    def loadBuckets(self):
        if getSettings("DisableScoop"):
            return
        for i in range(self.bucketList.topLevelItemCount()):
            item = self.bucketList.takeTopLevelItem(0)
            del item
        Thread(target=scoopHelpers.loadBuckets, args=(self.addBucketsignal, self.finishLoading), name="MAIN: Load scoop buckets").start()
        self.loadingProgressBar.show()
        self.bucketList.label.show()
        self.bucketList.label.setText("Loading...")
        
    def addItem(self, name: str, source: str, updatedate: str, manifests: str):
        self.bucketList.label.hide()
        item = QTreeWidgetItem()
        item.setText(0, name)
        item.setToolTip(0, name)
        item.setIcon(0, self.bucketIcon)
        item.setText(1, source)
        item.setToolTip(1, source)
        item.setText(2, updatedate)
        item.setToolTip(2, updatedate)
        item.setText(3, manifests)
        item.setToolTip(3, manifests)
        self.bucketList.addTopLevelItem(item)
        btn = QPushButton()
        btn.clicked.connect(lambda: (self.scoopRemoveExtraBucket(name), self.bucketList.takeTopLevelItem(self.bucketList.indexOfTopLevelItem(item))))
        btn.setFixedSize(24, 24)
        btn.setIcon(QIcon(getMedia("menu_uninstall")))
        self.bucketList.setItemWidget(item, 4, btn)
        
    def scoopAddExtraBucket(self) -> None:
        r = QInputDialog.getItem(self, _("Scoop bucket manager"), _("Which bucket do you want to add?"), ["main", "extras", "versions", "nirsoft", "php", "nerd-fonts", "nonportable", "java", "games"], 1, editable=False)
        if r[1]:
            print(r[0])
            p = PackageInstallerWidget(f"{r[0]} Scoop bucket", "custom", customCommand=f"scoop bucket add {r[0]}")
            globals.installersWidget.addItem(p)
            p.finishInstallation.connect(self.loadBuckets)
            
    def scoopRemoveExtraBucket(self, bucket: str) -> None:
        globals.installersWidget.addItem(PackageUninstallerWidget(f"{bucket} Scoop bucket", "custom", customCommand=f"scoop bucket rm {bucket}"))


if __name__ == "__main__":
    import __init__
