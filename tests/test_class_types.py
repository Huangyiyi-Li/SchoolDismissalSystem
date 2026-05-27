import unittest

from src.services.class_types import (
    format_class_type_label,
    format_class_type_section_title,
)


class ClassTypeTests(unittest.TestCase):
    def test_known_class_types_use_business_names(self):
        self.assertEqual(format_class_type_label(1), "行政班")
        self.assertEqual(format_class_type_label(2), "社团班")
        self.assertEqual(format_class_type_section_title(1), "行政班放学时段")
        self.assertEqual(format_class_type_section_title(2), "社团班放学时段")

    def test_unknown_class_type_is_explicit(self):
        self.assertEqual(format_class_type_label(None), "未知类型")
        self.assertEqual(format_class_type_label(9), "类型9")


if __name__ == "__main__":
    unittest.main()
