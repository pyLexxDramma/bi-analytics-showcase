from app.services.default_filters_web import (
    format_filter_value_display,
    report_display_name,
    report_name_matches,
)


def test_report_display_name_nav_id():
    assert report_display_name("developer-projects") == "Девелоперские проекты"
    assert report_display_name("prescriptions") == "Предписания по подрядчикам"
    assert report_display_name("project-schedule") == "График проекта"


def test_report_display_name_keeps_readable_title():
    assert report_display_name("Девелоперские проекты") == "Девелоперские проекты"


def test_report_display_name_garbled_cyrillic():
    stored = "".join("?" if ch.isalpha() else ch for ch in "Утвержденный бюджет")
    assert report_display_name(stored) == "Утверждённый бюджет план/факт"

    prescriptions = "".join(
        "?" if ch.isalpha() else ch for ch in "Предписания по строительству"
    )
    assert report_display_name(prescriptions) == "Предписания по подрядчикам"

    schedule = "".join("?" if ch.isalpha() else ch for ch in "График проекта")
    assert report_display_name(schedule) == "График проекта"

    sroki = "".join("?" if ch.isalpha() else ch for ch in "Сроки проекта")
    assert sroki == "????? ???????"
    assert report_display_name(sroki) == "Сроки проекта"


def test_format_filter_value_json_list():
    assert (
        format_filter_value_display('["Есипово-5", "Дмитровский"]')
        == "Есипово-5, Дмитровский"
    )
    assert format_filter_value_display("Дмитровский") == "Дмитровский"
    assert format_filter_value_display("['Есипово-5', 'Дмитровский']") == (
        "Есипово-5, Дмитровский"
    )
    assert format_filter_value_display(None) == ""


def test_report_name_matches_aliases():
    assert report_name_matches("developer-projects", "Девелоперские проекты")
    assert report_name_matches("Девелоперские проекты", "developer-projects")
    schedule = "".join("?" if ch.isalpha() else ch for ch in "График проекта")
    assert report_name_matches(schedule, "График проекта")
    assert not report_name_matches("prescriptions", "Девелоперские проекты")
