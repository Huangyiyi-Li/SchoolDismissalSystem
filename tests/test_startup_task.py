import unittest

from src.services.startup_task import build_register_startup_task_script, quote_powershell_string


class StartupTaskTests(unittest.TestCase):
    def test_powershell_quote_escapes_single_quotes(self):
        self.assertEqual(quote_powershell_string(r"C:\App Bob's\app.exe"), "'C:\\App Bob''s\\app.exe'")

    def test_register_script_sets_executable_working_directory_and_delay(self):
        script = build_register_startup_task_script(
            task_name="SchoolDismissalSystem",
            executable_path=r"D:\SchoolDismissalSystem\SchoolDismissalSystem.exe",
            working_directory=r"D:\SchoolDismissalSystem",
        )

        self.assertIn("New-ScheduledTaskAction", script)
        self.assertIn("-Execute 'D:\\SchoolDismissalSystem\\SchoolDismissalSystem.exe'", script)
        self.assertIn("-WorkingDirectory 'D:\\SchoolDismissalSystem'", script)
        self.assertIn("$Trigger.Delay = 'PT30S'", script)
        self.assertIn("Register-ScheduledTask", script)
        self.assertIn("-TaskName 'SchoolDismissalSystem'", script)
        self.assertIn("-Force", script)


if __name__ == "__main__":
    unittest.main()
