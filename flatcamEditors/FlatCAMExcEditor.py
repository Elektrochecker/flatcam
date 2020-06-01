# ##########################################################
# FlatCAM: 2D Post-processing for Manufacturing            #
# File Author: Marius Adrian Stanciu (c)                   #
# Date: 8/17/2019                                          #
# MIT Licence                                              #
# ##########################################################

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt, QSettings

from camlib import distance, arc, FlatCAMRTreeStorage
from flatcamGUI.GUIElements import FCEntry, FCComboBox, FCTable, FCDoubleSpinner, RadioSet, FCSpinner
from flatcamEditors.FlatCAMGeoEditor import FCShapeTool, DrawTool, DrawToolShape, DrawToolUtilityShape, FlatCAMGeoEditor
from flatcamParsers.ParseExcellon import Excellon

from shapely.geometry import LineString, LinearRing, MultiLineString, Polygon, MultiPolygon, Point
import shapely.affinity as affinity

import numpy as np

from rtree import index as rtindex

import traceback
import math
import logging
from copy import deepcopy

import gettext
import FlatCAMTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class FCDrillAdd(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_add'

        self.selected_dia = None
        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' % _("To add a drill first select a tool"))
            self.draw_app.select_tool("drill_select")
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_drill.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit(_("Click to place ..."))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):
        self.make()
        return "Done."

    def utility_geometry(self, data=None):
        self.points = data
        return DrawToolUtilityShape(self.util_shape(data))

    def util_shape(self, point):
        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        start_hor_line = ((point_x - (self.selected_dia / 2)), point_y)
        stop_hor_line = ((point_x + (self.selected_dia / 2)), point_y)
        start_vert_line = (point_x, (point_y - (self.selected_dia / 2)))
        stop_vert_line = (point_x, (point_y + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to drills if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia].append(self.points)
        else:
            self.draw_app.points_edit[self.selected_dia] = [self.points]

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]
        self.geometry = DrawToolShape(self.util_shape(self.points))
        self.draw_app.in_action = False
        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Drill added."))
        self.draw_app.app.jump_signal.disconnect()

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCDrillArray(FCShapeTool):
    """
    Resulting type: MultiLineString
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_array'

        self.draw_app.array_frame.show()

        self.selected_dia = None
        self.drill_axis = 'X'
        self.drill_array = 'linear'
        self.drill_array_size = None
        self.drill_pitch = None
        self.drill_linear_angle = None

        self.drill_angle = None
        self.drill_direction = None
        self.drill_radius = None

        self.origin = None
        self.destination = None
        self.flag_for_circ_array = None

        self.last_dx = 0
        self.last_dy = 0

        self.pt = []

        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("To add an Drill Array first select a tool in Tool Table"))
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_drill_array.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y), static=True)

        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit(_("Click on target location ..."))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):

        if self.drill_array == 'Linear':
            self.make()
            return
        else:
            if self.flag_for_circ_array is None:
                self.draw_app.in_action = True
                self.pt.append(point)

                self.flag_for_circ_array = True
                self.set_origin(point)
                self.draw_app.app.inform.emit(_("Click on the Drill Circular Array Start position"))
            else:
                self.destination = point
                self.make()
                self.flag_for_circ_array = None
                return

    def set_origin(self, origin):
        self.origin = origin

    def utility_geometry(self, data=None, static=None):
        self.drill_axis = self.draw_app.drill_axis_radio.get_value()
        self.drill_direction = self.draw_app.drill_direction_radio.get_value()
        self.drill_array = self.draw_app.array_type_combo.get_value()
        try:
            self.drill_array_size = int(self.draw_app.drill_array_size_entry.get_value())
            try:
                self.drill_pitch = float(self.draw_app.drill_pitch_entry.get_value())
                self.drill_linear_angle = float(self.draw_app.linear_angle_spinner.get_value())
                self.drill_angle = float(self.draw_app.drill_angle_entry.get_value())
            except TypeError:
                self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' %
                                              _("The value is not Float. Check for comma instead of dot separator."))
                return
        except Exception as e:
            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s. %s' %
                                          (_("The value is mistyped. Check the value"), str(e)))
            return

        if self.drill_array == 'Linear':
            if data[0] is None and data[1] is None:
                dx = self.draw_app.x
                dy = self.draw_app.y
            else:
                dx = data[0]
                dy = data[1]

            geo_list = []
            geo = None
            self.points = [dx, dy]

            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((dx + (self.drill_pitch * item)), dy))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((dx, (dy + (self.drill_pitch * item))))
                if self.drill_axis == 'A':
                    x_adj = self.drill_pitch * math.cos(math.radians(self.drill_linear_angle))
                    y_adj = self.drill_pitch * math.sin(math.radians(self.drill_linear_angle))
                    geo = self.util_shape(
                        ((dx + (x_adj * item)), (dy + (y_adj * item)))
                    )

                if static is None or static is False:
                    geo_list.append(affinity.translate(geo, xoff=(dx - self.last_dx), yoff=(dy - self.last_dy)))
                else:
                    geo_list.append(geo)
            # self.origin = data

            self.last_dx = dx
            self.last_dy = dy
            return DrawToolUtilityShape(geo_list)
        else:
            if data[0] is None and data[1] is None:
                cdx = self.draw_app.x
                cdy = self.draw_app.y
            else:
                cdx = data[0]
                cdy = data[1]

            if len(self.pt) > 0:
                temp_points = [x for x in self.pt]
                temp_points.append([cdx, cdy])
                return DrawToolUtilityShape(LineString(temp_points))

    def util_shape(self, point):
        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        start_hor_line = ((point_x - (self.selected_dia / 2)), point_y)
        stop_hor_line = ((point_x + (self.selected_dia / 2)), point_y)
        start_vert_line = (point_x, (point_y - (self.selected_dia / 2)))
        stop_vert_line = (point_x, (point_y + (self.selected_dia / 2)))

        return MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])

    def make(self):
        self.geometry = []
        geo = None

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to drills if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia not in self.draw_app.points_edit:
            self.draw_app.points_edit[self.selected_dia] = []
        for i in range(self.drill_array_size):
            self.draw_app.points_edit[self.selected_dia].append(self.points)

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        if self.drill_array == 'Linear':
            for item in range(self.drill_array_size):
                if self.drill_axis == 'X':
                    geo = self.util_shape(((self.points[0] + (self.drill_pitch * item)), self.points[1]))
                if self.drill_axis == 'Y':
                    geo = self.util_shape((self.points[0], (self.points[1] + (self.drill_pitch * item))))
                if self.drill_axis == 'A':
                    x_adj = self.drill_pitch * math.cos(math.radians(self.drill_linear_angle))
                    y_adj = self.drill_pitch * math.sin(math.radians(self.drill_linear_angle))
                    geo = self.util_shape(
                        ((self.points[0] + (x_adj * item)), (self.points[1] + (y_adj * item)))
                    )

                self.geometry.append(DrawToolShape(geo))
        else:
            if (self.drill_angle * self.drill_array_size) > 360:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Too many drills for the selected spacing angle."))
                self.draw_app.app.jump_signal.disconnect()
                return

            radius = distance(self.destination, self.origin)
            initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)
            for i in range(self.drill_array_size):
                angle_radians = math.radians(self.drill_angle * i)
                if self.drill_direction == 'CW':
                    x = self.origin[0] + radius * math.cos(-angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(-angle_radians + initial_angle)
                else:
                    x = self.origin[0] + radius * math.cos(angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(angle_radians + initial_angle)

                geo = self.util_shape((x, y))
                self.geometry.append(DrawToolShape(geo))
        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Drill Array added."))
        self.draw_app.in_action = False
        self.draw_app.array_frame.hide()

        self.draw_app.app.jump_signal.disconnect()

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCSlot(FCShapeTool):
    """
    Resulting type: Polygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'slot_add'
        self.draw_app = draw_app

        self.draw_app.slot_frame.show()

        self.selected_dia = None
        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]

            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("To add a slot first select a tool"))
            self.draw_app.select_tool("drill_select")
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_slot.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

        self.half_height = 0.0
        self.half_width = 0.0
        self.radius = float(self.selected_dia / 2.0)

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y))
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit(_("Click on target location ..."))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):
        self.make()
        return "Done."

    def utility_geometry(self, data=None):

        self.points = data
        geo_data = self.util_shape(data)
        if geo_data:
            return DrawToolUtilityShape(geo_data)
        else:
            return None

    def util_shape(self, point):

        if point is None:
            return

        # updating values here allows us to change the aperture on the fly, after the Tool has been started
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
        self.radius = float(self.selected_dia / 2.0)
        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

        try:
            slot_length = float(self.draw_app.slot_length_entry.get_value())
        except ValueError:
            # try to convert comma to decimal point. if it's still not working error message and return
            try:
                slot_length = float(self.draw_app.slot_length_entry.get_value().replace(',', '.'))
                self.draw_app.slot_length_entry.set_value(slot_length)
            except ValueError:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Value is missing or wrong format. Add it and retry."))
                return

        try:
            slot_angle = float(self.draw_app.slot_angle_spinner.get_value())
        except ValueError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("Value is missing or wrong format. Add it and retry."))
            return

        if self.draw_app.slot_axis_radio.get_value() == 'X':
            self.half_width = slot_length / 2.0
            self.half_height = self.radius
        else:
            self.half_width = self.radius
            self.half_height = slot_length / 2.0

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        geo = []

        if self.half_height > self.half_width:
            p1 = (point_x - self.half_width, point_y - self.half_height + self.half_width)
            p2 = (point_x + self.half_width, point_y - self.half_height + self.half_width)
            p3 = (point_x + self.half_width, point_y + self.half_height - self.half_width)
            p4 = (point_x - self.half_width, point_y + self.half_height - self.half_width)

            down_center = [point_x, point_y - self.half_height + self.half_width]
            d_start_angle = math.pi
            d_stop_angle = 0.0
            down_arc = arc(down_center, self.half_width, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            up_center = [point_x, point_y + self.half_height - self.half_width]
            u_start_angle = 0.0
            u_stop_angle = math.pi
            up_arc = arc(up_center, self.half_width, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            for pt in down_arc:
                geo.append(pt)
            geo.append(p2)
            geo.append(p3)
            for pt in up_arc:
                geo.append(pt)
            geo.append(p4)

            if self.draw_app.slot_axis_radio.get_value() == 'A':
                return affinity.rotate(geom=Polygon(geo), angle=-slot_angle)
            else:
                return Polygon(geo)
        else:
            p1 = (point_x - self.half_width + self.half_height, point_y - self.half_height)
            p2 = (point_x + self.half_width - self.half_height, point_y - self.half_height)
            p3 = (point_x + self.half_width - self.half_height, point_y + self.half_height)
            p4 = (point_x - self.half_width + self.half_height, point_y + self.half_height)

            left_center = [point_x - self.half_width + self.half_height, point_y]
            d_start_angle = math.pi / 2
            d_stop_angle = 1.5 * math.pi
            left_arc = arc(left_center, self.half_height, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            right_center = [point_x + self.half_width - self.half_height, point_y]
            u_start_angle = 1.5 * math.pi
            u_stop_angle = math.pi / 2
            right_arc = arc(right_center, self.half_height, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            geo.append(p2)
            for pt in right_arc:
                geo.append(pt)
            geo.append(p3)
            geo.append(p4)
            for pt in left_arc:
                geo.append(pt)

            return Polygon(geo)

    def make(self):

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        try:
            self.geometry = DrawToolShape(self.util_shape(self.points))
        except Exception as e:
            log.debug("FCSlot.make() --> %s" % str(e))

        # add the point to drills/slots if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia in self.draw_app.slot_points_edit:
            self.draw_app.slot_points_edit[self.selected_dia].append(self.points)
        else:
            self.draw_app.slot_points_edit[self.selected_dia] = [self.points]

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        self.draw_app.in_action = False
        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Adding Slot completed."))
        self.draw_app.slot_frame.hide()
        self.draw_app.app.jump_signal.disconnect()

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCSlotArray(FCShapeTool):
    """
    Resulting type: MultiPolygon
    """

    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'slot_array'
        self.draw_app = draw_app

        self.draw_app.slot_frame.show()
        self.draw_app.slot_array_frame.show()

        self.selected_dia = None
        try:
            self.draw_app.app.inform.emit(_("Click to place ..."))
            self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
            # as a visual marker, select again in tooltable the actual tool that we are using
            # remember that it was deselected when clicking on canvas
            item = self.draw_app.tools_table_exc.item((self.draw_app.last_tool_selected - 1), 1)
            self.draw_app.tools_table_exc.setCurrentItem(item)
        except KeyError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("To add an Slot Array first select a tool in Tool Table"))
            return

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass
        self.cursor = QtGui.QCursor(QtGui.QPixmap(self.draw_app.app.resource_location + '/aero_array.png'))
        QtGui.QGuiApplication.setOverrideCursor(self.cursor)

        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

        self.half_width = 0.0
        self.half_height = 0.0
        self.radius = float(self.selected_dia / 2.0)

        self.slot_axis = 'X'
        self.slot_array = 'linear'
        self.slot_array_size = None
        self.slot_pitch = None
        self.slot_linear_angle = None

        self.slot_angle = None
        self.slot_direction = None
        self.slot_radius = None

        self.origin = None
        self.destination = None
        self.flag_for_circ_array = None

        self.last_dx = 0
        self.last_dy = 0

        self.pt = []

        geo = self.utility_geometry(data=(self.draw_app.snap_x, self.draw_app.snap_y), static=True)
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            self.draw_app.draw_utility_geometry(geo=geo)

        self.draw_app.app.inform.emit(_("Click on target location ..."))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def click(self, point):

        if self.slot_array == 'Linear':
            self.make()
            return
        else:
            if self.flag_for_circ_array is None:
                self.draw_app.in_action = True
                self.pt.append(point)

                self.flag_for_circ_array = True
                self.set_origin(point)
                self.draw_app.app.inform.emit(_("Click on the Slot Circular Array Start position"))
            else:
                self.destination = point
                self.make()
                self.flag_for_circ_array = None
                return

    def set_origin(self, origin):
        self.origin = origin

    def utility_geometry(self, data=None, static=None):
        self.slot_axis = self.draw_app.slot_array_axis_radio.get_value()
        self.slot_direction = self.draw_app.slot_array_direction_radio.get_value()
        self.slot_array = self.draw_app.slot_array_type_combo.get_value()
        try:
            self.slot_array_size = int(self.draw_app.slot_array_size_entry.get_value())
            try:
                self.slot_pitch = float(self.draw_app.slot_array_pitch_entry.get_value())
                self.slot_linear_angle = float(self.draw_app.slot_array_linear_angle_spinner.get_value())
                self.slot_angle = float(self.draw_app.slot_array_angle_entry.get_value())
            except TypeError:
                self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' %
                                              _("The value is not Float. Check for comma instead of dot separator."))
                return
        except Exception:
            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("The value is mistyped. Check the value."))
            return

        if self.slot_array == 'Linear':
            if data[0] is None and data[1] is None:
                dx = self.draw_app.x
                dy = self.draw_app.y
            else:
                dx = data[0]
                dy = data[1]

            geo_el_list = []
            geo_el = []
            self.points = [dx, dy]

            for item in range(self.slot_array_size):
                if self.slot_axis == 'X':
                    geo_el = self.util_shape(((dx + (self.slot_pitch * item)), dy))
                if self.slot_axis == 'Y':
                    geo_el = self.util_shape((dx, (dy + (self.slot_pitch * item))))
                if self.slot_axis == 'A':
                    x_adj = self.slot_pitch * math.cos(math.radians(self.slot_linear_angle))
                    y_adj = self.slot_pitch * math.sin(math.radians(self.slot_linear_angle))
                    geo_el = self.util_shape(
                        ((dx + (x_adj * item)), (dy + (y_adj * item)))
                    )

                if static is None or static is False:
                    geo_el = affinity.translate(geo_el, xoff=(dx - self.last_dx), yoff=(dy - self.last_dy))
                geo_el_list.append(geo_el)

            self.last_dx = dx
            self.last_dy = dy
            return DrawToolUtilityShape(geo_el_list)
        else:
            if data[0] is None and data[1] is None:
                cdx = self.draw_app.x
                cdy = self.draw_app.y
            else:
                cdx = data[0]
                cdy = data[1]

            if len(self.pt) > 0:
                temp_points = [x for x in self.pt]
                temp_points.append([cdx, cdy])
                return DrawToolUtilityShape(LineString(temp_points))

    def util_shape(self, point):
        # updating values here allows us to change the aperture on the fly, after the Tool has been started
        self.selected_dia = self.draw_app.tool2tooldia[self.draw_app.last_tool_selected]
        self.radius = float(self.selected_dia / 2.0)
        self.steps_per_circ = self.draw_app.app.defaults["geometry_circle_steps"]

        try:
            slot_length = float(self.draw_app.slot_length_entry.get_value())
        except ValueError:
            # try to convert comma to decimal point. if it's still not working error message and return
            try:
                slot_length = float(self.draw_app.slot_length_entry.get_value().replace(',', '.'))
                self.draw_app.slot_length_entry.set_value(slot_length)
            except ValueError:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Value is missing or wrong format. Add it and retry."))
                return

        try:
            slot_angle = float(self.draw_app.slot_angle_spinner.get_value())
        except ValueError:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("Value is missing or wrong format. Add it and retry."))
            return

        if self.draw_app.slot_axis_radio.get_value() == 'X':
            self.half_width = slot_length / 2.0
            self.half_height = self.radius
        else:
            self.half_width = self.radius
            self.half_height = slot_length / 2.0

        if point[0] is None and point[1] is None:
            point_x = self.draw_app.x
            point_y = self.draw_app.y
        else:
            point_x = point[0]
            point_y = point[1]

        geo = []

        if self.half_height > self.half_width:
            p1 = (point_x - self.half_width, point_y - self.half_height + self.half_width)
            p2 = (point_x + self.half_width, point_y - self.half_height + self.half_width)
            p3 = (point_x + self.half_width, point_y + self.half_height - self.half_width)
            p4 = (point_x - self.half_width, point_y + self.half_height - self.half_width)

            down_center = [point_x, point_y - self.half_height + self.half_width]
            d_start_angle = math.pi
            d_stop_angle = 0.0
            down_arc = arc(down_center, self.half_width, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            up_center = [point_x, point_y + self.half_height - self.half_width]
            u_start_angle = 0.0
            u_stop_angle = math.pi
            up_arc = arc(up_center, self.half_width, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            for pt in down_arc:
                geo.append(pt)
            geo.append(p2)
            geo.append(p3)
            for pt in up_arc:
                geo.append(pt)
            geo.append(p4)
        else:
            p1 = (point_x - self.half_width + self.half_height, point_y - self.half_height)
            p2 = (point_x + self.half_width - self.half_height, point_y - self.half_height)
            p3 = (point_x + self.half_width - self.half_height, point_y + self.half_height)
            p4 = (point_x - self.half_width + self.half_height, point_y + self.half_height)

            left_center = [point_x - self.half_width + self.half_height, point_y]
            d_start_angle = math.pi / 2
            d_stop_angle = 1.5 * math.pi
            left_arc = arc(left_center, self.half_height, d_start_angle, d_stop_angle, 'ccw', self.steps_per_circ)

            right_center = [point_x + self.half_width - self.half_height, point_y]
            u_start_angle = 1.5 * math.pi
            u_stop_angle = math.pi / 2
            right_arc = arc(right_center, self.half_height, u_start_angle, u_stop_angle, 'ccw', self.steps_per_circ)

            geo.append(p1)
            geo.append(p2)
            for pt in right_arc:
                geo.append(pt)
            geo.append(p3)
            geo.append(p4)
            for pt in left_arc:
                geo.append(pt)

        # this function return one slot in the slot array and the following will rotate that one slot around it's
        # center if the radio value is "A".
        if self.draw_app.slot_axis_radio.get_value() == 'A':
            return affinity.rotate(Polygon(geo), -slot_angle)
        else:
            return Polygon(geo)

    def make(self):
        self.geometry = []
        geo = None

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # add the point to slots if the diameter is a key in the dict, if not, create it add the drill location
        # to the value, as a list of itself
        if self.selected_dia not in self.draw_app.slot_points_edit:
            self.draw_app.slot_points_edit[self.selected_dia] = []
        for i in range(self.slot_array_size):
            self.draw_app.slot_points_edit[self.selected_dia].append(self.points)

        self.draw_app.current_storage = self.draw_app.storage_dict[self.selected_dia]

        if self.slot_array == 'Linear':
            for item in range(self.slot_array_size):
                if self.slot_axis == 'X':
                    geo = self.util_shape(((self.points[0] + (self.slot_pitch * item)), self.points[1]))
                if self.slot_axis == 'Y':
                    geo = self.util_shape((self.points[0], (self.points[1] + (self.slot_pitch * item))))
                if self.slot_axis == 'A':
                    x_adj = self.slot_pitch * math.cos(math.radians(self.slot_linear_angle))
                    y_adj = self.slot_pitch * math.sin(math.radians(self.slot_linear_angle))
                    geo = self.util_shape(
                        ((self.points[0] + (x_adj * item)), (self.points[1] + (y_adj * item)))
                    )

                self.geometry.append(DrawToolShape(geo))
        else:
            if (self.slot_angle * self.slot_array_size) > 360:
                self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                              _("Too many Slots for the selected spacing angle."))
                self.draw_app.app.jump_signal.disconnect()
                return

            radius = distance(self.destination, self.origin)
            initial_angle = math.asin((self.destination[1] - self.origin[1]) / radius)
            for i in range(self.slot_array_size):
                angle_radians = math.radians(self.slot_angle * i)
                if self.slot_direction == 'CW':
                    x = self.origin[0] + radius * math.cos(-angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(-angle_radians + initial_angle)
                else:
                    x = self.origin[0] + radius * math.cos(angle_radians + initial_angle)
                    y = self.origin[1] + radius * math.sin(angle_radians + initial_angle)

                geo = self.util_shape((x, y))
                if self.slot_direction == 'CW':
                    geo = affinity.rotate(geo, angle=(math.pi - angle_radians), use_radians=True)
                else:
                    geo = affinity.rotate(geo, angle=(angle_radians - math.pi), use_radians=True)

                self.geometry.append(DrawToolShape(geo))
        self.complete = True
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Slot Array added."))
        self.draw_app.in_action = False
        self.draw_app.slot_frame.hide()
        self.draw_app.slot_array_frame.hide()
        self.draw_app.app.jump_signal.disconnect()

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCDrillResize(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_resize'

        self.draw_app.app.inform.emit(_("Click on the Drill(s) to resize ..."))
        self.resize_dia = None
        self.draw_app.resize_frame.show()
        self.points = None

        # made this a set so there are no duplicates
        self.selected_dia_set = set()

        self.current_storage = None
        self.geometry = []
        self.destination_storage = None

        self.draw_app.resize_btn.clicked.connect(self.make)
        self.draw_app.resdrill_entry.editingFinished.connect(self.make)

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def make(self):
        self.draw_app.is_modified = True

        try:
            self.draw_app.tools_table_exc.itemChanged.disconnect()
        except TypeError:
            pass

        try:
            new_dia = self.draw_app.resdrill_entry.get_value()
        except Exception:
            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' %
                                          _("Resize drill(s) failed. Please enter a diameter for resize."))
            return

        if new_dia not in self.draw_app.olddia_newdia:
            self.destination_storage = FlatCAMGeoEditor.make_storage()
            self.draw_app.storage_dict[new_dia] = self.destination_storage

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.draw_app.olddia_newdia[new_dia] = new_dia
        else:
            self.destination_storage = self.draw_app.storage_dict[new_dia]

        for index in self.draw_app.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.tools_table_exc.item(row, 1).text()
            self.selected_dia_set.add(float(dia_on_row))

        # since we add a new tool, we update also the intial state of the tool_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.draw_app.tool2tooldia[len(self.draw_app.olddia_newdia)] = new_dia

        sel_shapes_to_be_deleted = []

        if self.selected_dia_set:
            for sel_dia in self.selected_dia_set:
                self.current_storage = self.draw_app.storage_dict[sel_dia]
                for select_shape in self.draw_app.get_selected():
                    if select_shape in self.current_storage.get_objects():

                        # add new geometry according to the new size
                        if isinstance(select_shape.geo, MultiLineString):
                            factor = new_dia / sel_dia
                            self.geometry.append(DrawToolShape(affinity.scale(select_shape.geo,
                                                                              xfact=factor,
                                                                              yfact=factor,
                                                                              origin='center')))
                        elif isinstance(select_shape.geo, Polygon):
                            # I don't have any info regarding the angle of the slot geometry, nor how thick it is or
                            # how long it is given the angle. So I will have to make an approximation because
                            # we need to conserve the slot length, we only resize the diameter for the tool
                            # Therefore scaling won't work and buffering will not work either.

                            # First we get the Linestring that is one that the original slot is built around with the
                            # tool having the diameter sel_dia
                            poly = select_shape.geo
                            xmin, ymin, xmax, ymax = poly.bounds
                            # a line that is certain to be bigger than our slot because it's the diagonal
                            # of it's bounding box
                            poly_diagonal = LineString([(xmin, ymin), (xmax, ymax)])
                            poly_centroid = poly.centroid
                            # center of the slot geometry
                            poly_center = (poly_centroid.x, poly_centroid.y)

                            # make a list of intersections with the rotated line
                            list_of_cuttings = []
                            for angle in range(0, 359, 1):
                                rot_poly_diagonal = affinity.rotate(poly_diagonal, angle=angle, origin=poly_center)
                                cut_line = rot_poly_diagonal.intersection(poly)
                                cut_line_len = cut_line.length
                                list_of_cuttings.append(
                                    (cut_line_len, cut_line)
                                )
                            # find the cut_line with the maximum length which is the LineString for which the start
                            # and stop point are the start and stop point of the slot as in the Gerber file
                            cut_line_with_max_length = max(list_of_cuttings, key=lambda i: i[0])[1]
                            # find the coordinates of this line
                            cut_line_with_max_length_coords = list(cut_line_with_max_length.coords)
                            # extract the first and last point of the line and build some buffered polygon circles
                            # around them
                            start_pt = Point(cut_line_with_max_length_coords[0])
                            stop_pt = Point(cut_line_with_max_length_coords[1])
                            start_cut_geo = start_pt.buffer(new_dia / 2)
                            stop_cut_geo = stop_pt.buffer(new_dia / 2)

                            # and we cut the above circle polygons from our line and get in this way a line around
                            # which we can build the new slot by buffering with the new tool diameter
                            new_line = cut_line_with_max_length.difference(start_cut_geo)
                            new_line = new_line.difference(stop_cut_geo)

                            # create the geometry for the resized slot by buffering with half of the
                            # new diameter value, new_dia
                            new_poly = new_line.buffer(new_dia / 2)

                            self.geometry.append(DrawToolShape(new_poly))
                        else:
                            # unexpected geometry so we cancel
                            self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Cancelled."))
                            return

                        # remove the geometry with the old size
                        self.current_storage.remove(select_shape)

                        # a hack to make the tool_table display less drills per diameter when shape(drill) is deleted
                        # self.points_edit it's only useful first time when we load the data into the storage
                        # but is still used as reference when building tool_table in self.build_ui()
                        # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                        # deleting self.points_edit elements (doesn't matter who but just the number)
                        # solved the display issue.
                        if isinstance(select_shape.geo, MultiLineString):
                            try:
                                del self.draw_app.points_edit[sel_dia][0]
                            except KeyError:
                                # if the exception happen here then we are not dealing with drills but with slots
                                # This should not happen as the drills have MultiLineString geometry and slots have
                                # Polygon geometry
                                pass
                        if isinstance(select_shape.geo, Polygon):
                            try:
                                del self.draw_app.slot_points_edit[sel_dia][0]
                            except KeyError:
                                # if the exception happen here then we are not dealing with slots but with drills
                                # This should not happen as the drills have MultiLineString geometry and slots have
                                # Polygon geometry
                                pass

                        sel_shapes_to_be_deleted.append(select_shape)

                        # a hack to make the tool_table display more drills/slots per diameter when shape(drill/slot)
                        # is added.
                        # self.points_edit it's only useful first time when we load the data into the storage
                        # but is still used as reference when building tool_table in self.build_ui()
                        # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                        # deleting self.points_edit elements (doesn't matter who but just the number)
                        # solved the display issue.

                        # for drills
                        if isinstance(select_shape.geo, MultiLineString):
                            if new_dia not in self.draw_app.points_edit:
                                self.draw_app.points_edit[new_dia] = [(0, 0)]
                            else:
                                self.draw_app.points_edit[new_dia].append((0, 0))

                        # for slots
                        if isinstance(select_shape.geo, Polygon):
                            if new_dia not in self.draw_app.slot_points_edit:
                                self.draw_app.slot_points_edit[new_dia] = [(0, 0)]
                            else:
                                self.draw_app.slot_points_edit[new_dia].append((0, 0))

            for dia_key in list(self.draw_app.storage_dict.keys()):
                # if following the resize of the drills there will be no more drills for some of the tools then
                # delete those tools
                try:
                    if not self.draw_app.points_edit[dia_key]:
                        self.draw_app.on_tool_delete(dia_key)
                except KeyError:
                    # if the exception happen here then we are not dealing with drills but with slots
                    # so we try for them
                    try:
                        if not self.draw_app.slot_points_edit[dia_key]:
                            self.draw_app.on_tool_delete(dia_key)
                    except KeyError:
                        # if the exception happen here then we are not dealing with slots neither
                        # therefore something else is not OK so we return
                        self.draw_app.app.inform.emit('[ERROR_NOTCL] %s' % _("Cancelled."))
                        return

            # this simple hack is used so we can delete form self.draw_app.selected but
            # after we no longer iterate through it
            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)

            # add the new geometry to storage
            self.draw_app.on_exc_shape_complete(self.destination_storage)

            self.draw_app.build_ui()
            self.draw_app.replot()

            # empty the self.geometry
            self.geometry = []

            # we reactivate the signals after the after the tool editing
            self.draw_app.tools_table_exc.itemChanged.connect(self.draw_app.on_tool_edit)

            self.draw_app.app.inform.emit('[success] %s' %
                                          _("Done. Drill/Slot Resize completed."))
        else:
            self.draw_app.app.inform.emit('[WARNING_NOTCL] %s' %
                                          _("Cancelled. No drills/slots selected for resize ..."))

        # init this set() for another use perhaps
        self.selected_dia_set = set()

        self.draw_app.resize_frame.hide()
        self.complete = True

        # MS: always return to the Select Tool
        self.draw_app.select_tool("drill_select")

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCDrillMove(FCShapeTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_move'

        # self.shape_buffer = self.draw_app.shape_buffer
        self.origin = None
        self.destination = None
        self.sel_limit = self.draw_app.app.defaults["excellon_editor_sel_limit"]
        self.selection_shape = self.selection_bbox()
        self.selected_dia_list = []

        if self.draw_app.launched_from_shortcuts is True:
            self.draw_app.launched_from_shortcuts = False
            self.draw_app.app.inform.emit(_("Click on target location ..."))
        else:
            self.draw_app.app.inform.emit(_("Click on reference location ..."))
        self.current_storage = None
        self.geometry = []

        for index in self.draw_app.tools_table_exc.selectedIndexes():
            row = index.row()
            # on column 1 in tool tables we hold the diameters, and we retrieve them as strings
            # therefore below we convert to float
            dia_on_row = self.draw_app.tools_table_exc.item(row, 1).text()
            self.selected_dia_list.append(float(dia_on_row))

        self.draw_app.app.jump_signal.connect(lambda x: self.draw_app.update_utility_geometry(data=x))

        # Switch notebook to Selected page
        self.draw_app.app.ui.notebook.setCurrentWidget(self.draw_app.app.ui.selected_tab)

    def set_origin(self, origin):
        self.origin = origin

    def click(self, point):
        if len(self.draw_app.get_selected()) == 0:
            return "Nothing to move."

        if self.origin is None:
            self.set_origin(point)
            self.draw_app.app.inform.emit(_("Click on target location ..."))
            return
        else:
            self.destination = point
            self.make()

            # MS: always return to the Select Tool
            self.draw_app.select_tool("drill_select")
            return

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():

                    self.geometry.append(DrawToolShape(affinity.translate(select_shape.geo, xoff=dx, yoff=dy)))
                    self.current_storage.remove(select_shape)
                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Drill(s) Move completed."))
        self.draw_app.app.jump_signal.disconnect()

    def selection_bbox(self):
        geo_list = []
        for select_shape in self.draw_app.get_selected():
            geometric_data = select_shape.geo
            try:
                for g in geometric_data:
                    geo_list.append(g)
            except TypeError:
                geo_list.append(geometric_data)

        xmin, ymin, xmax, ymax = get_shapely_list_bounds(geo_list)

        pt1 = (xmin, ymin)
        pt2 = (xmax, ymin)
        pt3 = (xmax, ymax)
        pt4 = (xmin, ymax)

        return Polygon([pt1, pt2, pt3, pt4])

    def utility_geometry(self, data=None):
        """
        Temporary geometry on screen while using this tool.

        :param data:
        :return:
        """
        geo_list = []

        if self.origin is None:
            return None

        if len(self.draw_app.get_selected()) == 0:
            return None

        dx = data[0] - self.origin[0]
        dy = data[1] - self.origin[1]

        if len(self.draw_app.get_selected()) <= self.sel_limit:
            try:
                for geom in self.draw_app.get_selected():
                    geo_list.append(affinity.translate(geom.geo, xoff=dx, yoff=dy))
            except AttributeError:
                self.draw_app.select_tool('drill_select')
                self.draw_app.selected = []
                return
            return DrawToolUtilityShape(geo_list)
        else:
            try:
                ss_el = affinity.translate(self.selection_shape, xoff=dx, yoff=dy)
            except ValueError:
                ss_el = None
            return DrawToolUtilityShape(ss_el)

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCDrillCopy(FCDrillMove):
    def __init__(self, draw_app):
        FCDrillMove.__init__(self, draw_app)
        self.name = 'drill_copy'

    def make(self):
        # Create new geometry
        dx = self.destination[0] - self.origin[0]
        dy = self.destination[1] - self.origin[1]
        sel_shapes_to_be_deleted = []

        for sel_dia in self.selected_dia_list:
            self.current_storage = self.draw_app.storage_dict[sel_dia]
            for select_shape in self.draw_app.get_selected():
                if select_shape in self.current_storage.get_objects():
                    self.geometry.append(DrawToolShape(affinity.translate(select_shape.geo, xoff=dx, yoff=dy)))

                    # Add some fake drills into the self.draw_app.points_edit to update the drill count in tool table
                    # This may fail if we copy slots.
                    try:
                        self.draw_app.points_edit[sel_dia].append((0, 0))
                    except KeyError:
                        pass

                    # add some fake slots into the self.draw_app.slots_points_edit
                    # to update the slot count in tool table
                    # This may fail if we copy drills.
                    try:
                        self.draw_app.slot_points_edit[sel_dia].append((0, 0))
                    except KeyError:
                        pass

                    sel_shapes_to_be_deleted.append(select_shape)
                    self.draw_app.on_exc_shape_complete(self.current_storage)
                    self.geometry = []

            for shp in sel_shapes_to_be_deleted:
                self.draw_app.selected.remove(shp)
            sel_shapes_to_be_deleted = []

        self.draw_app.build_ui()
        self.draw_app.app.inform.emit('[success] %s' % _("Done. Drill(s) copied."))
        self.draw_app.app.jump_signal.disconnect()

    def clean_up(self):
        self.draw_app.selected = []
        self.draw_app.tools_table_exc.clearSelection()
        self.draw_app.plot_all()

        try:
            self.draw_app.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass


class FCDrillSelect(DrawTool):
    def __init__(self, draw_app):
        DrawTool.__init__(self, draw_app)
        self.name = 'drill_select'

        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        self.exc_editor_app = draw_app
        self.storage = self.exc_editor_app.storage_dict
        # self.selected = self.exc_editor_app.selected

        # here we store the selected tools
        self.sel_tools = set()

        # here we store all shapes that were selected so we can search for the nearest to our click location
        self.sel_storage = FlatCAMExcEditor.make_storage()

        self.exc_editor_app.resize_frame.hide()
        self.exc_editor_app.array_frame.hide()
        self.exc_editor_app.slot_frame.hide()
        self.exc_editor_app.slot_array_frame.hide()

    def click(self, point):
        key_modifier = QtWidgets.QApplication.keyboardModifiers()

        if key_modifier == QtCore.Qt.ShiftModifier:
            mod_key = 'Shift'
        elif key_modifier == QtCore.Qt.ControlModifier:
            mod_key = 'Control'
        else:
            mod_key = None

        if mod_key == self.exc_editor_app.app.defaults["global_mselect_key"]:
            pass
        else:
            self.exc_editor_app.selected = []

    def click_release(self, pos):
        self.exc_editor_app.tools_table_exc.clearSelection()
        xmin, ymin, xmax, ymax = 0, 0, 0, 0

        try:
            for storage in self.exc_editor_app.storage_dict:
                # for sh in self.exc_editor_app.storage_dict[storage].get_objects():
                #     self.sel_storage.insert(sh)
                _, st_closest_shape = self.exc_editor_app.storage_dict[storage].nearest(pos)
                self.sel_storage.insert(st_closest_shape)

            _, closest_shape = self.sel_storage.nearest(pos)

            # constrain selection to happen only within a certain bounding box; it works only for MultiLineStrings
            if isinstance(closest_shape.geo, MultiLineString):
                x_coord, y_coord = closest_shape.geo[0].xy
                delta = (x_coord[1] - x_coord[0])
                # closest_shape_coords = (((x_coord[0] + delta / 2)), y_coord[0])
                xmin = x_coord[0] - (0.7 * delta)
                xmax = x_coord[0] + (1.7 * delta)
                ymin = y_coord[0] - (0.7 * delta)
                ymax = y_coord[0] + (1.7 * delta)
            elif isinstance(closest_shape.geo, Polygon):
                xmin, ymin, xmax, ymax = closest_shape.geo.bounds
                dx = xmax - xmin
                dy = ymax - ymin
                delta = dx if dx > dy else dy
                xmin -= 0.7 * delta
                xmax += 0.7 * delta
                ymin -= 0.7 * delta
                ymax += 0.7 * delta
        except StopIteration:
            return ""

        if pos[0] < xmin or pos[0] > xmax or pos[1] < ymin or pos[1] > ymax:
            self.exc_editor_app.selected = []
        else:
            modifiers = QtWidgets.QApplication.keyboardModifiers()

            if modifiers == QtCore.Qt.ShiftModifier:
                mod_key = 'Shift'
            elif modifiers == QtCore.Qt.ControlModifier:
                mod_key = 'Control'
            else:
                mod_key = None

            if mod_key == self.exc_editor_app.app.defaults["global_mselect_key"]:
                if closest_shape in self.exc_editor_app.selected:
                    self.exc_editor_app.selected.remove(closest_shape)
                else:
                    self.exc_editor_app.selected.append(closest_shape)
            else:
                self.exc_editor_app.selected = []
                self.exc_editor_app.selected.append(closest_shape)

            # select the diameter of the selected shape in the tool table
            try:
                self.exc_editor_app.tools_table_exc.cellPressed.disconnect()
            except (TypeError, AttributeError):
                pass

            # if mod_key == self.exc_editor_app.app.defaults["global_mselect_key"]:
            #     self.exc_editor_app.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
            self.sel_tools.clear()

            for shape_s in self.exc_editor_app.selected:
                for storage in self.exc_editor_app.storage_dict:
                    if shape_s in self.exc_editor_app.storage_dict[storage].get_objects():
                        self.sel_tools.add(storage)

            self.exc_editor_app.tools_table_exc.clearSelection()
            for storage in self.sel_tools:
                for k, v in self.exc_editor_app.tool2tooldia.items():
                    if v == storage:
                        self.exc_editor_app.tools_table_exc.selectRow(int(k) - 1)
                        self.exc_editor_app.last_tool_selected = int(k)
                        break

            # self.exc_editor_app.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

            self.exc_editor_app.tools_table_exc.cellPressed.connect(self.exc_editor_app.on_row_selected)

        # delete whatever is in selection storage, there is no longer need for those shapes
        self.sel_storage = FlatCAMExcEditor.make_storage()

        return ""

        # pos[0] and pos[1] are the mouse click coordinates (x, y)
        # for storage in self.exc_editor_app.storage_dict:
        #     for obj_shape in self.exc_editor_app.storage_dict[storage].get_objects():
        #         minx, miny, maxx, maxy = obj_shape.geo.bounds
        #         if (minx <= pos[0] <= maxx) and (miny <= pos[1] <= maxy):
        #             over_shape_list.append(obj_shape)
        #
        # try:
        #     # if there is no shape under our click then deselect all shapes
        #     if not over_shape_list:
        #         self.exc_editor_app.selected = []
        #         FlatCAMExcEditor.draw_shape_idx = -1
        #         self.exc_editor_app.tools_table_exc.clearSelection()
        #     else:
        #         # if there are shapes under our click then advance through the list of them, one at the time in a
        #         # circular way
        #         FlatCAMExcEditor.draw_shape_idx = (FlatCAMExcEditor.draw_shape_idx + 1) % len(over_shape_list)
        #         obj_to_add = over_shape_list[int(FlatCAMExcEditor.draw_shape_idx)]
        #
        #         if self.exc_editor_app.app.defaults["global_mselect_key"] == 'Shift':
        #             if self.exc_editor_app.modifiers == Qt.ShiftModifier:
        #                 if obj_to_add in self.exc_editor_app.selected:
        #                     self.exc_editor_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.exc_editor_app.selected.append(obj_to_add)
        #             else:
        #                 self.exc_editor_app.selected = []
        #                 self.exc_editor_app.selected.append(obj_to_add)
        #         else:
        #             # if CONTROL key is pressed then we add to the selected list the current shape but if it's already
        #             # in the selected list, we removed it. Therefore first click selects, second deselects.
        #             if self.exc_editor_app.modifiers == Qt.ControlModifier:
        #                 if obj_to_add in self.exc_editor_app.selected:
        #                     self.exc_editor_app.selected.remove(obj_to_add)
        #                 else:
        #                     self.exc_editor_app.selected.append(obj_to_add)
        #             else:
        #                 self.exc_editor_app.selected = []
        #                 self.exc_editor_app.selected.append(obj_to_add)
        #
        #     for storage in self.exc_editor_app.storage_dict:
        #         for shape in self.exc_editor_app.selected:
        #             if shape in self.exc_editor_app.storage_dict[storage].get_objects():
        #                 for key in self.exc_editor_app.tool2tooldia:
        #                     if self.exc_editor_app.tool2tooldia[key] == storage:
        #                         item = self.exc_editor_app.tools_table_exc.item((key - 1), 1)
        #                         item.setSelected(True)
        #                         # self.exc_editor_app.tools_table_exc.selectItem(key - 1)
        #
        # except Exception as e:
        #     log.error("[ERROR] Something went bad. %s" % str(e))
        #     raise


class FlatCAMExcEditor(QtCore.QObject):

    draw_shape_idx = -1

    def __init__(self, app):
        # assert isinstance(app, FlatCAMApp.App), "Expected the app to be a FlatCAMApp.App, got %s" % type(app)

        super(FlatCAMExcEditor, self).__init__()

        self.app = app
        self.canvas = self.app.plotcanvas

        # Number of decimals used by tools in this class
        self.decimals = self.app.decimals

        # ## Current application units in Upper Case
        self.units = self.app.defaults['units'].upper()

        self.exc_edit_widget = QtWidgets.QWidget()
        # ## Box for custom widgets
        # This gets populated in offspring implementations.
        layout = QtWidgets.QVBoxLayout()
        self.exc_edit_widget.setLayout(layout)

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add all the Drills widgets
        # this way I can hide/show the frame
        self.drills_frame = QtWidgets.QFrame()
        self.drills_frame.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.drills_frame)
        self.tools_box = QtWidgets.QVBoxLayout()
        self.tools_box.setContentsMargins(0, 0, 0, 0)
        self.drills_frame.setLayout(self.tools_box)

        # ## Page Title box (spacing between children)
        self.title_box = QtWidgets.QHBoxLayout()
        self.tools_box.addLayout(self.title_box)

        # ## Page Title icon
        pixmap = QtGui.QPixmap(self.app.resource_location + '/flatcam_icon32.png')
        self.icon = QtWidgets.QLabel()
        self.icon.setPixmap(pixmap)
        self.title_box.addWidget(self.icon, stretch=0)

        # ## Title label
        self.title_label = QtWidgets.QLabel("<font size=5><b>%s</b></font>" % _('Excellon Editor'))
        self.title_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.title_box.addWidget(self.title_label, stretch=1)

        # ## Object name
        self.name_box = QtWidgets.QHBoxLayout()
        self.tools_box.addLayout(self.name_box)
        name_label = QtWidgets.QLabel(_("Name:"))
        self.name_box.addWidget(name_label)
        self.name_entry = FCEntry()
        self.name_box.addWidget(self.name_entry)

        # ### Tools Drills ## ##
        self.tools_table_label = QtWidgets.QLabel("<b>%s</b>" % _('Tools Table'))
        self.tools_table_label.setToolTip(
           _("Tools in this Excellon object\n"
             "when are used for drilling.")
        )
        self.tools_box.addWidget(self.tools_table_label)

        self.tools_table_exc = FCTable()
        # delegate = SpinBoxDelegate(units=self.units)
        # self.tools_table_exc.setItemDelegateForColumn(1, delegate)

        self.tools_box.addWidget(self.tools_table_exc)

        self.tools_table_exc.setColumnCount(4)
        self.tools_table_exc.setHorizontalHeaderLabels(['#', _('Diameter'), 'D', 'S'])
        self.tools_table_exc.setSortingEnabled(False)
        self.tools_table_exc.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        self.empty_label = QtWidgets.QLabel('')
        self.tools_box.addWidget(self.empty_label)

        # ### Add a new Tool ## ##
        self.addtool_label = QtWidgets.QLabel('<b>%s</b>' % _('Add/Delete Tool'))
        self.addtool_label.setToolTip(
            _("Add/Delete a tool to the tool list\n"
              "for this Excellon object.")
        )
        self.tools_box.addWidget(self.addtool_label)

        grid1 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid1)
        grid1.setColumnStretch(0, 0)
        grid1.setColumnStretch(1, 1)

        addtool_entry_lbl = QtWidgets.QLabel('%s:' % _('Tool Dia'))
        addtool_entry_lbl.setToolTip(
            _("Diameter for the new tool")
        )

        hlay = QtWidgets.QHBoxLayout()
        self.addtool_entry = FCDoubleSpinner()
        self.addtool_entry.set_precision(self.decimals)
        self.addtool_entry.set_range(0.0000, 9999.9999)

        hlay.addWidget(self.addtool_entry)

        self.addtool_btn = QtWidgets.QPushButton(_('Add Tool'))
        self.addtool_btn.setToolTip(
           _("Add a new tool to the tool list\n"
             "with the diameter specified above.")
        )
        self.addtool_btn.setFixedWidth(80)
        hlay.addWidget(self.addtool_btn)

        grid1.addWidget(addtool_entry_lbl, 0, 0)
        grid1.addLayout(hlay, 0, 1)

        grid2 = QtWidgets.QGridLayout()
        self.tools_box.addLayout(grid2)

        self.deltool_btn = QtWidgets.QPushButton(_('Delete Tool'))
        self.deltool_btn.setToolTip(
           _("Delete a tool in the tool list\n"
             "by selecting a row in the tool table.")
        )
        grid2.addWidget(self.deltool_btn, 0, 1)

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add all the Drills widgets
        # this way I can hide/show the frame
        self.resize_frame = QtWidgets.QFrame()
        self.resize_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.resize_frame)
        self.resize_box = QtWidgets.QVBoxLayout()
        self.resize_box.setContentsMargins(0, 0, 0, 0)
        self.resize_frame.setLayout(self.resize_box)

        # ### Resize a  drill ## ##
        self.emptyresize_label = QtWidgets.QLabel('')
        self.resize_box.addWidget(self.emptyresize_label)

        self.drillresize_label = QtWidgets.QLabel('<b>%s</b>' % _("Resize Drill(s)"))
        self.drillresize_label.setToolTip(
            _("Resize a drill or a selection of drills.")
        )
        self.resize_box.addWidget(self.drillresize_label)

        grid3 = QtWidgets.QGridLayout()
        self.resize_box.addLayout(grid3)

        res_entry_lbl = QtWidgets.QLabel('%s:' % _('Resize Dia'))
        res_entry_lbl.setToolTip(
           _("Diameter to resize to.")
        )
        grid3.addWidget(res_entry_lbl, 0, 0)

        hlay2 = QtWidgets.QHBoxLayout()
        self.resdrill_entry = FCDoubleSpinner()
        self.resdrill_entry.set_precision(self.decimals)
        self.resdrill_entry.set_range(0.0000, 9999.9999)

        hlay2.addWidget(self.resdrill_entry)

        self.resize_btn = QtWidgets.QPushButton(_('Resize'))
        self.resize_btn.setToolTip(
            _("Resize drill(s)")
        )
        self.resize_btn.setFixedWidth(80)
        hlay2.addWidget(self.resize_btn)
        grid3.addLayout(hlay2, 0, 1)

        self.resize_frame.hide()

        # ####################################
        # ### Add DRILL Array ################
        # ####################################

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add
        # all the add drill array  widgets
        # this way I can hide/show the frame
        self.array_frame = QtWidgets.QFrame()
        self.array_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.array_frame)
        self.array_box = QtWidgets.QVBoxLayout()
        self.array_box.setContentsMargins(0, 0, 0, 0)
        self.array_frame.setLayout(self.array_box)

        self.emptyarray_label = QtWidgets.QLabel('')
        self.array_box.addWidget(self.emptyarray_label)

        self.drill_array_label = QtWidgets.QLabel('<b>%s</b>' % _("Add Drill Array"))
        self.drill_array_label.setToolTip(
            _("Add an array of drills (linear or circular array)")
        )
        self.array_box.addWidget(self.drill_array_label)

        self.array_type_combo = FCComboBox()
        self.array_type_combo.setToolTip(
           _("Select the type of drills array to create.\n"
             "It can be Linear X(Y) or Circular")
        )
        self.array_type_combo.addItem(_("Linear"))
        self.array_type_combo.addItem(_("Circular"))

        self.array_box.addWidget(self.array_type_combo)

        self.array_form = QtWidgets.QFormLayout()
        self.array_box.addLayout(self.array_form)

        # Set the number of drill holes in the drill array
        self.drill_array_size_label = QtWidgets.QLabel('%s:' % _('Nr of drills'))
        self.drill_array_size_label.setToolTip(_("Specify how many drills to be in the array."))
        self.drill_array_size_label.setMinimumWidth(100)

        self.drill_array_size_entry = FCSpinner()
        self.drill_array_size_entry.set_range(1, 9999)
        self.array_form.addRow(self.drill_array_size_label, self.drill_array_size_entry)

        self.array_linear_frame = QtWidgets.QFrame()
        self.array_linear_frame.setContentsMargins(0, 0, 0, 0)
        self.array_box.addWidget(self.array_linear_frame)
        self.linear_box = QtWidgets.QVBoxLayout()
        self.linear_box.setContentsMargins(0, 0, 0, 0)
        self.array_linear_frame.setLayout(self.linear_box)

        self.linear_form = QtWidgets.QFormLayout()
        self.linear_box.addLayout(self.linear_form)

        # Linear Drill Array direction
        self.drill_axis_label = QtWidgets.QLabel('%s:' % _('Direction'))
        self.drill_axis_label.setToolTip(
            _("Direction on which the linear array is oriented:\n"
              "- 'X' - horizontal axis \n"
              "- 'Y' - vertical axis or \n"
              "- 'Angle' - a custom angle for the array inclination")
        )
        self.drill_axis_label.setMinimumWidth(100)

        self.drill_axis_radio = RadioSet([{'label': _('X'), 'value': 'X'},
                                          {'label': _('Y'), 'value': 'Y'},
                                          {'label': _('Angle'), 'value': 'A'}])
        self.linear_form.addRow(self.drill_axis_label, self.drill_axis_radio)

        # Linear Drill Array pitch distance
        self.drill_pitch_label = QtWidgets.QLabel('%s:' % _('Pitch'))
        self.drill_pitch_label.setToolTip(
            _("Pitch = Distance between elements of the array.")
        )
        self.drill_pitch_label.setMinimumWidth(100)

        self.drill_pitch_entry = FCDoubleSpinner()
        self.drill_pitch_entry.set_precision(self.decimals)
        self.drill_pitch_entry.set_range(0.0000, 9999.9999)

        self.linear_form.addRow(self.drill_pitch_label, self.drill_pitch_entry)

        # Linear Drill Array angle
        self.linear_angle_label = QtWidgets.QLabel('%s:' % _('Angle'))
        self.linear_angle_label.setToolTip(
           _("Angle at which the linear array is placed.\n"
             "The precision is of max 2 decimals.\n"
             "Min value is: -360 degrees.\n"
             "Max value is:  360.00 degrees.")
        )
        self.linear_angle_label.setMinimumWidth(100)

        self.linear_angle_spinner = FCDoubleSpinner()
        self.linear_angle_spinner.set_precision(self.decimals)
        self.linear_angle_spinner.setSingleStep(1.0)
        self.linear_angle_spinner.setRange(-360.00, 360.00)
        self.linear_form.addRow(self.linear_angle_label, self.linear_angle_spinner)

        self.array_circular_frame = QtWidgets.QFrame()
        self.array_circular_frame.setContentsMargins(0, 0, 0, 0)
        self.array_box.addWidget(self.array_circular_frame)
        self.circular_box = QtWidgets.QVBoxLayout()
        self.circular_box.setContentsMargins(0, 0, 0, 0)
        self.array_circular_frame.setLayout(self.circular_box)

        self.drill_direction_label = QtWidgets.QLabel('%s:' % _('Direction'))
        self.drill_direction_label.setToolTip(_("Direction for circular array."
                                                "Can be CW = clockwise or CCW = counter clockwise."))
        self.drill_direction_label.setMinimumWidth(100)

        self.circular_form = QtWidgets.QFormLayout()
        self.circular_box.addLayout(self.circular_form)

        self.drill_direction_radio = RadioSet([{'label': _('CW'), 'value': 'CW'},
                                               {'label': _('CCW'), 'value': 'CCW'}])
        self.circular_form.addRow(self.drill_direction_label, self.drill_direction_radio)

        self.drill_angle_label = QtWidgets.QLabel('%s:' % _('Angle'))
        self.drill_angle_label.setToolTip(_("Angle at which each element in circular array is placed."))
        self.drill_angle_label.setMinimumWidth(100)

        self.drill_angle_entry = FCDoubleSpinner()
        self.drill_angle_entry.set_precision(self.decimals)
        self.drill_angle_entry.setSingleStep(1.0)
        self.drill_angle_entry.setRange(-360.00, 360.00)

        self.circular_form.addRow(self.drill_angle_label, self.drill_angle_entry)

        self.array_circular_frame.hide()

        self.linear_angle_spinner.hide()
        self.linear_angle_label.hide()

        self.array_frame.hide()

        # ######################################################
        # ##### ADDING SLOTS ###################################
        # ######################################################

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add
        # all the add slot  widgets
        # this way I can hide/show the frame
        self.slot_frame = QtWidgets.QFrame()
        self.slot_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.slot_frame)
        self.slot_box = QtWidgets.QVBoxLayout()
        self.slot_box.setContentsMargins(0, 0, 0, 0)
        self.slot_frame.setLayout(self.slot_box)

        self.emptyarray_label = QtWidgets.QLabel('')
        self.slot_box.addWidget(self.emptyarray_label)

        self.slot_label = QtWidgets.QLabel('<b>%s</b>' % _("Slot Parameters"))
        self.slot_label.setToolTip(
            _("Parameters for adding a slot (hole with oval shape)\n"
              "either single or as an part of an array.")
        )
        self.slot_box.addWidget(self.slot_label)

        self.slot_form = QtWidgets.QFormLayout()
        self.slot_box.addLayout(self.slot_form)

        # Slot length
        self.slot_length_label = QtWidgets.QLabel('%s:' % _('Length'))
        self.slot_length_label.setToolTip(
            _("Length = The length of the slot.")
        )
        self.slot_length_label.setMinimumWidth(100)

        self.slot_length_entry = FCDoubleSpinner()
        self.slot_length_entry.set_precision(self.decimals)
        self.slot_length_entry.setSingleStep(0.1)
        self.slot_length_entry.setRange(0.0000, 9999.9999)

        self.slot_form.addRow(self.slot_length_label, self.slot_length_entry)

        # Slot direction
        self.slot_axis_label = QtWidgets.QLabel('%s:' % _('Direction'))
        self.slot_axis_label.setToolTip(
            _("Direction on which the slot is oriented:\n"
              "- 'X' - horizontal axis \n"
              "- 'Y' - vertical axis or \n"
              "- 'Angle' - a custom angle for the slot inclination")
        )
        self.slot_axis_label.setMinimumWidth(100)

        self.slot_axis_radio = RadioSet([{'label': _('X'), 'value': 'X'},
                                         {'label': _('Y'), 'value': 'Y'},
                                         {'label': _('Angle'), 'value': 'A'}])
        self.slot_form.addRow(self.slot_axis_label, self.slot_axis_radio)

        # Slot custom angle
        self.slot_angle_label = QtWidgets.QLabel('%s:' % _('Angle'))
        self.slot_angle_label.setToolTip(
           _("Angle at which the slot is placed.\n"
             "The precision is of max 2 decimals.\n"
             "Min value is: -360 degrees.\n"
             "Max value is:  360.00 degrees.")
        )
        self.slot_angle_label.setMinimumWidth(100)

        self.slot_angle_spinner = FCDoubleSpinner()
        self.slot_angle_spinner.set_precision(self.decimals)
        self.slot_angle_spinner.setWrapping(True)
        self.slot_angle_spinner.setRange(-360.00, 360.00)
        self.slot_angle_spinner.setSingleStep(1.0)
        self.slot_form.addRow(self.slot_angle_label, self.slot_angle_spinner)

        self.slot_frame.hide()

        # ######################################################
        # ##### ADDING SLOT ARRAY  #############################
        # ######################################################

        # add a frame and inside add a vertical box layout. Inside this vbox layout I add
        # all the add slot  widgets
        # this way I can hide/show the frame
        self.slot_array_frame = QtWidgets.QFrame()
        self.slot_array_frame.setContentsMargins(0, 0, 0, 0)
        self.tools_box.addWidget(self.slot_array_frame)
        self.slot_array_box = QtWidgets.QVBoxLayout()
        self.slot_array_box.setContentsMargins(0, 0, 0, 0)
        self.slot_array_frame.setLayout(self.slot_array_box)

        self.emptyarray_label = QtWidgets.QLabel('')
        self.slot_array_box.addWidget(self.emptyarray_label)

        self.slot_array_label = QtWidgets.QLabel('<b>%s</b>' % _("Slot Array Parameters"))
        self.slot_array_label.setToolTip(
            _("Parameters for the array of slots (linear or circular array)")
        )
        self.slot_array_box.addWidget(self.slot_array_label)

        self.l_form = QtWidgets.QFormLayout()
        self.slot_array_box.addLayout(self.l_form)

        self.slot_array_type_combo = FCComboBox()
        self.slot_array_type_combo.setToolTip(
            _("Select the type of slot array to create.\n"
              "It can be Linear X(Y) or Circular")
        )
        self.slot_array_type_combo.addItem(_("Linear"))
        self.slot_array_type_combo.addItem(_("Circular"))

        self.slot_array_box.addWidget(self.slot_array_type_combo)

        self.slot_array_form = QtWidgets.QFormLayout()
        self.slot_array_box.addLayout(self.slot_array_form)

        # Set the number of slot holes in the slot array
        self.slot_array_size_label = QtWidgets.QLabel('%s:' % _('Nr of slots'))
        self.slot_array_size_label.setToolTip(_("Specify how many slots to be in the array."))
        self.slot_array_size_label.setMinimumWidth(100)

        self.slot_array_size_entry = FCSpinner()
        self.slot_array_size_entry.set_range(0, 9999)

        self.slot_array_form.addRow(self.slot_array_size_label, self.slot_array_size_entry)

        self.slot_array_linear_frame = QtWidgets.QFrame()
        self.slot_array_linear_frame.setContentsMargins(0, 0, 0, 0)
        self.slot_array_box.addWidget(self.slot_array_linear_frame)
        self.slot_array_linear_box = QtWidgets.QVBoxLayout()
        self.slot_array_linear_box.setContentsMargins(0, 0, 0, 0)
        self.slot_array_linear_frame.setLayout(self.slot_array_linear_box)

        self.slot_array_linear_form = QtWidgets.QFormLayout()
        self.slot_array_linear_box.addLayout(self.slot_array_linear_form)

        # Linear Slot Array direction
        self.slot_array_axis_label = QtWidgets.QLabel('%s:' % _('Direction'))
        self.slot_array_axis_label.setToolTip(
            _("Direction on which the linear array is oriented:\n"
              "- 'X' - horizontal axis \n"
              "- 'Y' - vertical axis or \n"
              "- 'Angle' - a custom angle for the array inclination")
        )
        self.slot_array_axis_label.setMinimumWidth(100)

        self.slot_array_axis_radio = RadioSet([{'label': _('X'), 'value': 'X'},
                                               {'label': _('Y'), 'value': 'Y'},
                                               {'label': _('Angle'), 'value': 'A'}])
        self.slot_array_linear_form.addRow(self.slot_array_axis_label, self.slot_array_axis_radio)

        # Linear Slot Array pitch distance
        self.slot_array_pitch_label = QtWidgets.QLabel('%s:' % _('Pitch'))
        self.slot_array_pitch_label.setToolTip(
            _("Pitch = Distance between elements of the array.")
        )
        self.slot_array_pitch_label.setMinimumWidth(100)

        self.slot_array_pitch_entry = FCDoubleSpinner()
        self.slot_array_pitch_entry.set_precision(self.decimals)
        self.slot_array_pitch_entry.setSingleStep(0.1)
        self.slot_array_pitch_entry.setRange(0.0000, 9999.9999)

        self.slot_array_linear_form.addRow(self.slot_array_pitch_label, self.slot_array_pitch_entry)

        # Linear Slot Array angle
        self.slot_array_linear_angle_label = QtWidgets.QLabel('%s:' % _('Angle'))
        self.slot_array_linear_angle_label.setToolTip(
            _("Angle at which the linear array is placed.\n"
              "The precision is of max 2 decimals.\n"
              "Min value is: -360 degrees.\n"
              "Max value is:  360.00 degrees.")
        )
        self.slot_array_linear_angle_label.setMinimumWidth(100)

        self.slot_array_linear_angle_spinner = FCDoubleSpinner()
        self.slot_array_linear_angle_spinner.set_precision(self.decimals)
        self.slot_array_linear_angle_spinner.setSingleStep(1.0)
        self.slot_array_linear_angle_spinner.setRange(-360.00, 360.00)
        self.slot_array_linear_form.addRow(self.slot_array_linear_angle_label, self.slot_array_linear_angle_spinner)

        self.slot_array_circular_frame = QtWidgets.QFrame()
        self.slot_array_circular_frame.setContentsMargins(0, 0, 0, 0)
        self.slot_array_box.addWidget(self.slot_array_circular_frame)
        self.slot_array_circular_box = QtWidgets.QVBoxLayout()
        self.slot_array_circular_box.setContentsMargins(0, 0, 0, 0)
        self.slot_array_circular_frame.setLayout(self.slot_array_circular_box)

        self.slot_array_direction_label = QtWidgets.QLabel('%s:' % _('Direction'))
        self.slot_array_direction_label.setToolTip(_("Direction for circular array."
                                                     "Can be CW = clockwise or CCW = counter clockwise."))
        self.slot_array_direction_label.setMinimumWidth(100)

        self.slot_array_circular_form = QtWidgets.QFormLayout()
        self.slot_array_circular_box.addLayout(self.slot_array_circular_form)

        self.slot_array_direction_radio = RadioSet([{'label': _('CW'), 'value': 'CW'},
                                                    {'label': _('CCW'), 'value': 'CCW'}])
        self.slot_array_circular_form.addRow(self.slot_array_direction_label, self.slot_array_direction_radio)

        self.slot_array_angle_label = QtWidgets.QLabel('%s:' % _('Angle'))
        self.slot_array_angle_label.setToolTip(_("Angle at which each element in circular array is placed."))
        self.slot_array_angle_label.setMinimumWidth(100)

        self.slot_array_angle_entry = FCDoubleSpinner()
        self.slot_array_angle_entry.set_precision(self.decimals)
        self.slot_array_angle_entry.setSingleStep(1)
        self.slot_array_angle_entry.setRange(-360.00, 360.00)

        self.slot_array_circular_form.addRow(self.slot_array_angle_label, self.slot_array_angle_entry)

        self.slot_array_linear_angle_spinner.hide()
        self.slot_array_linear_angle_label.hide()

        self.slot_array_frame.hide()

        self.tools_box.addStretch()

        # ## Toolbar events and properties
        self.tools_exc = {
            "drill_select": {"button": self.app.ui.select_drill_btn, "constructor": FCDrillSelect},
            "drill_add": {"button": self.app.ui.add_drill_btn, "constructor": FCDrillAdd},
            "drill_array": {"button": self.app.ui.add_drill_array_btn, "constructor": FCDrillArray},
            "slot_add": {"button": self.app.ui.add_slot_btn, "constructor": FCSlot},
            "slot_array": {"button": self.app.ui.add_slot_array_btn, "constructor": FCSlotArray},
            "drill_resize": {"button": self.app.ui.resize_drill_btn, "constructor": FCDrillResize},
            "drill_copy": {"button": self.app.ui.copy_drill_btn, "constructor": FCDrillCopy},
            "drill_move": {"button": self.app.ui.move_drill_btn, "constructor": FCDrillMove},
        }

        # ## Data
        self.active_tool = None

        self.in_action = False

        self.storage_dict = {}

        self.current_storage = []

        # build the data from the Excellon point into a dictionary
        #  {tool_dia: [geometry_in_points]}
        self.points_edit = {}
        self.slot_points_edit = {}

        self.sorted_diameters = []

        self.new_drills = []
        self.new_tools = {}
        self.new_slots = []

        # dictionary to store the tool_row and diameters in Tool_table
        # it will be updated everytime self.build_ui() is called
        self.olddia_newdia = {}

        self.tool2tooldia = {}

        # this will store the value for the last selected tool, for use after clicking on canvas when the selection
        # is cleared but as a side effect also the selected tool is cleared
        self.last_tool_selected = None
        self.utility = []

        # this will flag if the Editor "tools" are launched from key shortcuts (True) or from menu toolbar (False)
        self.launched_from_shortcuts = False

        # this var will store the state of the toolbar before starting the editor
        self.toolbar_old_state = False

        if self.units == 'MM':
            self.tolerance = float(self.app.defaults["global_tolerance"])
        else:
            self.tolerance = float(self.app.defaults["global_tolerance"]) / 20

        self.app.ui.delete_drill_btn.triggered.connect(self.on_delete_btn)
        self.name_entry.returnPressed.connect(self.on_name_activate)
        self.addtool_btn.clicked.connect(self.on_tool_add)
        self.addtool_entry.editingFinished.connect(self.on_tool_add)
        self.deltool_btn.clicked.connect(self.on_tool_delete)
        # self.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)
        self.tools_table_exc.cellPressed.connect(self.on_row_selected)

        self.array_type_combo.currentIndexChanged.connect(self.on_array_type_combo)
        self.slot_array_type_combo.currentIndexChanged.connect(self.on_slot_array_type_combo)

        self.drill_axis_radio.activated_custom.connect(self.on_linear_angle_radio)
        self.slot_axis_radio.activated_custom.connect(self.on_slot_angle_radio)

        self.slot_array_axis_radio.activated_custom.connect(self.on_slot_array_linear_angle_radio)

        self.app.ui.exc_add_array_drill_menuitem.triggered.connect(self.exc_add_drill_array)
        self.app.ui.exc_add_drill_menuitem.triggered.connect(self.exc_add_drill)

        self.app.ui.exc_add_array_slot_menuitem.triggered.connect(self.exc_add_slot_array)
        self.app.ui.exc_add_slot_menuitem.triggered.connect(self.exc_add_slot)

        self.app.ui.exc_resize_drill_menuitem.triggered.connect(self.exc_resize_drills)
        self.app.ui.exc_copy_drill_menuitem.triggered.connect(self.exc_copy_drills)
        self.app.ui.exc_delete_drill_menuitem.triggered.connect(self.on_delete_btn)

        self.app.ui.exc_move_drill_menuitem.triggered.connect(self.exc_move_drills)

        self.exc_obj = None

        # VisPy Visuals
        if self.app.is_legacy is False:
            self.shapes = self.app.plotcanvas.new_shape_collection(layers=1)
            if self.app.plotcanvas.big_cursor is True:
                self.tool_shape = self.app.plotcanvas.new_shape_collection(layers=1)
            else:
                self.tool_shape = self.app.plotcanvas.new_shape_collection(layers=1)
        else:
            from flatcamGUI.PlotCanvasLegacy import ShapeCollectionLegacy
            self.shapes = ShapeCollectionLegacy(obj=self, app=self.app, name='shapes_exc_editor')
            self.tool_shape = ShapeCollectionLegacy(obj=self, app=self.app, name='tool_shapes_exc_editor')

        self.app.pool_recreated.connect(self.pool_recreated)

        # Remove from scene
        self.shapes.enabled = False
        self.tool_shape.enabled = False

        # ## List of selected shapes.
        self.selected = []

        self.move_timer = QtCore.QTimer()
        self.move_timer.setSingleShot(True)

        self.key = None  # Currently pressed key
        self.modifiers = None
        self.x = None  # Current mouse cursor pos
        self.y = None
        # Current snapped mouse pos
        self.snap_x = None
        self.snap_y = None
        self.pos = None

        self.complete = False

        def make_callback(thetool):
            def f():
                self.on_tool_select(thetool)
            return f

        for tool in self.tools_exc:
            self.tools_exc[tool]["button"].triggered.connect(make_callback(tool))  # Events
            self.tools_exc[tool]["button"].setCheckable(True)  # Checkable

        self.options = {
            "global_gridx": 0.1,
            "global_gridy": 0.1,
            "snap_max": 0.05,
            "grid_snap": True,
            "corner_snap": False,
            "grid_gap_link": True
        }
        self.options.update(self.app.options)

        for option in self.options:
            if option in self.app.options:
                self.options[option] = self.app.options[option]

        self.data_defaults = {
            "plot": self.app.defaults["excellon_plot"],
            "solid": self.app.defaults["excellon_solid"],

            "operation": self.app.defaults["excellon_operation"],
            "milling_type": self.app.defaults["excellon_milling_type"],

            "milling_dia": self.app.defaults["excellon_milling_dia"],

            "cutz": self.app.defaults["excellon_cutz"],
            "multidepth": self.app.defaults["excellon_multidepth"],
            "depthperpass": self.app.defaults["excellon_depthperpass"],
            "travelz": self.app.defaults["excellon_travelz"],
            "feedrate": self.app.defaults["geometry_feedrate"],
            "feedrate_z": self.app.defaults["excellon_feedrate_z"],
            "feedrate_rapid": self.app.defaults["excellon_feedrate_rapid"],
            "tooldia": self.app.defaults["excellon_tooldia"],
            "slot_tooldia": self.app.defaults["excellon_slot_tooldia"],
            "toolchange": self.app.defaults["excellon_toolchange"],
            "toolchangez": self.app.defaults["excellon_toolchangez"],
            "toolchangexy": self.app.defaults["excellon_toolchangexy"],
            "extracut": self.app.defaults["geometry_extracut"],
            "extracut_length": self.app.defaults["geometry_extracut_length"],
            "endz": self.app.defaults["excellon_endz"],
            "endxy": self.app.defaults["excellon_endxy"],
            "startz": self.app.defaults["excellon_startz"],
            "offset": self.app.defaults["excellon_offset"],
            "spindlespeed": self.app.defaults["excellon_spindlespeed"],
            "dwell": self.app.defaults["excellon_dwell"],
            "dwelltime": self.app.defaults["excellon_dwelltime"],
            "ppname_e": self.app.defaults["excellon_ppname_e"],
            "ppname_g": self.app.defaults["geometry_ppname_g"],
            "z_pdepth": self.app.defaults["excellon_z_pdepth"],
            "feedrate_probe": self.app.defaults["excellon_feedrate_probe"],
            "optimization_type": self.app.defaults["excellon_optimization_type"]
        }

        self.rtree_exc_index = rtindex.Index()
        # flag to show if the object was modified
        self.is_modified = False

        self.edited_obj_name = ""

        # variable to store the total amount of drills per job
        self.tot_drill_cnt = 0
        self.tool_row = 0

        # variable to store the total amount of slots per job
        self.tot_slot_cnt = 0
        self.tool_row_slots = 0

        self.tool_row = 0

        # store the status of the editor so the Delete at object level will not work until the edit is finished
        self.editor_active = False

        # def entry2option(option, entry):
        #     self.options[option] = float(entry.text())

        # Event signals disconnect id holders
        self.mp = None
        self.mm = None
        self.mr = None

        # store the status of the editor so the Delete at object level will not work until the edit is finished
        self.editor_active = False
        log.debug("Initialization of the FlatCAM Excellon Editor is finished ...")

    def pool_recreated(self, pool):
        self.shapes.pool = pool
        self.tool_shape.pool = pool

    @staticmethod
    def make_storage():
        # ## Shape storage.
        storage = FlatCAMRTreeStorage()
        storage.get_points = DrawToolShape.get_pts

        return storage

    def set_ui(self):
        # updated units
        self.units = self.app.defaults['units'].upper()

        self.olddia_newdia.clear()
        self.tool2tooldia.clear()

        # build the self.points_edit dict {dimaters: [point_list]}
        for drill in self.exc_obj.drills:
            if drill['tool'] in self.exc_obj.tools:
                tool_dia = float('%.*f' % (self.decimals, self.exc_obj.tools[drill['tool']]['C']))

                try:
                    self.points_edit[tool_dia].append(drill['point'])
                except KeyError:
                    self.points_edit[tool_dia] = [drill['point']]

        # build the self.slot_points_edit dict {dimaters: {"start": Point, "stop": Point}}
        for slot in self.exc_obj.slots:
            if slot['tool'] in self.exc_obj.tools:
                tool_dia = float('%.*f' % (self.decimals, self.exc_obj.tools[slot['tool']]['C']))

                try:
                    self.slot_points_edit[tool_dia].append({
                        "start": slot["start"],
                        "stop": slot["stop"]
                    })
                except KeyError:
                    self.slot_points_edit[tool_dia] = [{
                        "start": slot["start"],
                        "stop": slot["stop"]
                    }]

        # update the olddia_newdia dict to make sure we have an updated state of the tool_table
        for key in self.points_edit:
            self.olddia_newdia[key] = key

        for key in self.slot_points_edit:
            if key not in self.olddia_newdia:
                self.olddia_newdia[key] = key

        sort_temp = []
        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # populate self.intial_table_rows dict with the tool number as keys and tool diameters as values
        if self.exc_obj.diameterless is False:
            for i in range(len(self.sorted_diameters)):
                tt_dia = self.sorted_diameters[i]
                self.tool2tooldia[i + 1] = tt_dia
        else:
            # the Excellon object has diameters that are bogus information, added by the application because the
            # Excellon file has no tool diameter information. In this case do not order the diameter in the table
            # but use the real order found in the exc_obj.tools
            for k, v in self.exc_obj.tools.items():
                tool_dia = float('%.*f' % (self.decimals, v['C']))
                self.tool2tooldia[int(k)] = tool_dia

        # Init GUI
        self.addtool_entry.set_value(float(self.app.defaults['excellon_editor_newdia']))
        self.drill_array_size_entry.set_value(int(self.app.defaults['excellon_editor_array_size']))
        self.drill_axis_radio.set_value(self.app.defaults['excellon_editor_lin_dir'])
        self.drill_pitch_entry.set_value(float(self.app.defaults['excellon_editor_lin_pitch']))
        self.linear_angle_spinner.set_value(float(self.app.defaults['excellon_editor_lin_angle']))
        self.drill_direction_radio.set_value(self.app.defaults['excellon_editor_circ_dir'])
        self.drill_angle_entry.set_value(float(self.app.defaults['excellon_editor_circ_angle']))

        self.slot_length_entry.set_value(float(self.app.defaults['excellon_editor_slot_length']))
        self.slot_axis_radio.set_value(self.app.defaults['excellon_editor_slot_direction'])
        self.slot_angle_spinner.set_value(float(self.app.defaults['excellon_editor_slot_angle']))

        self.slot_array_size_entry.set_value(int(self.app.defaults['excellon_editor_slot_array_size']))
        self.slot_array_axis_radio.set_value(self.app.defaults['excellon_editor_slot_lin_dir'])
        self.slot_array_pitch_entry.set_value(float(self.app.defaults['excellon_editor_slot_lin_pitch']))
        self.slot_array_linear_angle_spinner.set_value(float(self.app.defaults['excellon_editor_slot_lin_angle']))
        self.slot_array_direction_radio.set_value(self.app.defaults['excellon_editor_slot_circ_dir'])
        self.slot_array_angle_entry.set_value(float(self.app.defaults['excellon_editor_slot_circ_angle']))

        self.slot_array_circular_frame.hide()
        self.slot_array_linear_frame.show()

    def build_ui(self, first_run=None):

        try:
            # if connected, disconnect the signal from the slot on item_changed as it creates issues
            self.tools_table_exc.itemChanged.disconnect()
        except (TypeError, AttributeError):
            pass

        try:
            self.tools_table_exc.cellPressed.disconnect()
        except (TypeError, AttributeError):
            pass

        # updated units
        self.units = self.app.defaults['units'].upper()

        # make a new name for the new Excellon object (the one with edited content)
        self.edited_obj_name = self.exc_obj.options['name']
        self.name_entry.set_value(self.edited_obj_name)

        sort_temp = []

        for diam in self.olddia_newdia:
            sort_temp.append(float(diam))
        self.sorted_diameters = sorted(sort_temp)

        # here, self.sorted_diameters will hold in a oblique way, the number of tools
        n = len(self.sorted_diameters)
        # we have (n+2) rows because there are 'n' tools, each a row, plus the last 2 rows for totals.
        self.tools_table_exc.setRowCount(n + 2)

        self.tot_drill_cnt = 0
        self.tot_slot_cnt = 0

        self.tool_row = 0
        # this variable will serve as the real tool_number
        tool_id = 0

        for tool_no in self.sorted_diameters:
            tool_id += 1
            drill_cnt = 0  # variable to store the nr of drills per tool
            slot_cnt = 0  # variable to store the nr of slots per tool

            # Find no of drills for the current tool
            for tool_dia in self.points_edit:
                if float(tool_dia) == tool_no:
                    drill_cnt = len(self.points_edit[tool_dia])

            self.tot_drill_cnt += drill_cnt

            try:
                # Find no of slots for the current tool
                for slot in self.slot_points_edit:
                    if slot['tool'] == tool_no:
                        slot_cnt += 1

                self.tot_slot_cnt += slot_cnt
            except AttributeError:
                # log.debug("No slots in the Excellon file")
                # Find no of slots for the current tool
                for tool_dia in self.slot_points_edit:
                    if float(tool_dia) == tool_no:
                        slot_cnt = len(self.slot_points_edit[tool_dia])

                self.tot_slot_cnt += slot_cnt

            idd = QtWidgets.QTableWidgetItem('%d' % int(tool_id))
            idd.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.tools_table_exc.setItem(self.tool_row, 0, idd)  # Tool name/id

            # Make sure that the drill diameter when in MM is with no more than 2 decimals
            # There are no drill bits in MM with more than 2 decimals diameter
            # For INCH the decimals should be no more than 4. There are no drills under 10mils
            dia = QtWidgets.QTableWidgetItem('%.*f' % (self.decimals, self.olddia_newdia[tool_no]))

            dia.setFlags(QtCore.Qt.ItemIsEnabled)

            drill_count = QtWidgets.QTableWidgetItem('%d' % drill_cnt)
            drill_count.setFlags(QtCore.Qt.ItemIsEnabled)

            # if the slot number is zero is better to not clutter the GUI with zero's so we print a space
            if slot_cnt > 0:
                slot_count = QtWidgets.QTableWidgetItem('%d' % slot_cnt)
            else:
                slot_count = QtWidgets.QTableWidgetItem('')
            slot_count.setFlags(QtCore.Qt.ItemIsEnabled)

            self.tools_table_exc.setItem(self.tool_row, 1, dia)  # Diameter
            self.tools_table_exc.setItem(self.tool_row, 2, drill_count)  # Number of drills per tool
            self.tools_table_exc.setItem(self.tool_row, 3, slot_count)  # Number of drills per tool

            if first_run is True:
                # set now the last tool selected
                self.last_tool_selected = int(tool_id)

            self.tool_row += 1

        # make the diameter column editable
        for row in range(self.tool_row):
            self.tools_table_exc.item(row, 1).setFlags(
                QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.tools_table_exc.item(row, 2).setForeground(QtGui.QColor(0, 0, 0))
            self.tools_table_exc.item(row, 3).setForeground(QtGui.QColor(0, 0, 0))

        # add a last row with the Total number of drills
        # HACK: made the text on this cell '9999' such it will always be the one before last when sorting
        # it will have to have the foreground color (font color) white
        empty = QtWidgets.QTableWidgetItem('9998')
        empty.setForeground(QtGui.QColor(255, 255, 255))

        empty.setFlags(empty.flags() ^ QtCore.Qt.ItemIsEnabled)
        empty_b = QtWidgets.QTableWidgetItem('')
        empty_b.setFlags(empty_b.flags() ^ QtCore.Qt.ItemIsEnabled)

        label_tot_drill_count = QtWidgets.QTableWidgetItem(_('Total Drills'))
        tot_drill_count = QtWidgets.QTableWidgetItem('%d' % self.tot_drill_cnt)

        label_tot_drill_count.setFlags(label_tot_drill_count.flags() ^ QtCore.Qt.ItemIsEnabled)
        tot_drill_count.setFlags(tot_drill_count.flags() ^ QtCore.Qt.ItemIsEnabled)

        self.tools_table_exc.setItem(self.tool_row, 0, empty)
        self.tools_table_exc.setItem(self.tool_row, 1, label_tot_drill_count)
        self.tools_table_exc.setItem(self.tool_row, 2, tot_drill_count)  # Total number of drills
        self.tools_table_exc.setItem(self.tool_row, 3, empty_b)

        font = QtGui.QFont()
        font.setBold(True)
        font.setWeight(75)

        for k in [1, 2]:
            self.tools_table_exc.item(self.tool_row, k).setForeground(QtGui.QColor(127, 0, 255))
            self.tools_table_exc.item(self.tool_row, k).setFont(font)

        self.tool_row += 1

        # add a last row with the Total number of slots
        # HACK: made the text on this cell '9999' such it will always be the last when sorting
        # it will have to have the foreground color (font color) white
        empty_2 = QtWidgets.QTableWidgetItem('9999')
        empty_2.setForeground(QtGui.QColor(255, 255, 255))

        empty_2.setFlags(empty_2.flags() ^ QtCore.Qt.ItemIsEnabled)

        empty_3 = QtWidgets.QTableWidgetItem('')
        empty_3.setFlags(empty_3.flags() ^ QtCore.Qt.ItemIsEnabled)

        label_tot_slot_count = QtWidgets.QTableWidgetItem(_('Total Slots'))
        tot_slot_count = QtWidgets.QTableWidgetItem('%d' % self.tot_slot_cnt)
        label_tot_slot_count.setFlags(label_tot_slot_count.flags() ^ QtCore.Qt.ItemIsEnabled)
        tot_slot_count.setFlags(tot_slot_count.flags() ^ QtCore.Qt.ItemIsEnabled)

        self.tools_table_exc.setItem(self.tool_row, 0, empty_2)
        self.tools_table_exc.setItem(self.tool_row, 1, label_tot_slot_count)
        self.tools_table_exc.setItem(self.tool_row, 2, empty_3)
        self.tools_table_exc.setItem(self.tool_row, 3, tot_slot_count)  # Total number of slots

        for kl in [1, 2, 3]:
            self.tools_table_exc.item(self.tool_row, kl).setFont(font)
            self.tools_table_exc.item(self.tool_row, kl).setForeground(QtGui.QColor(0, 70, 255))

        # all the tools are selected by default
        self.tools_table_exc.selectColumn(0)
        #
        self.tools_table_exc.resizeColumnsToContents()
        self.tools_table_exc.resizeRowsToContents()

        vertical_header = self.tools_table_exc.verticalHeader()
        # vertical_header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        vertical_header.hide()
        self.tools_table_exc.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        horizontal_header = self.tools_table_exc.horizontalHeader()
        horizontal_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        horizontal_header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        horizontal_header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        horizontal_header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        # horizontal_header.setStretchLastSection(True)

        # self.tools_table_exc.setSortingEnabled(True)
        # sort by tool diameter
        self.tools_table_exc.sortItems(1)

        # After sorting, to display also the number of drills in the right row we need to update self.initial_rows dict
        # with the new order. Of course the last 2 rows in the tool table are just for display therefore we don't
        # use them
        self.tool2tooldia.clear()
        for row in range(self.tools_table_exc.rowCount() - 2):
            tool = int(self.tools_table_exc.item(row, 0).text())
            diameter = float(self.tools_table_exc.item(row, 1).text())
            self.tool2tooldia[tool] = diameter

        self.tools_table_exc.setMinimumHeight(self.tools_table_exc.getHeight())
        self.tools_table_exc.setMaximumHeight(self.tools_table_exc.getHeight())

        # make sure no rows are selected so the user have to click the correct row, meaning selecting the correct tool
        self.tools_table_exc.clearSelection()

        # Remove anything else in the GUI Selected Tab
        self.app.ui.selected_scroll_area.takeWidget()
        # Put ourself in the GUI Selected Tab
        self.app.ui.selected_scroll_area.setWidget(self.exc_edit_widget)
        # Switch notebook to Selected page
        self.app.ui.notebook.setCurrentWidget(self.app.ui.selected_tab)

        # we reactivate the signals after the after the tool adding as we don't need to see the tool been populated
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)
        self.tools_table_exc.cellPressed.connect(self.on_row_selected)

    def on_tool_add(self, tooldia=None):
        self.is_modified = True
        if tooldia:
            tool_dia = tooldia
        else:
            try:
                tool_dia = float(self.addtool_entry.get_value())
            except ValueError:
                # try to convert comma to decimal point. if it's still not working error message and return
                try:
                    tool_dia = float(self.addtool_entry.get_value().replace(',', '.'))
                except ValueError:
                    self.app.inform.emit('[ERROR_NOTCL] %s' %
                                         _("Wrong value format entered, use a number."))
                    return

        if tool_dia not in self.olddia_newdia:
            storage_elem = FlatCAMGeoEditor.make_storage()
            self.storage_dict[tool_dia] = storage_elem

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.olddia_newdia[tool_dia] = tool_dia
        else:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Tool already in the original or actual tool list.\n" 
                                                          "Save and reedit Excellon if you need to add this tool. "))
            return

        # since we add a new tool, we update also the initial state of the tool_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.tool2tooldia[len(self.olddia_newdia)] = tool_dia

        self.app.inform.emit('[success] %s: %s %s' %
                             (_("Added new tool with dia"), str(tool_dia), str(self.units)))

        self.build_ui()

        # make a quick sort through the tool2tooldia dict so we find which row to select
        row_to_be_selected = None
        for key in sorted(self.tool2tooldia):
            if self.tool2tooldia[key] == tool_dia:
                row_to_be_selected = int(key) - 1
                self.last_tool_selected = int(key)
                break
        try:
            self.tools_table_exc.selectRow(row_to_be_selected)
        except TypeError as e:
            log.debug("FlatCAMExcEditor.on_tool_add() --> %s" % str(e))

    def on_tool_delete(self, dia=None):
        self.is_modified = True
        deleted_tool_dia_list = []

        try:
            if dia is None or dia is False:
                # deleted_tool_dia = float(self.tools_table_exc.item(self.tools_table_exc.currentRow(), 1).text())
                for index in self.tools_table_exc.selectionModel().selectedRows():
                    row = index.row()
                    deleted_tool_dia_list.append(float(self.tools_table_exc.item(row, 1).text()))
            else:
                if isinstance(dia, list):
                    for dd in dia:
                        deleted_tool_dia_list.append(float('%.*f' % (self.decimals, dd)))
                else:
                    deleted_tool_dia_list.append(float('%.*f' % (self.decimals, dia)))
        except Exception:
            self.app.inform.emit('[WARNING_NOTCL] %s' % _("Select a tool in Tool Table"))
            return

        for deleted_tool_dia in deleted_tool_dia_list:

            # delete the storage used for that tool
            storage_elem = FlatCAMGeoEditor.make_storage()
            self.storage_dict[deleted_tool_dia] = storage_elem
            self.storage_dict.pop(deleted_tool_dia, None)

            # I've added this flag_del variable because dictionary don't like
            # having keys deleted while iterating through them
            flag_del = []
            # self.points_edit.pop(deleted_tool_dia, None)
            for deleted_tool in self.tool2tooldia:
                if self.tool2tooldia[deleted_tool] == deleted_tool_dia:
                    flag_del.append(deleted_tool)

            if flag_del:
                for tool_to_be_deleted in flag_del:
                    # delete the tool
                    self.tool2tooldia.pop(tool_to_be_deleted, None)

                    # delete also the drills from points_edit dict just in case we add the tool again,
                    # we don't want to show the number of drills from before was deleter
                    self.points_edit[deleted_tool_dia] = []

            self.olddia_newdia.pop(deleted_tool_dia, None)

            self.app.inform.emit('[success] %s: %s %s' %
                                 (_("Deleted tool with diameter"), str(deleted_tool_dia), str(self.units)))

        self.replot()
        # self.app.inform.emit("Could not delete selected tool")

        self.build_ui()

    def on_tool_edit(self, item_changed):
        # if connected, disconnect the signal from the slot on item_changed as it creates issues
        try:
            self.tools_table_exc.itemChanged.disconnect()
        except TypeError:
            pass

        try:
            self.tools_table_exc.cellPressed.disconnect()
        except TypeError:
            pass
        # self.tools_table_exc.selectionModel().currentChanged.disconnect()

        self.is_modified = True
        # new_dia = None

        try:
            new_dia = float(self.tools_table_exc.currentItem().text())
        except ValueError as e:
            log.debug("FlatCAMExcEditor.on_tool_edit() --> %s" % str(e))
            return

        row_of_item_changed = self.tools_table_exc.currentRow()
        # rows start with 0, tools start with 1 so we adjust the value by 1
        key_in_tool2tooldia = row_of_item_changed + 1
        old_dia = self.tool2tooldia[key_in_tool2tooldia]

        # SOURCE storage
        source_storage = self.storage_dict[old_dia]

        # DESTINATION storage
        # tool diameter is not used so we create a new tool with the desired diameter
        if new_dia not in self.olddia_newdia:
            destination_storage = FlatCAMGeoEditor.make_storage()
            self.storage_dict[new_dia] = destination_storage

            # self.olddia_newdia dict keeps the evidence on current tools diameters as keys and gets updated on values
            # each time a tool diameter is edited or added
            self.olddia_newdia[new_dia] = new_dia
        else:
            # tool diameter is already in use so we move the drills from the prior tool to the new tool
            destination_storage = self.storage_dict[new_dia]

        # since we add a new tool, we update also the intial state of the tool_table through it's dictionary
        # we add a new entry in the tool2tooldia dict
        self.tool2tooldia[len(self.olddia_newdia)] = new_dia

        # CHANGE the elements geometry according to the new diameter
        factor = new_dia / old_dia
        new_geo = Polygon()
        for shape_exc in source_storage.get_objects():
            geo_list = []
            if isinstance(shape_exc.geo, MultiLineString):
                for subgeo in shape_exc.geo:
                    geo_list.append(affinity.scale(subgeo, xfact=factor, yfact=factor, origin='center'))
                new_geo = MultiLineString(geo_list)
            elif isinstance(shape_exc.geo, Polygon):
                # I don't have any info regarding the angle of the slot geometry, nor how thick it is or
                # how long it is given the angle. So I will have to make an approximation because
                # we need to conserve the slot length, we only resize the diameter for the tool
                # Therefore scaling won't work and buffering will not work either.

                # First we get the Linestring that is one that the original slot is built around with the
                # tool having the diameter sel_dia
                poly = shape_exc.geo
                xmin, ymin, xmax, ymax = poly.bounds
                # a line that is certain to be bigger than our slot because it's the diagonal
                # of it's bounding box
                poly_diagonal = LineString([(xmin, ymin), (xmax, ymax)])
                poly_centroid = poly.centroid
                # center of the slot geometry
                poly_center = (poly_centroid.x, poly_centroid.y)

                # make a list of intersections with the rotated line
                list_of_cuttings = []
                for angle in range(0, 359, 1):
                    rot_poly_diagonal = affinity.rotate(poly_diagonal, angle=angle, origin=poly_center)
                    cut_line = rot_poly_diagonal.intersection(poly)
                    cut_line_len = cut_line.length
                    list_of_cuttings.append(
                        (cut_line_len, cut_line)
                    )
                # find the cut_line with the maximum length which is the LineString for which the start
                # and stop point are the start and stop point of the slot as in the Gerber file
                cut_line_with_max_length = max(list_of_cuttings, key=lambda i: i[0])[1]
                # find the coordinates of this line
                cut_line_with_max_length_coords = list(cut_line_with_max_length.coords)
                # extract the first and last point of the line and build some buffered polygon circles
                # around them
                start_pt = Point(cut_line_with_max_length_coords[0])
                stop_pt = Point(cut_line_with_max_length_coords[1])
                start_cut_geo = start_pt.buffer(new_dia / 2)
                stop_cut_geo = stop_pt.buffer(new_dia / 2)

                # and we cut the above circle polygons from our line and get in this way a line around
                # which we can build the new slot by buffering with the new tool diameter
                new_line = cut_line_with_max_length.difference(start_cut_geo)
                new_line = new_line.difference(stop_cut_geo)

                # create the geometry for the resized slot by buffering with half of the
                # new diameter value: new_dia
                new_geo = new_line.buffer(new_dia / 2)

            try:
                self.points_edit.pop(old_dia, None)
            except KeyError:
                pass
            try:
                self.slot_points_edit.pop(old_dia, None)
            except KeyError:
                pass

            # add bogus drill/slots points (for total count of drills/slots)
            # for drills
            if isinstance(shape_exc.geo, MultiLineString):
                if new_dia not in self.points_edit:
                    self.points_edit[new_dia] = [(0, 0)]
                else:
                    self.points_edit[new_dia].append((0, 0))

            # for slots
            if isinstance(shape_exc.geo, Polygon):
                if new_dia not in self.slot_points_edit:
                    self.slot_points_edit[new_dia] = [(0, 0)]
                else:
                    self.slot_points_edit[new_dia].append((0, 0))

            self.add_exc_shape(shape=DrawToolShape(new_geo), storage=destination_storage)

        # update the UI and the CANVAS
        self.build_ui()
        self.replot()

        # delete the old tool
        self.on_tool_delete(dia=old_dia)

        # we reactivate the signals after the after the tool editing
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)
        self.tools_table_exc.cellPressed.connect(self.on_row_selected)

        self.app.inform.emit('[success] %s' %
                             _("Done. Tool edit completed."))

        # self.tools_table_exc.selectionModel().currentChanged.connect(self.on_row_selected)

    def on_name_activate(self):
        self.edited_obj_name = self.name_entry.get_value()

    def activate(self):
        # adjust the status of the menu entries related to the editor
        self.app.ui.menueditedit.setDisabled(True)
        self.app.ui.menueditok.setDisabled(False)
        # adjust the visibility of some of the canvas context menu
        self.app.ui.popmenu_edit.setVisible(False)
        self.app.ui.popmenu_save.setVisible(True)

        self.connect_canvas_event_handlers()

        # initialize working objects
        self.storage_dict = {}
        self.current_storage = []
        self.points_edit = {}
        self.sorted_diameters = []
        self.new_drills = []
        self.new_tools = {}
        self.new_slots = []

        self.olddia_newdia = {}

        self.shapes.enabled = True
        self.tool_shape.enabled = True
        # self.app.app_cursor.enabled = True

        self.app.ui.snap_max_dist_entry.setEnabled(True)
        self.app.ui.corner_snap_btn.setEnabled(True)
        self.app.ui.snap_magnet.setVisible(True)
        self.app.ui.corner_snap_btn.setVisible(True)

        self.app.ui.exc_editor_menu.setDisabled(False)
        self.app.ui.exc_editor_menu.menuAction().setVisible(True)

        self.app.ui.update_obj_btn.setEnabled(True)
        self.app.ui.e_editor_cmenu.setEnabled(True)

        self.app.ui.exc_edit_toolbar.setDisabled(False)
        self.app.ui.exc_edit_toolbar.setVisible(True)
        # self.app.ui.snap_toolbar.setDisabled(False)

        # start with GRID toolbar activated
        if self.app.ui.grid_snap_btn.isChecked() is False:
            self.app.ui.grid_snap_btn.trigger()
            self.app.ui.on_grid_snap_triggered(state=True)

        self.app.ui.popmenu_disable.setVisible(False)
        self.app.ui.cmenu_newmenu.menuAction().setVisible(False)
        self.app.ui.popmenu_properties.setVisible(False)
        self.app.ui.e_editor_cmenu.menuAction().setVisible(True)
        self.app.ui.g_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.grb_editor_cmenu.menuAction().setVisible(False)

        # Tell the App that the editor is active
        self.editor_active = True

        # show the UI
        self.drills_frame.show()

    def deactivate(self):
        try:
            QtGui.QGuiApplication.restoreOverrideCursor()
        except Exception:
            pass

        # adjust the status of the menu entries related to the editor
        self.app.ui.menueditedit.setDisabled(False)
        self.app.ui.menueditok.setDisabled(True)
        # adjust the visibility of some of the canvas context menu
        self.app.ui.popmenu_edit.setVisible(True)
        self.app.ui.popmenu_save.setVisible(False)

        self.disconnect_canvas_event_handlers()
        self.clear()
        self.app.ui.exc_edit_toolbar.setDisabled(True)

        settings = QSettings("Open Source", "FlatCAM")
        if settings.contains("layout"):
            layout = settings.value('layout', type=str)
            if layout == 'standard':
                # self.app.ui.exc_edit_toolbar.setVisible(False)

                self.app.ui.snap_max_dist_entry.setEnabled(False)
                self.app.ui.corner_snap_btn.setEnabled(False)
                self.app.ui.snap_magnet.setVisible(False)
                self.app.ui.corner_snap_btn.setVisible(False)
            else:
                # self.app.ui.exc_edit_toolbar.setVisible(True)

                self.app.ui.snap_max_dist_entry.setEnabled(False)
                self.app.ui.corner_snap_btn.setEnabled(False)
                self.app.ui.snap_magnet.setVisible(True)
                self.app.ui.corner_snap_btn.setVisible(True)
        else:
            # self.app.ui.exc_edit_toolbar.setVisible(False)

            self.app.ui.snap_max_dist_entry.setEnabled(False)
            self.app.ui.corner_snap_btn.setEnabled(False)
            self.app.ui.snap_magnet.setVisible(False)
            self.app.ui.corner_snap_btn.setVisible(False)

        # set the Editor Toolbar visibility to what was before entering in the Editor
        self.app.ui.exc_edit_toolbar.setVisible(False) if self.toolbar_old_state is False \
            else self.app.ui.exc_edit_toolbar.setVisible(True)

        # Disable visuals
        self.shapes.enabled = False
        self.tool_shape.enabled = False
        # self.app.app_cursor.enabled = False

        # Tell the app that the editor is no longer active
        self.editor_active = False

        self.app.ui.exc_editor_menu.setDisabled(True)
        self.app.ui.exc_editor_menu.menuAction().setVisible(False)

        self.app.ui.update_obj_btn.setEnabled(False)

        self.app.ui.popmenu_disable.setVisible(True)
        self.app.ui.cmenu_newmenu.menuAction().setVisible(True)
        self.app.ui.popmenu_properties.setVisible(True)
        self.app.ui.g_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.e_editor_cmenu.menuAction().setVisible(False)
        self.app.ui.grb_editor_cmenu.menuAction().setVisible(False)

        # Show original geometry
        if self.exc_obj:
            self.exc_obj.visible = True

        # hide the UI
        self.drills_frame.hide()

    def connect_canvas_event_handlers(self):
        # ## Canvas events

        # first connect to new, then disconnect the old handlers
        # don't ask why but if there is nothing connected I've seen issues
        self.mp = self.canvas.graph_event_connect('mouse_press', self.on_canvas_click)
        self.mm = self.canvas.graph_event_connect('mouse_move', self.on_canvas_move)
        self.mr = self.canvas.graph_event_connect('mouse_release', self.on_exc_click_release)

        # make sure that the shortcuts key and mouse events will no longer be linked to the methods from FlatCAMApp
        # but those from FlatCAMGeoEditor
        if self.app.is_legacy is False:
            self.app.plotcanvas.graph_event_disconnect('mouse_press', self.app.on_mouse_click_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_move', self.app.on_mouse_move_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_release', self.app.on_mouse_click_release_over_plot)
            self.app.plotcanvas.graph_event_disconnect('mouse_double_click', self.app.on_mouse_double_click_over_plot)
        else:
            self.app.plotcanvas.graph_event_disconnect(self.app.mp)
            self.app.plotcanvas.graph_event_disconnect(self.app.mm)
            self.app.plotcanvas.graph_event_disconnect(self.app.mr)
            self.app.plotcanvas.graph_event_disconnect(self.app.mdc)

        self.app.collection.view.clicked.disconnect()

        self.app.ui.popmenu_copy.triggered.disconnect()
        self.app.ui.popmenu_delete.triggered.disconnect()
        self.app.ui.popmenu_move.triggered.disconnect()

        self.app.ui.popmenu_copy.triggered.connect(self.exc_copy_drills)
        self.app.ui.popmenu_delete.triggered.connect(self.on_delete_btn)
        self.app.ui.popmenu_move.triggered.connect(self.exc_move_drills)

        # Excellon Editor
        self.app.ui.drill.triggered.connect(self.exc_add_drill)
        self.app.ui.drill_array.triggered.connect(self.exc_add_drill_array)

    def disconnect_canvas_event_handlers(self):
        # we restore the key and mouse control to FlatCAMApp method
        # first connect to new, then disconnect the old handlers
        # don't ask why but if there is nothing connected I've seen issues
        self.app.mp = self.app.plotcanvas.graph_event_connect('mouse_press', self.app.on_mouse_click_over_plot)
        self.app.mm = self.app.plotcanvas.graph_event_connect('mouse_move', self.app.on_mouse_move_over_plot)
        self.app.mr = self.app.plotcanvas.graph_event_connect('mouse_release',
                                                              self.app.on_mouse_click_release_over_plot)
        self.app.mdc = self.app.plotcanvas.graph_event_connect('mouse_double_click',
                                                               self.app.on_mouse_double_click_over_plot)
        self.app.collection.view.clicked.connect(self.app.collection.on_mouse_down)

        if self.app.is_legacy is False:
            self.canvas.graph_event_disconnect('mouse_press', self.on_canvas_click)
            self.canvas.graph_event_disconnect('mouse_move', self.on_canvas_move)
            self.canvas.graph_event_disconnect('mouse_release', self.on_exc_click_release)
        else:
            self.canvas.graph_event_disconnect(self.mp)
            self.canvas.graph_event_disconnect(self.mm)
            self.canvas.graph_event_disconnect(self.mr)

        try:
            self.app.ui.popmenu_copy.triggered.disconnect(self.exc_copy_drills)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.popmenu_delete.triggered.disconnect(self.on_delete_btn)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.popmenu_move.triggered.disconnect(self.exc_move_drills)
        except (TypeError, AttributeError):
            pass

        self.app.ui.popmenu_copy.triggered.connect(self.app.on_copy_command)
        self.app.ui.popmenu_delete.triggered.connect(self.app.on_delete)
        self.app.ui.popmenu_move.triggered.connect(self.app.obj_move)

        # Excellon Editor
        try:
            self.app.ui.drill.triggered.disconnect(self.exc_add_drill)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.ui.drill_array.triggered.disconnect(self.exc_add_drill_array)
        except (TypeError, AttributeError):
            pass

        try:
            self.app.jump_signal.disconnect()
        except (TypeError, AttributeError):
            pass

    def clear(self):
        self.active_tool = None
        # self.shape_buffer = []
        self.selected = []

        self.points_edit = {}
        self.new_tools = {}
        self.new_drills = []

        # self.storage_dict = {}

        self.shapes.clear(update=True)
        self.tool_shape.clear(update=True)

        # self.storage = FlatCAMExcEditor.make_storage()
        self.replot()

    def edit_fcexcellon(self, exc_obj):
        """
        Imports the geometry from the given FlatCAM Excellon object
        into the editor.

        :param exc_obj: ExcellonObject object
        :return: None
        """

        assert isinstance(exc_obj, Excellon), \
            "Expected an Excellon Object, got %s" % type(exc_obj)

        self.deactivate()
        self.activate()

        # Hide original geometry
        self.exc_obj = exc_obj
        exc_obj.visible = False

        self.points_edit = {}
        self.slot_points_edit = {}

        # Set selection tolerance
        # DrawToolShape.tolerance = fc_excellon.drawing_tolerance * 10

        self.select_tool("drill_select")

        # reset the tool table
        self.tools_table_exc.clear()
        self.tools_table_exc.setHorizontalHeaderLabels(['#', _('Diameter'), 'D', 'S'])
        self.last_tool_selected = None

        self.set_ui()

        # now that we hava data, create the GUI interface and add it to the Tool Tab
        self.build_ui(first_run=True)

        # we activate this after the initial build as we don't need to see the tool been populated
        self.tools_table_exc.itemChanged.connect(self.on_tool_edit)

        # build the geometry for each tool-diameter, each drill will be represented by a '+' symbol
        # and then add it to the storage elements (each storage elements is a member of a list
        for tool_dia in self.points_edit:
            storage_elem = FlatCAMGeoEditor.make_storage()
            for point in self.points_edit[tool_dia]:
                # make a '+' sign, the line length is the tool diameter
                start_hor_line = ((point.x - (tool_dia / 2)), point.y)
                stop_hor_line = ((point.x + (tool_dia / 2)), point.y)
                start_vert_line = (point.x, (point.y - (tool_dia / 2)))
                stop_vert_line = (point.x, (point.y + (tool_dia / 2)))
                shape_geo = MultiLineString([(start_hor_line, stop_hor_line), (start_vert_line, stop_vert_line)])
                if shape_geo is not None:
                    self.add_exc_shape(DrawToolShape(shape_geo), storage_elem)
            self.storage_dict[tool_dia] = storage_elem

        # slots
        for tool_dia in self.slot_points_edit:
            buf_value = float(tool_dia) / 2
            for elem_dict in self.slot_points_edit[tool_dia]:

                line_geo = LineString([elem_dict['start'], elem_dict['stop']])
                shape_geo = line_geo.buffer(buf_value)

                if tool_dia not in self.storage_dict:
                    storage_elem = FlatCAMGeoEditor.make_storage()
                    self.storage_dict[tool_dia] = storage_elem

                if shape_geo is not None:
                    self.add_exc_shape(DrawToolShape(shape_geo), self.storage_dict[tool_dia])

        self.replot()

        # add a first tool in the Tool Table but only if the Excellon Object is empty
        if not self.tool2tooldia:
            self.on_tool_add(tooldia=float('%.*f' % (self.decimals,
                                                     float(self.app.defaults['excellon_editor_newdia']))))

    def update_fcexcellon(self, exc_obj):
        """
        Create a new Excellon object that contain the edited content of the source Excellon object

        :param exc_obj: ExcellonObject
        :return: None
        """

        # this dictionary will contain tooldia's as keys and a list of coordinates tuple as values
        # the values of this dict are coordinates of the holes (drills)
        edited_points = {}

        """
         - this dictionary will contain tooldia's as keys and a list of another dicts as values
         - the dict element of the list has the structure
         ================  ====================================
        Key               Value
        ================  ====================================
        start             (Shapely.Point) Start point of the slot
        stop              (Shapely.Point) Stop point of the slot
        ================  ====================================
        """
        edited_slot_points = {}

        for storage_tooldia in self.storage_dict:
            for x in self.storage_dict[storage_tooldia].get_objects():
                if isinstance(x.geo, MultiLineString):
                    # all x.geo in self.storage_dict[storage] are MultiLinestring objects for drills
                    # each MultiLineString is made out of Linestrings
                    # select first Linestring object in the current MultiLineString
                    first_linestring = x.geo[0]
                    # get it's coordinates
                    first_linestring_coords = first_linestring.coords
                    x_coord = first_linestring_coords[0][0] + (float(first_linestring.length / 2))
                    y_coord = first_linestring_coords[0][1]

                    # create a tuple with the coordinates (x, y) and add it to the list that is the value of the
                    # edited_points dictionary
                    point = (x_coord, y_coord)
                    if storage_tooldia not in edited_points:
                        edited_points[storage_tooldia] = [point]
                    else:
                        edited_points[storage_tooldia].append(point)
                elif isinstance(x.geo, Polygon):
                    # create a tuple with the points (start, stop) and add it to the list that is the value of the
                    # edited_points dictionary

                    # first determine the start and stop coordinates for the slot knowing the geometry and the tool
                    # diameter
                    radius = float(storage_tooldia) / 2
                    radius = radius - 0.0000001

                    poly = x.geo
                    poly = poly.buffer(-radius)

                    xmin, ymin, xmax, ymax = poly.bounds
                    line_one = LineString([(xmin, ymin), (xmax, ymax)]).intersection(poly).length
                    line_two = LineString([(xmin, ymax), (xmax, ymin)]).intersection(poly).length

                    if line_one < line_two:
                        point_elem = {
                            "start": (xmin, ymax),
                            "stop": (xmax, ymin)
                        }
                    else:
                        point_elem = {
                            "start": (xmin, ymin),
                            "stop": (xmax, ymax)
                        }

                    if storage_tooldia not in edited_slot_points:
                        edited_slot_points[storage_tooldia] = [point_elem]
                    else:
                        edited_slot_points[storage_tooldia].append(point_elem)

        # recreate the drills and tools to be added to the new Excellon edited object
        # first, we look in the tool table if one of the tool diameters was changed then
        # append that a tuple formed by (old_dia, edited_dia) to a list
        changed_key = set()
        for initial_dia in self.olddia_newdia:
            edited_dia = self.olddia_newdia[initial_dia]
            if edited_dia != initial_dia:
                # for drills
                for old_dia in edited_points:
                    if old_dia == initial_dia:
                        changed_key.add((old_dia, edited_dia))
                # for slots
                for old_dia in edited_slot_points:
                    if old_dia == initial_dia:
                        changed_key.add((old_dia, edited_dia))
            # if the initial_dia is not in edited_points it means it is a new tool with no drill points
            # (and we have to add it)
            # because in case we have drill points it will have to be already added in edited_points
            # if initial_dia not in edited_points.keys():
            #     edited_points[initial_dia] = []

        for el in changed_key:
            edited_points[el[1]] = edited_points.pop(el[0])
            edited_slot_points[el[1]] = edited_slot_points.pop(el[0])

        # Let's sort the edited_points dictionary by keys (diameters) and store the result in a zipped list
        # ordered_edited_points is a ordered list of tuples;
        # element[0] of the tuple is the diameter and
        # element[1] of the tuple is a list of coordinates (a tuple themselves)
        ordered_edited_points = sorted(zip(edited_points.keys(), edited_points.values()))

        current_tool = 0
        for tool_dia in ordered_edited_points:
            current_tool += 1

            # create the self.tools for the new Excellon object (the one with edited content)
            name = str(current_tool)
            spec = {"C": float(tool_dia[0])}
            self.new_tools[name] = spec

            # add in self.tools the 'solid_geometry' key, the value (a list) is populated below
            self.new_tools[name]['solid_geometry'] = []

            # create the self.drills for the new Excellon object (the one with edited content)
            for point in tool_dia[1]:
                self.new_drills.append(
                    {
                        'point': Point(point),
                        'tool': str(current_tool)
                    }
                )
                # repopulate the 'solid_geometry' for each tool
                poly = Point(point).buffer(float(tool_dia[0]) / 2.0, int(int(exc_obj.geo_steps_per_circle) / 4))
                self.new_tools[name]['solid_geometry'].append(poly)

        ordered_edited_slot_points = sorted(zip(edited_slot_points.keys(), edited_slot_points.values()))
        for tool_dia in ordered_edited_slot_points:

            tool_exist_flag = False
            for tool in self.new_tools:
                if tool_dia[0] == self.new_tools[tool]["C"]:
                    current_tool = tool
                    tool_exist_flag = True
                    break

            if tool_exist_flag is False:
                current_tool += 1
                # create the self.tools for the new Excellon object (the one with edited content)
                name = str(current_tool)
                spec = {"C": float(tool_dia[0])}
                self.new_tools[name] = spec

                # add in self.tools the 'solid_geometry' key, the value (a list) is populated below
                self.new_tools[name]['solid_geometry'] = []

            # create the self.slots for the new Excellon object (the one with edited content)
            for coord_dict in tool_dia[1]:
                self.new_slots.append(
                    {
                        'start': Point(coord_dict['start']),
                        'stop': Point(coord_dict['stop']),
                        'tool': str(current_tool)
                    }
                )
                # repopulate the 'solid_geometry' for each tool
                poly = LineString([coord_dict['start'], coord_dict['stop']]).buffer(
                    float(tool_dia[0]) / 2.0, int(int(exc_obj.geo_steps_per_circle) / 4)
                )
                self.new_tools[str(current_tool)]['solid_geometry'].append(poly)

        if self.is_modified is True:
            if "_edit" in self.edited_obj_name:
                try:
                    idd = int(self.edited_obj_name[-1]) + 1
                    self.edited_obj_name = self.edited_obj_name[:-1] + str(idd)
                except ValueError:
                    self.edited_obj_name += "_1"
            else:
                self.edited_obj_name += "_edit"

        self.app.worker_task.emit({'fcn': self.new_edited_excellon,
                                   'params': [self.edited_obj_name,
                                              self.new_drills,
                                              self.new_slots,
                                              self.new_tools]})

        return self.edited_obj_name

    @staticmethod
    def update_options(obj):
        try:
            if not obj.options:
                obj.options = {}
                obj.options['xmin'] = 0
                obj.options['ymin'] = 0
                obj.options['xmax'] = 0
                obj.options['ymax'] = 0
                return True
            else:
                return False
        except AttributeError:
            obj.options = {}
            return True

    def new_edited_excellon(self, outname, n_drills, n_slots, n_tools):
        """
        Creates a new Excellon object for the edited Excellon. Thread-safe.

        :param outname:     Name of the resulting object. None causes the
                            name to be that of the file.
        :type outname:      str

        :param n_drills:    The new Drills storage
        :param n_slots:     The new Slots storage
        :param n_tools:     The new Tools storage
        :return:            None
        """

        self.app.log.debug("Update the Excellon object with edited content. Source is %s" %
                           self.exc_obj.options['name'])

        new_drills = n_drills
        new_slots = n_slots
        new_tools = n_tools

        # How the object should be initialized
        def obj_init(excellon_obj, app_obj):

            excellon_obj.drills = deepcopy(new_drills)
            excellon_obj.tools = deepcopy(new_tools)
            excellon_obj.slots = deepcopy(new_slots)

            excellon_obj.options['name'] = outname

            # add a 'data' dict for each tool with the default values
            for tool in excellon_obj.tools:
                excellon_obj.tools[tool]['data'] = {}
                excellon_obj.tools[tool]['data'].update(deepcopy(self.data_defaults))

            try:
                excellon_obj.create_geometry()
            except KeyError:
                self.app.inform.emit('[ERROR_NOTCL] %s' %
                                     _("There are no Tools definitions in the file. Aborting Excellon creation.")
                                     )
            except Exception:
                msg = '[ERROR] %s' % \
                      _("An internal error has ocurred. See Shell.\n")
                msg += traceback.format_exc()
                app_obj.inform.emit(msg)
                return

        with self.app.proc_container.new(_("Creating Excellon.")):

            try:
                edited_obj = self.app.new_object("excellon", outname, obj_init)
                edited_obj.source_file = self.app.export_excellon(obj_name=edited_obj.options['name'],
                                                                  local_use=edited_obj,
                                                                  filename=None,
                                                                  use_thread=False)
            except Exception as e:
                log.error("Error on Edited object creation: %s" % str(e))
                return

            self.app.inform.emit('[success] %s' % _("Excellon editing finished."))

    def on_tool_select(self, tool):
        """
        Behavior of the toolbar. Tool initialization.

        :rtype : None
        """
        current_tool = tool

        self.app.log.debug("on_tool_select('%s')" % tool)

        if self.last_tool_selected is None and current_tool != 'drill_select':
            # self.draw_app.select_tool('drill_select')
            self.complete = True
            current_tool = 'drill_select'
            self.app.inform.emit('[WARNING_NOTCL] %s' %
                                 _("Cancelled. There is no Tool/Drill selected"))

        # This is to make the group behave as radio group
        if current_tool in self.tools_exc:
            if self.tools_exc[current_tool]["button"].isChecked():
                self.app.log.debug("%s is checked." % current_tool)
                for t in self.tools_exc:
                    if t != current_tool:
                        self.tools_exc[t]["button"].setChecked(False)

                # this is where the Editor toolbar classes (button's) are instantiated
                self.active_tool = self.tools_exc[current_tool]["constructor"](self)
                # self.app.inform.emit(self.active_tool.start_msg)
            else:
                self.app.log.debug("%s is NOT checked." % current_tool)
                for t in self.tools_exc:
                    self.tools_exc[t]["button"].setChecked(False)

                self.select_tool('drill_select')
                self.active_tool = FCDrillSelect(self)

    def on_row_selected(self, row, col):
        if col == 0:
            key_modifier = QtWidgets.QApplication.keyboardModifiers()
            if self.app.defaults["global_mselect_key"] == 'Control':
                modifier_to_use = Qt.ControlModifier
            else:
                modifier_to_use = Qt.ShiftModifier

            if key_modifier == modifier_to_use:
                pass
            else:
                self.selected = []

            try:
                selected_dia = self.tool2tooldia[self.tools_table_exc.currentRow() + 1]
                self.last_tool_selected = int(self.tools_table_exc.currentRow()) + 1
                for obj in self.storage_dict[selected_dia].get_objects():
                    self.selected.append(obj)
            except Exception as e:
                self.app.log.debug(str(e))

            self.replot()

    # def toolbar_tool_toggle(self, key):
    #     self.options[key] = self.sender().isChecked()
    #     if self.options[key] is True:
    #         return 1
    #     else:
    #         return 0

    def on_canvas_click(self, event):
        """
        event.x and .y have canvas coordinates
        event.xdata and .ydata have plot coordinates

        :param event: Event object dispatched by VisPy
        :return: None
        """
        if self.app.is_legacy is False:
            event_pos = event.pos
            # event_is_dragging = event.is_dragging
            # right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # event_is_dragging = self.app.plotcanvas.is_dragging
            # right_button = 3

        self.pos = self.canvas.translate_coords(event_pos)

        if self.app.grid_status():
            self.pos = self.app.geo_editor.snap(self.pos[0], self.pos[1])
        else:
            self.pos = (self.pos[0], self.pos[1])

        if event.button == 1:
            self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
                                                   "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (0, 0))

            # Selection with left mouse button
            if self.active_tool is not None and event.button == 1:
                # Dispatch event to active_tool
                # msg = self.active_tool.click(self.app.geo_editor.snap(event.xdata, event.ydata))
                self.active_tool.click(self.app.geo_editor.snap(self.pos[0], self.pos[1]))

                # If it is a shape generating tool
                if isinstance(self.active_tool, FCShapeTool) and self.active_tool.complete:
                    if self.current_storage is not None:
                        self.on_exc_shape_complete(self.current_storage)
                        self.build_ui()

                    # MS: always return to the Select Tool if modifier key is not pressed
                    # else return to the current tool
                    key_modifier = QtWidgets.QApplication.keyboardModifiers()
                    if self.app.defaults["global_mselect_key"] == 'Control':
                        modifier_to_use = Qt.ControlModifier
                    else:
                        modifier_to_use = Qt.ShiftModifier

                    # if modifier key is pressed then we add to the selected list the current shape but if it's already
                    # in the selected list, we removed it. Therefore first click selects, second deselects.
                    if key_modifier == modifier_to_use:
                        self.select_tool(self.active_tool.name)
                    else:
                        # return to Select tool but not for FCDrillAdd or FCSlot
                        if isinstance(self.active_tool, FCDrillAdd) or isinstance(self.active_tool, FCSlot):
                            self.select_tool(self.active_tool.name)
                        else:
                            self.select_tool("drill_select")
                        return

                if isinstance(self.active_tool, FCDrillSelect):
                    # self.app.log.debug("Replotting after click.")
                    self.replot()
            else:
                self.app.log.debug("No active tool to respond to click!")

    def on_exc_shape_complete(self, storage):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        if type(storage) is list:
            for item_storage in storage:
                self.add_exc_shape(self.active_tool.geometry, item_storage)
        else:
            self.add_exc_shape(self.active_tool.geometry, storage)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def add_exc_shape(self, shape, storage):
        """
        Adds a shape to a specified shape storage.

        :param shape: Shape to be added.
        :type shape: DrawToolShape
        :param storage: object where to store the shapes
        :return: None
        """
        # List of DrawToolShape?
        if isinstance(shape, list):
            for subshape in shape:
                self.add_exc_shape(subshape, storage)
            return

        assert isinstance(shape, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % str(type(shape))

        assert shape.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shape.geo, list) and len(shape.geo) > 0) or not isinstance(shape.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shape, DrawToolUtilityShape):
            self.utility.append(shape)
        else:
            storage.insert(shape)  # TODO: Check performance

    def add_shape(self, shape):
        """
        Adds a shape to the shape storage.

        :param shape: Shape to be added.
        :type shape: DrawToolShape
        :return: None
        """

        # List of DrawToolShape?
        if isinstance(shape, list):
            for subshape in shape:
                self.add_shape(subshape)
            return

        assert isinstance(shape, DrawToolShape), \
            "Expected a DrawToolShape, got %s" % type(shape)

        assert shape.geo is not None, \
            "Shape object has empty geometry (None)"

        assert (isinstance(shape.geo, list) and len(shape.geo) > 0) or not isinstance(shape.geo, list), \
            "Shape objects has empty geometry ([])"

        if isinstance(shape, DrawToolUtilityShape):
            self.utility.append(shape)
        # else:
        #     self.storage.insert(shape)

    def on_exc_click_release(self, event):
        """
        Handler of the "mouse_release" event.
        It will pop-up the context menu on right mouse click unless there was a panning move (decided in the
        "mouse_move" event handler) and only if the current tool is the Select tool.
        It will 'close' a Editor tool if it is the case.

        :param event: Event object dispatched by VisPy SceneCavas
        :return: None
        """

        if self.app.is_legacy is False:
            event_pos = event.pos
            # event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            # event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        pos_canvas = self.canvas.translate_coords(event_pos)

        if self.app.grid_status():
            pos = self.app.geo_editor.snap(pos_canvas[0], pos_canvas[1])
        else:
            pos = (pos_canvas[0], pos_canvas[1])

        # if the released mouse button was RMB then test if it was a panning motion or not, if not it was a context
        # canvas menu
        try:
            if event.button == right_button:  # right click
                if self.app.ui.popMenu.mouse_is_panning is False:
                    try:
                        QtGui.QGuiApplication.restoreOverrideCursor()
                    except Exception:
                        pass
                    if self.active_tool.complete is False and not isinstance(self.active_tool, FCDrillSelect):
                        self.active_tool.complete = True
                        self.in_action = False
                        self.delete_utility_geometry()
                        self.app.inform.emit('[success] %s' %
                                             _("Done."))
                        self.select_tool('drill_select')
                    else:
                        if isinstance(self.active_tool, FCDrillAdd):
                            self.active_tool.complete = True
                            self.in_action = False
                            self.delete_utility_geometry()
                            self.app.inform.emit('[success] %s' %
                                                 _("Done."))
                            self.select_tool('drill_select')

                        self.app.cursor = QtGui.QCursor()
                        self.app.populate_cmenu_grids()
                        self.app.ui.popMenu.popup(self.app.cursor.pos())

        except Exception as e:
            log.warning("FlatCAMExcEditor.on_exc_click_release() RMB click --> Error: %s" % str(e))
            raise

        # if the released mouse button was LMB then test if we had a right-to-left selection or a left-to-right
        # selection and then select a type of selection ("enclosing" or "touching")
        try:
            if event.button == 1:  # left click
                if self.app.selection_type is not None:
                    self.draw_selection_area_handler(self.pos, pos, self.app.selection_type)
                    self.app.selection_type = None

                elif isinstance(self.active_tool, FCDrillSelect):
                    self.active_tool.click_release((self.pos[0], self.pos[1]))

                    # if there are selected objects then plot them
                    if self.selected:
                        self.replot()
        except Exception as e:
            log.warning("FlatCAMExcEditor.on_exc_click_release() LMB click --> Error: %s" % str(e))
            raise

    def draw_selection_area_handler(self, start, end, sel_type):
        """
        This function is called whenever we have a left mouse click release and only we have a left mouse click drag,
        be it from left to right or from right to left. The direction of the drag is decided in the "mouse_move"
        event handler.
        Pressing a modifier key (eg. Ctrl, Shift or Alt) will change the behavior of the selection.

        Depending on which tool belongs the selected shapes, the corresponding rows in the Tools Table are selected or
        deselected.

        :param start: mouse position when the selection LMB click was done
        :param end: mouse position when the left mouse button is released
        :param sel_type: if True it's a left to right selection (enclosure), if False it's a 'touch' selection
        :return:
        """

        start_pos = (start[0], start[1])
        end_pos = (end[0], end[1])
        poly_selection = Polygon([start_pos, (end_pos[0], start_pos[1]), end_pos, (start_pos[0], end_pos[1])])
        modifiers = None

        # delete the selection shape that was just drawn, we no longer need it
        self.app.delete_selection_shape()

        # detect if a modifier key was pressed while the left mouse button was released
        self.modifiers = QtWidgets.QApplication.keyboardModifiers()
        if self.modifiers == QtCore.Qt.ShiftModifier:
            modifiers = 'Shift'
        elif self.modifiers == QtCore.Qt.ControlModifier:
            modifiers = 'Control'

        if modifiers == self.app.defaults["global_mselect_key"]:
            for storage in self.storage_dict:
                for obj in self.storage_dict[storage].get_objects():
                    if (sel_type is True and poly_selection.contains(obj.geo)) or \
                            (sel_type is False and poly_selection.intersects(obj.geo)):

                        if obj in self.selected:
                            # remove the shape object from the selected shapes storage
                            self.selected.remove(obj)
                        else:
                            # add the shape object to the selected shapes storage
                            self.selected.append(obj)
        else:
            # clear the selection shapes storage
            self.selected = []
            # then add to the selection shapes storage the shapes that are included (touched) by the selection rectangle
            for storage in self.storage_dict:
                for obj in self.storage_dict[storage].get_objects():
                    if (sel_type is True and poly_selection.contains(obj.geo)) or \
                            (sel_type is False and poly_selection.intersects(obj.geo)):
                        self.selected.append(obj)

        try:
            self.tools_table_exc.cellPressed.disconnect()
        except Exception:
            pass

        # first deselect all rows (tools) in the Tools Table
        self.tools_table_exc.clearSelection()
        # and select the rows (tools) in the tool table according to the diameter(s) of the selected shape(s)
        self.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        for storage in self.storage_dict:
            for shape_s in self.selected:
                if shape_s in self.storage_dict[storage].get_objects():
                    for key_tool_nr in self.tool2tooldia:
                        if self.tool2tooldia[key_tool_nr] == storage:
                            row_to_sel = key_tool_nr - 1
                            # item = self.tools_table_exc.item(row_to_sel, 1)
                            # self.tools_table_exc.setCurrentItem(item)
                            # item.setSelected(True)

                            # if the row to be selected is not already in the selected rows then select it
                            # otherwise don't do it as it seems that we have a toggle effect
                            if row_to_sel not in set(index.row() for index in self.tools_table_exc.selectedIndexes()):
                                self.tools_table_exc.selectRow(row_to_sel)
                            self.last_tool_selected = int(key_tool_nr)

        self.tools_table_exc.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.tools_table_exc.cellPressed.connect(self.on_row_selected)
        self.replot()

    def on_canvas_move(self, event):
        """
        Called on 'mouse_move' event.
        It updates the mouse cursor if the grid snapping is ON.
        It decide if we have a mouse drag and if it is done with the right mouse click. Then it passes this info to a
        class object which is used in the "mouse_release" handler to decide if to pop-up the context menu or not.
        It draws utility_geometry for the Editor tools.
        Update the position labels from status bar.
        Decide if we have a right to left or a left to right mouse drag with left mouse button and call a function
        that will draw a selection shape on canvas.

        event.pos have canvas screen coordinates

        :param event: Event object dispatched by VisPy SceneCavas
        :return: None
        """

        if self.app.is_legacy is False:
            event_pos = event.pos
            event_is_dragging = event.is_dragging
            right_button = 2
        else:
            event_pos = (event.xdata, event.ydata)
            event_is_dragging = self.app.plotcanvas.is_dragging
            right_button = 3

        pos = self.canvas.translate_coords(event_pos)
        event.xdata, event.ydata = pos[0], pos[1]

        self.x = event.xdata
        self.y = event.ydata

        self.app.ui.popMenu.mouse_is_panning = False

        # if the RMB is clicked and mouse is moving over plot then 'panning_action' is True
        if event.button == right_button and event_is_dragging == 1:
            self.app.ui.popMenu.mouse_is_panning = True
            return

        try:
            x = float(event.xdata)
            y = float(event.ydata)
        except TypeError:
            return

        if self.active_tool is None:
            return

        # ## Snap coordinates
        if self.app.grid_status():
            x, y = self.app.geo_editor.snap(x, y)

            # Update cursor
            self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color=self.app.cursor_color_3D,
                                         edge_width=self.app.defaults["global_cursor_width"],
                                         size=self.app.defaults["global_cursor_size"])

        self.snap_x = x
        self.snap_y = y

        if self.pos is None:
            self.pos = (0, 0)
        self.app.dx = x - self.pos[0]
        self.app.dy = y - self.pos[1]

        # # update the position label in the infobar since the APP mouse event handlers are disconnected
        # self.app.ui.position_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;<b>X</b>: %.4f&nbsp;&nbsp;   "
        #                                    "<b>Y</b>: %.4f" % (x, y))
        # # update the reference position label in the infobar since the APP mouse event handlers are disconnected
        # self.app.ui.rel_position_label.setText("<b>Dx</b>: %.4f&nbsp;&nbsp;  <b>Dy</b>: "
        #                                        "%.4f&nbsp;&nbsp;&nbsp;&nbsp;" % (self.app.dx, self.app.dy))

        units = self.app.defaults["units"].lower()
        self.plotcanvas.text_hud.text = \
            'Dx:\t{:<.4f} [{:s}]\nDy:\t{:<.4f} [{:s}]\nX:  \t{:<.4f} [{:s}]\nY:  \t{:<.4f} [{:s}]'.format(
                self.app.dx, units, self.app.dy, units, x, units, y, units)

        # ## Utility geometry (animated)
        self.update_utility_geometry(data=(x, y))

        # ## Selection area on canvas section # ##
        if event_is_dragging == 1 and event.button == 1:
            # I make an exception for FCDrillAdd and FCDrillArray because clicking and dragging while making regions
            # can create strange issues. Also for FCSlot and FCSlotArray
            if isinstance(self.active_tool, FCDrillAdd) or isinstance(self.active_tool, FCDrillArray) or \
                    isinstance(self.active_tool, FCSlot) or isinstance(self.active_tool, FCSlotArray):
                self.app.selection_type = None
            else:
                dx = pos[0] - self.pos[0]
                self.app.delete_selection_shape()
                if dx < 0:
                    self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x, y),
                                                         color=self.app.defaults["global_alt_sel_line"],
                                                         face_color=self.app.defaults['global_alt_sel_fill'])
                    self.app.selection_type = False
                else:
                    self.app.draw_moving_selection_shape((self.pos[0], self.pos[1]), (x, y))
                    self.app.selection_type = True
        else:
            self.app.selection_type = None

        # Update cursor
        self.app.app_cursor.set_data(np.asarray([(x, y)]), symbol='++', edge_color=self.app.cursor_color_3D,
                                     edge_width=self.app.defaults["global_cursor_width"],
                                     size=self.app.defaults["global_cursor_size"])

    def update_utility_geometry(self, data):
        # ### Utility geometry (animated) ###
        geo = self.active_tool.utility_geometry(data=data)
        if isinstance(geo, DrawToolShape) and geo.geo is not None:
            # Remove any previous utility shape
            self.tool_shape.clear(update=True)
            self.draw_utility_geometry(geo=geo)

    def on_canvas_key_release(self, event):
        self.key = None

    def draw_utility_geometry(self, geo):
        # Add the new utility shape
        try:
            # this case is for the Font Parse
            for el in list(geo.geo):
                if type(el) == MultiPolygon:
                    for poly in el:
                        self.tool_shape.add(
                            shape=poly,
                            color=(self.app.defaults["global_draw_color"] + '80'),
                            update=False,
                            layer=0,
                            tolerance=None
                        )
                elif type(el) == MultiLineString:
                    for linestring in el:
                        self.tool_shape.add(
                            shape=linestring,
                            color=(self.app.defaults["global_draw_color"] + '80'),
                            update=False,
                            layer=0,
                            tolerance=None
                        )
                else:
                    self.tool_shape.add(
                        shape=el,
                        color=(self.app.defaults["global_draw_color"] + '80'),
                        update=False,
                        layer=0,
                        tolerance=None
                    )
        except TypeError:
            self.tool_shape.add(
                shape=geo.geo, color=(self.app.defaults["global_draw_color"] + '80'),
                update=False, layer=0, tolerance=None)
        self.tool_shape.redraw()

    def replot(self):
        self.plot_all()

    def plot_all(self):
        """
        Plots all shapes in the editor.

        :return: None
        :rtype: None
        """
        # self.app.log.debug("plot_all()")
        self.shapes.clear(update=True)

        for storage in self.storage_dict:
            for shape_plus in self.storage_dict[storage].get_objects():
                if shape_plus.geo is None:
                    continue

                if shape_plus in self.selected:
                    self.plot_shape(geometry=shape_plus.geo, color=self.app.defaults['global_sel_draw_color'] + 'FF',
                                    linewidth=2)
                    continue
                self.plot_shape(geometry=shape_plus.geo, color=self.app.defaults['global_draw_color'] + 'FF')

        # for shape in self.storage.get_objects():
        #     if shape.geo is None:  # TODO: This shouldn't have happened
        #         continue
        #
        #     if shape in self.selected:
        #         self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_sel_draw_color'], linewidth=2)
        #         continue
        #
        #     self.plot_shape(geometry=shape.geo, color=self.app.defaults['global_draw_color'])

        for shape_form in self.utility:
            self.plot_shape(geometry=shape_form.geo, linewidth=1)
            continue

        self.shapes.redraw()

    def plot_shape(self, geometry=None, color='0x000000FF', linewidth=1):
        """
        Plots a geometric object or list of objects without rendering. Plotted objects
        are returned as a list. This allows for efficient/animated rendering.

        :param geometry: Geometry to be plotted (Any Shapely.geom kind or list of such)
        :param color: Shape color
        :param linewidth: Width of lines in # of pixels.
        :return: List of plotted elements.
        """
        plot_elements = []

        if geometry is None:
            geometry = self.active_tool.geometry

        try:
            for geo in geometry:
                plot_elements += self.plot_shape(geometry=geo, color=color, linewidth=linewidth)

        # ## Non-iterable
        except TypeError:
            # ## DrawToolShape
            if isinstance(geometry, DrawToolShape):
                plot_elements += self.plot_shape(geometry=geometry.geo, color=color, linewidth=linewidth)

            # ## Polygon: Descend into exterior and each interior.
            if type(geometry) == Polygon:
                plot_elements += self.plot_shape(geometry=geometry.exterior, color=color, linewidth=linewidth)
                plot_elements += self.plot_shape(geometry=geometry.interiors, color=color, linewidth=linewidth)

            if type(geometry) == LineString or type(geometry) == LinearRing:
                plot_elements.append(self.shapes.add(shape=geometry, color=color, layer=0, tolerance=self.tolerance))

            if type(geometry) == Point:
                pass

        return plot_elements

    def on_shape_complete(self):
        self.app.log.debug("on_shape_complete()")

        # Add shape
        self.add_shape(self.active_tool.geometry)

        # Remove any utility shapes
        self.delete_utility_geometry()
        self.tool_shape.clear(update=True)

        # Replot and reset tool.
        self.replot()
        # self.active_tool = type(self.active_tool)(self)

    def get_selected(self):
        """
        Returns list of shapes that are selected in the editor.

        :return: List of shapes.
        """
        # return [shape for shape in self.shape_buffer if shape["selected"]]
        return self.selected

    def delete_selected(self):
        temp_ref = [s for s in self.selected]
        for shape_sel in temp_ref:
            self.delete_shape(shape_sel)

        self.selected = []
        self.build_ui()
        self.app.inform.emit('[success] %s' %
                             _("Done. Drill(s) deleted."))

    def delete_shape(self, del_shape):
        self.is_modified = True

        if del_shape in self.utility:
            self.utility.remove(del_shape)
            return

        for storage in self.storage_dict:
            # try:
            #     self.storage_dict[storage].remove(shape)
            # except:
            #     pass
            if del_shape in self.storage_dict[storage].get_objects():
                if isinstance(del_shape.geo, MultiLineString):
                    self.storage_dict[storage].remove(del_shape)
                    # a hack to make the tool_table display less drills per diameter
                    # self.points_edit it's only useful first time when we load the data into the storage
                    # but is still used as referecen when building tool_table in self.build_ui()
                    # the number of drills displayed in column 2 is just a len(self.points_edit) therefore
                    # deleting self.points_edit elements (doesn't matter who but just the number)
                    # solved the display issue.
                    del self.points_edit[storage][0]
                else:
                    self.storage_dict[storage].remove(del_shape)
                    del self.slot_points_edit[storage][0]

        if del_shape in self.selected:
            self.selected.remove(del_shape)

    def delete_utility_geometry(self):
        for_deletion = [util_shape for util_shape in self.utility]
        for util_shape in for_deletion:
            self.delete_shape(util_shape)

        self.tool_shape.clear(update=True)
        self.tool_shape.redraw()

    def on_delete_btn(self):
        self.delete_selected()
        self.replot()

    def select_tool(self, toolname):
        """
        Selects a drawing tool. Impacts the object and GUI.

        :param toolname: Name of the tool.
        :return: None
        """
        self.tools_exc[toolname]["button"].setChecked(True)
        self.on_tool_select(toolname)

    def set_selected(self, sel_shape):

        # Remove and add to the end.
        if sel_shape in self.selected:
            self.selected.remove(sel_shape)

        self.selected.append(sel_shape)

    def set_unselected(self, unsel_shape):
        if unsel_shape in self.selected:
            self.selected.remove(unsel_shape)

    def on_array_type_combo(self):
        if self.array_type_combo.currentIndex() == 0:
            self.array_circular_frame.hide()
            self.array_linear_frame.show()
        else:
            self.delete_utility_geometry()
            self.array_circular_frame.show()
            self.array_linear_frame.hide()
            self.app.inform.emit(_("Click on the circular array Center position"))

    def on_slot_array_type_combo(self):
        if self.slot_array_type_combo.currentIndex() == 0:
            self.slot_array_circular_frame.hide()
            self.slot_array_linear_frame.show()
        else:
            self.delete_utility_geometry()
            self.slot_array_circular_frame.show()
            self.slot_array_linear_frame.hide()
            self.app.inform.emit(_("Click on the circular array Center position"))

    def on_linear_angle_radio(self):
        val = self.drill_axis_radio.get_value()
        if val == 'A':
            self.linear_angle_spinner.show()
            self.linear_angle_label.show()
        else:
            self.linear_angle_spinner.hide()
            self.linear_angle_label.hide()

    def on_slot_array_linear_angle_radio(self):
        val = self.slot_array_axis_radio.get_value()
        if val == 'A':
            self.slot_array_linear_angle_spinner.show()
            self.slot_array_linear_angle_label.show()
        else:
            self.slot_array_linear_angle_spinner.hide()
            self.slot_array_linear_angle_label.hide()

    def on_slot_angle_radio(self):
        val = self.slot_axis_radio.get_value()
        if val == 'A':
            self.slot_angle_spinner.show()
            self.slot_angle_label.show()
        else:
            self.slot_angle_spinner.hide()
            self.slot_angle_label.hide()

    def exc_add_drill(self):
        self.select_tool('drill_add')
        return

    def exc_add_drill_array(self):
        self.select_tool('drill_array')
        return

    def exc_add_slot(self):
        self.select_tool('slot_add')
        return

    def exc_add_slot_array(self):
        self.select_tool('slot_array')
        return

    def exc_resize_drills(self):
        self.select_tool('drill_resize')
        return

    def exc_copy_drills(self):
        self.select_tool('drill_copy')
        return

    def exc_move_drills(self):
        self.select_tool('drill_move')
        return


def get_shapely_list_bounds(geometry_list):
    xmin = np.Inf
    ymin = np.Inf
    xmax = -np.Inf
    ymax = -np.Inf

    for gs in geometry_list:
        try:
            gxmin, gymin, gxmax, gymax = gs.bounds
            xmin = min([xmin, gxmin])
            ymin = min([ymin, gymin])
            xmax = max([xmax, gxmax])
            ymax = max([ymax, gymax])
        except Exception as e:
            log.warning("DEVELOPMENT: Tried to get bounds of empty geometry. --> %s" % str(e))

    return [xmin, ymin, xmax, ymax]

# EOF
