from tclCommands.TclCommand import TclCommand

import collections
import logging

import gettext
import FlatCAMTranslation as fcTranslate
import builtins

fcTranslate.apply_language('strings')
if '_' not in builtins.__dict__:
    _ = gettext.gettext

log = logging.getLogger('base')


class TclCommandPaint(TclCommand):
    """
    Paint the interior of polygons
    """

    # Array of all command aliases, to be able use old names for backward compatibility (add_poly, add_polygon)
    aliases = ['paint']

    description = '%s %s' % ("--", "Paint polygons in the specified object by covering them with toolpaths.")

    # dictionary of types from Tcl command, needs to be ordered
    arg_names = collections.OrderedDict([
        ('name', str),
    ])

    # dictionary of types from Tcl command, needs to be ordered , this  is  for options  like -optionname value
    option_types = collections.OrderedDict([
        ('tooldia', str),
        ('overlap', float),
        ('order', str),
        ('margin', float),
        ('method', str),
        ('connect', str),
        ('contour', str),

        ('all', str),
        ('single', str),
        ('ref', str),
        ('box', str),
        ('x', float),
        ('y', float),
        ('outname', str),
    ])

    # array of mandatory options for current Tcl command: required = {'name','outname'}
    required = ['name']

    # structured help for current command, args needs to be ordered
    help = {
        'main': "Paint polygons in the specified object by covering them with toolpaths.",
        'args': collections.OrderedDict([
            ('name', 'Name of the source Geometry object. String.'),
            ('tooldia', 'Diameter of the tool to be used. Can be a comma separated list of diameters. No space is '
                        'allowed between tool diameters. E.g: correct: 0.5,1 / incorrect: 0.5, 1'),
            ('overlap', 'Percentage of tool diameter to overlap current pass over previous pass. Float [0, 99.9999]\n'
                        'E.g: for a 25% from tool diameter overlap use -overlap 25'),
            ('margin', 'Bounding box margin. Float number.'),
            ('order', 'Can have the values: "no", "fwd" and "rev". String.'
                      'It is useful when there are multiple tools in tooldia parameter.'
                      '"no" -> the order used is the one provided.'
                      '"fwd" -> tools are ordered from smallest to biggest.'
                      '"rev" -> tools are ordered from biggest to smallest.'),
            ('method', 'Algorithm for painting. Can be: "standard", "seed", "lines", "laser_lines", "combo".'),
            ('connect', 'Draw lines to minimize tool lifts. True (1) or False (0)'),
            ('contour', 'Cut around the perimeter of the painting. True (1) or False (0)'),
            ('all', 'If used, paint all polygons in the object.'),
            ('box', 'name of the object to be used as paint reference. String.'),
            ('single', 'Paint a single polygon specified by "x" and "y" parameters. True (1) or False (0)'),
            ('x', 'X value of coordinate for the selection of a single polygon. Float number.'),
            ('y', 'Y value of coordinate for the selection of a single polygon. Float number.'),
            ('outname', 'Name of the resulting Geometry object. String.'),
        ]),
        'examples': ["paint obj_name -tooldia 0.3 -margin 0.1 -method 'seed' -all"]
    }

    def execute(self, args, unnamed_args):
        """
        execute current TCL shell command

        :param args: array of known named arguments and options
        :param unnamed_args: array of other values which were passed into command
            without -somename and  we do not have them in known arg_names
        :return: None or exception
        """

        name = args['name']

        # Get source object.
        try:
            obj = self.app.collection.get_by_name(str(name))
        except Exception as e:
            log.debug("TclCommandPaint.execute() --> %s" % str(e))
            self.raise_tcl_error("%s: %s" % (_("Could not retrieve object"), name))
            return "Could not retrieve object: %s" % name

        if 'tooldia' in args:
            tooldia = str(args['tooldia'])
        else:
            tooldia = float(self.app.defaults["tools_paintoverlap"])

        if 'overlap' in args:
            overlap = float(args['overlap']) / 100.0
        else:
            overlap = float(self.app.defaults["tools_paintoverlap"]) / 100.0

        if 'order' in args:
            order = args['order']
        else:
            order = str(self.app.defaults["tools_paintorder"])

        if 'margin' in args:
            margin = float(args['margin'])
        else:
            margin = float(self.app.defaults["tools_paintmargin"])

        if 'method' in args:
            method = args['method']
            if method == "standard":
                method = _("Standard")
            elif method == "seed":
                method = _("Seed")
            elif method == "lines":
                method = _("Lines")
            elif method == "laser_lines":
                method = _("Laser_lines")
            else:
                method = _("Combo")
        else:
            method = str(self.app.defaults["tools_paintmethod"])

        if 'connect' in args:
            try:
                par = args['connect'].capitalize()
            except AttributeError:
                par = args['connect']
            connect = bool(eval(par))
        else:
            connect = bool(eval(str(self.app.defaults["tools_pathconnect"])))

        if 'contour' in args:
            try:
                par = args['contour'].capitalize()
            except AttributeError:
                par = args['contour']
            contour = bool(eval(par))
        else:
            contour = bool(eval(str(self.app.defaults["tools_paintcontour"])))

        if 'outname' in args:
            outname = args['outname']
        else:
            outname = name + "_paint"

        # used only to have correct information's in the obj.tools[tool]['data'] dict
        if "all" in args:
            select = _("All Polygons")
        elif "single" in args:
            select = _("Polygon Selection")
        else:
            select = _("Reference Object")

        try:
            tools = [float(eval(dia)) for dia in tooldia.split(",") if dia != '']
        except AttributeError:
            tools = [float(tooldia)]
        # store here the default data for Geometry Data
        default_data = {}
        default_data.update({
            "name": outname,
            "plot": False,
            "cutz": self.app.defaults["geometry_cutz"],
            "vtipdia": 0.1,
            "vtipangle": 30,
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

            "tooldia": self.app.defaults["tools_painttooldia"],
            "paintmargin": margin,
            "paintmethod": method,
            "selectmethod": select,
            "pathconnect": connect,
            "paintcontour": contour,
            "paintoverlap": overlap
        })
        paint_tools = {}

        tooluid = 0
        for tool in tools:
            tooluid += 1
            paint_tools.update({
                int(tooluid): {
                    'tooldia': float('%.*f' % (obj.decimals, tool)),
                    'offset': 'Path',
                    'offset_value': 0.0,
                    'type': 'Iso',
                    'tool_type': 'C1',
                    'data': dict(default_data),
                    'solid_geometry': []
                }
            })
            paint_tools[int(tooluid)]['data']['tooldia'] = float('%.*f' % (obj.decimals, tool))

        if obj is None:
            return "Object not found: %s" % name

        # Paint all polygons in the painted object
        if 'all' in args:
            self.app.paint_tool.paint_poly_all(obj=obj,
                                               tooldia=tooldia,
                                               order=order,
                                               method=method,
                                               outname=outname,
                                               tools_storage=paint_tools,
                                               plot=False,
                                               run_threaded=False)
            return

        # Paint single polygon in the painted object
        if 'single' in args:
            if 'x' not in args and 'y' not in args:
                self.raise_tcl_error('%s' % _("Expected -x <value> and -y <value>."))
            else:
                x = args['x']
                y = args['y']

                self.app.paint_tool.paint_poly(obj=obj,
                                               inside_pt=[x, y],
                                               tooldia=tooldia,
                                               order=order,
                                               method=method,
                                               outname=outname,
                                               tools_storage=paint_tools,
                                               plot=False,
                                               run_threaded=False)
            return

        # Paint all polygons found within the box object from the the painted object
        if 'box' in args:
            box_name = args['box']

            if box_name is None:
                self.raise_tcl_error('%s' % _("Expected -box <value>."))

            # Get box source object.
            try:
                box_obj = self.app.collection.get_by_name(str(box_name))
            except Exception as e:
                log.debug("TclCommandPaint.execute() --> %s" % str(e))
                self.raise_tcl_error("%s: %s" % (_("Could not retrieve box object"), name))
                return "Could not retrieve object: %s" % name

            self.app.paint_tool.paint_poly_ref(obj=obj,
                                               sel_obj=box_obj,
                                               tooldia=tooldia,
                                               order=order,
                                               method=method,
                                               outname=outname,
                                               tools_storage=paint_tools,
                                               plot=False,
                                               run_threaded=False)
            return

        self.raise_tcl_error("%s:" % _("None of the following args: 'box', 'single', 'all' were used.\n"
                                       "Paint failed."))
        return "None of the following args: 'box', 'single', 'all' were used. Paint failed."
