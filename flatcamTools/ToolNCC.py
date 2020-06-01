# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Modified by: Marius Adrian Stanciu (c)              #
# Date: 3/10/2019                                          #
# MIT Licence                                              #
# ##########################################################

from PyQt5 import QtWidgets, QtCore, QtGui

from FlatCAMTool import FlatCAMTool
from flatcamGUI.GUIElements import FCCheckBox, FCDoubleSpinner, RadioSet, FCTable, FCInputDialog, FCButton,\
    FCComboBox, OptionalInputSection
from flatcamParsers.ParseGerber import Gerber

from FlatCAMCommon import GracefulException as grace

from copy import deepcopy

import numpy as np
import math
from shapely.geometry import base
from shapely.ops import cascaded_union
from shapely.geometry import MultiPolygon, Polygon, MultiLineString, LineString, LinearRing

from matplotlib.backend_bases import KeyEvent as mpl_key_event

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
        self.decimals = self.app.decimals

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
        # self.type_obj_radio = FCComboBox()
        # self.type_obj_radio.addItem("Gerber")
        # self.type_obj_radio.addItem("Excellon")
        # self.type_obj_radio.addItem("Geometry")
        #
        # # we get rid of item1 ("Excellon") as it is not suitable
        # self.type_obj_radio.view().setRowHidden(1, True)
        # self.type_obj_radio.setItemIcon(0, QtGui.QIcon(self.app.resource_location + "/flatcam_icon16.png"))
        # self.type_obj_radio.setItemIcon(2, QtGui.QIcon(self.app.resource_location + "/geometry16.png"))

        self.type_obj_combo_label = QtWidgets.QLabel('%s:' % _("Obj Type"))
        self.type_obj_combo_label.setToolTip(
            _("Specify the type of object to be cleared of excess copper.\n"
              "It can be of type: Gerber or Geometry.\n"
              "What is selected here will dictate the kind\n"
              "of objects that will populate the 'Object' combobox.")
        )
        self.type_obj_combo_label.setMinimumWidth(60)

        self.type_obj_radio = RadioSet([{'label': _("Geometry"), 'value': 'geometry'},
                                        {'label': _("Gerber"), 'value': 'gerber'}])

        form_layout.addRow(self.type_obj_combo_label, self.type_obj_radio)

        # ################################################
        # ##### The object to be copper cleaned ##########
        # ################################################
        self.object_combo = FCComboBox()
        self.object_combo.setModel(self.app.collection)
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        # self.object_combo.setCurrentIndex(1)
        self.object_combo.is_last = True

        self.object_label = QtWidgets.QLabel('%s:' % _("Object"))
        self.object_label.setToolTip(_("Object to be cleared of excess copper."))

        form_layout.addRow(self.object_label, self.object_combo)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.tools_box.addWidget(separator_line)

        # ### Tools ## ##
        self.tools_table_label = QtWidgets.QLabel('<b>%s</b>' % _('Tools Table'))
        self.tools_table_label.setToolTip(
            _("Tools pool from which the algorithm\n"
              "will pick the ones used for copper clearing.")
        )
        self.tools_box.addWidget(self.tools_table_label)

        self.tools_table = FCTable()
        self.tools_box.addWidget(self.tools_table)

        self.tools_table.setColumnCount(4)
        # 3rd column is reserved (and hidden) for the tool ID
        self.tools_table.setHorizontalHeaderLabels(['#', _('Diameter'), _('TT'), ''])
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
              "- V-Shape -> it will disable Z-Cut parameter in the resulting geometry UI form\n"
              "and enable two additional UI form fields in the resulting geometry: V-Tip Dia and\n"
              "V-Tip Angle. Adjusting those two values will adjust the Z-Cut parameter such\n"
              "as the cut width into material will be equal with the value in the Tool Diameter\n"
              "column of this table.\n"
              "Choosing the 'V-Shape' Tool Type automatically will select the Operation Type\n"
              "in the resulting geometry as Isolation."))

        # self.tools_table.horizontalHeaderItem(4).setToolTip(
        #     _("The 'Operation' can be:\n"
        #       "- Isolation -> will ensure that the non-copper clearing is always complete.\n"
        #       "If it's not successful then the non-copper clearing will fail, too.\n"
        #       "- Clear -> the regular non-copper clearing."))

        grid1 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid1)
        grid1.setColumnStretch(0, 0)
        grid1.setColumnStretch(1, 1)

        # Tool order
        self.ncc_order_label = QtWidgets.QLabel('%s:' % _('Tool order'))
        self.ncc_order_label.setToolTip(_("This set the way that the tools in the tools table are used.\n"
                                          "'No' --> means that the used order is the one in the tool table\n"
                                          "'Forward' --> means that the tools will be ordered from small to big\n"
                                          "'Reverse' --> means that the tools will ordered from big to small\n\n"
                                          "WARNING: using rest machining will automatically set the order\n"
                                          "in reverse and disable this control."))

        self.ncc_order_radio = RadioSet([{'label': _('No'), 'value': 'no'},
                                         {'label': _('Forward'), 'value': 'fwd'},
                                         {'label': _('Reverse'), 'value': 'rev'}])
        self.ncc_order_radio.setToolTip(_("This set the way that the tools in the tools table are used.\n"
                                          "'No' --> means that the used order is the one in the tool table\n"
                                          "'Forward' --> means that the tools will be ordered from small to big\n"
                                          "'Reverse' --> means that the tools will ordered from big to small\n\n"
                                          "WARNING: using rest machining will automatically set the order\n"
                                          "in reverse and disable this control."))

        grid1.addWidget(self.ncc_order_label, 1, 0)
        grid1.addWidget(self.ncc_order_radio, 1, 1)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        grid1.addWidget(separator_line, 2, 0, 1, 2)

        # #############################################################
        # ############### Tool selection ##############################
        # #############################################################

        self.grid3 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(self.grid3)
        self.grid3.setColumnStretch(0, 0)
        self.grid3.setColumnStretch(1, 1)

        self.tool_sel_label = QtWidgets.QLabel('<b>%s</b>' % _("New Tool"))
        self.grid3.addWidget(self.tool_sel_label, 1, 0, 1, 2)

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
        self.tool_type_radio.setObjectName(_("Tool Type"))

        self.grid3.addWidget(self.tool_type_label, 2, 0)
        self.grid3.addWidget(self.tool_type_radio, 2, 1)

        # Tip Dia
        self.tipdialabel = QtWidgets.QLabel('%s:' % _('V-Tip Dia'))
        self.tipdialabel.setToolTip(
            _("The tip diameter for V-Shape Tool"))
        self.tipdia_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.tipdia_entry.set_precision(self.decimals)
        self.tipdia_entry.set_range(0.0000, 9999.9999)
        self.tipdia_entry.setSingleStep(0.1)
        self.tipdia_entry.setObjectName(_("V-Tip Dia"))

        self.grid3.addWidget(self.tipdialabel, 3, 0)
        self.grid3.addWidget(self.tipdia_entry, 3, 1)

        # Tip Angle
        self.tipanglelabel = QtWidgets.QLabel('%s:' % _('V-Tip Angle'))
        self.tipanglelabel.setToolTip(
            _("The tip angle for V-Shape Tool.\n"
              "In degree."))
        self.tipangle_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.tipangle_entry.set_precision(self.decimals)
        self.tipangle_entry.set_range(0.0000, 180.0000)
        self.tipangle_entry.setSingleStep(5)
        self.tipangle_entry.setObjectName(_("V-Tip Angle"))

        self.grid3.addWidget(self.tipanglelabel, 4, 0)
        self.grid3.addWidget(self.tipangle_entry, 4, 1)

        # Cut Z entry
        cutzlabel = QtWidgets.QLabel('%s:' % _('Cut Z'))
        cutzlabel.setToolTip(
           _("Depth of cut into material. Negative value.\n"
             "In FlatCAM units.")
        )
        self.cutz_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.cutz_entry.set_precision(self.decimals)
        self.cutz_entry.set_range(-99999.9999, 0.0000)
        self.cutz_entry.setObjectName(_("Cut Z"))

        self.cutz_entry.setToolTip(
           _("Depth of cut into material. Negative value.\n"
             "In FlatCAM units.")
        )
        self.grid3.addWidget(cutzlabel, 5, 0)
        self.grid3.addWidget(self.cutz_entry, 5, 1)

        # ### Tool Diameter ####
        self.addtool_entry_lbl = QtWidgets.QLabel('<b>%s:</b>' % _('Tool Dia'))
        self.addtool_entry_lbl.setToolTip(
            _("Diameter for the new tool to add in the Tool Table.\n"
              "If the tool is V-shape type then this value is automatically\n"
              "calculated from the other parameters.")
        )
        self.addtool_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.addtool_entry.set_precision(self.decimals)
        self.addtool_entry.set_range(0.000, 9999.9999)
        self.addtool_entry.setObjectName(_("Tool Dia"))

        self.grid3.addWidget(self.addtool_entry_lbl, 6, 0)
        self.grid3.addWidget(self.addtool_entry, 6, 1)

        hlay = QtWidgets.QHBoxLayout()

        self.addtool_btn = QtWidgets.QPushButton(_('Add'))
        self.addtool_btn.setToolTip(
            _("Add a new tool to the Tool Table\n"
              "with the diameter specified above.")
        )

        self.addtool_from_db_btn = QtWidgets.QPushButton(_('Add from DB'))
        self.addtool_from_db_btn.setToolTip(
            _("Add a new tool to the Tool Table\n"
              "from the Tool DataBase.")
        )

        hlay.addWidget(self.addtool_btn)
        hlay.addWidget(self.addtool_from_db_btn)

        self.grid3.addLayout(hlay, 7, 0, 1, 2)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.grid3.addWidget(separator_line, 8, 0, 1, 2)

        self.deltool_btn = QtWidgets.QPushButton(_('Delete'))
        self.deltool_btn.setToolTip(
            _("Delete a selection of tools in the Tool Table\n"
              "by first selecting a row(s) in the Tool Table.")
        )
        self.grid3.addWidget(self.deltool_btn, 9, 0, 1, 2)

        self.grid3.addWidget(QtWidgets.QLabel(''), 10, 0, 1, 2)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.grid3.addWidget(separator_line, 11, 0, 1, 2)

        self.tool_data_label = QtWidgets.QLabel(
            "<b>%s: <font color='#0000FF'>%s %d</font></b>" % (_('Parameters for'), _("Tool"), int(1)))
        self.tool_data_label.setToolTip(
            _(
                "The data used for creating GCode.\n"
                "Each tool store it's own set of such data."
            )
        )
        self.grid3.addWidget(self.tool_data_label, 12, 0, 1, 2)

        # Operation
        op_label = QtWidgets.QLabel('%s:' % _('Operation'))
        op_label.setToolTip(
            _("The 'Operation' can be:\n"
              "- Isolation -> will ensure that the non-copper clearing is always complete.\n"
              "If it's not successful then the non-copper clearing will fail, too.\n"
              "- Clear -> the regular non-copper clearing.")
        )

        self.op_radio = RadioSet([
            {"label": _("Clear"), "value": "clear"},
            {"label": _("Isolation"), "value": "iso"}
        ], orientation='horizontal', stretch=False)
        self.op_radio.setObjectName("n_operation")

        self.grid3.addWidget(op_label, 13, 0)
        self.grid3.addWidget(self.op_radio, 13, 1)

        # Milling Type Radio Button
        self.milling_type_label = QtWidgets.QLabel('%s:' % _('Milling Type'))
        self.milling_type_label.setToolTip(
            _("Milling type when the selected tool is of type: 'iso_op':\n"
              "- climb / best for precision milling and to reduce tool usage\n"
              "- conventional / useful when there is no backlash compensation")
        )

        self.milling_type_radio = RadioSet([{'label': _('Climb'), 'value': 'cl'},
                                            {'label': _('Conventional'), 'value': 'cv'}])
        self.milling_type_radio.setToolTip(
            _("Milling type when the selected tool is of type: 'iso_op':\n"
              "- climb / best for precision milling and to reduce tool usage\n"
              "- conventional / useful when there is no backlash compensation")
        )
        self.milling_type_radio.setObjectName("n_milling_type")

        self.milling_type_label.setEnabled(False)
        self.milling_type_radio.setEnabled(False)

        self.grid3.addWidget(self.milling_type_label, 14, 0)
        self.grid3.addWidget(self.milling_type_radio, 14, 1)

        # Overlap Entry
        nccoverlabel = QtWidgets.QLabel('%s:' % _('Overlap'))
        nccoverlabel.setToolTip(
            _("How much (percentage) of the tool width to overlap each tool pass.\n"
              "Adjust the value starting with lower values\n"
              "and increasing it if areas that should be cleared are still \n"
              "not cleared.\n"
              "Lower values = faster processing, faster execution on CNC.\n"
              "Higher values = slow processing and slow execution on CNC\n"
              "due of too many paths.")
        )
        self.ncc_overlap_entry = FCDoubleSpinner(callback=self.confirmation_message, suffix='%')
        self.ncc_overlap_entry.set_precision(self.decimals)
        self.ncc_overlap_entry.setWrapping(True)
        self.ncc_overlap_entry.setRange(0.000, 99.9999)
        self.ncc_overlap_entry.setSingleStep(0.1)
        self.ncc_overlap_entry.setObjectName("n_overlap")

        self.grid3.addWidget(nccoverlabel, 15, 0)
        self.grid3.addWidget(self.ncc_overlap_entry, 15, 1)

        # Margin
        nccmarginlabel = QtWidgets.QLabel('%s:' % _('Margin'))
        nccmarginlabel.setToolTip(
            _("Bounding box margin.")
        )
        self.ncc_margin_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.ncc_margin_entry.set_precision(self.decimals)
        self.ncc_margin_entry.set_range(-9999.9999, 9999.9999)
        self.ncc_margin_entry.setObjectName("n_margin")

        self.grid3.addWidget(nccmarginlabel, 16, 0)
        self.grid3.addWidget(self.ncc_margin_entry, 16, 1)

        # Method
        methodlabel = QtWidgets.QLabel('%s:' % _('Method'))
        methodlabel.setToolTip(
            _("Algorithm for copper clearing:\n"
              "- Standard: Fixed step inwards.\n"
              "- Seed-based: Outwards from seed.\n"
              "- Line-based: Parallel lines.")
        )
        # self.ncc_method_radio = RadioSet([
        #     {"label": _("Standard"), "value": "standard"},
        #     {"label": _("Seed-based"), "value": "seed"},
        #     {"label": _("Straight lines"), "value": "lines"}
        # ], orientation='vertical', stretch=False)

        self.ncc_method_combo = FCComboBox()
        self.ncc_method_combo.addItems(
            [_("Standard"), _("Seed"), _("Lines")]
        )
        self.ncc_method_combo.setObjectName("n_method")

        self.grid3.addWidget(methodlabel, 17, 0)
        self.grid3.addWidget(self.ncc_method_combo, 17, 1)

        # Connect lines
        self.ncc_connect_cb = FCCheckBox('%s' % _("Connect"))
        self.ncc_connect_cb.setObjectName("n_connect")

        self.ncc_connect_cb.setToolTip(
            _("Draw lines between resulting\n"
              "segments to minimize tool lifts.")
        )
        self.grid3.addWidget(self.ncc_connect_cb, 18, 0)

        # Contour
        self.ncc_contour_cb = FCCheckBox('%s' % _("Contour"))
        self.ncc_contour_cb.setObjectName("n_contour")

        self.ncc_contour_cb.setToolTip(
            _("Cut around the perimeter of the polygon\n"
              "to trim rough edges.")
        )
        self.grid3.addWidget(self.ncc_contour_cb, 18, 1)

        # ## NCC Offset choice
        self.ncc_choice_offset_cb = FCCheckBox('%s' % _("Offset"))
        self.ncc_choice_offset_cb.setObjectName("n_offset")

        self.ncc_choice_offset_cb.setToolTip(
            _("If used, it will add an offset to the copper features.\n"
              "The copper clearing will finish to a distance\n"
              "from the copper features.\n"
              "The value can be between 0 and 10 FlatCAM units.")
        )
        self.grid3.addWidget(self.ncc_choice_offset_cb, 19, 0)

        # ## NCC Offset Entry
        self.ncc_offset_spinner = FCDoubleSpinner(callback=self.confirmation_message)
        self.ncc_offset_spinner.set_range(0.00, 10.00)
        self.ncc_offset_spinner.set_precision(4)
        self.ncc_offset_spinner.setWrapping(True)
        self.ncc_offset_spinner.setObjectName("n_offset_value")

        units = self.app.defaults['units'].upper()
        if units == 'MM':
            self.ncc_offset_spinner.setSingleStep(0.1)
        else:
            self.ncc_offset_spinner.setSingleStep(0.01)

        self.grid3.addWidget(self.ncc_offset_spinner, 19, 1)
        
        self.ois_ncc_offset = OptionalInputSection(self.ncc_choice_offset_cb, [self.ncc_offset_spinner])
        
        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.grid3.addWidget(separator_line, 21, 0, 1, 2)

        self.apply_param_to_all = FCButton(_("Apply parameters to all tools"))
        self.apply_param_to_all.setToolTip(
            _("The parameters in the current form will be applied\n"
              "on all the tools from the Tool Table.")
        )
        self.grid3.addWidget(self.apply_param_to_all, 22, 0, 1, 2)

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.grid3.addWidget(separator_line, 23, 0, 1, 2)

        # General Parameters
        self.gen_param_label = QtWidgets.QLabel('<b>%s</b>' % _("Common Parameters"))
        self.gen_param_label.setToolTip(
            _("Parameters that are common for all tools.")
        )
        self.grid3.addWidget(self.gen_param_label, 24, 0, 1, 2)

        # Rest Machining
        self.ncc_rest_cb = FCCheckBox('%s' % _("Rest Machining"))
        self.ncc_rest_cb.setObjectName("n_rest_machining")

        self.ncc_rest_cb.setToolTip(
            _("If checked, use 'rest machining'.\n"
              "Basically it will clear copper outside PCB features,\n"
              "using the biggest tool and continue with the next tools,\n"
              "from bigger to smaller, to clear areas of copper that\n"
              "could not be cleared by previous tool, until there is\n"
              "no more copper to clear or there are no more tools.\n"
              "If not checked, use the standard algorithm.")
        )

        self.grid3.addWidget(self.ncc_rest_cb, 25, 0, 1, 2)

        # ## Reference
        # self.select_radio = RadioSet([
        #     {'label': _('Itself'), 'value': 'itself'},
        #     {"label": _("Area Selection"), "value": "area"},
        #     {'label': _("Reference Object"), 'value': 'box'}
        # ], orientation='vertical', stretch=False)
        self.select_combo = FCComboBox()
        self.select_combo.addItems(
            [_("Itself"), _("Area Selection"), _("Reference Object")]
        )
        self.select_combo.setObjectName("n_selection")

        self.select_label = QtWidgets.QLabel('%s:' % _("Selection"))
        self.select_label.setToolTip(
            _("Selection of area to be processed.\n"
              "- 'Itself' - the processing extent is based on the object that is processed.\n "
              "- 'Area Selection' - left mouse click to start selection of the area to be processed.\n"
              "- 'Reference Object' - will process the area specified by another object.")
        )
        self.grid3.addWidget(self.select_label, 26, 0,)
        self.grid3.addWidget(self.select_combo, 26, 1)

        form1 = QtWidgets.QFormLayout()
        self.grid3.addLayout(form1, 28, 0, 1, 2)

        self.reference_combo_type_label = QtWidgets.QLabel('%s:' % _("Ref. Type"))
        self.reference_combo_type_label.setToolTip(
            _("The type of FlatCAM object to be used as non copper clearing reference.\n"
              "It can be Gerber, Excellon or Geometry.")
        )
        self.reference_combo_type = FCComboBox()
        self.reference_combo_type.addItems([_("Gerber"), _("Excellon"), _("Geometry")])

        form1.addRow(self.reference_combo_type_label, self.reference_combo_type)

        self.reference_combo_label = QtWidgets.QLabel('%s:' % _("Ref. Object"))
        self.reference_combo_label.setToolTip(
            _("The FlatCAM object to be used as non copper clearing reference.")
        )
        self.reference_combo = FCComboBox()
        self.reference_combo.setModel(self.app.collection)
        self.reference_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.reference_combo.is_last = True
        form1.addRow(self.reference_combo_label, self.reference_combo)

        self.reference_combo.hide()
        self.reference_combo_label.hide()
        self.reference_combo_type.hide()
        self.reference_combo_type_label.hide()

        # Area Selection shape
        self.area_shape_label = QtWidgets.QLabel('%s:' % _("Shape"))
        self.area_shape_label.setToolTip(
            _("The kind of selection shape used for area selection.")
        )

        self.area_shape_radio = RadioSet([{'label': _("Square"), 'value': 'square'},
                                          {'label': _("Polygon"), 'value': 'polygon'}])

        self.grid3.addWidget(self.area_shape_label, 29, 0)
        self.grid3.addWidget(self.area_shape_radio, 29, 1)

        self.area_shape_label.hide()
        self.area_shape_radio.hide()

        separator_line = QtWidgets.QFrame()
        separator_line.setFrameShape(QtWidgets.QFrame.HLine)
        separator_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        self.grid3.addWidget(separator_line, 30, 0, 1, 2)

        self.generate_ncc_button = QtWidgets.QPushButton(_('Generate Geometry'))
        self.generate_ncc_button.setToolTip(
            _("Create the Geometry Object\n"
              "for non-copper routing.")
        )
        self.generate_ncc_button.setStyleSheet("""
                        QPushButton
                        {
                            font-weight: bold;
                        }
                        """)
        self.tools_box.addWidget(self.generate_ncc_button)
        self.tools_box.addStretch()

        # ## Reset Tool
        self.reset_button = QtWidgets.QPushButton(_("Reset Tool"))
        self.reset_button.setToolTip(
            _("Will reset the tool parameters.")
        )
        self.reset_button.setStyleSheet("""
                        QPushButton
                        {
                            font-weight: bold;
                        }
                        """)
        self.tools_box.addWidget(self.reset_button)
        # ############################ FINSIHED GUI ###################################
        # #############################################################################

        # #############################################################################
        # ###################### Setup CONTEXT MENU ###################################
        # #############################################################################
        self.tools_table.setupContextMenu()
        self.tools_table.addContextMenu(
            _("Add"), self.on_add_tool_by_key, icon=QtGui.QIcon(self.app.resource_location + "/plus16.png")
        )
        self.tools_table.addContextMenu(
            _("Add from DB"), self.on_add_tool_by_key, icon=QtGui.QIcon(self.app.resource_location + "/plus16.png")
        )
        self.tools_table.addContextMenu(
            _("Delete"), lambda:
            self.on_tool_delete(rows_to_delete=None, all_tools=None),
            icon=QtGui.QIcon(self.app.resource_location + "/delete32.png")
        )

        # #############################################################################
        # ########################## VARIABLES ########################################
        # #############################################################################
        self.units = ''
        self.ncc_tools = {}
        self.tooluid = 0

        # store here the default data for Geometry Data
        self.default_data = {}

        self.obj_name = ""
        self.ncc_obj = None

        self.sel_rect = []

        self.bound_obj_name = ""
        self.bound_obj = None

        self.ncc_dia_list = []
        self.iso_dia_list = []
        self.has_offset = None
        self.o_name = None
        self.overlap = None
        self.connect = None
        self.contour = None
        self.rest = None

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False

        # store here the points for the "Polygon" area selection shape
        self.points = []
        # set this as True when in middle of drawing a "Polygon" area selection shape
        # it is made False by first click to signify that the shape is complete
        self.poly_drawn = False

        self.mm = None
        self.mr = None

        self.kp = None

        # store here solid_geometry when there are tool with isolation job
        self.solid_geometry = []

        self.select_method = None
        self.tool_type_item_options = []

        self.grb_circle_steps = int(self.app.defaults["gerber_circle_steps"])

        self.tooldia = None

        self.form_fields = {
            "tools_nccoperation": self.op_radio,
            "tools_nccoverlap": self.ncc_overlap_entry,
            "tools_nccmargin": self.ncc_margin_entry,
            "tools_nccmethod": self.ncc_method_combo,
            "tools_nccconnect": self.ncc_connect_cb,
            "tools_ncccontour": self.ncc_contour_cb,
            "tools_ncc_offset_choice": self.ncc_choice_offset_cb,
            "tools_ncc_offset_value": self.ncc_offset_spinner,
            "tools_nccmilling_type": self.milling_type_radio
        }

        self.name2option = {
            "n_operation": "tools_nccoperation",
            "n_overlap": "tools_nccoverlap",
            "n_margin": "tools_nccmargin",
            "n_method": "tools_nccmethod",
            "n_connect": "tools_nccconnect",
            "n_contour": "tools_ncccontour",
            "n_offset": "tools_ncc_offset_choice",
            "n_offset_value": "tools_ncc_offset_value",
            "n_milling_type": "tools_nccmilling_type",
        }

        self.old_tool_dia = None

        # #############################################################################
        # ############################ SIGNALS ########################################
        # #############################################################################
        self.addtool_btn.clicked.connect(self.on_tool_add)
        self.addtool_entry.returnPressed.connect(self.on_tooldia_updated)
        self.deltool_btn.clicked.connect(self.on_tool_delete)
        self.generate_ncc_button.clicked.connect(self.on_ncc_click)

        self.tipdia_entry.returnPressed.connect(self.on_calculate_tooldia)
        self.tipangle_entry.returnPressed.connect(self.on_calculate_tooldia)
        self.cutz_entry.returnPressed.connect(self.on_calculate_tooldia)

        self.op_radio.activated_custom.connect(self.on_operation_change)

        self.reference_combo_type.currentIndexChanged.connect(self.on_reference_combo_changed)
        self.select_combo.currentIndexChanged.connect(self.on_toggle_reference)

        self.ncc_rest_cb.stateChanged.connect(self.on_rest_machining_check)
        self.ncc_order_radio.activated_custom[str].connect(self.on_order_changed)

        self.type_obj_radio.activated_custom.connect(self.on_type_obj_index_changed)
        self.apply_param_to_all.clicked.connect(self.on_apply_param_to_all_clicked)
        self.addtool_from_db_btn.clicked.connect(self.on_ncc_tool_add_from_db_clicked)

        self.reset_button.clicked.connect(self.set_tool_ui)

        # Cleanup on Graceful exit (CTRL+ALT+X combo key)
        self.app.cleanup.connect(self.reset_usage)

    def on_type_obj_index_changed(self, val):
        obj_type = 0 if val == 'gerber' else 2
        self.object_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.object_combo.setCurrentIndex(0)
        self.object_combo.obj_type = {
            "gerber": "Gerber", "geometry": "Geometry"
        }[self.type_obj_radio.get_value()]

    def on_operation_change(self, val):
        if val == 'iso':
            self.milling_type_label.setEnabled(True)
            self.milling_type_radio.setEnabled(True)
        else:
            self.milling_type_label.setEnabled(False)
            self.milling_type_radio.setEnabled(False)

        current_row = self.tools_table.currentRow()
        try:
            current_uid = int(self.tools_table.item(current_row, 3).text())
            self.ncc_tools[current_uid]['data']['tools_nccoperation'] = val
        except AttributeError:
            return

    def on_row_selection_change(self):
        self.blockSignals(True)

        sel_rows = [it.row() for it in self.tools_table.selectedItems()]
        # sel_rows = sorted(set(index.row() for index in self.tools_table.selectedIndexes()))

        if not sel_rows:
            sel_rows = [0]

        for current_row in sel_rows:
            # populate the form with the data from the tool associated with the row parameter
            try:
                item = self.tools_table.item(current_row, 3)
                if item is not None:
                    tooluid = int(item.text())
                else:
                    return
            except Exception as e:
                log.debug("Tool missing. Add a tool in the Tool Table. %s" % str(e))
                return

            # update the QLabel that shows for which Tool we have the parameters in the UI form
            if len(sel_rows) == 1:
                cr = current_row + 1
                self.tool_data_label.setText(
                    "<b>%s: <font color='#0000FF'>%s %d</font></b>" % (_('Parameters for'), _("Tool"), cr)
                )
                try:
                    # set the form with data from the newly selected tool
                    for tooluid_key, tooluid_value in list(self.ncc_tools.items()):
                        if int(tooluid_key) == tooluid:
                            for key, value in tooluid_value.items():
                                if key == 'data':
                                    form_value_storage = tooluid_value[key]
                                    self.storage_to_form(form_value_storage)
                except Exception as e:
                    log.debug("NonCopperClear ---> update_ui() " + str(e))
            else:
                self.tool_data_label.setText(
                    "<b>%s: <font color='#0000FF'>%s</font></b>" % (_('Parameters for'), _("Multiple Tools"))
                )

        self.blockSignals(False)

    def storage_to_form(self, dict_storage):
        for form_key in self.form_fields:
            for storage_key in dict_storage:
                if form_key == storage_key:
                    try:
                        self.form_fields[form_key].set_value(dict_storage[form_key])
                    except Exception as e:
                        log.debug("NonCopperClear.storage_to_form() --> %s" % str(e))
                        pass

    def form_to_storage(self):
        if self.tools_table.rowCount() == 0:
            # there is no tool in tool table so we can't save the GUI elements values to storage
            return

        self.blockSignals(True)

        widget_changed = self.sender()
        wdg_objname = widget_changed.objectName()
        option_changed = self.name2option[wdg_objname]

        # row = self.tools_table.currentRow()
        rows = sorted(set(index.row() for index in self.tools_table.selectedIndexes()))
        for row in rows:
            if row < 0:
                row = 0
            tooluid_item = int(self.tools_table.item(row, 3).text())

            for tooluid_key, tooluid_val in self.ncc_tools.items():
                if int(tooluid_key) == tooluid_item:
                    new_option_value = self.form_fields[option_changed].get_value()
                    if option_changed in tooluid_val:
                        tooluid_val[option_changed] = new_option_value
                    if option_changed in tooluid_val['data']:
                        tooluid_val['data'][option_changed] = new_option_value

        self.blockSignals(False)

    def on_apply_param_to_all_clicked(self):
        if self.tools_table.rowCount() == 0:
            # there is no tool in tool table so we can't save the GUI elements values to storage
            log.debug("NonCopperClear.on_apply_param_to_all_clicked() --> no tool in Tools Table, aborting.")
            return

        self.blockSignals(True)

        row = self.tools_table.currentRow()
        if row < 0:
            row = 0

        tooluid_item = int(self.tools_table.item(row, 3).text())
        temp_tool_data = {}

        for tooluid_key, tooluid_val in self.ncc_tools.items():
            if int(tooluid_key) == tooluid_item:
                # this will hold the 'data' key of the self.tools[tool] dictionary that corresponds to
                # the current row in the tool table
                temp_tool_data = tooluid_val['data']
                break

        for tooluid_key, tooluid_val in self.ncc_tools.items():
            tooluid_val['data'] = deepcopy(temp_tool_data)

        # store all the data associated with the row parameter to the self.tools storage
        # tooldia_item = float(self.tools_table.item(row, 1).text())
        # type_item = self.tools_table.cellWidget(row, 2).currentText()
        # operation_type_item = self.tools_table.cellWidget(row, 4).currentText()
        #
        # nccoffset_item = self.ncc_choice_offset_cb.get_value()
        # nccoffset_value_item = float(self.ncc_offset_spinner.get_value())

        # this new dict will hold the actual useful data, another dict that is the value of key 'data'
        # temp_tools = {}
        # temp_dia = {}
        # temp_data = {}
        #
        # for tooluid_key, tooluid_value in self.ncc_tools.items():
        #     for key, value in tooluid_value.items():
        #         if key == 'data':
        #             # update the 'data' section
        #             for data_key in tooluid_value[key].keys():
        #                 for form_key, form_value in self.form_fields.items():
        #                     if form_key == data_key:
        #                         temp_data[data_key] = form_value.get_value()
        #                 # make sure we make a copy of the keys not in the form (we may use 'data' keys that are
        #                 # updated from self.app.defaults
        #                 if data_key not in self.form_fields:
        #                     temp_data[data_key] = value[data_key]
        #             temp_dia[key] = deepcopy(temp_data)
        #             temp_data.clear()
        #
        #         elif key == 'solid_geometry':
        #             temp_dia[key] = deepcopy(self.tools[tooluid_key]['solid_geometry'])
        #         else:
        #             temp_dia[key] = deepcopy(value)
        #
        #         temp_tools[tooluid_key] = deepcopy(temp_dia)
        #
        # self.ncc_tools.clear()
        # self.ncc_tools = deepcopy(temp_tools)
        # temp_tools.clear()

        self.app.inform.emit('[success] %s' % _("Current Tool parameters were applied to all tools."))

        self.blockSignals(False)

    def on_add_tool_by_key(self):
        tool_add_popup = FCInputDialog(title='%s...' % _("New Tool"),
                                       text='%s:' % _('Enter a Tool Diameter'),
                                       min=0.0001, max=9999.9999, decimals=self.decimals)
        tool_add_popup.setWindowIcon(QtGui.QIcon(self.app.resource_location + '/letter_t_32.png'))

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
        FlatCAMTool.install(self, icon, separator, shortcut='Alt+N', **kwargs)

    def run(self, toggle=True):
        self.app.defaults.report_usage("ToolNonCopperClear()")
        log.debug("ToolNCC().run() was launched ...")

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
        self.units = self.app.defaults['units'].upper()
        self.old_tool_dia = self.app.defaults["tools_nccnewdia"]

        self.tools_frame.show()

        self.type_obj_radio.set_value('gerber')

        # run those once so the obj_type attribute is updated for the FCComboboxes
        # so the last loaded object is displayed
        self.on_type_obj_index_changed(val="gerber")
        self.on_reference_combo_changed()

        self.op_radio.set_value(self.app.defaults["tools_nccoperation"])
        self.ncc_order_radio.set_value(self.app.defaults["tools_nccorder"])
        self.ncc_overlap_entry.set_value(self.app.defaults["tools_nccoverlap"])
        self.ncc_margin_entry.set_value(self.app.defaults["tools_nccmargin"])
        self.ncc_method_combo.set_value(self.app.defaults["tools_nccmethod"])
        self.ncc_connect_cb.set_value(self.app.defaults["tools_nccconnect"])
        self.ncc_contour_cb.set_value(self.app.defaults["tools_ncccontour"])
        self.ncc_rest_cb.set_value(self.app.defaults["tools_nccrest"])
        self.ncc_choice_offset_cb.set_value(self.app.defaults["tools_ncc_offset_choice"])
        self.ncc_offset_spinner.set_value(self.app.defaults["tools_ncc_offset_value"])

        self.select_combo.set_value(self.app.defaults["tools_nccref"])
        self.area_shape_radio.set_value(self.app.defaults["tools_ncc_area_shape"])

        self.milling_type_radio.set_value(self.app.defaults["tools_nccmilling_type"])
        self.cutz_entry.set_value(self.app.defaults["tools_ncccutz"])
        self.tool_type_radio.set_value(self.app.defaults["tools_ncctool_type"])
        self.tipdia_entry.set_value(self.app.defaults["tools_ncctipdia"])
        self.tipangle_entry.set_value(self.app.defaults["tools_ncctipangle"])
        self.addtool_entry.set_value(self.app.defaults["tools_nccnewdia"])

        self.old_tool_dia = self.app.defaults["tools_nccnewdia"]

        self.on_tool_type(val=self.tool_type_radio.get_value())

        # init the working variables
        self.default_data.clear()
        self.default_data = {
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
            "extracut_length": self.app.defaults["geometry_extracut_length"],
            "toolchange": self.app.defaults["geometry_toolchange"],
            "toolchangez": self.app.defaults["geometry_toolchangez"],
            "endz": self.app.defaults["geometry_endz"],
            "endxy": self.app.defaults["geometry_endxy"],

            "spindlespeed": self.app.defaults["geometry_spindlespeed"],
            "toolchangexy": self.app.defaults["geometry_toolchangexy"],
            "startz": self.app.defaults["geometry_startz"],

            "area_exclusion": self.app.defaults["geometry_area_exclusion"],
            "area_shape": self.app.defaults["geometry_area_shape"],
            "area_strategy": self.app.defaults["geometry_area_strategy"],
            "area_overz": float(self.app.defaults["geometry_area_overz"]),

            "tools_nccoperation": self.app.defaults["tools_nccoperation"],
            "tools_nccmargin": self.app.defaults["tools_nccmargin"],
            "tools_nccmethod": self.app.defaults["tools_nccmethod"],
            "tools_nccconnect": self.app.defaults["tools_nccconnect"],
            "tools_ncccontour": self.app.defaults["tools_ncccontour"],
            "tools_nccoverlap": self.app.defaults["tools_nccoverlap"],
            "nccrest": self.app.defaults["tools_nccrest"],
            "nccref": self.app.defaults["tools_nccref"],
            "tools_ncc_offset_choice": self.app.defaults["tools_ncc_offset_choice"],
            "tools_ncc_offset_value": self.app.defaults["tools_ncc_offset_value"],
            "tools_nccmilling_type": self.app.defaults["tools_nccmilling_type"],
        }

        try:
            dias = [float(self.app.defaults["tools_ncctools"])]
        except (ValueError, TypeError):
            dias = [float(eval(dia)) for dia in self.app.defaults["tools_ncctools"].split(",") if dia != '']

        if not dias:
            log.error("At least one tool diameter needed. Verify in Edit -> Preferences -> TOOLS -> NCC Tools.")
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
                    'data': deepcopy(self.default_data),
                    'solid_geometry': []
                }
            })

        self.obj_name = ""
        self.ncc_obj = None
        self.bound_obj_name = ""
        self.bound_obj = None

        self.tool_type_item_options = ["C1", "C2", "C3", "C4", "B", "V"]
        self.units = self.app.defaults['units'].upper()

    def build_ui(self):
        self.ui_disconnect()

        # updated units
        self.units = self.app.defaults['units'].upper()

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

                    tool_type_item = FCComboBox()
                    tool_type_item.addItems(self.tool_type_item_options)

                    # tool_type_item.setStyleSheet('background-color: rgb(255,255,255)')
                    idx = tool_type_item.findText(tooluid_value['tool_type'])
                    tool_type_item.setCurrentIndex(idx)

                    tool_uid_item = QtWidgets.QTableWidgetItem(str(int(tooluid_key)))

                    # operation_type = FCComboBox()
                    # operation_type.addItems(['iso_op', 'clear_op'])
                    #
                    # # operation_type.setStyleSheet('background-color: rgb(255,255,255)')
                    # op_idx = operation_type.findText(tooluid_value['operation'])
                    # operation_type.setCurrentIndex(op_idx)

                    self.tools_table.setItem(row_no, 1, dia)  # Diameter
                    self.tools_table.setCellWidget(row_no, 2, tool_type_item)

                    # ## REMEMBER: THIS COLUMN IS HIDDEN IN OBJECTUI.PY # ##
                    self.tools_table.setItem(row_no, 3, tool_uid_item)  # Tool unique ID

                    # self.tools_table.setCellWidget(row_no, 4, operation_type)

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

        # set the text on tool_data_label after loading the object
        sel_rows = []
        sel_items = self.tools_table.selectedItems()
        for it in sel_items:
            sel_rows.append(it.row())
        if len(sel_rows) > 1:
            self.tool_data_label.setText(
                "<b>%s: <font color='#0000FF'>%s</font></b>" % (_('Parameters for'), _("Multiple Tools"))
            )

    def ui_connect(self):
        self.tools_table.itemChanged.connect(self.on_tool_edit)

        # rows selected
        self.tools_table.clicked.connect(self.on_row_selection_change)
        self.tools_table.horizontalHeader().sectionClicked.connect(self.on_row_selection_change)

        for row in range(self.tools_table.rowCount()):
            try:
                self.tools_table.cellWidget(row, 2).currentIndexChanged.connect(self.on_tooltable_cellwidget_change)
            except AttributeError:
                pass

        self.tool_type_radio.activated_custom.connect(self.on_tool_type)

        for opt in self.form_fields:
            current_widget = self.form_fields[opt]
            if isinstance(current_widget, FCCheckBox):
                current_widget.stateChanged.connect(self.form_to_storage)
            if isinstance(current_widget, RadioSet):
                current_widget.activated_custom.connect(self.form_to_storage)
            elif isinstance(current_widget, FCDoubleSpinner):
                current_widget.returnPressed.connect(self.form_to_storage)
            elif isinstance(current_widget, FCComboBox):
                current_widget.currentIndexChanged.connect(self.form_to_storage)

        self.ncc_rest_cb.stateChanged.connect(self.on_rest_machining_check)
        self.ncc_order_radio.activated_custom[str].connect(self.on_order_changed)

    def ui_disconnect(self):

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tools_table.itemChanged.disconnect()
        except (TypeError, AttributeError):
            pass

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tool_type_radio.activated_custom.disconnect()
        except (TypeError, AttributeError):
            pass

        for row in range(self.tools_table.rowCount()):

            try:
                self.tools_table.cellWidget(row, 2).currentIndexChanged.disconnect()
            except (TypeError, AttributeError):
                pass

        for opt in self.form_fields:
            current_widget = self.form_fields[opt]
            if isinstance(current_widget, FCCheckBox):
                try:
                    current_widget.stateChanged.disconnect(self.form_to_storage)
                except (TypeError, ValueError):
                    pass
            if isinstance(current_widget, RadioSet):
                try:
                    current_widget.activated_custom.disconnect(self.form_to_storage)
                except (TypeError, ValueError):
                    pass
            elif isinstance(current_widget, FCDoubleSpinner):
                try:
                    current_widget.returnPressed.disconnect(self.form_to_storage)
                except (TypeError, ValueError):
                    pass
            elif isinstance(current_widget, FCComboBox):
                try:
                    current_widget.currentIndexChanged.disconnect(self.form_to_storage)
                except (TypeError, ValueError):
                    pass

        try:
            self.ncc_rest_cb.stateChanged.disconnect()
        except (TypeError, ValueError):
            pass
        try:
            self.ncc_order_radio.activated_custom[str].disconnect()
        except (TypeError, ValueError):
            pass

        # rows selected
        try:
            self.tools_table.clicked.disconnect()
        except (TypeError, AttributeError):
            pass
        try:
            self.tools_table.horizontalHeader().sectionClicked.disconnect()
        except (TypeError, AttributeError):
            pass

    def on_tooldia_updated(self):
        if self.tool_type_radio.get_value() == 'C1':
            self.old_tool_dia = self.addtool_entry.get_value()

    def on_reference_combo_changed(self):
        obj_type = self.reference_combo_type.currentIndex()
        self.reference_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.reference_combo.setCurrentIndex(0)
        self.reference_combo.obj_type = {
            _("Gerber"): "Gerber", _("Excellon"): "Excellon", _("Geometry"): "Geometry"
        }[self.reference_combo_type.get_value()]

    def on_toggle_reference(self):
        sel_combo = self.select_combo.get_value()

        if sel_combo == _("Itself"):
            self.reference_combo.hide()
            self.reference_combo_label.hide()
            self.reference_combo_type.hide()
            self.reference_combo_type_label.hide()
            self.area_shape_label.hide()
            self.area_shape_radio.hide()

            # disable rest-machining for area painting
            self.ncc_rest_cb.setDisabled(False)
        elif sel_combo == _("Area Selection"):
            self.reference_combo.hide()
            self.reference_combo_label.hide()
            self.reference_combo_type.hide()
            self.reference_combo_type_label.hide()
            self.area_shape_label.show()
            self.area_shape_radio.show()

            # disable rest-machining for area painting
            self.ncc_rest_cb.set_value(False)
            self.ncc_rest_cb.setDisabled(True)
        else:
            self.reference_combo.show()
            self.reference_combo_label.show()
            self.reference_combo_type.show()
            self.reference_combo_type_label.show()
            self.area_shape_label.hide()
            self.area_shape_radio.hide()

            # disable rest-machining for area painting
            self.ncc_rest_cb.setDisabled(False)

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
        assert isinstance(cw, QtWidgets.QComboBox),\
            "Expected a QtWidgets.QComboBox, got %s" % isinstance(cw, QtWidgets.QComboBox)

        cw_index = self.tools_table.indexAt(cw.pos())
        cw_row = cw_index.row()
        cw_col = cw_index.column()

        current_uid = int(self.tools_table.item(cw_row, 3).text())

        # if the sender is in the column with index 2 then we update the tool_type key
        if cw_col == 2:
            tt = cw.currentText()
            typ = 'Iso' if tt == 'V' else "Rough"

            self.ncc_tools[current_uid].update({
                'type': typ,
                'tool_type': tt,
            })

    def on_tool_type(self, val):
        if val == 'V':
            self.addtool_entry_lbl.setDisabled(True)
            self.addtool_entry.setDisabled(True)
            self.tipdialabel.show()
            self.tipdia_entry.show()
            self.tipanglelabel.show()
            self.tipangle_entry.show()

            self.on_calculate_tooldia()
        else:
            self.addtool_entry_lbl.setDisabled(False)
            self.addtool_entry.setDisabled(False)
            self.tipdialabel.hide()
            self.tipdia_entry.hide()
            self.tipanglelabel.hide()
            self.tipangle_entry.hide()

            self.addtool_entry.set_value(self.old_tool_dia)

    def on_calculate_tooldia(self):
        if self.tool_type_radio.get_value() == 'V':
            tip_dia = float(self.tipdia_entry.get_value())
            tip_angle = float(self.tipangle_entry.get_value()) / 2.0
            cut_z = float(self.cutz_entry.get_value())
            cut_z = -cut_z if cut_z < 0 else cut_z

            # calculated tool diameter so the cut_z parameter is obeyed
            tool_dia = tip_dia + (2 * cut_z * math.tan(math.radians(tip_angle)))

            # update the default_data so it is used in the ncc_tools dict
            self.default_data.update({
                "vtipdia": tip_dia,
                "vtipangle": (tip_angle * 2),
            })

            self.addtool_entry.set_value(tool_dia)

            return tool_dia
        else:
            return float(self.addtool_entry.get_value())

    def on_tool_add(self, dia=None, muted=None):
        self.blockSignals(True)

        self.units = self.app.defaults['units'].upper()

        if dia:
            tool_dia = dia
        else:
            tool_dia = self.on_calculate_tooldia()
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
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. Tool already in Tool Table."))
            # self.tools_table.itemChanged.connect(self.on_tool_edit)
            self.blockSignals(False)

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
                    'data': deepcopy(self.default_data),
                    'solid_geometry': []
                }
            })

        self.blockSignals(False)
        self.build_ui()

    def on_tool_edit(self):
        self.blockSignals(True)

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
                    self.app.inform.emit('[ERROR_NOTCL]  %s' % _("Wrong value format entered, use a number."))
                    self.blockSignals(False)
                    return

            tooluid = int(self.tools_table.item(row, 3).text())

            # identify the tool that was edited and get it's tooluid
            if new_tool_dia not in tool_dias:
                self.ncc_tools[tooluid]['tooldia'] = new_tool_dia
                self.app.inform.emit('[success] %s' % _("Tool from Tool Table was edited."))
                self.blockSignals(False)
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
                self.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. "
                                                              "New diameter value is already in the Tool Table."))
        self.blockSignals(False)
        self.build_ui()

    def on_tool_delete(self, rows_to_delete=None, all_tools=None):
        """
        Will delete a tool in the tool table

        :param rows_to_delete: which rows to delete; can be a list
        :param all_tools: delete all tools in the tool table
        :return:
        """
        self.blockSignals(True)

        deleted_tools_list = []

        if all_tools:
            self.ncc_tools.clear()
            self.blockSignals(False)
            self.build_ui()
            return

        if rows_to_delete:
            try:
                for row in rows_to_delete:
                    tooluid_del = int(self.tools_table.item(row, 3).text())
                    deleted_tools_list.append(tooluid_del)
            except TypeError:
                tooluid_del = int(self.tools_table.item(rows_to_delete, 3).text())
                deleted_tools_list.append(tooluid_del)

            for t in deleted_tools_list:
                self.ncc_tools.pop(t, None)

            self.blockSignals(False)
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
            self.blockSignals(False)
            return
        except Exception as e:
            log.debug(str(e))

        self.app.inform.emit('[success] %s' % _("Tool(s) deleted from Tool Table."))
        self.blockSignals(False)
        self.build_ui()

    def on_ncc_click(self):
        """
        Slot for clicking signal of the self.generate.ncc_button
        :return: None
        """

        # init values for the next usage
        self.reset_usage()

        self.app.defaults.report_usage("on_paint_button_click")

        self.grb_circle_steps = int(self.app.defaults["gerber_circle_steps"])
        self.obj_name = self.object_combo.currentText()

        # Get source object.
        try:
            self.ncc_obj = self.app.collection.get_by_name(self.obj_name)
        except Exception as e:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"),  str(self.obj_name)))
            return "Could not retrieve object: %s with error: %s" % (self.obj_name, str(e))

        if self.ncc_obj is None:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Object not found"), str(self.obj_name)))
            return

        # use the selected tools in the tool table; get diameters for non-copper clear
        self.iso_dia_list = []
        # use the selected tools in the tool table; get diameters for non-copper clear
        self.ncc_dia_list = []
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

                if self.op_radio.get_value() == _("Isolation"):
                    self.iso_dia_list.append(self.tooldia)
                else:
                    self.ncc_dia_list.append(self.tooldia)
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _("No selected tools in Tool Table."))
            return

        self.o_name = '%s_ncc' % self.obj_name

        self.select_method = self.select_combo.get_value()
        if self.select_method == _('Itself'):
            self.bound_obj_name = self.object_combo.currentText()
            # Get source object.
            try:
                self.bound_obj = self.app.collection.get_by_name(self.bound_obj_name)
            except Exception as e:
                self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), self.bound_obj_name))
                return "Could not retrieve object: %s with error: %s" % (self.bound_obj_name, str(e))

            self.clear_copper(ncc_obj=self.ncc_obj,
                              ncctooldia=self.ncc_dia_list,
                              isotooldia=self.iso_dia_list,
                              outname=self.o_name)
        elif self.select_method == _("Area Selection"):
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
            self.kp = self.app.plotcanvas.graph_event_connect('key_press', self.on_key_press)

        elif self.select_method == _("Reference Object"):
            self.bound_obj_name = self.reference_combo.currentText()
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
                              outname=self.o_name)

    # To be called after clicking on the plot.
    def on_mouse_release(self, event):
        if self.app.is_legacy is False:
            event_pos = event.pos
            # event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        event_pos = self.app.plotcanvas.translate_coords(event_pos)
        if self.app.grid_status():
            curr_pos = self.app.geo_editor.snap(event_pos[0], event_pos[1])
        else:
            curr_pos = (event_pos[0], event_pos[1])

        x1, y1 = curr_pos[0], curr_pos[1]

        shape_type = self.area_shape_radio.get_value()

        # do clear area only for left mouse clicks
        if event.button == 1:
            if shape_type == "square":
                if self.first_click is False:
                    self.first_click = True
                    self.app.inform.emit('[WARNING_NOTCL] %s' % _("Click the end point of the paint area."))

                    self.cursor_pos = self.app.plotcanvas.translate_coords(event_pos)
                    if self.app.grid_status():
                        self.cursor_pos = self.app.geo_editor.snap(event_pos[0], event_pos[1])
                else:
                    self.app.inform.emit(_("Zone added. Click to start adding next zone or right click to finish."))
                    self.app.delete_selection_shape()

                    x0, y0 = self.cursor_pos[0], self.cursor_pos[1]

                    pt1 = (x0, y0)
                    pt2 = (x1, y0)
                    pt3 = (x1, y1)
                    pt4 = (x0, y1)

                    new_rectangle = Polygon([pt1, pt2, pt3, pt4])
                    self.sel_rect.append(new_rectangle)

                    # add a temporary shape on canvas
                    self.draw_tool_selection_shape(old_coords=(x0, y0), coords=(x1, y1))

                    self.first_click = False
                    return
            else:
                self.points.append((x1, y1))

                if len(self.points) > 1:
                    self.poly_drawn = True
                    self.app.inform.emit(_("Click on next Point or click right mouse button to complete ..."))

                return ""
        elif event.button == right_button and self.mouse_is_dragging is False:

            shape_type = self.area_shape_radio.get_value()

            if shape_type == "square":
                self.first_click = False
            else:
                # if we finish to add a polygon
                if self.poly_drawn is True:
                    try:
                        # try to add the point where we last clicked if it is not already in the self.points
                        last_pt = (x1, y1)
                        if last_pt != self.points[-1]:
                            self.points.append(last_pt)
                    except IndexError:
                        pass

                    # we need to add a Polygon and a Polygon can be made only from at least 3 points
                    if len(self.points) > 2:
                        self.delete_moving_selection_shape()
                        pol = Polygon(self.points)
                        # do not add invalid polygons even if they are drawn by utility geometry
                        if pol.is_valid:
                            self.sel_rect.append(pol)
                            self.draw_selection_shape_polygon(points=self.points)
                            self.app.inform.emit(
                                _("Zone added. Click to start adding next zone or right click to finish."))

                    self.points = []
                    self.poly_drawn = False
                    return

            self.delete_tool_selection_shape()

            if self.app.is_legacy is False:
                self.app.plotcanvas.graph_event_disconnect('mouse_release', self.on_mouse_release)
                self.app.plotcanvas.graph_event_disconnect('mouse_move', self.on_mouse_move)
                self.app.plotcanvas.graph_event_disconnect('key_press', self.on_key_press)
            else:
                self.app.plotcanvas.graph_event_disconnect(self.mr)
                self.app.plotcanvas.graph_event_disconnect(self.mm)
                self.app.plotcanvas.graph_event_disconnect(self.kp)

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
                              outname=self.o_name)

    # called on mouse move
    def on_mouse_move(self, event):
        shape_type = self.area_shape_radio.get_value()

        if self.app.is_legacy is False:
            event_pos = event.pos
            event_is_dragging = event.is_dragging
            # right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            event_is_dragging = self.app.plotcanvas.is_dragging
            # right_button = 3

        curr_pos = self.app.plotcanvas.translate_coords(event_pos)

        # detect mouse dragging motion
        if event_is_dragging is True:
            self.mouse_is_dragging = True
        else:
            self.mouse_is_dragging = False

        # update the cursor position
        if self.app.grid_status():
            # Update cursor
            curr_pos = self.app.geo_editor.snap(curr_pos[0], curr_pos[1])

            self.app.app_cursor.set_data(np.asarray([(curr_pos[0], curr_pos[1])]),
                                         symbol='++', edge_color=self.app.cursor_color_3D,
                                         edge_width=self.app.defaults["global_cursor_width"],
                                         size=self.app.defaults["global_cursor_size"])

        if self.cursor_pos is None:
            self.cursor_pos = (0, 0)

        self.app.dx = curr_pos[0] - float(self.cursor_pos[0])
        self.app.dy = curr_pos[1] - float(self.cursor_pos[1])

        # # update the positions on status bar
        # self.app.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
        #                                    "<b>Y</b>: %.4f" % (curr_pos[0], curr_pos[1]))
        # self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
        #                                        "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (self.app.dx, self.app.dy))

        units = self.app.defaults["units"].lower()
        self.plotcanvas.text_hud.text = \
            'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
                self.app.dx, units, self.app.dy, units, curr_pos[0], units, curr_pos[1], units)

        # draw the utility geometry
        if shape_type == "square":
            if self.first_click:
                self.app.delete_selection_shape()
                self.app.draw_moving_selection_shape(old_coords=(self.cursor_pos[0], self.cursor_pos[1]),
                                                     coords=(curr_pos[0], curr_pos[1]))
        else:
            self.delete_moving_selection_shape()
            self.draw_moving_selection_shape_poly(points=self.points, data=(curr_pos[0], curr_pos[1]))

    def on_key_press(self, event):
        # modifiers = QtWidgets.QApplication.keyboardModifiers()
        # matplotlib_key_flag = False

        # events out of the self.app.collection view (it's about Project Tab) are of type int
        if type(event) is int:
            key = event
        # events from the GUI are of type QKeyEvent
        elif type(event) == QtGui.QKeyEvent:
            key = event.key()
        elif isinstance(event, mpl_key_event):  # MatPlotLib key events are trickier to interpret than the rest
            # matplotlib_key_flag = True

            key = event.key
            key = QtGui.QKeySequence(key)

            # check for modifiers
            key_string = key.toString().lower()
            if '+' in key_string:
                mod, __, key_text = key_string.rpartition('+')
                if mod.lower() == 'ctrl':
                    # modifiers = QtCore.Qt.ControlModifier
                    pass
                elif mod.lower() == 'alt':
                    # modifiers = QtCore.Qt.AltModifier
                    pass
                elif mod.lower() == 'shift':
                    # modifiers = QtCore.Qt.ShiftModifier
                    pass
                else:
                    # modifiers = QtCore.Qt.NoModifier
                    pass
                key = QtGui.QKeySequence(key_text)

        # events from Vispy are of type KeyEvent
        else:
            key = event.key

        if key == QtCore.Qt.Key_Escape or key == 'Escape':
            if self.app.is_legacy is False:
                self.app.plotcanvas.graph_event_disconnect('mouse_release', self.on_mouse_release)
                self.app.plotcanvas.graph_event_disconnect('mouse_move', self.on_mouse_move)
                self.app.plotcanvas.graph_event_disconnect('key_press', self.on_key_press)
            else:
                self.app.plotcanvas.graph_event_disconnect(self.mr)
                self.app.plotcanvas.graph_event_disconnect(self.mm)
                self.app.plotcanvas.graph_event_disconnect(self.kp)

            self.app.mp = self.app.plotcanvas.graph_event_connect('mouse_press',
                                                                  self.app.on_mouse_click_over_plot)
            self.app.mm = self.app.plotcanvas.graph_event_connect('mouse_move',
                                                                  self.app.on_mouse_move_over_plot)
            self.app.mr = self.app.plotcanvas.graph_event_connect('mouse_release',
                                                                  self.app.on_mouse_click_release_over_plot)
            self.points = []
            self.poly_drawn = False
            self.delete_moving_selection_shape()
            self.delete_tool_selection_shape()

    def envelope_object(self, ncc_obj, ncc_select, box_obj=None):
        """

        :param ncc_obj:
        :param box_obj:
        :param ncc_select:
        :return:
        """
        box_kind = box_obj.kind if box_obj is not None else None

        env_obj = None
        if ncc_select == _('Itself'):
            geo_n = ncc_obj.solid_geometry

            try:
                if isinstance(geo_n, MultiPolygon):
                    env_obj = geo_n.convex_hull
                elif (isinstance(geo_n, MultiPolygon) and len(geo_n) == 1) or \
                        (isinstance(geo_n, list) and len(geo_n) == 1) and isinstance(geo_n[0], Polygon):
                    env_obj = cascaded_union(geo_n)
                else:
                    env_obj = cascaded_union(geo_n)
                    env_obj = env_obj.convex_hull
            except Exception as e:
                log.debug("NonCopperClear.envelope_object() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return None
        elif ncc_select == _("Area Selection"):
            env_obj = cascaded_union(self.sel_rect)
            try:
                __ = iter(env_obj)
            except Exception:
                env_obj = [env_obj]
        elif ncc_select == _("Reference Object"):
            if box_obj is None:
                return None, None

            box_geo = box_obj.solid_geometry
            if box_kind == 'geometry':
                try:
                    __ = iter(box_geo)
                    env_obj = box_geo
                except Exception:
                    env_obj = [box_geo]

            elif box_kind == 'gerber':
                box_geo = cascaded_union(box_obj.solid_geometry).convex_hull
                ncc_geo = cascaded_union(ncc_obj.solid_geometry).convex_hull
                env_obj = ncc_geo.intersection(box_geo)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        return env_obj, box_kind

    def envelope_object_to_tool_bounding_box(self, env_obj, box_kind, ncc_select, ncc_margin):
        """
        Prepare non-copper polygons.
        Create the bounding box area from which the copper features will be subtracted

        :param env_obj:     the Geometry to be used as bounding box after applying the ncc_margin
        :param box_kind:    "geometry" or "gerber"
        :param ncc_select:  the kind of area to be copper cleared
        :param ncc_margin:  the margin around the area to be copper cleared
        :return:            an geometric element (Polygon or MultiPolygon) that specify the area to be copper cleared
        """

        log.debug("NCC Tool. Preparing non-copper polygons.")
        self.app.inform.emit(_("NCC Tool. Preparing non-copper polygons."))

        if env_obj is None:
            log.debug("NonCopperClear.envelope_object_to_tool_bounding_box() --> The object is None")
            return 'fail'

        bounding_box = None
        if ncc_select == _('Itself'):
            try:
                bounding_box = env_obj.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            except Exception as e:
                log.debug("NonCopperClear.envelope_object_to_tool_bounding_box() 'itself'  --> %s" % str(e))
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("No object available."))
                return 'fail'
        elif ncc_select == _("Area Selection"):
            geo_buff_list = []
            for poly in env_obj:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace
                geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))
            bounding_box = cascaded_union(geo_buff_list)
        elif ncc_select == _("Reference Object"):
            if box_kind == 'geometry':
                geo_buff_list = []
                for poly in env_obj:
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

                bounding_box = cascaded_union(geo_buff_list)
            elif box_kind == 'gerber':
                bounding_box = env_obj.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre)
            else:
                self.app.inform.emit('[ERROR_NOTCL] %s' % _("The reference object type is not supported."))
                return 'fail'

        log.debug("NCC Tool. Finished non-copper polygons.")
        return bounding_box

    def get_tool_empty_area(self, name, ncc_obj, geo_obj, isotooldia, has_offset, ncc_offset, ncc_margin,
                            bounding_box, tools_storage):
        """
        Calculate the empty area by subtracting the solid_geometry from the object bounding box geometry.

        :param name:
        :param ncc_obj:
        :param geo_obj:
        :param isotooldia:
        :param has_offset:
        :param ncc_offset:
        :param ncc_margin:
        :param bounding_box:
        :param tools_storage:
        :return:
        """

        log.debug("NCC Tool. Calculate 'empty' area.")
        self.app.inform.emit(_("NCC Tool. Calculate 'empty' area."))

        # a flag to signal that the isolation is broken by the bounding box in 'area' and 'box' cases
        # will store the number of tools for which the isolation is broken
        warning_flag = 0

        if ncc_obj.kind == 'gerber' and not isotooldia:
            # unfortunately for this function to work time efficient,
            # if the Gerber was loaded without buffering then it require the buffering now.
            if self.app.defaults['gerber_buffering'] == 'no':
                sol_geo = ncc_obj.solid_geometry.buffer(0)
            else:
                sol_geo = ncc_obj.solid_geometry

            if has_offset is True:
                self.app.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                if isinstance(sol_geo, list):
                    sol_geo = MultiPolygon(sol_geo)
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit('[success] %s ...' % _("Buffering finished"))

            empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
            if empty == 'fail':
                return 'fail'

            if empty.is_empty:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Could not get the extent of the area to be non copper cleared."))
                return 'fail'
        elif ncc_obj.kind == 'gerber' and isotooldia:
            isolated_geo = []

            # unfortunately for this function to work time efficient,
            # if the Gerber was loaded without buffering then it require the buffering now.
            # TODO 'buffering status' should be a property of the object not the project property
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
                    self.app.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                else:
                    if ncc_margin < tool_iso:
                        self.app.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                      "than isolation tool diameter."))
                    try:
                        for geo_elem in isolated_geo:
                            # provide the app with a way to process the GUI events when in a blocking loop
                            QtWidgets.QApplication.processEvents()

                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise grace

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

                    current_uid = 0
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
                self.app.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit('[success] %s ...' % _("Buffering finished"))

            empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
            if empty == 'fail':
                return 'fail'

            if empty.is_empty:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Isolation geometry is broken. Margin is less than isolation tool diameter."))
                return 'fail'
        elif ncc_obj.kind == 'geometry':
            sol_geo = cascaded_union(ncc_obj.solid_geometry)
            if has_offset is True:
                self.app.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                sol_geo = sol_geo.buffer(distance=ncc_offset)
                self.app.inform.emit('[success] %s ...' % _("Buffering finished"))
            empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
            if empty == 'fail':
                return 'fail'

            if empty.is_empty:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Could not get the extent of the area to be non copper cleared."))
                return 'fail'
        else:
            self.app.inform.emit('[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.'))
            return 'fail'

        if type(empty) is Polygon:
            empty = MultiPolygon([empty])

        log.debug("NCC Tool. Finished calculation of 'empty' area.")
        self.app.inform.emit(_("NCC Tool. Finished calculation of 'empty' area."))

        return empty, warning_flag

    def clear_copper(self, ncc_obj,
                     sel_obj=None,
                     ncctooldia=None,
                     isotooldia=None,
                     outname=None,
                     order=None,
                     tools_storage=None,
                     run_threaded=True):
        """
        Clear the excess copper from the entire object.

        :param ncc_obj:         ncc cleared object
        :param sel_obj:
        :param ncctooldia:      a tuple or single element made out of diameters of the tools to be used to ncc clear
        :param isotooldia:      a tuple or single element made out of diameters of the tools to be used for isolation
        :param outname:         name of the resulting object
        :param order:           Tools order
        :param tools_storage:   whether to use the current tools_storage self.ncc_tools or a different one.
                                Usage of the different one is related to when this function is called
                                from a TcL command.

        :param run_threaded: If True the method will be run in a threaded way suitable for GUI usage; if False it will
        run non-threaded for TclShell usage
        :return:
        """
        log.debug("Executing the handler ...")

        if run_threaded:
            proc = self.app.proc_container.new(_("Non-Copper clearing ..."))
        else:
            self.app.proc_container.view.set_busy(_("Non-Copper clearing ..."))
            QtWidgets.QApplication.processEvents()

        # #####################################################################
        # ####### Read the parameters #########################################
        # #####################################################################

        units = self.app.defaults['units']
        order = order if order else self.ncc_order_radio.get_value()
        ncc_select = self.select_combo.get_value()
        rest_machining_choice = self.ncc_rest_cb.get_value()

        # determine if to use the progressive plotting
        prog_plot = True if self.app.defaults["tools_ncc_plotting"] == 'progressive' else False
        tools_storage = tools_storage if tools_storage is not None else self.ncc_tools

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
            # for row in range(self.tools_table.rowCount()):
            #     if self.tools_table.cellWidget(row, 1).currentText() == 'clear_op':
            #         sorted_tools.append(float(self.tools_table.item(row, 1).text()))
            for tooluid in self.ncc_tools:
                if self.ncc_tools[tooluid]['data']['tools_nccoperation'] == 'clear':
                    sorted_tools.append(self.ncc_tools[tooluid]['tooldia'])

        # ########################################################################################################
        # set the name for the future Geometry object
        # I do it here because it is also stored inside the gen_clear_area() and gen_clear_area_rest() methods
        # ########################################################################################################
        name = outname if outname is not None else self.obj_name + "_ncc"

        # ##########################################################################################
        # Initializes the new geometry object ######################################################
        # ##########################################################################################
        def gen_clear_area(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

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

            if ncc_select == _("Reference Object"):
                env_obj, box_obj_kind = self.envelope_object(ncc_obj=ncc_obj, box_obj=sel_obj, ncc_select=ncc_select)
            else:
                env_obj, box_obj_kind = self.envelope_object(ncc_obj=ncc_obj, ncc_select=ncc_select)

            if env_obj is None and box_obj_kind is None:
                self.app.inform.emit("[ERROR_NOTCL] %s" % _("NCC Tool failed creating bounding box."))
                return "fail"

            # COPPER CLEARING #
            for tool in sorted_tools:
                log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool_uid = 0
                for k, v in self.ncc_tools.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool)):
                        tool_uid = int(k)
                        break

                ncc_overlap = float(self.ncc_tools[tool_uid]["data"]["tools_nccoverlap"]) / 100.0
                ncc_margin = float(self.ncc_tools[tool_uid]["data"]["tools_nccmargin"])
                ncc_method = self.ncc_tools[tool_uid]["data"]["tools_nccmethod"]
                ncc_connect = self.ncc_tools[tool_uid]["data"]["tools_nccconnect"]
                ncc_contour = self.ncc_tools[tool_uid]["data"]["tools_ncccontour"]
                has_offset = self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_choice"]
                ncc_offset = float(self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_value"])

                cleared_geo[:] = []

                # Get remaining tools offset
                offset -= (tool - 1e-12)

                # Bounding box for current tool
                bbox = self.envelope_object_to_tool_bounding_box(env_obj=env_obj, box_kind=box_obj_kind,
                                                                 ncc_select=ncc_select, ncc_margin=ncc_margin)

                # Area to clear
                empty, warning_flag = self.get_tool_empty_area(name=name, ncc_obj=ncc_obj, geo_obj=geo_obj,
                                                               isotooldia=isotooldia,
                                                               has_offset=has_offset,  ncc_offset=ncc_offset,
                                                               ncc_margin=ncc_margin, tools_storage=tools_storage,
                                                               bounding_box=bbox)

                area = empty.buffer(-offset)
                try:
                    area = area.difference(cleared)
                except Exception:
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
                                raise grace

                            # clean the polygon
                            p = p.buffer(0)

                            if p is not None and p.is_valid:
                                poly_processed = []
                                try:
                                    for pol in p:
                                        if pol is not None and isinstance(pol, Polygon):
                                            if ncc_method == _("Standard"):
                                                cp = self.clear_polygon(pol, tool,
                                                                        self.grb_circle_steps,
                                                                        overlap=ncc_overlap, contour=ncc_contour,
                                                                        connect=ncc_connect,
                                                                        prog_plot=prog_plot)
                                            elif ncc_method == _("Seed"):
                                                cp = self.clear_polygon2(pol, tool,
                                                                         self.grb_circle_steps,
                                                                         overlap=ncc_overlap, contour=ncc_contour,
                                                                         connect=ncc_connect,
                                                                         prog_plot=prog_plot)
                                            else:
                                                cp = self.clear_polygon3(pol, tool,
                                                                         self.grb_circle_steps,
                                                                         overlap=ncc_overlap, contour=ncc_contour,
                                                                         connect=ncc_connect,
                                                                         prog_plot=prog_plot)
                                            if cp:
                                                cleared_geo += list(cp.get_objects())
                                                poly_processed.append(True)
                                            else:
                                                poly_processed.append(False)
                                                log.warning("Polygon in MultiPolygon can not be cleared.")
                                        else:
                                            log.warning("Geo in Iterable can not be cleared because it is not Polygon. "
                                                        "It is: %s" % str(type(pol)))
                                except TypeError:
                                    if isinstance(p, Polygon):
                                        if ncc_method == _("Standard"):
                                            cp = self.clear_polygon(p, tool, self.grb_circle_steps,
                                                                    overlap=ncc_overlap, contour=ncc_contour,
                                                                    connect=ncc_connect,
                                                                    prog_plot=prog_plot)
                                        elif ncc_method == _("Seed"):
                                            cp = self.clear_polygon2(p, tool, self.grb_circle_steps,
                                                                     overlap=ncc_overlap, contour=ncc_contour,
                                                                     connect=ncc_connect,
                                                                     prog_plot=prog_plot)
                                        else:
                                            cp = self.clear_polygon3(p, tool, self.grb_circle_steps,
                                                                     overlap=ncc_overlap, contour=ncc_contour,
                                                                     connect=ncc_connect,
                                                                     prog_plot=prog_plot)
                                        if cp:
                                            cleared_geo += list(cp.get_objects())
                                            poly_processed.append(True)
                                        else:
                                            poly_processed.append(False)
                                            log.warning("Polygon can not be cleared.")
                                    else:
                                        log.warning("Geo can not be cleared because it is: %s" % str(type(p)))

                                p_cleared = poly_processed.count(True)
                                p_not_cleared = poly_processed.count(False)

                                if p_not_cleared:
                                    app_obj.poly_not_cleared = True

                                if p_cleared == 0:
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
                            cleared = empty.buffer(-offset * (1 + ncc_overlap)).buffer(-tool / 1.999999).buffer(
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
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid, uid_val in list(tools_storage.items()):
                try:
                    # if the solid_geometry (type=list) is empty
                    if not uid_val['solid_geometry']:
                        tools_storage.pop(uid, None)
                except KeyError:
                    tools_storage.pop(uid, None)

            geo_obj.options["cnctooldia"] = str(tool)

            geo_obj.multigeo = True
            geo_obj.tools.clear()
            geo_obj.tools = dict(tools_storage)

            # test if at least one tool has solid_geometry. If no tool has solid_geometry we raise an Exception
            has_solid_geo = 0
            for tid in geo_obj.tools:
                if geo_obj.tools[tid]['solid_geometry']:
                    has_solid_geo += 1
            if has_solid_geo == 0:
                app_obj.inform.emit('[ERROR] %s' %
                                    _("There is no NCC Geometry in the file.\n"
                                      "Usually it means that the tool diameter is too big for the painted geometry.\n"
                                      "Change the painting parameters and try again."))
                return 'fail'

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool clear all done."))
                else:
                    self.app.inform.emit('[WARNING] %s: %s %s.' % (
                        _("NCC Tool clear all done but the copper features isolation is broken for"),
                        str(warning_flag),
                        _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tool_id in geo_obj.tools:
                    if geo_obj.tools[tool_id]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tool_id]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tool_id]['solid_geometry'])
            else:
                # I will use this variable for this purpose although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

            # # Experimental...
            # # print("Indexing...", end=' ')
            # # geo_obj.make_index()

        # ###########################################################################################
        # Initializes the new geometry object for the case of the rest-machining ####################
        # ###########################################################################################
        def gen_clear_area_rest(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

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

            if ncc_select == _("Reference Object"):
                env_obj, box_obj_kind = self.envelope_object(ncc_obj=ncc_obj, box_obj=sel_obj, ncc_select=ncc_select)
            else:
                env_obj, box_obj_kind = self.envelope_object(ncc_obj=ncc_obj, ncc_select=ncc_select)

            if env_obj is None and box_obj_kind is None:
                self.app.inform.emit("[ERROR_NOTCL] %s" % _("NCC Tool failed creating bounding box."))
                return "fail"

            log.debug("NCC Tool. Calculate 'empty' area.")
            app_obj.inform.emit("NCC Tool. Calculate 'empty' area.")

            # Generate area for each tool
            while sorted_tools:
                log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool = sorted_tools.pop(0)

                tool_uid = 0
                for k, v in self.ncc_tools.items():
                    if float('%.*f' % (self.decimals, v['tooldia'])) == float('%.*f' % (self.decimals, tool)):
                        tool_uid = int(k)
                        break

                ncc_overlap = float(self.ncc_tools[tool_uid]["data"]["tools_nccoverlap"]) / 100.0
                ncc_margin = float(self.ncc_tools[tool_uid]["data"]["tools_nccmargin"])
                ncc_method = self.ncc_tools[tool_uid]["data"]["tools_nccmethod"]
                ncc_connect = self.ncc_tools[tool_uid]["data"]["tools_nccconnect"]
                ncc_contour = self.ncc_tools[tool_uid]["data"]["tools_ncccontour"]
                has_offset = self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_choice"]
                ncc_offset = float(self.ncc_tools[tool_uid]["data"]["tools_ncc_offset_value"])

                tool_used = tool - 1e-12
                cleared_geo[:] = []

                # Bounding box for current tool
                bbox = self.envelope_object_to_tool_bounding_box(env_obj=env_obj, box_kind=box_obj_kind,
                                                                 ncc_select=ncc_select, ncc_margin=ncc_margin)

                # Area to clear
                empty, warning_flag = self.get_tool_empty_area(name=name, ncc_obj=ncc_obj, geo_obj=geo_obj,
                                                               isotooldia=isotooldia,
                                                               has_offset=has_offset, ncc_offset=ncc_offset,
                                                               ncc_margin=ncc_margin, tools_storage=tools_storage,
                                                               bounding_box=bbox)

                area = empty.buffer(0)

                # Area to clear
                for poly in cleared_by_last_tool:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    try:
                        area = area.difference(poly)
                    except Exception:
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
                old_disp_number = 0
                log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if area.geoms:
                    if len(area.geoms) > 0:
                        pol_nr = 0
                        for p in area.geoms:
                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise grace

                            # clean the polygon
                            p = p.buffer(0)

                            if p is not None and p.is_valid:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if isinstance(p, Polygon):
                                    try:
                                        if ncc_method == _("Standard"):
                                            cp = self.clear_polygon(p, tool_used,
                                                                    self.grb_circle_steps,
                                                                    overlap=ncc_overlap, contour=ncc_contour,
                                                                    connect=ncc_connect,
                                                                    prog_plot=prog_plot)
                                        elif ncc_method == _("Seed"):
                                            cp = self.clear_polygon2(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=ncc_overlap, contour=ncc_contour,
                                                                     connect=ncc_connect,
                                                                     prog_plot=prog_plot)
                                        else:
                                            cp = self.clear_polygon3(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=ncc_overlap, contour=ncc_contour,
                                                                     connect=ncc_connect,
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
                                            # provide the app with a way to process the GUI events when
                                            # in a blocking loop
                                            QtWidgets.QApplication.processEvents()

                                            try:
                                                if ncc_method == _("Standard"):
                                                    cp = self.clear_polygon(poly, tool_used,
                                                                            self.grb_circle_steps,
                                                                            overlap=ncc_overlap, contour=ncc_contour,
                                                                            connect=ncc_connect,
                                                                            prog_plot=prog_plot)
                                                elif ncc_method == _("Seed"):
                                                    cp = self.clear_polygon2(poly, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=ncc_overlap, contour=ncc_contour,
                                                                             connect=ncc_connect,
                                                                             prog_plot=prog_plot)
                                                else:
                                                    cp = self.clear_polygon3(poly, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=ncc_overlap, contour=ncc_contour,
                                                                             connect=ncc_connect,
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
                            raise grace

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
                                    raise grace

                                poly = p.buffer(buffer_value)
                                cleared_by_last_tool.append(poly)

                            # find the tool uid associated with the current tool_dia so we know
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

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tool_uid in geo_obj.tools:
                    if geo_obj.tools[tool_uid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tool_uid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tool_uid]['solid_geometry'])
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
                    app_obj.new_object("geometry", name, gen_clear_area_rest)
                else:
                    app_obj.new_object("geometry", name, gen_clear_area)
            except grace:
                if run_threaded:
                    proc.done()
                return
            except Exception:
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

    def clear_copper_tcl(self, ncc_obj,
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
                         run_threaded=False):
        """
        Clear the excess copper from the entire object. To be used only in a TCL command.

        :param ncc_obj: ncc cleared object
        :param sel_obj:
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

        units = self.app.defaults['units']

        log.debug("NCC Tool started. Reading parameters.")
        self.app.inform.emit(_("NCC Tool started. Reading parameters."))

        ncc_method = method
        ncc_margin = margin
        ncc_select = select_method
        overlap = overlap

        connect = connect
        contour = contour
        order = order

        if tools_storage is not None:
            tools_storage = tools_storage
        else:
            tools_storage = self.ncc_tools

        ncc_offset = 0.0
        if has_offset is True:
            ncc_offset = offset

        # ######################################################################################################
        # # Read the tooldia parameter and create a sorted list out them - they may be more than one diameter ##
        # ######################################################################################################
        sorted_tools = []
        try:
            sorted_tools = [float(eval(dia)) for dia in ncctooldia.split(",") if dia != '']
        except AttributeError:
            if not isinstance(ncctooldia, list):
                sorted_tools = [float(ncctooldia)]
            else:
                sorted_tools = ncctooldia

        # ##############################################################################################################
        # Prepare non-copper polygons. Create the bounding box area from which the copper features will be subtracted ##
        # ##############################################################################################################
        log.debug("NCC Tool. Preparing non-copper polygons.")
        self.app.inform.emit(_("NCC Tool. Preparing non-copper polygons."))

        try:
            if sel_obj is None or sel_obj == _('Itself'):
                ncc_sel_obj = ncc_obj
            else:
                ncc_sel_obj = sel_obj
        except Exception as e:
            log.debug("NonCopperClear.clear_copper() --> %s" % str(e))
            return 'fail'

        bounding_box = None
        if ncc_select == _('Itself'):
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
                    raise grace
                geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

            bounding_box = cascaded_union(geo_buff_list)

        elif ncc_select == _("Reference Object"):
            geo_n = ncc_sel_obj.solid_geometry
            if ncc_sel_obj.kind == 'geometry':
                try:
                    __ = iter(geo_n)
                except Exception as e:
                    log.debug("NonCopperClear.clear_copper() 'Reference Object' --> %s" % str(e))
                    geo_n = [geo_n]

                geo_buff_list = []
                for poly in geo_n:
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    geo_buff_list.append(poly.buffer(distance=ncc_margin, join_style=base.JOIN_STYLE.mitre))

                bounding_box = cascaded_union(geo_buff_list)
            elif ncc_sel_obj.kind == 'gerber':
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
        rest_machining_choice = rest
        if rest_machining_choice is True:
            name = outname if outname is not None else self.obj_name + "_ncc_rm"
        else:
            name = outname if outname is not None else self.obj_name + "_ncc"

        # ##########################################################################################
        # Initializes the new geometry object ######################################################
        # ##########################################################################################
        def gen_clear_area(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

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
            offset_a = sum(sorted_tools)
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

            if ncc_obj.kind == 'gerber' and not isotooldia:
                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.defaults['gerber_buffering'] == 'no':
                    sol_geo = ncc_obj.solid_geometry.buffer(0)
                else:
                    sol_geo = ncc_obj.solid_geometry

                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))

                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            elif ncc_obj.kind == 'gerber' and isotooldia:
                isolated_geo = []

                # unfortunately for this function to work time efficient,
                # if the Gerber was loaded without buffering then it require the buffering now.
                if self.app.defaults['gerber_buffering'] == 'no':
                    self.solid_geometry = ncc_obj.solid_geometry.buffer(0)
                else:
                    self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.app.defaults["tools_nccmilling_type"]

                for tool_iso in isotooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso / 2, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso / 2, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        if ncc_margin < tool_iso:
                            app_obj.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                         "than isolation tool diameter."))
                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for a_poly in geo_elem:
                                        for ring in self.poly2rings(a_poly):
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
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Isolation geometry is broken. Margin is less than isolation tool diameter."))
                    return 'fail'

            elif ncc_obj.kind == 'geometry':
                sol_geo = cascaded_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'

            else:
                app_obj.inform.emit('[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.'))
                return 'fail'

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            log.debug("NCC Tool. Finished calculation of 'empty' area.")
            self.app.inform.emit(_("NCC Tool. Finished calculation of 'empty' area."))

            # COPPER CLEARING #
            for tool in sorted_tools:
                log.debug("Starting geometry processing for tool: %s" % str(tool))
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                # provide the app with a way to process the GUI events when in a blocking loop
                QtWidgets.QApplication.processEvents()

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                cleared_geo[:] = []

                # Get remaining tools offset
                offset_a -= (tool - 1e-12)

                # Area to clear
                area = empty.buffer(-offset_a)
                try:
                    area = area.difference(cleared)
                except Exception:
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
                                raise grace

                            # clean the polygon
                            p = p.buffer(0)

                            if p is not None and p.is_valid:
                                poly_processed = []
                                try:
                                    for pol in p:
                                        if pol is not None and isinstance(pol, Polygon):
                                            if ncc_method == 'standard':
                                                cp = self.clear_polygon(pol, tool,
                                                                        self.grb_circle_steps,
                                                                        overlap=overlap, contour=contour,
                                                                        connect=connect,
                                                                        prog_plot=False)
                                            elif ncc_method == 'seed':
                                                cp = self.clear_polygon2(pol, tool,
                                                                         self.grb_circle_steps,
                                                                         overlap=overlap, contour=contour,
                                                                         connect=connect,
                                                                         prog_plot=False)
                                            else:
                                                cp = self.clear_polygon3(pol, tool,
                                                                         self.grb_circle_steps,
                                                                         overlap=overlap, contour=contour,
                                                                         connect=connect,
                                                                         prog_plot=False)
                                            if cp:
                                                cleared_geo += list(cp.get_objects())
                                                poly_processed.append(True)
                                            else:
                                                poly_processed.append(False)
                                                log.warning("Polygon in MultiPolygon can not be cleared.")
                                        else:
                                            log.warning("Geo in Iterable can not be cleared because it is not Polygon. "
                                                        "It is: %s" % str(type(pol)))
                                except TypeError:
                                    if isinstance(p, Polygon):
                                        if ncc_method == 'standard':
                                            cp = self.clear_polygon(p, tool, self.grb_circle_steps,
                                                                    overlap=overlap, contour=contour, connect=connect,
                                                                    prog_plot=False)
                                        elif ncc_method == 'seed':
                                            cp = self.clear_polygon2(p, tool, self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=False)
                                        else:
                                            cp = self.clear_polygon3(p, tool, self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=False)
                                        if cp:
                                            cleared_geo += list(cp.get_objects())
                                            poly_processed.append(True)
                                        else:
                                            poly_processed.append(False)
                                            log.warning("Polygon can not be cleared.")
                                    else:
                                        log.warning("Geo can not be cleared because it is: %s" % str(type(p)))

                                p_cleared = poly_processed.count(True)
                                p_not_cleared = poly_processed.count(False)

                                if p_not_cleared:
                                    app_obj.poly_not_cleared = True

                                if p_cleared == 0:
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
                            cleared = empty.buffer(-offset_a * (1 + overlap)).buffer(-tool / 1.999999).buffer(
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

            # delete tools with empty geometry
            # look for keys in the tools_storage dict that have 'solid_geometry' values empty
            for uid, uid_val in list(tools_storage.items()):
                try:
                    # if the solid_geometry (type=list) is empty
                    if not uid_val['solid_geometry']:
                        tools_storage.pop(uid, None)
                except KeyError:
                    tools_storage.pop(uid, None)

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
                app_obj.inform.emit('[ERROR] %s' %
                                    _("There is no NCC Geometry in the file.\n"
                                      "Usually it means that the tool diameter is too big for the painted geometry.\n"
                                      "Change the painting parameters and try again."))
                return 'fail'

            # check to see if geo_obj.tools is empty
            # it will be updated only if there is a solid_geometry for tools
            if geo_obj.tools:
                if warning_flag == 0:
                    self.app.inform.emit('[success] %s' % _("NCC Tool clear all done."))
                else:
                    self.app.inform.emit('[WARNING] %s: %s %s.' % (
                        _("NCC Tool clear all done but the copper features isolation is broken for"),
                        str(warning_flag),
                        _("tools")))
                    return

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tooluid in geo_obj.tools:
                    if geo_obj.tools[tooluid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tooluid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tooluid]['solid_geometry'])
            else:
                # I will use this variable for this purpose although it was meant for something else
                # signal that we have no geo in the object therefore don't create it
                app_obj.poly_not_cleared = False
                return "fail"

        # ###########################################################################################
        # Initializes the new geometry object for the case of the rest-machining ####################
        # ###########################################################################################
        def gen_clear_area_rest(geo_obj, app_obj):
            assert geo_obj.kind == 'geometry', \
                "Initializer expected a GeometryObject, got %s" % type(geo_obj)

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
            if ncc_obj.kind == 'gerber' and not isotooldia:
                sol_geo = ncc_obj.solid_geometry
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            elif ncc_obj.kind == 'gerber' and isotooldia:
                isolated_geo = []
                self.solid_geometry = ncc_obj.solid_geometry

                # if milling type is climb then the move is counter-clockwise around features
                milling_type = self.app.defaults["tools_nccmilling_type"]

                for tool_iso in isotooldia:
                    new_geometry = []

                    if milling_type == 'cl':
                        isolated_geo = self.generate_envelope(tool_iso, 1)
                    else:
                        isolated_geo = self.generate_envelope(tool_iso, 0)

                    if isolated_geo == 'fail':
                        app_obj.inform.emit('[ERROR_NOTCL] %s' % _("Isolation geometry could not be generated."))
                    else:
                        app_obj.inform.emit('[WARNING_NOTCL] %s' % _("Isolation geometry is broken. Margin is less "
                                                                     "than isolation tool diameter."))

                        try:
                            for geo_elem in isolated_geo:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                if isinstance(geo_elem, Polygon):
                                    for ring in self.poly2rings(geo_elem):
                                        new_geo = ring.intersection(bounding_box)
                                        if new_geo and not new_geo.is_empty:
                                            new_geometry.append(new_geo)
                                elif isinstance(geo_elem, MultiPolygon):
                                    for poly_g in geo_elem:
                                        for ring in self.poly2rings(poly_g):
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
                            except Exception:
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
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Isolation geometry is broken. Margin is less than isolation tool diameter."))
                    return 'fail'

            elif ncc_obj.kind == 'geometry':
                sol_geo = cascaded_union(ncc_obj.solid_geometry)
                if has_offset is True:
                    app_obj.inform.emit('[WARNING_NOTCL] %s ...' % _("Buffering"))
                    sol_geo = sol_geo.buffer(distance=ncc_offset)
                    app_obj.inform.emit('[success] %s ...' % _("Buffering finished"))
                empty = self.get_ncc_empty_area(target=sol_geo, boundary=bounding_box)
                if empty == 'fail':
                    return 'fail'

                if empty.is_empty:
                    app_obj.inform.emit('[ERROR_NOTCL] %s' %
                                        _("Could not get the extent of the area to be non copper cleared."))
                    return 'fail'
            else:
                app_obj.inform.emit('[ERROR_NOTCL] %s' % _('The selected object is not suitable for copper clearing.'))
                return

            if self.app.abort_flag:
                # graceful abort requested by the user
                raise grace

            if type(empty) is Polygon:
                empty = MultiPolygon([empty])

            area = empty.buffer(0)

            log.debug("NCC Tool. Finished calculation of 'empty' area.")
            app_obj.inform.emit("NCC Tool. Finished calculation of 'empty' area.")

            # Generate area for each tool
            while sorted_tools:
                if self.app.abort_flag:
                    # graceful abort requested by the user
                    raise grace

                tool = sorted_tools.pop(0)
                log.debug("Starting geometry processing for tool: %s" % str(tool))

                app_obj.inform.emit('[success] %s = %s%s %s' % (
                    _('NCC Tool clearing with tool diameter'), str(tool), units.lower(), _('started.'))
                )
                app_obj.proc_container.update_view_text(' %d%%' % 0)

                tool_used = tool - 1e-12
                cleared_geo[:] = []

                # Area to clear
                for poly_r in cleared_by_last_tool:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()

                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace
                    try:
                        area = area.difference(poly_r)
                    except Exception:
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
                old_disp_number = 0
                log.warning("Total number of polygons to be cleared. %s" % str(geo_len))

                if area.geoms:
                    if len(area.geoms) > 0:
                        pol_nr = 0
                        for p in area.geoms:
                            if self.app.abort_flag:
                                # graceful abort requested by the user
                                raise grace

                            # clean the polygon
                            p = p.buffer(0)

                            if p is not None and p.is_valid:
                                # provide the app with a way to process the GUI events when in a blocking loop
                                QtWidgets.QApplication.processEvents()

                                if isinstance(p, Polygon):
                                    try:
                                        if ncc_method == 'standard':
                                            cp = self.clear_polygon(p, tool_used,
                                                                    self.grb_circle_steps,
                                                                    overlap=overlap, contour=contour, connect=connect,
                                                                    prog_plot=False)
                                        elif ncc_method == 'seed':
                                            cp = self.clear_polygon2(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=False)
                                        else:
                                            cp = self.clear_polygon3(p, tool_used,
                                                                     self.grb_circle_steps,
                                                                     overlap=overlap, contour=contour, connect=connect,
                                                                     prog_plot=False)
                                        cleared_geo.append(list(cp.get_objects()))
                                    except Exception as ee:
                                        log.warning("Polygon can't be cleared. %s" % str(ee))
                                        # this polygon should be added to a list and then try clear it with
                                        # a smaller tool
                                        rest_geo.append(p)
                                elif isinstance(p, MultiPolygon):
                                    for poly_p in p:
                                        if poly_p is not None:
                                            # provide the app with a way to process the GUI events when
                                            # in a blocking loop
                                            QtWidgets.QApplication.processEvents()

                                            try:
                                                if ncc_method == 'standard':
                                                    cp = self.clear_polygon(poly_p, tool_used,
                                                                            self.grb_circle_steps,
                                                                            overlap=overlap, contour=contour,
                                                                            connect=connect,
                                                                            prog_plot=False)
                                                elif ncc_method == 'seed':
                                                    cp = self.clear_polygon2(poly_p, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=False)
                                                else:
                                                    cp = self.clear_polygon3(poly_p, tool_used,
                                                                             self.grb_circle_steps,
                                                                             overlap=overlap, contour=contour,
                                                                             connect=connect,
                                                                             prog_plot=False)
                                                cleared_geo.append(list(cp.get_objects()))
                                            except Exception as eee:
                                                log.warning("Polygon can't be cleared. %s" % str(eee))
                                                # this polygon should be added to a list and then try clear it with
                                                # a smaller tool
                                                rest_geo.append(poly_p)

                                pol_nr += 1
                                disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                                # log.debug("Polygons cleared: %d" % pol_nr)

                                if old_disp_number < disp_number <= 100:
                                    self.app.proc_container.update_view_text(' %d%%' % disp_number)
                                    old_disp_number = disp_number
                                    # log.debug("Polygons cleared: %d. Percentage done: %d%%" % (pol_nr, disp_number))

                        if self.app.abort_flag:
                            # graceful abort requested by the user
                            raise grace

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
                                    raise grace

                                r_poly = p.buffer(buffer_value)
                                cleared_by_last_tool.append(r_poly)

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

                # create the solid_geometry
                geo_obj.solid_geometry = []
                for tooluid in geo_obj.tools:
                    if geo_obj.tools[tooluid]['solid_geometry']:
                        try:
                            for geo in geo_obj.tools[tooluid]['solid_geometry']:
                                geo_obj.solid_geometry.append(geo)
                        except TypeError:
                            geo_obj.solid_geometry.append(geo_obj.tools[tooluid]['solid_geometry'])
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
            except grace:
                if run_threaded:
                    proc.done()
                return
            except Exception:
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

    def get_ncc_empty_area(self, target, boundary=None):
        """
        Returns the complement of target geometry within
        the given boundary polygon. If not specified, it defaults to
        the rectangular bounding box of target geometry.

        :param target:      The geometry that is to be 'inverted'
        :param boundary:    A polygon that surrounds the entire solid geometry and from which we subtract in order to
                            create a "negative" geometry (geometry to be emptied of copper)
        :return:
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
        except Exception:
            try:
                for el in target:
                    # provide the app with a way to process the GUI events when in a blocking loop
                    QtWidgets.QApplication.processEvents()
                    if self.app.abort_flag:
                        # graceful abort requested by the user
                        raise grace

                    boundary = boundary.difference(el)
                    pol_nr += 1
                    disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))

                    if old_disp_number < disp_number <= 100:
                        self.app.proc_container.update_view_text(' %d%%' % disp_number)
                        old_disp_number = disp_number
                return boundary
            except Exception:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("Try to use the Buffering Type = Full in Preferences -> Gerber General. "
                                       "Reload the Gerber file after this change."))
                return 'fail'

        return ret_val

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

    def on_ncc_tool_add_from_db_executed(self, tool):
        """
        Here add the tool from DB  in the selected geometry object
        :return:
        """
        tool_from_db = deepcopy(tool)

        res = self.on_ncc_tool_from_db_inserted(tool=tool_from_db)

        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                wdg = self.app.ui.plot_tab_area.widget(idx)
                wdg.deleteLater()
                self.app.ui.plot_tab_area.removeTab(idx)

        if res == 'fail':
            return
        self.app.inform.emit('[success] %s' % _("Tool from DB added in Tool Table."))

        # select last tool added
        toolid = res
        for row in range(self.tools_table.rowCount()):
            if int(self.tools_table.item(row, 3).text()) == toolid:
                self.tools_table.selectRow(row)
        self.on_row_selection_change()

    def on_ncc_tool_from_db_inserted(self, tool):
        """
        Called from the Tools DB object through a App method when adding a tool from Tools Database
        :param tool: a dict with the tool data
        :return: None
        """

        self.ui_disconnect()
        self.units = self.app.defaults['units'].upper()

        tooldia = float(tool['tooldia'])

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
        tooluid = max_uid + 1

        tooldia = float('%.*f' % (self.decimals, tooldia))

        tool_dias = []
        for k, v in self.ncc_tools.items():
            for tool_v in v.keys():
                if tool_v == 'tooldia':
                    tool_dias.append(float('%.*f' % (self.decimals, (v[tool_v]))))

        if float('%.*f' % (self.decimals, tooldia)) in tool_dias:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Cancelled. Tool already in Tool Table."))
            self.ui_connect()
            return 'fail'

        self.ncc_tools.update({
            tooluid: {
                'tooldia': float('%.*f' % (self.decimals, tooldia)),
                'offset': tool['offset'],
                'offset_value': tool['offset_value'],
                'type': tool['type'],
                'tool_type': tool['tool_type'],
                'data': deepcopy(tool['data']),
                'solid_geometry': []
            }
        })
        self.ncc_tools[tooluid]['data']['name'] = '_ncc'

        self.app.inform.emit('[success] %s' % _("New tool added to Tool Table."))

        self.ui_connect()
        self.build_ui()

        # if self.tools_table.rowCount() != 0:
        #     self.param_frame.setDisabled(False)

    def on_ncc_tool_add_from_db_clicked(self):
        """
        Called when the user wants to add a new tool from Tools Database. It will create the Tools Database object
        and display the Tools Database tab in the form needed for the Tool adding
        :return: None
        """

        # if the Tools Database is already opened focus on it
        for idx in range(self.app.ui.plot_tab_area.count()):
            if self.app.ui.plot_tab_area.tabText(idx) == _("Tools Database"):
                self.app.ui.plot_tab_area.setCurrentWidget(self.app.tools_db_tab)
                break
        self.app.on_tools_database(source='ncc')
        self.app.tools_db_tab.ok_to_add = True
        self.app.tools_db_tab.buttons_frame.hide()
        self.app.tools_db_tab.add_tool_from_db.show()
        self.app.tools_db_tab.cancel_tool_from_db.show()

    def reset_fields(self):
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))

    def reset_usage(self):
        self.obj_name = ""
        self.ncc_obj = None
        self.bound_obj = None

        self.first_click = False
        self.cursor_pos = None
        self.mouse_is_dragging = False

        prog_plot = True if self.app.defaults["tools_ncc_plotting"] == 'progressive' else False
        if prog_plot:
            self.temp_shapes.clear(update=True)

        self.sel_rect = []
