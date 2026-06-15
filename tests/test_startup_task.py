import unittest

from src.services.startup_task import (
    build_register_startup_task_script,
    build_startup_vbs_script,
    quote_powershell_string,
)


class StartupTaskTests(unittest.TestCase):
    def test_powershell_quote_escapes_single_quotes(self):
        self.assertEqual(quote_powershell_string(r"C:\App Bob's\app.exe"), "'C:\\App Bob''s\\app.exe'")

    def test_register_script_sets_executable_working_directory_and_delay(self):
        script = build_register_startup_task_script(
            task_name="数智家校放学系统",
            executable_path=r"D:\数智家校放学系统\数智家校放学系统.exe",
            working_directory=r"D:\数智家校放学系统",
        )

        self.assertIn("New-ScheduledTaskAction", script)
        self.assertIn("-Execute 'D:\\数智家校放学系统\\数智家校放学系统.exe'", script)
        self.assertIn("-WorkingDirectory 'D:\\数智家校放学系统'", script)
        self.assertIn("$Trigger.Delay = 'PT30S'", script)
        self.assertIn("Register-ScheduledTask", script)
        self.assertIn("-TaskName '数智家校放学系统'", script)
        self.assertIn("数智家校放学系统开机自启", script)
        self.assertIn("-Force", script)

    def test_startup_vbs_sets_working_directory_and_delays_launch(self):
        script = build_startup_vbs_script(
            executable_path=r"D:\数智家校放学系统\数智家校放学系统.exe",
            working_directory=r"D:\数智家校放学系统",
            delay_milliseconds=30000,
        )

        self.assertIn("WScript.Sleep 30000", script)
        self.assertIn('WshShell.CurrentDirectory = "D:\\数智家校放学系统"', script)
        self.assertIn(
            'WshShell.Run """D:\\数智家校放学系统\\数智家校放学系统.exe"""',
            script,
        )


if __name__ == "__main__":
    unittest.main()
