import sys
import autobuild.autobuild_main
from tests.basetest import BaseTest

captured_stdout = ""

class EarlyExitException(Exception):
    pass

class CatchStdOut:
    def write(self, text):
        global captured_stdout
        captured_stdout += text

class TestOptions(BaseTest):
    def setUp(self):
        super().setUp()
        global captured_stdout
        captured_stdout = ""
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.old_exit = sys.exit
        sys.stdout = CatchStdOut()
        sys.stderr = CatchStdOut()
        self.autobuild_fixture = autobuild.autobuild_main.Autobuild()

        def mock_exit(value=None, message=None):
            if message:
                print(message)
            raise EarlyExitException()

        self.autobuild_fixture.exit = mock_exit
        self.autobuild_fixture.parser.exit = mock_exit
        sys.exit = mock_exit

    def tearDown(self):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr
        sys.exit = self.old_exit
        super().tearDown()

    def test_empty_options(self):
        """no options: should print usage and exit"""
        with self.assertRaises(EarlyExitException):
            self.autobuild_fixture.main([])
        self.assertIn("usage:", captured_stdout)

    def test_typo_subtool(self):
        """invalid subtool name: should print usage and exit"""
        with self.assertRaises(EarlyExitException):
            self.autobuild_fixture.main(["foobardribble"])
        self.assertIn("usage:", captured_stdout)

    def test_version(self):
        """-v should print version and exit"""
        with self.assertRaises(EarlyExitException):
            self.autobuild_fixture.main(["-v"])
        self.assertIn("autobuild", captured_stdout)

    def test_tool_register(self):
        """check if autobuild_tool_test.py is registered"""
        with self.assertRaises(EarlyExitException):
            self.autobuild_fixture.main(["build", "-h"])
        self.assertIn("an option to pass to the build command", captured_stdout)

    def test_tool_search_for_tools(self):
        """--help should show tool info"""
        with self.assertRaises(EarlyExitException):
            self.autobuild_fixture.main(["--help"])
        self.assertIn("Builds platform targets.", captured_stdout)
