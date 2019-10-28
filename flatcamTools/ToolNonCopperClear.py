# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Modified by: Marius Adrian Stanciu (c)              #
# Date: 3/10/2019                                          #
# MIT Licence                                              #
# ##########################################################

from PyQt5 import QtWidgets, QtCore, QtGui
from FlatCAMTool import FlatCAMTool
from flatcamGUI.GUIElements import FCCheckBox, FCDoubleSpinner, RadioSet, FCTable, FCInputDialog
from flatcamParsers.ParseGerber import Gerber
from FlatCAMObj import FlatCAMGeometry, FlatCAMGerber
import FlatCAMApp

from copy import deepcopy

import numpy as np
import math
from shapely.geometry import base
from shapely.ops import cascaded_union
from shapely.geometry import MultiPolygon, Polygon, MultiLineString, LineString, LinearRing

import logging
import traceback
import gettext
import FlatCAMTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class NonCopperClear(FlatCAMTool, Gerber):

    toolName = _("Non-Copper Clearing")

    def __init__(self, app):
        self.app = app
        self.decimals = 4

        FlatCAMTool.__init__(self, app)
        Gerber.__init__(self, steps_per_circle=self.app.defaults["gerber_circle_steps"])

        self.tools_frame = QtWidgets.QFrame()
        self.tools_frame.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.tools_frame)
        self.tools_box = QtWidgets.QVBoxLayout()
        self.tools_box.setContentsMargins(0, 0, 0, 0)
        self.tools_frame.setLayout(self.tools_box)

        # ## Title
        title_label = QtWidgets.QLabel("%s" % self.toolName)
        title_label.setStyleSheet("""
                        QLabel
                        {
                            font-size: 16px;
                            font-weight: bold;
                        }
                        """)
        self.tools_box.addWidget(title_label)

        # ## Form Layout
        form_layout = QtWidgets.QFormLayout()
        self.tools_box.addLayout(form_layout)

        # ################################################
        # ##### Type of object to be copper cleaned ######
        # ################################################
        self.type_obj_combo = QtWidgets.QComboBox()
        self.type_obj_combo.addItem("Gerber")
        self.type_obj_combo.addItem("Excellon")
        self.type_obj_combo.addItem("Geometry")

        # we get rid of item1 ("Excellon") as it is not suitable
        self.type_obj_combo.view().setRowHidden(1, True)
        self.type_obj_combo.setItemIcon(0, QtGui.QIcon("share/flatcam_icon16.png"))
        self.type_obj_combo.setItemIcon(2, QtGui.QIcon("share/geometry16.png"))

        self.type_obj_combo_label = QtWidgets.QLabel('%s:' % _("Obj Type"))
        self.type_obj_combo_label.setToolTip(
            _("Specify the type of object to be cleared of excess copper.\n"
              "It can be of type: Gerber or Geometry.\n"
              "What is selected here will dictate the kind\n"
              "of objects that will populate the 'Object' combobox.")
        )
        self.type_obj_combo_label.setMinimumWidth(60)
        form_layout.addRow(self.type_obj_combo_label, self.type_obj_combo)

        # ################################################
        # ##### The object to be copper cleaned ##########
        # ################################################
        self.object_combo = QtWidgets.QComboBox()
        self.object_combo.setModel(self.app.collection)
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.object_combo.setCurrentIndex(1)

        self.object_label = QtWidgets.QLabel('%s:' % _("Object"))
        self.object_label.setToolTip(_("Object to be cleared of excess copper."))

        form_layout.addRow(self.object_label, self.object_combo)

        e_lab_0 = QtWidgets.QLabel('')
        form_layout.addRow(e_lab_0)

        # ### Tools ## ##
        self.tools_table_label = QtWidgets.QLabel('<b>%s</b>' % _('Tools Table'))
        self.tools_table_label.setToolTip(
            _("Tools pool from which the algorithm\n"
              "will pick the ones used for copper clearing.")
        )
        self.tools_box.addWidget(self.tools_table_label)

        self.tools_table = FCTable()
        self.tools_box.addWidget(self.tools_table)

        self.tools_table.setColumnCount(5)
        self.tools_table.setHorizontalHeaderLabels(['#', _('Diameter'), _('TT'), '', _("Operation")])
        self.tools_table.setColumnHidden(3, True)
        self.tools_table.setSortingEnabled(False)
        # self.tools_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.tools_table.horizontalHeaderItem(0).setToolTip(
            _("This is the Tool Number.\n"
              "Non copper clearing will start with the tool with the biggest \n"
              "diameter, continuing until there are no more tools.\n"
              "Only tools that create NCC clearing geometry will still be present\n"
              "in the resulting geometry. This is because with some tools\n"
              "this function will not be able to create painting geometry.")
            )
        self.tools_table.horizontalHeaderItem(1).setToolTip(
            _("Tool Diameter. It's value (in current FlatCAM units)\n"
              "is the cut width into the material."))

        self.tools_table.horizontalHeaderItem(2).setToolTip(
            _("The Tool Type (TT) can be:\n"
              "- Circular with 1 ... 4 teeth -> it is informative only. Being circular,\n"
              "the cut width in material is exactly the tool diameter.\n"
              "- Ball -> informative only and make reference to the Ball type endmill.\n"
              "- V-Shape -> it will disable de Z-Cut parameter in the resulting geometry UI form\n"
              "and enable two additional UI form fields in the resulting geometry: V-Tip Dia and\n"
              "V-Tip Angle. Adjusting those two values will adjust the Z-Cut parameter such\n"
              "as the cut width into material will be equal with the value in the Tool Diameter\n"
              "column of this table.\n"
              "Choosing the 'V-Shape' Tool Type automatically will select the Operation Type\n"
              "in the resulting geometry as Isolation."))

        self.tools_table.horizontalHeaderItem(4).setToolTip(
            _("The 'Operation' can be:\n"
              "- Isolation -> will ensure that the non-copper clearing is always complete.\n"
              "If it's not successful then the non-copper clearing will fail, too.\n"
              "- Clear -> the regular non-copper clearing."))

        form = QtWidgets.QFormLayout()
        self.tools_box.addLayout(form)

        # Milling Type Radio Button
        self.milling_type_label = QtWidgets.QLabel('%s:' % _('Milling Type'))
        self.milling_type_label.setToolTip(
            _("Milling type when the selected tool is of type: 'iso_op':\n"
              "- climb / best for precision milling and to reduce tool usage\n"
              "- conventional / useful when there is no backlash compensation")
        )

        self.milling_type_radio = RadioSet([{'label': _('Climb'), 'value': 'cl'},
                                            {'label': _('Conv.'), 'value': 'cv'}])
        self.milling_type_radio.setToolTip(
            _("Milling type when the selected tool is of type: 'iso_op':\n"
              "- climb / best for precision milling and to reduce tool usage\n"
              "- conventional / useful when there is no backlash compensation")
        )

        # Tool order
        self.ncc_order_label = QtWidgets.QLabel('<b>%s:</b>' % _('Tool order'))
        self.ncc_order_label.setToolTip(_("This set the way that the tools in the tools table are used.\n"
                                          "'No' --> means that the used order is the one in the tool table\n"
                                          "'Forward' --> means that the tools will be ordered from small to big\n"
                                          "'Reverse' --> menas that the tools will ordered from big to small\n\n"
                                          "WARNING: using rest machining will automatically set the order\n"
                                          "in reverse and disable this control."))

        self.ncc_order_radio = RadioSet([{'label': _('No'), 'value': 'no'},
                                         {'label': _('Forward'), 'value': 'fwd'},
                                         {'label': _('Reverse'), 'value': 'rev'}])
        self.ncc_order_radio.setToolTip(_("This set the way that the tools in the tools table are used.\n"
                                          "'No' --> means that the used order is the one in the tool table\n"
                                          "'Forward' --> means that the tools will be ordered from small to big\n"
                                          "'Reverse' --> menas that the tools will ordered from big to small\n\n"
                                          "WARNING: using rest machining will automatically set the order\n"
                                          "in reverse and disable this control."))

        form.addRow(self.milling_type_label, self.milling_type_radio)
        form.addRow(self.ncc_order_label, self.ncc_order_radio)
        form.addRow(QtWidgets.QLabel(''))

        self.milling_type_label.hide()
        self.milling_type_radio.hide()

        # #############################################################
        # ############### Tool selection ##############################
        # #############################################################
        self.tool_sel_label = QtWidgets.QLabel('<b>%s</b>' % _("Tool Selection"))
        form.addRow(self.tool_sel_label)

        # Tool Type Radio Button
        self.tool_type_label = QtWidgets.QLabel('%s:' % _('Tool Type'))
        self.tool_type_label.setToolTip(
            _("Default tool type:\n"
              "- 'V-shape'\n"
              "- Circular")
        )

        self.tool_type_radio = RadioSet([{'label': _('V-shape'), 'value': 'V'},
                                         {'label': _('Circular'), 'value': 'C1'}])
        self.tool_type_radio.setToolTip(
            _("Default tool type:\n"
              "- 'V-shape'\n"
              "- Circular")
        )
        form.addRow(self.tool_type_label, self.tool_type_radio)

        # ### Add a new Tool ####
        self.addtool_entry_lbl = QtWidgets.QLabel('<b>%s:</b>' % _('Tool Dia'))
        self.addtool_entry_lbl.setToolTip(
            _("Diameter for the new tool to add in the Tool Table")
        )
        self.addtool_entry = FCDoubleSpinner()
        self.addtool_entry.set_precision(self.decimals)

        form.addRow(self.addtool_entry_lbl, self.addtool_entry)

        # Tip Dia
        self.tipdialabel = QtWidgets.QLabel('%s:' % _('V-Tip Dia'))
        self.tipdialabel.setToolTip(
            _("The tip diameter for V-Shape Tool"))
        self.tipdia_entry = FCDoubleSpinner()
        self.tipdia_entry.set_precision(self.decimals)
        self.tipdia_entry.setSingleStep(0.1)

        form.addRow(self.tipdialabel, self.tipdia_entry)

        # Tip Angle
        self.tipanglelabel = QtWidgets.QLabel('%s:' % _('V-Tip Angle'))
        self.tipanglelabel.setToolTip(
            _("The tip angle for V-Shape Tool.\n"
              "In degree."))
        self.tipangle_entry = FCDoubleSpinner()
        self.tipangle_entry.set_precision(self.decimals)
        self.tipangle_entry.setSingleStep(5)

        form.addRow(self.tipanglelabel, self.tipangle_entry)

        grid2 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid2)

        self.addtool_btn = QtWidgets.QPushButton(_('Add'))
        self.addtool_btn.setToolTip(
            _("Add a new tool to the Tool Table\n"
              "with the diameter specified above.")
        )

        # self.copytool_btn = QtWidgets.QPushButton('Copy')
        # self.copytool_btn.setToolTip(
        #     "Copy a selection of tools in the Tool Table\n"
        #     "by first selecting a row in the Tool Table."
        # )

        self.deltool_btn = QtWidgets.QPushButton(_('Delete'))
        self.deltool_btn.setToolTip(
            _("Delete a selection of tools in the Tool Table\n"
              "by first selecting a row(s) in the Tool Table.")
        )

        grid2.addWidget(self.addtool_btn, 0, 0)
        grid2.addWidget(self.deltool_btn, 0, 2)

        self.empty_label_0 = QtWidgets.QLabel('')
        self.tools_box.addWidget(self.empty_label_0)

        grid3 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid3)
        grid3.setColumnStretch(0, 0)
        grid3.setColumnStretch(1, 1)

        e_lab_1 = QtWidgets.QLabel('<b>%s:</b>' % _("Parameters"))
        grid3.addWidget(e_lab_1, 0, 0)

        # Cut Z entry
        cutzlabel = QtWidgets.QLabel('%s:' % _('Cut Z'))
        cutzlabel.setToolTip(
           _("Depth of cut into material. Negative value.\n"
             "In FlatCAM units.")
        )
        self.cutz_entry = FCDoubleSpinner()
        self.cutz_entry.set_precision(self.decimals)
        self.cutz_entry.set_range(-99999, -0.00000000000001)

        self.cutz_entry.setToolTip(
           _("Depth of cut into material. Negative value.\n"
             "In FlatCAM units.")
        )
        grid3.addWidget(cutzlabel, 1, 0)
        grid3.addWidget(self.cutz_entry, 1, 1)

        # Overlap Entry
        nccoverlabel = QtWidgets.QLabel('%s:' % _('Overlap Rate'))
        nccoverlabel.setToolTip(
            _("How much (fraction) of the tool width to overlap each tool pass.\n"
              "Example:\n"
              "A value here of 0.25 means 25%% from the tool diameter found above.\n\n"
              "Adjust the value starting with lower values\n"
              "and increasing it if areas that should be cleared are still \n"
              "not cleared.\n"
              "Lower values = faster processing, faster execution on PCB.\n"
              "Higher values = slow processing and slow execution on CNC\n"
              "due of too many paths.")
        )
        self.ncc_overlap_entry = FCDoubleSpinner()
        self.ncc_overlap_entry.set_precision(3)
        self.ncc_overlap_entry.setWrapping(True)
        self.ncc_overlap_entry.setRange(0.000, 0.999)
        self.ncc_overlap_entry.setSingleStep(0.1)
        grid3.addWidget(nccoverlabel, 2, 0)
        grid3.addWidget(self.ncc_overlap_entry, 2, 1)

        nccmarginlabel = QtWidgets.QLabel('%s:' % _('Margin'))
        nccmarginlabel.setToolTip(
            _("Bounding box margin.")
        )
        grid3.addWidget(nccmarginlabel, 3, 0)
        self.ncc_margin_entry = FCDoubleSpinner()
        self.ncc_margin_entry.set_precision(self.decimals)

        grid3.addWidget(self.ncc_margin_entry, 3, 1)

        # Method
        methodlabel = QtWidgets.QLabel('%s:' % _('Method'))
        methodlabel.setToolTip(
            _("Algorithm for non-copper clearing:<BR>"
              "<B>Standard</B>: Fixed step inwards.<BR>"
              "<B>Seed-based</B>: Outwards from seed.<BR>"
              "<B>Line-based</B>: Parallel lines.")
        )
        grid3.addWidget(methodlabel, 4, 0)
        self.ncc_method_radio = RadioSet([
            {"label": _("Standard"), "value": "standard"},
            {"label": _("Seed-based"), "value": "seed"},
            {"label": _("Straight lines"), "value": "lines"}
        ], orientation='vertical', stretch=False)
        grid3.addWidget(self.ncc_method_radio, 4, 1)

        # Connect lines
        pathconnectlabel = QtWidgets.QLabel('%s:' % _("Connect"))
        pathconnectlabel.setToolTip(
            _("Draw lines between resulting\n"
              "segments to minimize tool lifts.")
        )
        grid3.addWidget(pathconnectlabel, 5, 0)
        self.ncc_connect_cb = FCCheckBox()
        grid3.addWidget(self.ncc_connect_cb, 5, 1)

        contourlabel = QtWidgets.QLabel('%s:' % _("Contour"))
        contourlabel.setToolTip(
            _("Cut around the perimeter of the polygon\n"
              "to trim rough edges.")
        )
        grid3.addWidget(contourlabel, 6, 0)
        self.ncc_contour_cb = FCCheckBox()
        grid3.addWidget(self.ncc_contour_cb, 6, 1)

        restlabel = QtWidgets.QLabel('%s:' % _("Rest M."))
        restlabel.setToolTip(
            _("If checked, use 'rest machining'.\n"
              "Basically it will clear copper outside PCB features,\n"
              "using the biggest tool and continue with the next tools,\n"
              "from bigger to smaller, to clear areas of copper that\n"
              "could not be cleared by previous tool, until there is\n"
              "no more copper to clear or there are no more tools.\n"
              "If not checked, use the standard algorithm.")
        )
        grid3.addWidget(restlabel, 7, 0)
        self.ncc_rest_cb = FCCheckBox()
        grid3.addWidget(self.ncc_rest_cb, 7, 1)

        # ## NCC Offset choice
        self.ncc_offset_choice_label = QtWidgets.QLabel('%s:' % _("Offset"))
        self.ncc_offset_choice_label.setToolTip(
            _("If used, it will add an offset to the copper features.\n"
              "The copper clearing will finish to a distance\n"
              "from the copper features.\n"
              "The value can be between 0 and 10 FlatCAM units.")
        )
        grid3.addWidget(self.ncc_offset_choice_label, 8, 0)
        self.ncc_choice_offset_cb = FCCheckBox()
        grid3.addWidget(self.ncc_choice_offset_cb, 8, 1)

        # ## NCC Offset value
        self.ncc_offset_label = QtWidgets.QLabel('%s:' % _("Offset value"))
        self.ncc_offset_label.setToolTip(
            _("If used, it will add an offset to the copper features.\n"
              "The copper clearing will finish to a distance\n"
              "from the copper features.\n"
              "The value can be between 0 and 10 FlatCAM units.")
        )
        grid3.addWidget(self.ncc_offset_label, 9, 0)
        self.ncc_offset_spinner = FCDoubleSpinner()
        self.ncc_offset_spinner.set_range(0.00, 10.00)
        self.ncc_offset_spinner.set_precision(4)
        self.ncc_offset_spinner.setWrapping(True)

        units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value().upper()
        if units == 'MM':
            self.ncc_offset_spinner.setSingleStep(0.1)
        else:
            self.ncc_offset_spinner.setSingleStep(0.01)

        grid3.addWidget(self.ncc_offset_spinner, 9, 1)

        self.ncc_offset_label.hide()
        self.ncc_offset_spinner.hide()

        # ## Reference
        self.reference_radio = RadioSet([
            {'label': _('Itself'), 'value': 'itself'},
            {"label": _("Area Selection"), "value": "area"},
            {'label':  _("Reference Object"), 'value': 'box'}
        ], orientation='vertical', stretch=False)
        self.reference_label = QtWidgets.QLabel(_("Reference:"))
        self.reference_label.setToolTip(
            _("- 'Itself' - the non copper clearing extent is based on the object that is copper cleared.\n "
              "- 'Area Selection' - left mouse click to start selection of the area to be painted.\n"
              "- 'Reference Object' - will do non copper clearing within the area specified by another object.")
        )
        grid3.addWidget(self.reference_label, 10, 0)
        grid3.addWidget(self.reference_radio, 10, 1)

        form1 = QtWidgets.QFormLayout()
        self.tools_box.addLayout(form1)

        self.box_combo_type_label = QtWidgets.QLabel('%s:' % _("Ref. Type"))
        self.box_combo_type_label.setToolTip(
            _("The type of FlatCAM object to be used as non copper clearing reference.\n"
              "It can be Gerber, Excellon or Geometry.")
        )
        self.box_combo_type = QtWidgets.QComboBox()
        self.box_combo_type.addItem(_("Reference Gerber"))
        self.box_combo_type.addItem(_("Reference Excellon"))
        self.box_combo_type.addItem(_("Reference Geometry"))
        form1.addRow(self.box_combo_type_label, self.box_combo_type)

        self.box_combo_label = QtWidgets.QLabel('%s:' % _("Ref. Object"))
        self.box_combo_label.setToolTip(
            _("The FlatCAM object to be used as non copper clearing reference.")
        )
        self.box_combo = QtWidgets.QComboBox()
        self.box_combo.setModel(self.app.collection)
        self.box_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.box_combo.setCurrentIndex(1)
        form1.addRow(self.box_combo_label, self.box_combo)

        self.box_combo.hide()
        self.box_combo_label.hide()
        self.box_combo_type.hide()
        self.box_combo_type_label.hide()

        self.generate_ncc_button = QtWidgets.QPushButton(_('Generate Geometry'))
        self.generate_ncc_button.setToolTip(
            _("Create the Geometry Object\n"
              "for non-copper routing.")
        )
        self.tools_box.addWidget(self.generate_ncc_button)
        self.tools_box.addStretch()
        # ############################ FINSIHED GUI ###################################
        # #############################################################################

        # #############################################################################
        # ###################### Setup CONTEXT MENU ###################################
        # #############################################################################
        self.tools_table.setupContextMenu()
        self.tools_table.addContextMenu(
            "Add", self.on_add_tool_by_key, icon=QtGui.QIcon("share/plus16.png"))
        self.tools_table.addContextMenu(
            "Delete", lambda:
            self.on_tool_delete(rows_to_delete=None, all_tools=None), icon=QtGui.QIcon("share/delete32.png"))

        # #############################################################################
        # ########################## VARIABLES ########################################
        # #############################################################################
        self.units = ''
        self.ncc_tools = dict()
        self.tooluid = 0

        # store here the default data for Geometry Data
        self.default_data = dict()

        self.obj_name = ""
        self.ncc_obj = None

        self.sel_rect = list()

        self.bound_obj_name = ""
        self.bound_obj = None

        self.ncc_dia_list = list()
        self.iso_dia_list = list()
        self.has_offset = None
        self.o_name = None
        self.overlap = None
        self.connect = None
        self.contour = None
        self.rest = None

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False

        self.mm = None
        self.mr = None

        # store here solid_geometry when there are tool with isolation job
        self.solid_geometry = list()

        self.select_method = None
        self.tool_type_item_options = list()

        self.grb_circle_steps = int(self.app.defaults["gerber_circle_steps"])

        # #############################################################################
        # ############################ SGINALS ########################################
        # #############################################################################
        self.addtool_btn.clicked.connect(self.on_tool_add)
        self.addtool_entry.returnPressed.connect(self.on_tool_add)
        self.deltool_btn.clicked.connect(self.on_tool_delete)
        self.generate_ncc_button.clicked.connect(self.on_ncc_click)

        self.box_combo_type.currentIndexChanged.connect(self.on_combo_box_type)
        self.reference_radio.group_toggle_fn = self.on_toggle_reference
        self.ncc_choice_offset_cb.stateChanged.connect(self.on_offset_choice)
        self.ncc_rest_cb.stateChanged.connect(self.on_rest_machining_check)
        self.ncc_order_radio.activated_custom[str].connect(self.on_order_changed)

        self.type_obj_combo.currentIndexChanged.connect(self.on_type_obj_index_changed)

    def on_type_obj_index_changed(self, index):
        obj_type = self.type_obj_combo.currentIndex()
        self.object_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.object_combo.setCurrentIndex(0)

    def on_add_tool_by_key(self):
        tool_add_popup = FCInputDialog(title='%s...' % _("New Tool"),
                                       text='%s:' % _('Enter a Tool Diameter'),
                                       min=0.0000, max=99.9999, decimals=4)
        tool_add_popup.setWindowIcon(QtGui.QIcon('share/letter_t_32.png'))

        val, ok = tool_add_popup.get_value()
        if ok:
            if float(val) == 0:
                self.app.inform.emit('[WARNING_NOTCL] %s' %
                                     _("Please enter a tool diameter with non-zero value, in Float format."))
                return
            self.on_tool_add(dia=float(val))
        else:
            self.app.inform.emit('[WARNING_NOTCL] %s...' % _("Adding Tool cancelled"))

    def install(self, icon=None, separator=None, **kwargs):
        FlatCAMTool.install(self, icon, separator, shortcut='ALT+N', **kwargs)

    def run(self, toggle=True):
        self.app.report_usage("ToolNonCopperClear()")

        if toggle:
            # if the splitter is hidden, display it, else hide it but only if the current widget is the same
            if self.app.ui.splitter.sizes()[0] == 0:
                self.app.ui.splitter.setSizes([1, 1])
            else:
                try:
                    if self.app.ui.tool_scroll_area.widget().objectName() == self.toolName:
                        # if tab is populated with the tool but it does not have the focus, focus on it
                        if not self.app.ui.notebook.currentWidget() is self.app.ui.tool_tab:
                            # focus on Tool Tab
                            self.app.ui.notebook.setCurrentWidget(self.app.ui.tool_tab)
                        else:
                            self.app.ui.splitter.setSizes([0, 1])
                except AttributeError:
                    pass
        else:
            if self.app.ui.splitter.sizes()[0] == 0:
                self.app.ui.splitter.setSizes([1, 1])

        FlatCAMTool.run(self)
        self.set_tool_ui()

        # reset those objects on a new run
        self.ncc_obj = None
        self.bound_obj = None
        self.obj_name = ''
        self.bound_obj_name = ''

        self.build_ui()
        self.app.ui.notebook.setTabText(2, _("NCC Tool"))

    def set_tool_ui(self):
        self.units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value().upper()

        if self.units == "IN":
            self.decimals = 4
        else:
            self.decimals = 2

        self.tools_frame.show()

        self.ncc_order_radio.set_value(self.app.defaults["tools_nccorder"])
        self.ncc_overlap_entry.set_value(self.app.defaults["tools_nccoverlap"])
        self.ncc_margin_entry.set_value(self.app.defaults["tools_nccmargin"])
        self.ncc_method_radio.set_value(self.app.defaults["tools_nccmethod"])
        self.ncc_connect_cb.set_value(self.app.defaults["tools_nccconnect"])
        self.ncc_contour_cb.set_value(self.app.defaults["tools_ncccontour"])
        self.ncc_rest_cb.set_value(self.app.defaults["tools_nccrest"])
        self.reference_radio.set_value(self.app.defaults["tools_nccref"])
        self.milling_type_radio.set_value(self.app.defaults["tools_nccmilling_type"])
        self.cutz_entry.set_value(self.app.defaults["tools_ncccutz"])
        self.tool_type_radio.set_value(self.app.defaults["tools_ncctool_type"])
        self.tipdia_entry.set_value(self.app.defaults["tools_ncctipdia"])
        self.tipangle_entry.set_value(self.app.defaults["tools_ncctipangle"])

        self.on_tool_type(val=self.tool_type_radio.get_value())

        # init the working variables
        self.default_data.clear()
        self.default_data.update({
            "name": '_ncc',
            "plot": self.app.defaults["geometry_plot"],
            "cutz": float(self.cutz_entry.get_value()),
            "vtipdia": float(self.tipdia_entry.get_value()),
            "vtipangle": float(self.tipangle_entry.get_value()),
            "travelz": self.app.defaults["geometry_travelz"],
            "feedrate": self.app.defaults["geometry_feedrate"],
            "feedrate_z": self.app.defaults["geometry_feedrate_z"],
            "feedrate_rapid": self.app.defaults["geometry_feedrate_rapid"],
            "dwell": self.app.defaults["geometry_dwell"],
            "dwelltime": self.app.defaults["geometry_dwelltime"],
            "multidepth": self.app.defaults["geometry_multidepth"],
            "ppname_g": self.app.defaults["geometry_ppname_g"],
            "depthperpass": self.app.defaults["geometry_depthperpass"],
            "extracut": self.app.defaults["geometry_extracut"],
            "toolchange": self.app.defaults["geometry_toolchange"],
            "toolchangez": self.app.defaults["geometry_toolchangez"],
            "endz": self.app.defaults["geometry_endz"],
            "spindlespeed": self.app.defaults["geometry_spindlespeed"],
            "toolchangexy": self.app.defaults["geometry_toolchangexy"],
            "startz": self.app.defaults["geometry_startz"],

            "tooldia": self.app.defaults["tools_painttooldia"],
            "paintmargin": self.app.defaults["tools_paintmargin"],
            "paintmethod": self.app.defaults["tools_paintmethod"],
            "selectmethod": self.app.defaults["tools_selectmethod"],
            "pathconnect": self.app.defaults["tools_pathconnect"],
            "paintcontour": self.app.defaults["tools_paintcontour"],
            "paintoverlap": self.app.defaults["tools_paintoverlap"],

            "nccoverlap": self.app.defaults["tools_nccoverlap"],
            "nccmargin": self.app.defaults["tools_nccmargin"],
            "nccmethod": self.app.defaults["tools_nccmethod"],
            "nccconnect": self.app.defaults["tools_nccconnect"],
            "ncccontour": self.app.defaults["tools_ncccontour"],
            "nccrest": self.app.defaults["tools_nccrest"]
        })

        try:
            dias = [float(eval(dia)) for dia in self.app.defaults["tools_ncctools"].split(",") if dia != '']
        except Exception as e:
            log.error("At least one tool diameter needed. "
                      "Verify in Edit -> Preferences -> TOOLS -> NCC Tools. %s" % str(e))
            return

        self.tooluid = 0

        self.ncc_tools.clear()
        for tool_dia in dias:
            self.tooluid += 1
            self.ncc_tools.update({
                int(self.tooluid): {
                    'tooldia': float('%.*f' % (self.decimals, tool_dia)),
                    'offset': 'Path',
                    'offset_value': 0.0,
                    'type': 'Iso',
                    'tool_type': self.tool_type_radio.get_value(),
                    'operation': 'clear_op',
                    'data': deepcopy(self.default_data),
                    'solid_geometry': []
                }
            })

        self.obj_name = ""
        self.ncc_obj = None
        self.bound_obj_name = ""
        self.bound_obj = None

        self.tool_type_item_options = ["C1", "C2", "C3", "C4", "B", "V"]
        self.units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value().upper()

    def build_ui(self):
        self.ui_disconnect()

        # updated units
        self.units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value().upper()

        if self.units == "IN":
            self.addtool_entry.set_value(0.039)
        else:
            self.addtool_entry.set_value(1)

        sorted_tools = []
        for k, v in self.ncc_tools.items():
            if self.units == "IN":
                sorted_tools.append(float('%.*f' % (self.decimals, float(v['tooldia']))))
            else:
                sorted_tools.append(float('%.*f' % (self.decimals, float(v['tooldia']))))

        order = self.ncc_order_radio.get_value()
        if order == 'fwd':
            sorted_tools.sort(reverse=False)
        elif order == 'rev':
            sorted_tools.sort(reverse=True)
        else:
            pass

        n = len(sorted_tools)
        self.tools_table.setRowCount(n)
        tool_id = 0

        for tool_sorted in sorted_tools:
            for tooluid_key, tooluid_value in self.ncc_tools.items():
                if float('%.*f' % (self.decimals, tooluid_value['tooldia'])) == tool_sorted:
                    tool_id += 1
                    id_ = QtWidgets.QTableWidgetItem('%d' % int(tool_id))
                    id_.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                    row_no = tool_id - 1
                    self.tools_table.setItem(row_no, 0, id_)  # Tool name/id

                    # Make sure that the drill diameter when in MM is with no more than 2 decimals
                    # There are no drill bits in MM with more than 2 decimals diameter
                    # For INCH the decimals should be no more than 4. There are no drills under 10mils
                    dia = QtWidgets.QTableWidgetItem('%.*f' % (self.decimals, tooluid_value['tooldia']))

                    dia.setFlags(QtCore.Qt.ItemIsEnabled)

                    tool_type_item = QtWidgets.QComboBox()
                    for item in self.tool_type_item_options:
                        tool_type_item.addItem(item)
                        # tool_type_item.setStyleSheet('background-color: rgb(255,255,255)')
                    idx = tool_type_item.findText(tooluid_value['tool_type'])
                    tool_type_item.setCurrentIndex(idx)

                    tool_uid_item = QtWidgets.QTableWidgetItem(str(int(tooluid_key)))

                    operation_type = QtWidgets.QComboBox()
                    operation_type.addItem('iso_op')
                    # operation_type.setStyleSheet('background-color: rgb(255,255,255)')
                    operation_type.addItem('clear_op')
                    # operation_type.setStyleSheet('background-color: rgb(255,255,255)')
                    op_idx = operation_type.findText(tooluid_value['operation'])
                    operation_type.setCurrentIndex(op_idx)

                    self.tools_table.setItem(row_no, 1, dia)  # Diameter
                    self.tools_table.setCellWidget(row_no, 2, tool_type_item)

                    # ## REMEMBER: THIS COLUMN IS HIDDEN IN OBJECTUI.PY # ##
                    self.tools_table.setItem(row_no, 3, tool_uid_item)  # Tool unique ID

                    self.tools_table.setCellWidget(row_no, 4, operation_type)

        # make the diameter column editable
        for row in range(tool_id):
            self.tools_table.item(row, 1).setFlags(
                QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

        # all the tools are selected by default
        self.tools_table.selectColumn(0)
        #
        self.tools_table.resizeColumnsToContents()
        self.tools_table.resizeRowsToContents()

        vertical_header = self.tools_table.verticalHeader()
        vertical_header.hide()
        self.tools_table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        horizontal_header = self.tools_table.horizontalHeader()
        horizontal_header.setMinimumSectionSize(10)
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        horizontal_header.resizeSection(0, 20)
        horizontal_header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        # self.tools_table.setSortingEnabled(True)
        # sort by tool diameter
        # self.tools_table.sortItems(1)

        self.tools_table.setMinimumHeight(self.tools_table.getHeight())
        self.tools_table.setMaximumHeight(self.tools_table.getHeight())

        self.ui_connect()

    def ui_connect(self):
        self.tools_table.itemChanged.connect(self.on_tool_edit)

        for row in range(self.tools_table.rowCount()):
            for col in [2, 4]:
                self.tools_table.cellWidget(row, col).currentIndexChanged.connect(self.on_tooltable_cellwidget_change)

        self.tool_type_radio.activated_custom.connect(self.on_tool_type)

    def ui_disconnect(self):
        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tools_table.itemChanged.disconnect(self.on_tool_edit)
        except (TypeError, AttributeError):
            pass

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tool_type_radio.activated_custom.disconnect(self.on_tool_type)
        except (TypeError, AttributeError):
            pass

        for row in range(self.tools_table.rowCount()):
            for col in [2, 4]:
                try:
                    self.ui.geo_tools_table.cellWidget(row, col).currentIndexChanged.disconnect()
                except (TypeError, AttributeError):
                    pass

    def on_combo_box_type(self):
        obj_type = self.box_combo_type.currentIndex()
        self.box_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.box_combo.setCurrentIndex(0)

    def on_toggle_reference(self):
        if self.reference_radio.get_value() == "itself" or self.reference_radio.get_value() == "area":
            self.box_combo.hide()
            self.box_combo_label.hide()
            self.box_combo_type.hide()
            self.box_combo_type_label.hide()
        else:
            self.box_combo.show()
            self.box_combo_label.show()
            self.box_combo_type.show()
            self.box_combo_type_label.show()

    def on_offset_choice(self, state):
        if state:
            self.ncc_offset_label.show()
            self.ncc_offset_spinner.show()
        else:
            self.ncc_offset_label.hide()
            self.ncc_offset_spinner.hide()

    def on_order_changed(self, order):
        if order != 'no':
            self.build_ui()

    def on_rest_machining_check(self, state):
        if state:
            self.ncc_order_radio.set_value('rev')
            self.ncc_order_label.setDisabled(True)
            self.ncc_order_radio.setDisabled(True)
        else:
            self.ncc_order_label.setDisabled(False)
            self.ncc_order_radio.setDisabled(False)

    def on_tooltable_cellwidget_change(self):
        cw = self.sender()
        cw_index = self.tools_table.indexAt(cw.pos())
        cw_row = cw_index.row()
        cw_col = cw_index.column()

        current_uid = int(self.tools_table.item(cw_row, 3).text())

        hide_iso_type = True
        for row in range(self.tools_table.rowCount()):
            if self.tools_table.cellWidget(row, 4).currentText() == 'iso_op':
                hide_iso_type = False
                break

        if hide_iso_type is False:
            self.milling_type_label.show()
            self.milling_type_radio.show()
        else:
            self.milling_type_label.hide()
            self.milling_type_radio.hide()

        # if the sender is in the column with index 2 then we update the tool_type key
        if cw_col == 2:
            tt = cw.currentText()
            if tt == 'V':
                typ = 'Iso'
            else:
                typ = "Rough"

            self.ncc_tools[current_uid].update({
                'type': typ,
                'tool_type': tt,
            })

    def on_tool_type(self, val):
        if val == 'V':
            self.addtool_entry_lbl.hide()
            self.addtool_entry.hide()
            self.tipdialabel.show()
            self.tipdia_entry.show()
            self.tipanglelabel.show()
            self.tipangle_entry.show()
        else:
            self.addtool_entry_lbl.show()
            self.addtool_entry.show()
            self.tipdialabel.hide()
            self.tipdia_entry.hide()
            self.tipanglelabel.hide()
            self.tipangle_entry.hide()

    def on_tool_add(self, dia=None, muted=None):

        self.ui_disconnect()

        self.units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value().upper()

        if dia:
            tool_dia = dia
        else:
            if self.tool_type_radio.get_value() == 'V':

                tip_dia = float(self.tipdia_entry.get_value())
                tip_angle = float(self.tipangle_entry.get_value()) / 2
                cut_z = float(self.cutz_entry.get_value())

                # calculated tool diameter so the cut_z parameter is obeyed
                tool_dia = tip_dia + 2 * cut_z * math.tan(math.radians(tip_angle))

                # update the default_data so it is used in the ncc_tools dict
                self.default_data.update({
                    "vtipdia": tip_dia,
                    "vtipangle": (tip_angle * 2),
                })
            else:
                try:
                    tool_dia = float(self.addtool_entry.get_value())
                except ValueError:
                    # try to convert comma to decimal point. if it's still not working error message and return
                    try:
                        tool_dia = float(self.addtool_entry.get_value().replace(',', '.'))
                    except ValueError:
                        self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                        return

            if tool_dia is None:
                self.build_ui()
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Please enter a tool diameter to add, in Float format."))
                return

        tool_dia = float('%.*f' % (self.decimals, tool_dia))

        if tool_dia == 0:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Please enter a tool diameter with non-zero value, "
                                                          "in Float format."))
            return

        # construct a list of all 'tooluid' in the self.tools
        tool_uid_list = []
        for tooluid_key in self.ncc_tools:
            tool_uid_item = int(tooluid_key)
            tool_uid_list.append(tool_uid_item)

        # find maximum from the temp_uid, add 1 and this is the new 'tooluid'
        if not tool_uid_list:
            max_uid = 0
        else:
            max_uid = max(tool_uid_list)
        self.tooluid = int(max_uid + 1)

        tool_dias = []
        for k, v in self.ncc_tools.items():
            for tool_v in v.keys():
                if tool_v == 'tooldia':
                    tool_dias.append(float('%.*f' % (self.decimals, (v[tool_v]))))

        if float('%.*f' % (self.decimals, tool_dia)) in tool_dias:
            if muted is None:
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Adding tool cancelled. Tool already in Tool Table."))
            self.tools_table.itemChanged.connect(self.on_tool_edit)
            return
        else:
            if muted is None:
                self.app.inform.emit('[success] %s' % _("New tool added to Tool Table."))
            self.ncc_tools.update({
                int(self.tooluid): {
                    'tooldia': float('%.*f' % (self.decimals, tool_dia)),
                    'offset': 'Path',
                    'offset_value': 0.0,
                    'type': 'Iso',
                    'tool_type': self.tool_type_radio.get_value(),
                    'operation': 'clear_op',
                    'data': deepcopy(self.default_data),
                    'solid_geometry': []
                }
            })

        self.build_ui()

    def on_tool_edit(self):
        self.ui_disconnect()

        old_tool_dia = ''
        tool_dias = []
        for k, v in self.ncc_tools.items():
            for tool_v in v.keys():
                if tool_v == 'tooldia':
                    tool_dias.append(float('%.*f' % (self.decimals, v[tool_v])))

        for row in range(self.tools_table.rowCount()):

            try:
                new_tool_dia = float(self.tools_table.item(row, 1).text())
            except ValueError:
                # try to convert comma to decimal point. if it's still not working error message and return
                try:
                    new_tool_dia = float(self.tools_table.item(row, 1).text().replace(',', '.'))
                except ValueError:
                    self.app.inform.emit('[ERROR_NOTCL]  %s' % _("Wrong value format entered, "
                                         "use a number."))
                    return

            tooluid = int(self.tools_table.item(row, 3).text())

            # identify the tool that was edited and get it's tooluid
            if new_tool_dia not in tool_dias:
                self.ncc_tools[tooluid]['tooldia'] = new_tool_dia
                self.app.inform.emit('[success] %s' % _("Tool from Tool Table was edited."))
                self.build_ui()
                return
            else:
                # identify the old tool_dia and restore the text in tool table
                for k, v in self.ncc_tools.items():
                    if k == tooluid:
                        old_tool_dia = v['tooldia']
                        break
                restore_dia_item = self.tools_table.item(row, 1)
                restore_dia_item.setText(str(old_tool_dia))
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Edit cancelled. "
                                                              "New diameter value is already in the Tool Table."))
        self.build_ui()

    def on_tool_delete(self, rows_to_delete=None, all_tools=None):
        """
        Will delete a tool in the tool table

        :param rows_to_delete: which rows to delete; can be a list
        :param all_tools: delete all tools in the tool table
        :return:
        """
        self.ui_disconnect()

        deleted_tools_list = []

        if all_tools:
            self.paint_tools.clear()
            self.build_ui()
            return

        if rows_to_delete:
            try:
                for row in rows_to_delete:
                    tooluid_del = int(self.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)
            except TypeError:
                deleted_tools_list.append(rows_to_delete)

            for t in deleted_tools_list:
                self.ncc_tools.pop(t, None)
            self.build_ui()
            return

        try:
            if self.tools_table.selectedItems():
                for row_sel in self.tools_table.selectedItems():
                    row = row_sel.row()
                    if row < 0:
                        continue
                    tooluid_del = int(self.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)

                for t in deleted_tools_list:
                    self.ncc_tools.pop(t, None)

        except AttributeError:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Delete failed. Select a tool to delete."))
            return
        except Exception as e:
            log.debug(str(e))

        self.app.inform.emit('[success] %s' % _("Tool(s) deleted from Tool Table."))
        self.build_ui()

    def on_ncc_click(self):
        """
        Slot for clicking signal of the self.generate.ncc_button
        :return: None
        """

        # init values for the next usage
        self.reset_usage()
        self.app.report_usage("on_paint_button_click")

        self.overlap = float(self.ncc_overlap_entry.get_value())

        self.grb_circle_steps = int(self.app.defaults["gerber_circle_steps"])

        if self.overlap >= 1 or self.overlap < 0:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("Overlap value must be between "
                                                        "0 (inclusive) and 1 (exclusive), "))
            return

        self.connect = self.ncc_connect_cb.get_value()
        self.contour = self.ncc_contour_cb.get_value()
        self.has_offset = self.ncc_choice_offset_cb.isChecked()
        self.rest = self.ncc_rest_cb.get_value()

        self.obj_name = self.object_combo.currentText()
        # Get source object.
        try:
            self.ncc_obj = self.app.collection.get_by_name(self.obj_name)
        except Exception as e:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"),  str(self.obj_name)))
            return "Could not retrieve object: %s" % self.obj_name

        if self.ncc_obj is None:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Object not found"), str(self.obj_name)))
            return

        # use the selected tools in the tool table; get diameters for non-copper clear
        self.iso_dia_list = list()
        # use the selected tools in the tool table; get diameters for non-copper clear
        self.ncc_dia_list = list()
        if self.tools_table.selectedItems():
            for x in self.tools_table.selectedItems():
                try:
                    self.tooldia = float(self.tools_table.item(x.row(), 1).text())
                except ValueError:
                    # try to convert comma to decimal point. if it's still not working error message and return
                    try:
                        self.tooldia = float(self.tools_table.item(x.row(), 1).text().replace(',', '.'))
                    except ValueError:
                        self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong Tool Dia value format entered, "
                                                                    "use a number."))
                        continue

                if self.tools_table.cellWidget(x.row(), 4).currentText() == 'iso_op':
                    self.iso_dia_list.append(self.tooldia)
                else:
                    self.ncc_dia_list.append(self.tooldia)
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("No selected tools in Tool Table."))
            return

        self.o_name = '%s_ncc' % self.obj_name

        self.select_method = self.reference_radio.get_value()
        if self.select_method == 'itself':
            self.bound_obj_name = self.object_combo.currentText()
            # Get source object.
            try:
                self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.bound_obj_name))
                return "Could not retrieve object: %s" % self.bound_obj_name

            self.clear_copper(ncc_obj=self.ncc_obj,
                              ncctooldia=self.ncc_dia_list,
                              isotooldia=self.iso_dia_list,
                              has_offset=self.has_offset,
                              outname=self.o_name,
                              overlap=self.overlap,
                              connect=self.connect,
                              contour=self.contour,
                              rest=self.rest)
        elif self.select_method == 'area':
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Click the start point of the area."))

            if self.app.is_legacy is False:
                self.app.plotcanvas.graph_event_disconnect('mouse_press', self.app.on_mouse_click_over_plot)
                self.app.plotcanvas.graph_event_disconnect('mouse_move', self.app.on_mouse_move_over_plot)
                self.app.plotcanvas.graph_event_disconnect('mouse_release', self.app.on_mouse_click_release_over_plot)
            else:
                self.app.plotcanvas.graph_event_disconnect(self.app.mp)
                self.app.plotcanvas.graph_event_disconnect(self.app.mm)
                self.app.plotcanvas.graph_event_disconnect(self.app.mr)

            self.mr = self.app.plotcanvas.graph_event_connect('mouse_release', self.on_mouse_release)
            self.mm = self.app.plotcanvas.graph_event_connect('mouse_move', self.on_mouse_move)
        elif self.select_method == 'box':
            self.bound_obj_name = self.box_combo.currentText()
            # Get source object.
            try:
                self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.bound_obj_name))
                return "Could not retrieve object: %s. Error: %s" % (self.bound_obj_name, str(e))

            self.clear_copper(ncc_obj=self.ncc_obj,
                              sel_obj=self.bound_obj,
                              ncctooldia=self.ncc_dia_list,
                              isotooldia=self.iso_dia_list,
                              has_offset=self.has_offset,
                              outname=self.o_name,
                              overlap=self.overlap,
                              connect=self.connect,
                              contour=self.contour,
                              rest=self.rest)

    # To be called after clicking on the plot.
    def on_mouse_release(self, event):
        if self.app.is_legacy is False:
            event_pos = event.pos
            event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        event_pos = self.app.plotcanvas.translate_coords(event_pos)

        # do clear area only for left mouse clicks
        if event.button == 1:
            if self.first_click is False:
                self.first_click = True
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Click the end point of the paint area."))

                self.cursor_pos = self.app.plotcanvas.translate_coords(event_pos)
                if self.app.grid_status() == True:
                    self.cursor_pos = self.app.geo_editor.snap(event_pos[0], event_pos[1])
            else:
                self.app.inform.emit(_("Zone added. Click to start adding next zone or right click to finish."))

                if self.app.grid_status() == True:
                    curr_pos = self.app.geo_editor.snap(event_pos[0], event_pos[1])
                else:
                    curr_pos = (event_pos[0], event_pos[1])

                x0, y0 = self.cursor_pos[0], self.cursor_pos[1]
                x1, y1 = curr_pos[0], curr_pos[1]
                pt1 = (x0, y0)
                pt2 = (x1, y0)
                pt3 = (x1, y1)
                pt4 = (x0, y1)

                self.sel_rect.append(Polygon([pt1, pt2, pt3, pt4]))
                self.first_click = False
                return

        elif event.button == right_button and self.mouse_is_dragging == False:
            self.app.delete_selection_shape()

            self.first_click = False

            if self.app.is_legacy is False:
                self.app.plotcanvas.graph_event_disconnect('mouse_release', self.on_mouse_release)
                self.app.plotcanvas.graph_event_disconnect('mouse_move', self.on_mouse_move)
            else:
                self.app.plotcanvas.graph_event_disconnect(self.mr)
                self.app.plotcanvas.graph_event_disconnect(self.mm)

            self.app.mp = self.app.plotcanvas.graph_event_connect('mouse_press',
                                                                  self.app.on_mouse_click_over_plot)
            self.app.mm = self.app.plotcanvas.graph_event_connect('mouse_move',
                                                                  self.app.on_mouse_move_over_plot)
            self.app.mr = self.app.plotcanvas.graph_event_connect('mouse_release',
                                                                  self.app.on_mouse_click_release_over_plot)

            if len(self.sel_rect) == 0:
                return

            self.sel_rect = cascaded_union(self.sel_rect)

            self.clear_copper(ncc_obj=self.ncc_obj,
                              sel_obj=self.bound_obj,
                              ncctooldia=self.ncc_dia_list,
                              isotooldia=self.iso_dia_list,
                              has_offset=self.has_offset,
                              outname=self.o_name,
                              overlap=self.overlap,
                              connect=self.connect,
                              contour=self.contour,
                              rest=self.rest)

    # called on mouse move
    def on_mouse_move(self, event):
        if self.app.is_legacy is False:
            event_pos = event.pos
            event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        curr_pos = self.app.plotcanvas.translate_coords(event_pos)

        # detect mouse dragging motion
        if event_is_dragging is True:
            self.mouse_is_dragging = True
        else:
            self.mouse_is_dragging = False

        # update the cursor position
        if self.app.grid_status() == True:
            # Update cursor
            curr_pos = self.app.geo_editor.snap(curr_pos[0], curr_pos[1])

            self.app.app_cursor.set_data(np.asarray([(curr_pos[0], curr_pos[1])]),
                                         symbol='++', edge_color=self.app.cursor_color_3D,
                                         size=self.app.defaults["global_cursor_size"])

        # update the positions on status bar
        self.app.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
                                           "<b>Y</b>: %.4f" % (curr_pos[0], curr_pos[1]))
        if self.cursor_pos is None:
            self.cursor_pos = (0, 0)

        dx = curr_pos[0] - float(self.cursor_pos[0])
        dy = curr_pos[1] - float(self.cursor_pos[1])
        self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                               "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (dx, dy))

        # draw the utility geometry
        if self.first_click:
            self.app.delete_selection_shape()
            self.app.draw_moving_selection_shape(old_coords=(self.cursor_pos[0], self.cursor_pos[1]),
                                                 coords=(curr_pos[0], curr_pos[1]))

    def clear_copper(self, ncc_obj,
                     sel_obj=None,
                     ncctooldia=None,
                     isotooldia=None,
                     margin=None,
                     has_offset=None,
                     offset=None,
                     select_method=None,
                     outname=None,
                     overlap=None,
                     connect=None,
                     contour=None,
                     order=None,
                     method=None,
                     rest=None,
                     tools_storage=None,
                     plot=True,
                     run_threaded=True):
        """
        Clear the excess copper from the entire object.

        :param ncc_obj: ncc cleared object
        :param ncctooldia: a tuple or single element made out of diameters of the tools to be used to ncc clear
        :param isotooldia: a tuple or single element made out of diameters of the tools to be used for isolation
        :param overlap: value by which the paths will overlap
        :param order: if the tools are ordered and how
        :param select_method: if to do ncc on the whole object, on an defined area or on an area defined by
        another object
        :param has_offset: True if an offset is needed
        :param offset: distance from the copper features where the copper clearing is stopping
        :param margin: a border around cleared area
        :param outname: name of the resulting object
        :param connect: Connect lines to avoid tool lifts.
        :param contour: Paint around the edges.
        :param method: choice out of 'seed', 'normal', 'lines'
        :param rest: True if to use rest-machining
        :param tools_storage: whether to use the current tools_storage self.ncc_tools or a different one.
        Usage of the different one is related to when this function is called from a TcL command.
        :param plot: if True after the job is finished the result will be plotted, else it will not.
        :param run_threaded: If True the method will be run in a threaded way suitable for GUI usage; if False it will
        run non-threaded for TclShell usage
        :return:
        """
        if run_threaded:
            proc = self.app.proc_container.new(_("Non-Copper clearing ..."))
        else:
            self.app.proc_container.view.set_busy(_("Non-Copper clearing ..."))
            QtWidgets.QApplication.processEvents()

        # #####################################################################
        # ####### Read the parameters #########################################
        # #####################################################################

        units = self.app.ui.general_defaults_form.general_app_group.units_radio.get_value()

        log.debug("NCC Tool started. Reading parameters.")
        self.app.inform.emit(_("NCC Tool started. Reading parameters."))

        ncc_method = method if method else self.ncc_method_radio.get_value()

        if margin is not None:
            ncc_margin = margin
        else:
            ncc_margin = float(self.ncc_margin_entry.get_value())

        if select_method is not None:
            ncc_select = select_method
        else:
            ncc_select = self.reference_radio.get_value()

        overlap = overlap if overlap else float(self.app.defaults["tools_nccoverlap"])

        connect = connect if connect else self.app.defaults["tools_nccconnect"]
        contour = contour if contour else self.app.defaults["tools_ncccontour"]
        order = order if order else self.ncc_order_radio.get_value()

        # determine if to use the progressive plotting
        if self.app.defaults["tools_ncc_plotting"] == 'progressive':
            prog_plot = True
        else:
            prog_plot = False

        if tools_storage is not None:
            tools_storage = tools_storage
        else:
            tools_storage = self.ncc_tools

        ncc_offset = 0.0
        if has_offset is True:
            if offset is not None:
                ncc_offset = offset
            else:
                try:
                    ncc_offset = float(self.ncc_offset_spinner.get_value())
                except ValueError:
                    self.app.inform.emit('[ERROR_NOTCL] %s' % _("Wrong value format entered, use a number."))
                    return

        # ######################################################################################################
        # # Read the tooldia parameter and create a sorted list out them - they may be more than one diameter ##
        # ######################################################################################################
        sorted_tools = []
        if ncctooldia is not None:
            try:
                sorted_tools = [float(eval(dia)) for dia in ncctooldia.split(",") if dia != '']
            except AttributeError:
                if not isinstance(ncctooldia, list):
                    sorted_tools = [float(ncctooldia)]
                else:
                    sorted_tools = ncctooldia
        else:
            for row in range(self.tools_table.rowCount()):
                if self.tools_table.cellWidget(row, 1).currentText() == 'clear_op':
                    sorted_tools.append(float(self.tools_table.item(row, 1).text()))

        # ##############################################################################################################
        # Prepare non-copper polygons. Create the bounding box area from which the copper features will be subtracted ##
        # ##############################################################################################################
        log.debug("NCC Tool. Preparing non-copper polygons.")
        self.app.inform.emit(_("NCC Tool. Preparing non-copper polygons."))

        try:
            if sel_obj is None or sel_obj == 'itself':
                ncc_sel_obj = ncc_obj
            else:
                ncc_sel_obj = sel_obj
        except Exception as e:
            log.debug("NonCopperClear.clear_copper() --> %s" % str(e))
            return 'fail'

        bounding_box = None
        if ncc_select == 'itself':
            geo_n = ncc_sel_obj.solid_geometry

            try:
                if isinstance(geo_n, MultiPolygon):
                    env_obj = geo_n.convex_hull
                elif (isinstance(geo_n, MultiPolygon) and len(geo_n) == 1) or \
                        (isinstance(geo_n, list) and len(geo_n) == 1) and isinstance(geo_n[0], Polygon):
                    env_obj = cascaded_union(geo_n)
                else:
                    env_obj = cascaded_union(geo_n)
                    env_obj = env_obj.convex_hull

                bounding_box = env_obj.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            except Exception as e:
                log.debug("NonCopperClear.clear_copper() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return 'fail'

        elif ncc_select == 'area':
            geo_n = cascaded_union(self.sel_rect)
            try:
                __ = iter(geo_n)
            except Exception as e:
                log.debug("NonCopperClear.clear_copper() 'area' --> %s" % str(e))
                geo_n = [geo_n]

            geo_buff_list = []
            for poly in geo_n:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise FlatCAMApp.GracefulException
                geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

            bounding_box = cascaded_union(geo_buff_list)

        elif ncc_select == 'box':
            geo_n = ncc_sel_obj.solid_geometry
            if isinstance(ncc_sel_obj, FlatCAMGeometry):
                try:
                    __ = iter(geo_n)
                except Exception as e:
                    log.debug("NonCopperClear.clear_copper() 'box' --> %s" % str(e))
                    geo_n = [geo_n]

                geo_buff_list = []
                for poly in geo_n:
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise FlatCAMApp.GracefulException
                    geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

                bounding_box = cascaded_union(geo_buff_list)
            elif isinstance(ncc_sel_obj, FlatCAMGerber):
                geo_n = cascaded_union(geo_n).convex_hull
                bounding_box = cascaded_union(self.ncc_obj.solid_geometry).convex_hull.intersection(geo_n)
                bounding_box = bounding_box.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        log.debug("NCC Tool. Finished non-copper polygons.")
        # ########################################################################################################
        # set the name for the future Geometry object
        # I do it here because it is also stored inside the gen_clear_area() and gen_clear_area_rest() methods
        # ########################################################################################################
        rest_machining_choice = rest if rest is not None else self.app.defaults["tools_nccrest"]
        if rest_machining_choice is True:
            name = outname if outname is not None else self.obj_name + "_ncc_rm"
        else:
            name = outname if outname is not None else self.obj_name + "_ncc"

        # ##########################################################################################
        # Initializes the new geometry object ######################################################
        # ##########################################################################################
        def gen_clear_area(geo_obj, app_obj):
            assert isinstance(geo_obj, FlatCAMGeometry), \
                "Initializer expected a FlatCAMGeometry, got %s" % type(geo_obj)

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            log.debug("NCC Tool. Normal copper clearing task started.")
            self.app.inform.emit(_("NCC Tool. Finished non-copper polygons. Normal copper clearing task started."))

            # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
            # will store the number of tools for which the isolation is broken
            warning_flag = 0

            if order == 'fwd':
                sorted_tools.sort(reverse=False)
            elif order == 'rev':
                sorted_tools.sort(reverse=True)
            else:
                pass

            cleared_geo = []
            # Already cleared area
            cleared = MultiPolygon()

            # flag for polygons not cleared
            app_obj.poly_not_cleared = False

            # Generate area for each tool
            offset = sum(sorted_tools)
            current_uid = int(1)
            try:
                tool = eval(self.app.defaults["tools_ncctools"])[0]
            except TypeError:
                tool = eval(self.app.defaults["tools_ncctools"])

            # ###################################################################################################
            # Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry ##
            # ###################################################################################################
            log.debug("NCC Tool. Calculate 'empty' area.")
            self.app.inform.emit(_("NCC Tool. Calculate 'empty' area."))

            if isinstance(ncc_obj, FlatCAMGerber) and not isotooldia:
                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.defaults['gerber_buffering'] == 'no':
                    sol_geo = ncc_obj.solid_geometry.buffer(0)
                else:
                    sol_geo = ncc_obj.solid_geometry

                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'
            elif isinstance(ncc_obj, FlatCAMGerber) and isotooldia:
                isolated_geo = []

                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.defaults['gerber_buffering'] == 'no':
                    self.solid_geometry = ncc_obj.solid_geometry.buffer(0)
                else:
                    self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.milling_type_radio.get_value()

                for tool_iso in isotooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso / 2, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso / 2, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise FlatCAMApp.GracefulException

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for poly in geo_elem:
                                        for ring in self.poly2rings(poly):
                                            new_geo = ring.intersection(bounding_box)
                                            if new_geo and not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(geo_elem, LineString):
                                    new_geo = geo_elem.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiLineString):
                                    for line_elem in geo_elem:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                        except TypeError:
                            if isinstance(isolated_geo, Polygon):
                                for ring in self.poly2rings(isolated_geo):
                                    new_geo = ring.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                            elif isinstance(isolated_geo, LineString):
                                new_geo = isolated_geo.intersection(bounding_box)
                                if new_geo and not new_geo.is_empty:
                                    new_geometry.append(new_geo)
                            elif isinstance(isolated_geo, MultiLineString):
                                for line_elem in isolated_geo:
                                    new_geo = line_elem.intersection(bounding_box)
                                    if new_geo and not new_geo.is_empty:
                                        new_geometry.append(new_geo)

                        # a MultiLineString geometry element will show that the isolation is broken for this tool
                        for geo_e in new_geometry:
                            if type(geo_e) == MultiLineString:
                                warning_flag += 1
                                break

                        for k, v in tools_storage.items():
                            if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                tool_iso)):
                                current_uid = int(k)
                                # add the solid_geometry to the current too in self.paint_tools dictionary
                                # and then reset the temporary list that stored that solid_geometry
                                v['solid_geometry'] = deepcopy(new_geometry)
                                v['data']['name'] = name
                                break
                        geo_obj.tools[current_uid] = dict(tools_storage[current_uid])

                sol_geo = cascaded_union(isolated_geo)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

            elif isinstance(ncc_obj, FlatCAMGeometry):
                sol_geo = cascaded_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

            else:
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _('The selected object is not suitable for copper clearing.'))
                return

            if empty.is_empty:
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _("Could not get the extent of the area to be non copper cleared."))
                return 'fail'

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            log.debug("NCC Tool. Finished calculation of 'empty' area.")
            self.app.inform.emit(_("NCC Tool. Finished calculation of 'empty' area."))

            cp = None
            for tool in sorted_tools:
                log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise FlatCAMApp.GracefulException

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit(
                    '[success] %s %s%s %s' % (_('NCC Tool clearing with tool diameter = '),
                                              str(tool),
                                              units.lower(),
                                              _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                cleared_geo[:] = []

                # Get remaining tools offset
                offset -= (tool - 1e-12)

                # Area to clear
                area = empty.buffer(-offset)
                try:
                    area = area.difference(cleared)
                except Exception as e:
                    continue

                # Transform area to MultiPolygon
                if type(area) is Polygon:
                    area = MultiPolygon([area])

                # variables to display the percentage of work done
                geo_len = len(area.geoms)

                old_disp_number = 0
                log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if area.geoms:
                    if len(area.geoms) > 0:
                        pol_nr = 0
                        for p in area.geoms:
                            # provide the app with a way to process the GUI events when in a blocking loop
                            QtWidgets.QApplication.processEvents()

                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise FlatCAMApp.GracefulException
                            if p is not None:
                                try:
                                    if isinstance(p, Polygon):
                                        if ncc_method == 'standard':
                                            cp = self.clear_polygon(p, tool, self.grb_circle_steps,
                                                                    overlap=overlap, contour=contour, connect=connect,
                                                                    prog_plot=prog_plot)
                                        elif ncc_method == 'seed':
                                            cp = self.clear_polygon2(p, tool, self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=prog_plot)
                                        else:
                                            cp = self.clear_polygon3(p, tool, self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=prog_plot)
                                        if cp:
                                            cleared_geo += list(cp.get_objects())
                                    elif isinstance(p, MultiPolygon):
                                        for pol in p:
                                            if pol is not None:
                                                if ncc_method == 'standard':
                                                    cp = self.clear_polygon(pol, tool,
                                                                            self.grb_circle_steps,
                                                                            overlap=overlap, contour=contour,
                                                                            connect=connect,
                                                                            prog_plot=prog_plot)
                                                elif ncc_method == 'seed':
                                                    cp = self.clear_polygon2(pol, tool,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=prog_plot)
                                                else:
                                                    cp = self.clear_polygon3(pol, tool,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=prog_plot)
                                                if cp:
                                                    cleared_geo += list(cp.get_objects())
                                except Exception as e:
                                    log.warning("Polygon can not be cleared. %s" % str(e))
                                    app_obj.poly_not_cleared = True
                                    continue

                                pol_nr += 1
                                disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                                # log.debug("Polygons cleared: %d" % pol_nr)

                                if old_disp_number < disp_number <= 100:
                                    self.app.proc_container.update_view_text(' %d%%' % disp_number)
                                    old_disp_number = disp_number
                                    # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                            # check if there is a geometry at all in the cleared geometry
                        if cleared_geo:
                            # Overall cleared area
                            cleared = empty.buffer(-offset * (1 + overlap)).buffer(-tool / 1.999999).buffer(
                                tool / 1.999999)

                            # clean-up cleared geo
                            cleared = cleared.buffer(0)

                            # find the tooluid associated with the current tool_dia so we know where to add the tool
                            # solid_geometry
                            for k, v in tools_storage.items():
                                if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                    tool)):
                                    current_uid = int(k)

                                    # add the solid_geometry to the current too in self.paint_tools dictionary
                                    # and then reset the temporary list that stored that solid_geometry
                                    v['solid_geometry'] = deepcopy(cleared_geo)
                                    v['data']['name'] = name
                                    break
                            geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                        else:
                            log.debug("There are no geometries in the cleared polygon.")

            # clean the progressive plotted shapes if it was used
            if self.app.defaults["tools_ncc_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # delete tools with empty geometry
            keys_to_delete = []
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid in tools_storage:
                # if the solid_geometry (type=list) is empty
                if not tools_storage[uid]['solid_geometry']:
                    keys_to_delete.append(uid)

            # actual delete of keys from the tools_storage dict
            for k in keys_to_delete:
                tools_storage.pop(k, None)

            geo_obj.options["cnctooldia"] = str(tool)
            geo_obj.multigeo = True
            geo_obj.tools.clear()
            geo_obj.tools = dict(tools_storage)

            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            has_solid_geo = 0
            for tooluid in geo_obj.tools:
                if geo_obj.tools[tooluid]['solid_geometry']:
                    has_solid_geo += 1
            if has_solid_geo == 0:
                app_obj.inform.emit('[ERROR] %s' % _("There is no NCC Geometry in the file.\n"
                                                     "Usually it means that the tool diameter is too big "
                                                     "for the painted geometry.\n"
                                                     "Change the painting parameters and try again."))
                return

            # Experimental...
            # print("Indexing...", end=' ')
            # geo_obj.make_index()
            if warning_flag == 0:
                self.app.inform.emit('[success] %s' % _("NCC Tool clear all done."))
            else:
                self.app.inform.emit('[WARNING] %s: %s %s.' % (_("NCC Tool clear all done but the copper features "
                                                                 "isolation is broken for"),
                                                               str(warning_flag),
                                                               _("tools")))

        # ###########################################################################################
        # Initializes the new geometry object for the case of the rest-machining ####################
        # ###########################################################################################
        def gen_clear_area_rest(geo_obj, app_obj):
            assert isinstance(geo_obj, FlatCAMGeometry), \
                "Initializer expected a FlatCAMGeometry, got %s" % type(geo_obj)

            log.debug("NCC Tool. Rest machining copper clearing task started.")
            app_obj.inform.emit('_(NCC Tool. Rest machining copper clearing task started.')

            # provide the app with a way to process the GUI events when in a blocking loop
            if not run_threaded:
                QtWidgets.QApplication.processEvents()

            # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
            # will store the number of tools for which the isolation is broken
            warning_flag = 0

            sorted_tools.sort(reverse=True)

            cleared_geo = []
            cleared_by_last_tool = []
            rest_geo = []
            current_uid = 1
            try:
                tool = eval(self.app.defaults["tools_ncctools"])[0]
            except TypeError:
                tool = eval(self.app.defaults["tools_ncctools"])

            # repurposed flag for final object, geo_obj. True if it has any solid_geometry, False if not.
            app_obj.poly_not_cleared = True
            log.debug("NCC Tool. Calculate 'empty' area.")
            app_obj.inform.emit("NCC Tool. Calculate 'empty' area.")

            # ###################################################################################################
            # Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry ##
            # ###################################################################################################
            if isinstance(ncc_obj, FlatCAMGerber) and not isotooldia:
                sol_geo = ncc_obj.solid_geometry
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

            elif isinstance(ncc_obj, FlatCAMGerber) and isotooldia:
                isolated_geo = []
                self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.milling_type_radio.get_value()

                for tool_iso in isotooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise FlatCAMApp.GracefulException

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for poly in geo_elem:
                                        for ring in self.poly2rings(poly):
                                            new_geo = ring.intersection(bounding_box)
                                            if new_geo and not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(geo_elem, LineString):
                                    new_geo = geo_elem.intersection(bounding_box)
                                    if new_geo:
                                        if not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiLineString):
                                    for line_elem in geo_elem:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                        except TypeError:
                            try:
                                if isinstance(isolated_geo, Polygon):
                                    for ring in self.poly2rings(isolated_geo):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo:
                                            if not new_geo.is_empty:
                                                new_geometry.append(new_geo)
                                elif isinstance(isolated_geo, LineString):
                                    new_geo = isolated_geo.intersection(bounding_box)
                                    if new_geo and not new_geo.is_empty:
                                        new_geometry.append(new_geo)
                                elif isinstance(isolated_geo, MultiLineString):
                                    for line_elem in isolated_geo:
                                        new_geo = line_elem.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                            except Exception as e:
                                pass

                        # a MultiLineString geometry element will show that the isolation is broken for this tool
                        for geo_e in new_geometry:
                            if type(geo_e) == MultiLineString:
                                warning_flag += 1
                                break

                        for k, v in tools_storage.items():
                            if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                tool_iso)):
                                current_uid = int(k)
                                # add the solid_geometry to the current too in self.paint_tools dictionary
                                # and then reset the temporary list that stored that solid_geometry
                                v['solid_geometry'] = deepcopy(new_geometry)
                                v['data']['name'] = name
                                break
                        geo_obj.tools[current_uid] = dict(tools_storage[current_uid])

                sol_geo = cascaded_union(isolated_geo)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

            elif isinstance(ncc_obj, FlatCAMGeometry):
                sol_geo = cascaded_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' %
                                        _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' %
                                        _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'
            else:
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _('The selected object is not suitable for copper clearing.'))
                return

            if empty.is_empty:
                app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                    _("Could not get the extent of the area to be non copper cleared."))
                return 'fail'

            if self.app.abort_flag:
                # graceful abort requested by the user
                raise FlatCAMApp.GracefulException

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            area = empty.buffer(0)

            log.debug("NCC Tool. Finished calculation of 'empty' area.")
            app_obj.inform.emit("NCC Tool. Finished calculation of 'empty' area.")

            # Generate area for each tool
            while sorted_tools:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise FlatCAMApp.GracefulException

                tool = sorted_tools.pop(0)
                log.debug("Starting geometry processing for tool: %s" % str(tool))

                app_obj.inform.emit(
                    '[success] %s %s%s %s' % (_('NCC Tool clearing with tool diameter = '),
                                              str(tool),
                                              units.lower(),
                                              _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool_used = tool - 1e-12
                cleared_geo[:] = []

                # Area to clear
                for poly in cleared_by_last_tool:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise FlatCAMApp.GracefulException
                    try:
                        area = area.difference(poly)
                    except Exception as e:
                        pass
                cleared_by_last_tool[:] = []

                # Transform area to MultiPolygon
                if type(area) is Polygon:
                    area = MultiPolygon([area])

                # add the rest that was not able to be cleared previously; area is a MultyPolygon
                # and rest_geo it's a list
                allparts = [p.buffer(0) for p in area.geoms]
                allparts += deepcopy(rest_geo)
                rest_geo[:] = []
                area = MultiPolygon(deepcopy(allparts))
                allparts[:] = []

                # variables to display the percentage of work done
                geo_len = len(area.geoms)
                disp_number = 0
                old_disp_number = 0
                log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if area.geoms:
                    if len(area.geoms) > 0:
                        pol_nr = 0
                        for p in area.geoms:
                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise FlatCAMApp.GracefulException

                            if p is not None:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if isinstance(p, Polygon):
                                    try:
                                        if ncc_method == 'standard':
                                            cp = self.clear_polygon(p, tool_used,
                                                                    self.grb_circle_steps,
                                                                    overlap=overlap, contour=contour, connect=connect,
                                                                    prog_plot=prog_plot)
                                        elif ncc_method == 'seed':
                                            cp = self.clear_polygon2(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=prog_plot)
                                        else:
                                            cp = self.clear_polygon3(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=prog_plot)
                                        cleared_geo.append(list(cp.get_objects()))
                                    except Exception as e:
                                        log.warning("Polygon can't be cleared. %s" % str(e))
                                        # this polygon should be added to a list and then try clear it with
                                        # a smaller tool
                                        rest_geo.append(p)
                                elif isinstance(p, MultiPolygon):
                                    for poly in p:
                                        if poly is not None:
                                            # provide the app with a way to process the GUI events when in a blocking loop
                                            QtWidgets.QApplication.processEvents()

                                            try:
                                                if ncc_method == 'standard':
                                                    cp = self.clear_polygon(poly, tool_used,
                                                                            self.grb_circle_steps,
                                                                            overlap=overlap, contour=contour,
                                                                            connect=connect,
                                                                            prog_plot=prog_plot)
                                                elif ncc_method == 'seed':
                                                    cp = self.clear_polygon2(poly, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=prog_plot)
                                                else:
                                                    cp = self.clear_polygon3(poly, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=prog_plot)
                                                cleared_geo.append(list(cp.get_objects()))
                                            except Exception as e:
                                                log.warning("Polygon can't be cleared. %s" % str(e))
                                                # this polygon should be added to a list and then try clear it with
                                                # a smaller tool
                                                rest_geo.append(poly)

                                pol_nr += 1
                                disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                                # log.debug("Polygons cleared: %d" % pol_nr)

                                if old_disp_number < disp_number <= 100:
                                    self.app.proc_container.update_view_text(' %d%%' % disp_number)
                                    old_disp_number = disp_number
                                    # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise FlatCAMApp.GracefulException

                        # check if there is a geometry at all in the cleared geometry
                        if cleared_geo:
                            # Overall cleared area
                            cleared_area = list(self.flatten_list(cleared_geo))

                            # cleared = MultiPolygon([p.buffer(tool_used / 2).buffer(-tool_used / 2)
                            #                         for p in cleared_area])

                            # here we store the poly's already processed in the original geometry by the current tool
                            # into cleared_by_last_tool list
                            # this will be sutracted from the original geometry_to_be_cleared and make data for
                            # the next tool
                            buffer_value = tool_used / 2
                            for p in cleared_area:
                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise FlatCAMApp.GracefulException

                                poly = p.buffer(buffer_value)
                                cleared_by_last_tool.append(poly)

                            # find the tooluid associated with the current tool_dia so we know
                            # where to add the tool solid_geometry
                            for k, v in tools_storage.items():
                                if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals,
                                                                                                    tool)):
                                    current_uid = int(k)

                                    # add the solid_geometry to the current too in self.paint_tools dictionary
                                    # and then reset the temporary list that stored that solid_geometry
                                    v['solid_geometry'] = deepcopy(cleared_area)
                                    v['data']['name'] = name
                                    cleared_area[:] = []
                                    break

                            geo_obj.tools[current_uid] = dict(tools_storage[current_uid])
                        else:
                            log.debug("There are no geometries in the cleared polygon.")

            geo_obj.multigeo = True
            geo_obj.options["cnctooldia"] = str(tool)

            # clean the progressive plotted shapes if it was used
            if self.app.defaults["tools_ncc_plotting"] == 'progressive':
                self.temp_shapes.clear(update=True)

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool Rest Machining clear all done."))
                else:
                    self.app.inform.emit(
                        '[WARNING] %s: %s %s.' % (_("NCC Tool Rest Machining clear all done but the copper features "
                                                    "isolation is broken for"), str(warning_flag), _("tools")))
                return
            else:
                # I will use this variable for this purpose although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

        # ###########################################################################################
        # Create the Job function and send it to the worker to be processed in another thread #######
        # ###########################################################################################
        def job_thread(app_obj):
            try:
                if rest_machining_choice is True:
                    app_obj.new_object("geometry", name, gen_clear_area_rest, plot=plot)
                else:
                    app_obj.new_object("geometry", name, gen_clear_area, plot=plot)
            except FlatCAMApp.GracefulException:
                if run_threaded:
                    proc.done()
                return
            except Exception as e:
                if run_threaded:
                    proc.done()
                traceback.print_stack()
                return
            if run_threaded:
                proc.done()
            else:
                app_obj.proc_container.view.set_idle()

            # focus on Selected Tab
            self.app.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)

        if run_threaded:
            # Promise object with the new name
            self.app.collection.promise(name)

            # Background
            self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})
        else:
            job_thread(app_obj=self.app)

    # def on_ncc(self):
    #
    #     # Prepare non-copper polygons
    #     if self.reference_radio.get_value() == 'area':
    #         geo_n = self.sel_rect
    #
    #         geo_buff_list = []
    #         for poly in geo_n:
    #             geo_buff_list.append(poly.buffer(distance=margin, join_style=base.JOIN_STYLE.mitre))
    #         bounding_box = cascaded_union(geo_buff_list)
    #     else:
    #         geo_n = self.bound_obj.solid_geometry
    #
    #         try:
    #             if isinstance(geo_n, MultiPolygon):
    #                 env_obj = geo_n.convex_hull
    #             elif (isinstance(geo_n, MultiPolygon) and len(geo_n) == 1) or \
    #                     (isinstance(geo_n, list) and len(geo_n) == 1) and isinstance(geo_n[0], Polygon):
    #                 env_obj = cascaded_union(geo_n)
    #             else:
    #                 env_obj = cascaded_union(geo_n)
    #                 env_obj = env_obj.convex_hull
    #             bounding_box = env_obj.buffer(distance=margin, join_style=base.JOIN_STYLE.mitre)
    #         except Exception as e:
    #             log.debug("NonCopperClear.on_ncc() --> %s" % str(e))
    #             self.app.inform.emit(_("[ERROR_NOTCL] No object available."))
    #             return
    #
    #     # calculate the empty area by subtracting the solid_geometry from the object bounding box geometry
    #     if isinstance(self.ncc_obj, FlatCAMGerber):
    #         if self.ncc_choice_offset_cb.isChecked():
    #             self.app.inform.emit(_("[WARNING_NOTCL] Buffering ..."))
    #             offseted_geo = self.ncc_obj.solid_geometry.buffer(distance=ncc_offset_value)
    #             self.app.inform.emit(_("[success] Buffering finished ..."))
    #             empty = self.get_ncc_empty_area(target=offseted_geo, boundary=bounding_box)
    #         else:
    #             empty = self.get_ncc_empty_area(target=self.ncc_obj.solid_geometry, boundary=bounding_box)
    #     elif isinstance(self.ncc_obj, FlatCAMGeometry):
    #         sol_geo = cascaded_union(self.ncc_obj.solid_geometry)
    #         if self.ncc_choice_offset_cb.isChecked():
    #             self.app.inform.emit(_("[WARNING_NOTCL] Buffering ..."))
    #             offseted_geo = sol_geo.buffer(distance=ncc_offset_value)
    #             self.app.inform.emit(_("[success] Buffering finished ..."))
    #             empty = self.get_ncc_empty_area(target=offseted_geo, boundary=bounding_box)
    #         else:
    #             empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
    #     else:
    #         self.inform.emit(_('[ERROR_NOTCL] The selected object is not suitable for copper clearing.'))
    #         return
    #
    #     if type(empty) is Polygon:
    #         empty = MultiPolygon([empty])
    #
    #     if empty.is_empty:
    #         self.app.inform.emit(_("[ERROR_NOTCL] Could not get the extent of the area to be non copper cleared."))
    #         return
    #
    #     # clear non copper using standard algorithm
    #     if clearing_method is False:
    #         self.clear_non_copper(
    #             empty=empty,
    #             over=over,
    #             pol_method=pol_method,
    #             connect=connect,
    #             contour=contour
    #         )
    #     # clear non copper using rest machining algorithm
    #     else:
    #         self.clear_non_copper_rest(
    #             empty=empty,
    #             over=over,
    #             pol_method=pol_method,
    #             connect=connect,
    #             contour=contour
    #         )
    #
    # def clear_non_copper(self, empty, over, pol_method, outname=None, connect=True, contour=True):
    #
    #     name = outname if outname else self.obj_name + "_ncc"
    #
    #     # Sort tools in descending order
    #     sorted_tools = []
    #     for k, v in self.ncc_tools.items():
    #         sorted_tools.append(float('%.4f' % float(v['tooldia'])))
    #
    #     order = self.ncc_order_radio.get_value()
    #     if order == 'fwd':
    #         sorted_tools.sort(reverse=False)
    #     elif order == 'rev':
    #         sorted_tools.sort(reverse=True)
    #     else:
    #         pass
    #
    #     # Do job in background
    #     proc = self.app.proc_container.new(_("Clearing Non-Copper areas."))
    #
    #     def initialize(geo_obj, app_obj):
    #         assert isinstance(geo_obj, FlatCAMGeometry), \
    #             "Initializer expected a FlatCAMGeometry, got %s" % type(geo_obj)
    #
    #         cleared_geo = []
    #         # Already cleared area
    #         cleared = MultiPolygon()
    #
    #         # flag for polygons not cleared
    #         app_obj.poly_not_cleared = False
    #
    #         # Generate area for each tool
    #         offset = sum(sorted_tools)
    #         current_uid = int(1)
    #         tool = eval(self.app.defaults["tools_ncctools"])[0]
    #
    #         for tool in sorted_tools:
    #             self.app.inform.emit(_('[success] Non-Copper Clearing with ToolDia = %s started.') % str(tool))
    #             cleared_geo[:] = []
    #
    #             # Get remaining tools offset
    #             offset -= (tool - 1e-12)
    #
    #             # Area to clear
    #             area = empty.buffer(-offset)
    #             try:
    #                 area = area.difference(cleared)
    #             except Exception as e:
    #                 continue
    #
    #             # Transform area to MultiPolygon
    #             if type(area) is Polygon:
    #                 area = MultiPolygon([area])
    #
    #             if area.geoms:
    #                 if len(area.geoms) > 0:
    #                     for p in area.geoms:
    #                         try:
    #                             if pol_method == 'standard':
    #                                 cp = self.clear_polygon(p, tool, self.app.defaults["gerber_circle_steps"],
    #                                                         overlap=over, contour=contour, connect=connect)
    #                             elif pol_method == 'seed':
    #                                 cp = self.clear_polygon2(p, tool, self.app.defaults["gerber_circle_steps"],
    #                                                          overlap=over, contour=contour, connect=connect)
    #                             else:
    #                                 cp = self.clear_polygon3(p, tool, self.app.defaults["gerber_circle_steps"],
    #                                                          overlap=over, contour=contour, connect=connect)
    #                             if cp:
    #                                 cleared_geo += list(cp.get_objects())
    #                         except Exception as e:
    #                             log.warning("Polygon can not be cleared. %s" % str(e))
    #                             app_obj.poly_not_cleared = True
    #                             continue
    #
    #                     # check if there is a geometry at all in the cleared geometry
    #                     if cleared_geo:
    #                         # Overall cleared area
    #                         cleared = empty.buffer(-offset * (1 + over)).buffer(-tool / 1.999999).buffer(
    #                             tool / 1.999999)
    #
    #                         # clean-up cleared geo
    #                         cleared = cleared.buffer(0)
    #
    #                         # find the tooluid associated with the current tool_dia so we know where to add the tool
    #                         # solid_geometry
    #                         for k, v in self.ncc_tools.items():
    #                             if float('%.4f' % v['tooldia']) == float('%.4f' % tool):
    #                                 current_uid = int(k)
    #
    #                                 # add the solid_geometry to the current too in self.paint_tools dictionary
    #                                 # and then reset the temporary list that stored that solid_geometry
    #                                 v['solid_geometry'] = deepcopy(cleared_geo)
    #                                 v['data']['name'] = name
    #                                 break
    #                         geo_obj.tools[current_uid] = dict(self.ncc_tools[current_uid])
    #                     else:
    #                         log.debug("There are no geometries in the cleared polygon.")
    #
    #         geo_obj.options["cnctooldia"] = str(tool)
    #         geo_obj.multigeo = True
    #
    #     def job_thread(app_obj):
    #         try:
    #             app_obj.new_object("geometry", name, initialize)
    #         except Exception as e:
    #             proc.done()
    #             self.app.inform.emit(_('[ERROR_NOTCL] NCCTool.clear_non_copper() --> %s') % str(e))
    #             return
    #         proc.done()
    #
    #         if app_obj.poly_not_cleared is False:
    #             self.app.inform.emit(_('[success] NCC Tool finished.'))
    #         else:
    #             self.app.inform.emit(_('[WARNING_NOTCL] NCC Tool finished but some PCB features could not be cleared. '
    #                                  'Check the result.'))
    #         # reset the variable for next use
    #         app_obj.poly_not_cleared = False
    #
    #         # focus on Selected Tab
    #         self.app.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)
    #
    #     # Promise object with the new name
    #     self.app.collection.promise(name)
    #
    #     # Background
    #     self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})
    #
    # # clear copper with 'rest-machining' algorithm
    # def clear_non_copper_rest(self, empty, over, pol_method, outname=None, connect=True, contour=True):
    #
    #     name = outname if outname is not None else self.obj_name + "_ncc_rm"
    #
    #     # Sort tools in descending order
    #     sorted_tools = []
    #     for k, v in self.ncc_tools.items():
    #         sorted_tools.append(float('%.4f' % float(v['tooldia'])))
    #     sorted_tools.sort(reverse=True)
    #
    #     # Do job in background
    #     proc = self.app.proc_container.new(_("Clearing Non-Copper areas."))
    #
    #     def initialize_rm(geo_obj, app_obj):
    #         assert isinstance(geo_obj, FlatCAMGeometry), \
    #             "Initializer expected a FlatCAMGeometry, got %s" % type(geo_obj)
    #
    #         cleared_geo = []
    #         cleared_by_last_tool = []
    #         rest_geo = []
    #         current_uid = 1
    #         tool = eval(self.app.defaults["tools_ncctools"])[0]
    #
    #         # repurposed flag for final object, geo_obj. True if it has any solid_geometry, False if not.
    #         app_obj.poly_not_cleared = True
    #
    #         area = empty.buffer(0)
    #         # Generate area for each tool
    #         while sorted_tools:
    #             tool = sorted_tools.pop(0)
    #             self.app.inform.emit(_('[success] Non-Copper Rest Clearing with ToolDia = %s started.') % str(tool))
    #
    #             tool_used = tool - 1e-12
    #             cleared_geo[:] = []
    #
    #             # Area to clear
    #             for poly in cleared_by_last_tool:
    #                 try:
    #                     area = area.difference(poly)
    #                 except Exception as e:
    #                     pass
    #             cleared_by_last_tool[:] = []
    #
    #             # Transform area to MultiPolygon
    #             if type(area) is Polygon:
    #                 area = MultiPolygon([area])
    #
    #             # add the rest that was not able to be cleared previously; area is a MultyPolygon
    #             # and rest_geo it's a list
    #             allparts = [p.buffer(0) for p in area.geoms]
    #             allparts += deepcopy(rest_geo)
    #             rest_geo[:] = []
    #             area = MultiPolygon(deepcopy(allparts))
    #             allparts[:] = []
    #
    #             if area.geoms:
    #                 if len(area.geoms) > 0:
    #                     for p in area.geoms:
    #                         try:
    #                             if pol_method == 'standard':
    #                                 cp = self.clear_polygon(p, tool_used, self.app.defaults["gerber_circle_steps"],
    #                                                         overlap=over, contour=contour, connect=connect)
    #                             elif pol_method == 'seed':
    #                                 cp = self.clear_polygon2(p, tool_used,
    #                                                          self.app.defaults["gerber_circle_steps"],
    #                                                          overlap=over, contour=contour, connect=connect)
    #                             else:
    #                                 cp = self.clear_polygon3(p, tool_used,
    #                                                          self.app.defaults["gerber_circle_steps"],
    #                                                          overlap=over, contour=contour, connect=connect)
    #                             cleared_geo.append(list(cp.get_objects()))
    #                         except:
    #                             log.warning("Polygon can't be cleared.")
    #                             # this polygon should be added to a list and then try clear it with a smaller tool
    #                             rest_geo.append(p)
    #
    #                     # check if there is a geometry at all in the cleared geometry
    #                     if cleared_geo:
    #                         # Overall cleared area
    #                         cleared_area = list(self.flatten_list(cleared_geo))
    #
    #                         # cleared = MultiPolygon([p.buffer(tool_used / 2).buffer(-tool_used / 2)
    #                         #                         for p in cleared_area])
    #
    #                         # here we store the poly's already processed in the original geometry by the current tool
    #                         # into cleared_by_last_tool list
    #                         # this will be sustracted from the original geometry_to_be_cleared and make data for
    #                         # the next tool
    #                         buffer_value = tool_used / 2
    #                         for p in cleared_area:
    #                             poly = p.buffer(buffer_value)
    #                             cleared_by_last_tool.append(poly)
    #
    #                         # find the tooluid associated with the current tool_dia so we know
    #                         # where to add the tool solid_geometry
    #                         for k, v in self.ncc_tools.items():
    #                             if float('%.4f' % v['tooldia']) == float('%.4f' % tool):
    #                                 current_uid = int(k)
    #
    #                                 # add the solid_geometry to the current too in self.paint_tools dictionary
    #                                 # and then reset the temporary list that stored that solid_geometry
    #                                 v['solid_geometry'] = deepcopy(cleared_area)
    #                                 v['data']['name'] = name
    #                                 cleared_area[:] = []
    #                                 break
    #
    #                         geo_obj.tools[current_uid] = dict(self.ncc_tools[current_uid])
    #                     else:
    #                         log.debug("There are no geometries in the cleared polygon.")
    #
    #         geo_obj.multigeo = True
    #         geo_obj.options["cnctooldia"] = str(tool)
    #
    #         # check to see if geo_obj.tools is empty
    #         # it will be updated only if there is a solid_geometry for tools
    #         if geo_obj.tools:
    #             return
    #         else:
    #             # I will use this variable for this purpose although it was meant for something else
    #             # signal that we have no geo in the object therefore don't create it
    #             app_obj.poly_not_cleared = False
    #             return "fail"
    #
    #     def job_thread(app_obj):
    #         try:
    #             app_obj.new_object("geometry", name, initialize_rm)
    #         except Exception as e:
    #             proc.done()
    #             app_obj.inform.emit(_('[ERROR_NOTCL] NCCTool.clear_non_copper_rest() --> %s') % str(e))
    #             return
    #
    #         if app_obj.poly_not_cleared is True:
    #             app_obj.inform.emit('[success] NCC Tool finished.')
    #             # focus on Selected Tab
    #             app_obj.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)
    #         else:
    #             app_obj.inform.emit(_('[ERROR_NOTCL] NCC Tool finished but could not clear the object '
    #                                  'with current settings.'))
    #             # focus on Project Tab
    #             app_obj.ui.notebook.setCurrentWidget(self.app.ui.project_tab)
    #         proc.done()
    #         # reset the variable for next use
    #         app_obj.poly_not_cleared = False
    #
    #     # Promise object with the new name
    #     self.app.collection.promise(name)
    #
    #     # Background
    #     self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})

    def get_ncc_empty_area(self, target, boundary=None):
        """
        Returns the complement of target geometry within
        the given boundary polygon. If not specified, it defaults to
        the rectangular bounding box of target geometry.
        """
        if isinstance(target, Polygon):
            geo_len = 1
        else:
            geo_len = len(target)
        pol_nr = 0
        old_disp_number = 0

        if boundary is None:
            boundary = target.envelope
        else:
            boundary = boundary
        try:
            ret_val = boundary.difference(target)
        except Exception as e:
            try:
                for el in target:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise FlatCAMApp.GracefulException
                    boundary = boundary.difference(el)
                    pol_nr += 1
                    disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))

                    if old_disp_number < disp_number <= 100:
                        self.app.proc_container.update_view_text(' %d%%' % disp_number)
                        old_disp_number = disp_number
                return boundary
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Try to use the Buffering Type = Full in Preferences -> Gerber General. "
                                       "Reload the Gerber file after this change."))
                return 'fail'

        return ret_val

    def reset_fields(self):
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))

    def reset_usage(self):
        self.obj_name = ""
        self.ncc_obj = None
        self.bound_obj = None

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False

        self.sel_rect = []

    @staticmethod
    def poly2rings(poly):
        return [poly.exterior] + [interior for interior in poly.interiors]

    def generate_envelope(self, offset, invert, envelope_iso_type=2, follow=None):
        # isolation_geometry produces an envelope that is going on the left of the geometry
        # (the copper features). To leave the least amount of burrs on the features
        # the tool needs to travel on the right side of the features (this is called conventional milling)
        # the first pass is the one cutting all of the features, so it needs to be reversed
        # the other passes overlap preceding ones and cut the left over copper. It is better for them
        # to cut on the right side of the left over copper i.e on the left side of the features.
        try:
            geom = self.isolation_geometry(offset, iso_type=envelope_iso_type, follow=follow)
        except Exception as e:
            log.debug('NonCopperClear.generate_envelope() --> %s' % str(e))
            return 'fail'

        if invert:
            try:
                try:
                    pl = []
                    for p in geom:
                        if p is not None:
                            if isinstance(p, Polygon):
                                pl.append(Polygon(p.exterior.coords[::-1], p.interiors))
                            elif isinstance(p, LinearRing):
                                pl.append(Polygon(p.coords[::-1]))
                    geom = MultiPolygon(pl)
                except TypeError:
                    if isinstance(geom, Polygon) and geom is not None:
                        geom = Polygon(geom.exterior.coords[::-1], geom.interiors)
                    elif isinstance(geom, LinearRing) and geom is not None:
                        geom = Polygon(geom.coords[::-1])
                    else:
                        log.debug("NonCopperClear.generate_envelope() Error --> Unexpected Geometry %s" %
                                  type(geom))
            except Exception as e:
                log.debug("NonCopperClear.generate_envelope() Error --> %s" % str(e))
                return 'fail'
        return geom
