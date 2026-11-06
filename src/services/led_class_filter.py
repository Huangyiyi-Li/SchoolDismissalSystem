"""Administrative display selection shared by LED, preview and desktop output."""


def filter_admin_classes(classes, grade_filter_mode='all', visible_grades=(),
                         visible_classes_by_grade=None):
    selected_grades = {str(g).strip() for g in visible_grades}
    # Missing grade means all its classes, including classes added by a later sync.
    selections = {grade: set(ids) for grade, ids in (visible_classes_by_grade or {}).items()}
    result = []
    for item in classes:
        grade = str(item.get('grade_name') or '').strip()
        if grade_filter_mode == 'selected' and grade not in selected_grades:
            continue
        if grade in selections and str(item.get('class_id') or '').strip() not in selections[grade]:
            continue
        result.append(item)
    return result
