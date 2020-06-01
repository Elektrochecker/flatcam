# ###########################################################
# FlatCAM: 2D Post-processing for Manufacturing             #
# http://flatcam.org                                        #
# Author: Juan Pablo Caram (c)                              #
# Date: 2/5/2014                                            #
# MIT Licence                                               #
# ###########################################################

import urllib.request
import urllib.parse
import urllib.error

import getopt
import random
import simplejson as json
import lzma
import shutil
from datetime import datetime
import time
import ctypes
import traceback

from PyQt5.QtCore import pyqtSlot, Qt
from shapely.geometry import Point, MultiPolygon
from io import StringIO

from reportlab.graphics import renderPDF
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, mm
from reportlab.lib.pagesizes import landscape, portrait
from svglib.svglib import svg2rlg

import gc

from xml.dom.minidom import parseString as parse_xml_string

from multiprocessing.connection import Listener, Client
from multiprocessing import Pool
import socket

# ####################################################################################################################
# ###################################      Imports part of FlatCAM       #############################################
# ####################################################################################################################

# Diverse
from FlatCAMCommon import LoudDict, color_variant, ExclusionAreas
from FlatCAMBookmark import BookmarkManager
from FlatCAMDB import ToolsDB2

from vispy.gloo.util import _screenshot
from vispy.io import write_png

# FlatCAM Objects
from defaults import FlatCAMDefaults
from flatcamGUI.preferences.OptionsGroupUI import OptionsGroupUI
from flatcamGUI.preferences.PreferencesUIManager import PreferencesUIManager
from flatcamObjects.ObjectCollection import *
from flatcamObjects.FlatCAMObj import FlatCAMObj
from flatcamObjects.FlatCAMCNCJob import CNCJobObject
from flatcamObjects.FlatCAMDocument import DocumentObject
from flatcamObjects.FlatCAMExcellon import ExcellonObject
from flatcamObjects.FlatCAMGeometry import GeometryObject
from flatcamObjects.FlatCAMGerber import GerberObject
from flatcamObjects.FlatCAMScript import ScriptObject

# FlatCAM Parsing files
from flatcamParsers.ParseExcellon import Excellon
from flatcamParsers.ParseGerber import Gerber
from camlib import to_dict, dict2obj, ET, ParseError, Geometry, CNCjob

# FlatCAM GUI
from flatcamGUI.PlotCanvas import *
from flatcamGUI.PlotCanvasLegacy import *
from flatcamGUI.FlatCAMGUI import *
from flatcamGUI.GUIElements import FCFileSaveDialog

# FlatCAM Pre-processors
from FlatCAMPostProc import load_preprocessors

# FlatCAM Editors
from flatcamEditors.FlatCAMGeoEditor import FlatCAMGeoEditor
from flatcamEditors.FlatCAMExcEditor import FlatCAMExcEditor
from flatcamEditors.FlatCAMGrbEditor import FlatCAMGrbEditor
from flatcamEditors.FlatCAMTextEditor import TextEditor
from flatcamParsers.ParseHPGL2 import HPGL2

# FlatCAM Workers
from FlatCAMProcess import *
from FlatCAMWorkerStack import WorkerStack

# FlatCAM Tools
from flatcamTools import *

# FlatCAM Translation
import gettext
import FlatCAMTranslation as fcTranslate
import builtins

if sys.platform == 'win32':
    import winreg
    from win32comext.shell import shell, shellcon

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext


class App(QtCore.QObject):
    """
    The main application class. The constructor starts the GUI.
    """

    # ###############################################################################################################
    # ########################################## App ################################################################
    # ###############################################################################################################

    # ###############################################################################################################
    # ######################################### LOGGING #############################################################
    # ###############################################################################################################
    log = logging.getLogger('base')
    log.setLevel(logging.DEBUG)
    # log.setLevel(logging.WARNING)
    formatter = logging.Formatter('[%(levelname)s][%(threadName)s] %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    log.addHandler(handler)

    # ###############################################################################################################
    # #################################### Get Cmd Line Options #####################################################
    # ###############################################################################################################
    cmd_line_shellfile = ''
    cmd_line_shellvar = ''
    cmd_line_headless = None

    cmd_line_help = "FlatCam.py --shellfile=<cmd_line_shellfile>\n" \
                    "FlatCam.py --shellvar=<1,'C:\\path',23>\n" \
                    "FlatCam.py --headless=1"
    try:
        # Multiprocessing pool will spawn additional processes with 'multiprocessing-fork' flag
        cmd_line_options, args = getopt.getopt(sys.argv[1:], "h:", ["shellfile=",
                                                                    "shellvar=",
                                                                    "headless=",
                                                                    "multiprocessing-fork="])
    except getopt.GetoptError:
        print(cmd_line_help)
        sys.exit(2)

    for opt, arg in cmd_line_options:
        if opt == '-h':
            print(cmd_line_help)
            sys.exit()
        elif opt == '--shellfile':
            cmd_line_shellfile = arg
        elif opt == '--shellvar':
            cmd_line_shellvar = arg
        elif opt == '--headless':
            try:
                cmd_line_headless = eval(arg)
            except NameError:
                pass

    # ###############################################################################################################
    # ################################### Version and VERSION DATE ##################################################
    # ###############################################################################################################
    version = 8.993
    version_date = "2020/08/01"
    beta = True

    engine = '3D'

    # current date now
    date = str(datetime.today()).rpartition('.')[0]
    date = ''.join(c for c in date if c not in ':-')
    date = date.replace(' ', '_')

    # ###############################################################################################################
    # ############################################ URLS's ###########################################################
    # ###############################################################################################################
    # URL for update checks and statistics
    version_url = "http://flatcam.org/version"

    # App URL
    app_url = "http://flatcam.org"

    # Manual URL
    manual_url = "http://flatcam.org/manual/index.html"
    video_url = "https://www.youtube.com/playlist?list=PLVvP2SYRpx-AQgNlfoxw93tXUXon7G94_"
    gerber_spec_url = "https://www.ucamco.com/files/downloads/file/81/The_Gerber_File_Format_specification." \
                      "pdf?7ac957791daba2cdf4c2c913f67a43da"
    excellon_spec_url = "https://www.ucamco.com/files/downloads/file/305/the_xnc_file_format_specification.pdf"
    bug_report_url = "https://bitbucket.org/jpcgt/flatcam/issues?status=new&status=open"

    # this variable will hold the project status
    # if True it will mean that the project was modified and not saved
    should_we_save = False

    # flag is True if saving action has been triggered
    save_in_progress = False

    # ###############################################################################################################
    # #######################################    APP Signals   ######################################################
    # ###############################################################################################################

    # Inform the user
    # Handled by:
    #  * App.info() --> Print on the status bar
    inform = QtCore.pyqtSignal(str)

    app_quit = QtCore.pyqtSignal()

    # General purpose background task
    worker_task = QtCore.pyqtSignal(dict)

    # File opened
    # Handled by:
    #  * register_folder()
    #  * register_recent()
    # Note: Setting the parameters to unicode does not seem
    #       to have an effect. Then are received as Qstring
    #       anyway.

    # File type and filename
    file_opened = QtCore.pyqtSignal(str, str)
    # File type and filename
    file_saved = QtCore.pyqtSignal(str, str)

    # Percentage of progress
    progress = QtCore.pyqtSignal(int)

    plots_updated = QtCore.pyqtSignal()

    # Emitted by new_object() and passes the new object as argument, plot flag.
    # on_object_created() adds the object to the collection, plots on appropriate flag
    # and emits new_object_available.
    object_created = QtCore.pyqtSignal(object, bool, bool)

    # Emitted when a object has been changed (like scaled, mirrored)
    object_changed = QtCore.pyqtSignal(object)

    # Emitted after object has been plotted.
    # Calls 'on_zoom_fit' method to fit object in scene view in main thread to prevent drawing glitches.
    object_plotted = QtCore.pyqtSignal(object)

    # Emitted when a new object has been added or deleted from/to the collection
    object_status_changed = QtCore.pyqtSignal(object, str, str)

    message = QtCore.pyqtSignal(str, str, str)

    # Emmited when shell command is finished(one command only)
    shell_command_finished = QtCore.pyqtSignal(object)

    # Emitted when multiprocess pool has been recreated
    pool_recreated = QtCore.pyqtSignal(object)

    # Emitted when an unhandled exception happens
    # in the worker task.
    thread_exception = QtCore.pyqtSignal(object)

    # used to signal that there are arguments for the app
    args_at_startup = QtCore.pyqtSignal(list)

    # a reusable signal to replot a list of objects
    # should be disconnected after use so it can be reused
    replot_signal = pyqtSignal(list)

    # signal emitted when jumping
    jump_signal = pyqtSignal(tuple)

    # signal emitted when jumping
    locate_signal = pyqtSignal(tuple, str)

    # close app signal
    close_app_signal = pyqtSignal()

    # will perform the cleanup operation after a Graceful Exit
    # usefull for the NCC Tool and Paint Tool where some progressive plotting might leave
    # graphic residues behind
    cleanup = pyqtSignal()

    def __init__(self, user_defaults=True):
        """
        Starts the application.

        :return: app
        :rtype: App
        """

        super().__init__()

        App.log.info("FlatCAM Starting...")

        self.main_thread = QtWidgets.QApplication.instance().thread()

        # ############################################################################################################
        # ################# Setup the listening thread for another instance launching with args ######################
        # ############################################################################################################
        if sys.platform == 'win32' or sys.platform == 'linux':
            # make sure the thread is stored by using a self. otherwise it's garbage collected
            self.th = QtCore.QThread()
            self.th.start(priority=QtCore.QThread.LowestPriority)

            self.new_launch = ArgsThread()
            self.new_launch.open_signal[list].connect(self.on_startup_args)
            self.new_launch.moveToThread(self.th)
            self.new_launch.start.emit()

        # ############################################################################################################
        # # ######################################## OS-specific #####################################################
        # ############################################################################################################
        portable = False

        # Folder for user settings.
        if sys.platform == 'win32':
            if platform.architecture()[0] == '32bit':
                App.log.debug("Win32!")
            else:
                App.log.debug("Win64!")

            # #######################################################################################################
            # ####### CONFIG FILE WITH PARAMETERS REGARDING PORTABILITY #############################################
            # #######################################################################################################
            config_file = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\config\\configuration.txt'
            try:
                with open(config_file, 'r'):
                    pass
            except FileNotFoundError:
                config_file = os.path.dirname(os.path.realpath(__file__)) + '\\config\\configuration.txt'

            try:
                with open(config_file, 'r') as f:
                    try:
                        for line in f:
                            param = str(line).replace('\n', '').rpartition('=')

                            if param[0] == 'portable':
                                try:
                                    portable = eval(param[2])
                                except NameError:
                                    portable = False
                            if param[0] == 'headless':
                                if param[2].lower() == 'true':
                                    self.cmd_line_headless = 1
                                else:
                                    self.cmd_line_headless = None
                    except Exception as e:
                        log.debug('App.__init__() -->%s' % str(e))
                        return
            except FileNotFoundError as e:
                log.debug(str(e))
                pass

            if portable is False:
                self.data_path = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, None, 0) + '\\FlatCAM'
            else:
                self.data_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\config'

            self.os = 'windows'
        else:  # Linux/Unix/MacOS
            self.data_path = os.path.expanduser('~') + '/.FlatCAM'
            self.os = 'unix'

        # ############################################################################################################
        # ################################# Setup folders and files ##################################################
        # ############################################################################################################

        if not os.path.exists(self.data_path):
            os.makedirs(self.data_path)
            App.log.debug('Created data folder: ' + self.data_path)
            os.makedirs(os.path.join(self.data_path, 'preprocessors'))
            App.log.debug('Created data preprocessors folder: ' + os.path.join(self.data_path, 'preprocessors'))

        self.preprocessorpaths = os.path.join(self.data_path, 'preprocessors')
        if not os.path.exists(self.preprocessorpaths):
            os.makedirs(self.preprocessorpaths)
            App.log.debug('Created preprocessors folder: ' + self.preprocessorpaths)

        # create geo_tools_db.FlatDB file if there is none
        try:
            f = open(self.data_path + '/geo_tools_db.FlatDB')
            f.close()
        except IOError:
            App.log.debug('Creating empty geo_tool_db.FlatDB')
            f = open(self.data_path + '/geo_tools_db.FlatDB', 'w')
            json.dump({}, f)
            f.close()

        # create current_defaults.FlatConfig file if there is none
        try:
            f = open(self.data_path + '/current_defaults.FlatConfig')
            f.close()
        except IOError:
            App.log.debug('Creating empty current_defaults.FlatConfig')
            f = open(self.data_path + '/current_defaults.FlatConfig', 'w')
            json.dump({}, f)
            f.close()

        # Write factory_defaults.FlatConfig file to disk
        FlatCAMDefaults.save_factory_defaults(os.path.join(self.data_path, "factory_defaults.FlatConfig"))

        # create a recent files json file if there is none
        try:
            f = open(self.data_path + '/recent.json')
            f.close()
        except IOError:
            App.log.debug('Creating empty recent.json')
            f = open(self.data_path + '/recent.json', 'w')
            json.dump([], f)
            f.close()

        # create a recent projects json file if there is none
        try:
            fp = open(self.data_path + '/recent_projects.json')
            fp.close()
        except IOError:
            App.log.debug('Creating empty recent_projects.json')
            fp = open(self.data_path + '/recent_projects.json', 'w')
            json.dump([], fp)
            fp.close()

        # Application directory. CHDIR to it. Otherwise, trying to load
        # GUI icons will fail as their path is relative.
        # This will fail under cx_freeze ...
        self.app_home = os.path.dirname(os.path.realpath(__file__))

        App.log.debug("Application path is " + self.app_home)
        App.log.debug("Started in " + os.getcwd())

        # cx_freeze workaround
        if os.path.isfile(self.app_home):
            self.app_home = os.path.dirname(self.app_home)

        os.chdir(self.app_home)

        # ############################################################################################################
        # ################################# DEFAULTS - PREFERENCES STORAGE ###########################################
        # ############################################################################################################
        self.defaults = FlatCAMDefaults()

        self.defaults["root_folder_path"] = self.app_home

        current_defaults_path = os.path.join(self.data_path, "current_defaults.FlatConfig")
        if user_defaults:
            self.defaults.load(filename=current_defaults_path)

        if self.defaults['units'] == 'MM':
            self.decimals = int(self.defaults['decimals_metric'])
        else:
            self.decimals = int(self.defaults['decimals_inch'])

        if self.defaults["global_gray_icons"] is False:
            self.resource_location = 'assets/resources'
        else:
            self.resource_location = 'assets/resources/dark_resources'

        self.current_units = self.defaults['units']



        # ###########################################################################################################
        # #################################### SETUP OBJECT CLASSES #################################################
        # ###########################################################################################################
        self.setup_obj_classes()

        # ###########################################################################################################
        # ###################################### CREATE MULTIPROCESSING POOL #######################################
        # ###########################################################################################################
        self.pool = Pool()

        # ###########################################################################################################
        # ###################################### Setting the Splash Screen ##########################################
        # ###########################################################################################################

        splash_settings = QSettings("Open Source", "FlatCAM")
        if splash_settings.contains("splash_screen"):
            show_splash = splash_settings.value("splash_screen")
        else:
            splash_settings.setValue('splash_screen', 1)

            # This will write the setting to the platform specific storage.
            del splash_settings
            show_splash = 1

        if show_splash and self.cmd_line_headless != 1:
            splash_pix = QtGui.QPixmap(self.resource_location + '/splash.png')
            self.splash = QtWidgets.QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
            # self.splash.setMask(splash_pix.mask())

            # move splashscreen to the current monitor
            desktop = QtWidgets.QApplication.desktop()
            screen = desktop.screenNumber(QtGui.QCursor.pos())
            current_screen_center = desktop.availableGeometry(screen).center()
            self.splash.move(current_screen_center - self.splash.rect().center())

            self.splash.show()
            self.splash.showMessage(_("FlatCAM is initializing ..."),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))
        else:
            show_splash = 0

        # ###########################################################################################################
        # ######################################### Initialize GUI ##################################################
        # ###########################################################################################################

        # FlatCAM colors used in plotting
        self.FC_light_green = '#BBF268BF'
        self.FC_dark_green = '#006E20BF'
        self.FC_light_blue = '#a5a5ffbf'
        self.FC_dark_blue = '#0000ffbf'

        self.ui = FlatCAMGUI(self)

        theme_settings = QtCore.QSettings("Open Source", "FlatCAM")
        if theme_settings.contains("theme"):
            theme = theme_settings.value('theme', type=str)
        else:
            theme = 'white'

        if self.defaults["global_cursor_color_enabled"]:
            self.cursor_color_3D = self.defaults["global_cursor_color"]
        else:
            if theme == 'white':
                self.cursor_color_3D = 'black'
            else:
                self.cursor_color_3D = 'gray'

        # update the defaults dict with the setting in QSetting
        self.defaults['global_theme'] = theme

        self.ui.geom_update[int, int, int, int, int].connect(self.save_geometry)
        self.ui.final_save.connect(self.final_save)

        # restore the toolbar view
        self.restore_toolbar_view()

        # restore the GUI geometry
        self.restore_main_win_geom()

        # set FlatCAM units in the Status bar
        self.set_screen_units(self.defaults['units'])

        # ###########################################################################################################
        # ########################################### AUTOSAVE SETUP ################################################
        # ###########################################################################################################

        self.block_autosave = False
        self.autosave_timer = QtCore.QTimer(self)
        self.save_project_auto_update()
        self.autosave_timer.timeout.connect(self.save_project_auto)

        # ###########################################################################################################
        # #################################### LOAD PREPROCESSORS ###################################################
        # ###########################################################################################################

        # ----------------------------------------- WARNING --------------------------------------------------------
        # Preprocessors need to be loaded before the Preferences Manager builds the Preferences
        # That's because the number of preprocessors can vary and here the comboboxes are populated
        # -----------------------------------------------------------------------------------------------------------

        # a dictionary that have as keys the name of the preprocessor files and the value is the class from
        # the preprocessor file
        self.preprocessors = load_preprocessors(self)

        # make sure that always the 'default' preprocessor is the first item in the dictionary
        if 'default' in self.preprocessors.keys():
            new_ppp_dict = {}

            # add the 'default' name first in the dict after removing from the preprocessor's dictionary
            default_pp = self.preprocessors.pop('default')
            new_ppp_dict['default'] = default_pp

            # then add the rest of the keys
            for name, val_class in self.preprocessors.items():
                new_ppp_dict[name] = val_class

            # and now put back the ordered dict with 'default' key first
            self.preprocessors = new_ppp_dict

        for name in list(self.preprocessors.keys()):
            # 'Paste' preprocessors are to be used only in the Solder Paste Dispensing Tool
            if name.partition('_')[0] == 'Paste':
                self.ui.tools_defaults_form.tools_solderpaste_group.pp_combo.addItem(name)
                continue

            self.ui.geometry_defaults_form.geometry_opt_group.pp_geometry_name_cb.addItem(name)
            # HPGL preprocessor is only for Geometry objects therefore it should not be in the Excellon Preferences
            if name == 'hpgl':
                continue

            self.ui.excellon_defaults_form.excellon_opt_group.pp_excellon_name_cb.addItem(name)

        # ###########################################################################################################
        # ##################################### UPDATE PREFERENCES GUI FORMS ########################################
        # ###########################################################################################################

        self.preferencesUiManager = PreferencesUIManager(defaults=self.defaults, data_path=self.data_path, ui=self.ui,
                                                         inform=self.inform)
        self.preferencesUiManager.defaults_write_form()

        # When the self.defaults dictionary changes will update the Preferences GUI forms
        self.defaults.set_change_callback(self.on_defaults_dict_change)

        # ###########################################################################################################
        # ##################################### FIRST RUN SECTION ###################################################
        # ################################ It's done only once after install   #####################################
        # ###########################################################################################################
        if self.defaults["first_run"] is True:
            # ONLY AT FIRST STARTUP INIT THE GUI LAYOUT TO 'minimal'
            initial_lay = 'minimal'
            layout_field = self.preferencesUiManager.get_form_field("layout")
            layout_field.setCurrentIndex(layout_field.findText(initial_lay))
            self.ui.set_layout(initial_lay)

            # after the first run, this object should be False
            self.defaults["first_run"] = False
            self.preferencesUiManager.save_defaults(silent=True)

        # ###########################################################################################################
        # ############################################ Data #########################################################
        # ###########################################################################################################

        self.recent = []
        self.recent_projects = []

        self.clipboard = QtWidgets.QApplication.clipboard()

        self.project_filename = None
        self.toggle_units_ignore = False

        # ###########################################################################################################
        # ########################################## LOAD LANGUAGES  ################################################
        # ###########################################################################################################

        self.languages = fcTranslate.load_languages()
        language_field = self.preferencesUiManager.get_form_field("global_language")
        for name in sorted(self.languages.values()):
            language_field.addItem(name)

        # ###########################################################################################################
        # ####################################### APPLY APP LANGUAGE ################################################
        # ###########################################################################################################

        ret_val = fcTranslate.apply_language('strings')

        if ret_val == "no language":
            self.inform.emit('[ERROR] %s' % _("Could not find the Language files. The App strings are missing."))
            log.debug("Could not find the Language files. The App strings are missing.")
        else:
            # make the current language the current selection on the language combobox
            self.preferencesUiManager.get_form_field("global_language").setCurrentText(ret_val)
            log.debug("App.__init__() --> Applied %s language." % str(ret_val).capitalize())

        # ###########################################################################################################
        # ###################################### CREATE UNIQUE SERIAL NUMBER ########################################
        # ###########################################################################################################

        chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
        if self.defaults['global_serial'] == 0 or len(str(self.defaults['global_serial'])) < 10:
            self.defaults['global_serial'] = ''.join([random.choice(chars) for __ in range(20)])
            self.preferencesUiManager.save_defaults(silent=True, first_time=True)

        self.defaults.propagate_defaults()

        # ###########################################################################################################
        # ######################################## UPDATE THE OPTIONS ###############################################
        # ###########################################################################################################

        self.options = LoudDict()
        # -----------------------------------------------------------------------------------------------------------
        #   Update the self.options from the self.defaults
        #   The self.defaults holds the application defaults while the self.options holds the object defaults
        # -----------------------------------------------------------------------------------------------------------
        # Copy app defaults to project options
        for def_key, def_val in self.defaults.items():
            self.options[def_key] = deepcopy(def_val)

        self.preferencesUiManager.show_preferences_gui()

        # ### End of Data ####

        # ###########################################################################################################
        # #################################### SETUP OBJECT COLLECTION ##############################################
        # ###########################################################################################################

        self.collection = ObjectCollection(self)
        self.ui.project_tab_layout.addWidget(self.collection.view)

        # ### Adjust tabs width ## ##
        # self.collection.view.setMinimumWidth(self.ui.options_scroll_area.widget().sizeHint().width() +
        #     self.ui.options_scroll_area.verticalScrollBar().sizeHint().width())
        self.collection.view.setMinimumWidth(290)
        self.log.debug("Finished creating Object Collection.")

        # ###########################################################################################################
        # ######################################## SETUP Plot Area ##################################################
        # ###########################################################################################################

        # determine if the Legacy Graphic Engine is to be used or the OpenGL one
        if self.defaults["global_graphic_engine"] == '3D':
            self.is_legacy = False
        else:
            self.is_legacy = True

        # Event signals disconnect id holders
        self.mp = None
        self.mm = None
        self.mr = None
        self.mdc = None
        self.mp_zc = None
        self.kp = None

        # Matplotlib axis
        self.axes = None

        if show_splash:
            self.splash.showMessage(_("FlatCAM is initializing ...\n"
                                      "Canvas initialization started."),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))
        start_plot_time = time.time()  # debug
        self.plotcanvas = None

        self.app_cursor = None
        self.hover_shapes = None

        self.log.debug("Setting up canvas: %s" % str(self.defaults["global_graphic_engine"]))

        # setup the PlotCanvas
        self.on_plotcanvas_setup()

        end_plot_time = time.time()
        self.used_time = end_plot_time - start_plot_time
        self.log.debug("Finished Canvas initialization in %s seconds." % str(self.used_time))

        if show_splash:
            self.splash.showMessage('%s: %ssec' % (_("FlatCAM is initializing ...\n"
                                                     "Canvas initialization started.\n"
                                                     "Canvas initialization finished in"), '%.2f' % self.used_time),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))
        self.ui.splitter.setStretchFactor(1, 2)

        # ###########################################################################################################
        # ############################################### SYS TRAY ##################################################
        # ###########################################################################################################
        if self.defaults["global_systray_icon"]:
            self.parent_w = QtWidgets.QWidget()

            if self.cmd_line_headless == 1:
                self.trayIcon = FlatCAMSystemTray(app=self,
                                                  icon=QtGui.QIcon(self.resource_location +
                                                                   '/flatcam_icon32_green.png'),
                                                  headless=True,
                                                  parent=self.parent_w)
            else:
                self.trayIcon = FlatCAMSystemTray(app=self,
                                                  icon=QtGui.QIcon(self.resource_location +
                                                                   '/flatcam_icon32_green.png'),
                                                  parent=self.parent_w)

        # ###########################################################################################################
        # ############################################### Worker SETUP ##############################################
        # ###########################################################################################################
        if self.defaults["global_worker_number"]:
            self.workers = WorkerStack(workers_number=int(self.defaults["global_worker_number"]))
        else:
            self.workers = WorkerStack(workers_number=2)
        self.worker_task.connect(self.workers.add_task)
        self.log.debug("Finished creating Workers crew.")

        # ###########################################################################################################
        # ############################################# Activity Monitor ###########################################
        # ###########################################################################################################
        self.activity_view = FlatCAMActivityView(app=self)
        self.ui.infobar.addWidget(self.activity_view)
        self.proc_container = FCVisibleProcessContainer(self.activity_view)

        # ###########################################################################################################
        # ############################################# Signal handling #############################################
        # ###########################################################################################################

        # ########################################## Custom signals  ################################################
        # signal for displaying messages in status bar
        self.inform.connect(self.info)
        # signal to be called when the app is quiting
        self.app_quit.connect(self.quit_application, type=Qt.QueuedConnection)
        self.message.connect(self.message_dialog)
        # self.progress.connect(self.set_progress_bar)

        # signals that are emitted when object state changes
        self.object_created.connect(self.on_object_created)
        self.object_changed.connect(self.on_object_changed)
        self.object_plotted.connect(self.on_object_plotted)
        self.plots_updated.connect(self.on_plots_updated)

        # signals emitted when file state change
        self.file_opened.connect(self.register_recent)
        self.file_opened.connect(lambda kind, filename: self.register_folder(filename))
        self.file_saved.connect(lambda kind, filename: self.register_save_folder(filename))

        # ########################################## Standard signals ###############################################
        # ### Menu
        self.ui.menufilenewproject.triggered.connect(self.on_file_new_click)
        self.ui.menufilenewgeo.triggered.connect(self.new_geometry_object)
        self.ui.menufilenewgrb.triggered.connect(self.new_gerber_object)
        self.ui.menufilenewexc.triggered.connect(self.new_excellon_object)
        self.ui.menufilenewdoc.triggered.connect(self.new_document_object)

        self.ui.menufileopengerber.triggered.connect(self.on_fileopengerber)
        self.ui.menufileopenexcellon.triggered.connect(self.on_fileopenexcellon)
        self.ui.menufileopengcode.triggered.connect(self.on_fileopengcode)
        self.ui.menufileopenproject.triggered.connect(self.on_file_openproject)
        self.ui.menufileopenconfig.triggered.connect(self.on_file_openconfig)

        self.ui.menufilenewscript.triggered.connect(self.on_filenewscript)
        self.ui.menufileopenscript.triggered.connect(self.on_fileopenscript)
        self.ui.menufileopenscriptexample.triggered.connect(self.on_fileopenscript_example)

        self.ui.menufilerunscript.triggered.connect(self.on_filerunscript)

        self.ui.menufileimportsvg.triggered.connect(lambda: self.on_file_importsvg("geometry"))
        self.ui.menufileimportsvg_as_gerber.triggered.connect(lambda: self.on_file_importsvg("gerber"))

        self.ui.menufileimportdxf.triggered.connect(lambda: self.on_file_importdxf("geometry"))
        self.ui.menufileimportdxf_as_gerber.triggered.connect(lambda: self.on_file_importdxf("gerber"))
        self.ui.menufileimport_hpgl2_as_geo.triggered.connect(self.on_fileopenhpgl2)
        self.ui.menufileexportsvg.triggered.connect(self.on_file_exportsvg)
        self.ui.menufileexportpng.triggered.connect(self.on_file_exportpng)
        self.ui.menufileexportexcellon.triggered.connect(self.on_file_exportexcellon)
        self.ui.menufileexportgerber.triggered.connect(self.on_file_exportgerber)

        self.ui.menufileexportdxf.triggered.connect(self.on_file_exportdxf)

        self.ui.menufile_print.triggered.connect(lambda: self.on_file_save_objects_pdf(use_thread=True))

        self.ui.menufilesaveproject.triggered.connect(self.on_file_saveproject)
        self.ui.menufilesaveprojectas.triggered.connect(self.on_file_saveprojectas)
        # self.ui.menufilesaveprojectcopy.triggered.connect(lambda: self.on_file_saveprojectas(make_copy=True))
        self.ui.menufilesavedefaults.triggered.connect(self.on_file_savedefaults)

        self.ui.menufileexportpref.triggered.connect(self.on_export_preferences)
        self.ui.menufileimportpref.triggered.connect(self.on_import_preferences)

        self.ui.menufile_exit.triggered.connect(self.final_save)

        self.ui.menueditedit.triggered.connect(lambda: self.object2editor())
        self.ui.menueditok.triggered.connect(lambda: self.editor2object())

        self.ui.menuedit_convertjoin.triggered.connect(self.on_edit_join)
        self.ui.menuedit_convertjoinexc.triggered.connect(self.on_edit_join_exc)
        self.ui.menuedit_convertjoingrb.triggered.connect(self.on_edit_join_grb)

        self.ui.menuedit_convert_sg2mg.triggered.connect(self.on_convert_singlegeo_to_multigeo)
        self.ui.menuedit_convert_mg2sg.triggered.connect(self.on_convert_multigeo_to_singlegeo)

        self.ui.menueditdelete.triggered.connect(self.on_delete)

        self.ui.menueditcopyobject.triggered.connect(self.on_copy_command)
        self.ui.menueditconvert_any2geo.triggered.connect(self.convert_any2geo)
        self.ui.menueditconvert_any2gerber.triggered.connect(self.convert_any2gerber)

        self.ui.menueditorigin.triggered.connect(self.on_set_origin)
        self.ui.menuedit_move2origin.triggered.connect(self.on_move2origin)

        self.ui.menueditjump.triggered.connect(self.on_jump_to)
        self.ui.menueditlocate.triggered.connect(lambda: self.on_locate(obj=self.collection.get_active()))

        self.ui.menuedittoggleunits.triggered.connect(self.on_toggle_units_click)
        self.ui.menueditselectall.triggered.connect(self.on_selectall)
        self.ui.menueditpreferences.triggered.connect(self.on_preferences)

        # self.ui.menuoptions_transfer_a2o.triggered.connect(self.on_options_app2object)
        # self.ui.menuoptions_transfer_a2p.triggered.connect(self.on_options_app2project)
        # self.ui.menuoptions_transfer_o2a.triggered.connect(self.on_options_object2app)
        # self.ui.menuoptions_transfer_p2a.triggered.connect(self.on_options_project2app)
        # self.ui.menuoptions_transfer_o2p.triggered.connect(self.on_options_object2project)
        # self.ui.menuoptions_transfer_p2o.triggered.connect(self.on_options_project2object)

        self.ui.menuoptions_transform_rotate.triggered.connect(self.on_rotate)

        self.ui.menuoptions_transform_skewx.triggered.connect(self.on_skewx)
        self.ui.menuoptions_transform_skewy.triggered.connect(self.on_skewy)

        self.ui.menuoptions_transform_flipx.triggered.connect(self.on_flipx)
        self.ui.menuoptions_transform_flipy.triggered.connect(self.on_flipy)
        self.ui.menuoptions_view_source.triggered.connect(self.on_view_source)
        self.ui.menuoptions_tools_db.triggered.connect(lambda: self.on_tools_database(source='app'))

        self.ui.menuviewdisableall.triggered.connect(self.disable_all_plots)
        self.ui.menuviewdisableother.triggered.connect(self.disable_other_plots)
        self.ui.menuviewenable.triggered.connect(self.enable_all_plots)

        self.ui.menuview_zoom_fit.triggered.connect(self.on_zoom_fit)
        self.ui.menuview_zoom_in.triggered.connect(self.on_zoom_in)
        self.ui.menuview_zoom_out.triggered.connect(self.on_zoom_out)
        self.ui.menuview_replot.triggered.connect(self.plot_all)

        self.ui.menuview_toggle_code_editor.triggered.connect(self.on_toggle_code_editor)
        self.ui.menuview_toggle_fscreen.triggered.connect(self.on_fullscreen)
        self.ui.menuview_toggle_parea.triggered.connect(self.on_toggle_plotarea)
        self.ui.menuview_toggle_notebook.triggered.connect(self.on_toggle_notebook)
        self.ui.menu_toggle_nb.triggered.connect(self.on_toggle_notebook)
        self.ui.menuview_toggle_grid.triggered.connect(self.on_toggle_grid)
        self.ui.menuview_toggle_grid_lines.triggered.connect(self.on_toggle_grid_lines)
        self.ui.menuview_toggle_axis.triggered.connect(self.on_toggle_axis)
        self.ui.menuview_toggle_workspace.triggered.connect(self.on_workspace_toggle)

        self.ui.menutoolshell.triggered.connect(self.toggle_shell)

        self.ui.menuhelp_about.triggered.connect(self.on_about)
        self.ui.menuhelp_manual.triggered.connect(lambda: webbrowser.open(self.manual_url))
        self.ui.menuhelp_report_bug.triggered.connect(lambda: webbrowser.open(self.bug_report_url))
        self.ui.menuhelp_exc_spec.triggered.connect(lambda: webbrowser.open(self.excellon_spec_url))
        self.ui.menuhelp_gerber_spec.triggered.connect(lambda: webbrowser.open(self.gerber_spec_url))
        self.ui.menuhelp_videohelp.triggered.connect(lambda: webbrowser.open(self.video_url))
        self.ui.menuhelp_shortcut_list.triggered.connect(self.on_shortcut_list)

        self.ui.menuprojectenable.triggered.connect(self.on_enable_sel_plots)
        self.ui.menuprojectdisable.triggered.connect(self.on_disable_sel_plots)
        self.ui.menuprojectgeneratecnc.triggered.connect(lambda: self.generate_cnc_job(self.collection.get_selected()))
        self.ui.menuprojectviewsource.triggered.connect(self.on_view_source)

        self.ui.menuprojectcopy.triggered.connect(self.on_copy_command)
        self.ui.menuprojectedit.triggered.connect(self.object2editor)

        self.ui.menuprojectdelete.triggered.connect(self.on_delete)
        self.ui.menuprojectsave.triggered.connect(self.on_project_context_save)
        self.ui.menuprojectproperties.triggered.connect(self.obj_properties)

        # ToolBar signals
        self.connect_toolbar_signals()

        # Notebook and Plot Tab Area signals
        # make the right click on the notebook tab and plot tab area tab raise a menu
        self.ui.notebook.tabBar.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.ui.plot_tab_area.tabBar.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.on_tab_setup_context_menu()
        # activate initial state
        self.on_tab_rmb_click(self.defaults["global_tabs_detachable"])

        # Context Menu
        self.ui.popmenu_disable.triggered.connect(lambda: self.toggle_plots(self.collection.get_selected()))
        self.ui.popmenu_panel_toggle.triggered.connect(self.on_toggle_notebook)

        self.ui.popmenu_new_geo.triggered.connect(self.new_geometry_object)
        self.ui.popmenu_new_grb.triggered.connect(self.new_gerber_object)
        self.ui.popmenu_new_exc.triggered.connect(self.new_excellon_object)
        self.ui.popmenu_new_prj.triggered.connect(self.on_file_new)

        self.ui.zoomfit.triggered.connect(self.on_zoom_fit)
        self.ui.clearplot.triggered.connect(self.clear_plots)
        self.ui.replot.triggered.connect(self.plot_all)

        self.ui.popmenu_copy.triggered.connect(self.on_copy_command)
        self.ui.popmenu_delete.triggered.connect(self.on_delete)
        self.ui.popmenu_edit.triggered.connect(self.object2editor)
        self.ui.popmenu_save.triggered.connect(lambda: self.editor2object())
        self.ui.popmenu_move.triggered.connect(self.obj_move)

        self.ui.popmenu_properties.triggered.connect(self.obj_properties)

        # Project Context Menu -> Color Setting
        for act in self.ui.menuprojectcolor.actions():
            act.triggered.connect(self.on_set_color_action_triggered)

        # ###########################################################################################################
        # #################################### GUI PREFERENCES SIGNALS ##############################################
        # ###########################################################################################################

        self.preferencesUiManager.get_form_field("units").activated_custom.connect(
            lambda: self.on_toggle_units(no_pref=False))

        # ##################################### Workspace Setting Signals ###########################################


        self.preferencesUiManager.get_form_field("global_workspaceT").currentIndexChanged.connect(
            self.on_workspace_modified)
        self.preferencesUiManager.get_form_field("global_workspace_orientation").activated_custom.connect(
            self.on_workspace_modified
        )
        self.preferencesUiManager.get_form_field("global_workspace").stateChanged.connect(self.on_workspace)


        # ###########################################################################################################
        # ######################################## GUI SETTINGS SIGNALS #############################################
        # ###########################################################################################################
        self.preferencesUiManager.get_form_field("global_graphic_engine").activated_custom.connect(self.on_app_restart)
        self.preferencesUiManager.get_form_field("global_cursor_type").activated_custom.connect(self.on_cursor_type)

        # ######################################## Tools related signals ############################################
        # Film Tool
        self.ui.tools_defaults_form.tools_film_group.film_color_entry.editingFinished.connect(
            self.on_film_color_entry)
        self.ui.tools_defaults_form.tools_film_group.film_color_button.clicked.connect(
            self.on_film_color_button)

        # QRCode Tool
        self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_entry.editingFinished.connect(
            self.on_qrcode_fill_color_entry)
        self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_button.clicked.connect(
            self.on_qrcode_fill_color_button)
        self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_entry.editingFinished.connect(
            self.on_qrcode_back_color_entry)
        self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_button.clicked.connect(
            self.on_qrcode_back_color_button)

        # portability changed signal
        self.preferencesUiManager.get_form_field("global_portable").stateChanged.connect(self.on_portable_checked)

        # Object list
        self.collection.view.activated.connect(self.on_row_activated)
        self.collection.item_selected.connect(self.on_row_selected)

        self.object_status_changed.connect(self.on_collection_updated)

        # when there are arguments at application startup this get launched
        self.args_at_startup[list].connect(self.on_startup_args)

        # ###########################################################################################################
        # ####################################### FILE ASSOCIATIONS SIGNALS #########################################
        # ###########################################################################################################

        self.ui.util_defaults_form.fa_excellon_group.restore_btn.clicked.connect(
            lambda: self.restore_extensions(ext_type='excellon'))
        self.ui.util_defaults_form.fa_gcode_group.restore_btn.clicked.connect(
            lambda: self.restore_extensions(ext_type='gcode'))
        self.ui.util_defaults_form.fa_gerber_group.restore_btn.clicked.connect(
            lambda: self.restore_extensions(ext_type='gerber'))

        self.ui.util_defaults_form.fa_excellon_group.del_all_btn.clicked.connect(
            lambda: self.delete_all_extensions(ext_type='excellon'))
        self.ui.util_defaults_form.fa_gcode_group.del_all_btn.clicked.connect(
            lambda: self.delete_all_extensions(ext_type='gcode'))
        self.ui.util_defaults_form.fa_gerber_group.del_all_btn.clicked.connect(
            lambda: self.delete_all_extensions(ext_type='gerber'))

        self.ui.util_defaults_form.fa_excellon_group.add_btn.clicked.connect(
            lambda: self.add_extension(ext_type='excellon'))
        self.ui.util_defaults_form.fa_gcode_group.add_btn.clicked.connect(
            lambda: self.add_extension(ext_type='gcode'))
        self.ui.util_defaults_form.fa_gerber_group.add_btn.clicked.connect(
            lambda: self.add_extension(ext_type='gerber'))

        self.ui.util_defaults_form.fa_excellon_group.del_btn.clicked.connect(
            lambda: self.del_extension(ext_type='excellon'))
        self.ui.util_defaults_form.fa_gcode_group.del_btn.clicked.connect(
            lambda: self.del_extension(ext_type='gcode'))
        self.ui.util_defaults_form.fa_gerber_group.del_btn.clicked.connect(
            lambda: self.del_extension(ext_type='gerber'))

        # connect the 'Apply' buttons from the Preferences/File Associations
        self.ui.util_defaults_form.fa_excellon_group.exc_list_btn.clicked.connect(
            lambda: self.on_register_files(obj_type='excellon'))
        self.ui.util_defaults_form.fa_gcode_group.gco_list_btn.clicked.connect(
            lambda: self.on_register_files(obj_type='gcode'))
        self.ui.util_defaults_form.fa_gerber_group.grb_list_btn.clicked.connect(
            lambda: self.on_register_files(obj_type='gerber'))

        # ###########################################################################################################
        # ########################################### KEYWORDS SIGNALS ##############################################
        # ###########################################################################################################
        self.ui.util_defaults_form.kw_group.restore_btn.clicked.connect(
            lambda: self.restore_extensions(ext_type='keyword'))
        self.ui.util_defaults_form.kw_group.del_all_btn.clicked.connect(
            lambda: self.delete_all_extensions(ext_type='keyword'))
        self.ui.util_defaults_form.kw_group.add_btn.clicked.connect(
            lambda: self.add_extension(ext_type='keyword'))
        self.ui.util_defaults_form.kw_group.del_btn.clicked.connect(
            lambda: self.del_extension(ext_type='keyword'))

        # connect the abort_all_tasks related slots to the related signals
        self.proc_container.idle_flag.connect(self.app_is_idle)

        # signal emitted when a tab is closed in the Plot Area
        self.ui.plot_tab_area.tab_closed_signal.connect(self.on_plot_area_tab_closed)

        # signal to close the application
        self.close_app_signal.connect(self.kill_app)
        # ################################# FINISHED CONNECTING SIGNALS #############################################
        # ###########################################################################################################
        # ###########################################################################################################
        # ###########################################################################################################

        self.log.debug("Finished connecting Signals.")

        # ###########################################################################################################
        # ########################################## Other setups ###################################################
        # ###########################################################################################################

        # to use for tools like Distance tool who depends on the event sources who are changed inside the Editors
        # depending on from where those tools are called different actions can be done
        self.call_source = 'app'

        # this is a flag to signal to other tools that the ui tooltab is locked and not accessible
        self.tool_tab_locked = False

        # decide if to show or hide the Notebook side of the screen at startup
        if self.defaults["global_project_at_startup"] is True:
            self.ui.splitter.setSizes([1, 1])
        else:
            self.ui.splitter.setSizes([0, 1])

        # Sets up FlatCAMObj, FCProcess and FCProcessContainer.
        self.setup_component_editor()

        # ###########################################################################################################
        # ####################################### Auto-complete KEYWORDS ############################################
        # ###########################################################################################################
        self.tcl_commands_list = ['add_circle', 'add_poly', 'add_polygon', 'add_polyline', 'add_rectangle',
                                  'aligndrill', 'aligndrillgrid', 'bbox', 'clear', 'cncjob', 'cutout',
                                  'del', 'drillcncjob', 'export_dxf', 'edxf', 'export_excellon',
                                  'export_exc',
                                  'export_gcode', 'export_gerber', 'export_svg', 'ext', 'exteriors', 'follow',
                                  'geo_union', 'geocutout', 'get_bounds', 'get_names', 'get_path', 'get_sys', 'help',
                                  'interiors', 'isolate', 'join_excellon',
                                  'join_geometry', 'list_sys', 'milld', 'mills', 'milldrills', 'millslots',
                                  'mirror', 'ncc',
                                  'ncr', 'new', 'new_geometry', 'non_copper_regions', 'offset',
                                  'open_dxf', 'open_excellon', 'open_gcode', 'open_gerber', 'open_project', 'open_svg',
                                  'options', 'origin',
                                  'paint', 'panelize', 'plot_all', 'plot_objects', 'plot_status', 'quit_flatcam',
                                  'save', 'save_project',
                                  'save_sys', 'scale', 'set_active', 'set_origin', 'set_path', 'set_sys',
                                  'skew', 'subtract_poly', 'subtract_rectangle',
                                  'version', 'write_gcode'
                                  ]

        self.default_keywords = ['Desktop', 'Documents', 'FlatConfig', 'FlatPrj', 'False', 'Marius', 'My Documents',
                                 'Paste_1',
                                 'Repetier', 'Roland_MDX_20', 'Users', 'Toolchange_Custom', 'Toolchange_Probe_MACH3',
                                 'Toolchange_manual', 'True', 'Users',
                                 'all', 'auto', 'axis',
                                 'axisoffset', 'box', 'center_x', 'center_y', 'columns', 'combine', 'connect',
                                 'contour', 'default',
                                 'depthperpass', 'dia', 'diatol', 'dist', 'drilled_dias', 'drillz', 'dpp',
                                 'dwelltime', 'extracut_length', 'endxy', 'enz', 'f', 'feedrate',
                                 'feedrate_z', 'grbl_11', 'GRBL_laser', 'gridoffsety', 'gridx', 'gridy',
                                 'has_offset', 'holes', 'hpgl', 'iso_type', 'line_xyz', 'margin', 'marlin', 'method',
                                 'milled_dias', 'minoffset', 'name', 'offset', 'opt_type', 'order',
                                 'outname', 'overlap', 'passes', 'postamble', 'pp', 'ppname_e', 'ppname_g',
                                 'preamble', 'radius', 'ref', 'rest', 'rows', 'shellvar_', 'scale_factor',
                                 'spacing_columns',
                                 'spacing_rows', 'spindlespeed', 'startz', 'startxy',
                                 'toolchange_xy', 'toolchangez', 'travelz',
                                 'tooldia', 'use_threads', 'value',
                                 'x', 'x0', 'x1', 'y', 'y0', 'y1', 'z_cut', 'z_move'
                                 ]

        self.tcl_keywords = [
            'after', 'append', 'apply', 'argc', 'argv', 'argv0', 'array', 'attemptckalloc', 'attemptckrealloc',
            'auto_execok', 'auto_import', 'auto_load', 'auto_mkindex', 'auto_path', 'auto_qualify', 'auto_reset',
            'bgerror', 'binary', 'break', 'case', 'catch', 'cd', 'chan', 'ckalloc', 'ckfree', 'ckrealloc', 'clock',
            'close', 'concat', 'continue', 'coroutine', 'dde', 'dict', 'encoding', 'env', 'eof', 'error', 'errorCode',
            'errorInfo', 'eval', 'exec', 'exit', 'expr', 'fblocked', 'fconfigure', 'fcopy', 'file', 'fileevent',
            'filename', 'flush', 'for', 'foreach', 'format', 'gets', 'glob', 'global', 'history', 'http', 'if', 'incr',
            'info', 'interp', 'join', 'lappend', 'lassign', 'lindex', 'linsert', 'list', 'llength', 'load', 'lrange',
            'lrepeat', 'lreplace', 'lreverse', 'lsearch', 'lset', 'lsort', 'mathfunc', 'mathop', 'memory', 'msgcat',
            'my', 'namespace', 'next', 'nextto', 'open', 'package', 'parray', 'pid', 'pkg_mkIndex', 'platform',
            'proc', 'puts', 'pwd', 're_syntax', 'read', 'refchan', 'regexp', 'registry', 'regsub', 'rename', 'return',
            'safe', 'scan', 'seek', 'self', 'set', 'socket', 'source', 'split', 'string', 'subst', 'switch',
            'tailcall', 'Tcl', 'Tcl_Access', 'Tcl_AddErrorInfo', 'Tcl_AddObjErrorInfo', 'Tcl_AlertNotifier',
            'Tcl_Alloc', 'Tcl_AllocHashEntryProc', 'Tcl_AllocStatBuf', 'Tcl_AllowExceptions', 'Tcl_AppendAllObjTypes',
            'Tcl_AppendElement', 'Tcl_AppendExportList', 'Tcl_AppendFormatToObj', 'Tcl_AppendLimitedToObj',
            'Tcl_AppendObjToErrorInfo', 'Tcl_AppendObjToObj', 'Tcl_AppendPrintfToObj', 'Tcl_AppendResult',
            'Tcl_AppendResultVA', 'Tcl_AppendStringsToObj', 'Tcl_AppendStringsToObjVA', 'Tcl_AppendToObj',
            'Tcl_AppendUnicodeToObj', 'Tcl_AppInit', 'Tcl_AppInitProc', 'Tcl_ArgvInfo', 'Tcl_AsyncCreate',
            'Tcl_AsyncDelete', 'Tcl_AsyncInvoke', 'Tcl_AsyncMark', 'Tcl_AsyncProc', 'Tcl_AsyncReady',
            'Tcl_AttemptAlloc', 'Tcl_AttemptRealloc', 'Tcl_AttemptSetObjLength', 'Tcl_BackgroundError',
            'Tcl_BackgroundException', 'Tcl_Backslash', 'Tcl_BadChannelOption', 'Tcl_CallWhenDeleted', 'Tcl_Canceled',
            'Tcl_CancelEval', 'Tcl_CancelIdleCall', 'Tcl_ChannelBlockModeProc', 'Tcl_ChannelBuffered',
            'Tcl_ChannelClose2Proc', 'Tcl_ChannelCloseProc', 'Tcl_ChannelFlushProc', 'Tcl_ChannelGetHandleProc',
            'Tcl_ChannelGetOptionProc', 'Tcl_ChannelHandlerProc', 'Tcl_ChannelInputProc', 'Tcl_ChannelName',
            'Tcl_ChannelOutputProc', 'Tcl_ChannelProc', 'Tcl_ChannelSeekProc', 'Tcl_ChannelSetOptionProc',
            'Tcl_ChannelThreadActionProc', 'Tcl_ChannelTruncateProc', 'Tcl_ChannelType', 'Tcl_ChannelVersion',
            'Tcl_ChannelWatchProc', 'Tcl_ChannelWideSeekProc', 'Tcl_Chdir', 'Tcl_ClassGetMetadata',
            'Tcl_ClassSetConstructor', 'Tcl_ClassSetDestructor', 'Tcl_ClassSetMetadata', 'Tcl_ClearChannelHandlers',
            'Tcl_CloneProc', 'Tcl_Close', 'Tcl_CloseProc', 'Tcl_CmdDeleteProc', 'Tcl_CmdInfo',
            'Tcl_CmdObjTraceDeleteProc', 'Tcl_CmdObjTraceProc', 'Tcl_CmdProc', 'Tcl_CmdTraceProc',
            'Tcl_CommandComplete', 'Tcl_CommandTraceInfo', 'Tcl_CommandTraceProc', 'Tcl_CompareHashKeysProc',
            'Tcl_Concat', 'Tcl_ConcatObj', 'Tcl_ConditionFinalize', 'Tcl_ConditionNotify', 'Tcl_ConditionWait',
            'Tcl_Config', 'Tcl_ConvertCountedElement', 'Tcl_ConvertElement', 'Tcl_ConvertToType',
            'Tcl_CopyObjectInstance', 'Tcl_CreateAlias', 'Tcl_CreateAliasObj', 'Tcl_CreateChannel',
            'Tcl_CreateChannelHandler', 'Tcl_CreateCloseHandler', 'Tcl_CreateCommand', 'Tcl_CreateEncoding',
            'Tcl_CreateEnsemble', 'Tcl_CreateEventSource', 'Tcl_CreateExitHandler', 'Tcl_CreateFileHandler',
            'Tcl_CreateHashEntry', 'Tcl_CreateInterp', 'Tcl_CreateMathFunc', 'Tcl_CreateNamespace',
            'Tcl_CreateObjCommand', 'Tcl_CreateObjTrace', 'Tcl_CreateSlave', 'Tcl_CreateThread',
            'Tcl_CreateThreadExitHandler', 'Tcl_CreateTimerHandler', 'Tcl_CreateTrace',
            'Tcl_CutChannel', 'Tcl_DecrRefCount', 'Tcl_DeleteAssocData', 'Tcl_DeleteChannelHandler',
            'Tcl_DeleteCloseHandler', 'Tcl_DeleteCommand', 'Tcl_DeleteCommandFromToken', 'Tcl_DeleteEvents',
            'Tcl_DeleteEventSource', 'Tcl_DeleteExitHandler', 'Tcl_DeleteFileHandler', 'Tcl_DeleteHashEntry',
            'Tcl_DeleteHashTable', 'Tcl_DeleteInterp', 'Tcl_DeleteNamespace', 'Tcl_DeleteThreadExitHandler',
            'Tcl_DeleteTimerHandler', 'Tcl_DeleteTrace', 'Tcl_DetachChannel', 'Tcl_DetachPids', 'Tcl_DictObjDone',
            'Tcl_DictObjFirst', 'Tcl_DictObjGet', 'Tcl_DictObjNext', 'Tcl_DictObjPut', 'Tcl_DictObjPutKeyList',
            'Tcl_DictObjRemove', 'Tcl_DictObjRemoveKeyList', 'Tcl_DictObjSize', 'Tcl_DiscardInterpState',
            'Tcl_DiscardResult', 'Tcl_DontCallWhenDeleted', 'Tcl_DoOneEvent', 'Tcl_DoWhenIdle',
            'Tcl_DriverBlockModeProc', 'Tcl_DriverClose2Proc', 'Tcl_DriverCloseProc', 'Tcl_DriverFlushProc',
            'Tcl_DriverGetHandleProc', 'Tcl_DriverGetOptionProc', 'Tcl_DriverHandlerProc', 'Tcl_DriverInputProc',
            'Tcl_DriverOutputProc', 'Tcl_DriverSeekProc', 'Tcl_DriverSetOptionProc', 'Tcl_DriverThreadActionProc',
            'Tcl_DriverTruncateProc', 'Tcl_DriverWatchProc', 'Tcl_DriverWideSeekProc', 'Tcl_DStringAppend',
            'Tcl_DStringAppendElement', 'Tcl_DStringEndSublist', 'Tcl_DStringFree', 'Tcl_DStringGetResult',
            'Tcl_DStringInit', 'Tcl_DStringLength', 'Tcl_DStringResult', 'Tcl_DStringSetLength',
            'Tcl_DStringStartSublist', 'Tcl_DStringTrunc', 'Tcl_DStringValue', 'Tcl_DumpActiveMemory',
            'Tcl_DupInternalRepProc', 'Tcl_DuplicateObj', 'Tcl_EncodingConvertProc', 'Tcl_EncodingFreeProc',
            'Tcl_EncodingType', 'tcl_endOfWord', 'Tcl_Eof', 'Tcl_ErrnoId', 'Tcl_ErrnoMsg', 'Tcl_Eval', 'Tcl_EvalEx',
            'Tcl_EvalFile', 'Tcl_EvalObjEx', 'Tcl_EvalObjv', 'Tcl_EvalTokens', 'Tcl_EvalTokensStandard', 'Tcl_Event',
            'Tcl_EventCheckProc', 'Tcl_EventDeleteProc', 'Tcl_EventProc', 'Tcl_EventSetupProc', 'Tcl_EventuallyFree',
            'Tcl_Exit', 'Tcl_ExitProc', 'Tcl_ExitThread', 'Tcl_Export', 'Tcl_ExposeCommand', 'Tcl_ExprBoolean',
            'Tcl_ExprBooleanObj', 'Tcl_ExprDouble', 'Tcl_ExprDoubleObj', 'Tcl_ExprLong', 'Tcl_ExprLongObj',
            'Tcl_ExprObj', 'Tcl_ExprString', 'Tcl_ExternalToUtf', 'Tcl_ExternalToUtfDString', 'Tcl_FileProc',
            'Tcl_Filesystem', 'Tcl_Finalize', 'Tcl_FinalizeNotifier', 'Tcl_FinalizeThread', 'Tcl_FindCommand',
            'Tcl_FindEnsemble', 'Tcl_FindExecutable', 'Tcl_FindHashEntry', 'tcl_findLibrary', 'Tcl_FindNamespace',
            'Tcl_FirstHashEntry', 'Tcl_Flush', 'Tcl_ForgetImport', 'Tcl_Format', 'Tcl_FreeHashEntryProc',
            'Tcl_FreeInternalRepProc', 'Tcl_FreeParse', 'Tcl_FreeProc', 'Tcl_FreeResult',
            'Tcl_Free·\xa0Tcl_FreeEncoding', 'Tcl_FSAccess', 'Tcl_FSAccessProc', 'Tcl_FSChdir',
            'Tcl_FSChdirProc', 'Tcl_FSConvertToPathType', 'Tcl_FSCopyDirectory', 'Tcl_FSCopyDirectoryProc',
            'Tcl_FSCopyFile', 'Tcl_FSCopyFileProc', 'Tcl_FSCreateDirectory', 'Tcl_FSCreateDirectoryProc',
            'Tcl_FSCreateInternalRepProc', 'Tcl_FSData', 'Tcl_FSDeleteFile', 'Tcl_FSDeleteFileProc',
            'Tcl_FSDupInternalRepProc', 'Tcl_FSEqualPaths', 'Tcl_FSEvalFile', 'Tcl_FSEvalFileEx',
            'Tcl_FSFileAttrsGet', 'Tcl_FSFileAttrsGetProc', 'Tcl_FSFileAttrsSet', 'Tcl_FSFileAttrsSetProc',
            'Tcl_FSFileAttrStrings', 'Tcl_FSFileSystemInfo', 'Tcl_FSFilesystemPathTypeProc',
            'Tcl_FSFilesystemSeparatorProc', 'Tcl_FSFreeInternalRepProc', 'Tcl_FSGetCwd', 'Tcl_FSGetCwdProc',
            'Tcl_FSGetFileSystemForPath', 'Tcl_FSGetInternalRep', 'Tcl_FSGetNativePath', 'Tcl_FSGetNormalizedPath',
            'Tcl_FSGetPathType', 'Tcl_FSGetTranslatedPath', 'Tcl_FSGetTranslatedStringPath',
            'Tcl_FSInternalToNormalizedProc', 'Tcl_FSJoinPath', 'Tcl_FSJoinToPath', 'Tcl_FSLinkProc',
            'Tcl_FSLink·\xa0Tcl_FSListVolumes', 'Tcl_FSListVolumesProc', 'Tcl_FSLoadFile', 'Tcl_FSLoadFileProc',
            'Tcl_FSLstat', 'Tcl_FSLstatProc', 'Tcl_FSMatchInDirectory', 'Tcl_FSMatchInDirectoryProc',
            'Tcl_FSMountsChanged', 'Tcl_FSNewNativePath', 'Tcl_FSNormalizePathProc', 'Tcl_FSOpenFileChannel',
            'Tcl_FSOpenFileChannelProc', 'Tcl_FSPathInFilesystemProc', 'Tcl_FSPathSeparator', 'Tcl_FSRegister',
            'Tcl_FSRemoveDirectory', 'Tcl_FSRemoveDirectoryProc', 'Tcl_FSRenameFile', 'Tcl_FSRenameFileProc',
            'Tcl_FSSplitPath', 'Tcl_FSStat', 'Tcl_FSStatProc', 'Tcl_FSUnloadFile', 'Tcl_FSUnloadFileProc',
            'Tcl_FSUnregister', 'Tcl_FSUtime', 'Tcl_FSUtimeProc', 'Tcl_GetAccessTimeFromStat', 'Tcl_GetAlias',
            'Tcl_GetAliasObj', 'Tcl_GetAssocData', 'Tcl_GetBignumFromObj', 'Tcl_GetBlocksFromStat',
            'Tcl_GetBlockSizeFromStat', 'Tcl_GetBoolean', 'Tcl_GetBooleanFromObj', 'Tcl_GetByteArrayFromObj',
            'Tcl_GetChangeTimeFromStat', 'Tcl_GetChannel', 'Tcl_GetChannelBufferSize', 'Tcl_GetChannelError',
            'Tcl_GetChannelErrorInterp', 'Tcl_GetChannelHandle', 'Tcl_GetChannelInstanceData', 'Tcl_GetChannelMode',
            'Tcl_GetChannelName', 'Tcl_GetChannelNames', 'Tcl_GetChannelNamesEx', 'Tcl_GetChannelOption',
            'Tcl_GetChannelThread', 'Tcl_GetChannelType', 'Tcl_GetCharLength', 'Tcl_GetClassAsObject',
            'Tcl_GetCommandFromObj', 'Tcl_GetCommandFullName', 'Tcl_GetCommandInfo', 'Tcl_GetCommandInfoFromToken',
            'Tcl_GetCommandName', 'Tcl_GetCurrentNamespace', 'Tcl_GetCurrentThread', 'Tcl_GetCwd',
            'Tcl_GetDefaultEncodingDir', 'Tcl_GetDeviceTypeFromStat', 'Tcl_GetDouble', 'Tcl_GetDoubleFromObj',
            'Tcl_GetEncoding', 'Tcl_GetEncodingFromObj', 'Tcl_GetEncodingName', 'Tcl_GetEncodingNameFromEnvironment',
            'Tcl_GetEncodingNames', 'Tcl_GetEncodingSearchPath', 'Tcl_GetEnsembleFlags', 'Tcl_GetEnsembleMappingDict',
            'Tcl_GetEnsembleNamespace', 'Tcl_GetEnsembleParameterList', 'Tcl_GetEnsembleSubcommandList',
            'Tcl_GetEnsembleUnknownHandler', 'Tcl_GetErrno', 'Tcl_GetErrorLine', 'Tcl_GetFSDeviceFromStat',
            'Tcl_GetFSInodeFromStat', 'Tcl_GetGlobalNamespace', 'Tcl_GetGroupIdFromStat', 'Tcl_GetHashKey',
            'Tcl_GetHashValue', 'Tcl_GetHostName', 'Tcl_GetIndexFromObj', 'Tcl_GetIndexFromObjStruct', 'Tcl_GetInt',
            'Tcl_GetInterpPath', 'Tcl_GetIntFromObj', 'Tcl_GetLinkCountFromStat', 'Tcl_GetLongFromObj',
            'Tcl_GetMaster', 'Tcl_GetMathFuncInfo', 'Tcl_GetModeFromStat', 'Tcl_GetModificationTimeFromStat',
            'Tcl_GetNameOfExecutable', 'Tcl_GetNamespaceUnknownHandler', 'Tcl_GetObjectAsClass', 'Tcl_GetObjectCommand',
            'Tcl_GetObjectFromObj', 'Tcl_GetObjectName', 'Tcl_GetObjectNamespace', 'Tcl_GetObjResult', 'Tcl_GetObjType',
            'Tcl_GetOpenFile', 'Tcl_GetPathType', 'Tcl_GetRange', 'Tcl_GetRegExpFromObj', 'Tcl_GetReturnOptions',
            'Tcl_Gets', 'Tcl_GetServiceMode', 'Tcl_GetSizeFromStat', 'Tcl_GetSlave', 'Tcl_GetsObj',
            'Tcl_GetStackedChannel', 'Tcl_GetStartupScript', 'Tcl_GetStdChannel', 'Tcl_GetString',
            'Tcl_GetStringFromObj', 'Tcl_GetStringResult', 'Tcl_GetThreadData', 'Tcl_GetTime', 'Tcl_GetTopChannel',
            'Tcl_GetUniChar', 'Tcl_GetUnicode', 'Tcl_GetUnicodeFromObj', 'Tcl_GetUserIdFromStat', 'Tcl_GetVar',
            'Tcl_GetVar2', 'Tcl_GetVar2Ex', 'Tcl_GetVersion', 'Tcl_GetWideIntFromObj', 'Tcl_GlobalEval',
            'Tcl_GlobalEvalObj', 'Tcl_GlobTypeData', 'Tcl_HashKeyType', 'Tcl_HashStats', 'Tcl_HideCommand',
            'Tcl_IdleProc', 'Tcl_Import', 'Tcl_IncrRefCount', 'Tcl_Init', 'Tcl_InitCustomHashTable',
            'Tcl_InitHashTable', 'Tcl_InitMemory', 'Tcl_InitNotifier', 'Tcl_InitObjHashTable', 'Tcl_InitStubs',
            'Tcl_InputBlocked', 'Tcl_InputBuffered', 'tcl_interactive', 'Tcl_Interp', 'Tcl_InterpActive',
            'Tcl_InterpDeleted', 'Tcl_InterpDeleteProc', 'Tcl_InvalidateStringRep', 'Tcl_IsChannelExisting',
            'Tcl_IsChannelRegistered', 'Tcl_IsChannelShared', 'Tcl_IsEnsemble', 'Tcl_IsSafe', 'Tcl_IsShared',
            'Tcl_IsStandardChannel', 'Tcl_JoinPath', 'Tcl_JoinThread', 'tcl_library', 'Tcl_LimitAddHandler',
            'Tcl_LimitCheck', 'Tcl_LimitExceeded', 'Tcl_LimitGetCommands', 'Tcl_LimitGetGranularity',
            'Tcl_LimitGetTime', 'Tcl_LimitHandlerDeleteProc', 'Tcl_LimitHandlerProc', 'Tcl_LimitReady',
            'Tcl_LimitRemoveHandler', 'Tcl_LimitSetCommands', 'Tcl_LimitSetGranularity', 'Tcl_LimitSetTime',
            'Tcl_LimitTypeEnabled', 'Tcl_LimitTypeExceeded', 'Tcl_LimitTypeReset', 'Tcl_LimitTypeSet',
            'Tcl_LinkVar', 'Tcl_ListMathFuncs', 'Tcl_ListObjAppendElement', 'Tcl_ListObjAppendList',
            'Tcl_ListObjGetElements', 'Tcl_ListObjIndex', 'Tcl_ListObjLength', 'Tcl_ListObjReplace',
            'Tcl_LogCommandInfo', 'Tcl_Main', 'Tcl_MainLoopProc', 'Tcl_MakeFileChannel', 'Tcl_MakeSafe',
            'Tcl_MakeTcpClientChannel', 'Tcl_MathProc', 'TCL_MEM_DEBUG', 'Tcl_Merge', 'Tcl_MethodCallProc',
            'Tcl_MethodDeclarerClass', 'Tcl_MethodDeclarerObject', 'Tcl_MethodDeleteProc', 'Tcl_MethodIsPublic',
            'Tcl_MethodIsType', 'Tcl_MethodName', 'Tcl_MethodType', 'Tcl_MutexFinalize', 'Tcl_MutexLock',
            'Tcl_MutexUnlock', 'Tcl_NamespaceDeleteProc', 'Tcl_NewBignumObj', 'Tcl_NewBooleanObj',
            'Tcl_NewByteArrayObj', 'Tcl_NewDictObj', 'Tcl_NewDoubleObj', 'Tcl_NewInstanceMethod', 'Tcl_NewIntObj',
            'Tcl_NewListObj', 'Tcl_NewLongObj', 'Tcl_NewMethod', 'Tcl_NewObj', 'Tcl_NewObjectInstance',
            'Tcl_NewStringObj', 'Tcl_NewUnicodeObj', 'Tcl_NewWideIntObj', 'Tcl_NextHashEntry', 'tcl_nonwordchars',
            'Tcl_NotifierProcs', 'Tcl_NotifyChannel', 'Tcl_NRAddCallback', 'Tcl_NRCallObjProc', 'Tcl_NRCmdSwap',
            'Tcl_NRCreateCommand', 'Tcl_NREvalObj', 'Tcl_NREvalObjv', 'Tcl_NumUtfChars', 'Tcl_Obj', 'Tcl_ObjCmdProc',
            'Tcl_ObjectContextInvokeNext', 'Tcl_ObjectContextIsFiltering', 'Tcl_ObjectContextMethod',
            'Tcl_ObjectContextObject', 'Tcl_ObjectContextSkippedArgs', 'Tcl_ObjectDeleted', 'Tcl_ObjectGetMetadata',
            'Tcl_ObjectGetMethodNameMapper', 'Tcl_ObjectMapMethodNameProc', 'Tcl_ObjectMetadataDeleteProc',
            'Tcl_ObjectSetMetadata', 'Tcl_ObjectSetMethodNameMapper', 'Tcl_ObjGetVar2', 'Tcl_ObjPrintf',
            'Tcl_ObjSetVar2', 'Tcl_ObjType', 'Tcl_OpenCommandChannel', 'Tcl_OpenFileChannel', 'Tcl_OpenTcpClient',
            'Tcl_OpenTcpServer', 'Tcl_OutputBuffered', 'Tcl_PackageInitProc', 'Tcl_PackageUnloadProc', 'Tcl_Panic',
            'Tcl_PanicProc', 'Tcl_PanicVA', 'Tcl_ParseArgsObjv', 'Tcl_ParseBraces', 'Tcl_ParseCommand', 'Tcl_ParseExpr',
            'Tcl_ParseQuotedString', 'Tcl_ParseVar', 'Tcl_ParseVarName', 'tcl_patchLevel', 'tcl_pkgPath',
            'Tcl_PkgPresent', 'Tcl_PkgPresentEx', 'Tcl_PkgProvide', 'Tcl_PkgProvideEx', 'Tcl_PkgRequire',
            'Tcl_PkgRequireEx', 'Tcl_PkgRequireProc', 'tcl_platform', 'Tcl_PosixError', 'tcl_precision',
            'Tcl_Preserve', 'Tcl_PrintDouble', 'Tcl_PutEnv', 'Tcl_QueryTimeProc', 'Tcl_QueueEvent', 'tcl_rcFileName',
            'Tcl_Read', 'Tcl_ReadChars', 'Tcl_ReadRaw', 'Tcl_Realloc', 'Tcl_ReapDetachedProcs', 'Tcl_RecordAndEval',
            'Tcl_RecordAndEvalObj', 'Tcl_RegExpCompile', 'Tcl_RegExpExec', 'Tcl_RegExpExecObj', 'Tcl_RegExpGetInfo',
            'Tcl_RegExpIndices', 'Tcl_RegExpInfo', 'Tcl_RegExpMatch', 'Tcl_RegExpMatchObj', 'Tcl_RegExpRange',
            'Tcl_RegisterChannel', 'Tcl_RegisterConfig', 'Tcl_RegisterObjType', 'Tcl_Release', 'Tcl_ResetResult',
            'Tcl_RestoreInterpState', 'Tcl_RestoreResult', 'Tcl_SaveInterpState', 'Tcl_SaveResult', 'Tcl_ScaleTimeProc',
            'Tcl_ScanCountedElement', 'Tcl_ScanElement', 'Tcl_Seek', 'Tcl_ServiceAll', 'Tcl_ServiceEvent',
            'Tcl_ServiceModeHook', 'Tcl_SetAssocData', 'Tcl_SetBignumObj', 'Tcl_SetBooleanObj',
            'Tcl_SetByteArrayLength', 'Tcl_SetByteArrayObj', 'Tcl_SetChannelBufferSize', 'Tcl_SetChannelError',
            'Tcl_SetChannelErrorInterp', 'Tcl_SetChannelOption', 'Tcl_SetCommandInfo', 'Tcl_SetCommandInfoFromToken',
            'Tcl_SetDefaultEncodingDir', 'Tcl_SetDoubleObj', 'Tcl_SetEncodingSearchPath', 'Tcl_SetEnsembleFlags',
            'Tcl_SetEnsembleMappingDict', 'Tcl_SetEnsembleParameterList', 'Tcl_SetEnsembleSubcommandList',
            'Tcl_SetEnsembleUnknownHandler', 'Tcl_SetErrno', 'Tcl_SetErrorCode', 'Tcl_SetErrorCodeVA',
            'Tcl_SetErrorLine', 'Tcl_SetExitProc', 'Tcl_SetFromAnyProc', 'Tcl_SetHashValue', 'Tcl_SetIntObj',
            'Tcl_SetListObj', 'Tcl_SetLongObj', 'Tcl_SetMainLoop', 'Tcl_SetMaxBlockTime',
            'Tcl_SetNamespaceUnknownHandler', 'Tcl_SetNotifier', 'Tcl_SetObjErrorCode', 'Tcl_SetObjLength',
            'Tcl_SetObjResult', 'Tcl_SetPanicProc', 'Tcl_SetRecursionLimit', 'Tcl_SetResult', 'Tcl_SetReturnOptions',
            'Tcl_SetServiceMode', 'Tcl_SetStartupScript', 'Tcl_SetStdChannel', 'Tcl_SetStringObj',
            'Tcl_SetSystemEncoding', 'Tcl_SetTimeProc', 'Tcl_SetTimer', 'Tcl_SetUnicodeObj', 'Tcl_SetVar',
            'Tcl_SetVar2', 'Tcl_SetVar2Ex', 'Tcl_SetWideIntObj', 'Tcl_SignalId', 'Tcl_SignalMsg', 'Tcl_Sleep',
            'Tcl_SourceRCFile', 'Tcl_SpliceChannel', 'Tcl_SplitList', 'Tcl_SplitPath', 'Tcl_StackChannel',
            'Tcl_StandardChannels', 'tcl_startOfNextWord', 'tcl_startOfPreviousWord', 'Tcl_Stat', 'Tcl_StaticPackage',
            'Tcl_StringCaseMatch', 'Tcl_StringMatch', 'Tcl_SubstObj', 'Tcl_TakeBignumFromObj', 'Tcl_TcpAcceptProc',
            'Tcl_Tell', 'Tcl_ThreadAlert', 'Tcl_ThreadQueueEvent', 'Tcl_Time', 'Tcl_TimerProc', 'Tcl_Token',
            'Tcl_TraceCommand', 'tcl_traceCompile', 'tcl_traceEval', 'Tcl_TraceVar', 'Tcl_TraceVar2',
            'Tcl_TransferResult', 'Tcl_TranslateFileName', 'Tcl_TruncateChannel', 'Tcl_Ungets', 'Tcl_UniChar',
            'Tcl_UniCharAtIndex', 'Tcl_UniCharCaseMatch', 'Tcl_UniCharIsAlnum', 'Tcl_UniCharIsAlpha',
            'Tcl_UniCharIsControl', 'Tcl_UniCharIsDigit', 'Tcl_UniCharIsGraph', 'Tcl_UniCharIsLower',
            'Tcl_UniCharIsPrint', 'Tcl_UniCharIsPunct', 'Tcl_UniCharIsSpace', 'Tcl_UniCharIsUpper',
            'Tcl_UniCharIsWordChar', 'Tcl_UniCharLen', 'Tcl_UniCharNcasecmp', 'Tcl_UniCharNcmp', 'Tcl_UniCharToLower',
            'Tcl_UniCharToTitle', 'Tcl_UniCharToUpper', 'Tcl_UniCharToUtf', 'Tcl_UniCharToUtfDString', 'Tcl_UnlinkVar',
            'Tcl_UnregisterChannel', 'Tcl_UnsetVar', 'Tcl_UnsetVar2', 'Tcl_UnstackChannel', 'Tcl_UntraceCommand',
            'Tcl_UntraceVar', 'Tcl_UntraceVar2', 'Tcl_UpdateLinkedVar', 'Tcl_UpdateStringProc', 'Tcl_UpVar',
            'Tcl_UpVar2', 'Tcl_UtfAtIndex', 'Tcl_UtfBackslash', 'Tcl_UtfCharComplete', 'Tcl_UtfFindFirst',
            'Tcl_UtfFindLast', 'Tcl_UtfNext', 'Tcl_UtfPrev', 'Tcl_UtfToExternal', 'Tcl_UtfToExternalDString',
            'Tcl_UtfToLower', 'Tcl_UtfToTitle', 'Tcl_UtfToUniChar', 'Tcl_UtfToUniCharDString', 'Tcl_UtfToUpper',
            'Tcl_ValidateAllMemory', 'Tcl_Value', 'Tcl_VarEval', 'Tcl_VarEvalVA', 'Tcl_VarTraceInfo',
            'Tcl_VarTraceInfo2', 'Tcl_VarTraceProc', 'tcl_version', 'Tcl_WaitForEvent', 'Tcl_WaitPid',
            'Tcl_WinTCharToUtf', 'Tcl_WinUtfToTChar', 'tcl_wordBreakAfter', 'tcl_wordBreakBefore', 'tcl_wordchars',
            'Tcl_Write', 'Tcl_WriteChars', 'Tcl_WriteObj', 'Tcl_WriteRaw', 'Tcl_WrongNumArgs', 'Tcl_ZlibAdler32',
            'Tcl_ZlibCRC32', 'Tcl_ZlibDeflate', 'Tcl_ZlibInflate', 'Tcl_ZlibStreamChecksum', 'Tcl_ZlibStreamClose',
            'Tcl_ZlibStreamEof', 'Tcl_ZlibStreamGet', 'Tcl_ZlibStreamGetCommandName', 'Tcl_ZlibStreamInit',
            'Tcl_ZlibStreamPut', 'tcltest', 'tell', 'throw', 'time', 'tm', 'trace', 'transchan', 'try', 'unknown',
            'unload', 'unset', 'update', 'uplevel', 'upvar', 'variable', 'vwait', 'while', 'yield', 'yieldto', 'zlib'
        ]

        self.autocomplete_kw_list = self.defaults['util_autocomplete_keywords'].replace(' ', '').split(',')
        self.myKeywords = self.tcl_commands_list + self.autocomplete_kw_list + self.tcl_keywords

        # ###########################################################################################################
        # ############################################## Shell SETUP ################################################
        # ###########################################################################################################

        self.shell = FCShell(app=self, version=self.version)

        self.ui.shell_dock.setWidget(self.shell)
        self.log.debug("TCL Shell has been initialized.")

        # show TCL shell at start-up based on the Menu -? Edit -> Preferences setting.
        if self.defaults["global_shell_at_startup"]:
            self.ui.shell_dock.show()
        else:
            self.ui.shell_dock.hide()

        # ###########################################################################################################
        # ########################################## Tools and Plugins ##############################################
        # ###########################################################################################################

        self.dblsidedtool = None
        self.distance_tool = None
        self.distance_min_tool = None
        self.panelize_tool = None
        self.film_tool = None
        self.paste_tool = None
        self.calculator_tool = None
        self.rules_tool = None
        self.sub_tool = None
        self.move_tool = None
        self.cutout_tool = None
        self.ncclear_tool = None
        self.optimal_tool = None
        self.paint_tool = None
        self.transform_tool = None
        self.properties_tool = None
        self.pdf_tool = None
        self.image_tool = None
        self.pcb_wizard_tool = None
        self.cal_exc_tool = None
        self.qrcode_tool = None
        self.copper_thieving_tool = None
        self.fiducial_tool = None
        self.edrills_tool = None
        self.align_objects_tool = None
        self.punch_tool = None
        self.invert_tool = None

        # always install tools only after the shell is initialized because the self.inform.emit() depends on shell
        try:
            self.install_tools()
        except AttributeError as e:
            log.debug("App.__init__() install tools() --> %s" % str(e))

        # ###########################################################################################################
        # ############################################ SETUP RECENT ITEMS ###########################################
        # ###########################################################################################################
        self.setup_recent_items()

        # ###########################################################################################################
        # ######################################### BookMarks Manager ###############################################
        # ###########################################################################################################

        # install Bookmark Manager and populate bookmarks in the Help -> Bookmarks
        self.install_bookmarks()
        self.book_dialog_tab = BookmarkManager(app=self, storage=self.defaults["global_bookmarks"])

        # ###########################################################################################################
        # ########################################### Tools Database ################################################
        # ###########################################################################################################

        self.tools_db_tab = None

        # ### System Font Parsing ###
        # self.f_parse = ParseFont(self)
        # self.parse_system_fonts()

        # ###########################################################################################################
        # ######################################### Check for updates ###############################################
        # ###########################################################################################################

        # Separate thread (Not worker)
        # Check for updates on startup but only if the user consent and the app is not in Beta version
        if (self.beta is False or self.beta is None) and \
                self.preferencesUiManager.get_form_field("global_version_check").get_value() is True:
            App.log.info("Checking for updates in background (this is version %s)." % str(self.version))

            # self.thr2 = QtCore.QThread()
            self.worker_task.emit({'fcn': self.version_check,
                                   'params': []})
            # self.thr2.start(QtCore.QThread.LowPriority)

        # ###########################################################################################################
        # ##################################### Register files with FlatCAM;  #######################################
        # ################################### It works only for Windows for now  ####################################
        # ###########################################################################################################
        if sys.platform == 'win32' and self.defaults["first_run"] is True:
            self.on_register_files()

        # ###########################################################################################################
        # ######################################## Variables for global usage #######################################
        # ###########################################################################################################

        # hold the App units
        self.units = 'MM'

        # coordinates for relative position display
        self.rel_point1 = (0, 0)
        self.rel_point2 = (0, 0)

        # variable to store coordinates
        self.pos = (0, 0)
        self.pos_canvas = (0, 0)
        self.pos_jump = (0, 0)

        # variable to store mouse coordinates
        self.mouse = [0, 0]

        # variable to store the delta positions on cavnas
        self.dx = 0
        self.dy = 0

        # decide if we have a double click or single click
        self.doubleclick = False

        # store here the is_dragging value
        self.event_is_dragging = False

        # variable to store if a command is active (then the var is not None) and which one it is
        self.command_active = None
        # variable to store the status of moving selection action
        # None value means that it's not an selection action
        # True value = a selection from left to right
        # False value = a selection from right to left
        self.selection_type = None

        # List to store the objects that are currently loaded in FlatCAM
        # This list is updated on each object creation or object delete
        self.all_objects_list = []

        self.objects_under_the_click_list = []

        # List to store the objects that are selected
        self.sel_objects_list = []

        # holds the key modifier if pressed (CTRL, SHIFT or ALT)
        self.key_modifiers = None

        # Variable to hold the status of the axis
        self.toggle_axis = True

        # Variable to hold the status of the grid lines
        self.toggle_grid_lines = True

        # Variable to store the status of the fullscreen event
        self.toggle_fscreen = False

        # Variable to store the status of the code editor
        self.toggle_codeeditor = False

        # Variable to be used for situations when we don't want the LMB click on canvas to auto open the Project Tab
        self.click_noproject = False

        self.cursor = None

        # Variable to store the GCODE that was edited
        self.gcode_edited = ""

        self.text_editor_tab = None

        # reference for the self.ui.code_editor
        self.reference_code_editor = None
        self.script_code = ''

        # if Tools DB are changed/edited in the Edit -> Tools Database tab the value will be set to True
        self.tools_db_changed_flag = False

        self.grb_list = ['art', 'bot', 'bsm', 'cmp', 'crc', 'crs', 'dim', 'g4', 'gb0', 'gb1', 'gb2', 'gb3', 'gb5',
                         'gb6', 'gb7', 'gb8', 'gb9', 'gbd', 'gbl', 'gbo', 'gbp', 'gbr', 'gbs', 'gdo', 'ger', 'gko',
                         'gml', 'gm1', 'gm2', 'gm3', 'grb', 'gtl', 'gto', 'gtp', 'gts', 'ly15', 'ly2', 'mil', 'outline',
                         'pho', 'plc', 'pls', 'smb', 'smt', 'sol', 'spb', 'spt', 'ssb', 'sst', 'stc', 'sts', 'top',
                         'tsm']

        self.exc_list = ['drd', 'drl', 'drill', 'exc', 'ncd', 'tap', 'txt', 'xln']

        self.gcode_list = ['cnc', 'din', 'dnc', 'ecs', 'eia', 'fan', 'fgc', 'fnc', 'gc', 'gcd', 'gcode', 'h', 'hnc',
                           'i', 'min', 'mpf', 'mpr', 'nc', 'ncc', 'ncg', 'ngc', 'ncp', 'out', 'ply', 'rol',
                           'sbp', 'tap', 'xpi']
        self.svg_list = ['svg']
        self.dxf_list = ['dxf']
        self.pdf_list = ['pdf']
        self.prj_list = ['flatprj']
        self.conf_list = ['flatconfig']

        # global variable used by NCC Tool to signal that some polygons could not be cleared, if True
        # flag for polygons not cleared
        self.poly_not_cleared = False

        # VisPy visuals
        self.isHovering = False
        self.notHovering = True

        # Window geometry
        self.x_pos = None
        self.y_pos = None
        self.width = None
        self.height = None

        # when True, the app has to return from any thread
        self.abort_flag = False

        # set the value used in the Windows Title
        self.engine = self.preferencesUiManager.get_form_field("global_graphic_engine").get_value()

        # this holds a widget that is installed in the Plot Area when View Source option is used
        self.source_editor_tab = None

        self.pagesize = {}

        # Storage for shapes, storage that can be used by FlatCAm tools for utility geometry
        # VisPy visuals
        if self.is_legacy is False:
            try:
                self.tool_shapes = ShapeCollection(parent=self.plotcanvas.view.scene, layers=1)
            except AttributeError:
                self.tool_shapes = None
        else:
            from flatcamGUI.PlotCanvasLegacy import ShapeCollectionLegacy
            self.tool_shapes = ShapeCollectionLegacy(obj=self, app=self, name="tool")

        # used in the delayed shutdown self.start_delayed_quit() method
        self.save_timer = None

        # ###########################################################################################################
        # ################################## ADDING FlatCAM EDITORS section #########################################
        # ###########################################################################################################

        # watch out for the position of the editors instantiation ... if it is done before a save of the default values
        # at the first launch of the App , the editors will not be functional.
        try:
            self.geo_editor = FlatCAMGeoEditor(self)
        except AttributeError:
            pass

        try:
            self.exc_editor = FlatCAMExcEditor(self)
        except AttributeError:
            pass

        try:
            self.grb_editor = FlatCAMGrbEditor(self)
        except AttributeError:
            pass
        self.log.debug("Finished adding FlatCAM Editor's.")

        self.set_ui_title(name=_("New Project - Not saved"))



        # ###########################################################################################################
        # ########################################### EXCLUSION AREAS ###############################################
        # ###########################################################################################################
        self.exc_areas = ExclusionAreas(app=self)

        # ###########################################################################################################
        # ##################################### Finished the CONSTRUCTOR ############################################
        # ###########################################################################################################
        App.log.debug("END of constructor. Releasing control.")

        # ###########################################################################################################
        # ########################################## SHOW GUI #######################################################
        # ###########################################################################################################

        # if the app is not started as headless, show it
        if self.cmd_line_headless != 1:
            if show_splash:
                # finish the splash
                self.splash.finish(self.ui)

            mgui_settings = QSettings("Open Source", "FlatCAM")
            if mgui_settings.contains("maximized_gui"):
                maximized_ui = mgui_settings.value('maximized_gui', type=bool)
                if maximized_ui is True:
                    self.ui.showMaximized()
                else:
                    self.ui.show()
            else:
                self.ui.show()

            if self.defaults["global_systray_icon"]:
                self.trayIcon.show()
        else:
            log.warning("*******************  RUNNING HEADLESS  *******************")

        # ###########################################################################################################
        # ######################################## START-UP ARGUMENTS ###############################################
        # ###########################################################################################################

        # test if the program was started with a script as parameter
        if self.cmd_line_shellvar:
            try:
                cnt = 0
                command_tcl = 0
                for i in self.cmd_line_shellvar.split(','):
                    if i is not None:
                        # noinspection PyBroadException
                        try:
                            command_tcl = eval(i)
                        except Exception:
                            command_tcl = i

                    command_tcl_formatted = 'set shellvar_{nr} "{cmd}"'.format(cmd=str(command_tcl), nr=str(cnt))

                    cnt += 1

                    # if there are Windows paths then replace the path separator with a Unix like one
                    if sys.platform == 'win32':
                        command_tcl_formatted = command_tcl_formatted.replace('\\', '/')
                    self.shell.exec_command(command_tcl_formatted, no_echo=True)
            except Exception as ext:
                print("ERROR: ", ext)
                sys.exit(2)

        if self.cmd_line_shellfile:
            if self.cmd_line_headless != 1:
                if self.ui.shell_dock.isHidden():
                    self.ui.shell_dock.show()
            try:
                with open(self.cmd_line_shellfile, "r") as myfile:
                    # if show_splash:
                    #     self.splash.showMessage('%s: %ssec\n%s' % (
                    #         _("Canvas initialization started.\n"
                    #           "Canvas initialization finished in"), '%.2f' % self.used_time,
                    #         _("Executing Tcl Script ...")),
                    #                             alignment=Qt.AlignBottom | Qt.AlignLeft,
                    #                             color=QtGui.QColor("gray"))
                    cmd_line_shellfile_text = myfile.read()
                    if self.cmd_line_headless != 1:
                        self.shell.exec_command(cmd_line_shellfile_text)
                    else:
                        self.shell.exec_command(cmd_line_shellfile_text, no_echo=True)

            except Exception as ext:
                print("ERROR: ", ext)
                sys.exit(2)

        # accept some type file as command line parameter: FlatCAM project, FlatCAM preferences or scripts
        # the path/file_name must be enclosed in quotes if it contain spaces
        if App.args:
            self.args_at_startup.emit(App.args)

        if self.defaults.old_defaults_found is True:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Found old default preferences files. "
                                                      "Please reboot the application to update."))
            self.defaults.old_defaults_found = False

    # ######################################### INIT FINISHED  #######################################################
    # #################################################################################################################
    # #################################################################################################################
    # #################################################################################################################
    # #################################################################################################################
    # #################################################################################################################

    @staticmethod
    def copy_and_overwrite(from_path, to_path):
        """
        From here:
        https://stackoverflow.com/questions/12683834/how-to-copy-directory-recursively-in-python-and-overwrite-all

        :param from_path: source path
        :param to_path: destination path
        :return: None
        """
        if os.path.exists(to_path):
            shutil.rmtree(to_path)
        try:
            shutil.copytree(from_path, to_path)
        except FileNotFoundError:
            from_new_path = os.path.dirname(os.path.realpath(__file__)) + '\\flatcamGUI\\VisPyData\\data'
            shutil.copytree(from_new_path, to_path)

    def on_startup_args(self, args, silent=False):
        """
        This will process any arguments provided to the application at startup. Like trying to launch a file or project.

        :param silent: when True it will not print messages on Tcl Shell and/or status bar
        :param args: a list containing the application args at startup
        :return: None
        """

        if args is not None:
            args_to_process = args
        else:
            args_to_process = App.args

        log.debug("Application was started with arguments: %s. Processing ..." % str(args_to_process))
        for argument in args_to_process:
            if '.FlatPrj'.lower() in argument.lower():
                try:
                    project_name = str(argument)

                    if project_name == "":
                        if silent is False:
                            self.inform.emit(_("Cancelled."))
                    else:
                        # self.open_project(project_name)
                        run_from_arg = True
                        # self.worker_task.emit({'fcn': self.open_project,
                        #                        'params': [project_name, run_from_arg]})
                        self.open_project(filename=project_name, run_from_arg=run_from_arg)
                except Exception as e:
                    log.debug("Could not open FlatCAM project file as App parameter due: %s" % str(e))

            elif '.FlatConfig'.lower() in argument.lower():
                try:
                    file_name = str(argument)

                    if file_name == "":
                        if silent is False:
                            self.inform.emit(_("Open Config file failed."))
                    else:
                        run_from_arg = True
                        # self.worker_task.emit({'fcn': self.open_config_file,
                        #                        'params': [file_name, run_from_arg]})
                        self.open_config_file(file_name, run_from_arg=run_from_arg)
                except Exception as e:
                    log.debug("Could not open FlatCAM Config file as App parameter due: %s" % str(e))

            elif '.FlatScript'.lower() in argument.lower() or '.TCL'.lower() in argument.lower():
                try:
                    file_name = str(argument)

                    if file_name == "":
                        if silent is False:
                            self.inform.emit(_("Open Script file failed."))
                    else:
                        if silent is False:
                            self.on_fileopenscript(name=file_name)
                            self.ui.plot_tab_area.setCurrentWidget(self.ui.plot_tab)
                        self.on_filerunscript(name=file_name)
                except Exception as e:
                    log.debug("Could not open FlatCAM Script file as App parameter due: %s" % str(e))

            elif 'quit'.lower() in argument.lower() or 'exit'.lower() in argument.lower():
                log.debug("App.on_startup_args() --> Quit event.")
                sys.exit()

            elif 'save'.lower() in argument.lower():
                log.debug("App.on_startup_args() --> Save event. App Defaults saved.")
                self.preferencesUiManager.save_defaults()
            else:
                exc_list = self.ui.util_defaults_form.fa_excellon_group.exc_list_text.get_value().split(',')
                proc_arg = argument.lower()
                for ext in exc_list:
                    proc_ext = ext.replace(' ', '')
                    proc_ext = '.%s' % proc_ext
                    if proc_ext.lower() in proc_arg and proc_ext != '.':
                        file_name = str(argument)
                        if file_name == "":
                            if silent is False:
                                self.inform.emit(_("Open Excellon file failed."))
                        else:
                            self.on_fileopenexcellon(name=file_name, signal=None)
                            return

                gco_list = self.ui.util_defaults_form.fa_gcode_group.gco_list_text.get_value().split(',')
                for ext in gco_list:
                    proc_ext = ext.replace(' ', '')
                    proc_ext = '.%s' % proc_ext
                    if proc_ext.lower() in proc_arg and proc_ext != '.':
                        file_name = str(argument)
                        if file_name == "":
                            if silent is False:
                                self.inform.emit(_("Open GCode file failed."))
                        else:
                            self.on_fileopengcode(name=file_name, signal=None)
                            return

                grb_list = self.ui.util_defaults_form.fa_gerber_group.grb_list_text.get_value().split(',')
                for ext in grb_list:
                    proc_ext = ext.replace(' ', '')
                    proc_ext = '.%s' % proc_ext
                    if proc_ext.lower() in proc_arg and proc_ext != '.':
                        file_name = str(argument)
                        if file_name == "":
                            if silent is False:
                                self.inform.emit(_("Open Gerber file failed."))
                        else:
                            self.on_fileopengerber(name=file_name, signal=None)
                            return

        # if it reached here without already returning then the app was registered with a file that it does not
        # recognize therefore we must quit but take into consideration the app reboot from within, in that case
        # the args_to_process will contain the path to the FlatCAM.exe (cx_freezed executable)

        # for arg in args_to_process:
        #     if 'FlatCAM.exe' in arg:
        #         continue
        #     else:
        #         sys.exit(2)

    def set_ui_title(self, name):
        """
        Sets the title of the main window.

        :param name: String that store the project path and project name
        :return: None
        """
        self.ui.setWindowTitle('FlatCAM %s %s - %s - [%s]    %s' %
                               (self.version,
                                ('BETA' if self.beta else ''),
                                platform.architecture()[0],
                                self.engine,
                                name)
                               )

    def on_app_restart(self):

        # make sure that the Sys Tray icon is hidden before restart otherwise it will
        # be left in the SySTray
        try:
            self.trayIcon.hide()
        except Exception:
            pass

        fcTranslate.restart_program(app=self)

    def clear_pool(self):
        """
        Clear the multiprocessing pool and calls garbage collector.

        :return: None
        """
        self.pool.close()

        self.pool = Pool()
        self.pool_recreated.emit(self.pool)

        gc.collect()

    def install_tools(self):
        """
        This installs the FlatCAM tools (plugin-like) which reside in their own classes.
        Instantiation of the Tools classes.
        The order that the tools are installed is important as they can depend on each other install position.

        :return: None
        """
        self.distance_tool = Distance(self)
        self.distance_tool.install(icon=QtGui.QIcon(self.resource_location + '/distance16.png'), pos=self.ui.menuedit,
                                   before=self.ui.menueditorigin,
                                   separator=False)

        self.distance_min_tool = DistanceMin(self)
        self.distance_min_tool.install(icon=QtGui.QIcon(self.resource_location + '/distance_min16.png'),
                                       pos=self.ui.menuedit,
                                       before=self.ui.menueditorigin,
                                       separator=True)

        self.dblsidedtool = DblSidedTool(self)
        self.dblsidedtool.install(icon=QtGui.QIcon(self.resource_location + '/doubleside16.png'), separator=False)

        self.cal_exc_tool = ToolCalibration(self)
        self.cal_exc_tool.install(icon=QtGui.QIcon(self.resource_location + '/calibrate_16.png'), pos=self.ui.menutool,
                                  before=self.dblsidedtool.menuAction,
                                  separator=False)

        self.align_objects_tool = AlignObjects(self)
        self.align_objects_tool.install(icon=QtGui.QIcon(self.resource_location + '/align16.png'), separator=False)

        self.edrills_tool = ToolExtractDrills(self)
        self.edrills_tool.install(icon=QtGui.QIcon(self.resource_location + '/drill16.png'), separator=True)

        self.panelize_tool = Panelize(self)
        self.panelize_tool.install(icon=QtGui.QIcon(self.resource_location + '/panelize16.png'))

        self.film_tool = Film(self)
        self.film_tool.install(icon=QtGui.QIcon(self.resource_location + '/film16.png'))

        self.paste_tool = SolderPaste(self)
        self.paste_tool.install(icon=QtGui.QIcon(self.resource_location + '/solderpastebis32.png'))

        self.calculator_tool = ToolCalculator(self)
        self.calculator_tool.install(icon=QtGui.QIcon(self.resource_location + '/calculator16.png'), separator=True)

        self.sub_tool = ToolSub(self)
        self.sub_tool.install(icon=QtGui.QIcon(self.resource_location + '/sub32.png'),
                              pos=self.ui.menutool, separator=True)

        self.rules_tool = RulesCheck(self)
        self.rules_tool.install(icon=QtGui.QIcon(self.resource_location + '/rules32.png'),
                                pos=self.ui.menutool, separator=False)

        self.optimal_tool = ToolOptimal(self)
        self.optimal_tool.install(icon=QtGui.QIcon(self.resource_location + '/open_excellon32.png'),
                                  pos=self.ui.menutool, separator=True)

        self.move_tool = ToolMove(self)
        self.move_tool.install(icon=QtGui.QIcon(self.resource_location + '/move16.png'), pos=self.ui.menuedit,
                               before=self.ui.menueditorigin, separator=True)

        self.cutout_tool = CutOut(self)
        self.cutout_tool.install(icon=QtGui.QIcon(self.resource_location + '/cut16_bis.png'), pos=self.ui.menutool,
                                 before=self.sub_tool.menuAction)

        self.ncclear_tool = NonCopperClear(self)
        self.ncclear_tool.install(icon=QtGui.QIcon(self.resource_location + '/ncc16.png'), pos=self.ui.menutool,
                                  before=self.sub_tool.menuAction, separator=True)

        self.paint_tool = ToolPaint(self)
        self.paint_tool.install(icon=QtGui.QIcon(self.resource_location + '/paint16.png'), pos=self.ui.menutool,
                                before=self.sub_tool.menuAction, separator=True)

        self.copper_thieving_tool = ToolCopperThieving(self)
        self.copper_thieving_tool.install(icon=QtGui.QIcon(self.resource_location + '/copperfill32.png'),
                                          pos=self.ui.menutool)

        self.fiducial_tool = ToolFiducials(self)
        self.fiducial_tool.install(icon=QtGui.QIcon(self.resource_location + '/fiducials_32.png'),
                                   pos=self.ui.menutool)

        self.qrcode_tool = QRCode(self)
        self.qrcode_tool.install(icon=QtGui.QIcon(self.resource_location + '/qrcode32.png'),
                                 pos=self.ui.menutool)

        self.punch_tool = ToolPunchGerber(self)
        self.punch_tool.install(icon=QtGui.QIcon(self.resource_location + '/punch32.png'), pos=self.ui.menutool)

        self.invert_tool = ToolInvertGerber(self)
        self.invert_tool.install(icon=QtGui.QIcon(self.resource_location + '/invert32.png'), pos=self.ui.menutool)

        self.transform_tool = ToolTransform(self)
        self.transform_tool.install(icon=QtGui.QIcon(self.resource_location + '/transform.png'),
                                    pos=self.ui.menuoptions, separator=True)

        self.properties_tool = Properties(self)
        self.properties_tool.install(icon=QtGui.QIcon(self.resource_location + '/properties32.png'),
                                     pos=self.ui.menuoptions)

        self.pdf_tool = ToolPDF(self)
        self.pdf_tool.install(icon=QtGui.QIcon(self.resource_location + '/pdf32.png'),
                              pos=self.ui.menufileimport,
                              separator=True)

        self.image_tool = ToolImage(self)
        self.image_tool.install(icon=QtGui.QIcon(self.resource_location + '/image32.png'),
                                pos=self.ui.menufileimport,
                                separator=True)

        self.pcb_wizard_tool = PcbWizard(self)
        self.pcb_wizard_tool.install(icon=QtGui.QIcon(self.resource_location + '/drill32.png'),
                                     pos=self.ui.menufileimport)

        self.log.debug("Tools are installed.")

    def remove_tools(self):
        """
        Will remove all the actions in the Tool menu.
        :return: None
        """
        for act in self.ui.menutool.actions():
            self.ui.menutool.removeAction(act)

    def init_tools(self):
        """
        Initialize the Tool tab in the notebook side of the central widget.
        Remove the actions in the Tools menu.
        Instantiate again the FlatCAM tools (plugins).
        All this is required when changing the layout: standard, compact etc.

        :return: None
        """

        log.debug("init_tools()")

        # delete the data currently in the Tools Tab and the Tab itself
        widget = QtWidgets.QTabWidget.widget(self.ui.notebook, 2)
        if widget is not None:
            widget.deleteLater()
        self.ui.notebook.removeTab(2)

        # rebuild the Tools Tab
        self.ui.tool_tab = QtWidgets.QWidget()
        self.ui.tool_tab_layout = QtWidgets.QVBoxLayout(self.ui.tool_tab)
        self.ui.tool_tab_layout.setContentsMargins(2, 2, 2, 2)
        self.ui.notebook.addTab(self.ui.tool_tab, "Tool")
        self.ui.tool_scroll_area = VerticalScrollArea()
        self.ui.tool_tab_layout.addWidget(self.ui.tool_scroll_area)

        # reinstall all the Tools as some may have been removed when the data was removed from the Tools Tab
        # first remove all of them
        self.remove_tools()

        # re-add the TCL Shell action to the Tools menu and reconnect it to ist slot function
        self.ui.menutoolshell = self.ui.menutool.addAction(QtGui.QIcon(self.resource_location + '/shell16.png'),
                                                           '&Command Line\tS')
        self.ui.menutoolshell.triggered.connect(self.toggle_shell)

        # third install all of them
        try:
            self.install_tools()
        except AttributeError:
            pass

        self.log.debug("Tools are initialized.")

    # def parse_system_fonts(self):
    #     self.worker_task.emit({'fcn': self.f_parse.get_fonts_by_types,
    #                            'params': []})

    def connect_toolbar_signals(self):
        """
        Reconnect the signals to the actions in the toolbar.
        This has to be done each time after the FlatCAM tools are removed/installed.

        :return: None
        """

        # Toolbar
        # self.ui.file_new_btn.triggered.connect(self.on_file_new)
        self.ui.file_open_btn.triggered.connect(self.on_file_openproject)
        self.ui.file_save_btn.triggered.connect(self.on_file_saveproject)
        self.ui.file_open_gerber_btn.triggered.connect(self.on_fileopengerber)
        self.ui.file_open_excellon_btn.triggered.connect(self.on_fileopenexcellon)

        self.ui.clear_plot_btn.triggered.connect(self.clear_plots)
        self.ui.replot_btn.triggered.connect(self.plot_all)
        self.ui.zoom_fit_btn.triggered.connect(self.on_zoom_fit)
        self.ui.zoom_in_btn.triggered.connect(lambda: self.plotcanvas.zoom(1 / 1.5))
        self.ui.zoom_out_btn.triggered.connect(lambda: self.plotcanvas.zoom(1.5))

        self.ui.newgeo_btn.triggered.connect(self.new_geometry_object)
        self.ui.newgrb_btn.triggered.connect(self.new_gerber_object)
        self.ui.newexc_btn.triggered.connect(self.new_excellon_object)
        self.ui.editgeo_btn.triggered.connect(self.object2editor)
        self.ui.update_obj_btn.triggered.connect(lambda: self.editor2object())
        self.ui.copy_btn.triggered.connect(self.on_copy_command)
        self.ui.delete_btn.triggered.connect(self.on_delete)

        self.ui.distance_btn.triggered.connect(lambda: self.distance_tool.run(toggle=True))
        self.ui.distance_min_btn.triggered.connect(lambda: self.distance_min_tool.run(toggle=True))
        self.ui.origin_btn.triggered.connect(self.on_set_origin)
        self.ui.move2origin_btn.triggered.connect(self.on_move2origin)

        self.ui.jmp_btn.triggered.connect(self.on_jump_to)
        self.ui.locate_btn.triggered.connect(lambda: self.on_locate(obj=self.collection.get_active()))

        self.ui.shell_btn.triggered.connect(self.toggle_shell)
        self.ui.new_script_btn.triggered.connect(self.on_filenewscript)
        self.ui.open_script_btn.triggered.connect(self.on_fileopenscript)
        self.ui.run_script_btn.triggered.connect(self.on_filerunscript)

        # Tools Toolbar Signals
        self.ui.dblsided_btn.triggered.connect(lambda: self.dblsidedtool.run(toggle=True))
        self.ui.cal_btn.triggered.connect(lambda: self.cal_exc_tool.run(toggle=True))
        self.ui.align_btn.triggered.connect(lambda: self.align_objects_tool.run(toggle=True))
        self.ui.extract_btn.triggered.connect(lambda: self.edrills_tool.run(toggle=True))

        self.ui.cutout_btn.triggered.connect(lambda: self.cutout_tool.run(toggle=True))
        self.ui.ncc_btn.triggered.connect(lambda: self.ncclear_tool.run(toggle=True))
        self.ui.paint_btn.triggered.connect(lambda: self.paint_tool.run(toggle=True))

        self.ui.panelize_btn.triggered.connect(lambda: self.panelize_tool.run(toggle=True))
        self.ui.film_btn.triggered.connect(lambda: self.film_tool.run(toggle=True))
        self.ui.solder_btn.triggered.connect(lambda: self.paste_tool.run(toggle=True))
        self.ui.sub_btn.triggered.connect(lambda: self.sub_tool.run(toggle=True))
        self.ui.rules_btn.triggered.connect(lambda: self.rules_tool.run(toggle=True))
        self.ui.optimal_btn.triggered.connect(lambda: self.optimal_tool.run(toggle=True))

        self.ui.calculators_btn.triggered.connect(lambda: self.calculator_tool.run(toggle=True))
        self.ui.transform_btn.triggered.connect(lambda: self.transform_tool.run(toggle=True))
        self.ui.qrcode_btn.triggered.connect(lambda: self.qrcode_tool.run(toggle=True))
        self.ui.copperfill_btn.triggered.connect(lambda: self.copper_thieving_tool.run(toggle=True))
        self.ui.fiducials_btn.triggered.connect(lambda: self.fiducial_tool.run(toggle=True))
        self.ui.punch_btn.triggered.connect(lambda: self.punch_tool.run(toggle=True))
        self.ui.invert_btn.triggered.connect(lambda: self.invert_tool.run(toggle=True))

    def object2editor(self):
        """
        Send the current Geometry or Excellon object (if any) into the it's editor.

        :return: None
        """
        self.defaults.report_usage("object2editor()")

        # disable the objects menu as it may interfere with the Editors
        self.ui.menuobjects.setDisabled(True)

        edited_object = self.collection.get_active()

        if isinstance(edited_object, GerberObject) or isinstance(edited_object, GeometryObject) or \
                isinstance(edited_object, ExcellonObject):
            pass
        else:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Select a Geometry, Gerber or Excellon Object to edit."))
            return

        if isinstance(edited_object, GeometryObject):
            # store the Geometry Editor Toolbar visibility before entering in the Editor
            self.geo_editor.toolbar_old_state = True if self.ui.geo_edit_toolbar.isVisible() else False

            # we set the notebook to hidden
            # self.ui.splitter.setSizes([0, 1])

            if edited_object.multigeo is True:
                sel_rows = [item.row() for item in edited_object.ui.geo_tools_table.selectedItems()]

                if len(sel_rows) > 1:
                    self.inform.emit('[WARNING_NOTCL] %s' %
                                     _("Simultaneous editing of tools geometry in a MultiGeo Geometry "
                                       "is not possible.\n"
                                       "Edit only one geometry at a time."))

                # determine the tool dia of the selected tool
                selected_tooldia = float(edited_object.ui.geo_tools_table.item(sel_rows[0], 1).text())

                # now find the key in the edited_object.tools that has this tooldia
                multi_tool = 1
                for tool in edited_object.tools:
                    if edited_object.tools[tool]['tooldia'] == selected_tooldia:
                        multi_tool = tool
                        break

                self.geo_editor.edit_fcgeometry(edited_object, multigeo_tool=multi_tool)
            else:
                self.geo_editor.edit_fcgeometry(edited_object)

            # set call source to the Editor we go into
            self.call_source = 'geo_editor'

        elif isinstance(edited_object, ExcellonObject):
            # store the Excellon Editor Toolbar visibility before entering in the Editor
            self.exc_editor.toolbar_old_state = True if self.ui.exc_edit_toolbar.isVisible() else False

            if self.ui.splitter.sizes()[0] == 0:
                self.ui.splitter.setSizes([1, 1])

            self.exc_editor.edit_fcexcellon(edited_object)

            # set call source to the Editor we go into
            self.call_source = 'exc_editor'

        elif isinstance(edited_object, GerberObject):
            # store the Gerber Editor Toolbar visibility before entering in the Editor
            self.grb_editor.toolbar_old_state = True if self.ui.grb_edit_toolbar.isVisible() else False

            if self.ui.splitter.sizes()[0] == 0:
                self.ui.splitter.setSizes([1, 1])

            self.grb_editor.edit_fcgerber(edited_object)

            # set call source to the Editor we go into
            self.call_source = 'grb_editor'

            # reset the following variables so the UI is built again after edit
            edited_object.ui_build = False
            edited_object.build_aperture_storage = False

        # make sure that we can't select another object while in Editor Mode:
        # self.collection.view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.ui.project_frame.setDisabled(True)

        # delete any selection shape that might be active as they are not relevant in Editor
        self.delete_selection_shape()

        self.ui.plot_tab_area.setTabText(0, "EDITOR Area")
        self.ui.plot_tab_area.protectTab(0)
        self.inform.emit('[WARNING_NOTCL] %s' % _("Editor is activated ..."))

        self.should_we_save = True

    def editor2object(self, cleanup=None):
        """
        Transfers the Geometry or Excellon from it's editor to the current object.

        :return: None
        """
        self.defaults.report_usage("editor2object()")

        # re-enable the objects menu that was disabled on entry in Editor mode
        self.ui.menuobjects.setDisabled(False)

        # do not update a geometry or excellon object unless it comes out of an editor
        if self.call_source != 'app':
            edited_obj = self.collection.get_active()

            if cleanup is None:
                msgbox = QtWidgets.QMessageBox()
                msgbox.setText(_("Do you want to save the edited object?"))
                msgbox.setWindowTitle(_("Close Editor"))
                msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/save_as.png'))

                bt_yes = msgbox.addButton(_('Yes'), QtWidgets.QMessageBox.YesRole)
                bt_no = msgbox.addButton(_('No'), QtWidgets.QMessageBox.NoRole)
                bt_cancel = msgbox.addButton(_('Cancel'), QtWidgets.QMessageBox.RejectRole)

                msgbox.setDefaultButton(bt_yes)
                msgbox.exec_()
                response = msgbox.clickedButton()

                if response == bt_yes:
                    # clean the Tools Tab
                    self.ui.tool_scroll_area.takeWidget()
                    self.ui.tool_scroll_area.setWidget(QtWidgets.QWidget())
                    self.ui.notebook.setTabText(2, "Tool")

                    if isinstance(edited_obj, GeometryObject):
                        obj_type = "Geometry"
                        if cleanup is None:
                            self.geo_editor.update_fcgeometry(edited_obj)
                            # self.geo_editor.update_options(edited_obj)

                        self.geo_editor.deactivate()

                        # restore GUI to the Selected TAB
                        # Remove anything else in the GUI
                        self.ui.tool_scroll_area.takeWidget()

                        # update the geo object options so it is including the bounding box values
                        try:
                            xmin, ymin, xmax, ymax = edited_obj.bounds(flatten=True)
                            edited_obj.options['xmin'] = xmin
                            edited_obj.options['ymin'] = ymin
                            edited_obj.options['xmax'] = xmax
                            edited_obj.options['ymax'] = ymax
                        except AttributeError as e:
                            self.inform.emit('[WARNING] %s' % _("Object empty after edit."))
                            log.debug("App.editor2object() --> Geometry --> %s" % str(e))

                        edited_obj.build_ui()
                        self.inform.emit('[success] %s' % _("Editor exited. Editor content saved."))

                    elif isinstance(edited_obj, GerberObject):
                        obj_type = "Gerber"
                        if cleanup is None:
                            self.grb_editor.update_fcgerber()
                            self.grb_editor.update_options(edited_obj)
                        self.grb_editor.deactivate_grb_editor()

                        # delete the old object (the source object) if it was an empty one
                        try:
                            if len(edited_obj.solid_geometry) == 0:
                                old_name = edited_obj.options['name']
                                self.collection.set_active(old_name)
                                self.collection.delete_active()
                        except TypeError:
                            # if the solid_geometry is a single Polygon the len() will not work
                            # in any case, falling here means that we have something in the solid_geometry, even if only
                            # a single Polygon, therefore we pass this
                            pass

                        self.inform.emit('[success] %s' % _("Editor exited. Editor content saved."))

                        # restore GUI to the Selected TAB
                        # Remove anything else in the GUI
                        self.ui.selected_scroll_area.takeWidget()

                    elif isinstance(edited_obj, ExcellonObject):
                        obj_type = "Excellon"
                        if cleanup is None:
                            self.exc_editor.update_fcexcellon(edited_obj)
                            # self.exc_editor.update_options(edited_obj)

                        self.exc_editor.deactivate()

                        # restore GUI to the Selected TAB
                        # Remove anything else in the GUI
                        self.ui.tool_scroll_area.takeWidget()

                        # delete the old object (the source object) if it was an empty one
                        if len(edited_obj.drills) == 0 and len(edited_obj.slots) == 0:
                            old_name = edited_obj.options['name']
                            self.collection.delete_by_name(name=old_name)
                        self.inform.emit('[success] %s' % _("Editor exited. Editor content saved."))

                    else:
                        self.inform.emit('[WARNING_NOTCL] %s' %
                                         _("Select a Gerber, Geometry or Excellon Object to update."))
                        return

                    self.inform.emit('[selected] %s %s' % (obj_type, _("is updated, returning to App...")))
                elif response == bt_no:
                    # clean the Tools Tab
                    self.ui.tool_scroll_area.takeWidget()
                    self.ui.tool_scroll_area.setWidget(QtWidgets.QWidget())
                    self.ui.notebook.setTabText(2, "Tool")

                    self.inform.emit('[WARNING_NOTCL] %s' % _("Editor exited. Editor content was not saved."))

                    if isinstance(edited_obj, GeometryObject):
                        self.geo_editor.deactivate()
                        edited_obj.build_ui()
                    elif isinstance(edited_obj, GerberObject):
                        self.grb_editor.deactivate_grb_editor()
                        edited_obj.build_ui()
                    elif isinstance(edited_obj, ExcellonObject):
                        self.exc_editor.deactivate()
                        edited_obj.build_ui()
                    else:
                        self.inform.emit('[WARNING_NOTCL] %s' %
                                         _("Select a Gerber, Geometry or Excellon Object to update."))
                        return
                elif response == bt_cancel:
                    return

                # edited_obj.set_ui(edited_obj.ui_type(decimals=self.decimals))
                # edited_obj.build_ui()
                # Switch notebook to Selected page
                self.ui.notebook.setCurrentWidget(self.ui.selected_tab)
            else:
                if isinstance(edited_obj, GeometryObject):
                    self.geo_editor.deactivate()
                elif isinstance(edited_obj, GerberObject):
                    self.grb_editor.deactivate_grb_editor()
                elif isinstance(edited_obj, ExcellonObject):
                    self.exc_editor.deactivate()
                else:
                    self.inform.emit('[WARNING_NOTCL] %s' %
                                     _("Select a Gerber, Geometry or Excellon Object to update."))
                    return

            # if notebook is hidden we show it
            if self.ui.splitter.sizes()[0] == 0:
                self.ui.splitter.setSizes([1, 1])

            # restore the call_source to app
            self.call_source = 'app'

            edited_obj.plot()
            self.ui.plot_tab_area.setTabText(0, "Plot Area")
            self.ui.plot_tab_area.protectTab(0)

            # make sure that we reenable the selection on Project Tab after returning from Editor Mode:
            # self.collection.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            self.ui.project_frame.setDisabled(False)

    def get_last_folder(self):
        """
        Get the folder path from where the last file was opened.
        :return: String, last opened folder path
        """
        return self.defaults["global_last_folder"]

    def get_last_save_folder(self):
        """
        Get the folder path from where the last file was saved.
        :return: String, last saved folder path
        """
        loc = self.defaults["global_last_save_folder"]
        if loc is None:
            loc = self.defaults["global_last_folder"]
        if loc is None:
            loc = os.path.dirname(__file__)
        return loc

    def info(self, msg):
        """
        Informs the user. Normally on the status bar, optionally
        also on the shell.

        :param msg: Text to write.
        :return: None
        """

        # Type of message in brackets at the beginning of the message.
        match = re.search(r"\[(.*)\](.*)", msg)
        if match:
            level = match.group(1)
            msg_ = match.group(2)
            self.ui.fcinfo.set_status(str(msg_), level=level)

            if level.lower() == "error":
                self.shell_message(msg, error=True, show=True)
            elif level.lower() == "warning":
                self.shell_message(msg, warning=True, show=True)

            elif level.lower() == "error_notcl":
                self.shell_message(msg, error=True, show=False)

            elif level.lower() == "warning_notcl":
                self.shell_message(msg, warning=True, show=False)

            elif level.lower() == "success":
                self.shell_message(msg, success=True, show=False)

            elif level.lower() == "selected":
                self.shell_message(msg, selected=True, show=False)

            else:
                self.shell_message(msg, show=False)

        else:
            self.ui.fcinfo.set_status(str(msg), level="info")

            # make sure that if the message is to clear the infobar with a space
            # is not printed over and over on the shell
            if msg != '':
                self.shell_message(msg)

    def restore_toolbar_view(self):
        """
        Some toolbars may be hidden by user and here we restore the state of the toolbars visibility that
        was saved in the defaults dictionary.

        :return: None
        """
        tb = self.defaults["global_toolbar_view"]

        if tb & 1:
            self.ui.toolbarfile.setVisible(True)
        else:
            self.ui.toolbarfile.setVisible(False)

        if tb & 2:
            self.ui.toolbargeo.setVisible(True)
        else:
            self.ui.toolbargeo.setVisible(False)

        if tb & 4:
            self.ui.toolbarview.setVisible(True)
        else:
            self.ui.toolbarview.setVisible(False)

        if tb & 8:
            self.ui.toolbartools.setVisible(True)
        else:
            self.ui.toolbartools.setVisible(False)

        if tb & 16:
            self.ui.exc_edit_toolbar.setVisible(True)
        else:
            self.ui.exc_edit_toolbar.setVisible(False)

        if tb & 32:
            self.ui.geo_edit_toolbar.setVisible(True)
        else:
            self.ui.geo_edit_toolbar.setVisible(False)

        if tb & 64:
            self.ui.grb_edit_toolbar.setVisible(True)
        else:
            self.ui.grb_edit_toolbar.setVisible(False)

        if tb & 128:
            self.ui.snap_toolbar.setVisible(True)
        else:
            self.ui.snap_toolbar.setVisible(False)

        if tb & 256:
            self.ui.toolbarshell.setVisible(True)
        else:
            self.ui.toolbarshell.setVisible(False)

    def on_import_preferences(self):
        """
        Loads the application default settings from a saved file into
        ``self.defaults`` dictionary.

        :return: None
        """

        self.defaults.report_usage("on_import_preferences")
        App.log.debug("App.on_import_preferences()")

        # Show file chooser
        filter_ = "Config File (*.FlatConfig);;All Files (*.*)"
        try:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Import FlatCAM Preferences"),
                                                                 directory=self.data_path,
                                                                 filter=filter_)
        except TypeError:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Import FlatCAM Preferences"),
                                                                 filter=filter_)
        filename = str(filename)
        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return

        # Load in the defaults from the chosen file
        self.defaults.load(filename=filename)

        self.preferencesUiManager.on_preferences_edited()
        self.inform.emit('[success] %s: %s' % (_("Imported Defaults from"), filename))

    def on_export_preferences(self):
        """
        Save the defaults dictionary to a file.

        :return: None
        """
        self.defaults.report_usage("on_export_preferences")
        App.log.debug("on_export_preferences()")

        # defaults_file_content = None

        # Show file chooser
        date = str(datetime.today()).rpartition('.')[0]
        date = ''.join(c for c in date if c not in ':-')
        date = date.replace(' ', '_')
        filter__ = "Config File .FlatConfig (*.FlatConfig);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export FlatCAM Preferences"),
                directory=self.data_path + '/preferences_' + date,
                filter=filter__
            )
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export FlatCAM Preferences"), filter=filter__)
        filename = str(filename)
        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return

        # Update options
        self.preferencesUiManager.defaults_read_form()
        self.defaults.propagate_defaults()

        # Save update options
        try:
            self.defaults.write(filename=filename)
        except Exception:
            self.inform.emit('[ERROR_NOTCL] %s %s' % (_("Failed to write defaults to file."), str(filename)))
            return

        if self.defaults["global_open_style"] is False:
            self.file_opened.emit("preferences", filename)
        self.file_saved.emit("preferences", filename)
        self.inform.emit('[success] %s: %s' % (_("Exported preferences to"), filename))

    def save_to_file(self, content_to_save, txt_content):
        """
        Save something to a file.

        :return: None
        """
        self.defaults.report_usage("save_to_file")
        App.log.debug("save_to_file()")

        self.date = str(datetime.today()).rpartition('.')[0]
        self.date = ''.join(c for c in self.date if c not in ':-')
        self.date = self.date.replace(' ', '_')

        filter__ = "HTML File .html (*.html);;TXT File .txt (*.txt);;All Files (*.*)"
        path_to_save = self.defaults["global_last_save_folder"] if \
            self.defaults["global_last_save_folder"] is not None else self.data_path
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Save to file"),
                directory=path_to_save + '/file_' + self.date,
                filter=filter__
            )
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save to file"), filter=filter__)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            try:
                with open(filename, 'w') as f:
                    ___ = f.read()
            except PermissionError:
                self.inform.emit('[WARNING] %s' %
                                 _("Permission denied, saving not possible.\n"
                                   "Most likely another app is holding the file open and not accessible."))
                return
            except IOError:
                App.log.debug('Creating a new file ...')
                f = open(filename, 'w')
                f.close()
            except Exception:
                e = sys.exc_info()[0]
                App.log.error("Could not load the file.")
                App.log.error(str(e))
                self.inform.emit('[ERROR_NOTCL] %s' % _("Could not load the file."))
                return

            # Save content
            if filename.rpartition('.')[2].lower() == 'html':
                file_content = content_to_save
            else:
                file_content = txt_content

            try:
                with open(filename, "w") as f:
                    f.write(file_content)
            except Exception:
                self.inform.emit('[ERROR_NOTCL] %s %s' % (_("Failed to write defaults to file."), str(filename)))
                return

        self.inform.emit('[success] %s: %s' % (_("Exported file to"), filename))

    def save_geometry(self, x, y, width, height, notebook_width):
        """
        Will save the application geometry and positions in the defaults discitionary to be restored at the next
        launch of the application.

        :param x: X position of the main window
        :param y: Y position of the main window
        :param width: width of the main window
        :param height: height of the main window
        :param notebook_width: the notebook width is adjustable so it get saved here, too.

        :return: None
        """
        self.defaults["global_def_win_x"] = x
        self.defaults["global_def_win_y"] = y
        self.defaults["global_def_win_w"] = width
        self.defaults["global_def_win_h"] = height
        self.defaults["global_def_notebook_width"] = notebook_width
        self.preferencesUiManager.save_defaults()

    def restore_main_win_geom(self):
        try:
            self.ui.setGeometry(self.defaults["global_def_win_x"],
                                self.defaults["global_def_win_y"],
                                self.defaults["global_def_win_w"],
                                self.defaults["global_def_win_h"])
            self.ui.splitter.setSizes([self.defaults["global_def_notebook_width"], 0])
        except KeyError as e:
            log.debug("App.restore_main_win_geom() --> %s" % str(e))

    def message_dialog(self, title, message, kind="info"):
        """
        Builds and show a custom QMessageBox to be used in FlatCAM.

        :param title: title of the QMessageBox
        :param message: message to be displayed
        :param kind: type of QMessageBox; will display a specific icon.
        :return:
        """
        icon = {"info": QtWidgets.QMessageBox.Information,
                "warning": QtWidgets.QMessageBox.Warning,
                "error": QtWidgets.QMessageBox.Critical}[str(kind)]
        dlg = QtWidgets.QMessageBox(icon, title, message, parent=self.ui)
        dlg.setText(message)
        dlg.exec_()

    def register_recent(self, kind, filename):
        """
        Will register the files opened into record dictionaries. The FlatCAM projects has it's own
        dictionary.

        :param kind: type of file that was opened
        :param filename: the path and file name for the file that was opened
        :return:
        """
        self.log.debug("register_recent()")
        self.log.debug("   %s" % kind)
        self.log.debug("   %s" % filename)

        record = {'kind': str(kind), 'filename': str(filename)}
        if record in self.recent:
            return
        if record in self.recent_projects:
            return

        if record['kind'] == 'project':
            self.recent_projects.insert(0, record)
        else:
            self.recent.insert(0, record)

        if len(self.recent) > self.defaults['global_recent_limit']:  # Limit reached
            self.recent.pop()

        if len(self.recent_projects) > self.defaults['global_recent_limit']:  # Limit reached
            self.recent_projects.pop()

        try:
            f = open(self.data_path + '/recent.json', 'w')
        except IOError:
            App.log.error("Failed to open recent items file for writing.")
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _('Failed to open recent files file for writing.'))
            return

        json.dump(self.recent, f, default=to_dict, indent=2, sort_keys=True)
        f.close()

        try:
            fp = open(self.data_path + '/recent_projects.json', 'w')
        except IOError:
            App.log.error("Failed to open recent items file for writing.")
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _('Failed to open recent projects file for writing.'))
            return

        json.dump(self.recent_projects, fp, default=to_dict, indent=2, sort_keys=True)
        fp.close()

        # Re-build the recent items menu
        self.setup_recent_items()

    def new_object(self, kind, name, initialize, plot=True, autoselected=True):
        """
        Creates a new specialized FlatCAMObj and attaches it to the application,
        this is, updates the GUI accordingly, any other records and plots it.
        This method is thread-safe.

        Notes:
            * If the name is in use, the self.collection will modify it
              when appending it to the collection. There is no need to handle
              name conflicts here.

        :param kind: The kind of object to create. One of 'gerber', 'excellon', 'cncjob' and 'geometry'.
        :type kind: str
        :param name: Name for the object.
        :type name: str
        :param initialize: Function to run after creation of the object but before it is attached to the application.
        The function is called with 2 parameters: the new object and the App instance.
        :type initialize: function
        :param plot: If to plot the resulting object
        :param autoselected: if the resulting object is autoselected in the Project tab and therefore in the
        self.collection
        :return: None
        :rtype: None
        """

        App.log.debug("new_object()")
        obj_plot = plot
        obj_autoselected = autoselected

        t0 = time.time()  # Debug

        # ## Create object
        classdict = {
            "gerber": GerberObject,
            "excellon": ExcellonObject,
            "cncjob": CNCJobObject,
            "geometry": GeometryObject,
            "script": ScriptObject,
            "document": DocumentObject
        }

        App.log.debug("Calling object constructor...")

        # Object creation/instantiation
        obj = classdict[kind](name)

        obj.units = self.options["units"]

        # IMPORTANT
        # The key names in defaults and options dictionary's are not random:
        # they have to have in name first the type of the object (geometry, excellon, cncjob and gerber) or how it's
        # called here, the 'kind' followed by an underline. Above the App default values from self.defaults are
        # copied to self.options. After that, below, depending on the type of
        # object that is created, it will strip the name of the object and the underline (if the original key was
        # let's say "excellon_toolchange", it will strip the excellon_) and to the obj.options the key will become
        # "toolchange"

        for option in self.options:
            if option.find(kind + "_") == 0:
                oname = option[len(kind) + 1:]
                obj.options[oname] = self.options[option]

        obj.isHovering = False
        obj.notHovering = True

        # Initialize as per user request
        # User must take care to implement initialize
        # in a thread-safe way as is is likely that we
        # have been invoked in a separate thread.
        t1 = time.time()
        self.log.debug("%f seconds before initialize()." % (t1 - t0))
        try:
            return_value = initialize(obj, self)
        except Exception as e:
            msg = '[ERROR_NOTCL] %s' % _("An internal error has occurred. See shell.\n")
            msg += _("Object ({kind}) failed because: {error} \n\n").format(kind=kind, error=str(e))
            msg += traceback.format_exc()
            self.inform.emit(msg)
            return "fail"

        t2 = time.time()
        self.log.debug("%f seconds executing initialize()." % (t2 - t1))

        if return_value == 'fail':
            log.debug("Object (%s) parsing and/or geometry creation failed." % kind)
            return "fail"

        # Check units and convert if necessary
        # This condition CAN be true because initialize() can change obj.units
        if self.options["units"].upper() != obj.units.upper():
            self.inform.emit('%s: %s' % (_("Converting units to "), self.options["units"]))
            obj.convert_units(self.options["units"])
            t3 = time.time()
            self.log.debug("%f seconds converting units." % (t3 - t2))

        # Create the bounding box for the object and then add the results to the obj.options
        # But not for Scripts or for Documents
        if kind != 'document' and kind != 'script':
            try:
                xmin, ymin, xmax, ymax = obj.bounds()
                obj.options['xmin'] = xmin
                obj.options['ymin'] = ymin
                obj.options['xmax'] = xmax
                obj.options['ymax'] = ymax
            except Exception as e:
                log.warning("App.new_object() -> The object has no bounds properties. %s" % str(e))
                return "fail"

            try:
                if kind == 'excellon':
                    obj.fill_color = self.defaults["excellon_plot_fill"]
                    obj.outline_color = self.defaults["excellon_plot_line"]

                if kind == 'gerber':
                    obj.fill_color = self.defaults["gerber_plot_fill"]
                    obj.outline_color = self.defaults["gerber_plot_line"]
            except Exception as e:
                log.warning("App.new_object() -> setting colors error. %s" % str(e))

        # update the KeyWords list with the name of the file
        self.myKeywords.append(obj.options['name'])

        log.debug("Moving new object back to main thread.")

        # Move the object to the main thread and let the app know that it is available.
        obj.moveToThread(self.main_thread)
        self.object_created.emit(obj, obj_plot, obj_autoselected)

        return obj

    def new_excellon_object(self):
        """
        Creates a new, blank Excellon object.

        :return: None
        """
        self.defaults.report_usage("new_excellon_object()")

        self.new_object('excellon', 'new_exc', lambda x, y: None, plot=False)

    def new_geometry_object(self):
        """
        Creates a new, blank and single-tool Geometry object.

        :return: None
        """
        self.defaults.report_usage("new_geometry_object()")

        def initialize(obj, app):
            obj.multitool = False

        self.new_object('geometry', 'new_geo', initialize, plot=False)

    def new_gerber_object(self):
        """
        Creates a new, blank Gerber object.

        :return: None
        """
        self.defaults.report_usage("new_gerber_object()")

        def initialize(grb_obj, app):
            grb_obj.multitool = False
            grb_obj.source_file = []
            grb_obj.multigeo = False
            grb_obj.follow = False
            grb_obj.apertures = {}
            grb_obj.solid_geometry = []

            try:
                grb_obj.options['xmin'] = 0
                grb_obj.options['ymin'] = 0
                grb_obj.options['xmax'] = 0
                grb_obj.options['ymax'] = 0
            except KeyError:
                pass

        self.new_object('gerber', 'new_grb', initialize, plot=False)

    def new_script_object(self):
        """
        Creates a new, blank TCL Script object.

        :return: None
        """
        self.defaults.report_usage("new_script_object()")

        # commands_list = "# AddCircle, AddPolygon, AddPolyline, AddRectangle, AlignDrill, " \
        #                 "AlignDrillGrid, Bbox, Bounds, ClearShell, CopperClear,\n" \
        #                 "# Cncjob, Cutout, Delete, Drillcncjob, ExportDXF, ExportExcellon, ExportGcode,\n" \
        #                 "# ExportGerber, ExportSVG, Exteriors, Follow, GeoCutout, GeoUnion, GetNames,\n" \
        #                 "# GetSys, ImportSvg, Interiors, Isolate, JoinExcellon, JoinGeometry, " \
        #                 "ListSys, MillDrills,\n" \
        #                 "# MillSlots, Mirror, New, NewExcellon, NewGeometry, NewGerber, Nregions, " \
        #                 "Offset, OpenExcellon, OpenGCode, OpenGerber, OpenProject,\n" \
        #                 "# Options, Paint, Panelize, PlotAl, PlotObjects, SaveProject, " \
        #                 "SaveSys, Scale, SetActive, SetSys, SetOrigin, Skew, SubtractPoly,\n" \
        #                 "# SubtractRectangle, Version, WriteGCode\n"

        new_source_file = '# %s\n' % _('CREATE A NEW FLATCAM TCL SCRIPT') + \
                          '# %s:\n' % _('TCL Tutorial is here') + \
                          '# https://www.tcl.tk/man/tcl8.5/tutorial/tcltutorial.html\n' + '\n\n' + \
                          '# %s:\n' % _("FlatCAM commands list")
        new_source_file += '# %s\n\n' % _("Type >help< followed by Run Code for a list of FlatCAM Tcl Commands "
                                          "(displayed in Tcl Shell).")

        def initialize(obj, app):
            obj.source_file = deepcopy(new_source_file)

        outname = 'new_script'
        self.new_object('script', outname, initialize, plot=False)

    def new_document_object(self):
        """
        Creates a new, blank Document object.

        :return: None
        """
        self.defaults.report_usage("new_document_object()")

        def initialize(obj, app):
            obj.source_file = ""

        self.new_object('document', 'new_document', initialize, plot=False)

    def on_object_created(self, obj, plot, auto_select):
        """
        Event callback for object creation.
        It will add the new object to the collection. After that it will plot the object in a threaded way

        :param obj: The newly created FlatCAM object.
        :param plot: if the newly create object t obe plotted
        :param auto_select: if the newly created object to be autoselected after creation
        :return: None
        """
        t0 = time.time()  # DEBUG
        self.log.debug("on_object_created()")

        # The Collection might change the name if there is a collision
        self.collection.append(obj)

        # after adding the object to the collection always update the list of objects that are in the collection
        self.all_objects_list = self.collection.get_list()

        # self.inform.emit('[selected] %s created & selected: %s' %
        #                  (str(obj.kind).capitalize(), str(obj.options['name'])))
        if obj.kind == 'gerber':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='green',
                name=str(obj.options['name']), tx=_("created/selected"))
            )
        elif obj.kind == 'excellon':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='brown',
                name=str(obj.options['name']), tx=_("created/selected"))
            )
        elif obj.kind == 'cncjob':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='blue',
                name=str(obj.options['name']), tx=_("created/selected"))
            )
        elif obj.kind == 'geometry':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='red',
                name=str(obj.options['name']), tx=_("created/selected"))
            )
        elif obj.kind == 'script':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='orange',
                name=str(obj.options['name']), tx=_("created/selected"))
            )
        elif obj.kind == 'document':
            self.inform.emit('[selected] {kind} {tx}: <span style="color:{color};">{name}</span>'.format(
                kind=obj.kind.capitalize(),
                color='darkCyan',
                name=str(obj.options['name']), tx=_("created/selected"))
            )

        # update the SHELL auto-completer model with the name of the new object
        self.shell._edit.set_model_data(self.myKeywords)

        if auto_select:
            # select the just opened object but deselect the previous ones
            self.collection.set_all_inactive()
            self.collection.set_active(obj.options["name"])
        else:
            self.collection.set_all_inactive()

        # here it is done the object plotting
        def worker_task(t_obj):
            with self.proc_container.new(_("Plotting")):
                if isinstance(t_obj, CNCJobObject):
                    t_obj.plot(kind=self.defaults["cncjob_plot_kind"])
                else:
                    t_obj.plot()
                t1 = time.time()  # DEBUG
                self.log.debug("%f seconds adding object and plotting." % (t1 - t0))
                self.object_plotted.emit(t_obj)

        # Send to worker
        # self.worker.add_task(worker_task, [self])
        if plot is True:
            self.worker_task.emit({'fcn': worker_task, 'params': [obj]})

    def on_object_changed(self, obj):
        """
        Called whenever the geometry of the object was changed in some way.
        This require the update of it's bounding values so it can be the selected on canvas.
        Update the bounding box data from obj.options

        :param obj: the object that was changed
        :return: None
        """

        xmin, ymin, xmax, ymax = obj.bounds()
        obj.options['xmin'] = xmin
        obj.options['ymin'] = ymin
        obj.options['xmax'] = xmax
        obj.options['ymax'] = ymax

        log.debug("Object changed, updating the bounding box data on self.options")
        # delete the old selection shape
        self.delete_selection_shape()
        self.should_we_save = True

    def on_object_plotted(self):
        """
        Callback called whenever the plotted object needs to be fit into the viewport (canvas)

        :return: None
        """
        self.on_zoom_fit(None)

    def on_about(self):
        """
        Displays the "about" dialog found in the Menu --> Help.

        :return: None
        """
        self.defaults.report_usage("on_about")

        version = self.version
        version_date = self.version_date
        beta = self.beta

        class AboutDialog(QtWidgets.QDialog):
            def __init__(self, app, parent=None):
                QtWidgets.QDialog.__init__(self, parent)

                self.app = app

                # Icon and title
                self.setWindowIcon(parent.app_icon)
                self.setWindowTitle(_("About FlatCAM"))
                self.resize(600, 200)
                # self.setStyleSheet("background-image: url(share/flatcam_icon256.png); background-attachment: fixed")
                # self.setStyleSheet(
                #     "border-image: url(share/flatcam_icon256.png) 0 0 0 0 stretch stretch; "
                #     "background-attachment: fixed"
                # )

                # bgimage = QtGui.QImage(self.resource_location + '/flatcam_icon256.png')
                # s_bgimage = bgimage.scaled(QtCore.QSize(self.frameGeometry().width(), self.frameGeometry().height()))
                # palette = QtGui.QPalette()
                # palette.setBrush(10, QtGui.QBrush(bgimage))  # 10 = Windowrole
                # self.setPalette(palette)

                logo = QtWidgets.QLabel()
                logo.setPixmap(QtGui.QPixmap(self.app.resource_location + '/flatcam_icon256.png'))

                title = QtWidgets.QLabel(
                    "<font size=8><B>FlatCAM</B></font><BR>"
                    "{title}<BR>"
                    "<BR>"
                    "<BR>"
                    "<a href = \"https://bitbucket.org/jpcgt/flatcam/src/Beta/\"><B>{devel}</B></a><BR>"
                    "<a href = \"https://bitbucket.org/jpcgt/flatcam/downloads/\"><b>{down}</B></a><BR>"
                    "<a href = \"https://bitbucket.org/jpcgt/flatcam/issues?status=new&status=open/\">"
                    "<B>{issue}</B></a><BR>".format(
                        title=_("2D Computer-Aided Printed Circuit Board Manufacturing"),
                        devel=_("Development"),
                        down=_("DOWNLOAD"),
                        issue=_("Issue tracker"))
                )
                title.setOpenExternalLinks(True)

                closebtn = QtWidgets.QPushButton(_("Close"))

                tab_widget = QtWidgets.QTabWidget()
                description_label = QtWidgets.QLabel(
                    "FlatCAM {version} {beta} ({date}) - {arch}<br>"
                    "<a href = \"http://flatcam.org/\">http://flatcam.org</a><br>".format(
                        version=version,
                        beta=('BETA' if beta else ''),
                        date=version_date,
                        arch=platform.architecture()[0])
                )
                description_label.setOpenExternalLinks(True)

                lic_lbl_header = QtWidgets.QLabel(
                    '%s:<br>%s<br>' % (
                        _('Licensed under the MIT license'),
                        "<a href = \"http://www.opensource.org/licenses/mit-license.php\">"
                        "http://www.opensource.org/licenses/mit-license.php</a>"
                    )
                )
                lic_lbl_header.setOpenExternalLinks(True)

                lic_lbl_body = QtWidgets.QLabel(
                    _(
                        'Permission is hereby granted, free of charge, to any person obtaining a copy\n'
                        'of this software and associated documentation files (the "Software"), to deal\n'
                        'in the Software without restriction, including without limitation the rights\n'
                        'to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n'
                        'copies of the Software, and to permit persons to whom the Software is\n'
                        'furnished to do so, subject to the following conditions:\n\n'

                        'The above copyright notice and this permission notice shall be included in\n'
                        'all copies or substantial portions of the Software.\n\n'

                        'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
                        'IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n'
                        'FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n'
                        'AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n'
                        'LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n'
                        'OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN\n'
                        'THE SOFTWARE.'
                    )
                )

                attributions_label = QtWidgets.QLabel(
                    _(
                        'Some of the icons used are from the following sources:<br>'
                        '<div>Icons by <a href="https://www.flaticon.com/authors/freepik" '
                        'title="Freepik">Freepik</a> from <a href="https://www.flaticon.com/"             '
                        'title="Flaticon">www.flaticon.com</a></div>'
                        '<div>Icons by <a target="_blank" href="https://icons8.com">Icons8</a></div>'
                        'Icons by <a href="http://www.onlinewebfonts.com">oNline Web Fonts</a>'
                    )
                )
                attributions_label.setOpenExternalLinks(True)

                # layouts
                layout1 = QtWidgets.QVBoxLayout()
                layout1_1 = QtWidgets.QHBoxLayout()
                layout1_2 = QtWidgets.QHBoxLayout()

                layout2 = QtWidgets.QHBoxLayout()
                layout3 = QtWidgets.QHBoxLayout()

                self.setLayout(layout1)
                layout1.addLayout(layout1_1)
                layout1.addLayout(layout1_2)

                layout1.addLayout(layout2)
                layout1.addLayout(layout3)

                layout1_1.addStretch()
                layout1_1.addWidget(description_label)
                layout1_2.addWidget(tab_widget)

                self.splash_tab = QtWidgets.QWidget()
                self.splash_tab.setObjectName("splash_about")
                self.splash_tab_layout = QtWidgets.QHBoxLayout(self.splash_tab)
                self.splash_tab_layout.setContentsMargins(2, 2, 2, 2)
                tab_widget.addTab(self.splash_tab, _("Splash"))

                self.programmmers_tab = QtWidgets.QWidget()
                self.programmmers_tab.setObjectName("programmers_about")
                self.programmmers_tab_layout = QtWidgets.QVBoxLayout(self.programmmers_tab)
                self.programmmers_tab_layout.setContentsMargins(2, 2, 2, 2)
                tab_widget.addTab(self.programmmers_tab, _("Programmers"))

                self.translators_tab = QtWidgets.QWidget()
                self.translators_tab.setObjectName("translators_about")
                self.translators_tab_layout = QtWidgets.QVBoxLayout(self.translators_tab)
                self.translators_tab_layout.setContentsMargins(2, 2, 2, 2)
                tab_widget.addTab(self.translators_tab, _("Translators"))

                self.license_tab = QtWidgets.QWidget()
                self.license_tab.setObjectName("license_about")
                self.license_tab_layout = QtWidgets.QVBoxLayout(self.license_tab)
                self.license_tab_layout.setContentsMargins(2, 2, 2, 2)
                tab_widget.addTab(self.license_tab, _("License"))

                self.attributions_tab = QtWidgets.QWidget()
                self.attributions_tab.setObjectName("attributions_about")
                self.attributions_tab_layout = QtWidgets.QVBoxLayout(self.attributions_tab)
                self.attributions_tab_layout.setContentsMargins(2, 2, 2, 2)
                tab_widget.addTab(self.attributions_tab, _("Attributions"))

                self.splash_tab_layout.addWidget(logo, stretch=0)
                self.splash_tab_layout.addWidget(title, stretch=1)

                pal = QtGui.QPalette()
                pal.setColor(QtGui.QPalette.Background, Qt.white)

                self.prog_grid_lay = QtWidgets.QGridLayout()
                self.prog_grid_lay.setHorizontalSpacing(20)
                self.prog_grid_lay.setColumnStretch(0, 0)
                self.prog_grid_lay.setColumnStretch(2, 1)

                prog_widget = QtWidgets.QWidget()
                prog_widget.setLayout(self.prog_grid_lay)
                prog_scroll = QtWidgets.QScrollArea()
                prog_scroll.setWidget(prog_widget)
                prog_scroll.setWidgetResizable(True)
                prog_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
                prog_scroll.setPalette(pal)

                self.programmmers_tab_layout.addWidget(prog_scroll)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("Programmer")), 0, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("Status")), 0, 1)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("E-mail")), 0, 2)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Juan Pablo Caram"), 1, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % _("Program Author")), 1, 1)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<>"), 1, 2)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Denis Hayrullin"), 2, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Kamil Sopko"), 3, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marius Stanciu"), 4, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % _("BETA Maintainer >= 2019")), 4, 1)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<marius_adrian@yahoo.com>"), 4, 2)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 5, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "David Robertson"), 6, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Matthieu Berthomé"), 7, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Mike Evans"), 8, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Victor Benso"), 9, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 10, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Jørn Sandvik Nilsson"), 12, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Lei Zheng"), 13, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Leandro Heck"), 14, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marco A Quezada"), 15, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 16, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Cedric Dussud"), 20, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Chris Hemingway"), 22, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Damian Wrobel"), 24, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Daniel Sallin"), 28, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 32, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Bruno Vunderl"), 40, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Gonzalo Lopez"), 42, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Jakob Staudt"), 45, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Mike Smith"), 49, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 52, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Barnaby Walters"), 55, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Steve Martina"), 57, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Thomas Duffin"), 59, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Andrey Kultyapov"), 61, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 63, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Alex Lazar"), 64, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Chris Breneman"), 65, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Eric Varsanyi"), 67, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Lubos Medovarsky"), 69, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel(''), 74, 0)

                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "@Idechix"), 100, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "@SM"), 101, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "@grbf"), 102, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "@Symonty"), 103, 0)
                self.prog_grid_lay.addWidget(QtWidgets.QLabel('%s' % "@mgix"), 104, 0)

                self.translator_grid_lay = QtWidgets.QGridLayout()
                self.translator_grid_lay.setColumnStretch(0, 0)
                self.translator_grid_lay.setColumnStretch(1, 0)
                self.translator_grid_lay.setColumnStretch(2, 1)
                self.translator_grid_lay.setColumnStretch(3, 0)

                # trans_widget = QtWidgets.QWidget()
                # trans_widget.setLayout(self.translator_grid_lay)
                # self.translators_tab_layout.addWidget(trans_widget)
                # self.translators_tab_layout.addStretch()

                trans_widget = QtWidgets.QWidget()
                trans_widget.setLayout(self.translator_grid_lay)
                trans_scroll = QtWidgets.QScrollArea()
                trans_scroll.setWidget(trans_widget)
                trans_scroll.setWidgetResizable(True)
                trans_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
                trans_scroll.setPalette(pal)
                self.translators_tab_layout.addWidget(trans_scroll)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("Language")), 0, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("Translator")), 0, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("Corrections")), 0, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('<b>%s</b>' % _("E-mail")), 0, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "BR - Portuguese"), 1, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Carlos Stein"), 1, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<carlos.stein@gmail.com>"), 1, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "French"), 2, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marius Stanciu (Google-Tr)"), 2, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % ""), 2, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 2, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Hungarian"), 3, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 3, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 3, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 3, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Italian"), 4, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Golfetto Massimiliano"), 4, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 4, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<golfetto.pcb@gmail.com>"), 4, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "German"), 5, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marius Stanciu (Google-Tr)"), 5, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Jens Karstedt, Detlef Eckardt"), 5, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 5, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Romanian"), 6, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marius Stanciu"), 6, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<marius_adrian@yahoo.com>"), 6, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Russian"), 7, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Andrey Kultyapov"), 7, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "<camellan@yandex.ru>"), 7, 3)

                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Spanish"), 8, 0)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % "Marius Stanciu (Google-Tr)"), 8, 1)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % ""), 8, 2)
                self.translator_grid_lay.addWidget(QtWidgets.QLabel('%s' % " "), 8, 3)
                self.translator_grid_lay.setColumnStretch(0, 0)
                self.translators_tab_layout.addStretch()

                self.license_tab_layout.addWidget(lic_lbl_header)
                self.license_tab_layout.addWidget(lic_lbl_body)

                self.license_tab_layout.addStretch()

                self.attributions_tab_layout.addWidget(attributions_label)
                self.attributions_tab_layout.addStretch()

                layout3.addStretch()
                layout3.addWidget(closebtn)

                closebtn.clicked.connect(self.accept)

        AboutDialog(app=self, parent=self.ui).exec_()

    def install_bookmarks(self, book_dict=None):
        """
        Install the bookmarks actions in the Help menu -> Bookmarks

        :param book_dict: a dict having the actions text as keys and the weblinks as the values
        :return: None
        """

        if book_dict is None:
            self.defaults["global_bookmarks"].update(
                {
                    '1': ['FlatCAM', "http://flatcam.org"],
                    '2': ['Backup Site', ""]
                }
            )
        else:
            self.defaults["global_bookmarks"].clear()
            self.defaults["global_bookmarks"].update(book_dict)

        # first try to disconnect if somehow they get connected from elsewhere
        for act in self.ui.menuhelp_bookmarks.actions():
            try:
                act.triggered.disconnect()
            except TypeError:
                pass

            # clear all actions except the last one who is the Bookmark manager
            if act is self.ui.menuhelp_bookmarks.actions()[-1]:
                pass
            else:
                self.ui.menuhelp_bookmarks.removeAction(act)

        bm_limit = int(self.defaults["global_bookmarks_limit"])
        if self.defaults["global_bookmarks"]:

            # order the self.defaults["global_bookmarks"] dict keys by the value as integer
            # the whole convoluted things is because when serializing the self.defaults (on app close or save)
            # the JSON is first making the keys as strings (therefore I have to use strings too
            # or do the conversion :(
            # )
            # and it is ordering them (actually I want that to make the defaults easy to search within) but making
            # the '10' entry jsut after '1' therefore ordering as strings

            sorted_bookmarks = sorted(list(self.defaults["global_bookmarks"].items())[:bm_limit],
                                      key=lambda x: int(x[0]))
            for entry, bookmark in sorted_bookmarks:
                title = bookmark[0]
                weblink = bookmark[1]

                act = QtWidgets.QAction(parent=self.ui.menuhelp_bookmarks)
                act.setText(title)

                act.setIcon(QtGui.QIcon(self.resource_location + '/link16.png'))
                # from here: https://stackoverflow.com/questions/20390323/pyqt-dynamic-generate-qmenu-action-and-connect
                if title == 'Backup Site' and weblink == "":
                    act.triggered.connect(self.on_backup_site)
                else:
                    act.triggered.connect(lambda sig, link=weblink: webbrowser.open(link))
                self.ui.menuhelp_bookmarks.insertAction(self.ui.menuhelp_bookmarks_manager, act)

        self.ui.menuhelp_bookmarks_manager.triggered.connect(self.on_bookmarks_manager)

    def on_bookmarks_manager(self):
        """
        Adds the bookmark manager in a Tab in Plot Area
        :return:
        """
        for idx in range(self.ui.plot_tab_area.count()):
            if self.ui.plot_tab_area.tabText(idx) == _("Bookmarks Manager"):
                # there can be only one instance of Bookmark Manager at one time
                return

        # BookDialog(app=self, storage=self.defaults["global_bookmarks"], parent=self.ui).exec_()
        self.book_dialog_tab = BookmarkManager(app=self, storage=self.defaults["global_bookmarks"], parent=self.ui)
        self.book_dialog_tab.setObjectName("bookmarks_tab")

        # add the tab if it was closed
        self.ui.plot_tab_area.addTab(self.book_dialog_tab, _("Bookmarks Manager"))

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        # Switch plot_area to preferences page
        self.ui.plot_tab_area.setCurrentWidget(self.book_dialog_tab)

    def on_backup_site(self):
        msgbox = QtWidgets.QMessageBox()
        msgbox.setText(_("This entry will resolve to another website if:\n\n"
                         "1. FlatCAM.org website is down\n"
                         "2. Someone forked FlatCAM project and wants to point\n"
                         "to his own website\n\n"
                         "If you can't get any informations about FlatCAM beta\n"
                         "use the YouTube channel link from the Help menu."))

        msgbox.setWindowTitle(_("Alternative website"))
        msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/globe16.png'))
        bt_yes = msgbox.addButton(_('Close'), QtWidgets.QMessageBox.YesRole)

        msgbox.setDefaultButton(bt_yes)
        msgbox.exec_()
        # response = msgbox.clickedButton()

    def on_file_savedefaults(self):
        """
        Callback for menu item File->Save Defaults. Saves application default options
        ``self.defaults`` to current_defaults.FlatConfig.

        :return: None
        """
        self.preferencesUiManager.save_defaults()

    def final_save(self):
        """
        Callback for doing a preferences save to file whenever the application is about to quit.
        If the project has changes, it will ask the user to save the project.

        :return: None
        """

        if self.save_in_progress:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Application is saving the project. Please wait ..."))
            return

        if self.should_we_save and self.collection.get_list():
            msgbox = QtWidgets.QMessageBox()
            msgbox.setText(_("There are files/objects modified in FlatCAM. "
                             "\n"
                             "Do you want to Save the project?"))
            msgbox.setWindowTitle(_("Save changes"))
            msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/save_as.png'))
            bt_yes = msgbox.addButton(_('Yes'), QtWidgets.QMessageBox.YesRole)
            bt_no = msgbox.addButton(_('No'), QtWidgets.QMessageBox.NoRole)
            bt_cancel = msgbox.addButton(_('Cancel'), QtWidgets.QMessageBox.RejectRole)

            msgbox.setDefaultButton(bt_yes)
            msgbox.exec_()
            response = msgbox.clickedButton()

            if response == bt_yes:
                try:
                    self.trayIcon.hide()
                except Exception:
                    pass
                self.on_file_saveprojectas(use_thread=True, quit_action=True)
            elif response == bt_no:
                try:
                    self.trayIcon.hide()
                except Exception:
                    pass
                self.quit_application()
            elif response == bt_cancel:
                return
        else:
            try:
                self.trayIcon.hide()
            except Exception:
                pass
            self.quit_application()

    def quit_application(self):
        """
        Called (as a pyslot or not) when the application is quit.

        :return: None
        """
        self.preferencesUiManager.save_defaults(silent=True)
        log.debug("App.quit_application() --> App Defaults saved.")

        if self.cmd_line_headless != 1:
            # save app state to file
            stgs = QSettings("Open Source", "FlatCAM")
            stgs.setValue('saved_gui_state', self.ui.saveState())
            stgs.setValue('maximized_gui', self.ui.isMaximized())
            stgs.setValue(
                'language',
                self.preferencesUiManager.get_form_field("global_language").get_value()
            )
            stgs.setValue(
                'notebook_font_size',
                self.preferencesUiManager.get_form_field("notebook_font_size").get_value()
            )
            stgs.setValue(
                'axis_font_size',
                self.preferencesUiManager.get_form_field("axis_font_size").get_value()
            )
            stgs.setValue(
                'textbox_font_size',
                self.preferencesUiManager.get_form_field("textbox_font_size").get_value()
            )
            stgs.setValue('toolbar_lock', self.ui.lock_action.isChecked())
            stgs.setValue(
                'machinist',
                1 if self.preferencesUiManager.get_form_field("global_machinist_setting").get_value() else 0
            )

            # This will write the setting to the platform specific storage.
            del stgs

        log.debug("App.quit_application() --> App UI state saved.")

        # try to quit the Socket opened by ArgsThread class
        try:
            self.new_launch.stop.emit()
        except Exception as err:
            log.debug("App.quit_application() --> %s" % str(err))

        # try to quit the QThread that run ArgsThread class
        try:
            self.th.quit()
        except Exception as e:
            log.debug("App.quit_application() --> %s" % str(e))

        # terminate workers
        self.workers.__del__()

        # quit app by signalling for self.kill_app() method
        # self.close_app_signal.emit()
        QtWidgets.qApp.quit()

        # When the main event loop is not started yet in which case the qApp.quit() will do nothing
        # we use the following command
        minor_v = sys.version_info.minor
        if minor_v < 8:
            sys.exit(0)
        else:
            os._exit(0)  # fix to work with Python 3.8

    @staticmethod
    def kill_app():
        QtWidgets.qApp.quit()
        # When the main event loop is not started yet in which case the qApp.quit() will do nothing
        # we use the following command
        sys.exit(0)

    def on_portable_checked(self, state):
        """
        Callback called when the checkbox in Preferences GUI is checked.
        It will set the application as portable by creating the preferences and recent files in the
        'config' folder found in the FlatCAM installation folder.

        :param state: boolean, the state of the checkbox when clicked/checked
        :return:
        """

        line_no = 0
        data = None

        if sys.platform != 'win32':
            # this won't work in Linux or MacOS
            return

        # test if the app was frozen and choose the path for the configuration file
        if getattr(sys, "frozen", False) is True:
            current_data_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\config'
        else:
            current_data_path = os.path.dirname(os.path.realpath(__file__)) + '\\config'

        config_file = current_data_path + '\\configuration.txt'
        try:
            with open(config_file, 'r') as f:
                try:
                    data = f.readlines()
                except Exception as e:
                    log.debug('App.__init__() -->%s' % str(e))
                    return
        except FileNotFoundError:
            pass

        for line in data:
            line = line.strip('\n')
            param = str(line).rpartition('=')
            if param[0] == 'portable':
                break
            line_no += 1

        if state:
            data[line_no] = 'portable=True\n'
            # create the new defauults files
            # create current_defaults.FlatConfig file if there is none
            try:
                f = open(current_data_path + '/current_defaults.FlatConfig')
                f.close()
            except IOError:
                App.log.debug('Creating empty current_defaults.FlatConfig')
                f = open(current_data_path + '/current_defaults.FlatConfig', 'w')
                json.dump({}, f)
                f.close()

            # create factory_defaults.FlatConfig file if there is none
            try:
                f = open(current_data_path + '/factory_defaults.FlatConfig')
                f.close()
            except IOError:
                App.log.debug('Creating empty factory_defaults.FlatConfig')
                f = open(current_data_path + '/factory_defaults.FlatConfig', 'w')
                json.dump({}, f)
                f.close()

            try:
                f = open(current_data_path + '/recent.json')
                f.close()
            except IOError:
                App.log.debug('Creating empty recent.json')
                f = open(current_data_path + '/recent.json', 'w')
                json.dump([], f)
                f.close()

            try:
                fp = open(current_data_path + '/recent_projects.json')
                fp.close()
            except IOError:
                App.log.debug('Creating empty recent_projects.json')
                fp = open(current_data_path + '/recent_projects.json', 'w')
                json.dump([], fp)
                fp.close()

            # save the current defaults to the new defaults file
            self.preferencesUiManager.save_defaults(silent=True, data_path=current_data_path)

        else:
            data[line_no] = 'portable=False\n'

        with open(config_file, 'w') as f:
            f.writelines(data)

    def on_register_files(self, obj_type=None):
        """
        Called whenever there is a need to register file extensions with FlatCAM.
        Works only in Windows and should be called only when FlatCAM is run in Windows.

        :param obj_type: the type of object to be register for.
        Can be: 'gerber', 'excellon' or 'gcode'. 'geometry' is not used for the moment.

        :return: None
        """
        log.debug("Manufacturing files extensions are registered with FlatCAM.")

        new_reg_path = 'Software\\Classes\\'
        # find if the current user is admin
        try:
            is_admin = os.getuid() == 0
        except AttributeError:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() == 1

        if is_admin is True:
            root_path = winreg.HKEY_LOCAL_MACHINE
        else:
            root_path = winreg.HKEY_CURRENT_USER

        # create the keys
        def set_reg(name, root_pth, new_reg_path, value):
            try:
                winreg.CreateKey(root_pth, new_reg_path)
                with winreg.OpenKey(root_pth, new_reg_path, 0, winreg.KEY_WRITE) as registry_key:
                    winreg.SetValueEx(registry_key, name, 0, winreg.REG_SZ, value)
                return True
            except WindowsError:
                return False

        # delete key in registry
        def delete_reg(root_pth, reg_path, key_to_del):
            key_to_del_path = reg_path + key_to_del
            try:
                winreg.DeleteKey(root_pth, key_to_del_path)
                return True
            except WindowsError:
                return False

        if obj_type is None or obj_type == 'excellon':
            exc_list = \
                self.ui.util_defaults_form.fa_excellon_group.exc_list_text.get_value().replace(' ', '').split(',')
            exc_list = [x for x in exc_list if x != '']

            # register all keys in the Preferences window
            for ext in exc_list:
                new_k = new_reg_path + '.%s' % ext
                set_reg('', root_path=root_path, new_reg_path=new_k, value='FlatCAM')

            # and unregister those that are no longer in the Preferences windows but are in the file
            for ext in self.defaults["fa_excellon"].replace(' ', '').split(','):
                if ext not in exc_list:
                    delete_reg(root_path=root_path, reg_path=new_reg_path, key_to_del='.%s' % ext)

            # now write the updated extensions to the self.defaults
            # new_ext = ''
            # for ext in exc_list:
            #     new_ext = new_ext + ext + ', '
            # self.defaults["fa_excellon"] = new_ext
            self.inform.emit('[success] %s' % _("Selected Excellon file extensions registered with FlatCAM."))

        if obj_type is None or obj_type == 'gcode':
            gco_list = self.ui.util_defaults_form.fa_gcode_group.gco_list_text.get_value().replace(' ', '').split(',')
            gco_list = [x for x in gco_list if x != '']

            # register all keys in the Preferences window
            for ext in gco_list:
                new_k = new_reg_path + '.%s' % ext
                set_reg('', root_path=root_path, new_reg_path=new_k, value='FlatCAM')

            # and unregister those that are no longer in the Preferences windows but are in the file
            for ext in self.defaults["fa_gcode"].replace(' ', '').split(','):
                if ext not in gco_list:
                    delete_reg(root_path=root_path, reg_path=new_reg_path, key_to_del='.%s' % ext)

            # now write the updated extensions to the self.defaults
            # new_ext = ''
            # for ext in gco_list:
            #     new_ext = new_ext + ext + ', '
            # self.defaults["fa_gcode"] = new_ext
            self.inform.emit('[success] %s' %
                             _("Selected GCode file extensions registered with FlatCAM."))

        if obj_type is None or obj_type == 'gerber':
            grb_list = self.ui.util_defaults_form.fa_gerber_group.grb_list_text.get_value().replace(' ', '').split(',')
            grb_list = [x for x in grb_list if x != '']

            # register all keys in the Preferences window
            for ext in grb_list:
                new_k = new_reg_path + '.%s' % ext
                set_reg('', root_path=root_path, new_reg_path=new_k, value='FlatCAM')

            # and unregister those that are no longer in the Preferences windows but are in the file
            for ext in self.defaults["fa_gerber"].replace(' ', '').split(','):
                if ext not in grb_list:
                    delete_reg(root_path=root_path, reg_path=new_reg_path, key_to_del='.%s' % ext)

            # now write the updated extensions to the self.defaults
            # new_ext = ''
            # for ext in grb_list:
            #     new_ext = new_ext + ext + ', '
            # self.defaults["fa_gerber"] = new_ext
            self.inform.emit('[success] %s' %
                             _("Selected Gerber file extensions registered with FlatCAM."))

    def add_extension(self, ext_type):
        """
        Add a file extension to the list for a specific object

        :param ext_type: type of FlatCAM object: excellon, gerber, geometry and then 'not FlatCAM object' keyword
        :return:
        """

        if ext_type == 'excellon':
            new_ext = self.ui.util_defaults_form.fa_excellon_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_excellon_group.exc_list_text.get_value().replace(' ', '').split(',')
            if new_ext in old_val:
                return
            old_val.append(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_excellon_group.exc_list_text.set_value(', '.join(old_val))
        if ext_type == 'gcode':
            new_ext = self.ui.util_defaults_form.fa_gcode_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_gcode_group.gco_list_text.get_value().replace(' ', '').split(',')
            if new_ext in old_val:
                return
            old_val.append(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_gcode_group.gco_list_text.set_value(', '.join(old_val))
        if ext_type == 'gerber':
            new_ext = self.ui.util_defaults_form.fa_gerber_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_gerber_group.grb_list_text.get_value().replace(' ', '').split(',')
            if new_ext in old_val:
                return
            old_val.append(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_gerber_group.grb_list_text.set_value(', '.join(old_val))
        if ext_type == 'keyword':
            new_kw = self.ui.util_defaults_form.kw_group.kw_entry.get_value()
            if new_kw == '':
                return

            old_val = self.ui.util_defaults_form.kw_group.kw_list_text.get_value().replace(' ', '').split(',')
            if new_kw in old_val:
                return
            old_val.append(new_kw)
            old_val.sort()
            self.ui.util_defaults_form.kw_group.kw_list_text.set_value(', '.join(old_val))

            # update the self.myKeywords so the model is updated
            self.autocomplete_kw_list = \
                self.ui.util_defaults_form.kw_group.kw_list_text.get_value().replace(' ', '').split(',')
            self.myKeywords = self.tcl_commands_list + self.autocomplete_kw_list + self.tcl_keywords
            self.shell._edit.set_model_data(self.myKeywords)

    def del_extension(self, ext_type):
        """
        Remove a file extension from the list for a specific object

        :param ext_type: type of FlatCAM object: excellon, gerber, geometry and then 'not FlatCAM object' keyword
        :return:
        """
        if ext_type == 'excellon':
            new_ext = self.ui.util_defaults_form.fa_excellon_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_excellon_group.exc_list_text.get_value().replace(' ', '').split(',')
            if new_ext not in old_val:
                return
            old_val.remove(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_excellon_group.exc_list_text.set_value(', '.join(old_val))
        if ext_type == 'gcode':
            new_ext = self.ui.util_defaults_form.fa_gcode_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_gcode_group.gco_list_text.get_value().replace(' ', '').split(',')
            if new_ext not in old_val:
                return
            old_val.remove(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_gcode_group.gco_list_text.set_value(', '.join(old_val))
        if ext_type == 'gerber':
            new_ext = self.ui.util_defaults_form.fa_gerber_group.ext_entry.get_value()
            if new_ext == '':
                return

            old_val = self.ui.util_defaults_form.fa_gerber_group.grb_list_text.get_value().replace(' ', '').split(',')
            if new_ext not in old_val:
                return
            old_val.remove(new_ext)
            old_val.sort()
            self.ui.util_defaults_form.fa_gerber_group.grb_list_text.set_value(', '.join(old_val))
        if ext_type == 'keyword':
            new_kw = self.ui.util_defaults_form.kw_group.kw_entry.get_value()
            if new_kw == '':
                return

            old_val = self.ui.util_defaults_form.kw_group.kw_list_text.get_value().replace(' ', '').split(',')
            if new_kw not in old_val:
                return
            old_val.remove(new_kw)
            old_val.sort()
            self.ui.util_defaults_form.kw_group.kw_list_text.set_value(', '.join(old_val))

            # update the self.myKeywords so the model is updated
            self.autocomplete_kw_list = \
                self.ui.util_defaults_form.kw_group.kw_list_text.get_value().replace(' ', '').split(',')
            self.myKeywords = self.tcl_commands_list + self.autocomplete_kw_list + self.tcl_keywords
            self.shell._edit.set_model_data(self.myKeywords)

    def restore_extensions(self, ext_type):
        """
        Restore all file extensions associations with FlatCAM, for a specific object

        :param ext_type: type of FlatCAM object: excellon, gerber, geometry and then 'not FlatCAM object' keyword
        :return:
        """

        if ext_type == 'excellon':
            # don't add 'txt' to the associations (too many files are .txt and not Excellon) but keep it in the list
            # for the ability to open Excellon files with .txt extension
            new_exc_list = deepcopy(self.exc_list)

            try:
                new_exc_list.remove('txt')
            except ValueError:
                pass
            self.ui.util_defaults_form.fa_excellon_group.exc_list_text.set_value(', '.join(new_exc_list))
        if ext_type == 'gcode':
            self.ui.util_defaults_form.fa_gcode_group.gco_list_text.set_value(', '.join(self.gcode_list))
        if ext_type == 'gerber':
            self.ui.util_defaults_form.fa_gerber_group.grb_list_text.set_value(', '.join(self.grb_list))
        if ext_type == 'keyword':
            self.ui.util_defaults_form.kw_group.kw_list_text.set_value(', '.join(self.default_keywords))

            # update the self.myKeywords so the model is updated
            self.autocomplete_kw_list = self.default_keywords
            self.myKeywords = self.tcl_commands_list + self.autocomplete_kw_list + self.tcl_keywords
            self.shell._edit.set_model_data(self.myKeywords)

    def delete_all_extensions(self, ext_type):
        """
        Delete all file extensions associations with FlatCAM, for a specific object

        :param ext_type: type of FlatCAM object: excellon, gerber, geometry and then 'not FlatCAM object' keyword
        :return:
        """

        if ext_type == 'excellon':
            self.ui.util_defaults_form.fa_excellon_group.exc_list_text.set_value('')
        if ext_type == 'gcode':
            self.ui.util_defaults_form.fa_gcode_group.gco_list_text.set_value('')
        if ext_type == 'gerber':
            self.ui.util_defaults_form.fa_gerber_group.grb_list_text.set_value('')
        if ext_type == 'keyword':
            self.ui.util_defaults_form.kw_group.kw_list_text.set_value('')

            # update the self.myKeywords so the model is updated
            self.myKeywords = self.tcl_commands_list + self.tcl_keywords
            self.shell._edit.set_model_data(self.myKeywords)

    def on_edit_join(self, name=None):
        """
        Callback for Edit->Join. Joins the selected geometry objects into
        a new one.

        :return: None
        """
        self.defaults.report_usage("on_edit_join()")

        obj_name_single = str(name) if name else "Combo_SingleGeo"
        obj_name_multi = str(name) if name else "Combo_MultiGeo"

        geo_type_set = set()

        objs = self.collection.get_selected()

        if len(objs) < 2:
            self.inform.emit('[ERROR_NOTCL] %s: %d' %
                             (_("At least two objects are required for join. Objects currently selected"), len(objs)))
            return 'fail'

        for obj in objs:
            geo_type_set.add(obj.multigeo)

        # if len(geo_type_list) == 1 means that all list elements are the same
        if len(geo_type_set) != 1:
            self.inform.emit('[ERROR] %s' %
                             _("Failed join. The Geometry objects are of different types.\n"
                               "At least one is MultiGeo type and the other is SingleGeo type. A possibility is to "
                               "convert from one to another and retry joining \n"
                               "but in the case of converting from MultiGeo to SingleGeo, informations may be lost and "
                               "the result may not be what was expected. \n"
                               "Check the generated GCODE."))
            return

        # if at least one True object is in the list then due of the previous check, all list elements are True objects
        if True in geo_type_set:
            def initialize(geo_obj, app):
                GeometryObject.merge(geo_list=objs, geo_final=geo_obj, multigeo=True)
                app.inform.emit('[success] %s.' % _("Geometry merging finished"))

                # rename all the ['name] key in obj.tools[tooluid]['data'] to the obj_name_multi
                for v in geo_obj.tools.values():
                    v['data']['name'] = obj_name_multi

            self.new_object("geometry", obj_name_multi, initialize)
        else:
            def initialize(geo_obj, app):
                GeometryObject.merge(geo_list=objs, geo_final=geo_obj, multigeo=False)
                app.inform.emit('[success] %s.' % _("Geometry merging finished"))

                # rename all the ['name] key in obj.tools[tooluid]['data'] to the obj_name_multi
                for v in geo_obj.tools.values():
                    v['data']['name'] = obj_name_single

            self.new_object("geometry", obj_name_single, initialize)

        self.should_we_save = True

    def on_edit_join_exc(self):
        """
        Callback for Edit->Join Excellon. Joins the selected Excellon objects into
        a new Excellon.

        :return: None
        """
        self.defaults.report_usage("on_edit_join_exc()")

        objs = self.collection.get_selected()

        for obj in objs:
            if not isinstance(obj, ExcellonObject):
                self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Excellon joining works only on Excellon objects."))
                return

        if len(objs) < 2:
            self.inform.emit('[ERROR_NOTCL] %s: %d' %
                             (_("At least two objects are required for join. Objects currently selected"), len(objs)))
            return 'fail'

        def initialize(exc_obj, app):
            ExcellonObject.merge(exc_list=objs, exc_final=exc_obj, decimals=self.decimals)
            app.inform.emit('[success] %s.' % _("Excellon merging finished"))

        self.new_object("excellon", 'Combo_Excellon', initialize)
        self.should_we_save = True

    def on_edit_join_grb(self):
        """
        Callback for Edit->Join Gerber. Joins the selected Gerber objects into
        a new Gerber object.

        :return: None
        """
        self.defaults.report_usage("on_edit_join_grb()")

        objs = self.collection.get_selected()

        for obj in objs:
            if not isinstance(obj, GerberObject):
                self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Gerber joining works only on Gerber objects."))
                return

        if len(objs) < 2:
            self.inform.emit('[ERROR_NOTCL] %s: %d' %
                             (_("At least two objects are required for join. Objects currently selected"), len(objs)))
            return 'fail'

        def initialize(grb_obj, app):
            GerberObject.merge(grb_list=objs, grb_final=grb_obj)
            app.inform.emit('[success] %s.' % _("Gerber merging finished"))

        self.new_object("gerber", 'Combo_Gerber', initialize)
        self.should_we_save = True

    def on_convert_singlegeo_to_multigeo(self):
        """
        Called for converting a Geometry object from single-geo to multi-geo.
        Single-geo Geometry objects store their geometry data into self.solid_geometry.
        Multi-geo Geometry objects store their geometry data into the self.tools dictionary, each key (a tool actually)
        having as a value another dictionary. This value dictionary has one of it's keys 'solid_geometry' which holds
        the solid-geometry of that tool.

        :return: None
        """
        self.defaults.report_usage("on_convert_singlegeo_to_multigeo()")

        obj = self.collection.get_active()

        if obj is None:
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Select a Geometry Object and try again."))
            return

        if not isinstance(obj, GeometryObject):
            self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Expected a GeometryObject, got"), type(obj)))
            return

        obj.multigeo = True
        for tooluid, dict_value in obj.tools.items():
            dict_value['solid_geometry'] = deepcopy(obj.solid_geometry)

        if not isinstance(obj.solid_geometry, list):
            obj.solid_geometry = [obj.solid_geometry]

        # obj.solid_geometry[:] = []
        obj.plot()

        self.should_we_save = True

        self.inform.emit('[success] %s' % _("A Geometry object was converted to MultiGeo type."))

    def on_convert_multigeo_to_singlegeo(self):
        """
        Called for converting a Geometry object from multi-geo to single-geo.
        Single-geo Geometry objects store their geometry data into self.solid_geometry.
        Multi-geo Geometry objects store their geometry data into the self.tools dictionary, each key (a tool actually)
        having as a value another dictionary. This value dictionary has one of it's keys 'solid_geometry' which holds
        the solid-geometry of that tool.

        :return: None
        """
        self.defaults.report_usage("on_convert_multigeo_to_singlegeo()")

        obj = self.collection.get_active()

        if obj is None:
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _("Failed. Select a Geometry Object and try again."))
            return

        if not isinstance(obj, GeometryObject):
            self.inform.emit('[ERROR_NOTCL] %s: %s' %
                             (_("Expected a GeometryObject, got"), type(obj)))
            return

        obj.multigeo = False
        total_solid_geometry = []
        for tooluid, dict_value in obj.tools.items():
            total_solid_geometry += deepcopy(dict_value['solid_geometry'])
            # clear the original geometry
            dict_value['solid_geometry'][:] = []
        obj.solid_geometry = deepcopy(total_solid_geometry)
        obj.plot()

        self.should_we_save = True

        self.inform.emit('[success] %s' %
                         _("A Geometry object was converted to SingleGeo type."))

    def on_defaults_dict_change(self, field):
        """
        Called whenever a key changed in the self.defaults dictionary. It will set the required GUI element in the
        Edit -> Preferences tab window.

        :param field: the key of the self.defaults dictionary that was changed.
        :return: None
        """
        self.preferencesUiManager.defaults_write_form_field(field=field)

        if field == "units":
            self.set_screen_units(self.defaults['units'])

    def set_screen_units(self, units):
        """
        Set the FlatCAM units on the status bar.

        :param units: the new measuring units to be displayed in FlatCAM's status bar.
        :return: None
        """
        self.ui.units_label.setText("[" + units.lower() + "]")

    def on_toggle_units_click(self):
        try:
            self.preferencesUiManager.get_form_field("units").activated_custom.disconnect()
        except (TypeError, AttributeError):
            pass

        if self.defaults["units"] == 'MM':
            self.preferencesUiManager.get_form_field("units").set_value("IN")
        else:
            self.preferencesUiManager.get_form_field("units").set_value("MM")

        self.on_toggle_units(no_pref=True)

        self.preferencesUiManager.get_form_field("units").activated_custom.connect(
            lambda: self.on_toggle_units(no_pref=False))

    def on_toggle_units(self, no_pref=False):
        """
        Callback for the Units radio-button change in the Preferences tab.
        Changes the application's default units adn for the project too.
        If changing the project's units, the change propagates to all of
        the objects in the project.

        :return: None
        """

        self.defaults.report_usage("on_toggle_units")

        if self.toggle_units_ignore:
            return

        new_units = self.preferencesUiManager.get_form_field("units").get_value().upper()

        # If option is the same, then ignore
        if new_units == self.defaults["units"].upper():
            self.log.debug("on_toggle_units(): Same as previous, ignoring.")
            return

        # Keys in self.defaults for which to scale their values
        dimensions = ['gerber_isotooldia', 'gerber_noncoppermargin', 'gerber_bboxmargin',
                      "gerber_editor_newsize", "gerber_editor_lin_pitch", "gerber_editor_buff_f", "gerber_vtipdia",
                      "gerber_vcutz", "gerber_editor_newdim", "gerber_editor_ma_low",
                      "gerber_editor_ma_high",

                      'excellon_cutz', 'excellon_travelz', "excellon_toolchangexy", 'excellon_offset',
                      'excellon_feedrate_z', 'excellon_feedrate_rapid', 'excellon_toolchangez',
                      'excellon_tooldia', 'excellon_slot_tooldia', 'excellon_endz', 'excellon_endxy',
                      "excellon_feedrate_probe", "excellon_milling_dia",
                      "excellon_z_pdepth", "excellon_editor_newdia", "excellon_editor_lin_pitch",
                      "excellon_editor_slot_lin_pitch", "excellon_editor_slot_length",

                      'geometry_cutz', "geometry_depthperpass", 'geometry_travelz', 'geometry_feedrate',
                      'geometry_feedrate_rapid', "geometry_toolchangez", "geometry_feedrate_z",
                      "geometry_toolchangexy", 'geometry_cnctooldia', 'geometry_endz', 'geometry_endxy',
                      "geometry_extracut_length", "geometry_z_pdepth",
                      "geometry_feedrate_probe", "geometry_startz", "geometry_segx", "geometry_segy",

                      'cncjob_tooldia',

                      'tools_paintmargin', 'tools_painttooldia', "tools_paintcutz", "tools_painttipdia",
                      "tools_paintnewdia",

                      "tools_ncctools", "tools_nccmargin", "tools_ncccutz", "tools_ncctipdia",
                      "tools_nccnewdia", "tools_ncc_offset_value",

                      "tools_2sided_drilldia",
                      "tools_film_boundary", "tools_film_scale_stroke",

                      "tools_cutouttooldia", 'tools_cutoutmargin', 'tools_cutoutgapsize', "tools_cutout_z",
                      "tools_cutout_depthperpass",

                      "tools_panelize_constrainx", "tools_panelize_constrainy", "tools_panelize_spacing_columns",
                      "tools_panelize_spacing_rows",

                      "tools_calc_vshape_tip_dia", "tools_calc_vshape_cut_z",

                      "tools_transform_offset_x", "tools_transform_offset_y", "tools_transform_mirror_point",
                      "tools_transform_buffer_dis",

                      "tools_solderpaste_tools", "tools_solderpaste_new", "tools_solderpaste_z_start",
                      "tools_solderpaste_z_dispense", "tools_solderpaste_z_stop", "tools_solderpaste_z_travel",
                      "tools_solderpaste_z_toolchange", "tools_solderpaste_xy_toolchange", "tools_solderpaste_frxy",
                      "tools_solderpaste_frz", "tools_solderpaste_frz_dispense",

                      "tools_cr_trace_size_val", "tools_cr_c2c_val", "tools_cr_c2o_val", "tools_cr_s2s_val",
                      "tools_cr_s2sm_val", "tools_cr_s2o_val", "tools_cr_sm2sm_val", "tools_cr_ri_val",
                      "tools_cr_h2h_val", "tools_cr_dh_val",

                      "tools_fiducials_dia", "tools_fiducials_margin", "tools_fiducials_line_thickness",

                      "tools_copper_thieving_clearance", "tools_copper_thieving_margin",
                      "tools_copper_thieving_dots_dia", "tools_copper_thieving_dots_spacing",
                      "tools_copper_thieving_squares_size", "tools_copper_thieving_squares_spacing",
                      "tools_copper_thieving_lines_size", "tools_copper_thieving_lines_spacing",
                      "tools_copper_thieving_rb_margin", "tools_copper_thieving_rb_thickness",
                      "tools_copper_thieving_mask_clearance",

                      "tools_cal_travelz", "tools_cal_verz", "tools_cal_toolchangez", "tools_cal_toolchange_xy",

                      "tools_edrills_hole_fixed_dia", "tools_edrills_circular_ring", "tools_edrills_oblong_ring",
                      "tools_edrills_square_ring", "tools_edrills_rectangular_ring", "tools_edrills_others_ring",

                      "tools_punch_hole_fixed_dia", "tools_punch_circular_ring", "tools_punch_oblong_ring",
                      "tools_punch_square_ring", "tools_punch_rectangular_ring", "tools_punch_others_ring",

                      "tools_invert_margin",

                      'global_gridx', 'global_gridy', 'global_snap_max', "global_tolerance",
                      'global_tpdf_bmargin', 'global_tpdf_tmargin', 'global_tpdf_rmargin', 'global_tpdf_lmargin']

        def scale_defaults(sfactor):
            for dim in dimensions:
                if dim in [
                    'gerber_editor_newdim', 'excellon_toolchangexy', 'geometry_toolchangexy', 'excellon_endxy',
                    'geometry_endxy', 'tools_solderpaste_xy_toolchange', 'tools_cal_toolchange_xy',
                    'tools_transform_mirror_point'
                ]:
                    if self.defaults[dim] is None or self.defaults[dim] == '':
                        continue

                    try:
                        coordinates = self.defaults[dim].split(",")
                        coords_xy = [float(eval(a)) for a in coordinates if a != '']
                        coords_xy[0] *= sfactor
                        coords_xy[1] *= sfactor
                        self.defaults[dim] = "%.*f, %.*f" % (
                            self.decimals, coords_xy[0], self.decimals, coords_xy[1])
                    except Exception as e:
                        log.debug("App.on_toggle_units.scale_defaults() --> 'string tuples': %s" % str(e))

                elif dim in [
                    'geometry_cnctooldia', 'tools_ncctools', 'tools_solderpaste_tools'
                ]:
                    if self.defaults[dim] is None or self.defaults[dim] == '':
                        continue

                    try:
                        self.defaults[dim] = float(self.defaults[dim])
                        tools_diameters = [self.defaults[dim]]
                    except ValueError:
                        try:
                            tools_string = self.defaults[dim].split(",")
                            tools_diameters = [eval(a) for a in tools_string if a != '']
                        except Exception as e:
                            log.debug("App.on_toggle_units().scale_options() --> %s" % str(e))
                            continue

                    self.defaults[dim] = ''
                    td_len = len(tools_diameters)
                    if td_len > 1:
                        for t in range(td_len):
                            tools_diameters[t] *= sfactor
                            self.defaults[dim] += "%.*f," % (self.decimals, tools_diameters[t])
                    else:
                        tools_diameters[0] *= sfactor
                        self.defaults[dim] += "%.*f" % (self.decimals, tools_diameters[0])

                elif dim in ['global_gridx', 'global_gridy']:
                    # format the number of decimals to the one specified in self.decimals
                    try:
                        val = float(self.defaults[dim]) * sfactor
                    except Exception as e:
                        log.debug('App.on_toggle_units().scale_defaults() --> %s' % str(e))
                        continue

                    self.defaults[dim] = float('%.*f' % (self.decimals, val))
                else:
                    # the number of decimals for the rest is kept unchanged
                    if self.defaults[dim]:
                        try:
                            val = float(self.defaults[dim]) * sfactor
                        except Exception as e:
                            log.debug('App.on_toggle_units().scale_defaults() --> Value: %s %s' % (str(dim), str(e)))
                            continue

                        self.defaults[dim] = val

        # The scaling factor depending on choice of units.
        factor = 25.4 if new_units == 'MM' else 1 / 25.4

        # Changing project units. Warn user.
        msgbox = QtWidgets.QMessageBox()
        msgbox.setWindowTitle(_("Toggle Units"))
        msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/toggle_units32.png'))
        msgbox.setText(_("Changing the units of the project\n"
                         "will scale all objects.\n\n"
                         "Do you want to continue?"))
        bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
        msgbox.addButton(_('Cancel'), QtWidgets.QMessageBox.RejectRole)

        msgbox.setDefaultButton(bt_ok)
        msgbox.exec_()
        response = msgbox.clickedButton()

        if response == bt_ok:
            if no_pref is False:
                self.preferencesUiManager.defaults_read_form()
                scale_defaults(factor)
                self.preferencesUiManager.defaults_write_form(fl_units=new_units)

                self.defaults["units"] = new_units

                # update the defaults from form, some may assume that the conversion is enough and it's not
                self.on_options_app2project()

            # update the objects
            for obj in self.collection.get_list():
                obj.convert_units(new_units)

                # make that the properties stored in the object are also updated
                self.object_changed.emit(obj)
                # rebuild the object UI
                obj.build_ui()

            # change this only if the workspace is active
            if self.defaults['global_workspace'] is True:
                self.plotcanvas.draw_workspace(pagesize=self.defaults['global_workspaceT'])

            # adjust the grid values on the main toolbar
            val_x = float(self.defaults['global_gridx']) * factor
            val_y = val_x if self.ui.grid_gap_link_cb.isChecked() else float(self.defaults['global_gridx']) * factor

            current = self.collection.get_active()
            if current is not None:
                # the transfer of converted values to the UI form for Geometry is done local in the FlatCAMObj.py
                if not isinstance(current, GeometryObject):
                    current.to_form()

            # replot all objects
            self.plot_all()

            # set the status labels to reflect the current FlatCAM units
            self.set_screen_units(new_units)

            # signal to the app that we changed the object properties and it should save the project
            self.should_we_save = True

            self.inform.emit('[success] %s: %s' % (_("Converted units to"), new_units))
        else:
            # Undo toggling
            self.toggle_units_ignore = True
            if self.defaults['units'].upper() == 'MM':
                self.preferencesUiManager.get_form_field("units").set_value('IN')
            else:
                self.preferencesUiManager.get_form_field("units").set_value('MM')
            self.toggle_units_ignore = False

            # store the grid values so they are not changed in the next step
            val_x = float(self.defaults['global_gridx'])
            val_y = float(self.defaults['global_gridy'])

            self.inform.emit('[WARNING_NOTCL]%s' % _("Cancelled."))

        self.preferencesUiManager.defaults_read_form()

        # the self.preferencesUiManager.defaults_read_form() will update all defaults values
        # in self.defaults from the GUI elements but
        # I don't want it for the grid values, so I update them here
        self.defaults['global_gridx'] = val_x
        self.defaults['global_gridy'] = val_y
        self.ui.grid_gap_x_entry.set_value(val_x, decimals=self.decimals)
        self.ui.grid_gap_y_entry.set_value(val_y, decimals=self.decimals)

    def on_fullscreen(self, disable=False):
        self.defaults.report_usage("on_fullscreen()")

        flags = self.ui.windowFlags()
        if self.toggle_fscreen is False and disable is False:
            # self.ui.showFullScreen()
            self.ui.setWindowFlags(flags | Qt.FramelessWindowHint)
            a = self.ui.geometry()
            self.x_pos = a.x()
            self.y_pos = a.y()
            self.width = a.width()
            self.height = a.height()

            # set new geometry to full desktop rect
            # Subtracting and adding the pixels below it's hack to bypass a bug in Qt5 and OpenGL that made that a
            # window drawn with OpenGL in fullscreen will not show any other windows on top which means that menus and
            # everything else will not work without this hack. This happen in Windows.
            # https://bugreports.qt.io/browse/QTBUG-41309
            desktop = QtWidgets.QApplication.desktop()
            screen = desktop.screenNumber(QtGui.QCursor.pos())

            rec = desktop.screenGeometry(screen)
            x = rec.x() - 1
            y = rec.y() - 1
            h = rec.height() + 2
            w = rec.width() + 2
            self.ui.setGeometry(x, y, w, h)
            self.ui.show()

            for tb in self.ui.findChildren(QtWidgets.QToolBar):
                tb.setVisible(False)
            self.ui.splitter_left.setVisible(False)
            self.toggle_fscreen = True
        elif self.toggle_fscreen is True or disable is True:
            self.ui.setWindowFlags(flags & ~Qt.FramelessWindowHint)
            self.ui.setGeometry(self.x_pos, self.y_pos, self.width, self.height)
            self.ui.showNormal()
            self.restore_toolbar_view()
            self.ui.splitter_left.setVisible(True)
            self.toggle_fscreen = False

    def on_toggle_plotarea(self):
        self.defaults.report_usage("on_toggle_plotarea()")

        try:
            name = self.ui.plot_tab_area.widget(0).objectName()
        except AttributeError:
            self.ui.plot_tab_area.addTab(self.ui.plot_tab, "Plot Area")
            # remove the close button from the Plot Area tab (first tab index = 0) as this one will always be ON
            self.ui.plot_tab_area.protectTab(0)
            return

        if name != 'plotarea_tab':
            self.ui.plot_tab_area.insertTab(0, self.ui.plot_tab, "Plot Area")
            # remove the close button from the Plot Area tab (first tab index = 0) as this one will always be ON
            self.ui.plot_tab_area.protectTab(0)
        else:
            self.ui.plot_tab_area.closeTab(0)

    def on_toggle_notebook(self):
        if self.ui.splitter.sizes()[0] == 0:
            self.ui.splitter.setSizes([1, 1])
            self.ui.menu_toggle_nb.setChecked(True)
        else:
            self.ui.splitter.setSizes([0, 1])
            self.ui.menu_toggle_nb.setChecked(False)

    def on_toggle_axis(self):
        self.defaults.report_usage("on_toggle_axis()")

        if self.toggle_axis is False:
            if self.is_legacy is False:
                self.plotcanvas.v_line = InfiniteLine(pos=0, color=(0.70, 0.3, 0.3, 1.0), vertical=True,
                                                      parent=self.plotcanvas.view.scene)

                self.plotcanvas.h_line = InfiniteLine(pos=0, color=(0.70, 0.3, 0.3, 1.0), vertical=False,
                                                      parent=self.plotcanvas.view.scene)
            else:
                if self.plotcanvas.h_line not in self.plotcanvas.axes.lines and \
                        self.plotcanvas.v_line not in self.plotcanvas.axes.lines:
                    self.plotcanvas.h_line = self.plotcanvas.axes.axhline(color=(0.70, 0.3, 0.3), linewidth=2)
                    self.plotcanvas.v_line = self.plotcanvas.axes.axvline(color=(0.70, 0.3, 0.3), linewidth=2)
                    self.plotcanvas.canvas.draw()

            self.toggle_axis = True
        else:
            if self.is_legacy is False:
                self.plotcanvas.v_line.parent = None
                self.plotcanvas.h_line.parent = None
            else:
                if self.plotcanvas.h_line in self.plotcanvas.axes.lines and \
                        self.plotcanvas.v_line in self.plotcanvas.axes.lines:
                    self.plotcanvas.axes.lines.remove(self.plotcanvas.h_line)
                    self.plotcanvas.axes.lines.remove(self.plotcanvas.v_line)
                    self.plotcanvas.canvas.draw()
            self.toggle_axis = False

    def on_toggle_grid(self):
        self.defaults.report_usage("on_toggle_grid()")

        self.ui.grid_snap_btn.trigger()
        self.ui.on_grid_snap_triggered(state=True)

    def on_toggle_grid_lines(self):
        self.defaults.report_usage("on_toggle_grd_lines()")

        tt_settings = QtCore.QSettings("Open Source", "FlatCAM")
        if tt_settings.contains("theme"):
            theme = tt_settings.value('theme', type=str)
        else:
            theme = 'white'

        if self.toggle_grid_lines is False:
            if self.is_legacy is False:
                if theme == 'white':
                    self.plotcanvas.grid._grid_color_fn['color'] = Color('dimgray').rgba
                else:
                    self.plotcanvas.grid._grid_color_fn['color'] = Color('#dededeff').rgba
            else:
                self.plotcanvas.axes.grid(True)
                try:
                    self.plotcanvas.canvas.draw()
                except IndexError:
                    pass
                pass
            self.toggle_grid_lines = True
        else:
            if self.is_legacy is False:
                if theme == 'white':
                    self.plotcanvas.grid._grid_color_fn['color'] = Color('#ffffffff').rgba
                else:
                    self.plotcanvas.grid._grid_color_fn['color'] = Color('#000000FF').rgba
            else:
                self.plotcanvas.axes.grid(False)
                try:
                    self.plotcanvas.canvas.draw()
                except IndexError:
                    pass
            self.toggle_grid_lines = False

        if self.is_legacy is False:
            # HACK: enabling/disabling the cursor seams to somehow update the shapes on screen
            # - perhaps is a bug in VisPy implementation
            if self.grid_status() is True:
                self.app_cursor.enabled = False
                self.app_cursor.enabled = True
            else:
                self.app_cursor.enabled = True
                self.app_cursor.enabled = False



    def on_film_color_entry(self):
        self.defaults['tools_film_color'] = \
            self.ui.tools_defaults_form.tools_film_group.film_color_entry.get_value()
        self.ui.tools_defaults_form.tools_film_group.film_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(self.defaults['tools_film_color'])
        )

    def on_film_color_button(self):
        current_color = QtGui.QColor(self.defaults['tools_film_color'])

        c_dialog = QtWidgets.QColorDialog()
        film_color = c_dialog.getColor(initial=current_color)

        if film_color.isValid() is False:
            return

        # if new color is different then mark that the Preferences are changed
        if film_color != current_color:
            self.preferencesUiManager.on_preferences_edited()

        self.ui.tools_defaults_form.tools_film_group.film_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(film_color.name())
        )
        new_val_sel = str(film_color.name())
        self.ui.tools_defaults_form.tools_film_group.film_color_entry.set_value(new_val_sel)
        self.defaults['tools_film_color'] = new_val_sel

    def on_qrcode_fill_color_entry(self):
        self.defaults['tools_qrcode_fill_color'] = \
            self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_entry.get_value()
        self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(self.defaults['tools_qrcode_fill_color'])
        )

    def on_qrcode_fill_color_button(self):
        current_color = QtGui.QColor(self.defaults['tools_qrcode_fill_color'])

        c_dialog = QtWidgets.QColorDialog()
        fill_color = c_dialog.getColor(initial=current_color)

        if fill_color.isValid() is False:
            return

        # if new color is different then mark that the Preferences are changed
        if fill_color != current_color:
            self.preferencesUiManager.on_preferences_edited()

        self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(fill_color.name())
        )

        new_val_sel = str(fill_color.name())
        self.ui.tools2_defaults_form.tools2_qrcode_group.fill_color_entry.set_value(new_val_sel)
        self.defaults['tools_qrcode_fill_color'] = new_val_sel

    def on_qrcode_back_color_entry(self):
        self.defaults['tools_qrcode_back_color'] = \
            self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_entry.get_value()
        self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(self.defaults['tools_qrcode_back_color'])
        )

    def on_qrcode_back_color_button(self):
        current_color = QtGui.QColor(self.defaults['tools_qrcode_back_color'])

        c_dialog = QtWidgets.QColorDialog()
        back_color = c_dialog.getColor(initial=current_color)

        if back_color.isValid() is False:
            return

        # if new color is different then mark that the Preferences are changed
        if back_color != current_color:
            self.preferencesUiManager.on_preferences_edited()

        self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_button.setStyleSheet(
            "background-color:%s;"
            "border-color: dimgray" % str(back_color.name())
        )

        new_val_sel = str(back_color.name())
        self.ui.tools2_defaults_form.tools2_qrcode_group.back_color_entry.set_value(new_val_sel)
        self.defaults['tools_qrcode_back_color'] = new_val_sel

    def on_tab_rmb_click(self, checked):
        self.ui.notebook.set_detachable(val=checked)
        self.defaults["global_tabs_detachable"] = checked

        self.ui.plot_tab_area.set_detachable(val=checked)
        self.defaults["global_tabs_detachable"] = checked

    def on_tab_setup_context_menu(self):
        initial_checked = self.defaults["global_tabs_detachable"]
        action_name = str(_("Detachable Tabs"))
        action = QtWidgets.QAction(self)
        action.setCheckable(True)
        action.setText(action_name)
        action.setChecked(initial_checked)

        self.ui.notebook.tabBar.addAction(action)
        self.ui.plot_tab_area.tabBar.addAction(action)

        try:
            action.triggered.disconnect()
        except TypeError:
            pass
        action.triggered.connect(self.on_tab_rmb_click)

    def on_deselect_all(self):
        self.collection.set_all_inactive()
        self.delete_selection_shape()

    def on_workspace_modified(self):
        # self.save_defaults(silent=True)
        if self.is_legacy is True:
            self.plotcanvas.delete_workspace()
        self.preferencesUiManager.defaults_read_form()
        self.plotcanvas.draw_workspace(workspace_size=self.defaults['global_workspaceT'])

    def on_workspace(self):
        if self.preferencesUiManager.get_form_field("global_workspace").get_value():
            self.plotcanvas.draw_workspace(workspace_size=self.defaults['global_workspaceT'])
        else:
            self.plotcanvas.delete_workspace()
        self.preferencesUiManager.defaults_read_form()
        # self.save_defaults(silent=True)

    def on_workspace_toggle(self):
        state = False if self.preferencesUiManager.get_form_field("global_workspace").get_value() else True
        try:
            self.preferencesUiManager.get_form_field("global_workspace").stateChanged.disconnect(self.on_workspace)
        except TypeError:
            pass
        self.preferencesUiManager.get_form_field("global_workspace").set_value(state)
        self.preferencesUiManager.get_form_field("global_workspace").stateChanged.connect(self.on_workspace)
        self.on_workspace()

    def on_cursor_type(self, val):
        """

        :param val: type of mouse cursor, set in Preferences ('small' or 'big')
        :return: None
        """
        self.app_cursor.enabled = False

        if val == 'small':
            self.preferencesUiManager.get_form_field("global_cursor_size").setDisabled(False)
            #self.ui.general_defaults_form.general_app_set_group.cursor_size_lbl.setDisabled(False)
            self.app_cursor = self.plotcanvas.new_cursor()
        else:
            self.preferencesUiManager.get_form_field("global_cursor_size").setDisabled(False)
            #self.ui.general_defaults_form.general_app_set_group.cursor_size_lbl.setDisabled(True)
            self.app_cursor = self.plotcanvas.new_cursor(big=True)

        if self.ui.grid_snap_btn.isChecked():
            self.app_cursor.enabled = True
        else:
            self.app_cursor.enabled = False

    def on_tool_add_keypress(self):
        # ## Current application units in Upper Case
        self.units = self.defaults['units'].upper()

        notebook_widget_name = self.ui.notebook.currentWidget().objectName()

        # work only if the notebook tab on focus is the Selected_Tab and only if the object is Geometry
        if notebook_widget_name == 'selected_tab':
            if self.collection.get_active().kind == 'geometry':
                # Tool add works for Geometry only if Advanced is True in Preferences
                if self.defaults["global_app_level"] == 'a':
                    tool_add_popup = FCInputDialog(title="New Tool ...",
                                                   text='Enter a Tool Diameter:',
                                                   min=0.0000, max=99.9999, decimals=4)
                    tool_add_popup.setWindowIcon(QtGui.QIcon(self.resource_location + '/letter_t_32.png'))

                    val, ok = tool_add_popup.get_value()
                    if ok:
                        if float(val) == 0:
                            self.inform.emit('[WARNING_NOTCL] %s' %
                                             _("Please enter a tool diameter with non-zero value, in Float format."))
                            return
                        self.collection.get_active().on_tool_add(dia=float(val))
                    else:
                        self.inform.emit('[WARNING_NOTCL] %s...' % _("Adding Tool cancelled"))
                else:
                    msgbox = QtWidgets.QMessageBox()
                    msgbox.setText(_("Adding Tool works only when Advanced is checked.\n"
                                     "Go to Preferences -> General - Show Advanced Options."))
                    msgbox.setWindowTitle("Tool adding ...")
                    msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/warning.png'))
                    bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)

                    msgbox.setDefaultButton(bt_ok)
                    msgbox.exec_()

        # work only if the notebook tab on focus is the Tools_Tab
        if notebook_widget_name == 'tool_tab':
            tool_widget = self.ui.tool_scroll_area.widget().objectName()

            # and only if the tool is NCC Tool
            if tool_widget == self.ncclear_tool.toolName:
                self.ncclear_tool.on_add_tool_by_key()

            # and only if the tool is Paint Area Tool
            elif tool_widget == self.paint_tool.toolName:
                self.paint_tool.on_add_tool_by_key()

            # and only if the tool is Solder Paste Dispensing Tool
            elif tool_widget == self.paste_tool.toolName:
                self.paste_tool.on_add_tool_by_key()

    # It's meant to delete tools in tool tables via a 'Delete' shortcut key but only if certain conditions are met
    # See description below.
    def on_delete_keypress(self):
        notebook_widget_name = self.ui.notebook.currentWidget().objectName()

        # work only if the notebook tab on focus is the Selected_Tab and only if the object is Geometry
        if notebook_widget_name == 'selected_tab':
            if str(type(self.collection.get_active())) == "<class 'FlatCAMObj.GeometryObject'>":
                self.collection.get_active().on_tool_delete()

        # work only if the notebook tab on focus is the Tools_Tab
        elif notebook_widget_name == 'tool_tab':
            tool_widget = self.ui.tool_scroll_area.widget().objectName()

            # and only if the tool is NCC Tool
            if tool_widget == self.ncclear_tool.toolName:
                self.ncclear_tool.on_tool_delete()

            # and only if the tool is Paint Tool
            elif tool_widget == self.paint_tool.toolName:
                self.paint_tool.on_tool_delete()

            # and only if the tool is Solder Paste Dispensing Tool
            elif tool_widget == self.paste_tool.toolName:
                self.paste_tool.on_tool_delete()
        else:
            self.on_delete()

    # It's meant to delete selected objects. It work also activated by a shortcut key 'Delete' same as above so in
    # some screens you have to be careful where you hover with your mouse.
    # Hovering over Selected tab, if the selected tab is a Geometry it will delete tools in tool table. But even if
    # there is a Selected tab in focus with a Geometry inside, if you hover over canvas it will delete an object.
    # Complicated, I know :)
    def on_delete(self, force_deletion=False):
        """
        Delete the currently selected FlatCAMObjs.

        :param force_deletion:  used by Tcl command
        :return: None
        """
        self.defaults.report_usage("on_delete()")

        response = None
        bt_ok = None

        # Make sure that the deletion will happen only after the Editor is no longer active otherwise we might delete
        # a geometry object before we update it.
        if self.geo_editor.editor_active is False and self.exc_editor.editor_active is False \
                and self.grb_editor.editor_active is False:
            if self.defaults["global_delete_confirmation"] is True and force_deletion is False:
                msgbox = QtWidgets.QMessageBox()
                msgbox.setWindowTitle(_("Delete objects"))
                msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/deleteshape32.png'))
                # msgbox.setText("<B>%s</B>" % _("Change project units ..."))
                msgbox.setText(_("Are you sure you want to permanently delete\n"
                                 "the selected objects?"))
                bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
                msgbox.addButton(_('Cancel'), QtWidgets.QMessageBox.RejectRole)

                msgbox.setDefaultButton(bt_ok)
                msgbox.exec_()
                response = msgbox.clickedButton()

            if self.defaults["global_delete_confirmation"] is False or force_deletion is True:
                response = bt_ok

            if response == bt_ok:
                if self.collection.get_active():
                    self.log.debug("App.on_delete()")

                    for obj_active in self.collection.get_selected():
                        # if the deleted object is GerberObject then make sure to delete the possible mark shapes
                        if obj_active.kind == 'gerber':
                            for el in obj_active.mark_shapes:
                                obj_active.mark_shapes[el].clear(update=True)
                                obj_active.mark_shapes[el].enabled = False
                                # obj_active.mark_shapes[el] = None
                                del el
                        elif isinstance(obj_active, CNCJobObject):
                            try:
                                obj_active.text_col.enabled = False
                                del obj_active.text_col
                                obj_active.annotation.clear(update=True)
                                del obj_active.annotation
                            except AttributeError as e:
                                log.debug(
                                    "App.on_delete() --> delete annotations on a FlatCAMCNCJob object. %s" % str(e)
                                )

                    while self.collection.get_selected():
                        self.delete_first_selected()

                    self.inform.emit('%s...' % _("Object(s) deleted"))
                    # make sure that the selection shape is deleted, too
                    self.delete_selection_shape()

                    # if there are no longer objects delete also the exclusion areas shapes
                    if not self.collection.get_list():
                        self.exc_areas.clear_shapes()
                else:
                    self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. No object(s) selected..."))
        else:
            self.inform.emit(_("Save the work in Editor and try again ..."))

    def delete_first_selected(self):
        # Keep this for later
        try:
            sel_obj = self.collection.get_active()
            name = sel_obj.options["name"]
            isPlotted = sel_obj.options["plot"]
        except AttributeError:
            self.log.debug("Nothing selected for deletion")
            return

        if self.is_legacy is True:
            # Remove plot only if the object was plotted otherwise delaxes will fail
            if isPlotted:
                try:
                    # self.plotcanvas.figure.delaxes(self.collection.get_active().axes)
                    self.plotcanvas.figure.delaxes(self.collection.get_active().shapes.axes)
                except Exception as e:
                    log.debug("App.delete_first_selected() --> %s" % str(e))

            self.plotcanvas.auto_adjust_axes()

        # Remove from dictionary
        self.collection.delete_active()

        # Clear form
        self.setup_component_editor()

        self.inform.emit('%s: %s' % (_("Object deleted"), name))

    def on_set_origin(self):
        """
        Set the origin to the left mouse click position

        :return: None
        """

        # display the message for the user
        # and ask him to click on the desired position
        self.defaults.report_usage("on_set_origin()")

        def origin_replot():

            def worker_task():
                with self.proc_container.new('%s...' % _("Plotting")):
                    for obj in self.collection.get_list():
                        obj.plot()
                    self.plotcanvas.fit_view()
                if self.is_legacy:
                    self.plotcanvas.graph_event_disconnect(self.mp_zc)
                else:
                    self.plotcanvas.graph_event_disconnect('mouse_press', self.on_set_zero_click)

            self.worker_task.emit({'fcn': worker_task, 'params': []})

        self.inform.emit(_('Click to set the origin ...'))
        self.mp_zc = self.plotcanvas.graph_event_connect('mouse_press', self.on_set_zero_click)

        # first disconnect it as it may have been used by something else
        try:
            self.replot_signal.disconnect()
        except TypeError:
            pass
        self.replot_signal[list].connect(origin_replot)

    def on_set_zero_click(self, event, location=None, noplot=False, use_thread=True):
        """

        :param event:
        :param location:
        :param noplot:
        :param use_thread:
        :return:
        """
        noplot_sig = noplot

        def worker_task():
            with self.proc_container.new(_("Setting Origin...")):
                obj_list = self.collection.get_list()

                for obj in obj_list:
                    obj.offset((x, y))
                    self.object_changed.emit(obj)

                    # Update the object bounding box options
                    a, b, c, d = obj.bounds()
                    obj.options['xmin'] = a
                    obj.options['ymin'] = b
                    obj.options['xmax'] = c
                    obj.options['ymax'] = d
                self.inform.emit('[success] %s...' % _('Origin set'))

                for obj in obj_list:
                    out_name = obj.options["name"]

                    if obj.kind == 'gerber':
                        obj.source_file = self.export_gerber(
                            obj_name=out_name, filename=None, local_use=obj, use_thread=False)
                    elif obj.kind == 'excellon':
                        obj.source_file = self.export_excellon(
                            obj_name=out_name, filename=None, local_use=obj, use_thread=False)

                if noplot_sig is False:
                    self.replot_signal.emit([])

        if location is not None:
            if len(location) != 2:
                self.inform.emit('[ERROR_NOTCL] %s...' % _("Origin coordinates specified but incomplete."))
                return 'fail'

            x, y = location

            if use_thread is True:
                self.worker_task.emit({'fcn': worker_task, 'params': []})
            else:
                worker_task()
            self.should_we_save = True
            return

        if event.button == 1:
            if self.is_legacy is False:
                event_pos = event.pos
            else:
                event_pos = (event.xdata, event.ydata)
            pos_canvas = self.plotcanvas.translate_coords(event_pos)

            if self.grid_status():
                pos = self.geo_editor.snap(pos_canvas[0], pos_canvas[1])
            else:
                pos = pos_canvas

            x = 0 - pos[0]
            y = 0 - pos[1]

            if use_thread is True:
                self.worker_task.emit({'fcn': worker_task, 'params': []})
            else:
                worker_task()
            self.should_we_save = True

    def on_move2origin(self, use_thread=True):
        """
        Move selected objects to origin.
        :param use_thread: Control if to use threaded operation. Boolean.
        :return:
        """

        def worker_task():
            with self.proc_container.new(_("Moving to Origin...")):
                obj_list = self.collection.get_selected()

                if not obj_list:
                    self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. No object(s) selected..."))
                    return

                xminlist = []
                yminlist = []

                # first get a bounding box to fit all
                for obj in obj_list:
                    xmin, ymin, xmax, ymax = obj.bounds()
                    xminlist.append(xmin)
                    yminlist.append(ymin)

                # get the minimum x,y for all objects selected
                x = min(xminlist)
                y = min(yminlist)

                for obj in obj_list:
                    obj.offset((-x, -y))
                    self.object_changed.emit(obj)

                    # Update the object bounding box options
                    a, b, c, d = obj.bounds()
                    obj.options['xmin'] = a
                    obj.options['ymin'] = b
                    obj.options['xmax'] = c
                    obj.options['ymax'] = d

                for obj in obj_list:
                    obj.plot()

                for obj in obj_list:
                    out_name = obj.options["name"]

                    if obj.kind == 'gerber':
                        obj.source_file = self.export_gerber(
                            obj_name=out_name, filename=None, local_use=obj, use_thread=False)
                    elif obj.kind == 'excellon':
                        obj.source_file = self.export_excellon(
                            obj_name=out_name, filename=None, local_use=obj, use_thread=False)

                self.inform.emit('[success] %s...' % _('Origin set'))

        if use_thread is True:
            self.worker_task.emit({'fcn': worker_task, 'params': []})
        else:
            worker_task()
        self.should_we_save = True

    def on_jump_to(self, custom_location=None, fit_center=True):
        """
        Jump to a location by setting the mouse cursor location.

        :param custom_location:     Jump to a specified point. (x, y) tuple.
        :param fit_center:          If to fit view. Boolean.
        :return:

        """
        self.defaults.report_usage("on_jump_to()")

        if not custom_location:
            dia_box_location = None

            try:
                dia_box_location = eval(self.clipboard.text())
            except Exception:
                pass

            if type(dia_box_location) == tuple:
                dia_box_location = str(dia_box_location)
            else:
                dia_box_location = None

            # dia_box = Dialog_box(title=_("Jump to ..."),
            #                      label=_("Enter the coordinates in format X,Y:"),
            #                      icon=QtGui.QIcon(self.resource_location + '/jump_to16.png'),
            #                      initial_text=dia_box_location)

            dia_box = DialogBoxRadio(title=_("Jump to ..."),
                                     label=_("Enter the coordinates in format X,Y:"),
                                     icon=QtGui.QIcon(self.resource_location + '/jump_to16.png'),
                                     initial_text=dia_box_location,
                                     reference=self.defaults['global_jump_ref'])

            if dia_box.ok is True:
                try:
                    location = eval(dia_box.location)

                    if not isinstance(location, tuple):
                        self.inform.emit(_("Wrong coordinates. Enter coordinates in format: X,Y"))
                        return

                    if dia_box.reference == 'rel':
                        rel_x = self.mouse[0] + location[0]
                        rel_y = self.mouse[1] + location[1]
                        location = (rel_x, rel_y)
                    self.defaults['global_jump_ref'] = dia_box.reference
                except Exception:
                    return
            else:
                return
        else:
            location = custom_location

        self.jump_signal.emit(location)

        if fit_center:
            self.plotcanvas.fit_center(loc=location)

        cursor = QtGui.QCursor()

        if self.is_legacy is False:
            # I don't know where those differences come from but they are constant for the current
            # execution of the application and they are multiples of a value around 0.0263mm.
            # In a random way sometimes they are more sometimes they are less
            # if units == 'MM':
            #     cal_factor = 0.0263
            # else:
            #     cal_factor = 0.0263 / 25.4

            cal_location = (location[0], location[1])

            canvas_origin = self.plotcanvas.native.mapToGlobal(QtCore.QPoint(0, 0))
            jump_loc = self.plotcanvas.translate_coords_2((cal_location[0], cal_location[1]))

            j_pos = (
                int(canvas_origin.x() + round(jump_loc[0])),
                int(canvas_origin.y() + round(jump_loc[1]))
            )
            cursor.setPos(j_pos[0], j_pos[1])
        else:
            # find the canvas origin which is in the top left corner
            canvas_origin = self.plotcanvas.native.mapToGlobal(QtCore.QPoint(0, 0))
            # determine the coordinates for the lowest left point of the canvas
            x0, y0 = canvas_origin.x(), canvas_origin.y() + self.ui.right_layout.geometry().height()

            # transform the given location from data coordinates to display coordinates. THe display coordinates are
            # in pixels where the origin 0,0 is in the lowest left point of the display window (in our case is the
            # canvas) and the point (width, height) is in the top-right location
            loc = self.plotcanvas.axes.transData.transform_point(location)
            j_pos = (
                int(x0 + loc[0]),
                int(y0 - loc[1])
            )
            cursor.setPos(j_pos[0], j_pos[1])
            self.plotcanvas.mouse = [location[0], location[1]]
            if self.defaults["global_cursor_color_enabled"] is True:
                self.plotcanvas.draw_cursor(x_pos=location[0], y_pos=location[1], color=self.cursor_color_3D)
            else:
                self.plotcanvas.draw_cursor(x_pos=location[0], y_pos=location[1])

        if self.grid_status():
            # Update cursor
            self.app_cursor.set_data(np.asarray([(location[0], location[1])]),
                                     symbol='++', edge_color=self.cursor_color_3D,
                                     edge_width=self.defaults["global_cursor_width"],
                                     size=self.defaults["global_cursor_size"])

        # Set the relative position label
        dx = location[0] - float(self.rel_point1[0])
        dy = location[1] - float(self.rel_point1[1])
        # self.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
        #                                "<b>Y</b>: %.4f" % (location[0], location[1]))
        # # Set the position label
        #
        # self.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
        #                                    "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (dx, dy))

        units = self.defaults["units"].lower()
        self.plotcanvas.text_hud.text = \
            'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
                dx, units, dy, units, location[0], units, location[1], units)

        self.inform.emit('[success] %s' % _("Done."))
        return location

    def on_locate(self, obj, fit_center=True):
        """
        Jump to one of the corners (or center) of an object by setting the mouse cursor location

        :param obj:         The object on which to locate certain points
        :param fit_center:  If to fit view. Boolean.
        :return:            A point location. (x, y) tuple.

        """
        self.defaults.report_usage("on_locate()")

        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return 'fail'

        class DialogBoxChoice(QtWidgets.QDialog):
            def __init__(self, title=None, icon=None, choice='bl'):
                """

                :param title: string with the window title
                """
                super(DialogBoxChoice, self).__init__()

                self.ok = False

                self.setWindowIcon(icon)
                self.setWindowTitle(str(title))

                self.form = QtWidgets.QFormLayout(self)

                self.ref_radio = RadioSet([
                    {"label": _("Bottom-Left"), "value": "bl"},
                    {"label": _("Top-Left"), "value": "tl"},
                    {"label": _("Bottom-Right"), "value": "br"},
                    {"label": _("Top-Right"), "value": "tr"},
                    {"label": _("Center"), "value": "c"}
                ], orientation='vertical', stretch=False)
                self.ref_radio.set_value(choice)
                self.form.addRow(self.ref_radio)

                self.button_box = QtWidgets.QDialogButtonBox(
                    QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
                    Qt.Horizontal, parent=self)
                self.form.addRow(self.button_box)

                self.button_box.accepted.connect(self.accept)
                self.button_box.rejected.connect(self.reject)

                if self.exec_() == QtWidgets.QDialog.Accepted:
                    self.ok = True
                    self.location_point = self.ref_radio.get_value()
                else:
                    self.ok = False
                    self.location_point = None

        dia_box = DialogBoxChoice(title=_("Locate ..."),
                                  icon=QtGui.QIcon(self.resource_location + '/locate16.png'),
                                  choice=self.defaults['global_locate_pt'])

        if dia_box.ok is True:
            try:
                location_point = dia_box.location_point
                self.defaults['global_locate_pt'] = dia_box.location_point
            except Exception:
                return
        else:
            return

        loc_b = obj.bounds()
        if location_point == 'bl':
            location = (loc_b[0], loc_b[1])
        elif location_point == 'tl':
            location = (loc_b[0], loc_b[3])
        elif location_point == 'br':
            location = (loc_b[2], loc_b[1])
        elif location_point == 'tr':
            location = (loc_b[2], loc_b[3])
        else:
            # center
            cx = loc_b[0] + ((loc_b[2] - loc_b[0]) / 2)
            cy = loc_b[1] + ((loc_b[3] - loc_b[1]) / 2)
            location = (cx, cy)

        self.locate_signal.emit(location, location_point)

        if fit_center:
            self.plotcanvas.fit_center(loc=location)

        cursor = QtGui.QCursor()

        if self.is_legacy is False:
            # I don't know where those differences come from but they are constant for the current
            # execution of the application and they are multiples of a value around 0.0263mm.
            # In a random way sometimes they are more sometimes they are less
            # if units == 'MM':
            #     cal_factor = 0.0263
            # else:
            #     cal_factor = 0.0263 / 25.4

            cal_location = (location[0], location[1])

            canvas_origin = self.plotcanvas.native.mapToGlobal(QtCore.QPoint(0, 0))
            jump_loc = self.plotcanvas.translate_coords_2((cal_location[0], cal_location[1]))

            j_pos = (
                int(canvas_origin.x() + round(jump_loc[0])),
                int(canvas_origin.y() + round(jump_loc[1]))
            )
            cursor.setPos(j_pos[0], j_pos[1])
        else:
            # find the canvas origin which is in the top left corner
            canvas_origin = self.plotcanvas.native.mapToGlobal(QtCore.QPoint(0, 0))
            # determine the coordinates for the lowest left point of the canvas
            x0, y0 = canvas_origin.x(), canvas_origin.y() + self.ui.right_layout.geometry().height()

            # transform the given location from data coordinates to display coordinates. THe display coordinates are
            # in pixels where the origin 0,0 is in the lowest left point of the display window (in our case is the
            # canvas) and the point (width, height) is in the top-right location
            loc = self.plotcanvas.axes.transData.transform_point(location)
            j_pos = (
                int(x0 + loc[0]),
                int(y0 - loc[1])
            )
            cursor.setPos(j_pos[0], j_pos[1])
            self.plotcanvas.mouse = [location[0], location[1]]
            if self.defaults["global_cursor_color_enabled"] is True:
                self.plotcanvas.draw_cursor(x_pos=location[0], y_pos=location[1], color=self.cursor_color_3D)
            else:
                self.plotcanvas.draw_cursor(x_pos=location[0], y_pos=location[1])

        if self.grid_status():
            # Update cursor
            self.app_cursor.set_data(np.asarray([(location[0], location[1])]),
                                     symbol='++', edge_color=self.cursor_color_3D,
                                     edge_width=self.defaults["global_cursor_width"],
                                     size=self.defaults["global_cursor_size"])

        # Set the relative position label
        self.dx = location[0] - float(self.rel_point1[0])
        self.dy = location[1] - float(self.rel_point1[1])
        # Set the position label
        # self.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
        #                                "<b>Y</b>: %.4f" % (location[0], location[1]))
        # self.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
        #                                    "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (self.dx, self.dy))

        units = self.defaults["units"].lower()
        self.plotcanvas.text_hud.text = \
            'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
                self.dx, units, self.dy, units, location[0], units, location[1], units)

        self.inform.emit('[success] %s' % _("Done."))
        return location

    def on_copy_command(self):
        """
        Will copy a selection of objects, creating new objects.
        :return:
        """
        self.defaults.report_usage("on_copy_command()")

        def initialize(obj_init, app):
            obj_init.solid_geometry = deepcopy(obj.solid_geometry)
            try:
                obj_init.follow_geometry = deepcopy(obj.follow_geometry)
            except AttributeError:
                pass

            try:
                obj_init.apertures = deepcopy(obj.apertures)
            except AttributeError:
                pass

            try:
                if obj.tools:
                    obj_init.tools = deepcopy(obj.tools)
            except Exception as err:
                log.debug("App.on_copy_command() --> %s" % str(err))

            try:
                obj_init.source_file = deepcopy(obj.source_file)
            except (AttributeError, TypeError):
                pass

        def initialize_excellon(obj_init, app):
            obj_init.source_file = deepcopy(obj.source_file)

            obj_init.tools = deepcopy(obj.tools)

            # drills are offset, so they need to be deep copied
            obj_init.drills = deepcopy(obj.drills)
            # slots are offset, so they need to be deep copied
            obj_init.slots = deepcopy(obj.slots)
            obj_init.create_geometry()

        def initialize_script(obj_init, app_obj):
            obj_init.source_file = deepcopy(obj.source_file)

        def initialize_document(obj_init, app_obj):
            obj_init.source_file = deepcopy(obj.source_file)

        for obj in self.collection.get_selected():
            obj_name = obj.options["name"]

            try:
                if isinstance(obj, ExcellonObject):
                    self.new_object("excellon", str(obj_name) + "_copy", initialize_excellon)
                elif isinstance(obj, GerberObject):
                    self.new_object("gerber", str(obj_name) + "_copy", initialize)
                elif isinstance(obj, GeometryObject):
                    self.new_object("geometry", str(obj_name) + "_copy", initialize)
                elif isinstance(obj, ScriptObject):
                    self.new_object("script", str(obj_name) + "_copy", initialize_script)
                elif isinstance(obj, DocumentObject):
                    self.new_object("document", str(obj_name) + "_copy", initialize_document)
            except Exception as e:
                return "Operation failed: %s" % str(e)

    def on_copy_object2(self, custom_name):

        def initialize_geometry(obj_init, app):
            obj_init.solid_geometry = deepcopy(obj.solid_geometry)
            try:
                obj_init.follow_geometry = deepcopy(obj.follow_geometry)
            except AttributeError:
                pass

            try:
                obj_init.apertures = deepcopy(obj.apertures)
            except AttributeError:
                pass

            try:
                if obj.tools:
                    obj_init.tools = deepcopy(obj.tools)
            except Exception as ee:
                log.debug("on_copy_object2() --> %s" % str(ee))

        def initialize_gerber(obj_init, app):
            obj_init.solid_geometry = deepcopy(obj.solid_geometry)
            obj_init.apertures = deepcopy(obj.apertures)
            obj_init.aperture_macros = deepcopy(obj.aperture_macros)

        def initialize_excellon(obj_init, app):
            obj_init.tools = deepcopy(obj.tools)
            # drills are offset, so they need to be deep copied
            obj_init.drills = deepcopy(obj.drills)
            # slots are offset, so they need to be deep copied
            obj_init.slots = deepcopy(obj.slots)
            obj_init.create_geometry()

        for obj in self.collection.get_selected():
            obj_name = obj.options["name"]
            try:
                if isinstance(obj, ExcellonObject):
                    self.new_object("excellon", str(obj_name) + custom_name, initialize_excellon)
                elif isinstance(obj, GerberObject):
                    self.new_object("gerber", str(obj_name) + custom_name, initialize_gerber)
                elif isinstance(obj, GeometryObject):
                    self.new_object("geometry", str(obj_name) + custom_name, initialize_geometry)
            except Exception as er:
                return "Operation failed: %s" % str(er)

    def on_rename_object(self, text):
        """
        Will rename an object.

        :param text:    New name for the object.
        :return:
        """
        self.defaults.report_usage("on_rename_object()")

        named_obj = self.collection.get_active()
        for obj in named_obj:
            if obj is list:
                self.on_rename_object(text)
            else:
                try:
                    obj.options['name'] = text
                except Exception as e:
                    log.warning("App.on_rename_object() --> Could not rename the object in the list. --> %s" % str(e))

    def convert_any2geo(self):
        """
        Will convert any object out of Gerber, Excellon, Geometry to Geometry object.
        :return:
        """
        self.defaults.report_usage("convert_any2geo()")

        def initialize(obj_init, app):
            obj_init.solid_geometry = obj.solid_geometry
            try:
                obj_init.follow_geometry = obj.follow_geometry
            except AttributeError:
                pass
            try:
                obj_init.apertures = obj.apertures
            except AttributeError:
                pass

            try:
                if obj.tools:
                    obj_init.tools = obj.tools
            except AttributeError:
                pass

        def initialize_excellon(obj_init, app):
            # objs = self.collection.get_selected()
            # GeometryObject.merge(objs, obj)
            solid_geo = []
            for tool in obj.tools:
                for geo in obj.tools[tool]['solid_geometry']:
                    solid_geo.append(geo)
            obj_init.solid_geometry = deepcopy(solid_geo)

        if not self.collection.get_selected():
            log.warning("App.convert_any2geo --> No object selected")
            self.inform.emit('[WARNING_NOTCL] %s' %
                             _("No object is selected. Select an object and try again."))
            return

        for obj in self.collection.get_selected():
            obj_name = obj.options["name"]

            try:
                if isinstance(obj, ExcellonObject):
                    self.new_object("geometry", str(obj_name) + "_conv", initialize_excellon)
                else:
                    self.new_object("geometry", str(obj_name) + "_conv", initialize)
            except Exception as e:
                return "Operation failed: %s" % str(e)

    def convert_any2gerber(self):
        """
        Will convert any object out of Gerber, Excellon, Geometry to Gerber object.

        :return:
        """

        self.defaults.report_usage("convert_any2gerber()")

        def initialize_geometry(obj_init, app):
            apertures = {}
            apid = 0

            apertures[str(apid)] = {}
            apertures[str(apid)]['geometry'] = []
            for obj_orig in obj.solid_geometry:
                new_elem = {}
                new_elem['solid'] = obj_orig
                try:
                    new_elem['follow'] = obj_orig.exterior
                except AttributeError:
                    pass
                apertures[str(apid)]['geometry'].append(deepcopy(new_elem))
            apertures[str(apid)]['size'] = 0.0
            apertures[str(apid)]['type'] = 'C'

            obj_init.solid_geometry = deepcopy(obj.solid_geometry)
            obj_init.apertures = deepcopy(apertures)

        def initialize_excellon(obj_init, app):
            apertures = {}

            apid = 10
            for tool in obj.tools:
                apertures[str(apid)] = {}
                apertures[str(apid)]['geometry'] = []
                for geo in obj.tools[tool]['solid_geometry']:
                    new_el = {}
                    new_el['solid'] = geo
                    new_el['follow'] = geo.exterior
                    apertures[str(apid)]['geometry'].append(deepcopy(new_el))

                apertures[str(apid)]['size'] = float(obj.tools[tool]['C'])
                apertures[str(apid)]['type'] = 'C'
                apid += 1

            # create solid_geometry
            solid_geometry = []
            for apid in apertures:
                for geo_el in apertures[apid]['geometry']:
                    solid_geometry.append(geo_el['solid'])

            solid_geometry = MultiPolygon(solid_geometry)
            solid_geometry = solid_geometry.buffer(0.0000001)

            obj_init.solid_geometry = deepcopy(solid_geometry)
            obj_init.apertures = deepcopy(apertures)
            # clear the working objects (perhaps not necessary due of Python GC)
            apertures.clear()

        if not self.collection.get_selected():
            log.warning("App.convert_any2gerber --> No object selected")
            self.inform.emit('[WARNING_NOTCL] %s' %
                             _("No object is selected. Select an object and try again."))
            return

        for obj in self.collection.get_selected():

            obj_name = obj.options["name"]

            try:
                if isinstance(obj, ExcellonObject):
                    self.new_object("gerber", str(obj_name) + "_conv", initialize_excellon)
                elif isinstance(obj, GeometryObject):
                    self.new_object("gerber", str(obj_name) + "_conv", initialize_geometry)
                else:
                    log.warning("App.convert_any2gerber --> This is no vaild object for conversion.")

            except Exception as e:
                return "Operation failed: %s" % str(e)

    def abort_all_tasks(self):
        """
        Executed when a certain key combo is pressed (Ctrl+Alt+X). Will abort current task
        on the first possible occasion.

        :return:
        """
        if self.abort_flag is False:
            self.inform.emit(_("Aborting. The current task will be gracefully closed as soon as possible..."))
            self.abort_flag = True
            self.cleanup.emit()

    def app_is_idle(self):
        if self.abort_flag:
            self.inform.emit('[WARNING_NOTCL] %s' % _("The current task was gracefully closed on user request..."))
            self.abort_flag = False

    def on_selectall(self):
        """
        Will draw a selection box shape around the selected objects.

        :return:
        """
        self.defaults.report_usage("on_selectall()")

        # delete the possible selection box around a possible selected object
        self.delete_selection_shape()
        for name in self.collection.get_names():
            self.collection.set_active(name)
            curr_sel_obj = self.collection.get_by_name(name)
            # create the selection box around the selected object
            if self.defaults['global_selection_shape'] is True:
                self.draw_selection_shape(curr_sel_obj)

    def on_preferences(self):
        """
        Adds the Preferences in a Tab in Plot Area

        :return:
        """

        # add the tab if it was closed
        self.ui.plot_tab_area.addTab(self.ui.preferences_tab, _("Preferences"))

        # delete the absolute and relative position and messages in the infobar
        # self.ui.position_label.setText("")
        # self.ui.rel_position_label.setText("")

        # Switch plot_area to preferences page
        self.ui.plot_tab_area.setCurrentWidget(self.ui.preferences_tab)
        # self.ui.show()

        # detect changes in the preferences
        for idx in range(self.ui.pref_tab_area.count()):
            for tb in self.ui.pref_tab_area.widget(idx).findChildren(QtCore.QObject):
                try:
                    try:
                        tb.textEdited.disconnect(self.preferencesUiManager.on_preferences_edited)
                    except (TypeError, AttributeError):
                        pass
                    tb.textEdited.connect(self.preferencesUiManager.on_preferences_edited)
                except AttributeError:
                    pass

                try:
                    try:
                        tb.modificationChanged.disconnect(self.preferencesUiManager.on_preferences_edited)
                    except (TypeError, AttributeError):
                        pass
                    tb.modificationChanged.connect(self.preferencesUiManager.on_preferences_edited)
                except AttributeError:
                    pass

                try:
                    try:
                        tb.toggled.disconnect(self.preferencesUiManager.on_preferences_edited)
                    except (TypeError, AttributeError):
                        pass
                    tb.toggled.connect(self.preferencesUiManager.on_preferences_edited)
                except AttributeError:
                    pass

                try:
                    try:
                        tb.valueChanged.disconnect(self.preferencesUiManager.on_preferences_edited)
                    except (TypeError, AttributeError):
                        pass
                    tb.valueChanged.connect(self.preferencesUiManager.on_preferences_edited)
                except AttributeError:
                    pass

                try:
                    try:
                        tb.currentIndexChanged.disconnect(self.preferencesUiManager.on_preferences_edited)
                    except (TypeError, AttributeError):
                        pass
                    tb.currentIndexChanged.connect(self.preferencesUiManager.on_preferences_edited)
                except AttributeError:
                    pass

    def on_tools_database(self, source='app'):
        """
        Adds the Tools Database in a Tab in Plot Area.

        :return:
        """
        for idx in range(self.ui.plot_tab_area.count()):
            if self.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                # there can be only one instance of Tools Database at one time
                return

        if source == 'app':
            self.tools_db_tab = ToolsDB2(
                app=self,
                parent=self.ui,
                callback_on_edited=self.on_tools_db_edited,
                callback_on_tool_request=self.on_geometry_tool_add_from_db_executed
            )
        elif source == 'ncc':
            self.tools_db_tab = ToolsDB2(
                app=self,
                parent=self.ui,
                callback_on_edited=self.on_tools_db_edited,
                callback_on_tool_request=self.ncclear_tool.on_ncc_tool_add_from_db_executed
            )
        elif source == 'paint':
            self.tools_db_tab = ToolsDB2(
                app=self,
                parent=self.ui,
                callback_on_edited=self.on_tools_db_edited,
                callback_on_tool_request=self.paint_tool.on_paint_tool_add_from_db_executed
            )

        # add the tab if it was closed
        try:
            self.ui.plot_tab_area.addTab(self.tools_db_tab, _("Tools Database"))
            self.tools_db_tab.setObjectName("database_tab")
        except Exception as e:
            log.debug("App.on_tools_database() --> %s" % str(e))
            return

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        # Switch plot_area to preferences page
        self.ui.plot_tab_area.setCurrentWidget(self.tools_db_tab)

        # detect changes in the Tools in Tools DB, connect signals from table widget in tab
        self.tools_db_tab.ui_connect()

    def on_tools_db_edited(self):
        """
        Executed whenever a tool is edited in Tools Database.
        Will color the text of the Tools Database tab to Red color.

        :return:
        """

        self.inform.emit('[WARNING_NOTCL] %s' % _("Tools in Tools Database edited but not saved."))

        for idx in range(self.ui.plot_tab_area.count()):
            if self.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                self.ui.plot_tab_area.tabBar.setTabTextColor(idx, QtGui.QColor('red'))
                self.tools_db_tab.save_db_btn.setStyleSheet("QPushButton {color: red;}")

        self.tools_db_changed_flag = True

    def on_geometry_tool_add_from_db_executed(self, tool):
        """
        Here add the tool from DB  in the selected geometry object.

        :return:
        """
        tool_from_db = deepcopy(tool)

        obj = self.collection.get_active()
        if isinstance(obj, GeometryObject):
            obj.on_tool_from_db_inserted(tool=tool_from_db)

            # close the tab and delete it
            for idx in range(self.ui.plot_tab_area.count()):
                if self.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                    wdg = self.ui.plot_tab_area.widget(idx)
                    wdg.deleteLater()
                    self.ui.plot_tab_area.removeTab(idx)
            self.inform.emit('[success] %s' % _("Tool from DB added in Tool Table."))
        else:
            self.inform.emit('[ERROR_NOTCL] %s' % _("Adding tool from DB is not allowed for this object."))

    def on_plot_area_tab_closed(self, tab_obj_name):
        """
        Executed whenever a QTab is closed in the Plot Area.

        :param tab_obj_name: The objectName of the Tab that was closed. This objectName is assigned on Tab creation
        :return:
        """

        if tab_obj_name == "preferences_tab":
            self.preferencesUiManager.on_close_preferences_tab()
        elif tab_obj_name == "database_tab":
            # disconnect the signals from the table widget in tab
            self.tools_db_tab.ui_disconnect()

            if self.tools_db_changed_flag is True:
                msgbox = QtWidgets.QMessageBox()
                msgbox.setText(_("One or more Tools are edited.\n"
                                 "Do you want to update the Tools Database?"))
                msgbox.setWindowTitle(_("Save Tools Database"))
                msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/save_as.png'))

                bt_yes = msgbox.addButton(_('Yes'), QtWidgets.QMessageBox.YesRole)
                msgbox.addButton(_('No'), QtWidgets.QMessageBox.NoRole)

                msgbox.setDefaultButton(bt_yes)
                msgbox.exec_()
                response = msgbox.clickedButton()

                if response == bt_yes:
                    self.tools_db_tab.on_save_tools_db()
                    self.inform.emit('[success] %s' % "Tools DB saved to file.")
                else:
                    self.tools_db_changed_flag = False
                    self.inform.emit('')
                    return
            self.tools_db_tab.deleteLater()
        elif tab_obj_name == "text_editor_tab":
            self.toggle_codeeditor = False
        elif tab_obj_name == "bookmarks_tab":
            self.book_dialog_tab.rebuild_actions()
            self.book_dialog_tab.deleteLater()
        else:
            return

    # def on_plotarea_tab_closed(self, tab_idx):
    #     """
    #
    #     :param tab_idx: Index of the Tab from the plotarea that was closed
    #     :return:
    #     """
    #     widget = self.ui.plot_tab_area.widget(tab_idx)
    #
    #     if widget is not None:
    #         widget.deleteLater()
    #     self.ui.plot_tab_area.removeTab(tab_idx)

    def on_flipy(self):
        """
        Executed when the menu entry in Options -> Flip on Y axis is clicked.

        :return:
        """
        self.defaults.report_usage("on_flipy()")

        obj_list = self.collection.get_selected()
        xminlist = []
        yminlist = []
        xmaxlist = []
        ymaxlist = []

        if not obj_list:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected to Flip on Y axis."))
        else:
            try:
                # first get a bounding box to fit all
                for obj in obj_list:
                    xmin, ymin, xmax, ymax = obj.bounds()
                    xminlist.append(xmin)
                    yminlist.append(ymin)
                    xmaxlist.append(xmax)
                    ymaxlist.append(ymax)

                # get the minimum x,y and maximum x,y for all objects selected
                xminimal = min(xminlist)
                yminimal = min(yminlist)
                xmaximal = max(xmaxlist)
                ymaximal = max(ymaxlist)

                px = 0.5 * (xminimal + xmaximal)
                py = 0.5 * (yminimal + ymaximal)

                # execute mirroring
                for obj in obj_list:
                    obj.mirror('X', [px, py])
                    obj.plot()
                    self.object_changed.emit(obj)
                self.inform.emit('[success] %s' %
                                 _("Flip on Y axis done."))
            except Exception as e:
                self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Flip action was not executed."), str(e)))
                return

    def on_flipx(self):
        """
        Executed when the menu entry in Options -> Flip on X axis is clicked.

        :return:
        """

        self.defaults.report_usage("on_flipx()")

        obj_list = self.collection.get_selected()
        xminlist = []
        yminlist = []
        xmaxlist = []
        ymaxlist = []

        if not obj_list:
            self.inform.emit('[WARNING_NOTCL] %s' %
                             _("No object selected to Flip on X axis."))
        else:
            try:
                # first get a bounding box to fit all
                for obj in obj_list:
                    xmin, ymin, xmax, ymax = obj.bounds()
                    xminlist.append(xmin)
                    yminlist.append(ymin)
                    xmaxlist.append(xmax)
                    ymaxlist.append(ymax)

                # get the minimum x,y and maximum x,y for all objects selected
                xminimal = min(xminlist)
                yminimal = min(yminlist)
                xmaximal = max(xmaxlist)
                ymaximal = max(ymaxlist)

                px = 0.5 * (xminimal + xmaximal)
                py = 0.5 * (yminimal + ymaximal)

                # execute mirroring
                for obj in obj_list:
                    obj.mirror('Y', [px, py])
                    obj.plot()
                    self.object_changed.emit(obj)
                self.inform.emit('[success] %s' %
                                 _("Flip on X axis done."))
            except Exception as e:
                self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Flip action was not executed."), str(e)))
                return

    def on_rotate(self, silent=False, preset=None):
        """
        Executed when Options -> Rotate Selection menu entry is clicked.

        :param silent:  If silent is True then use the preset value for the angle of the rotation.
        :param preset:  A value to be used as predefined angle for rotation.
        :return:
        """
        self.defaults.report_usage("on_rotate()")

        obj_list = self.collection.get_selected()
        xminlist = []
        yminlist = []
        xmaxlist = []
        ymaxlist = []

        if not obj_list:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected to Rotate."))
        else:
            if silent is False:
                rotatebox = FCInputDialog(title=_("Transform"), text=_("Enter the Angle value:"),
                                          min=-360, max=360, decimals=4,
                                          init_val=float(self.defaults['tools_transform_rotate']))
                num, ok = rotatebox.get_value()
            else:
                num = preset
                ok = True

            if ok:
                try:
                    # first get a bounding box to fit all
                    for obj in obj_list:
                        xmin, ymin, xmax, ymax = obj.bounds()
                        xminlist.append(xmin)
                        yminlist.append(ymin)
                        xmaxlist.append(xmax)
                        ymaxlist.append(ymax)

                    # get the minimum x,y and maximum x,y for all objects selected
                    xminimal = min(xminlist)
                    yminimal = min(yminlist)
                    xmaximal = max(xmaxlist)
                    ymaximal = max(ymaxlist)
                    px = 0.5 * (xminimal + xmaximal)
                    py = 0.5 * (yminimal + ymaximal)

                    for sel_obj in obj_list:
                        sel_obj.rotate(-float(num), point=(px, py))
                        sel_obj.plot()
                        self.object_changed.emit(sel_obj)
                    self.inform.emit('[success] %s' %
                                     _("Rotation done."))
                except Exception as e:
                    self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Rotation movement was not executed."), str(e)))
                    return

    def on_skewx(self):
        """
        Executed when the menu entry in Options -> Skew on X axis is clicked.

        :return:
        """

        self.defaults.report_usage("on_skewx()")

        obj_list = self.collection.get_selected()
        xminlist = []
        yminlist = []

        if not obj_list:
            self.inform.emit('[WARNING_NOTCL] %s' %
                             _("No object selected to Skew/Shear on X axis."))
        else:
            skewxbox = FCInputDialog(title=_("Transform"), text=_("Enter the Angle value:"),
                                     min=-360, max=360, decimals=4,
                                     init_val=float(self.defaults['tools_transform_skew_x']))
            num, ok = skewxbox.get_value()
            if ok:
                # first get a bounding box to fit all
                for obj in obj_list:
                    xmin, ymin, xmax, ymax = obj.bounds()
                    xminlist.append(xmin)
                    yminlist.append(ymin)

                # get the minimum x,y and maximum x,y for all objects selected
                xminimal = min(xminlist)
                yminimal = min(yminlist)

                for obj in obj_list:
                    obj.skew(num, 0, point=(xminimal, yminimal))
                    obj.plot()
                    self.object_changed.emit(obj)
                self.inform.emit('[success] %s' %
                                 _("Skew on X axis done."))

    def on_skewy(self):
        """
        Executed when the menu entry in Options -> Skew on Y axis is clicked.

        :return:
        """

        self.defaults.report_usage("on_skewy()")

        obj_list = self.collection.get_selected()
        xminlist = []
        yminlist = []

        if not obj_list:
            self.inform.emit('[WARNING_NOTCL] %s' %
                             _("No object selected to Skew/Shear on Y axis."))
        else:
            skewybox = FCInputDialog(title=_("Transform"), text=_("Enter the Angle value:"),
                                     min=-360, max=360, decimals=4,
                                     init_val=float(self.defaults['tools_transform_skew_y']))
            num, ok = skewybox.get_value()
            if ok:
                # first get a bounding box to fit all
                for obj in obj_list:
                    xmin, ymin, xmax, ymax = obj.bounds()
                    xminlist.append(xmin)
                    yminlist.append(ymin)

                # get the minimum x,y and maximum x,y for all objects selected
                xminimal = min(xminlist)
                yminimal = min(yminlist)

                for obj in obj_list:
                    obj.skew(0, num, point=(xminimal, yminimal))
                    obj.plot()
                    self.object_changed.emit(obj)
                self.inform.emit('[success] %s' %
                                 _("Skew on Y axis done."))

    def on_plots_updated(self):
        """
        Callback used to report when the plots have changed.
        Adjust axes and zooms to fit.

        :return: None
        """
        if self.is_legacy is False:
            self.plotcanvas.update()
        else:
            self.plotcanvas.auto_adjust_axes()

        self.on_zoom_fit(None)
        self.collection.update_view()
        # self.inform.emit(_("Plots updated ..."))

    def on_toolbar_replot(self):
        """
        Callback for toolbar button. Re-plots all objects.

        :return: None
        """

        self.defaults.report_usage("on_toolbar_replot")
        self.log.debug("on_toolbar_replot()")

        try:
            self.collection.get_active().read_form()
        except AttributeError:
            self.log.debug("on_toolbar_replot(): AttributeError")
            pass

        self.plot_all()

    def on_row_activated(self, index):
        if index.isValid():
            if index.internalPointer().parent_item != self.collection.root_item:
                self.ui.notebook.setCurrentWidget(self.ui.selected_tab)
        self.collection.on_item_activated(index)

    def on_row_selected(self, obj_name):
        """
        This is a special string; when received it will make all Menu -> Objects entries unchecked
        It mean we clicked outside of the items and deselected all

        :param obj_name:
        :return:
        """
        if obj_name == 'none':
            for act in self.ui.menuobjects.actions():
                act.setChecked(False)
            return

        # get the name of the selected objects and add them to a list
        name_list = []
        for obj in self.collection.get_selected():
            name_list.append(obj.options['name'])

        # set all actions as unchecked but the ones selected make them checked
        for act in self.ui.menuobjects.actions():
            act.setChecked(False)
            if act.text() in name_list:
                act.setChecked(True)

    def on_collection_updated(self, obj, state, old_name):
        """
        Create a menu from the object loaded in the collection.

        :param obj:         object that was changed (added, deleted, renamed)
        :param state:       what was done with the object. Can be: added, deleted, delete_all, renamed
        :param old_name:    the old name of the object before the action that triggered this slot happened
        :return:            None
        """
        icon_files = {
            "gerber": self.resource_location + "/flatcam_icon16.png",
            "excellon": self.resource_location + "/drill16.png",
            "cncjob": self.resource_location + "/cnc16.png",
            "geometry": self.resource_location + "/geometry16.png",
            "script": self.resource_location + "/script_new16.png",
            "document": self.resource_location + "/notes16_1.png"
        }

        if state == 'append':
            for act in self.ui.menuobjects.actions():
                try:
                    act.triggered.disconnect()
                except TypeError:
                    pass
            self.ui.menuobjects.clear()

            gerber_list = []
            exc_list = []
            cncjob_list = []
            geo_list = []
            script_list = []
            doc_list = []

            for name in self.collection.get_names():
                obj_named = self.collection.get_by_name(name)
                if obj_named.kind == 'gerber':
                    gerber_list.append(name)
                elif obj_named.kind == 'excellon':
                    exc_list.append(name)
                elif obj_named.kind == 'cncjob':
                    cncjob_list.append(name)
                elif obj_named.kind == 'geometry':
                    geo_list.append(name)
                elif obj_named.kind == 'script':
                    script_list.append(name)
                elif obj_named.kind == 'document':
                    doc_list.append(name)

            def add_act(o_name):
                obj_for_icon = self.collection.get_by_name(o_name)
                add_action = QtWidgets.QAction(parent=self.ui.menuobjects)
                add_action.setCheckable(True)
                add_action.setText(o_name)
                add_action.setIcon(QtGui.QIcon(icon_files[obj_for_icon.kind]))
                add_action.triggered.connect(
                    lambda: self.collection.set_active(o_name) if add_action.isChecked() is True else
                    self.collection.set_inactive(o_name))
                self.ui.menuobjects.addAction(add_action)

            for name in gerber_list:
                add_act(name)
            self.ui.menuobjects.addSeparator()

            for name in exc_list:
                add_act(name)
            self.ui.menuobjects.addSeparator()

            for name in cncjob_list:
                add_act(name)
            self.ui.menuobjects.addSeparator()

            for name in geo_list:
                add_act(name)
            self.ui.menuobjects.addSeparator()

            for name in script_list:
                add_act(name)
            self.ui.menuobjects.addSeparator()

            for name in doc_list:
                add_act(name)

            self.ui.menuobjects.addSeparator()
            self.ui.menuobjects_selall = self.ui.menuobjects.addAction(
                QtGui.QIcon(self.resource_location + '/select_all.png'),
                _('Select All')
            )
            self.ui.menuobjects_unselall = self.ui.menuobjects.addAction(
                QtGui.QIcon(self.resource_location + '/deselect_all32.png'),
                _('Deselect All')
            )
            self.ui.menuobjects_selall.triggered.connect(lambda: self.on_objects_selection(True))
            self.ui.menuobjects_unselall.triggered.connect(lambda: self.on_objects_selection(False))

        elif state == 'delete':
            for act in self.ui.menuobjects.actions():
                if act.text() == obj.options['name']:
                    try:
                        act.triggered.disconnect()
                    except TypeError:
                        pass
                    self.ui.menuobjects.removeAction(act)
                    break
        elif state == 'rename':
            for act in self.ui.menuobjects.actions():
                if act.text() == old_name:
                    add_action = QtWidgets.QAction(parent=self.ui.menuobjects)
                    add_action.setText(obj.options['name'])
                    add_action.setIcon(QtGui.QIcon(icon_files[obj.kind]))
                    add_action.triggered.connect(
                        lambda: self.collection.set_active(obj.options['name']) if add_action.isChecked() is True else
                        self.collection.set_inactive(obj.options['name']))

                    self.ui.menuobjects.insertAction(act, add_action)

                    try:
                        act.triggered.disconnect()
                    except TypeError:
                        pass
                    self.ui.menuobjects.removeAction(act)
                    break
        elif state == 'delete_all':
            for act in self.ui.menuobjects.actions():
                try:
                    act.triggered.disconnect()
                except TypeError:
                    pass
            self.ui.menuobjects.clear()

            self.ui.menuobjects.addSeparator()
            self.ui.menuobjects_selall = self.ui.menuobjects.addAction(
                QtGui.QIcon(self.resource_location + '/select_all.png'),
                _('Select All')
            )
            self.ui.menuobjects_unselall = self.ui.menuobjects.addAction(
                QtGui.QIcon(self.resource_location + '/deselect_all32.png'),
                _('Deselect All')
            )
            self.ui.menuobjects_selall.triggered.connect(lambda: self.on_objects_selection(True))
            self.ui.menuobjects_unselall.triggered.connect(lambda: self.on_objects_selection(False))

    def on_objects_selection(self, on_off):
        obj_list = self.collection.get_names()

        if on_off is True:
            self.collection.set_all_active()
            for act in self.ui.menuobjects.actions():
                try:
                    act.setChecked(True)
                except Exception:
                    pass
            if obj_list:
                self.inform.emit('[selected] %s' % _("All objects are selected."))
        else:
            self.collection.set_all_inactive()
            for act in self.ui.menuobjects.actions():
                try:
                    act.setChecked(False)
                except Exception:
                    pass

            if obj_list:
                self.inform.emit('%s' % _("Objects selection is cleared."))
            else:
                self.inform.emit('')

    def grid_status(self):
        if self.ui.grid_snap_btn.isChecked():
            return True
        else:
            return False

    def populate_cmenu_grids(self):
        units = self.defaults['units'].lower()

        # for act in self.ui.cmenu_gridmenu.actions():
        #     act.triggered.disconnect()
        self.ui.cmenu_gridmenu.clear()

        sorted_list = sorted(self.defaults["global_grid_context_menu"][str(units)])

        grid_toggle = self.ui.cmenu_gridmenu.addAction(QtGui.QIcon(self.resource_location + '/grid32_menu.png'),
                                                       _("Grid On/Off"))
        grid_toggle.setCheckable(True)
        grid_toggle.setChecked(True) if self.grid_status() else grid_toggle.setChecked(False)

        self.ui.cmenu_gridmenu.addSeparator()
        for grid in sorted_list:
            action = self.ui.cmenu_gridmenu.addAction(QtGui.QIcon(self.resource_location + '/grid32_menu.png'),
                                                      "%s" % str(grid))
            action.triggered.connect(self.set_grid)

        self.ui.cmenu_gridmenu.addSeparator()
        grid_add = self.ui.cmenu_gridmenu.addAction(QtGui.QIcon(self.resource_location + '/plus32.png'),
                                                    _("Add"))
        grid_delete = self.ui.cmenu_gridmenu.addAction(QtGui.QIcon(self.resource_location + '/delete32.png'),
                                                       _("Delete"))
        grid_add.triggered.connect(self.on_grid_add)
        grid_delete.triggered.connect(self.on_grid_delete)
        grid_toggle.triggered.connect(lambda: self.ui.grid_snap_btn.trigger())

    def set_grid(self):
        menu_action = self.sender()
        assert isinstance(menu_action, QtWidgets.QAction), "Expected QAction got %s" % type(menu_action)

        self.ui.grid_gap_x_entry.setText(menu_action.text())
        self.ui.grid_gap_y_entry.setText(menu_action.text())

    def on_grid_add(self):
        # ## Current application units in lower Case
        units = self.defaults['units'].lower()

        grid_add_popup = FCInputDialog(title=_("New Grid ..."),
                                       text=_('Enter a Grid Value:'),
                                       min=0.0000, max=99.9999, decimals=4)
        grid_add_popup.setWindowIcon(QtGui.QIcon(self.resource_location + '/plus32.png'))

        val, ok = grid_add_popup.get_value()
        if ok:
            if float(val) == 0:
                self.inform.emit('[WARNING_NOTCL] %s' %
                                 _("Please enter a grid value with non-zero value, in Float format."))
                return
            else:
                if val not in self.defaults["global_grid_context_menu"][str(units)]:
                    self.defaults["global_grid_context_menu"][str(units)].append(val)
                    self.inform.emit('[success] %s...' %
                                     _("New Grid added"))
                else:
                    self.inform.emit('[WARNING_NOTCL] %s...' %
                                     _("Grid already exists"))
        else:
            self.inform.emit('[WARNING_NOTCL] %s...' %
                             _("Adding New Grid cancelled"))

    def on_grid_delete(self):
        # ## Current application units in lower Case
        units = self.defaults['units'].lower()

        grid_del_popup = FCInputDialog(title="Delete Grid ...",
                                       text='Enter a Grid Value:',
                                       min=0.0000, max=99.9999, decimals=4)
        grid_del_popup.setWindowIcon(QtGui.QIcon(self.resource_location + '/delete32.png'))

        val, ok = grid_del_popup.get_value()
        if ok:
            if float(val) == 0:
                self.inform.emit('[WARNING_NOTCL] %s' %
                                 _("Please enter a grid value with non-zero value, in Float format."))
                return
            else:
                try:
                    self.defaults["global_grid_context_menu"][str(units)].remove(val)
                except ValueError:
                    self.inform.emit('[ERROR_NOTCL]%s...' %
                                     _(" Grid Value does not exist"))
                    return
                self.inform.emit('[success] %s...' %
                                 _("Grid Value deleted"))
        else:
            self.inform.emit('[WARNING_NOTCL] %s...' %
                             _("Delete Grid value cancelled"))

    def on_shortcut_list(self):
        self.defaults.report_usage("on_shortcut_list()")

        # add the tab if it was closed
        self.ui.plot_tab_area.addTab(self.ui.shortcuts_tab, _("Key Shortcut List"))

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        # Switch plot_area to preferences page
        self.ui.plot_tab_area.setCurrentWidget(self.ui.shortcuts_tab)
        # self.ui.show()

    def on_select_tab(self, name):
        # if the splitter is hidden, display it, else hide it but only if the current widget is the same
        if self.ui.splitter.sizes()[0] == 0:
            self.ui.splitter.setSizes([1, 1])
        else:
            if self.ui.notebook.currentWidget().objectName() == name + '_tab':
                self.ui.splitter.setSizes([0, 1])

        if name == 'project':
            self.ui.notebook.setCurrentWidget(self.ui.project_tab)
        elif name == 'selected':
            self.ui.notebook.setCurrentWidget(self.ui.selected_tab)
        elif name == 'tool':
            self.ui.notebook.setCurrentWidget(self.ui.tool_tab)

    def on_copy_name(self):
        self.defaults.report_usage("on_copy_name()")

        obj = self.collection.get_active()
        try:
            name = obj.options["name"]
        except AttributeError:
            log.debug("on_copy_name() --> No object selected to copy it's name")
            self.inform.emit('[WARNING_NOTCL]%s' %
                             _(" No object selected to copy it's name"))
            return

        self.clipboard.setText(name)
        self.inform.emit(_("Name copied on clipboard ..."))

    def on_mouse_click_over_plot(self, event):
        """
        Default actions are:
        :param event: Contains information about the event, like which button
            was clicked, the pixel coordinates and the axes coordinates.
        :return: None
        """
        self.pos = []

        if self.is_legacy is False:
            event_pos = event.pos
            # pan_button = 2 if self.defaults["global_pan_button"] == '2'else 3
            # # Set the mouse button for panning
            # self.plotcanvas.view.camera.pan_button_setting = pan_button
        else:
            event_pos = (event.xdata, event.ydata)
            # Matplotlib has the middle and right buttons mapped in reverse compared with VisPy
            # pan_button = 3 if self.defaults["global_pan_button"] == '2' else 2

        # So it can receive key presses
        self.plotcanvas.native.setFocus()

        self.pos_canvas = self.plotcanvas.translate_coords(event_pos)

        if self.grid_status():
            self.pos = self.geo_editor.snap(self.pos_canvas[0], self.pos_canvas[1])
        else:
            self.pos = (self.pos_canvas[0], self.pos_canvas[1])

        try:
            if event.button == 1:
                # Reset here the relative coordinates so there is a new reference on the click position
                if self.rel_point1 is None:
                    self.rel_point1 = self.pos
                else:
                    self.rel_point2 = copy(self.rel_point1)
                    self.rel_point1 = self.pos

            self.on_mouse_move_over_plot(event, origin_click=True)
        except Exception as e:
            App.log.debug("App.on_mouse_click_over_plot() --> Outside plot? --> %s" % str(e))

    def on_mouse_double_click_over_plot(self, event):
        if event.button == 1:
            self.doubleclick = True

    def on_mouse_move_over_plot(self, event, origin_click=None):
        """
        Callback for the mouse motion event over the plot.

        :param event: Contains information about the event.
        :param origin_click
        :return: None
        """

        if self.is_legacy is False:
            event_pos = event.pos
            if self.defaults["global_pan_button"] == '2':
                pan_button = 2
            else:
                pan_button = 3
            self.event_is_dragging = event.is_dragging
        else:
            event_pos = (event.xdata, event.ydata)
            # Matplotlib has the middle and right buttons mapped in reverse compared with VisPy
            if self.defaults["global_pan_button"] == '2':
                pan_button = 3
            else:
                pan_button = 2
            self.event_is_dragging = self.plotcanvas.is_dragging

        # So it can receive key presses but not when the Tcl Shell is active
        if not self.ui.shell_dock.isVisible():
            if not self.plotcanvas.native.hasFocus():
                self.plotcanvas.native.setFocus()

        self.pos_jump = event_pos

        self.ui.popMenu.mouse_is_panning = False

        if origin_click is None:
            # if the RMB is clicked and mouse is moving over plot then 'panning_action' is True
            if event.button == pan_button and self.event_is_dragging == 1:

                # if a popup menu is active don't change mouse_is_panning variable because is not True
                if self.ui.popMenu.popup_active:
                    self.ui.popMenu.popup_active = False
                    return
                self.ui.popMenu.mouse_is_panning = True
                return

        if self.rel_point1 is not None:
            try:  # May fail in case mouse not within axes
                pos_canvas = self.plotcanvas.translate_coords(event_pos)

                if pos_canvas[0] is None or pos_canvas[1] is None:
                    return

                if self.grid_status():
                    pos = self.geo_editor.snap(pos_canvas[0], pos_canvas[1])

                    # Update cursor
                    self.app_cursor.set_data(np.asarray([(pos[0], pos[1])]),
                                             symbol='++', edge_color=self.cursor_color_3D,
                                             edge_width=self.defaults["global_cursor_width"],
                                             size=self.defaults["global_cursor_size"])
                else:
                    pos = (pos_canvas[0], pos_canvas[1])

                self.dx = pos[0] - float(self.rel_point1[0])
                self.dy = pos[1] - float(self.rel_point1[1])

                # self.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
                #                                "<b>Y</b>: %.4f" % (pos[0], pos[1]))
                # self.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                #                                    "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (self.dx, self.dy))

                units = self.defaults["units"].lower()
                self.plotcanvas.text_hud.text = \
                    'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
                        self.dx, units, self.dy, units, pos[0], units, pos[1], units)

                self.mouse = [pos[0], pos[1]]

                # if the mouse is moved and the LMB is clicked then the action is a selection
                if self.event_is_dragging == 1 and event.button == 1:
                    self.delete_selection_shape()
                    if self.dx < 0:
                        self.draw_moving_selection_shape(self.pos, pos, color=self.defaults['global_alt_sel_line'],
                                                         face_color=self.defaults['global_alt_sel_fill'])
                        self.selection_type = False
                    elif self.dx >= 0:
                        self.draw_moving_selection_shape(self.pos, pos)
                        self.selection_type = True
                    else:
                        self.selection_type = None
                else:
                    self.selection_type = None

                # hover effect - enabled in Preferences -> General -> GUI Settings
                if self.defaults['global_hover']:
                    for obj in self.collection.get_list():
                        try:
                            # select the object(s) only if it is enabled (plotted)
                            if obj.options['plot']:
                                if obj not in self.collection.get_selected():
                                    poly_obj = Polygon(
                                        [(obj.options['xmin'], obj.options['ymin']),
                                         (obj.options['xmax'], obj.options['ymin']),
                                         (obj.options['xmax'], obj.options['ymax']),
                                         (obj.options['xmin'], obj.options['ymax'])]
                                    )
                                    if Point(pos).within(poly_obj):
                                        if obj.isHovering is False:
                                            obj.isHovering = True
                                            obj.notHovering = True
                                            # create the selection box around the selected object
                                            self.draw_hover_shape(obj, color='#d1e0e0FF')
                                    else:
                                        if obj.notHovering is True:
                                            obj.notHovering = False
                                            obj.isHovering = False
                                            self.delete_hover_shape()
                        except Exception:
                            # the Exception here will happen if we try to select on screen and we have an
                            # newly (and empty) just created Geometry or Excellon object that do not have the
                            # xmin, xmax, ymin, ymax options.
                            # In this case poly_obj creation (see above) will fail
                            pass

            except Exception as e:
                log.debug("App.on_mouse_move_over_plot() - rel_point1 is not None -> %s" % str(e))
                # self.ui.position_label.setText("")
                # self.ui.rel_position_label.setText("")
                self.mouse = None

    def on_mouse_click_release_over_plot(self, event):
        """
        Callback for the mouse click release over plot. This event is generated by the Matplotlib backend
        and has been registered in ''self.__init__()''.
        :param event: contains information about the event.
        :return:
        """

        if self.is_legacy is False:
            event_pos = event.pos
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # Matplotlib has the middle and right buttons mapped in reverse compared with VisPy
            right_button = 3

        pos_canvas = self.plotcanvas.translate_coords(event_pos)
        if self.grid_status():
            pos = self.geo_editor.snap(pos_canvas[0], pos_canvas[1])
        else:
            pos = (pos_canvas[0], pos_canvas[1])

        # if the released mouse button was RMB then test if it was a panning motion or not, if not it was a context
        # canvas menu
        if event.button == right_button and self.ui.popMenu.mouse_is_panning is False:  # right click
            self.ui.popMenu.mouse_is_panning = False

            self.cursor = QtGui.QCursor()
            self.populate_cmenu_grids()
            self.ui.popMenu.popup(self.cursor.pos())

        # if the released mouse button was LMB then test if we had a right-to-left selection or a left-to-right
        # selection and then select a type of selection ("enclosing" or "touching")

        if event.button == 1:  # left click
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            # If the SHIFT key is pressed when LMB is clicked then the coordinates are copied to clipboard
            if modifiers == QtCore.Qt.ShiftModifier:
                # do not auto open the Project Tab
                self.click_noproject = True

                self.clipboard.setText(
                    self.defaults["global_point_clipboard_format"] %
                    (self.decimals, self.pos[0], self.decimals, self.pos[1])
                )
                self.inform.emit('[success] %s' % _("Coordinates copied to clipboard."))
                return

            if self.doubleclick is True:
                self.doubleclick = False
                if self.collection.get_selected():
                    self.ui.notebook.setCurrentWidget(self.ui.selected_tab)
                    if self.ui.splitter.sizes()[0] == 0:
                        self.ui.splitter.setSizes([1, 1])
                    try:
                        # delete the selection shape(S) as it may be in the way
                        self.delete_selection_shape()
                        self.delete_hover_shape()
                    except Exception as e:
                        log.warning("FlatCAMApp.on_mouse_click_release_over_plot() double click --> Error: %s" % str(e))
                        return
            else:
                # WORKAROUND for LEGACY MODE
                if self.is_legacy is True:
                    # if there is no move on canvas then we have no dragging selection
                    if self.dx == 0 or self.dy == 0:
                        self.selection_type = None

                if self.selection_type is not None:
                    try:
                        self.selection_area_handler(self.pos, pos, self.selection_type)
                        self.selection_type = None
                    except Exception as e:
                        log.warning("FlatCAMApp.on_mouse_click_release_over_plot() select area --> Error: %s" % str(e))
                        return
                else:

                    key_modifier = QtWidgets.QApplication.keyboardModifiers()
                    if key_modifier == QtCore.Qt.ShiftModifier:
                        mod_key = 'Shift'
                    elif key_modifier == QtCore.Qt.ControlModifier:
                        mod_key = 'Control'
                    else:
                        mod_key = None

                    try:
                        if self.command_active is None:
                            # If the CTRL key is pressed when the LMB is clicked then if the object is selected it will
                            # deselect, and if it's not selected then it will be selected
                            # If there is no active command (self.command_active is None) then we check if we clicked
                            # on a object by checking the bounding limits against mouse click position
                            if mod_key == self.defaults["global_mselect_key"]:
                                self.select_objects(key='multisel')
                            else:
                                # If there is no active command (self.command_active is None) then we check if
                                # we clicked on a object by checking the bounding limits against mouse click position
                                self.select_objects()

                            self.delete_hover_shape()
                    except Exception as e:
                        log.warning("FlatCAMApp.on_mouse_click_release_over_plot() select click --> Error: %s" % str(e))
                        return

    def selection_area_handler(self, start_pos, end_pos, sel_type):
        """
        :param start_pos: mouse position when the selection LMB click was done
        :param end_pos: mouse position when the left mouse button is released
        :param sel_type: if True it's a left to right selection (enclosure), if False it's a 'touch' selection
        :return:
        """
        poly_selection = Polygon([start_pos, (end_pos[0], start_pos[1]), end_pos, (start_pos[0], end_pos[1])])

        # delete previous selection shape
        self.delete_selection_shape()

        # make all objects inactive
        self.collection.set_all_inactive()

        for obj in self.collection.get_list():
            try:
                # select the object(s) only if it is enabled (plotted)
                if obj.options['plot']:
                    poly_obj = Polygon([(obj.options['xmin'], obj.options['ymin']),
                                        (obj.options['xmax'], obj.options['ymin']),
                                        (obj.options['xmax'], obj.options['ymax']),
                                        (obj.options['xmin'], obj.options['ymax'])])
                    if sel_type is True:
                        if poly_obj.within(poly_selection):
                            # create the selection box around the selected object
                            if self.defaults['global_selection_shape'] is True:
                                self.draw_selection_shape(obj)
                            self.collection.set_active(obj.options['name'])
                    else:
                        if poly_selection.intersects(poly_obj):
                            # create the selection box around the selected object
                            if self.defaults['global_selection_shape'] is True:
                                self.draw_selection_shape(obj)
                            self.collection.set_active(obj.options['name'])
                    obj.selection_shape_drawn = True
            except Exception as e:
                # the Exception here will happen if we try to select on screen and we have an newly (and empty)
                # just created Geometry or Excellon object that do not have the xmin, xmax, ymin, ymax options.
                # In this case poly_obj creation (see above) will fail
                log.debug("App.selection_area_handler() --> %s" % str(e))

    def select_objects(self, key=None):
        """
        Will select objects clicked on canvas

        :param key: for future use in cumulative selection
        :return:
        """

        # list where we store the overlapped objects under our mouse left click position
        if key is None:
            self.objects_under_the_click_list = []

        # Populate the list with the overlapped objects on the click position
        curr_x, curr_y = self.pos

        for obj in self.all_objects_list:
            # ScriptObject and DocumentObject objects can't be selected
            if isinstance(obj, ScriptObject) or isinstance(obj, DocumentObject):
                continue

            if key == 'multisel' and obj.options['name'] in self.objects_under_the_click_list:
                continue

            if (curr_x >= obj.options['xmin']) and (curr_x <= obj.options['xmax']) and \
                    (curr_y >= obj.options['ymin']) and (curr_y <= obj.options['ymax']):
                if obj.options['name'] not in self.objects_under_the_click_list:
                    if obj.options['plot']:
                        # add objects to the objects_under_the_click list only if the object is plotted
                        # (active and not disabled)
                        self.objects_under_the_click_list.append(obj.options['name'])

        try:
            if self.objects_under_the_click_list:
                curr_sel_obj = self.collection.get_active()
                # case when there is only an object under the click and we toggle it
                if len(self.objects_under_the_click_list) == 1:
                    if curr_sel_obj is None:
                        self.collection.set_active(self.objects_under_the_click_list[0])
                        curr_sel_obj = self.collection.get_active()

                        # create the selection box around the selected object
                        if self.defaults['global_selection_shape'] is True:
                            self.draw_selection_shape(curr_sel_obj)
                            curr_sel_obj.selection_shape_drawn = True

                    elif curr_sel_obj.options['name'] not in self.objects_under_the_click_list:
                        self.on_objects_selection(False)
                        self.delete_selection_shape()
                        curr_sel_obj.selection_shape_drawn = False

                        self.collection.set_active(self.objects_under_the_click_list[0])
                        curr_sel_obj = self.collection.get_active()
                        # create the selection box around the selected object
                        if self.defaults['global_selection_shape'] is True:
                            self.draw_selection_shape(curr_sel_obj)
                            curr_sel_obj.selection_shape_drawn = True

                        self.selected_message(curr_sel_obj=curr_sel_obj)

                    elif curr_sel_obj.selection_shape_drawn is False:
                        if self.defaults['global_selection_shape'] is True:
                            self.draw_selection_shape(curr_sel_obj)
                            curr_sel_obj.selection_shape_drawn = True
                    else:
                        self.on_objects_selection(False)
                        self.delete_selection_shape()

                        if self.call_source != 'app':
                            self.call_source = 'app'

                    self.selected_message(curr_sel_obj=curr_sel_obj)

                else:
                    # If there is no selected object
                    # make active the first element of the overlapped objects list
                    if self.collection.get_active() is None:
                        self.collection.set_active(self.objects_under_the_click_list[0])
                        self.collection.get_by_name(self.objects_under_the_click_list[0]).selection_shape_drawn = True

                    name_sel_obj = self.collection.get_active().options['name']
                    # In case that there is a selected object but it is not in the overlapped object list
                    # make that object inactive and activate the first element in the overlapped object list
                    if name_sel_obj not in self.objects_under_the_click_list:
                        self.collection.set_inactive(name_sel_obj)
                        name_sel_obj = self.objects_under_the_click_list[0]
                        self.collection.set_active(name_sel_obj)
                    else:
                        sel_idx = self.objects_under_the_click_list.index(name_sel_obj)
                        self.collection.set_all_inactive()
                        self.collection.set_active(
                            self.objects_under_the_click_list[(sel_idx + 1) % len(self.objects_under_the_click_list)])

                    curr_sel_obj = self.collection.get_active()
                    # delete the possible selection box around a possible selected object
                    self.delete_selection_shape()
                    curr_sel_obj.selection_shape_drawn = False

                    # create the selection box around the selected object
                    if self.defaults['global_selection_shape'] is True:
                        self.draw_selection_shape(curr_sel_obj)
                        curr_sel_obj.selection_shape_drawn = True

                    self.selected_message(curr_sel_obj=curr_sel_obj)

            else:
                # deselect everything
                self.on_objects_selection(False)
                # delete the possible selection box around a possible selected object
                self.delete_selection_shape()

                for o in self.collection.get_list():
                    o.selection_shape_drawn = False

                # and as a convenience move the focus to the Project tab because Selected tab is now empty but
                # only when working on App
                if self.call_source == 'app':
                    if self.click_noproject is False:
                        # if the Tool Tab is in focus don't change focus to Project Tab
                        if not self.ui.notebook.currentWidget() is self.ui.tool_tab:
                            self.ui.notebook.setCurrentWidget(self.ui.project_tab)
                    else:
                        # restore auto open the Project Tab
                        self.click_noproject = False

                    # delete any text in the status bar, implicitly the last object name that was selected
                    # self.inform.emit("")
                else:
                    self.call_source = 'app'
        except Exception as e:
            log.error("[ERROR] Something went bad in App.select_objects(). %s" % str(e))

    def selected_message(self, curr_sel_obj):
        if curr_sel_obj:
            if curr_sel_obj.kind == 'gerber':
                self.inform.emit('[selected]<span style="color:{color};">{name}</span> {tx}'.format(
                    color='green',
                    name=str(curr_sel_obj.options['name']),
                    tx=_("selected"))
                )
            elif curr_sel_obj.kind == 'excellon':
                self.inform.emit('[selected]<span style="color:{color};">{name}</span> {tx}'.format(
                    color='brown',
                    name=str(curr_sel_obj.options['name']),
                    tx=_("selected"))
                )
            elif curr_sel_obj.kind == 'cncjob':
                self.inform.emit('[selected]<span style="color:{color};">{name}</span> {tx}'.format(
                    color='blue',
                    name=str(curr_sel_obj.options['name']),
                    tx=_("selected"))
                )
            elif curr_sel_obj.kind == 'geometry':
                self.inform.emit('[selected]<span style="color:{color};">{name}</span> {tx}'.format(
                    color='red',
                    name=str(curr_sel_obj.options['name']),
                    tx=_("selected"))
                )

    def delete_hover_shape(self):
        self.hover_shapes.clear()
        self.hover_shapes.redraw()

    def draw_hover_shape(self, sel_obj, color=None):
        """

        :param sel_obj: The object for which the hover shape must be drawn
        :param color:   The color of the hover shape
        :return:        None
        """

        pt1 = (float(sel_obj.options['xmin']), float(sel_obj.options['ymin']))
        pt2 = (float(sel_obj.options['xmax']), float(sel_obj.options['ymin']))
        pt3 = (float(sel_obj.options['xmax']), float(sel_obj.options['ymax']))
        pt4 = (float(sel_obj.options['xmin']), float(sel_obj.options['ymax']))

        hover_rect = Polygon([pt1, pt2, pt3, pt4])
        if self.defaults['units'].upper() == 'MM':
            hover_rect = hover_rect.buffer(-0.1)
            hover_rect = hover_rect.buffer(0.2)

        else:
            hover_rect = hover_rect.buffer(-0.00393)
            hover_rect = hover_rect.buffer(0.00787)

        # if color:
        #     face = Color(color)
        #     face.alpha = 0.2
        #     outline = Color(color, alpha=0.8)
        # else:
        #     face = Color(self.defaults['global_sel_fill'])
        #     face.alpha = 0.2
        #     outline = self.defaults['global_sel_line']

        if color:
            face = color[:-2] + str(hex(int(0.2 * 255)))[2:]
            outline = color[:-2] + str(hex(int(0.8 * 255)))[2:]
        else:
            face = self.defaults['global_sel_fill'][:-2] + str(hex(int(0.2 * 255)))[2:]
            outline = self.defaults['global_sel_line']

        self.hover_shapes.add(hover_rect, color=outline, face_color=face, update=True, layer=0, tolerance=None)

        if self.is_legacy is True:
            self.hover_shapes.redraw()

    def delete_selection_shape(self):
        self.move_tool.sel_shapes.clear()
        self.move_tool.sel_shapes.redraw()

    def draw_selection_shape(self, sel_obj, color=None):
        """
        Will draw a selection shape around the selected object.

        :param sel_obj: The object for which the selection shape must be drawn
        :param color:   The color for the selection shape.
        :return:        None
        """

        if sel_obj is None:
            return

        pt1 = (float(sel_obj.options['xmin']), float(sel_obj.options['ymin']))
        pt2 = (float(sel_obj.options['xmax']), float(sel_obj.options['ymin']))
        pt3 = (float(sel_obj.options['xmax']), float(sel_obj.options['ymax']))
        pt4 = (float(sel_obj.options['xmin']), float(sel_obj.options['ymax']))

        sel_rect = Polygon([pt1, pt2, pt3, pt4])

        if self.defaults['units'].upper() == 'MM':
            sel_rect = sel_rect.buffer(-0.1)
            sel_rect = sel_rect.buffer(0.2)
        else:
            sel_rect = sel_rect.buffer(-0.00393)
            sel_rect = sel_rect.buffer(0.00787)

        if color:
            face = color[:-2] + str(hex(int(0.2 * 255)))[2:]
            outline = color[:-2] + str(hex(int(0.8 * 255)))[2:]
        else:
            if self.is_legacy is False:
                face = self.defaults['global_sel_fill'][:-2] + str(hex(int(0.2 * 255)))[2:]
                outline = self.defaults['global_sel_line'][:-2] + str(hex(int(0.8 * 255)))[2:]
            else:
                face = self.defaults['global_sel_fill'][:-2] + str(hex(int(0.4 * 255)))[2:]
                outline = self.defaults['global_sel_line'][:-2] + str(hex(int(1.0 * 255)))[2:]

        self.sel_objects_list.append(self.move_tool.sel_shapes.add(sel_rect,
                                                                   color=outline,
                                                                   face_color=face,
                                                                   update=True,
                                                                   layer=0,
                                                                   tolerance=None))
        if self.is_legacy is True:
            self.move_tool.sel_shapes.redraw()

    def draw_moving_selection_shape(self, old_coords, coords, **kwargs):
        """
        Will draw a selection shape when dragging mouse on canvas.

        :param old_coords:  Old coordinates
        :param coords:      New coordinates
        :param kwargs:      Keyword arguments
        :return:
        """

        if 'color' in kwargs:
            color = kwargs['color']
        else:
            color = self.defaults['global_sel_line']

        if 'face_color' in kwargs:
            face_color = kwargs['face_color']
        else:
            face_color = self.defaults['global_sel_fill']

        if 'face_alpha' in kwargs:
            face_alpha = kwargs['face_alpha']
        else:
            face_alpha = 0.3

        x0, y0 = old_coords
        x1, y1 = coords

        pt1 = (x0, y0)
        pt2 = (x1, y0)
        pt3 = (x1, y1)
        pt4 = (x0, y1)
        sel_rect = Polygon([pt1, pt2, pt3, pt4])

        # color_t = Color(face_color)
        # color_t.alpha = face_alpha

        color_t = face_color[:-2] + str(hex(int(face_alpha * 255)))[2:]

        self.move_tool.sel_shapes.add(sel_rect, color=color, face_color=color_t, update=True,
                                      layer=0, tolerance=None)
        if self.is_legacy is True:
            self.move_tool.sel_shapes.redraw()

    def on_file_new_click(self):
        """
        Callback for menu item File -> New.
        Executed on clicking the Menu -> File -> New Project

        :return:
        """

        if self.collection.get_list() and self.should_we_save:
            msgbox = QtWidgets.QMessageBox()
            # msgbox.setText("<B>Save changes ...</B>")
            msgbox.setText(_("There are files/objects opened in FlatCAM.\n"
                             "Creating a New project will delete them.\n"
                             "Do you want to Save the project?"))
            msgbox.setWindowTitle(_("Save changes"))
            msgbox.setWindowIcon(QtGui.QIcon(self.resource_location + '/save_as.png'))
            bt_yes = msgbox.addButton(_('Yes'), QtWidgets.QMessageBox.YesRole)
            bt_no = msgbox.addButton(_('No'), QtWidgets.QMessageBox.NoRole)
            bt_cancel = msgbox.addButton(_('Cancel'), QtWidgets.QMessageBox.RejectRole)

            msgbox.setDefaultButton(bt_yes)
            msgbox.exec_()
            response = msgbox.clickedButton()

            if response == bt_yes:
                self.on_file_saveprojectas()
            elif response == bt_cancel:
                return
            elif response == bt_no:
                self.on_file_new()
        else:
            self.on_file_new()
        self.inform.emit('[success] %s...' % _("New Project created"))

    def on_file_new(self, cli=None):
        """
        Returns the application to its startup state. This method is thread-safe.

        :param cli:     Boolean. If True this method was run from command line
        :return:        None
        """

        self.defaults.report_usage("on_file_new")

        # Remove everything from memory
        App.log.debug("on_file_new()")

        # close any editor that might be open
        if self.call_source != 'app':
            self.editor2object(cleanup=True)
            # ## EDITOR section
            self.geo_editor = FlatCAMGeoEditor(self)
            self.exc_editor = FlatCAMExcEditor(self)
            self.grb_editor = FlatCAMGrbEditor(self)

        # Clear pool
        self.clear_pool()

        for obj in self.collection.get_list():
            # delete shapes left drawn from mark shape_collections, if any
            if isinstance(obj, GerberObject):
                try:
                    for el in obj.mark_shapes:
                        obj.mark_shapes[el].clear(update=True)
                        obj.mark_shapes[el].enabled = False
                        del el
                except AttributeError:
                    pass

            # also delete annotation shapes, if any
            elif isinstance(obj, CNCJobObject):
                try:
                    obj.text_col.enabled = False
                    del obj.text_col
                    obj.annotation.clear(update=True)
                    del obj.annotation
                except AttributeError:
                    pass

        # delete the exclusion areas
        self.exc_areas.clear_shapes()

        # tcl needs to be reinitialized, otherwise old shell variables etc  remains
        self.shell.init_tcl()

        # delete any selection shape on canvas
        self.delete_selection_shape()

        # delete all FlatCAM objects
        self.collection.delete_all()

        # add in Selected tab an initial text that describe the flow of work in FlatCAm
        self.setup_component_editor()

        # Clear project filename
        self.project_filename = None

        # Load the application defaults
        self.defaults.load(filename=os.path.join(self.data_path, 'current_defaults.FlatConfig'))

        # Re-fresh project options
        self.on_options_app2project()

        # Init FlatCAMTools
        self.init_tools()

        # Try to close all tabs in the PlotArea but only if the GUI is active (CLI is None)
        if cli is None:
            # we need to go in reverse because once we remove a tab then the index changes
            # meaning that removing the first tab (idx = 0) then the tab at former idx = 1 will assume idx = 0
            # and so on. Therefore the deletion should be done in reverse
            wdg_count = self.ui.plot_tab_area.tabBar.count() - 1
            for index in range(wdg_count, -1, -1):
                try:
                    self.ui.plot_tab_area.closeTab(index)
                except Exception as e:
                    log.debug("App.on_file_new() --> %s" % str(e))

            # # And then add again the Plot Area
            self.ui.plot_tab_area.insertTab(0, self.ui.plot_tab, "Plot Area")
            self.ui.plot_tab_area.protectTab(0)

        # take the focus of the Notebook on Project Tab.
        self.ui.notebook.setCurrentWidget(self.ui.project_tab)

        self.set_ui_title(name=_("New Project - Not saved"))

    def obj_properties(self):
        """
        Will launch the object Properties Tool

        :return:
        """

        self.defaults.report_usage("obj_properties()")
        self.properties_tool.run(toggle=False)

    def on_project_context_save(self):
        """
        Wrapper, will save the object function of it's type

        :return:
        """

        obj = self.collection.get_active()
        if type(obj) == GeometryObject:
            self.on_file_exportdxf()
        elif type(obj) == ExcellonObject:
            self.on_file_saveexcellon()
        elif type(obj) == CNCJobObject:
            obj.on_exportgcode_button_click()
        elif type(obj) == GerberObject:
            self.on_file_savegerber()
        elif type(obj) == ScriptObject:
            self.on_file_savescript()
        elif type(obj) == DocumentObject:
            self.on_file_savedocument()

    def obj_move(self):
        """
        Callback for the Move menu entry in various Context Menu's.

        :return:
        """

        self.defaults.report_usage("obj_move()")
        self.move_tool.run(toggle=False)

    def on_fileopengerber(self, signal, name=None):
        """
        File menu callback for opening a Gerber.

        :param signal: required because clicking the entry will generate a checked signal which needs a container
        :param name:
        :return: None
        """

        self.defaults.report_usage("on_fileopengerber")
        App.log.debug("on_fileopengerber()")

        _filter_ = "Gerber Files (*.gbr *.ger *.gtl *.gbl *.gts *.gbs *.gtp *.gbp *.gto *.gbo *.gm1 *.gml *.gm3 *" \
                   ".gko *.cmp *.sol *.stc *.sts *.plc *.pls *.crc *.crs *.tsm *.bsm *.ly2 *.ly15 *.dim *.mil *.grb" \
                   "*.top *.bot *.smt *.smb *.sst *.ssb *.spt *.spb *.pho *.gdo *.art *.gbd);;" \
                   "Protel Files (*.gtl *.gbl *.gts *.gbs *.gto *.gbo *.gtp *.gbp *.gml *.gm1 *.gm3 *.gko);;" \
                   "Eagle Files (*.cmp *.sol *.stc *.sts *.plc *.pls *.crc *.crs *.tsm *.bsm *.ly2 *.ly15 *.dim " \
                   "*.mil);;" \
                   "OrCAD Files (*.top *.bot *.smt *.smb *.sst *.ssb *.spt *.spb);;" \
                   "Allegro Files (*.art);;" \
                   "Mentor Files (*.pho *.gdo);;" \
                   "All Files (*.*)"

        if name is None:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open Gerber"),
                                                                       directory=self.get_last_folder(),
                                                                       filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open Gerber"), filter=_filter_)

            filenames = [str(filename) for filename in filenames]
        else:
            filenames = [name]
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening Gerber file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_gerber, 'params': [filename]})

    def on_fileopenexcellon(self, signal, name=None):
        """
        File menu callback for opening an Excellon file.

        :param signal: required because clicking the entry will generate a checked signal which needs a container
        :param name:
        :return: None
        """

        self.defaults.report_usage("on_fileopenexcellon")
        App.log.debug("on_fileopenexcellon()")

        _filter_ = "Excellon Files (*.drl *.txt *.xln *.drd *.tap *.exc *.ncd);;" \
                   "All Files (*.*)"
        if name is None:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open Excellon"),
                                                                       directory=self.get_last_folder(),
                                                                       filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open Excellon"), filter=_filter_)
            filenames = [str(filename) for filename in filenames]
        else:
            filenames = [str(name)]
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening Excellon file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL]%s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_excellon, 'params': [filename]})

    def on_fileopengcode(self, signal, name=None):
        """

        File menu call back for opening gcode.

        :param signal: required because clicking the entry will generate a checked signal which needs a container
        :param name:
        :return:
        """

        self.defaults.report_usage("on_fileopengcode")
        App.log.debug("on_fileopengcode()")

        # https://bobcadsupport.com/helpdesk/index.php?/Knowledgebase/Article/View/13/5/known-g-code-file-extensions
        _filter_ = "G-Code Files (*.txt *.nc *.ncc *.tap *.gcode *.cnc *.ecs *.fnc *.dnc *.ncg *.gc *.fan *.fgc" \
                   " *.din *.xpi *.hnc *.h *.i *.ncp *.min *.gcd *.rol *.mpr *.ply *.out *.eia *.sbp *.mpf);;" \
                   "All Files (*.*)"

        if name is None:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open G-Code"),
                                                                       directory=self.get_last_folder(),
                                                                       filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open G-Code"), filter=_filter_)

            filenames = [str(filename) for filename in filenames]
        else:
            filenames = [name]
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening G-Code file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_gcode, 'params': [filename, None, True]})

    def on_file_openproject(self, signal):
        """
        File menu callback for opening a project.

        :param signal: required because clicking the entry will generate a checked signal which needs a container
        :return: None
        """

        self.defaults.report_usage("on_file_openproject")
        App.log.debug("on_file_openproject()")
        _filter_ = "FlatCAM Project (*.FlatPrj);;All Files (*.*)"
        try:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Open Project"),
                                                                 directory=self.get_last_folder(), filter=_filter_)
        except TypeError:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Open Project"), filter=_filter_)

        # The Qt methods above will return a QString which can cause problems later.
        # So far json.dump() will fail to serialize it.
        # TODO: Improve the serialization methods and remove this fix.
        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            # self.worker_task.emit({'fcn': self.open_project,
            #                        'params': [filename]})
            # The above was failing because open_project() is not
            # thread safe. The new_project()
            self.open_project(filename)

    def on_fileopenhpgl2(self, signal, name=None):
        """
        File menu callback for opening a HPGL2.

        :param signal:  required because clicking the entry will generate a checked signal which needs a container
        :param name:
        :return:        None
        """

        self.defaults.report_usage("on_fileopenhpgl2")
        App.log.debug("on_fileopenhpgl2()")

        _filter_ = "HPGL2 Files (*.plt);;" \
                   "All Files (*.*)"

        if name is None:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open HPGL2"),
                                                                       directory=self.get_last_folder(),
                                                                       filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open HPGL2"), filter=_filter_)

            filenames = [str(filename) for filename in filenames]
        else:
            filenames = [name]
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening HPGL2 file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_hpgl2, 'params': [filename]})

    def on_file_openconfig(self, signal):
        """
        File menu callback for opening a config file.

        :param signal:  required because clicking the entry will generate a checked signal which needs a container
        :return:        None
        """

        self.defaults.report_usage("on_file_openconfig")
        App.log.debug("on_file_openconfig()")
        _filter_ = "FlatCAM Config (*.FlatConfig);;FlatCAM Config (*.json);;All Files (*.*)"
        try:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Open Configuration File"),
                                                                 directory=self.data_path, filter=_filter_)
        except TypeError:
            filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Open Configuration File"),
                                                                 filter=_filter_)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            self.open_config_file(filename)

    def on_file_exportsvg(self):
        """
        Callback for menu item File->Export SVG.

        :return: None
        """
        self.defaults.report_usage("on_file_exportsvg")
        App.log.debug("on_file_exportsvg()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            msg = _("Please Select a Geometry object to export")
            msgbox = QtWidgets.QMessageBox()
            msgbox.setInformativeText(msg)
            bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
            msgbox.setDefaultButton(bt_ok)
            msgbox.exec_()
            return

        # Check for more compatible types and add as required
        if (not isinstance(obj, GeometryObject)
                and not isinstance(obj, GerberObject)
                and not isinstance(obj, CNCJobObject)
                and not isinstance(obj, ExcellonObject)):
            msg = '[ERROR_NOTCL] %s' % \
                  _("Only Geometry, Gerber and CNCJob objects can be used.")
            msgbox = QtWidgets.QMessageBox()
            msgbox.setInformativeText(msg)
            bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
            msgbox.setDefaultButton(bt_ok)
            msgbox.exec_()
            return

        name = obj.options["name"]

        _filter = "SVG File (*.svg);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export SVG"),
                directory=self.get_last_save_folder() + '/' + str(name) + '_svg',
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export SVG"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL]%s' % _("Cancelled."))
            return
        else:
            self.export_svg(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("SVG", filename)
            self.file_saved.emit("SVG", filename)

    def on_file_exportpng(self):
        self.defaults.report_usage("on_file_exportpng")
        App.log.debug("on_file_exportpng()")

        self.date = str(datetime.today()).rpartition('.')[0]
        self.date = ''.join(c for c in self.date if c not in ':-')
        self.date = self.date.replace(' ', '_')

        if self.is_legacy is False:
            image = _screenshot()
            data = np.asarray(image)
            if not data.ndim == 3 and data.shape[-1] in (3, 4):
                self.inform.emit('[[WARNING_NOTCL]] %s' % _('Data must be a 3D array with last dimension 3 or 4'))
                return

        filter_ = "PNG File (*.png);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export PNG Image"),
                directory=self.get_last_save_folder() + '/png_' + self.date,
                filter=filter_)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export PNG Image"), filter=filter_)

        filename = str(filename)

        if filename == "":
            self.inform.emit(_("Cancelled."))
            return
        else:
            if self.is_legacy is False:
                write_png(filename, data)
            else:
                self.plotcanvas.figure.savefig(filename)

            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("png", filename)
            self.file_saved.emit("png", filename)

    def on_file_savegerber(self):
        """
        Callback for menu item in Project context menu.

        :return: None
        """
        self.defaults.report_usage("on_file_savegerber")
        App.log.debug("on_file_savegerber()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, GerberObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Gerber objects can be saved as Gerber files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter = "Gerber File (*.GBR);;Gerber File (*.GRB);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption="Save Gerber source file",
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Gerber source file"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            self.save_source_file(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Gerber", filename)
            self.file_saved.emit("Gerber", filename)

    def on_file_savescript(self):
        """
        Callback for menu item in Project context menu.

        :return: None
        """
        self.defaults.report_usage("on_file_savescript")
        App.log.debug("on_file_savescript()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, ScriptObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Script objects can be saved as TCL Script files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter = "FlatCAM Scripts (*.FlatScript);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption="Save Script source file",
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Script source file"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            self.save_source_file(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Script", filename)
            self.file_saved.emit("Script", filename)

    def on_file_savedocument(self):
        """
        Callback for menu item in Project context menu.

        :return: None
        """
        self.defaults.report_usage("on_file_savedocument")
        App.log.debug("on_file_savedocument()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, ScriptObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Document objects can be saved as Document files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter = "FlatCAM Documents (*.FlatDoc);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption="Save Document source file",
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Document source file"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            self.save_source_file(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Document", filename)
            self.file_saved.emit("Document", filename)

    def on_file_saveexcellon(self):
        """
        Callback for menu item in project context menu.

        :return: None
        """
        self.defaults.report_usage("on_file_saveexcellon")
        App.log.debug("on_file_saveexcellon()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, ExcellonObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Excellon objects can be saved as Excellon files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter = "Excellon File (*.DRL);;Excellon File (*.TXT);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Save Excellon source file"),
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Excellon source file"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            self.save_source_file(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Excellon", filename)
            self.file_saved.emit("Excellon", filename)

    def on_file_exportexcellon(self):
        """
        Callback for menu item File->Export->Excellon.

        :return: None
        """
        self.defaults.report_usage("on_file_exportexcellon")
        App.log.debug("on_file_exportexcellon()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, ExcellonObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Excellon objects can be saved as Excellon files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter = self.defaults["excellon_save_filters"]
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export Excellon"),
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export Excellon"), filter=_filter)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            used_extension = filename.rpartition('.')[2]
            obj.update_filters(last_ext=used_extension, filter_string='excellon_save_filters')

            self.export_excellon(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Excellon", filename)
            self.file_saved.emit("Excellon", filename)

    def on_file_exportgerber(self):
        """
        Callback for menu item File->Export->Gerber.

        :return: None
        """
        self.defaults.report_usage("on_file_exportgerber")
        App.log.debug("on_file_exportgerber()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, GerberObject):
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed. Only Gerber objects can be saved as Gerber files..."))
            return

        name = self.collection.get_active().options["name"]

        _filter_ = self.defaults['gerber_save_filters']
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export Gerber"),
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter_)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export Gerber"), filter=_filter_)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            used_extension = filename.rpartition('.')[2]
            obj.update_filters(last_ext=used_extension, filter_string='gerber_save_filters')

            self.export_gerber(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("Gerber", filename)
            self.file_saved.emit("Gerber", filename)

    def on_file_exportdxf(self):
        """
                Callback for menu item File->Export DXF.

                :return: None
                """
        self.defaults.report_usage("on_file_exportdxf")
        App.log.debug("on_file_exportdxf()")

        obj = self.collection.get_active()
        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("No object selected."))
            msg = _("Please Select a Geometry object to export")
            msgbox = QtWidgets.QMessageBox()
            msgbox.setInformativeText(msg)
            bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
            msgbox.setDefaultButton(bt_ok)
            msgbox.exec_()
            return

        # Check for more compatible types and add as required
        if not isinstance(obj, GeometryObject):
            msg = '[ERROR_NOTCL] %s' % _("Only Geometry objects can be used.")
            msgbox = QtWidgets.QMessageBox()
            msgbox.setInformativeText(msg)
            bt_ok = msgbox.addButton(_('Ok'), QtWidgets.QMessageBox.AcceptRole)
            msgbox.setDefaultButton(bt_ok)
            msgbox.exec_()

            return

        name = self.collection.get_active().options["name"]

        _filter_ = "DXF File .dxf (*.DXF);;All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Export DXF"),
                directory=self.get_last_save_folder() + '/' + name,
                filter=_filter_)
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Export DXF"), filter=_filter_)

        filename = str(filename)

        if filename == "":
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return
        else:
            self.export_dxf(name, filename)
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("DXF", filename)
            self.file_saved.emit("DXF", filename)

    def on_file_importsvg(self, type_of_obj):
        """
        Callback for menu item File->Import SVG.
        :param type_of_obj: to import the SVG as Geometry or as Gerber
        :type type_of_obj: str
        :return: None
        """
        self.defaults.report_usage("on_file_importsvg")
        App.log.debug("on_file_importsvg()")

        _filter_ = "SVG File .svg (*.svg);;All Files (*.*)"
        try:
            filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Import SVG"),
                                                                   directory=self.get_last_folder(), filter=_filter_)
        except TypeError:
            filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Import SVG"),
                                                                   filter=_filter_)

        if type_of_obj != "geometry" and type_of_obj != "gerber":
            type_of_obj = "geometry"

        filenames = [str(filename) for filename in filenames]

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.import_svg,
                                           'params': [filename, type_of_obj]})

    def on_file_importdxf(self, type_of_obj):
        """
        Callback for menu item File->Import DXF.
        :param type_of_obj: to import the DXF as Geometry or as Gerber
        :type type_of_obj: str
        :return: None
        """
        self.defaults.report_usage("on_file_importdxf")
        App.log.debug("on_file_importdxf()")

        _filter_ = "DXF File .dxf (*.DXF);;All Files (*.*)"
        try:
            filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Import DXF"),
                                                                   directory=self.get_last_folder(),
                                                                   filter=_filter_)
        except TypeError:
            filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Import DXF"),
                                                                   filter=_filter_)

        if type_of_obj != "geometry" and type_of_obj != "gerber":
            type_of_obj = "geometry"

        filenames = [str(filename) for filename in filenames]

        if len(filenames) == 0:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.import_dxf,
                                           'params': [filename, type_of_obj]})

    # ###############################################################################################################
    # ### The following section has the functions that are displayed and call the Editor tab CNCJob Tab #############
    # ###############################################################################################################
    def init_code_editor(self, name):

        self.text_editor_tab = TextEditor(app=self, plain_text=True)

        # add the tab if it was closed
        self.ui.plot_tab_area.addTab(self.text_editor_tab, '%s' % name)
        self.text_editor_tab.setObjectName('text_editor_tab')

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        # first clear previous text in text editor (if any)
        self.text_editor_tab.code_editor.clear()
        self.text_editor_tab.code_editor.setReadOnly(False)
        self.toggle_codeeditor = True
        self.text_editor_tab.code_editor.completer_enable = False
        self.text_editor_tab.buttonRun.hide()

        # make sure to keep a reference to the code editor
        self.reference_code_editor = self.text_editor_tab.code_editor

        # Switch plot_area to CNCJob tab
        self.ui.plot_tab_area.setCurrentWidget(self.text_editor_tab)

    def on_view_source(self):
        """
        Called when the user wants to see the source file of the selected object
        :return:
        """

        self.inform.emit('%s' % _("Viewing the source code of the selected object."))
        self.proc_container.view.set_busy(_("Loading..."))

        try:
            obj = self.collection.get_active()
        except Exception as e:
            log.debug("App.on_view_source() --> %s" % str(e))
            self.inform.emit('[WARNING_NOTCL] %s' % _("Select an Gerber or Excellon file to view it's source file."))
            return 'fail'

        if obj is None:
            self.inform.emit('[WARNING_NOTCL] %s' % _("Select an Gerber or Excellon file to view it's source file."))
            return 'fail'

        flt = "All Files (*.*)"
        if obj.kind == 'gerber':
            flt = "Gerber Files .gbr (*.GBR);;PDF Files .pdf (*.PDF);;All Files (*.*)"
        elif obj.kind == 'excellon':
            flt = "Excellon Files .drl (*.DRL);;PDF Files .pdf (*.PDF);;All Files (*.*)"
        elif obj.kind == 'cncjob':
            flt = "GCode Files .nc (*.NC);;PDF Files .pdf (*.PDF);;All Files (*.*)"

        self.source_editor_tab = TextEditor(app=self, plain_text=True)

        # add the tab if it was closed
        self.ui.plot_tab_area.addTab(self.source_editor_tab, '%s' % _("Source Editor"))
        self.source_editor_tab.setObjectName('source_editor_tab')

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        # first clear previous text in text editor (if any)
        self.source_editor_tab.code_editor.clear()
        self.source_editor_tab.code_editor.setReadOnly(False)

        self.source_editor_tab.code_editor.completer_enable = False
        self.source_editor_tab.buttonRun.hide()

        # Switch plot_area to CNCJob tab
        self.ui.plot_tab_area.setCurrentWidget(self.source_editor_tab)

        try:
            self.source_editor_tab.buttonOpen.clicked.disconnect()
        except TypeError:
            pass
        self.source_editor_tab.buttonOpen.clicked.connect(lambda: self.source_editor_tab.handleOpen(filt=flt))

        try:
            self.source_editor_tab.buttonSave.clicked.disconnect()
        except TypeError:
            pass
        self.source_editor_tab.buttonSave.clicked.connect(lambda: self.source_editor_tab.handleSaveGCode(filt=flt))

        # then append the text from GCode to the text editor
        if obj.kind == 'cncjob':
            try:
                file = obj.export_gcode(
                    preamble=self.defaults["cncjob_prepend"],
                    postamble=self.defaults["cncjob_append"],
                    to_file=True)
                if file == 'fail':
                    return 'fail'
            except AttributeError:
                self.inform.emit('[WARNING_NOTCL] %s' %
                                 _("There is no selected object for which to see it's source file code."))
                return 'fail'
        else:
            try:
                file = StringIO(obj.source_file)
            except (AttributeError, TypeError):
                self.inform.emit('[WARNING_NOTCL] %s' %
                                 _("There is no selected object for which to see it's source file code."))
                return 'fail'

        self.source_editor_tab.t_frame.hide()
        try:
            self.source_editor_tab.code_editor.setPlainText(file.getvalue())
            # for line in file:
            #     QtWidgets.QApplication.processEvents()
            #     proc_line = str(line).strip('\n')
            #     self.source_editor_tab.code_editor.append(proc_line)
        except Exception as e:
            log.debug('App.on_view_source() -->%s' % str(e))
            self.inform.emit('[ERROR] %s: %s' % (_('Failed to load the source code for the selected object'), str(e)))
            return

        self.source_editor_tab.handleTextChanged()
        self.source_editor_tab.t_frame.show()

        self.source_editor_tab.code_editor.moveCursor(QtGui.QTextCursor.Start)
        self.proc_container.view.set_idle()
        # self.ui.show()

    def on_toggle_code_editor(self):
        self.defaults.report_usage("on_toggle_code_editor()")

        if self.toggle_codeeditor is False:
            self.init_code_editor(name=_("Code Editor"))

            self.text_editor_tab.buttonOpen.clicked.disconnect()
            self.text_editor_tab.buttonOpen.clicked.connect(self.text_editor_tab.handleOpen)
            self.text_editor_tab.buttonSave.clicked.disconnect()
            self.text_editor_tab.buttonSave.clicked.connect(self.text_editor_tab.handleSaveGCode)
        else:
            for idx in range(self.ui.plot_tab_area.count()):
                if self.ui.plot_tab_area.widget(idx).objectName() == "text_editor_tab":
                    self.ui.plot_tab_area.closeTab(idx)
                    break
            self.toggle_codeeditor = False

    def on_code_editor_close(self):
        self.toggle_codeeditor = False

    def goto_text_line(self):
        """
        Will scroll a text to the specified text line.

        :return: None
        """
        dia_box = Dialog_box(title=_("Go to Line ..."),
                             label=_("Line:"),
                             icon=QtGui.QIcon(self.resource_location + '/jump_to16.png'),
                             initial_text='')
        try:
            line = int(dia_box.location) - 1
        except (ValueError, TypeError):
            line = 0

        if dia_box.ok:
            # make sure to move first the cursor at the end so after finding the line the line will be positioned
            # at the top of the window
            self.ui.plot_tab_area.currentWidget().code_editor.moveCursor(QTextCursor.End)
            # get the document() of the TextEditor
            doc = self.ui.plot_tab_area.currentWidget().code_editor.document()
            # create a Text Cursor based on the searched line
            cursor = QTextCursor(doc.findBlockByLineNumber(line))
            # set cursor of the code editor with the cursor at the searcehd line
            self.ui.plot_tab_area.currentWidget().code_editor.setTextCursor(cursor)

    def on_filenewscript(self, silent=False):
        """
        Will create a new script file and open it in the Code Editor

        :param silent:  if True will not display status messages
        :param name:    if specified will be the name of the new script
        :param text:    pass a source file to the newly created script to be loaded in it
        :return:        None
        """
        if silent is False:
            self.inform.emit('[success] %s' % _("New TCL script file created in Code Editor."))

        # delete the absolute and relative position and messages in the infobar
        self.ui.position_label.setText("")
        self.ui.rel_position_label.setText("")

        self.new_script_object()

        # script_text = script_obj.source_file
        #
        # self.proc_container.view.set_busy(_("Loading..."))
        # script_obj.script_editor_tab.t_frame.hide()
        #
        # script_obj.script_editor_tab.t_frame.show()
        # self.proc_container.view.set_idle()

    def on_fileopenscript(self, name=None, silent=False):
        """
        Will open a Tcl script file into the Code Editor

        :param silent:  if True will not display status messages
        :param name:    name of a Tcl script file to open
        :return:        None
        """

        self.defaults.report_usage("on_fileopenscript")
        App.log.debug("on_fileopenscript()")

        _filter_ = "TCL script .FlatScript (*.FlatScript);;TCL script .tcl (*.TCL);;TCL script .txt (*.TXT);;" \
                   "All Files (*.*)"

        if name:
            filenames = [name]
        else:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(
                    caption=_("Open TCL script"), directory=self.get_last_folder(), filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open TCL script"), filter=_filter_)

        if len(filenames) == 0:
            if silent is False:
                self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_script, 'params': [filename]})

    def on_fileopenscript_example(self, name=None, silent=False):
        """
        Will open a Tcl script file into the Code Editor

        :param silent: if True will not display status messages
        :param name: name of a Tcl script file to open
        :return:
        """

        self.defaults.report_usage("on_fileopenscript_example")
        log.debug("on_fileopenscript_example()")

        _filter_ = "TCL script .FlatScript (*.FlatScript);;TCL script .tcl (*.TCL);;TCL script .txt (*.TXT);;" \
                   "All Files (*.*)"

        # test if the app was frozen and choose the path for the configuration file
        if getattr(sys, "frozen", False) is True:
            example_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '\\assets\\examples'
        else:
            example_path = os.path.dirname(os.path.realpath(__file__)) + '\\assets\\examples'

        if name:
            filenames = [name]
        else:
            try:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(
                    caption=_("Open TCL script"), directory=example_path, filter=_filter_)
            except TypeError:
                filenames, _f = QtWidgets.QFileDialog.getOpenFileNames(caption=_("Open TCL script"), filter=_filter_)

        if len(filenames) == 0:
            if silent is False:
                self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            for filename in filenames:
                if filename != '':
                    self.worker_task.emit({'fcn': self.open_script, 'params': [filename]})

    def on_filerunscript(self, name=None, silent=False):
        """
        File menu callback for loading and running a TCL script.

        :param silent: if True will not display status messages
        :param name: name of a Tcl script file to be run by FlatCAM
        :return: None
        """

        self.defaults.report_usage("on_filerunscript")
        App.log.debug("on_file_runscript()")

        if name:
            filename = name
            if self.cmd_line_headless != 1:
                self.splash.showMessage('%s: %ssec\n%s' %
                                        (_("Canvas initialization started.\n"
                                           "Canvas initialization finished in"), '%.2f' % self.used_time,
                                         _("Executing ScriptObject file.")
                                         ),
                                        alignment=Qt.AlignBottom | Qt.AlignLeft,
                                        color=QtGui.QColor("gray"))
        else:
            _filter_ = "TCL script .FlatScript (*.FlatScript);;TCL script .tcl (*.TCL);;TCL script .txt (*.TXT);;" \
                       "All Files (*.*)"
            try:
                filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Run TCL script"),
                                                                     directory=self.get_last_folder(), filter=_filter_)
            except TypeError:
                filename, _f = QtWidgets.QFileDialog.getOpenFileName(caption=_("Run TCL script"), filter=_filter_)

        # The Qt methods above will return a QString which can cause problems later.
        # So far json.dump() will fail to serialize it.
        filename = str(filename)

        if filename == "":
            if silent is False:
                self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
        else:
            if self.cmd_line_headless != 1:
                if self.ui.shell_dock.isHidden():
                    self.ui.shell_dock.show()

            try:
                with open(filename, "r") as tcl_script:
                    cmd_line_shellfile_content = tcl_script.read()
                    if self.cmd_line_headless != 1:
                        self.shell.exec_command(cmd_line_shellfile_content)
                    else:
                        self.shell.exec_command(cmd_line_shellfile_content, no_echo=True)

                if silent is False:
                    self.inform.emit('[success] %s' % _("TCL script file opened in Code Editor and executed."))
            except Exception as e:
                log.debug("App.on_filerunscript() -> %s" % str(e))
                sys.exit(2)

    def on_file_saveproject(self, silent=False):
        """
        Callback for menu item File->Save Project. Saves the project to
        ``self.project_filename`` or calls ``self.on_file_saveprojectas()``
        if set to None. The project is saved by calling ``self.save_project()``.

        :param silent: if True will not display status messages
        :return: None
        """

        self.defaults.report_usage("on_file_saveproject")

        if self.project_filename is None:
            self.on_file_saveprojectas()
        else:
            self.worker_task.emit({'fcn': self.save_project,
                                   'params': [self.project_filename, silent]})
            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("project", self.project_filename)
            self.file_saved.emit("project", self.project_filename)

        self.set_ui_title(name=self.project_filename)

        self.should_we_save = False

    def on_file_saveprojectas(self, make_copy=False, use_thread=True, quit_action=False):
        """
        Callback for menu item File->Save Project As... Opens a file
        chooser and saves the project to the given file via
        ``self.save_project()``.

        :param make_copy if to be create a copy of the project; boolean
        :param use_thread: if to be run in a separate thread; boolean
        :param quit_action: if to be followed by quiting the application; boolean
        :return: None
        """

        self.defaults.report_usage("on_file_saveprojectas")

        self.date = str(datetime.today()).rpartition('.')[0]
        self.date = ''.join(c for c in self.date if c not in ':-')
        self.date = self.date.replace(' ', '_')

        filter_ = "FlatCAM Project .FlatPrj (*.FlatPrj);; All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Save Project As ..."),
                directory='{l_save}/{proj}_{date}'.format(l_save=str(self.get_last_save_folder()), date=self.date,
                                                          proj=_("Project")),
                filter=filter_
            )
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Project As ..."), filter=filter_)

        filename = str(filename)

        if filename == '':
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return

        if use_thread is True:
            self.worker_task.emit({'fcn': self.save_project,
                                   'params': [filename, quit_action]})
        else:
            self.save_project(filename, quit_action)

        # self.save_project(filename)
        if self.defaults["global_open_style"] is False:
            self.file_opened.emit("project", filename)
        self.file_saved.emit("project", filename)

        if not make_copy:
            self.project_filename = filename

        self.set_ui_title(name=self.project_filename)
        self.should_we_save = False

    def on_file_save_objects_pdf(self, use_thread=True):
        self.date = str(datetime.today()).rpartition('.')[0]
        self.date = ''.join(c for c in self.date if c not in ':-')
        self.date = self.date.replace(' ', '_')

        try:
            obj_selection = self.collection.get_selected()
            if len(obj_selection) == 1:
                obj_name = str(obj_selection[0].options['name'])
            else:
                obj_name = _("FlatCAM objects print")
        except AttributeError as err:
            log.debug("App.on_file_save_object_pdf() --> %s" % str(err))
            self.inform.emit('[ERROR_NOTCL] %s' % _("No object selected."))
            return

        if not obj_selection:
            self.inform.emit('[ERROR_NOTCL] %s' % _("No object selected."))
            return

        filter_ = "PDF File .pdf (*.PDF);; All Files (*.*)"
        try:
            filename, _f = FCFileSaveDialog.get_saved_filename(
                caption=_("Save Object as PDF ..."),
                directory='{l_save}/{obj_name}_{date}'.format(l_save=str(self.get_last_save_folder()),
                                                              obj_name=obj_name,
                                                              date=self.date),
                filter=filter_
            )
        except TypeError:
            filename, _f = FCFileSaveDialog.get_saved_filename(caption=_("Save Object as PDF ..."), filter=filter_)

        filename = str(filename)

        if filename == '':
            self.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled."))
            return

        if use_thread is True:
            self.proc_container.new(_("Printing PDF ... Please wait."))
            self.worker_task.emit({'fcn': self.save_pdf, 'params': [filename, obj_selection]})
        else:
            self.save_pdf(filename, obj_selection)

        # self.save_project(filename)
        if self.defaults["global_open_style"] is False:
            self.file_opened.emit("pdf", filename)
        self.file_saved.emit("pdf", filename)

    def save_pdf(self, file_name, obj_selection):

        p_size = self.defaults['global_workspaceT']
        orientation = self.defaults['global_workspace_orientation']
        color = 'black'
        transparency_level = 1.0

        self.pagesize = {}
        self.pagesize.update(
            {
                'Bounds': None,
                'A0': (841 * mm, 1189 * mm),
                'A1': (594 * mm, 841 * mm),
                'A2': (420 * mm, 594 * mm),
                'A3': (297 * mm, 420 * mm),
                'A4': (210 * mm, 297 * mm),
                'A5': (148 * mm, 210 * mm),
                'A6': (105 * mm, 148 * mm),
                'A7': (74 * mm, 105 * mm),
                'A8': (52 * mm, 74 * mm),
                'A9': (37 * mm, 52 * mm),
                'A10': (26 * mm, 37 * mm),

                'B0': (1000 * mm, 1414 * mm),
                'B1': (707 * mm, 1000 * mm),
                'B2': (500 * mm, 707 * mm),
                'B3': (353 * mm, 500 * mm),
                'B4': (250 * mm, 353 * mm),
                'B5': (176 * mm, 250 * mm),
                'B6': (125 * mm, 176 * mm),
                'B7': (88 * mm, 125 * mm),
                'B8': (62 * mm, 88 * mm),
                'B9': (44 * mm, 62 * mm),
                'B10': (31 * mm, 44 * mm),

                'C0': (917 * mm, 1297 * mm),
                'C1': (648 * mm, 917 * mm),
                'C2': (458 * mm, 648 * mm),
                'C3': (324 * mm, 458 * mm),
                'C4': (229 * mm, 324 * mm),
                'C5': (162 * mm, 229 * mm),
                'C6': (114 * mm, 162 * mm),
                'C7': (81 * mm, 114 * mm),
                'C8': (57 * mm, 81 * mm),
                'C9': (40 * mm, 57 * mm),
                'C10': (28 * mm, 40 * mm),

                # American paper sizes
                'LETTER': (8.5 * inch, 11 * inch),
                'LEGAL': (8.5 * inch, 14 * inch),
                'ELEVENSEVENTEEN': (11 * inch, 17 * inch),

                # From https://en.wikipedia.org/wiki/Paper_size
                'JUNIOR_LEGAL': (5 * inch, 8 * inch),
                'HALF_LETTER': (5.5 * inch, 8 * inch),
                'GOV_LETTER': (8 * inch, 10.5 * inch),
                'GOV_LEGAL': (8.5 * inch, 13 * inch),
                'LEDGER': (17 * inch, 11 * inch),
            }
        )

        exported_svg = []
        for obj in obj_selection:
            svg_obj = obj.export_svg(scale_stroke_factor=0.0,
                                     scale_factor_x=None, scale_factor_y=None,
                                     skew_factor_x=None, skew_factor_y=None,
                                     mirror=None)

            if obj.kind.lower() == 'gerber':
                # color = self.defaults["gerber_plot_fill"][:-2]
                color = obj.fill_color[:-2]
            elif obj.kind.lower() == 'excellon':
                color = '#C40000'
            elif obj.kind.lower() == 'geometry':
                color = self.defaults["global_draw_color"]

            # Change the attributes of the exported SVG
            # We don't need stroke-width
            # We set opacity to maximum
            # We set the colour to WHITE
            root = ET.fromstring(svg_obj)
            for child in root:
                child.set('fill', str(color))
                child.set('opacity', str(transparency_level))
                child.set('stroke', str(color))

            exported_svg.append(ET.tostring(root))

        xmin = Inf
        ymin = Inf
        xmax = -Inf
        ymax = -Inf

        for obj in obj_selection:
            try:
                gxmin, gymin, gxmax, gymax = obj.bounds()
                xmin = min([xmin, gxmin])
                ymin = min([ymin, gymin])
                xmax = max([xmax, gxmax])
                ymax = max([ymax, gymax])
            except Exception as e:
                log.warning("DEV WARNING: Tried to get bounds of empty geometry in App.save_pdf(). %s" % str(e))

        # Determine bounding area for svg export
        bounds = [xmin, ymin, xmax, ymax]
        size = bounds[2] - bounds[0], bounds[3] - bounds[1]

        # This contain the measure units
        uom = obj_selection[0].units.lower()

        # Define a boundary around SVG of about 1.0mm (~39mils)
        if uom in "mm":
            boundary = 1.0
        else:
            boundary = 0.0393701

        # Convert everything to strings for use in the xml doc
        svgwidth = str(size[0] + (2 * boundary))
        svgheight = str(size[1] + (2 * boundary))
        minx = str(bounds[0] - boundary)
        miny = str(bounds[1] + boundary + size[1])

        # Add a SVG Header and footer to the svg output from shapely
        # The transform flips the Y Axis so that everything renders
        # properly within svg apps such as inkscape
        svg_header = '<svg xmlns="http://www.w3.org/2000/svg" ' \
                     'version="1.1" xmlns:xlink="http://www.w3.org/1999/xlink" '
        svg_header += 'width="' + svgwidth + uom + '" '
        svg_header += 'height="' + svgheight + uom + '" '
        svg_header += 'viewBox="' + minx + ' -' + miny + ' ' + svgwidth + ' ' + svgheight + '" '
        svg_header += '>'
        svg_header += '<g transform="scale(1,-1)">'
        svg_footer = '</g> </svg>'

        svg_elem = str(svg_header)
        for svg_item in exported_svg:
            svg_elem += str(svg_item)
        svg_elem += str(svg_footer)

        # Parse the xml through a xml parser just to add line feeds
        # and to make it look more pretty for the output
        doc = parse_xml_string(svg_elem)
        doc_final = doc.toprettyxml()

        try:
            if self.defaults['units'].upper() == 'IN':
                unit = inch
            else:
                unit = mm

            doc_final = StringIO(doc_final)
            drawing = svg2rlg(doc_final)

            if p_size == 'Bounds':
                renderPDF.drawToFile(drawing, file_name)
            else:
                if orientation == 'p':
                    page_size = portrait(self.pagesize[p_size])
                else:
                    page_size = landscape(self.pagesize[p_size])

                my_canvas = canvas.Canvas(file_name, pagesize=page_size)
                my_canvas.translate(bounds[0] * unit, bounds[1] * unit)
                renderPDF.draw(drawing, my_canvas, 0, 0)
                my_canvas.save()
        except Exception as e:
            log.debug("App.save_pdf() --> PDF output --> %s" % str(e))
            return 'fail'

        self.inform.emit('[success] %s: %s' % (_("PDF file saved to"), file_name))

    def export_svg(self, obj_name, filename, scale_stroke_factor=0.00):
        """
        Exports a Geometry Object to an SVG file.

        :param obj_name: the name of the FlatCAM object to be saved as SVG
        :param filename: Path to the SVG file to save to.
        :param scale_stroke_factor: factor by which to change/scale the thickness of the features
        :return:
        """
        self.defaults.report_usage("export_svg()")

        if filename is None:
            filename = self.defaults["global_last_save_folder"] if self.defaults["global_last_save_folder"] \
                                                                   is not None else self.defaults["global_last_folder"]

        self.log.debug("export_svg()")

        try:
            obj = self.collection.get_by_name(str(obj_name))
        except Exception:
            # TODO: The return behavior has not been established... should raise exception?
            return "Could not retrieve object: %s" % obj_name

        with self.proc_container.new(_("Exporting SVG")) as proc:
            exported_svg = obj.export_svg(scale_stroke_factor=scale_stroke_factor)

            # Determine bounding area for svg export
            bounds = obj.bounds()
            size = obj.size()

            # Convert everything to strings for use in the xml doc
            svgwidth = str(size[0])
            svgheight = str(size[1])
            minx = str(bounds[0])
            miny = str(bounds[1] - size[1])
            uom = obj.units.lower()

            # Add a SVG Header and footer to the svg output from shapely
            # The transform flips the Y Axis so that everything renders
            # properly within svg apps such as inkscape
            svg_header = '<svg xmlns="http://www.w3.org/2000/svg" ' \
                         'version="1.1" xmlns:xlink="http://www.w3.org/1999/xlink" '
            svg_header += 'width="' + svgwidth + uom + '" '
            svg_header += 'height="' + svgheight + uom + '" '
            svg_header += 'viewBox="' + minx + ' ' + miny + ' ' + svgwidth + ' ' + svgheight + '">'
            svg_header += '<g transform="scale(1,-1)">'
            svg_footer = '</g> </svg>'
            svg_elem = svg_header + exported_svg + svg_footer

            # Parse the xml through a xml parser just to add line feeds
            # and to make it look more pretty for the output
            svgcode = parse_xml_string(svg_elem)
            svgcode = svgcode.toprettyxml()

            try:
                with open(filename, 'w') as fp:
                    fp.write(svgcode)
            except PermissionError:
                self.inform.emit('[WARNING] %s' %
                                 _("Permission denied, saving not possible.\n"
                                   "Most likely another app is holding the file open and not accessible."))
                return 'fail'

            if self.defaults["global_open_style"] is False:
                self.file_opened.emit("SVG", filename)
            self.file_saved.emit("SVG", filename)
            self.inform.emit('[success] %s: %s' % (_("SVG file exported to"), filename))

    def save_source_file(self, obj_name, filename, use_thread=True):
        """
        Exports a FlatCAM Object to an Gerber/Excellon file.

        :param obj_name: the name of the FlatCAM object for which to save it's embedded source file
        :param filename: Path to the Gerber file to save to.
        :param use_thread: if to be run in a separate thread
        :return:
        """
        self.defaults.report_usage("save source file()")

        if filename is None:
            filename = self.defaults["global_last_save_folder"] if self.defaults["global_last_save_folder"] \
                                                                   is not None else self.defaults["global_last_folder"]

        self.log.debug("save source file()")

        obj = self.collection.get_by_name(obj_name)

        file_string = StringIO(obj.source_file)
        time_string = "{:%A, %d %B %Y at %H:%M}".format(datetime.now())

        if file_string.getvalue() == '':
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _("Save cancelled because source file is empty. Try to export the Gerber file."))
            return 'fail'

        try:
            with open(filename, 'w') as file:
                file.writelines('G04*\n')
                file.writelines('G04 %s (RE)GENERATED BY FLATCAM v%s - www.flatcam.org - Version Date: %s*\n' %
                                (obj.kind.upper(), str(self.version), str(self.version_date)))
                file.writelines('G04 Filename: %s*\n' % str(obj_name))
                file.writelines('G04 Created on : %s*\n' % time_string)

                for line in file_string:
                    file.writelines(line)
        except PermissionError:
            self.inform.emit('[WARNING] %s' %
                             _("Permission denied, saving not possible.\n"
                               "Most likely another app is holding the file open and not accessible."))
            return 'fail'

    def export_excellon(self, obj_name, filename, local_use=None, use_thread=True):
        """
        Exports a Excellon Object to an Excellon file.

        :param obj_name: the name of the FlatCAM object to be saved as Excellon
        :param filename: Path to the Excellon file to save to.
        :param local_use:
        :param use_thread: if to be run in a separate thread
        :return:
        """
        self.defaults.report_usage("export_excellon()")

        if filename is None:
            if self.defaults["global_last_save_folder"]:
                filename = self.defaults["global_last_save_folder"] + '/' + 'exported_excellon'
            else:
                filename = self.defaults["global_last_folder"] + '/' + 'exported_excellon'

        self.log.debug("export_excellon()")

        format_exc = ';FILE_FORMAT=%d:%d\n' % (self.defaults["excellon_exp_integer"],
                                               self.defaults["excellon_exp_decimals"]
                                               )

        if local_use is None:
            try:
                obj = self.collection.get_by_name(str(obj_name))
            except Exception:
                return "Could not retrieve object: %s" % obj_name
        else:
            obj = local_use

        if not isinstance(obj, ExcellonObject):
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _("Failed. Only Excellon objects can be saved as Excellon files..."))
            return

        # updated units
        eunits = self.defaults["excellon_exp_units"]
        ewhole = self.defaults["excellon_exp_integer"]
        efract = self.defaults["excellon_exp_decimals"]
        ezeros = self.defaults["excellon_exp_zeros"]
        eformat = self.defaults["excellon_exp_format"]
        slot_type = self.defaults["excellon_exp_slot_type"]

        fc_units = self.defaults['units'].upper()
        if fc_units == 'MM':
            factor = 1 if eunits == 'METRIC' else 0.03937
        else:
            factor = 25.4 if eunits == 'METRIC' else 1

        def make_excellon():
            try:
                time_str = "{:%A, %d %B %Y at %H:%M}".format(datetime.now())

                header = 'M48\n'
                header += ';EXCELLON GENERATED BY FLATCAM v%s - www.flatcam.org - Version Date: %s\n' % \
                          (str(self.version), str(self.version_date))

                header += ';Filename: %s' % str(obj_name) + '\n'
                header += ';Created on : %s' % time_str + '\n'

                if eformat == 'dec':
                    has_slots, excellon_code = obj.export_excellon(ewhole, efract, factor=factor, slot_type=slot_type)
                    header += eunits + '\n'

                    for tool in obj.tools:
                        if eunits == 'METRIC':
                            header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                          tool=str(tool),
                                                                          dec=2)
                        else:
                            header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                          tool=str(tool),
                                                                          dec=4)
                else:
                    if ezeros == 'LZ':
                        has_slots, excellon_code = obj.export_excellon(ewhole, efract,
                                                                       form='ndec', e_zeros='LZ', factor=factor,
                                                                       slot_type=slot_type)
                        header += '%s,%s\n' % (eunits, 'LZ')
                        header += format_exc

                        for tool in obj.tools:
                            if eunits == 'METRIC':
                                header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                              tool=str(tool),
                                                                              dec=2)
                            else:
                                header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                              tool=str(tool),
                                                                              dec=4)
                    else:
                        has_slots, excellon_code = obj.export_excellon(ewhole, efract,
                                                                       form='ndec', e_zeros='TZ', factor=factor,
                                                                       slot_type=slot_type)
                        header += '%s,%s\n' % (eunits, 'TZ')
                        header += format_exc

                        for tool in obj.tools:
                            if eunits == 'METRIC':
                                header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                              tool=str(tool),
                                                                              dec=2)
                            else:
                                header += "T{tool}F00S00C{:.{dec}f}\n".format(float(obj.tools[tool]['C']) * factor,
                                                                              tool=str(tool),
                                                                              dec=4)
                header += '%\n'
                footer = 'M30\n'

                exported_excellon = header
                exported_excellon += excellon_code
                exported_excellon += footer

                if local_use is None:
                    try:
                        with open(filename, 'w') as fp:
                            fp.write(exported_excellon)
                    except PermissionError:
                        self.inform.emit('[WARNING] %s' %
                                         _("Permission denied, saving not possible.\n"
                                           "Most likely another app is holding the file open and not accessible."))
                        return 'fail'

                    if self.defaults["global_open_style"] is False:
                        self.file_opened.emit("Excellon", filename)
                    self.file_saved.emit("Excellon", filename)
                    self.inform.emit('[success] %s: %s' % (_("Excellon file exported to"), filename))
                else:
                    return exported_excellon
            except Exception as e:
                log.debug("App.export_excellon.make_excellon() --> %s" % str(e))
                return 'fail'

        if use_thread is True:

            with self.proc_container.new(_("Exporting Excellon")) as proc:

                def job_thread_exc(app_obj):
                    ret = make_excellon()
                    if ret == 'fail':
                        self.inform.emit('[ERROR_NOTCL] %s' % _('Could not export Excellon file.'))
                        return

                self.worker_task.emit({'fcn': job_thread_exc, 'params': [self]})
        else:
            eret = make_excellon()
            if eret == 'fail':
                self.inform.emit('[ERROR_NOTCL] %s' % _('Could not export Excellon file.'))
                return 'fail'
            if local_use is not None:
                return eret

    def export_gerber(self, obj_name, filename, local_use=None, use_thread=True):
        """
        Exports a Gerber Object to an Gerber file.

        :param obj_name: the name of the FlatCAM object to be saved as Gerber
        :param filename: Path to the Gerber file to save to.
        :param local_use: if the Gerber code is to be saved to a file (None) or used within FlatCAM.
        When not None, the value will be the actual Gerber object for which to create the Gerber code
        :param use_thread: if to be run in a separate thread
        :return:
        """
        self.defaults.report_usage("export_gerber()")

        if filename is None:
            filename = self.defaults["global_last_save_folder"] if self.defaults["global_last_save_folder"] \
                                                                   is not None else self.defaults["global_last_folder"]

        self.log.debug("export_gerber()")

        if local_use is None:
            try:
                obj = self.collection.get_by_name(str(obj_name))
            except Exception:
                return "Could not retrieve object: %s" % obj_name
        else:
            obj = local_use

        # updated units
        gunits = self.defaults["gerber_exp_units"]
        gwhole = self.defaults["gerber_exp_integer"]
        gfract = self.defaults["gerber_exp_decimals"]
        gzeros = self.defaults["gerber_exp_zeros"]

        fc_units = self.defaults['units'].upper()
        if fc_units == 'MM':
            factor = 1 if gunits == 'MM' else 0.03937
        else:
            factor = 25.4 if gunits == 'MM' else 1

        def make_gerber():
            try:
                time_str = "{:%A, %d %B %Y at %H:%M}".format(datetime.now())

                header = 'G04*\n'
                header += 'G04 RS-274X GERBER GENERATED BY FLATCAM v%s - www.flatcam.org - Version Date: %s*\n' % \
                          (str(self.version), str(self.version_date))

                header += 'G04 Filename: %s*' % str(obj_name) + '\n'
                header += 'G04 Created on : %s*' % time_str + '\n'
                header += '%%FS%sAX%s%sY%s%s*%%\n' % (gzeros, gwhole, gfract, gwhole, gfract)
                header += "%MO{units}*%\n".format(units=gunits)

                for apid in obj.apertures:
                    if obj.apertures[apid]['type'] == 'C':
                        header += "%ADD{apid}{type},{size}*%\n".format(
                            apid=str(apid),
                            type='C',
                            size=(factor * obj.apertures[apid]['size'])
                        )
                    elif obj.apertures[apid]['type'] == 'R':
                        header += "%ADD{apid}{type},{width}X{height}*%\n".format(
                            apid=str(apid),
                            type='R',
                            width=(factor * obj.apertures[apid]['width']),
                            height=(factor * obj.apertures[apid]['height'])
                        )
                    elif obj.apertures[apid]['type'] == 'O':
                        header += "%ADD{apid}{type},{width}X{height}*%\n".format(
                            apid=str(apid),
                            type='O',
                            width=(factor * obj.apertures[apid]['width']),
                            height=(factor * obj.apertures[apid]['height'])
                        )

                header += '\n'

                # obsolete units but some software may need it
                if gunits == 'IN':
                    header += 'G70*\n'
                else:
                    header += 'G71*\n'

                # Absolute Mode
                header += 'G90*\n'

                header += 'G01*\n'
                # positive polarity
                header += '%LPD*%\n'

                footer = 'M02*\n'

                gerber_code = obj.export_gerber(gwhole, gfract, g_zeros=gzeros, factor=factor)

                exported_gerber = header
                exported_gerber += gerber_code
                exported_gerber += footer

                if local_use is None:
                    try:
                        with open(filename, 'w') as fp:
                            fp.write(exported_gerber)
                    except PermissionError:
                        self.inform.emit('[WARNING] %s' %
                                         _("Permission denied, saving not possible.\n"
                                           "Most likely another app is holding the file open and not accessible."))
                        return 'fail'

                    if self.defaults["global_open_style"] is False:
                        self.file_opened.emit("Gerber", filename)
                    self.file_saved.emit("Gerber", filename)
                    self.inform.emit('[success] %s: %s' % (_("Gerber file exported to"), filename))
                else:
                    return exported_gerber
            except Exception as e:
                log.debug("App.export_gerber.make_gerber() --> %s" % str(e))
                return 'fail'

        if use_thread is True:
            with self.proc_container.new(_("Exporting Gerber")) as proc:

                def job_thread_grb(app_obj):
                    ret = make_gerber()
                    if ret == 'fail':
                        self.inform.emit('[ERROR_NOTCL] %s' % _('Could not export Gerber file.'))
                        return

                self.worker_task.emit({'fcn': job_thread_grb, 'params': [self]})
        else:
            gret = make_gerber()
            if gret == 'fail':
                self.inform.emit('[ERROR_NOTCL] %s' % _('Could not export Gerber file.'))
                return 'fail'
            if local_use is not None:
                return gret

    def export_dxf(self, obj_name, filename, use_thread=True):
        """
        Exports a Geometry Object to an DXF file.

        :param obj_name: the name of the FlatCAM object to be saved as DXF
        :param filename: Path to the DXF file to save to.
        :param use_thread: if to be run in a separate thread
        :return:
        """
        self.defaults.report_usage("export_dxf()")

        if filename is None:
            filename = self.defaults["global_last_save_folder"] if self.defaults["global_last_save_folder"] \
                                                                   is not None else self.defaults["global_last_folder"]

        self.log.debug("export_dxf()")

        try:
            obj = self.collection.get_by_name(str(obj_name))
        except Exception:
            # TODO: The return behavior has not been established... should raise exception?
            return "Could not retrieve object: %s" % obj_name

        def make_dxf():
            try:
                dxf_code = obj.export_dxf()
                dxf_code.saveas(filename)
                if self.defaults["global_open_style"] is False:
                    self.file_opened.emit("DXF", filename)
                self.file_saved.emit("DXF", filename)
                self.inform.emit('[success] %s: %s' % (_("DXF file exported to"), filename))
            except Exception:
                return 'fail'

        if use_thread is True:

            with self.proc_container.new(_("Exporting DXF")) as proc:

                def job_thread_exc(app_obj):
                    ret_dxf_val = make_dxf()
                    if ret_dxf_val == 'fail':
                        app_obj.inform.emit('[WARNING_NOTCL] %s' % _('Could not export DXF file.'))
                        return

                self.worker_task.emit({'fcn': job_thread_exc, 'params': [self]})
        else:
            ret = make_dxf()
            if ret == 'fail':
                self.inform.emit('[WARNING_NOTCL] %s' % _('Could not export DXF file.'))
                return

    def import_svg(self, filename, geo_type='geometry', outname=None, plot=True):
        """
        Adds a new Geometry Object to the projects and populates
        it with shapes extracted from the SVG file.

        :param plot:        If True then the resulting object will be plotted on canvas
        :param filename:    Path to the SVG file.
        :param geo_type:    Type of FlatCAM object that will be created from SVG
        :param outname:     The name given to the resulting FlatCAM object
        :return:
        """
        self.defaults.report_usage("import_svg()")
        log.debug("App.import_svg()")

        obj_type = ""
        if geo_type is None or geo_type == "geometry":
            obj_type = "geometry"
        elif geo_type == "gerber":
            obj_type = "gerber"
        else:
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _("Not supported type is picked as parameter. Only Geometry and Gerber are supported"))
            return

        units = self.defaults['units'].upper()

        def obj_init(geo_obj, app_obj):
            geo_obj.import_svg(filename, obj_type, units=units)
            geo_obj.multigeo = False
            geo_obj.source_file = self.export_gerber(obj_name=name, filename=None, local_use=geo_obj, use_thread=False)

        with self.proc_container.new(_("Importing SVG")) as proc:

            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]

            ret = self.new_object(obj_type, name, obj_init, autoselected=False, plot=plot)

            if ret == 'fail':
                self.inform.emit('[ERROR_NOTCL]%s' % _('Import failed.'))
                return 'fail'

            # Register recent file
            self.file_opened.emit("svg", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def import_dxf(self, filename, geo_type='geometry', outname=None, plot=True):
        """
        Adds a new Geometry Object to the projects and populates
        it with shapes extracted from the DXF file.

        :param filename:    Path to the DXF file.
        :param geo_type:    Type of FlatCAM object that will be created from DXF
        :param outname:     Name for the imported Geometry
        :param plot:        If True then the resulting object will be plotted on canvas
        :return:
        """
        self.defaults.report_usage("import_dxf()")

        obj_type = ""
        if geo_type is None or geo_type == "geometry":
            obj_type = "geometry"
        elif geo_type == "gerber":
            obj_type = geo_type
        else:
            self.inform.emit('[ERROR_NOTCL] %s' %
                             _("Not supported type is picked as parameter. Only Geometry and Gerber are supported"))
            return

        units = self.defaults['units'].upper()

        def obj_init(geo_obj, app_obj):
            geo_obj.import_dxf(filename, obj_type, units=units)
            geo_obj.multigeo = False

        with self.proc_container.new(_("Importing DXF")):

            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]

            ret = self.new_object(obj_type, name, obj_init, autoselected=False, plot=plot)

            if ret == 'fail':
                self.inform.emit('[ERROR_NOTCL]%s' % _('Import failed.'))
                return 'fail'

            # Register recent file
            self.file_opened.emit("dxf", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_gerber(self, filename, outname=None, plot=True, from_tcl=False):
        """
        Opens a Gerber file, parses it and creates a new object for
        it in the program. Thread-safe.

        :param outname:     Name of the resulting object. None causes the
                            name to be that of the file. Str.
        :param filename:    Gerber file filename
        :type filename:     str
        :param plot:        boolean, to plot or not the resulting object
        :param from_tcl:    True if run from Tcl Shell
        :return: None
        """

        # How the object should be initialized
        def obj_init(gerber_obj, app_obj):

            assert isinstance(gerber_obj, GerberObject), \
                "Expected to initialize a GerberObject but got %s" % type(gerber_obj)

            # Opening the file happens here
            try:
                gerber_obj.parse_file(filename)
            except IOError:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open file"), filename))
                return "fail"
            except ParseError as err:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s. %s' % (_("Failed to parse file"), filename, str(err)))
                app_obj.log.error(str(err))
                return "fail"
            except Exception as e:
                log.debug("App.open_gerber() --> %s" % str(e))
                msg = '[ERROR] %s' % _("An internal error has occurred. See shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return "fail"

            if gerber_obj.is_empty():
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _("Object is not Gerber file or empty. Aborting object creation."))
                return "fail"

        App.log.debug("open_gerber()")

        with self.proc_container.new(_("Opening Gerber")):
            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]

            # # ## Object creation # ##
            ret_val = self.new_object("gerber", name, obj_init, autoselected=False, plot=plot)
            if ret_val == 'fail':
                if from_tcl:
                    filename = self.defaults['global_tcl_path'] + '/' + name
                    ret_val = self.new_object("gerber", name, obj_init, autoselected=False, plot=plot)
                if ret_val == 'fail':
                    self.inform.emit('[ERROR_NOTCL]%s' % _('Open Gerber failed. Probable not a Gerber file.'))
                    return 'fail'

            # Register recent file
            self.file_opened.emit("gerber", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_excellon(self, filename, outname=None, plot=True, from_tcl=False):
        """
        Opens an Excellon file, parses it and creates a new object for
        it in the program. Thread-safe.

        :param outname:     Name of the resulting object. None causes the name to be that of the file.
        :param filename:    Excellon file filename
        :type filename:     str
        :param plot:        boolean, to plot or not the resulting object
        :param from_tcl:    True if run from Tcl Shell
        :return:            None
        """

        App.log.debug("open_excellon()")

        # How the object should be initialized
        def obj_init(excellon_obj, app_obj):

            try:
                ret = excellon_obj.parse_file(filename=filename)
                if ret == "fail":
                    log.debug("Excellon parsing failed.")
                    self.inform.emit('[ERROR_NOTCL] %s' %
                                     _("This is not Excellon file."))
                    return "fail"
            except IOError:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s' %
                                    (_("Cannot open file"), filename))
                log.debug("Could not open Excellon object.")
                return "fail"
            except Exception:
                msg = '[ERROR_NOTCL] %s' % \
                      _("An internal error has occurred. See shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return "fail"

            ret = excellon_obj.create_geometry()
            if ret == 'fail':
                log.debug("Could not create geometry for Excellon object.")
                return "fail"

            for tool in excellon_obj.tools:
                if excellon_obj.tools[tool]['solid_geometry']:
                    return
            app_obj.inform.emit('[ERROR_NOTCL] %s: %s' % (_("No geometry found in file"), filename))
            return "fail"

        with self.proc_container.new(_("Opening Excellon.")):
            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]
            ret_val = self.new_object("excellon", name, obj_init, autoselected=False, plot=plot)
            if ret_val == 'fail':
                if from_tcl:
                    filename = self.defaults['global_tcl_path'] + '/' + name
                    ret_val = self.new_object("excellon", name, obj_init, autoselected=False, plot=plot)
                if ret_val == 'fail':
                    self.inform.emit('[ERROR_NOTCL] %s' %
                                     _('Open Excellon file failed. Probable not an Excellon file.'))
                    return

            # Register recent file
            self.file_opened.emit("excellon", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_gcode(self, filename, outname=None, force_parsing=None, plot=True, from_tcl=False):
        """
        Opens a G-gcode file, parses it and creates a new object for
        it in the program. Thread-safe.

        :param filename:        G-code file filename
        :param outname:         Name of the resulting object. None causes the name to be that of the file.
        :param force_parsing:
        :param plot:            If True plot the object on canvas
        :param from_tcl:        True if run from Tcl Shell
        :return:                None
        """
        App.log.debug("open_gcode()")

        # How the object should be initialized
        def obj_init(job_obj, app_obj_):
            """
            :param job_obj: the resulting object
            :type app_obj_: App
            """
            assert isinstance(app_obj_, App), \
                "Initializer expected App, got %s" % type(app_obj_)

            app_obj_.inform.emit('%s...' % _("Reading GCode file"))
            try:
                f = open(filename)
                gcode = f.read()
                f.close()
            except IOError:
                app_obj_.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open"), filename))
                return "fail"

            job_obj.gcode = gcode

            gcode_ret = job_obj.gcode_parse(force_parsing=force_parsing)
            if gcode_ret == "fail":
                self.inform.emit('[ERROR_NOTCL] %s' % _("This is not GCODE"))
                return "fail"

            job_obj.create_geometry()

        with self.proc_container.new(_("Opening G-Code.")):

            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]

            # New object creation and file processing
            ret_val = self.new_object("cncjob", name, obj_init, autoselected=False, plot=plot)
            if ret_val == 'fail':
                if from_tcl:
                    filename = self.defaults['global_tcl_path'] + '/' + name
                    ret_val = self.new_object("cncjob", name, obj_init, autoselected=False, plot=plot)
                if ret_val == 'fail':
                    self.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Failed to create CNCJob Object. Probable not a GCode file. "
                                       "Try to load it from File menu.\n "
                                       "Attempting to create a FlatCAM CNCJob Object from "
                                       "G-Code file failed during processing"))
                    return "fail"

            # Register recent file
            self.file_opened.emit("cncjob", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_hpgl2(self, filename, outname=None):
        """
        Opens a HPGL2 file, parses it and creates a new object for
        it in the program. Thread-safe.

        :param outname:     Name of the resulting object. None causes the name to be that of the file.
        :param filename:    HPGL2 file filename
        :return:            None
        """
        filename = filename

        # How the object should be initialized
        def obj_init(geo_obj, app_obj):

            assert isinstance(geo_obj, GeometryObject), \
                "Expected to initialize a GeometryObject but got %s" % type(geo_obj)

            # Opening the file happens here
            obj = HPGL2(self)
            try:
                HPGL2.parse_file(obj, filename)
            except IOError:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open file"), filename))
                return "fail"
            except ParseError as err:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s. %s' % (_("Failed to parse file"), filename, str(err)))
                app_obj.log.error(str(err))
                return "fail"
            except Exception as e:
                log.debug("App.open_hpgl2() --> %s" % str(e))
                msg = '[ERROR] %s' % _("An internal error has occurred. See shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return "fail"

            geo_obj.multigeo = True
            geo_obj.solid_geometry = deepcopy(obj.solid_geometry)
            geo_obj.tools = deepcopy(obj.tools)
            geo_obj.source_file = deepcopy(obj.source_file)

            del obj

            if not geo_obj.solid_geometry:
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _("Object is not HPGL2 file or empty. Aborting object creation."))
                return "fail"

        App.log.debug("open_hpgl2()")

        with self.proc_container.new(_("Opening HPGL2")):
            # Object name
            name = outname or filename.split('/')[-1].split('\\')[-1]

            # # ## Object creation # ##
            ret = self.new_object("geometry", name, obj_init, autoselected=False)
            if ret == 'fail':
                self.inform.emit('[ERROR_NOTCL]%s' % _(' Open HPGL2 failed. Probable not a HPGL2 file.'))
                return 'fail'

            # Register recent file
            self.file_opened.emit("geometry", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_script(self, filename, outname=None, silent=False):
        """
        Opens a Script file, parses it and creates a new object for
        it in the program. Thread-safe.

        :param outname:     Name of the resulting object. None causes the name to be that of the file.
        :param filename:    Script file filename
        :param silent:      If True there will be no messages printed to StatusBar
        :return:            None
        """

        def obj_init(script_obj, app_obj):

            assert isinstance(script_obj, ScriptObject), \
                "Expected to initialize a ScriptObject but got %s" % type(script_obj)

            if silent is False:
                app_obj.inform.emit('[success] %s' % _("TCL script file opened in Code Editor."))

            try:
                script_obj.parse_file(filename)
            except IOError:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open file"), filename))
                return "fail"
            except ParseError as err:
                app_obj.inform.emit('[ERROR_NOTCL] %s: %s. %s' % (_("Failed to parse file"), filename, str(err)))
                app_obj.log.error(str(err))
                return "fail"
            except Exception as e:
                log.debug("App.open_script() -> %s" % str(e))
                msg = '[ERROR] %s' % _("An internal error has occurred. See shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return "fail"

        App.log.debug("open_script()")

        with self.proc_container.new(_("Opening TCL Script...")):

            # Object name
            script_name = outname or filename.split('/')[-1].split('\\')[-1]

            # Object creation
            ret_val = self.new_object("script", script_name, obj_init, autoselected=False, plot=False)
            if ret_val == 'fail':
                filename = self.defaults['global_tcl_path'] + '/' + script_name
                ret_val = self.new_object("script", script_name, obj_init, autoselected=False, plot=False)
                if ret_val == 'fail':
                    self.inform.emit('[ERROR_NOTCL]%s' % _('Failed to open TCL Script.'))
                    return 'fail'

            # Register recent file
            self.file_opened.emit("script", filename)

            # GUI feedback
            self.inform.emit('[success] %s: %s' % (_("Opened"), filename))

    def open_config_file(self, filename, run_from_arg=None):
        """
        Loads a config file from the specified file.

        :param filename:        Name of the file from which to load.
        :param run_from_arg:    if True the FlatConfig file will be open as an command line argument
        :return:                None
        """
        App.log.debug("Opening config file: " + filename)

        if run_from_arg:
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening FlatCAM Config file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))
        # # add the tab if it was closed
        # self.ui.plot_tab_area.addTab(self.ui.text_editor_tab, _("Code Editor"))
        # # first clear previous text in text editor (if any)
        # self.ui.text_editor_tab.code_editor.clear()
        #
        # # Switch plot_area to CNCJob tab
        # self.ui.plot_tab_area.setCurrentWidget(self.ui.text_editor_tab)

        # close the Code editor if already open
        if self.toggle_codeeditor:
            self.on_toggle_code_editor()

        self.on_toggle_code_editor()

        try:
            if filename:
                f = QtCore.QFile(filename)
                if f.open(QtCore.QIODevice.ReadOnly):
                    stream = QtCore.QTextStream(f)
                    code_edited = stream.readAll()
                    self.text_editor_tab.code_editor.setPlainText(code_edited)
                    f.close()
        except IOError:
            App.log.error("Failed to open config file: %s" % filename)
            self.inform.emit('[ERROR_NOTCL] %s: %s' %
                             (_("Failed to open config file"), filename))
            return

    def open_project(self, filename, run_from_arg=None, plot=True, cli=None, from_tcl=False):
        """
        Loads a project from the specified file.

        1) Loads and parses file
        2) Registers the file as recently opened.
        3) Calls on_file_new()
        4) Updates options
        5) Calls new_object() with the object's from_dict() as init method.
        6) Calls plot_all() if plot=True

        :param filename:        Name of the file from which to load.
        :param run_from_arg:    True if run for arguments
        :param plot:            If True plot all objects in the project
        :param cli:             Run from command line
        :param from_tcl:        True if run from Tcl Sehll
        :return:                None
        """
        App.log.debug("Opening project: " + filename)

        # block autosaving while a project is loaded
        self.block_autosave = True

        # for some reason, setting ui_title does not work when this method is called from Tcl Shell
        # it's because the TclCommand is run in another thread (it inherit TclCommandSignaled)
        if cli is None:
            self.set_ui_title(name=_("Loading Project ... Please Wait ..."))

        if run_from_arg:
            self.splash.showMessage('%s: %ssec\n%s' % (_("Canvas initialization started.\n"
                                                         "Canvas initialization finished in"), '%.2f' % self.used_time,
                                                       _("Opening FlatCAM Project file.")),
                                    alignment=Qt.AlignBottom | Qt.AlignLeft,
                                    color=QtGui.QColor("gray"))

        # Open and parse an uncompressed Project file
        try:
            f = open(filename, 'r')
        except IOError:
            if from_tcl:
                name = filename.split('/')[-1].split('\\')[-1]
                filename = self.defaults['global_tcl_path'] + '/' + name
                try:
                    f = open(filename, 'r')
                except IOError:
                    log.error("Failed to open project file: %s" % filename)
                    self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open project file"), filename))
                    return
            else:
                log.error("Failed to open project file: %s" % filename)
                self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open project file"), filename))
                return

        try:
            d = json.load(f, object_hook=dict2obj)
        except Exception as e:
            log.error("Failed to parse project file, trying to see if it loads as an LZMA archive: %s because %s" %
                      (filename, str(e)))
            f.close()

            # Open and parse a compressed Project file
            try:
                with lzma.open(filename) as f:
                    file_content = f.read().decode('utf-8')
                    d = json.loads(file_content, object_hook=dict2obj)
            except Exception as e:
                App.log.error("Failed to open project file: %s with error: %s" % (filename, str(e)))
                self.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Failed to open project file"), filename))
                return

        # Clear the current project
        # # NOT THREAD SAFE # ##
        if run_from_arg is True:
            pass
        elif cli is True:
            self.delete_selection_shape()
        else:
            self.on_file_new()

        # Project options
        self.options.update(d['options'])

        self.project_filename = filename

        # for some reason, setting ui_title does not work when this method is called from Tcl Shell
        # it's because the TclCommand is run in another thread (it inherit TclCommandSignaled)
        if cli is None:
            self.set_screen_units(self.options["units"])

        # Re create objects
        App.log.debug(" **************** Started PROEJCT loading... **************** ")

        for obj in d['objs']:
            try:
                def obj_init(obj_inst, app_inst):

                    obj_inst.from_dict(obj)

                App.log.debug("Recreating from opened project an %s object: %s" %
                              (obj['kind'].capitalize(), obj['options']['name']))

                # for some reason, setting ui_title does not work when this method is called from Tcl Shell
                # it's because the TclCommand is run in another thread (it inherit TclCommandSignaled)
                if cli is None:
                    self.set_ui_title(name="{} {}: {}".format(_("Loading Project ... restoring"),
                                                              obj['kind'].upper(),
                                                              obj['options']['name']
                                                              )
                                      )

                self.new_object(obj['kind'], obj['options']['name'], obj_init, plot=plot)
            except Exception as e:
                print('App.open_project() --> ' + str(e))

        self.inform.emit('[success] %s: %s' % (_("Project loaded from"), filename))

        self.should_we_save = False
        self.file_opened.emit("project", filename)

        # restore autosaving after a project was loaded
        self.block_autosave = False

        # for some reason, setting ui_title does not work when this method is called from Tcl Shell
        # it's because the TclCommand is run in another thread (it inherit TclCommandSignaled)
        if cli is None:
            self.set_ui_title(name=self.project_filename)

        App.log.debug(" **************** Finished PROJECT loading... **************** ")

    def plot_all(self, fit_view=True, use_thread=True):
        """
        Re-generates all plots from all objects.

        :param fit_view:    if True will plot the objects and will adjust the zoom to fit all plotted objects into view
        :param use_thread:  if True will use threading for plotting the objects
        :return:            None
        """
        self.log.debug("Plot_all()")
        self.inform.emit('[success] %s...' % _("Redrawing all objects"))

        for plot_obj in self.collection.get_list():
            def worker_task(obj):
                with self.proc_container.new("Plotting"):
                    obj.plot(kind=self.defaults["cncjob_plot_kind"])
                    if fit_view is True:
                        self.object_plotted.emit(obj)

            if use_thread is True:
                # Send to worker
                self.worker_task.emit({'fcn': worker_task, 'params': [plot_obj]})
            else:
                worker_task(plot_obj)

    def register_folder(self, filename):
        """
        Register the last folder used by the app to open something

        :param filename:    the last folder is extracted from the filename
        :return:            None
        """
        self.defaults["global_last_folder"] = os.path.split(str(filename))[0]

    def register_save_folder(self, filename):
        """
        Register the last folder used by the app to save something

        :param filename:    the last folder is extracted from the filename
        :return:            None
        """
        self.defaults["global_last_save_folder"] = os.path.split(str(filename))[0]

    # def set_progress_bar(self, percentage, text=""):
    #     """
    #     Set a progress bar to a value (percentage)
    #
    #     :param percentage:  Value set to the progressbar
    #     :param text:        Not used
    #     :return:            None
    #     """
    #     self.ui.progress_bar.setValue(int(percentage))

    def setup_recent_items(self):
        """
        Setup a dictionary with the recent files accessed, organized by type

        :return:
        """
        icons = {
            "gerber": self.resource_location + "/flatcam_icon16.png",
            "excellon": self.resource_location + "/drill16.png",
            'geometry': self.resource_location + "/geometry16.png",
            "cncjob": self.resource_location + "/cnc16.png",
            "script": self.resource_location + "/script_new24.png",
            "document": self.resource_location + "/notes16_1.png",
            "project": self.resource_location + "/project16.png",
            "svg": self.resource_location + "/geometry16.png",
            "dxf": self.resource_location + "/dxf16.png",
            "pdf": self.resource_location + "/pdf32.png",
            "image": self.resource_location + "/image16.png"

        }

        try:
            image_opener = self.image_tool.import_image
        except AttributeError:
            image_opener = None

        openers = {
            'gerber': lambda fname: self.worker_task.emit({'fcn': self.open_gerber, 'params': [fname]}),
            'excellon': lambda fname: self.worker_task.emit({'fcn': self.open_excellon, 'params': [fname]}),
            'geometry': lambda fname: self.worker_task.emit({'fcn': self.import_dxf, 'params': [fname]}),
            'cncjob': lambda fname: self.worker_task.emit({'fcn': self.open_gcode, 'params': [fname]}),
            "script": lambda fname: self.worker_task.emit({'fcn': self.open_script, 'params': [fname]}),
            "document": None,
            'project': self.open_project,
            'svg': self.import_svg,
            'dxf': self.import_dxf,
            'image': image_opener,
            'pdf': lambda fname: self.worker_task.emit({'fcn': self.pdf_tool.open_pdf, 'params': [fname]})
        }

        # Open recent file for files
        try:
            f = open(self.data_path + '/recent.json')
        except IOError:
            App.log.error("Failed to load recent item list.")
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed to load recent item list."))
            return

        try:
            self.recent = json.load(f)
        except json.errors.JSONDecodeError:
            App.log.error("Failed to parse recent item list.")
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed to parse recent item list."))
            f.close()
            return
        f.close()

        # Open recent file for projects
        try:
            fp = open(self.data_path + '/recent_projects.json')
        except IOError:
            App.log.error("Failed to load recent project item list.")
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed to load recent projects item list."))
            return

        try:
            self.recent_projects = json.load(fp)
        except json.errors.JSONDecodeError:
            App.log.error("Failed to parse recent project item list.")
            self.inform.emit('[ERROR_NOTCL] %s' % _("Failed to parse recent project item list."))
            fp.close()
            return
        fp.close()

        # Closure needed to create callbacks in a loop.
        # Otherwise late binding occurs.
        def make_callback(func, fname):
            def opener():
                func(fname)

            return opener

        def reset_recent_files():
            # Reset menu
            self.ui.recent.clear()
            self.recent = []
            try:
                ff = open(self.data_path + '/recent.json', 'w')
            except IOError:
                App.log.error("Failed to open recent items file for writing.")
                return

            json.dump(self.recent, ff)

        def reset_recent_projects():
            # Reset menu
            self.ui.recent_projects.clear()
            self.recent_projects = []

            try:
                frp = open(self.data_path + '/recent_projects.json', 'w')
            except IOError:
                App.log.error("Failed to open recent projects items file for writing.")
                return

            json.dump(self.recent, frp)

        # Reset menu
        self.ui.recent.clear()
        self.ui.recent_projects.clear()

        # Create menu items for projects
        for recent in self.recent_projects:
            filename = recent['filename'].split('/')[-1].split('\\')[-1]

            if recent['kind'] == 'project':
                try:
                    action = QtWidgets.QAction(QtGui.QIcon(icons[recent["kind"]]), filename, self)

                    # Attach callback
                    o = make_callback(openers[recent["kind"]], recent['filename'])
                    action.triggered.connect(o)

                    self.ui.recent_projects.addAction(action)

                except KeyError:
                    App.log.error("Unsupported file type: %s" % recent["kind"])

        # Last action in Recent Files menu is one that Clear the content
        clear_action_proj = QtWidgets.QAction(QtGui.QIcon(self.resource_location + '/trash32.png'),
                                              (_("Clear Recent projects")), self)
        clear_action_proj.triggered.connect(reset_recent_projects)
        self.ui.recent_projects.addSeparator()
        self.ui.recent_projects.addAction(clear_action_proj)

        # Create menu items for files
        for recent in self.recent:
            filename = recent['filename'].split('/')[-1].split('\\')[-1]

            if recent['kind'] != 'project':
                try:
                    action = QtWidgets.QAction(QtGui.QIcon(icons[recent["kind"]]), filename, self)

                    # Attach callback
                    o = make_callback(openers[recent["kind"]], recent['filename'])
                    action.triggered.connect(o)

                    self.ui.recent.addAction(action)

                except KeyError:
                    App.log.error("Unsupported file type: %s" % recent["kind"])

        # Last action in Recent Files menu is one that Clear the content
        clear_action = QtWidgets.QAction(QtGui.QIcon(self.resource_location + '/trash32.png'),
                                         (_("Clear Recent files")), self)
        clear_action.triggered.connect(reset_recent_files)
        self.ui.recent.addSeparator()
        self.ui.recent.addAction(clear_action)

        # self.builder.get_object('open_recent').set_submenu(recent_menu)
        # self.ui.menufilerecent.set_submenu(recent_menu)
        # recent_menu.show_all()
        # self.ui.recent.show()

        self.log.debug("Recent items list has been populated.")

    def setup_component_editor(self):
        """
        Default text for the Selected tab when is not taken by the Object UI.

        :return:
        """
        # label = QtWidgets.QLabel("Choose an item from Project")
        # label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)

        sel_title = QtWidgets.QTextEdit(
            _('<b>Shortcut Key List</b>'))
        sel_title.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        sel_title.setFrameStyle(QtWidgets.QFrame.NoFrame)

        f_settings = QSettings("Open Source", "FlatCAM")
        if f_settings.contains("notebook_font_size"):
            fsize = f_settings.value('notebook_font_size', type=int)
        else:
            fsize = 12

        tsize = fsize + int(fsize / 2)

        #         selected_text = (_('''
        # <p><span style="font-size:{tsize}px"><strong>Selected Tab - Choose an Item from Project Tab</strong></span>
        # </p>
        #
        # <p><span style="font-size:{fsize}px"><strong>Details</strong>:<br />
        # The normal flow when working in FlatCAM is the following:</span></p>
        #
        # <ol>
        # 	<li><span style="font-size:{fsize}px">Loat/Import a Gerber, Excellon, Gcode, DXF, Raster Image or SVG
        # 	file into
        # 	FlatCAM using either the menu&#39;s, toolbars, key shortcuts or
        # 	even dragging and dropping the files on the GUI.<br />
        # 	<br />
        # 	You can also load a <strong>FlatCAM project</strong> by double clicking on the project file, drag &amp;
        # 	drop of the
        # 	file into the FLATCAM GUI or through the menu/toolbar links offered within the app.</span><br />
        # 	&nbsp;</li>
        # 	<li><span style="font-size:{fsize}px">Once an object is available in the Project Tab, by selecting it
        # 	and then
        # 	focusing on <strong>SELECTED TAB </strong>(more simpler is to double click the object name in the
        # 	Project Tab), <strong>SELECTED TAB </strong>will be updated with the object properties according to
        # 	it&#39;s kind: Gerber, Excellon, Geometry or CNCJob object.<br />
        # 	<br />
        # 	If the selection of the object is done on the canvas by single click instead, and the
        # 	<strong>SELECTED TAB</strong>
        # 	is in focus, again the object properties will be displayed into the Selected Tab. Alternatively,
        # 	double clicking on the object on the canvas will bring the <strong>SELECTED TAB</strong> and populate
        # 	it even if it was out of focus.<br />
        # 	<br />
        # 	You can change the parameters in this screen and the flow direction is like this:<br />
        # 	<br />
        # 	<strong>Gerber/Excellon Object</strong> -&gt; Change Param -&gt; Generate Geometry -&gt;
        # 	<strong> Geometry Object
        # 	</strong>-&gt; Add tools (change param in Selected Tab) -&gt; Generate CNCJob -&gt;<strong> CNCJob Object
        # 	</strong>-&gt; Verify GCode (through Edit CNC Code) and/or append/prepend to GCode (again, done in
        # 	<strong>SELECTED TAB)&nbsp;</strong>-&gt; Save GCode</span></li>
        # </ol>
        #
        # <p><span style="font-size:{fsize}px">A list of key shortcuts is available through an menu entry in
        # <strong>Help -&gt; Shortcuts List</strong>&nbsp;or through it&#39;s own key shortcut:
        # <strong>F3</strong>.</span></p>
        #
        #         ''').format(fsize=fsize, tsize=tsize))

        selected_text = '''
        <p><span style="font-size:{tsize}px"><strong>{title}</strong></span></p>

        <p><span style="font-size:{fsize}px"><strong>{subtitle}</strong>:<br />
        {s1}</span></p>

        <ol>
            <li><span style="font-size:{fsize}px">{s2}<br />
            <br />
            {s3}</span><br />
            &nbsp;</li>
            <li><span style="font-size:{fsize}px">{s4}<br />
            &nbsp;</li>
            <br />
            <li><span style="font-size:{fsize}px">{s5}<br />
            &nbsp;</li>
            <br />
            <li><span style="font-size:{fsize}px">{s6}<br />
            <br />
            {s7}</span></li>
        </ol>

        <p><span style="font-size:{fsize}px">{s8}</span></p>
        '''.format(
            title=_("Selected Tab - Choose an Item from Project Tab"),
            subtitle=_("Details"),

            s1=_("The normal flow when working in FlatCAM is the following:"),
            s2=_("Load/Import a Gerber, Excellon, Gcode, DXF, Raster Image or SVG file into FlatCAM "
                 "using either the toolbars, key shortcuts or even dragging and dropping the "
                 "files on the GUI."),
            s3=_("You can also load a FlatCAM project by double clicking on the project file, "
                 "drag and drop of the file into the FLATCAM GUI or through the menu (or toolbar) "
                 "actions offered within the app."),
            s4=_("Once an object is available in the Project Tab, by selecting it and then focusing "
                 "on SELECTED TAB (more simpler is to double click the object name in the Project Tab, "
                 "SELECTED TAB will be updated with the object properties according to its kind: "
                 "Gerber, Excellon, Geometry or CNCJob object."),
            s5=_("If the selection of the object is done on the canvas by single click instead, "
                 "and the SELECTED TAB is in focus, again the object properties will be displayed into the "
                 "Selected Tab. Alternatively, double clicking on the object on the canvas will bring "
                 "the SELECTED TAB and populate it even if it was out of focus."),
            s6=_("You can change the parameters in this screen and the flow direction is like this:"),
            s7=_("Gerber/Excellon Object --> Change Parameter --> Generate Geometry --> Geometry Object --> "
                 "Add tools (change param in Selected Tab) --> Generate CNCJob --> CNCJob Object --> "
                 "Verify GCode (through Edit CNC Code) and/or append/prepend to GCode "
                 "(again, done in SELECTED TAB) --> Save GCode."),
            s8=_("A list of key shortcuts is available through an menu entry in Help --> Shortcuts List "
                 "or through its own key shortcut: <b>F3</b>."),
            tsize=tsize,
            fsize=fsize
        )

        sel_title.setText(selected_text)
        sel_title.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.ui.selected_scroll_area.setWidget(sel_title)

    def setup_obj_classes(self):
        """
        Sets up application specifics on the FlatCAMObj class. This way the object.app attribute will point to the App
        class.

        :return: None
        """
        FlatCAMObj.app = self
        ObjectCollection.app = self
        Gerber.app = self
        Excellon.app = self
        Geometry.app = self
        CNCjob.app = self
        FCProcess.app = self
        FCProcessContainer.app = self
        OptionsGroupUI.app = self

    def version_check(self):
        """
        Checks for the latest version of the program. Alerts the
        user if theirs is outdated. This method is meant to be run
        in a separate thread.

        :return: None
        """

        self.log.debug("version_check()")


        if self.defaults["global_send_stats"] is True:
            full_url = "%s?s=%s&v=%s&os=%s&%s" % (
                App.version_url,
                str(self.defaults['global_serial']),
                str(self.version),
                str(self.os),
                urllib.parse.urlencode(self.defaults["global_stats"])
            )
            # full_url = App.version_url + "?s=" + str(self.defaults['global_serial']) + \
            #            "&v=" + str(self.version) + "&os=" + str(self.os) + "&" + \
            #            urllib.parse.urlencode(self.defaults["global_stats"])
        else:
            # no_stats dict; just so it won't break things on website
            no_ststs_dict = {}
            no_ststs_dict["global_ststs"] = {}
            full_url = App.version_url + "?s=" + str(self.defaults['global_serial']) + "&v=" + str(self.version) + \
                       "&os=" + str(self.os) + "&" + urllib.parse.urlencode(no_ststs_dict["global_ststs"])

        App.log.debug("Checking for updates @ %s" % full_url)
        # ## Get the data
        try:
            f = urllib.request.urlopen(full_url)
        except Exception:
            # App.log.warning("Failed checking for latest version. Could not connect.")
            self.log.warning("Failed checking for latest version. Could not connect.")
            self.inform.emit('[WARNING_NOTCL] %s' % _("Failed checking for latest version. Could not connect."))
            return

        try:
            data = json.load(f)
        except Exception as e:
            App.log.error("Could not parse information about latest version.")
            self.inform.emit('[ERROR_NOTCL] %s' % _("Could not parse information about latest version."))
            App.log.debug("json.load(): %s" % str(e))
            f.close()
            return

        f.close()

        # ## Latest version?
        if self.version >= data["version"]:
            App.log.debug("FlatCAM is up to date!")
            self.inform.emit('[success] %s' % _("FlatCAM is up to date!"))
            return

        App.log.debug("Newer version available.")
        self.message.emit(
            _("Newer Version Available"),
            '%s<br><br>><b>%s</b><br>%s' % (
                _("There is a newer version of FlatCAM available for download:"),
                str(data["name"]),
                str(data["message"])
            ),
            _("info")
        )

    def on_plotcanvas_setup(self, container=None):
        """
        This is doing the setup for the plot area (canvas).

        :param container:   QT Widget where to install the canvas
        :return:            None
        """
        if container:
            plot_container = container
        else:
            plot_container = self.ui.right_layout

        modifier = QtWidgets.QApplication.queryKeyboardModifiers()
        if self.is_legacy is True or modifier == QtCore.Qt.ControlModifier:
            self.is_legacy = True
            self.defaults["global_graphic_engine"] = "2D"
            self.plotcanvas = PlotCanvasLegacy(plot_container, self)
        else:
            try:
                self.plotcanvas = PlotCanvas(plot_container, self)
            except Exception as er:
                msg_txt = traceback.format_exc()
                log.debug("App.on_plotcanvas_setup() failed -> %s" % str(er))
                log.debug("OpenGL canvas initialization failed with the following error.\n" + msg_txt)
                msg = '[ERROR_NOTCL] %s' % _("An internal error has occurred. See shell.\n")
                msg += _("OpenGL canvas initialization failed. HW or HW configuration not supported."
                         "Change the graphic engine to Legacy(2D) in Edit -> Preferences -> General tab.\n\n")
                msg += msg_txt
                self.inform.emit(msg)
                return 'fail'

        # So it can receive key presses
        self.plotcanvas.native.setFocus()

        if self.is_legacy is False:
            pan_button = 2 if self.defaults["global_pan_button"] == '2' else 3
            # Set the mouse button for panning
            self.plotcanvas.view.camera.pan_button_setting = pan_button

        self.mm = self.plotcanvas.graph_event_connect('mouse_move', self.on_mouse_move_over_plot)
        self.mp = self.plotcanvas.graph_event_connect('mouse_press', self.on_mouse_click_over_plot)
        self.mr = self.plotcanvas.graph_event_connect('mouse_release', self.on_mouse_click_release_over_plot)
        self.mdc = self.plotcanvas.graph_event_connect('mouse_double_click', self.on_mouse_double_click_over_plot)

        # Keys over plot enabled
        self.kp = self.plotcanvas.graph_event_connect('key_press', self.ui.keyPressEvent)

        if self.defaults['global_cursor_type'] == 'small':
            self.app_cursor = self.plotcanvas.new_cursor()
        else:
            self.app_cursor = self.plotcanvas.new_cursor(big=True)

        if self.ui.grid_snap_btn.isChecked():
            self.app_cursor.enabled = True
        else:
            self.app_cursor.enabled = False

        if self.is_legacy is False:
            self.hover_shapes = ShapeCollection(parent=self.plotcanvas.view.scene, layers=1)
        else:
            # will use the default Matplotlib axes
            self.hover_shapes = ShapeCollectionLegacy(obj=self, app=self, name='hover')

    def on_zoom_fit(self, event):
        """
        Callback for zoom-fit request. This can be either from the corresponding
        toolbar button or the '1' key when the canvas is focused. Calls ``self.adjust_axes()``
        with axes limits from the geometry bounds of all objects.

        :param event:   Ignored.
        :return:        None
        """
        if self.is_legacy is False:
            self.plotcanvas.fit_view()
        else:
            xmin, ymin, xmax, ymax = self.collection.get_bounds()
            width = xmax - xmin
            height = ymax - ymin
            xmin -= 0.05 * width
            xmax += 0.05 * width
            ymin -= 0.05 * height
            ymax += 0.05 * height
            self.plotcanvas.adjust_axes(xmin, ymin, xmax, ymax)

    def on_zoom_in(self):
        """
        Callback for zoom-in request.
        :return:
        """
        self.plotcanvas.zoom(1 / float(self.defaults['global_zoom_ratio']))

    def on_zoom_out(self):
        """
        Callback for zoom-out request.

        :return:
        """
        self.plotcanvas.zoom(float(self.defaults['global_zoom_ratio']))

    def disable_all_plots(self):
        self.defaults.report_usage("disable_all_plots()")

        self.disable_plots(self.collection.get_list())
        self.inform.emit('[success] %s' %
                         _("All plots disabled."))

    def disable_other_plots(self):
        self.defaults.report_usage("disable_other_plots()")

        self.disable_plots(self.collection.get_non_selected())
        self.inform.emit('[success] %s' %
                         _("All non selected plots disabled."))

    def enable_all_plots(self):
        self.defaults.report_usage("enable_all_plots()")

        self.enable_plots(self.collection.get_list())
        self.inform.emit('[success] %s' %
                         _("All plots enabled."))

    def on_enable_sel_plots(self):
        log.debug("App.on_enable_sel_plot()")
        object_list = self.collection.get_selected()
        self.enable_plots(objects=object_list)
        self.inform.emit('[success] %s' % _("Selected plots enabled..."))

    def on_disable_sel_plots(self):
        log.debug("App.on_disable_sel_plot()")

        # self.inform.emit(_("Disabling plots ..."))
        object_list = self.collection.get_selected()
        self.disable_plots(objects=object_list)
        self.inform.emit('[success] %s' % _("Selected plots disabled..."))

    def enable_plots(self, objects):
        """
        Enable plots

        :param objects: list of Objects to be enabled
        :return:
        """
        log.debug("Enabling plots ...")
        # self.inform.emit(_("Working ..."))

        for obj in objects:
            if obj.options['plot'] is False:
                obj.options.set_change_callback(lambda x: None)
                obj.options['plot'] = True
                try:
                    # only the Gerber obj has on_plot_cb_click() method
                    obj.ui.plot_cb.stateChanged.disconnect(obj.on_plot_cb_click)
                    # disable this cb while disconnected,
                    # in case the operation takes time the user is not allowed to change it
                    obj.ui.plot_cb.setDisabled(True)
                except AttributeError:
                    pass
                obj.set_form_item("plot")
                try:
                    obj.ui.plot_cb.stateChanged.connect(obj.on_plot_cb_click)
                    obj.ui.plot_cb.setDisabled(False)
                except AttributeError:
                    pass
                obj.options.set_change_callback(obj.on_options_change)

        def worker_task(objs):
            with self.proc_container.new(_("Enabling plots ...")):
                for plot_obj in objs:
                    # obj.options['plot'] = True
                    if isinstance(plot_obj, CNCJobObject):
                        plot_obj.plot(visible=True, kind=self.defaults["cncjob_plot_kind"])
                    else:
                        plot_obj.plot(visible=True)

        self.worker_task.emit({'fcn': worker_task, 'params': [objects]})

        # self.plots_updated.emit()

    def disable_plots(self, objects):
        """
        Disables plots

        :param objects: list of Objects to be disabled
        :return:
        """

        # if no objects selected then do nothing
        if not self.collection.get_selected():
            return

        log.debug("Disabling plots ...")
        # self.inform.emit(_("Working ..."))

        for obj in objects:
            if obj.options['plot'] is True:
                obj.options.set_change_callback(lambda x: None)
                obj.options['plot'] = False
                try:
                    # only the Gerber obj has on_plot_cb_click() method
                    obj.ui.plot_cb.stateChanged.disconnect(obj.on_plot_cb_click)
                    obj.ui.plot_cb.setDisabled(True)
                except AttributeError:
                    pass
                obj.set_form_item("plot")
                try:
                    obj.ui.plot_cb.stateChanged.connect(obj.on_plot_cb_click)
                    obj.ui.plot_cb.setDisabled(False)
                except AttributeError:
                    pass
                obj.options.set_change_callback(obj.on_options_change)

        try:
            self.delete_selection_shape()
        except Exception as e:
            log.debug("App.disable_plots() --> %s" % str(e))

        # self.plots_updated.emit()
        def worker_task(objs):
            with self.proc_container.new(_("Disabling plots ...")):
                for plot_obj in objs:
                    # obj.options['plot'] = True
                    if isinstance(plot_obj, CNCJobObject):
                        plot_obj.plot(visible=False, kind=self.defaults["cncjob_plot_kind"])
                    else:
                        plot_obj.plot(visible=False)

        self.worker_task.emit({'fcn': worker_task, 'params': [objects]})

    def toggle_plots(self, objects):
        """
        Toggle plots visibility

        :param objects:     list of Objects for which to be toggled the visibility
        :return:            None
        """

        # if no objects selected then do nothing
        if not self.collection.get_selected():
            return

        log.debug("Toggling plots ...")
        self.inform.emit(_("Working ..."))
        for obj in objects:
            if obj.options['plot'] is False:
                obj.options['plot'] = True
            else:
                obj.options['plot'] = False
        self.plots_updated.emit()

    def clear_plots(self):
        """
        Clear the plots

        :return:            None
        """

        objects = self.collection.get_list()

        for obj in objects:
            obj.clear(obj == objects[-1])

        # Clear pool to free memory
        self.clear_pool()

    def on_set_color_action_triggered(self):
        """
        This slot gets called by clicking on the menu entry in the Set Color submenu of the context menu in Project Tab

        :return:
        """
        new_color = self.defaults['gerber_plot_fill']
        clicked_action = self.sender()

        assert isinstance(clicked_action, QAction), "Expected a QAction, got %s" % type(clicked_action)
        act_name = clicked_action.text()
        sel_obj_list = self.collection.get_selected()

        if not sel_obj_list:
            return

        # a default value, I just chose this one
        alpha_level = 'BF'
        for sel_obj in sel_obj_list:
            if sel_obj.kind == 'excellon':
                alpha_level = self.defaults["excellon_plot_fill"][7:]
            elif sel_obj.kind == 'gerber':
                alpha_level = self.defaults["gerber_plot_fill"][7:]
            elif sel_obj.kind == 'geometry':
                alpha_level = 'FF'
            else:
                log.debug(
                    "App.on_set_color_action_triggered() --> Default alpfa for this object type not supported yet")
                continue
            sel_obj.alpha_level = alpha_level

        if act_name == _('Red'):
            new_color = '#FF0000' + alpha_level
        if act_name == _('Blue'):
            new_color = '#0000FF' + alpha_level

        if act_name == _('Yellow'):
            new_color = '#FFDF00' + alpha_level
        if act_name == _('Green'):
            new_color = '#00FF00' + alpha_level
        if act_name == _('Purple'):
            new_color = '#FF00FF' + alpha_level
        if act_name == _('Brown'):
            new_color = '#A52A2A' + alpha_level
        if act_name == _('White'):
            new_color = '#FFFFFF' + alpha_level
        if act_name == _('Black'):
            new_color = '#000000' + alpha_level

        if act_name == _('Custom'):
            new_color = QtGui.QColor(self.defaults['gerber_plot_fill'][:7])
            c_dialog = QtWidgets.QColorDialog()
            plot_fill_color = c_dialog.getColor(initial=new_color)

            if plot_fill_color.isValid() is False:
                return

            new_color = str(plot_fill_color.name()) + alpha_level

        if act_name == _("Default"):
            for sel_obj in sel_obj_list:
                if sel_obj.kind == 'excellon':
                    new_color = self.defaults['excellon_plot_fill']
                    new_line_color = self.defaults['excellon_plot_line']
                elif sel_obj.kind == 'gerber':
                    new_color = self.defaults['gerber_plot_fill']
                    new_line_color = self.defaults['gerber_plot_line']
                elif sel_obj.kind == 'geometry':
                    new_color = self.defaults['geometry_plot_line']
                    new_line_color = self.defaults['geometry_plot_line']
                else:
                    log.debug(
                        "App.on_set_color_action_triggered() --> Default color for this object type not supported yet")
                    continue

                sel_obj.fill_color = new_color
                sel_obj.outline_color = new_line_color

                sel_obj.shapes.redraw(
                    update_colors=(new_color, new_line_color)
                )
            return

        if act_name == _("Opacity"):
            alpha_level, ok_button = QtWidgets.QInputDialog.getInt(
                self.ui, _("Set alpha level ..."), '%s:' % _("Value"), min=0, max=255, step=1, value=191)

            if ok_button:

                alpha_str = str(hex(alpha_level)[2:]) if alpha_level != 0 else '00'
                for sel_obj in sel_obj_list:
                    sel_obj.fill_color = sel_obj.fill_color[:-2] + alpha_str

                    sel_obj.shapes.redraw(
                        update_colors=(sel_obj.fill_color, sel_obj.outline_color)
                    )

            return

        new_line_color = color_variant(new_color[:7], 0.7)
        if act_name == _("White"):
            new_line_color = color_variant("#dedede", 0.7)

        for sel_obj in sel_obj_list:
            sel_obj.fill_color = new_color
            sel_obj.outline_color = new_line_color

            sel_obj.shapes.redraw(
                update_colors=(new_color, new_line_color)
            )

    def generate_cnc_job(self, objects):
        """
        Slot that will be called by clicking an entry in the contextual menu generated in the Project Tab tree

        :param objects:     Selected objects in the Project Tab
        :return:
        """
        self.defaults.report_usage("generate_cnc_job()")

        # for obj in objects:
        #     obj.generatecncjob()
        for obj in objects:
            obj.on_generatecnc_button_click()

    def save_project(self, filename, quit_action=False, silent=False, from_tcl=False):
        """
        Saves the current project to the specified file.

        :param filename:        Name of the file in which to save.
        :type filename:         str
        :param quit_action:     if the project saving will be followed by an app quit; boolean
        :param silent:          if True will not display status messages
        :param from_tcl         True is run from Tcl Shell
        :return:                None
        """
        self.log.debug("save_project()")
        self.save_in_progress = True

        with self.proc_container.new(_("Saving FlatCAM Project")):
            # Capture the latest changes
            # Current object
            try:
                current_object = self.collection.get_active()
                if current_object:
                    current_object.read_form()
            except Exception as e:
                self.log.debug("save_project() --> There was no active object. Skipping read_form. %s" % str(e))
                pass

            # Serialize the whole project
            d = {"objs": [obj.to_dict() for obj in self.collection.get_list()],
                 "options": self.options,
                 "version": self.version}

            if self.defaults["global_save_compressed"] is True:
                with lzma.open(filename, "w", preset=int(self.defaults['global_compression_level'])) as f:
                    g = json.dumps(d, default=to_dict, indent=2, sort_keys=True).encode('utf-8')
                    # # Write
                    f.write(g)
                self.inform.emit('[success] %s: %s' % (_("Project saved to"), filename))
            else:
                # Open file
                try:
                    f = open(filename, 'w')
                except IOError:
                    App.log.error("Failed to open file for saving: %s", filename)
                    self.inform.emit('[ERROR_NOTCL] %s' % _("The object is used by another application."))
                    return

                # Write
                json.dump(d, f, default=to_dict, indent=2, sort_keys=True)
                f.close()

                # verification of the saved project
                # Open and parse
                try:
                    saved_f = open(filename, 'r')
                except IOError:
                    if silent is False:
                        self.inform.emit('[ERROR_NOTCL] %s: %s %s' %
                                         (_("Failed to verify project file"), filename, _("Retry to save it.")))
                    return

                try:
                    saved_d = json.load(saved_f, object_hook=dict2obj)
                except Exception:
                    if silent is False:
                        self.inform.emit('[ERROR_NOTCL] %s: %s %s' %
                                         (_("Failed to parse saved project file"), filename, _("Retry to save it.")))
                    f.close()
                    return
                saved_f.close()

                if silent is False:
                    if 'version' in saved_d:
                        self.inform.emit('[success] %s: %s' % (_("Project saved to"), filename))
                    else:
                        self.inform.emit('[ERROR_NOTCL] %s: %s %s' %
                                         (_("Failed to parse saved project file"), filename, _("Retry to save it.")))

                tb_settings = QSettings("Open Source", "FlatCAM")
                lock_state = self.ui.lock_action.isChecked()
                tb_settings.setValue('toolbar_lock', lock_state)

                # This will write the setting to the platform specific storage.
                del tb_settings

            # if quit:
            # t = threading.Thread(target=lambda: self.check_project_file_size(1, filename=filename))
            # t.start()
            self.start_delayed_quit(delay=500, filename=filename, should_quit=quit_action)

    def start_delayed_quit(self, delay, filename, should_quit=None):
        """

        :param delay:           period of checking if project file size is more than zero; in seconds
        :param filename:        the name of the project file to be checked periodically for size more than zero
        :param should_quit:     if the task finished will be followed by an app quit; boolean
        :return:
        """
        to_quit = should_quit
        self.save_timer = QtCore.QTimer()
        self.save_timer.setInterval(delay)
        self.save_timer.timeout.connect(lambda: self.check_project_file_size(filename=filename, should_quit=to_quit))
        self.save_timer.start()

    def check_project_file_size(self, filename, should_quit=None):
        """

        :param filename:        the name of the project file to be checked periodically for size more than zero
        :param should_quit:     will quit the app if True; boolean
        :return:
        """

        try:
            if os.stat(filename).st_size > 0:
                self.save_in_progress = False
                self.save_timer.stop()
                if should_quit:
                    self.app_quit.emit()
        except Exception:
            traceback.print_exc()

    def save_project_auto(self):
        """
        Called periodically to save the project.
        It will save if there is no block on the save, if the project was saved at least once and if there is no save in
        # progress.

        :return:
        """

        if self.block_autosave is False and self.should_we_save is True and self.save_in_progress is False:
            self.on_file_saveproject()

    def save_project_auto_update(self):
        """
        Update the auto save time interval value.
        :return:
        """
        log.debug("App.save_project_auto_update() --> updated the interval timeout.")
        try:
            if self.autosave_timer.isActive():
                self.autosave_timer.stop()
        except Exception:
            pass

        if self.defaults['global_autosave'] is True:
            self.autosave_timer.setInterval(int(self.defaults['global_autosave_timeout']))
            self.autosave_timer.start()

    def on_options_app2project(self):
        """
        Callback for Options->Transfer Options->App=>Project. Copies options
        from application defaults to project defaults.

        :return:    None
        """

        self.defaults.report_usage("on_options_app2project")

        self.preferencesUiManager.defaults_read_form()
        self.options.update(self.defaults)

    def toggle_shell(self):
        """
        Toggle shell: if is visible close it, if it is closed then open it
        :return: None
        """

        self.defaults.report_usage("toggle_shell()")

        if self.ui.shell_dock.isVisible():
            self.ui.shell_dock.hide()
            self.plotcanvas.native.setFocus()
        else:
            self.ui.shell_dock.show()

            # I want to take the focus and give it to the Tcl Shell when the Tcl Shell is run
            # self.shell._edit.setFocus()
            QtCore.QTimer.singleShot(0, lambda: self.ui.shell_dock.widget()._edit.setFocus())

            # HACK - simulate a mouse click - alternative
            # no_km = QtCore.Qt.KeyboardModifier(QtCore.Qt.NoModifier)    # no KB modifier
            # pos = QtCore.QPoint((self.shell._edit.width() - 40), (self.shell._edit.height() - 2))
            # e = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton,
            #                       no_km)
            # QtWidgets.qApp.sendEvent(self.shell._edit, e)
            # f = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton,
            #                       no_km)
            # QtWidgets.qApp.sendEvent(self.shell._edit, f)

    def shell_message(self, msg, show=False, error=False, warning=False, success=False, selected=False):
        """
        Shows a message on the FlatCAM Shell

        :param msg: Message to display.
        :param show: Opens the shell.
        :param error: Shows the message as an error.
        :param warning: Shows the message as an warning.
        :param success: Shows the message as an success.
        :param selected: Indicate that something was selected on canvas
        :return: None
        """
        if show:
            self.ui.shell_dock.show()
        try:
            if error:
                self.shell.append_error(msg + "\n")
            elif warning:
                self.shell.append_warning(msg + "\n")
            elif success:
                self.shell.append_success(msg + "\n")
            elif selected:
                self.shell.append_selected(msg + "\n")
            else:
                self.shell.append_output(msg + "\n")
        except AttributeError:
            log.debug("shell_message() is called before Shell Class is instantiated. The message is: %s", str(msg))


class ArgsThread(QtCore.QObject):
    open_signal = pyqtSignal(list)
    start = pyqtSignal()
    stop = pyqtSignal()

    if sys.platform == 'win32':
        address = (r'\\.\pipe\NPtest', 'AF_PIPE')
    else:
        address = ('/tmp/testipc', 'AF_UNIX')

    def __init__(self):
        super(ArgsThread, self).__init__()
        self.listener = None
        self.thread_exit = False

        self.start.connect(self.run)
        self.stop.connect(self.close_listener)

    def my_loop(self, address):
        try:
            self.listener = Listener(*address)
            while self.thread_exit is False:
                conn = self.listener.accept()
                self.serve(conn)
        except socket.error:
            try:
                conn = Client(*address)
                conn.send(sys.argv)
                conn.send('close')
                # close the current instance only if there are args
                if len(sys.argv) > 1:
                    try:
                        self.listener.close()
                    except Exception:
                        pass
                    sys.exit()
            except ConnectionRefusedError:
                if sys.platform == 'win32':
                    pass
                else:
                    os.system('rm /tmp/testipc')
                    self.listener = Listener(*address)
                    while True:
                        conn = self.listener.accept()
                        self.serve(conn)

    def serve(self, conn):
        while self.thread_exit is False:
            msg = conn.recv()
            if msg == 'close':
                break
            self.open_signal.emit(msg)
        conn.close()

    # the decorator is a must; without it this technique will not work unless the start signal is connected
    # in the main thread (where this class is instantiated) after the instance is moved o the new thread
    @pyqtSlot()
    def run(self):
        self.my_loop(self.address)

    @pyqtSlot()
    def close_listener(self):
        self.thread_exit = True
        self.listener.close()

# end of file
