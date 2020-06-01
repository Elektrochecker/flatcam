# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Author: Marius Adrian Stanciu (c)                   #
# Date: 3/10/2019                                          #
# MIT Licence                                              #
# ##########################################################

from PyQt5 import QtWidgets, QtGui, QtCore
from FlatCAMTool import FlatCAMTool

from flatcamGUI.GUIElements import FCSpinner, FCDoubleSpinner, RadioSet, FCCheckBox, OptionalInputSection, FCComboBox
from FlatCAMCommon import GracefulException as grace
from copy import deepcopy
import numpy as np

import shapely.affinity as affinity
from shapely.ops import unary_union
from shapely.geometry import LineString

import gettext
import FlatCAMTranslation as fcTranslate
import builtins
import logging

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class Panelize(FlatCAMTool):

    toolName = _("Panelize PCB")

    def __init__(self, app):
        self.decimals = app.decimals

        FlatCAMTool.__init__(self, app)

        # ## Title
        title_label = QtWidgets.QLabel("%s" % self.toolName)
        title_label.setStyleSheet("""
                        QLabel
                        {
                            font-size: 16px;
                            font-weight: bold;
                        }
                        """)
        self.layout.addWidget(title_label)

        self.layout.addWidget(QtWidgets.QLabel(''))

        self.object_label = QtWidgets.QLabel('<b>%s:</b>' % _("Source Object"))
        self.object_label.setToolTip(
            _("Specify the type of object to be panelized\n"
              "It can be of type: Gerber, Excellon or Geometry.\n"
              "The selection here decide the type of objects that will be\n"
              "in the Object combobox.")
        )

        self.layout.addWidget(self.object_label)

        # Form Layout
        form_layout_0 = QtWidgets.QFormLayout()
        self.layout.addLayout(form_layout_0)

        # Type of object to be panelized
        self.type_obj_combo = FCComboBox()
        self.type_obj_combo.addItem("Gerber")
        self.type_obj_combo.addItem("Excellon")
        self.type_obj_combo.addItem("Geometry")

        self.type_obj_combo.setItemIcon(0, QtGui.QIcon(self.app.resource_location + "/flatcam_icon16.png"))
        self.type_obj_combo.setItemIcon(1, QtGui.QIcon(self.app.resource_location + "/drill16.png"))
        self.type_obj_combo.setItemIcon(2, QtGui.QIcon(self.app.resource_location + "/geometry16.png"))

        self.type_object_label = QtWidgets.QLabel('%s:' % _("Object Type"))

        form_layout_0.addRow(self.type_object_label, self.type_obj_combo)

        # Object to be panelized
        self.object_combo = FCComboBox()
        self.object_combo.setModel(self.app.collection)
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.object_combo.is_last = True

        self.object_combo.setToolTip(
            _("Object to be panelized. This means that it will\n"
              "be duplicated in an array of rows and columns.")
        )
        form_layout_0.addRow(self.object_combo)
        form_layout_0.addRow(QtWidgets.QLabel(""))

        # Form Layout
        form_layout = QtWidgets.QFormLayout()
        self.layout.addLayout(form_layout)

        # Type of box Panel object
        self.reference_radio = RadioSet([{'label': _('Object'), 'value': 'object'},
                                         {'label': _('Bounding Box'), 'value': 'bbox'}])
        self.box_label = QtWidgets.QLabel("<b>%s:</b>" % _("Penelization Reference"))
        self.box_label.setToolTip(
            _("Choose the reference for panelization:\n"
              "- Object = the bounding box of a different object\n"
              "- Bounding Box = the bounding box of the object to be panelized\n"
              "\n"
              "The reference is useful when doing panelization for more than one\n"
              "object. The spacings (really offsets) will be applied in reference\n"
              "to this reference object therefore maintaining the panelized\n"
              "objects in sync.")
        )
        form_layout.addRow(self.box_label)
        form_layout.addRow(self.reference_radio)

        # Type of Box Object to be used as an envelope for panelization
        self.type_box_combo = FCComboBox()
        self.type_box_combo.addItems([_("Gerber"), _("Geometry")])

        # we get rid of item1 ("Excellon") as it is not suitable for use as a "box" for panelizing
        # self.type_box_combo.view().setRowHidden(1, True)
        self.type_box_combo.setItemIcon(0, QtGui.QIcon(self.app.resource_location + "/flatcam_icon16.png"))
        self.type_box_combo.setItemIcon(1, QtGui.QIcon(self.app.resource_location + "/geometry16.png"))

        self.type_box_combo_label = QtWidgets.QLabel('%s:' % _("Box Type"))
        self.type_box_combo_label.setToolTip(
            _("Specify the type of object to be used as an container for\n"
              "panelization. It can be: Gerber or Geometry type.\n"
              "The selection here decide the type of objects that will be\n"
              "in the Box Object combobox.")
        )
        form_layout.addRow(self.type_box_combo_label, self.type_box_combo)

        # Box
        self.box_combo = FCComboBox()
        self.box_combo.setModel(self.app.collection)
        self.box_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.box_combo.is_last = True

        self.box_combo.setToolTip(
            _("The actual object that is used as container for the\n "
              "selected object that is to be panelized.")
        )
        form_layout.addRow(self.box_combo)
        form_layout.addRow(QtWidgets.QLabel(""))

        panel_data_label = QtWidgets.QLabel("<b>%s:</b>" % _("Panel Data"))
        panel_data_label.setToolTip(
            _("This informations will shape the resulting panel.\n"
              "The number of rows and columns will set how many\n"
              "duplicates of the original geometry will be generated.\n"
              "\n"
              "The spacings will set the distance between any two\n"
              "elements of the panel array.")
        )
        form_layout.addRow(panel_data_label)

        # Spacing Columns
        self.spacing_columns = FCDoubleSpinner(callback=self.confirmation_message)
        self.spacing_columns.set_range(0, 9999)
        self.spacing_columns.set_precision(4)

        self.spacing_columns_label = QtWidgets.QLabel('%s:' % _("Spacing cols"))
        self.spacing_columns_label.setToolTip(
            _("Spacing between columns of the desired panel.\n"
              "In current units.")
        )
        form_layout.addRow(self.spacing_columns_label, self.spacing_columns)

        # Spacing Rows
        self.spacing_rows = FCDoubleSpinner(callback=self.confirmation_message)
        self.spacing_rows.set_range(0, 9999)
        self.spacing_rows.set_precision(4)

        self.spacing_rows_label = QtWidgets.QLabel('%s:' % _("Spacing rows"))
        self.spacing_rows_label.setToolTip(
            _("Spacing between rows of the desired panel.\n"
              "In current units.")
        )
        form_layout.addRow(self.spacing_rows_label, self.spacing_rows)

        # Columns
        self.columns = FCSpinner(callback=self.confirmation_message_int)
        self.columns.set_range(0, 9999)

        self.columns_label = QtWidgets.QLabel('%s:' % _("Columns"))
        self.columns_label.setToolTip(
            _("Number of columns of the desired panel")
        )
        form_layout.addRow(self.columns_label, self.columns)

        # Rows
        self.rows = FCSpinner(callback=self.confirmation_message_int)
        self.rows.set_range(0, 9999)

        self.rows_label = QtWidgets.QLabel('%s:' % _("Rows"))
        self.rows_label.setToolTip(
            _("Number of rows of the desired panel")
        )
        form_layout.addRow(self.rows_label, self.rows)
        form_layout.addRow(QtWidgets.QLabel(""))

        # Type of resulting Panel object
        self.panel_type_radio = RadioSet([{'label': _('Gerber'), 'value': 'gerber'},
                                          {'label': _('Geo'), 'value': 'geometry'}])
        self.panel_type_label = QtWidgets.QLabel("<b>%s:</b>" % _("Panel Type"))
        self.panel_type_label.setToolTip(
            _("Choose the type of object for the panel object:\n"
              "- Geometry\n"
              "- Gerber")
        )
        form_layout.addRow(self.panel_type_label)
        form_layout.addRow(self.panel_type_radio)

        # Constrains
        self.constrain_cb = FCCheckBox('%s:' % _("Constrain panel within"))
        self.constrain_cb.setToolTip(
            _("Area define by DX and DY within to constrain the panel.\n"
              "DX and DY values are in current units.\n"
              "Regardless of how many columns and rows are desired,\n"
              "the final panel will have as many columns and rows as\n"
              "they fit completely within selected area.")
        )
        form_layout.addRow(self.constrain_cb)

        self.x_width_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.x_width_entry.set_precision(4)
        self.x_width_entry.set_range(0, 9999)

        self.x_width_lbl = QtWidgets.QLabel('%s:' % _("Width (DX)"))
        self.x_width_lbl.setToolTip(
            _("The width (DX) within which the panel must fit.\n"
              "In current units.")
        )
        form_layout.addRow(self.x_width_lbl, self.x_width_entry)

        self.y_height_entry = FCDoubleSpinner(callback=self.confirmation_message)
        self.y_height_entry.set_range(0, 9999)
        self.y_height_entry.set_precision(4)

        self.y_height_lbl = QtWidgets.QLabel('%s:' % _("Height (DY)"))
        self.y_height_lbl.setToolTip(
            _("The height (DY)within which the panel must fit.\n"
              "In current units.")
        )
        form_layout.addRow(self.y_height_lbl, self.y_height_entry)

        self.constrain_sel = OptionalInputSection(
            self.constrain_cb, [self.x_width_lbl, self.x_width_entry, self.y_height_lbl, self.y_height_entry])

        # Buttons
        self.panelize_object_button = QtWidgets.QPushButton(_("Panelize Object"))
        self.panelize_object_button.setToolTip(
            _("Panelize the specified object around the specified box.\n"
              "In other words it creates multiple copies of the source object,\n"
              "arranged in a 2D array of rows and columns.")
        )
        self.panelize_object_button.setStyleSheet("""
                        QPushButton
                        {
                            font-weight: bold;
                        }
                        """)
        self.layout.addWidget(self.panelize_object_button)

        self.layout.addStretch()

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
        self.layout.addWidget(self.reset_button)

        # Signals
        self.reference_radio.activated_custom.connect(self.on_reference_radio_changed)
        self.panelize_object_button.clicked.connect(self.on_panelize)
        self.type_obj_combo.currentIndexChanged.connect(self.on_type_obj_index_changed)
        self.type_box_combo.currentIndexChanged.connect(self.on_type_box_index_changed)
        self.reset_button.clicked.connect(self.set_tool_ui)

        # list to hold the temporary objects
        self.objs = []

        # final name for the panel object
        self.outname = ""

        # flag to signal the constrain was activated
        self.constrain_flag = False

    def run(self, toggle=True):
        self.app.defaults.report_usage("ToolPanelize()")

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

        self.app.ui.notebook.setTabText(2, _("Panel. Tool"))

    def install(self, icon=None, separator=None, **kwargs):
        FlatCAMTool.install(self, icon, separator, shortcut='Alt+Z', **kwargs)

    def set_tool_ui(self):
        self.reset_fields()

        self.reference_radio.set_value('bbox')

        sp_c = self.app.defaults["tools_panelize_spacing_columns"] if \
            self.app.defaults["tools_panelize_spacing_columns"] else 0.0
        self.spacing_columns.set_value(float(sp_c))

        sp_r = self.app.defaults["tools_panelize_spacing_rows"] if \
            self.app.defaults["tools_panelize_spacing_rows"] else 0.0
        self.spacing_rows.set_value(float(sp_r))

        rr = self.app.defaults["tools_panelize_rows"] if \
            self.app.defaults["tools_panelize_rows"] else 0.0
        self.rows.set_value(int(rr))

        cc = self.app.defaults["tools_panelize_columns"] if \
            self.app.defaults["tools_panelize_columns"] else 0.0
        self.columns.set_value(int(cc))

        c_cb = self.app.defaults["tools_panelize_constrain"] if \
            self.app.defaults["tools_panelize_constrain"] else False
        self.constrain_cb.set_value(c_cb)

        x_w = self.app.defaults["tools_panelize_constrainx"] if \
            self.app.defaults["tools_panelize_constrainx"] else 0.0
        self.x_width_entry.set_value(float(x_w))

        y_w = self.app.defaults["tools_panelize_constrainy"] if \
            self.app.defaults["tools_panelize_constrainy"] else 0.0
        self.y_height_entry.set_value(float(y_w))

        panel_type = self.app.defaults["tools_panelize_panel_type"] if \
            self.app.defaults["tools_panelize_panel_type"] else 'gerber'
        self.panel_type_radio.set_value(panel_type)

        # run once the following so the obj_type attribute is updated in the FCComboBoxes
        # such that the last loaded object is populated in the combo boxes
        self.on_type_obj_index_changed()
        self.on_type_box_index_changed()

    def on_type_obj_index_changed(self):
        obj_type = self.type_obj_combo.currentIndex()
        self.object_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.object_combo.setCurrentIndex(0)
        self.object_combo.obj_type = {
            _("Gerber"): "Gerber", _("Excellon"): "Excellon", _("Geometry"): "Geometry"
        }[self.type_obj_combo.get_value()]

        # hide the panel type for Excellons, the panel can be only of type Geometry
        if self.type_obj_combo.currentText() != 'Excellon':
            self.panel_type_label.setDisabled(False)
            self.panel_type_radio.setDisabled(False)
        else:
            self.panel_type_label.setDisabled(True)
            self.panel_type_radio.setDisabled(True)
            self.panel_type_radio.set_value('geometry')

    def on_type_box_index_changed(self):
        obj_type = self.type_box_combo.currentIndex()
        self.box_combo.setRootModelIndex(self.app.collection.index(obj_type, 0, QtCore.QModelIndex()))
        self.box_combo.setCurrentIndex(0)
        self.box_combo.obj_type = {
            _("Gerber"): "Gerber", _("Geometry"): "Geometry"
        }[self.type_box_combo.get_value()]

    def on_reference_radio_changed(self, current_val):
        if current_val == 'object':
            self.type_box_combo.setDisabled(False)
            self.type_box_combo_label.setDisabled(False)
            self.box_combo.setDisabled(False)
        else:
            self.type_box_combo.setDisabled(True)
            self.type_box_combo_label.setDisabled(True)
            self.box_combo.setDisabled(True)

    def on_panelize(self):
        name = self.object_combo.currentText()

        # Get source object to be panelized.
        try:
            panel_source_obj = self.app.collection.get_by_name(str(name))
        except Exception as e:
            log.debug("Panelize.on_panelize() --> %s" % str(e))
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), name))
            return "Could not retrieve object: %s" % name

        if panel_source_obj is None:
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' %
                                 (_("Object not found"), panel_source_obj))
            return "Object not found: %s" % panel_source_obj

        boxname = self.box_combo.currentText()

        try:
            box = self.app.collection.get_by_name(boxname)
        except Exception as e:
            log.debug("Panelize.on_panelize() --> %s" % str(e))
            self.app.inform.emit('[ERROR_NOTCL] %s: %s' % (_("Could not retrieve object"), boxname))
            return "Could not retrieve object: %s" % boxname

        if box is None:
            self.app.inform.emit('[WARNING_NOTCL]%s: %s' % (_("No object Box. Using instead"), panel_source_obj))
            self.reference_radio.set_value('bbox')

        if self.reference_radio.get_value() == 'bbox':
            box = panel_source_obj

        self.outname = name + '_panelized'

        spacing_columns = float(self.spacing_columns.get_value())
        spacing_columns = spacing_columns if spacing_columns is not None else 0

        spacing_rows = float(self.spacing_rows.get_value())
        spacing_rows = spacing_rows if spacing_rows is not None else 0

        rows = int(self.rows.get_value())
        rows = rows if rows is not None else 1

        columns = int(self.columns.get_value())
        columns = columns if columns is not None else 1

        constrain_dx = float(self.x_width_entry.get_value())
        constrain_dy = float(self.y_height_entry.get_value())

        panel_type = str(self.panel_type_radio.get_value())

        if 0 in {columns, rows}:
            self.app.inform.emit('[ERROR_NOTCL] %s' %
                                 _("Columns or Rows are zero value. Change them to a positive integer."))
            return "Columns or Rows are zero value. Change them to a positive integer."

        xmin, ymin, xmax, ymax = box.bounds()
        lenghtx = xmax - xmin + spacing_columns
        lenghty = ymax - ymin + spacing_rows

        # check if constrain within an area is desired
        if self.constrain_cb.isChecked():
            panel_lengthx = ((xmax - xmin) * columns) + (spacing_columns * (columns - 1))
            panel_lengthy = ((ymax - ymin) * rows) + (spacing_rows * (rows - 1))

            # adjust the number of columns and/or rows so the panel will fit within the panel constraint area
            if (panel_lengthx > constrain_dx) or (panel_lengthy > constrain_dy):
                self.constrain_flag = True

                while panel_lengthx > constrain_dx:
                    columns -= 1
                    panel_lengthx = ((xmax - xmin) * columns) + (spacing_columns * (columns - 1))
                while panel_lengthy > constrain_dy:
                    rows -= 1
                    panel_lengthy = ((ymax - ymin) * rows) + (spacing_rows * (rows - 1))

        if panel_source_obj.kind == 'excellon' or panel_source_obj.kind == 'geometry':
            # make a copy of the panelized Excellon or Geometry tools
            copied_tools = {}
            for tt, tt_val in list(panel_source_obj.tools.items()):
                copied_tools[tt] = deepcopy(tt_val)

        if panel_source_obj.kind == 'gerber':
            # make a copy of the panelized Gerber apertures
            copied_apertures = {}
            for tt, tt_val in list(panel_source_obj.apertures.items()):
                copied_apertures[tt] = deepcopy(tt_val)

        def panelize_worker():
            if panel_source_obj is not None:
                self.app.inform.emit(_("Generating panel ... "))

                def job_init_excellon(obj_fin, app_obj):
                    currenty = 0.0
                    obj_fin.tools = copied_tools
                    obj_fin.drills = []
                    obj_fin.slots = []
                    obj_fin.solid_geometry = []

                    for option in panel_source_obj.options:
                        if option != 'name':
                            try:
                                obj_fin.options[option] = panel_source_obj.options[option]
                            except KeyError:
                                log.warning("Failed to copy option. %s" % str(option))

                    geo_len_drills = len(panel_source_obj.drills) if panel_source_obj.drills else 0
                    geo_len_slots = len(panel_source_obj.slots) if panel_source_obj.slots else 0

                    element = 0
                    for row in range(rows):
                        currentx = 0.0
                        for col in range(columns):
                            element += 1
                            old_disp_number = 0

                            if panel_source_obj.drills:
                                drill_nr = 0
                                for tool_dict in panel_source_obj.drills:
                                    if self.app.abort_flag:
                                        # graceful abort requested by the user
                                        raise grace

                                    point_offseted = affinity.translate(tool_dict['point'], currentx, currenty)
                                    obj_fin.drills.append(
                                        {
                                            "point": point_offseted,
                                            "tool": tool_dict['tool']
                                        }
                                    )

                                    drill_nr += 1
                                    disp_number = int(np.interp(drill_nr, [0, geo_len_drills], [0, 100]))

                                    if old_disp_number < disp_number <= 100:
                                        self.app.proc_container.update_view_text(' %s: %d D:%d%%' %
                                                                                 (_("Copy"),
                                                                                  int(element),
                                                                                  disp_number))
                                        old_disp_number = disp_number

                            if panel_source_obj.slots:
                                slot_nr = 0
                                for tool_dict in panel_source_obj.slots:
                                    if self.app.abort_flag:
                                        # graceful abort requested by the user
                                        raise grace

                                    start_offseted = affinity.translate(tool_dict['start'], currentx, currenty)
                                    stop_offseted = affinity.translate(tool_dict['stop'], currentx, currenty)
                                    obj_fin.slots.append(
                                        {
                                            "start": start_offseted,
                                            "stop": stop_offseted,
                                            "tool": tool_dict['tool']
                                        }
                                    )

                                    slot_nr += 1
                                    disp_number = int(np.interp(slot_nr, [0, geo_len_slots], [0, 100]))

                                    if old_disp_number < disp_number <= 100:
                                        self.app.proc_container.update_view_text(' %s: %d S:%d%%' %
                                                                                 (_("Copy"),
                                                                                  int(element),
                                                                                  disp_number))
                                        old_disp_number = disp_number

                            currentx += lenghtx
                        currenty += lenghty

                    obj_fin.create_geometry()
                    obj_fin.zeros = panel_source_obj.zeros
                    obj_fin.units = panel_source_obj.units
                    self.app.proc_container.update_view_text('')

                def job_init_geometry(obj_fin, app_obj):
                    currentx = 0.0
                    currenty = 0.0

                    def translate_recursion(geom):
                        if type(geom) == list:
                            geoms = []
                            for local_geom in geom:
                                res_geo = translate_recursion(local_geom)
                                try:
                                    geoms += res_geo
                                except TypeError:
                                    geoms.append(res_geo)
                            return geoms
                        else:
                            return affinity.translate(geom, xoff=currentx, yoff=currenty)

                    obj_fin.solid_geometry = []

                    # create the initial structure on which to create the panel
                    if panel_source_obj.kind == 'geometry':
                        obj_fin.multigeo = panel_source_obj.multigeo
                        obj_fin.tools = copied_tools
                        if panel_source_obj.multigeo is True:
                            for tool in panel_source_obj.tools:
                                obj_fin.tools[tool]['solid_geometry'][:] = []
                    elif panel_source_obj.kind == 'gerber':
                        obj_fin.apertures = copied_apertures
                        for ap in obj_fin.apertures:
                            obj_fin.apertures[ap]['geometry'] = []

                    # find the number of polygons in the source solid_geometry
                    geo_len = 0
                    if panel_source_obj.kind == 'geometry':
                        if panel_source_obj.multigeo is True:
                            for tool in panel_source_obj.tools:
                                try:
                                    geo_len += len(panel_source_obj.tools[tool]['solid_geometry'])
                                except TypeError:
                                    geo_len += 1
                        else:
                            try:
                                geo_len = len(panel_source_obj.solid_geometry)
                            except TypeError:
                                geo_len = 1
                    elif panel_source_obj.kind == 'gerber':
                        for ap in panel_source_obj.apertures:
                            if 'geometry' in panel_source_obj.apertures[ap]:
                                try:
                                    geo_len += len(panel_source_obj.apertures[ap]['geometry'])
                                except TypeError:
                                    geo_len += 1

                    element = 0
                    for row in range(rows):
                        currentx = 0.0

                        for col in range(columns):
                            element += 1
                            old_disp_number = 0

                            # Will panelize a Geometry Object
                            if panel_source_obj.kind == 'geometry':
                                if panel_source_obj.multigeo is True:
                                    for tool in panel_source_obj.tools:
                                        if self.app.abort_flag:
                                            # graceful abort requested by the user
                                            raise grace

                                        # calculate the number of polygons
                                        geo_len = len(panel_source_obj.tools[tool]['solid_geometry'])
                                        pol_nr = 0
                                        for geo_el in panel_source_obj.tools[tool]['solid_geometry']:
                                            trans_geo = translate_recursion(geo_el)
                                            obj_fin.tools[tool]['solid_geometry'].append(trans_geo)

                                            pol_nr += 1
                                            disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))
                                            if old_disp_number < disp_number <= 100:
                                                self.app.proc_container.update_view_text(' %s: %d %d%%' %
                                                                                         (_("Copy"),
                                                                                          int(element),
                                                                                          disp_number))
                                                old_disp_number = disp_number
                                else:
                                    if self.app.abort_flag:
                                        # graceful abort requested by the user
                                        raise grace

                                    try:
                                        # calculate the number of polygons
                                        geo_len = len(panel_source_obj.solid_geometry)
                                    except TypeError:
                                        geo_len = 1
                                    pol_nr = 0
                                    try:
                                        for geo_el in panel_source_obj.solid_geometry:
                                            if self.app.abort_flag:
                                                # graceful abort requested by the user
                                                raise grace

                                            trans_geo = translate_recursion(geo_el)
                                            obj_fin.solid_geometry.append(trans_geo)

                                            pol_nr += 1
                                            disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))

                                            if old_disp_number < disp_number <= 100:
                                                self.app.proc_container.update_view_text(' %s: %d %d%%' %
                                                                                         (_("Copy"),
                                                                                          int(element),
                                                                                          disp_number))
                                                old_disp_number = disp_number

                                    except TypeError:
                                        trans_geo = translate_recursion(panel_source_obj.solid_geometry)
                                        obj_fin.solid_geometry.append(trans_geo)
                            # Will panelize a Gerber Object
                            else:
                                if self.app.abort_flag:
                                    # graceful abort requested by the user
                                    raise grace

                                try:
                                    for geo_el in panel_source_obj.solid_geometry:
                                        if self.app.abort_flag:
                                            # graceful abort requested by the user
                                            raise grace

                                        trans_geo = translate_recursion(geo_el)
                                        obj_fin.solid_geometry.append(trans_geo)
                                except TypeError:
                                    trans_geo = translate_recursion(panel_source_obj.solid_geometry)
                                    obj_fin.solid_geometry.append(trans_geo)

                                for apid in panel_source_obj.apertures:
                                    if self.app.abort_flag:
                                        # graceful abort requested by the user
                                        raise grace
                                    if 'geometry' in panel_source_obj.apertures[apid]:
                                        try:
                                            # calculate the number of polygons
                                            geo_len = len(panel_source_obj.apertures[apid]['geometry'])
                                        except TypeError:
                                            geo_len = 1
                                        pol_nr = 0
                                        for el in panel_source_obj.apertures[apid]['geometry']:
                                            if self.app.abort_flag:
                                                # graceful abort requested by the user
                                                raise grace

                                            new_el = {}
                                            if 'solid' in el:
                                                geo_aper = translate_recursion(el['solid'])
                                                new_el['solid'] = geo_aper

                                            if 'clear' in el:
                                                geo_aper = translate_recursion(el['clear'])
                                                new_el['clear'] = geo_aper

                                            if 'follow' in el:
                                                geo_aper = translate_recursion(el['follow'])
                                                new_el['follow'] = geo_aper

                                            obj_fin.apertures[apid]['geometry'].append(deepcopy(new_el))

                                            pol_nr += 1
                                            disp_number = int(np.interp(pol_nr, [0, geo_len], [0, 100]))

                                            if old_disp_number < disp_number <= 100:
                                                self.app.proc_container.update_view_text(' %s: %d %d%%' %
                                                                                         (_("Copy"),
                                                                                          int(element),
                                                                                          disp_number))
                                                old_disp_number = disp_number

                            currentx += lenghtx
                        currenty += lenghty

                    print("before", obj_fin.tools)
                    if panel_source_obj.kind == 'geometry' and panel_source_obj.multigeo is True:
                        # I'm going to do this only here as a fix for panelizing cutouts
                        # I'm going to separate linestrings out of the solid geometry from other
                        # possible type of elements and apply unary_union on them to fuse them
                        for tool in obj_fin.tools:
                            lines = []
                            other_geo = []
                            for geo in obj_fin.tools[tool]['solid_geometry']:
                                if isinstance(geo, LineString):
                                    lines.append(geo)
                                else:
                                    other_geo.append(geo)
                            fused_lines = list(unary_union(lines))
                            obj_fin.tools[tool]['solid_geometry'] = fused_lines + other_geo
                    print("after", obj_fin.tools)

                    if panel_type == 'gerber':
                        self.app.inform.emit('%s' % _("Generating panel ... Adding the Gerber code."))
                        obj_fin.source_file = self.app.export_gerber(obj_name=self.outname, filename=None,
                                                                     local_use=obj_fin, use_thread=False)

                    # obj_fin.solid_geometry = cascaded_union(obj_fin.solid_geometry)
                    # app_obj.log.debug("Finished creating a cascaded union for the panel.")
                    self.app.proc_container.update_view_text('')

                self.app.inform.emit('%s: %d' % (_("Generating panel... Spawning copies"), (int(rows * columns))))
                if panel_source_obj.kind == 'excellon':
                    self.app.new_object("excellon", self.outname, job_init_excellon, plot=True, autoselected=True)
                else:
                    self.app.new_object(panel_type, self.outname, job_init_geometry, plot=True, autoselected=True)

        if self.constrain_flag is False:
            self.app.inform.emit('[success] %s' % _("Panel done..."))
        else:
            self.constrain_flag = False
            self.app.inform.emit(_("{text} Too big for the constrain area. "
                                   "Final panel has {col} columns and {row} rows").format(
                text='[WARNING] ', col=columns, row=rows))

        proc = self.app.proc_container.new(_("Working..."))

        def job_thread(app_obj):
            try:
                panelize_worker()
                self.app.inform.emit('[success] %s' % _("Panel created successfully."))
            except Exception as ee:
                proc.done()
                log.debug(str(ee))
                return
            proc.done()

        self.app.collection.promise(self.outname)
        self.app.worker_task.emit({'fcn': job_thread, 'params': [self.app]})

    def reset_fields(self):
        self.object_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
        self.box_combo.setRootModelIndex(self.app.collection.index(0, 0, QtCore.QModelIndex()))
