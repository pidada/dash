from __future__ import unicode_literals
import os
import sys
import json
import string
import shutil
import logging
from builtins import input  # pylint: disable=redefined-builtin
import coloredlogs
import fire

from .._utils import run_command_with_process, compute_md5, job

logger = logging.getLogger(__name__)
coloredlogs.install(
    fmt="%(asctime)s,%(msecs)03d %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)


class BuildProcess(object):
    def __init__(self, main, deps_info):
        self.main = main
        self.deps_info = deps_info
        self.package_lock = self._concat(self.main, "package-lock.json")
        self.npm_modules = self._concat(self.main, "node_modules")
        self._parse_package()
        self.asset_paths = (self.build_folder, self.npm_modules)

    def _parse_package(self):
        with open(self.package_lock, "r") as fp:
            package = json.load(fp)
            self.version = package["version"]
            self.name = package["name"]
            self.build_folder = self._concat(
                self.main, self.name.replace("-", "_")
            )
            self.deps = package["dependencies"]

    @staticmethod
    def _concat(*paths):
        return os.path.realpath(
            os.path.sep.join((path for path in paths if path))
        )

    @staticmethod
    def _clean_path(path):
        if os.path.exists(path):
            logger.warning("🚨 %s already exists, remove it!", path)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                if os.path.isdir(path):
                    shutil.rmtree(path)
            except OSError:
                sys.exit(1)
        else:
            logger.warning("🚨 %s doesn't exist, no action taken", path)

    @job("clean all the previous assets generated by build tool")
    def clean(self):
        for path in self.asset_paths:
            self._clean_path(path)

    @job("run `npm i --ignore-scripts`")
    def npm(self):
        """job to install npm packages"""
        os.chdir(self.main)
        self._clean_path(self.package_lock)
        run_command_with_process("npm i --ignore-scripts")

    @job("build the renderer in dev mode")
    def watch(self):
        os.chdir(self.main)
        os.system("npm run build:dev")

    @job("run the full building process")
    def build(self):
        self.clean()
        self.npm()
        self.bundles()
        self.digest()

    @job("compute the hash digest for assets")
    def digest(self):
        copies = (
            _
            for _ in os.listdir(self.build_folder)
            if os.path.splitext(_)[-1] in {".js", ".map"}
        )
        logger.info("bundles in %s %s", self.build_folder, copies)

        payload = {self.name: self.version}
        for copy in copies:
            payload["MD5 ({})".format(copy)] = compute_md5(
                self._concat(self.build_folder, copy)
            )

        with open(self._concat(self.main, "digest.json"), "w") as fp:
            json.dump(
                payload, fp, sort_keys=True, indent=4, separators=(",", ":")
            )
        logger.info(
            "bundle digest in digest.json:\n%s",
            json.dumps(payload, sort_keys=True, indent=4),
        )

    @job("copy and generate the bundles")
    def bundles(self):
        if not os.path.exists(self.build_folder):
            try:
                os.makedirs(self.build_folder)
            except OSError:
                logger.exception(
                    "🚨 having issues manipulating %s", self.build_folder
                )
                sys.exit(1)

        if self.__class__.__name__ == "DCC":
            shutil.copyfile(
                self._concat(self.main, "assets", "highlight.pack.js"),
                self._concat(self.build_folder, "highlight.pack.js"),
            )
            logger.info("copy the customized highligh js")

        versions = {
            "version": self.version,
            "package": self.name.replace(" ", "_").replace("-", "_"),
        }
        for name, subfolder, filename, target in self.deps_info:
            version = self.deps[name]["version"]
            versions[name.replace("-", "").replace(".", "")] = version

            logger.info("copy npm dependency => %s", filename)
            ext = "min.js" if "min" in filename.split(".") else "js"
            target = (
                target.format(version)
                if target
                else "{}@{}.{}".format(name, version, ext)
            )
            shutil.copyfile(
                self._concat(self.npm_modules, name, subfolder, filename),
                self._concat(self.build_folder, target),
            )

        logger.info("run `npm run build:webpack`")
        os.chdir(self.main)
        run_command_with_process("npm run build:webpack")

        logger.info("generate the `__init__.py` from template and verisons")
        with open(self._concat(self.main, "init.template")) as fp:
            t = string.Template(fp.read())

        with open(self._concat(self.build_folder, "__init__.py"), "w") as fp:
            fp.write(t.safe_substitute(versions))


class Renderer(BuildProcess):
    def __init__(self):
        # dash-renderer's path is binding with the dash folder hierarchy
        super(Renderer, self).__init__(
            self._concat(
                os.path.abspath(__file__),
                os.pardir,
                os.pardir,
                os.pardir,
                "dash-renderer",
            ),
            (
                ("react", "umd", "react.production.min.js", None),
                ("react", "umd", "react.development.js", None),
                ("react-dom", "umd", "react-dom.production.min.js", None),
                ("react-dom", "umd", "react-dom.development.js", None),
                ("prop-types", None, "prop-types.min.js", None),
                ("prop-types", None, "prop-types.js", None),
            ),
        )


class DCC(BuildProcess):
    def __init__(self, main=None):
        main = (
            os.path.abspath(os.path.expanduser(main)) if main else os.getcwd()
        )
        logger.info("start the build process at %s", main)
        if os.path.basename(main) != "dash-core-components":
            logger.warning(
                "⚡ the working folder is not `dash-core-components`. "
                "Unexpected file operation might happen if we are running the "
                "process in a wrong place. Try run `dcc build --main={path}` "
                "or go to the DCC root then execute `dcc build`."
            )
            if input("do you want to continue? yes/no\n").lower() != "yes":
                sys.exit(1)

        super(DCC, self).__init__(
            main, (("plotly.js-dist", None, "plotly.js", "plotly-{}.min.js"),)
        )
        self.asset_paths = self.asset_paths + (
            self._concat(self.main, "R"),
            self._concat(self.main, "inst"),
        )


def renderer():
    fire.Fire(Renderer)


def dcc():
    fire.Fire(DCC)
