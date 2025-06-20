#!/usr/bin/env python3

# Python 3.13 06/20/2025
import argparse
import glob
import importlib
import importlib.util
import logging
import os
import sys
from pathlib import Path

from autobuild import common
from autobuild.common import AutobuildError

# Environment variable name used for default log level verbosity
AUTOBUILD_LOGLEVEL = "AUTOBUILD_LOGLEVEL"

_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


class RunHelp(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        parser.parent.search_for_and_import_tools(parser.parent.tools_list)
        parser.parent.register_tools(parser.parent.tools_list)
        print(parser.format_help())
        parser.exit(0)


class Version(argparse.Action):
    """
    Like argparse's action='version', but prints to stdout instead of stderr.
    """

    def __init__(
        self,
        option_strings,
        version=None,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        help="show program's version number and exit",
        **kwds,
    ):
        super(Version, self).__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
            **kwds,
        )
        self.version = version

    def __call__(self, parser, namespace, values, option_string=None):
        formatter = parser._get_formatter()
        formatter.add_text(self.version or parser.version)
        print(formatter.format_help())
        parser.exit(message="")


class Autobuild:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description="Autobuild", prog="autobuild", add_help=False
        )

        self.parser.add_argument(
            "-V",
            "--version",
            action=Version,
            version="%%(prog)s %s" % common.AUTOBUILD_VERSION_STRING,
        )

        self.subparsers = self.parser.add_subparsers(
            title="Sub Commands",
            description="Valid Sub Commands",
            help="Sub Command help",
        )

    def listdir(self, dir):
        files = os.listdir(dir)
        if "AutobuildTool_test.py" in files:
            files.remove("AutobuildTool_test.py")
        return files

    def register_tool(self, tool):
        newtool = tool.AutobuildTool()
        details = newtool.get_details()
        self.new_tool_subparser = self.subparsers.add_parser(
            details["name"], help=details["description"]
        )
        newtool.register(self.new_tool_subparser)
        return newtool

    def register_tools(self, tools_list):
        for tool in tools_list:
            self.register_tool(tool)

    def search_for_and_import_tools(self, tools_list):
        for file_name in glob.glob(os.path.join(_SCRIPT_DIR, "autobuild_tool_*.py")):
            module_name = Path(file_name).stem
            possible_tool_module = importlib.import_module(
                f".{module_name}", package="autobuild"
            )
            if hasattr(possible_tool_module, "AutobuildTool"):
                tools_list.append(possible_tool_module)

    def try_to_import_tool(self, tool, tools_list):
        try:
            possible_tool_module = importlib.import_module(
                f".autobuild_tool_{tool}", package="autobuild"
            )
            if hasattr(possible_tool_module, "AutobuildTool"):
                tools_list.append(possible_tool_module)
                instance = self.register_tool(possible_tool_module)
                return instance
        except ImportError:
            pass
        return -1

    def get_default_loglevel_from_environment(self):
        try:
            environment_level = os.environ[AUTOBUILD_LOGLEVEL]
        except KeyError:
            environment_level = ""

        if environment_level in ("--quiet", "-q"):
            return logging.ERROR
        elif environment_level == "":
            return logging.WARNING
        elif environment_level in ("--verbose", "-v"):
            return logging.INFO
        elif environment_level in ("--debug", "-d"):
            return logging.DEBUG
        else:
            raise AutobuildError(
                f"invalid {AUTOBUILD_LOGLEVEL} value '{environment_level}'"
            )

    def set_recursive_loglevel(self, logger, level):
        logger.setLevel(level)
        level_map = {
            logging.ERROR: "--quiet",
            logging.WARNING: "",
            logging.INFO: "--verbose",
            logging.DEBUG: "--debug",
        }
        if level in level_map:
            os.environ[AUTOBUILD_LOGLEVEL] = level_map[level]
        else:
            raise common.AutobuildError(
                f"invalid effective log level {logging.getLevelName(level)}"
            )

    def main(self, args_in):
        logger = logging.getLogger("autobuild")
        logger.addHandler(logging.StreamHandler())
        default_loglevel = self.get_default_loglevel_from_environment()

        self.tools_list = []

        self.parser.parent = self
        self.parser.add_argument(
            "-h",
            "--help",
            help="find all valid Autobuild Tools and show help",
            action=RunHelp,
            nargs="?",
            default=argparse.SUPPRESS,
        )

        argdefs = (
            (
                (
                    "-n",
                    "--dry-run",
                ),
                dict(help="run tool in dry run mode if available", action="store_true"),
            ),
            (
                (
                    "-q",
                    "--quiet",
                ),
                dict(
                    help="minimal output",
                    action="store_const",
                    const=logging.ERROR,
                    dest="logging_level",
                    default=default_loglevel,
                ),
            ),
            (
                (
                    "-v",
                    "--verbose",
                ),
                dict(
                    help="verbose output",
                    action="store_const",
                    const=logging.INFO,
                    dest="logging_level",
                ),
            ),
            (
                (
                    "-d",
                    "--debug",
                ),
                dict(
                    help="debug output",
                    action="store_const",
                    const=logging.DEBUG,
                    dest="logging_level",
                ),
            ),
            (
                (
                    "-p",
                    "--platform",
                ),
                dict(
                    default=None,
                    dest="platform",
                    help=f'may only be the current platform or "{common.PLATFORM_COMMON}"',
                ),
            ),
            (
                (
                    "-A",
                    "--address-size",
                ),
                dict(
                    choices=[32, 64],
                    type=int,
                    default=int(
                        os.environ.get("AUTOBUILD_ADDRSIZE", common.DEFAULT_ADDRSIZE)
                    ),
                    dest="addrsize",
                    help="specify address size (modifies platform)",
                ),
            ),
        )

        for args, kwds in argdefs:
            self.parser.add_argument(*args, **kwds)

        tool_to_run = -1

        for arg in args_in:
            if not arg.startswith("-"):
                tool_to_run = self.try_to_import_tool(arg, self.tools_list)
                if tool_to_run != -1:
                    for args, kwds in argdefs:
                        self.new_tool_subparser.add_argument(*args, **kwds)
                break

        args = self.parser.parse_args(args_in)

        loglevel = (
            logging.INFO
            if args.dry_run and args.logging_level != logging.DEBUG
            else args.logging_level
        )
        self.set_recursive_loglevel(logger, loglevel)

        # establish platform and address options and related environment variables
        platform = common.establish_platform(args.platform, addrsize=args.addrsize)
        print(f"[DEBUG] Established platform: {platform}")

        if tool_to_run != -1:
            tool_to_run.run(args)
        else:
            self.parser.print_help()
            self.parser.error("no command specified")

        return 0


def main():
    script_path = os.path.dirname(common.get_autobuild_executable_path())
    logger = logging.getLogger("autobuild")

    try:
        os.environ["PATH"] = common.dedup_path(
            os.pathsep.join((os.environ.get("PATH", ""), script_path))
        )
        sys.exit(Autobuild().main(sys.argv[1:]))
    except KeyboardInterrupt as e:
        print(f"[DEBUG] User aborted with: {e}")
        sys.exit("Aborted...")
    except common.AutobuildError as e:
        if logger.getEffectiveLevel() <= logging.DEBUG:
            logger.exception(str(e))
        msg = ["ERROR: ", str(e)]
        if logger.getEffectiveLevel() > logging.DEBUG:
            msg.append("\nFor more information: try re-running your command with")
            if logger.getEffectiveLevel() > logging.INFO:
                msg.append(" --verbose or")
            msg.append(" --debug")
        print(f"[DEBUG] AutobuildError: {e}")
        sys.exit("".join(msg))


if __name__ == "__main__":
    main()
