from tclCommands.TclCommand import TclCommandSignaled

import collections
from copy import deepcopy


class TclCommandCncjob(TclCommandSignaled):
    """
    Tcl shell command to Generates a CNC Job from a Geometry Object.

    example:
        set_sys units MM
        new
        open_gerber tests/gerber_files/simple1.gbr -outname margin
        isolate margin -dia 3
        cncjob margin_iso
    """

    # array of all command aliases, to be able use  old names for backward compatibility (add_poly, add_polygon)
    aliases = ['cncjob']

    description = '%s %s' % ("--", "Generates a CNC Job object from a Geometry Object.")

    # dictionary of types from Tcl command, needs to be ordered
    arg_names = collections.OrderedDict([
        ('name', str)
    ])

    # dictionary of types from Tcl command, needs to be ordered , this  is  for options  like -optionname value
    option_types = collections.OrderedDict([
        ('dia', float),
        ('z_cut', float),
        ('z_move', float),
        ('feedrate', float),
        ('feedrate_z', float),
        ('feedrate_rapid', float),
        ('extracut_length', float),
        ('dpp', float),
        ('toolchangez', float),
        ('toolchangexy', tuple),
        ('startz', float),
        ('endz', float),
        ('spindlespeed', int),
        ('dwelltime', float),
        ('pp', str),
        ('muted', str),
        ('outname', str)
    ])

    # array of mandatory options for current Tcl command: required = {'name','outname'}
    required = []

    # structured help for current command, args needs to be ordered
    help = {
        'main': "Generates a CNC Job object from a Geometry Object.",
        'args': collections.OrderedDict([
            ('name', 'Name of the source object.'),
            ('dia', 'Tool diameter to show on screen.'),
            ('z_cut', 'Z-axis cutting position.'),
            ('z_move', 'Z-axis moving position.'),
            ('feedrate', 'Moving speed on X-Y plane when cutting.'),
            ('feedrate_z', 'Moving speed on Z plane when cutting.'),
            ('feedrate_rapid', 'Rapid moving at speed when cutting.'),
            ('extracut_length', 'The value for extra cnccut over the first point in path,in the job end; float'),
            ('dpp', 'If present then use multidepth cnc cut. Height of one layer for multidepth.'),
            ('toolchangez', 'Z distance for toolchange (example: 30.0).\n'
                            'If used in the command then a toolchange event will be included in gcode'),
            ('toolchangexy', 'X, Y coordonates for toolchange in format (x, y) (example: (2.0, 3.1) ).'),
            ('startz', 'Height before the first move.'),
            ('endz', 'Height where the last move will park.'),
            ('spindlespeed', 'Speed of the spindle in rpm (example: 4000).'),
            ('dwelltime', 'Time to pause to allow the spindle to reach the full speed.\n'
                          'If it is not used in command then it will not be included'),
            ('outname', 'Name of the resulting Geometry object.'),
            ('pp', 'Name of the Geometry preprocessor. No quotes, case sensitive'),
            ('muted', 'It will not put errors in the Shell. Can be True (1) or False (0)')
        ]),
        'examples': ['cncjob geo_name -dia 0.5 -z_cut -1.7 -z_move 2 -feedrate 120 -pp default']
    }

    def execute(self, args, unnamed_args):
        """
        execute current TCL shell command

        :param args: array of known named arguments and options
        :param unnamed_args: array of other values which were passed into command
            without -somename and  we do not have them in known arg_names
        :return: None or exception
        """

        name = ''

        if 'muted' in args:
            try:
                par = args['muted'].capitalize()
            except AttributeError:
                par = args['muted']
            muted = bool(eval(par))
        else:
            muted = False

        try:
            name = args['name']
        except KeyError:
            if muted is False:
                self.raise_tcl_error("Object name is missing")
            else:
                return "fail"

        if 'outname' not in args:
            args['outname'] = str(name) + "_cnc"

        obj = self.app.collection.get_by_name(str(name), isCaseSensitive=False)

        if obj is None:
            if muted is False:
                self.raise_tcl_error("Object not found: %s" % str(name))
            else:
                return "fail"

        if obj.kind != 'geometry':
            if muted is False:
                self.raise_tcl_error('Expected GeometryObject, got %s %s.' % (str(name), type(obj)))
            else:
                return

        args["dia"] = args["dia"] if "dia" in args and args["dia"] else obj.options["cnctooldia"]

        args["z_cut"] = args["z_cut"] if "z_cut" in args and args["z_cut"] else obj.options["cutz"]
        args["z_move"] = args["z_move"] if "z_move" in args and args["z_move"] else obj.options["travelz"]

        args["feedrate"] = args["feedrate"] if "feedrate" in args and args["feedrate"] else obj.options["feedrate"]
        args["feedrate_z"] = args["feedrate_z"] if "feedrate_z" in args and args["feedrate_z"] else \
            obj.options["feedrate_z"]
        args["feedrate_rapid"] = args["feedrate_rapid"] if "feedrate_rapid" in args and args["feedrate_rapid"] else \
            obj.options["feedrate_rapid"]

        if "extracut_length" in args:
            args["extracut"] = True
            if args["extracut_length"] is None:
                args["extracut_length"] = 0.0
            else:
                args["extracut_length"] = float(args["extracut_length"])
        else:
            args["extracut"] = False

        if "dpp" in args:
            args["multidepth"] = True
            if args["dpp"] is None:
                args["dpp"] = obj.options["dpp"]
            else:
                args["dpp"] = float(args["dpp"])
        else:
            args["multidepth"] = False

        args["startz"] = args["startz"] if "startz" in args and args["startz"] else \
            self.app.defaults["geometry_startz"]
        args["endz"] = args["endz"] if "endz" in args and args["endz"] else obj.options["endz"]

        args["spindlespeed"] = args["spindlespeed"] if "spindlespeed" in args and args["spindlespeed"] != 0 else None

        if 'dwelltime' in args:
            args["dwell"] = True
            if args['dwelltime'] is None:
                args["dwelltime"] = float(obj.options["dwelltime"])
            else:
                args["dwelltime"] = float(args['dwelltime'])
        else:
            args["dwell"] = False
            args["dwelltime"] = 0.0

        args["pp"] = args["pp"] if "pp" in args and args["pp"] else obj.options["ppname_g"]

        if "toolchangez" in args:
            args["toolchange"] = True
            if args["toolchangez"] is not None:
                args["toolchangez"] = args["toolchangez"]
            else:
                args["toolchangez"] = obj.options["toolchangez"]
        else:
            args["toolchange"] = False
            args["toolchangez"] = 0.0

        args["toolchangexy"] = args["toolchangexy"] if "toolchangexy" in args and args["toolchangexy"] else \
            self.app.defaults["geometry_toolchangexy"]

        del args['name']

        for arg in args:
            if arg == "toolchange_xy" or arg == "spindlespeed" or arg == "startz":
                continue
            else:
                if args[arg] is None:
                    print(arg, args[arg])
                    if muted is False:
                        self.raise_tcl_error('One of the command parameters that have to be not None, is None.\n'
                                             'The parameter that is None is in the default values found in the list \n'
                                             'generated by the TclCommand "list_sys geom". or in the arguments.')
                    else:
                        return

        # HACK !!! Should be solved elsewhere!!!
        # default option for multidepth is False
        obj.options['multidepth'] = False

        if not obj.multigeo:
            obj.generatecncjob(use_thread=False, plot=False, **args)
        else:
            # Update the local_tools_dict values with the args value
            local_tools_dict = deepcopy(obj.tools)

            for tool_uid in list(local_tools_dict.keys()):
                if 'data' in local_tools_dict[tool_uid]:
                    local_tools_dict[tool_uid]['data']['cutz'] = args["z_cut"]
                    local_tools_dict[tool_uid]['data']['travelz'] = args["z_move"]
                    local_tools_dict[tool_uid]['data']['feedrate'] = args["feedrate"]
                    local_tools_dict[tool_uid]['data']['feedrate_z'] = args["feedrate_z"]
                    local_tools_dict[tool_uid]['data']['feedrate_rapid'] = args["feedrate_rapid"]
                    local_tools_dict[tool_uid]['data']['multidepth'] = args["multidepth"]
                    local_tools_dict[tool_uid]['data']['extracut'] = args["extracut"]

                    if args["extracut"] is True:
                        local_tools_dict[tool_uid]['data']['extracut_length'] = args["extracut_length"]
                    else:
                        local_tools_dict[tool_uid]['data']['extracut_length'] = None

                    local_tools_dict[tool_uid]['data']['depthperpass'] = args["dpp"]
                    local_tools_dict[tool_uid]['data']['toolchange'] = args["toolchange"]
                    local_tools_dict[tool_uid]['data']['toolchangez'] = args["toolchangez"]
                    local_tools_dict[tool_uid]['data']['toolchangexy'] = args["toolchangexy"]
                    local_tools_dict[tool_uid]['data']['startz'] = args["startz"]
                    local_tools_dict[tool_uid]['data']['endz'] = args["endz"]
                    local_tools_dict[tool_uid]['data']['spindlespeed'] = args["spindlespeed"]
                    local_tools_dict[tool_uid]['data']['dwell'] = args["dwell"]
                    local_tools_dict[tool_uid]['data']['dwelltime'] = args["dwelltime"]
                    local_tools_dict[tool_uid]['data']['ppname_g'] = args["pp"]
            obj.mtool_gen_cncjob(
                outname=args['outname'],
                tools_dict=local_tools_dict,
                tools_in_use=[],
                use_thread=False,
                plot=False)
            # self.raise_tcl_error('The object is a multi-geo geometry which is not supported in cncjob Tcl Command')
