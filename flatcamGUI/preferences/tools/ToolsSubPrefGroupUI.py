from PyQt5 import QtWidgets
from PyQt5.QtCore import QSettings

from flatcamGUI.GUIElements import FCCheckBox
from flatcamGUI.preferences.OptionsGroupUI import OptionsGroupUI

import gettext
import FlatCAMTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

settings = QSettings("Open Source", "FlatCAM")
if settings.contains("machinist"):
    machinist_setting = settings.value('machinist', type=int)
else:
    machinist_setting = 0


class ToolsSubPrefGroupUI(OptionsGroupUI):
    def __init__(self, decimals=4, parent=None):

        super(ToolsSubPrefGroupUI, self).__init__(self, parent=parent)

        self.setTitle(str(_("Substractor Tool Options")))
        self.decimals = decimals

        # ## Subtractor Tool Parameters
        self.sublabel = QtWidgets.QLabel("<b>%s:</b>" % _("Parameters"))
        self.sublabel.setToolTip(
            _("A tool to substract one Gerber or Geometry object\n"
              "from another of the same type.")
        )
        self.layout.addWidget(self.sublabel)

        self.close_paths_cb = FCCheckBox(_("Close paths"))
        self.close_paths_cb.setToolTip(_("Checking this will close the paths cut by the Geometry substractor object."))
        self.layout.addWidget(self.close_paths_cb)

        self.layout.addStretch()
